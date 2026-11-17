"""Run an Agents v2 prompt agent with a gateway-connected model."""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import OpenAIError
from openai.types.responses import Response


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    model: str

    @property
    def connection_name(self) -> str:
        return self.model.split("/", 1)[0]

    @classmethod
    def from_env(cls, environment: Mapping[str, str]) -> "Settings":
        endpoint = (
            (
                environment.get("FOUNDRY_PROJECT_ENDPOINT")
                or environment.get("AI_FOUNDRY_PROJECT_ENDPOINT", "")
            )
            .strip()
            .rstrip("/")
        )
        model = environment.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "").strip()
        if not endpoint or "<" in endpoint or ">" in endpoint:
            raise ValueError(
                "Set FOUNDRY_PROJECT_ENDPOINT to your Foundry project endpoint."
            )
        parsed = urlsplit(endpoint)
        path = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or len(path) != 3
            or path[:2] != ["api", "projects"]
            or not path[2]
        ):
            raise ValueError(
                "Use an HTTPS project endpoint ending in /api/projects/<project-name>."
            )
        connection, separator, upstream_model = model.partition("/")
        if (
            not separator
            or not connection
            or not upstream_model
            or upstream_model.startswith("/")
            or model.endswith("/")
            or any(character.isspace() for character in model)
            or any(character in model for character in "<>?#")
        ):
            raise ValueError(
                "Set FOUNDRY_MODEL_DEPLOYMENT_NAME to <connection-name>/<model-name>."
            )
        return cls(project_endpoint=endpoint, model=model)


def gateway_request(
    settings: Settings, environment: Mapping[str, str]
) -> tuple[str, dict, dict]:
    base_url = environment.get("BYOM_GATEWAY_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "<" in base_url
        or not parsed.path.endswith("/openai/v1")
    ):
        raise ValueError(
            "Set BYOM_GATEWAY_BASE_URL to an HTTPS base URL ending in /openai/v1."
        )
    api_key = environment.get("BYOM_GATEWAY_API_KEY", "").strip()
    if not api_key or "<" in api_key:
        raise ValueError(
            "Set BYOM_GATEWAY_API_KEY for the optional direct gateway check."
        )
    header = environment.get("BYOM_GATEWAY_KEY_HEADER", "Ocp-Apim-Subscription-Key")
    value_format = environment.get("BYOM_GATEWAY_KEY_FORMAT", "{api_key}")
    if "{api_key}" not in value_format:
        raise ValueError("BYOM_GATEWAY_KEY_FORMAT must contain {api_key}.")
    return (
        base_url + "/chat/completions",
        {header: value_format.replace("{api_key}", api_key)},
        {
            "model": settings.model.split("/", 1)[1],
            "messages": [{"role": "user", "content": "Reply with BYOM_GATEWAY_OK."}],
            "max_tokens": 64,
        },
    )


def check_gateway(settings: Settings, environment: Mapping[str, str]) -> None:
    url, headers, payload = gateway_request(settings, environment)
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Gateway returned HTTP {response.status_code}; inspect gateway logs."
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError(
                "Gateway did not return an OpenAI Chat Completions response."
            ) from error
        if not isinstance(content, str) or "BYOM_GATEWAY_OK" not in content:
            raise RuntimeError("Gateway response did not contain BYOM_GATEWAY_OK.")
    print("PASS: direct gateway Chat Completions request")


def check_connection(project: AIProjectClient, settings: Settings) -> None:
    connection = project.connections.get(
        name=settings.connection_name, include_credentials=False
    )
    connection_type = getattr(connection.type, "value", connection.type)
    if connection_type not in {"ApiManagement", "ModelGateway"}:
        raise RuntimeError(
            "The selected connection is not an ApiManagement or ModelGateway connection."
        )
    print(f"PASS: {connection_type} connection found ({settings.connection_name})")


def require_text(response: Response, expected: str) -> str:
    if response.status != "completed":
        raise RuntimeError(
            f"Response {response.id} did not complete (status={response.status})."
        )
    text = response.output_text
    if not text or expected not in text:
        raise RuntimeError(
            f"Response {response.id} did not contain the expected verification value."
        )
    return text


def tool_outputs(response: Response, verification: str) -> list[dict[str, str]]:
    outputs = []
    for item in response.output:
        if item.type != "function_call":
            continue
        if item.name != "get_order_status":
            raise RuntimeError("The model requested an unexpected tool.")
        arguments = json.loads(item.arguments)
        if arguments != {"order_id": "ORDER-1001"}:
            raise ValueError("The model supplied unexpected order lookup arguments.")
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": json.dumps(
                    {
                        "order_id": "ORDER-1001",
                        "status": "shipped",
                        "verification": verification,
                    }
                ),
            }
        )
    if not outputs:
        raise RuntimeError(
            "No function call returned; the BYOM model must support tool calling."
        )
    return outputs


def run_agent(
    project: AIProjectClient,
    settings: Settings,
    *,
    with_tools: bool = True,
    keep: bool = False,
) -> dict[str, Any]:
    agent_name = "byom-demo-" + uuid4().hex[:12]
    tools = (
        [
            FunctionTool(
                name="get_order_status",
                description="Look up a synthetic order's status and verification value.",
                parameters={
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                    "required": ["order_id"],
                    "additionalProperties": False,
                },
                strict=True,
            )
        ]
        if with_tools
        else []
    )
    with ExitStack() as cleanup:
        agent = project.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=settings.model,
                instructions=(
                    "You are a synthetic order-support test agent. Follow the user's output instructions. "
                    "For order questions always call get_order_status. Never invent order data. "
                    "Include the status and the exact verification value returned by the tool."
                ),
                tools=tools,
            ),
        )
        if not keep:
            cleanup.callback(
                project.agents.delete_version,
                agent_name=agent.name,
                agent_version=agent.version,
            )
        print(f"Created agent: {agent.name}, version: {agent.version}")
        saved = project.agents.get_version(
            agent_name=agent.name, agent_version=agent.version
        )
        if saved.definition.model != settings.model:
            raise RuntimeError(
                "Agent read-back does not reference the configured connected model."
            )
        print("PASS: saved agent references the connected model")
        client = cleanup.enter_context(
            project.get_openai_client(timeout=90, max_retries=0)
        )
        conversation = client.conversations.create()
        if not keep:
            cleanup.callback(
                client.conversations.delete, conversation_id=conversation.id
            )
        print(f"Created conversation: {conversation.id}")
        reference = {
            "agent_reference": {
                "name": agent.name,
                "version": agent.version,
                "type": "agent_reference",
            }
        }
        marker = "BYOM_OK_" + uuid4().hex[:12]
        response = client.responses.create(
            conversation=conversation.id,
            input=f"Reply with exactly this text and nothing else: {marker}",
            extra_body=reference,
            tool_choice="none",
        )
        require_text(response, marker)
        print(f"PASS: prompt response ({response.id})")
        if with_tools:
            response = client.responses.create(
                conversation=conversation.id,
                input="Look up ORDER-1001 using get_order_status. Include its status and verification value.",
                extra_body=reference,
                tool_choice={"type": "function", "name": "get_order_status"},
            )
            verification = "TOOL_OK_" + uuid4().hex
            outputs = tool_outputs(response, verification)
            response = client.responses.create(
                conversation=conversation.id,
                input=outputs,
                extra_body=reference,
                tool_choice="none",
            )
            require_text(response, verification)
            require_text(response, "shipped")
            print(f"PASS: function call and tool-result round trip ({response.id})")
        result = {
            "agent_name": agent.name,
            "agent_version": agent.version,
            "conversation_id": conversation.id,
            "response_id": response.id,
            "tools_tested": with_tools,
        }
    print(
        "Resources retained (--keep)."
        if keep
        else "PASS: temporary conversation and agent version deleted"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check-config",
        action="store_true",
        help="Validate settings without network access.",
    )
    modes.add_argument(
        "--check-connection",
        action="store_true",
        help="Read the connection without creating an agent.",
    )
    parser.add_argument(
        "--check-gateway",
        action="store_true",
        help="Also probe the gateway directly using its API key.",
    )
    parser.add_argument(
        "--skip-tools", action="store_true", help="Run only the prompt smoke test."
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary agent version and conversation, even on failure.",
    )
    arguments = parser.parse_args()
    load_dotenv(arguments.env_file, override=False)
    try:
        settings = Settings.from_env(os.environ)
        print(f"Connected model: {settings.model}")
        if arguments.check_config:
            if arguments.check_gateway:
                gateway_request(settings, os.environ)
            print("PASS: local configuration (no network requests)")
            return 0
        if arguments.check_gateway:
            check_gateway(settings, os.environ)
        with (
            DefaultAzureCredential(
                exclude_interactive_browser_credential=True
            ) as credential,
            AIProjectClient(
                endpoint=settings.project_endpoint,
                credential=credential,
                connection_timeout=15,
                read_timeout=90,
                retry_total=0,
            ) as project,
        ):
            check_connection(project, settings)
            if not arguments.check_connection:
                run_agent(
                    project,
                    settings,
                    with_tools=not arguments.skip_tools,
                    keep=arguments.keep,
                )
        return 0
    except (
        AzureError,
        OpenAIError,
        httpx.HTTPError,
        ValueError,
        RuntimeError,
    ) as error:
        status = getattr(error, "status_code", None)
        detail = (
            str(error)
            if isinstance(error, (ValueError, RuntimeError))
            else "See the README troubleshooting table and service logs."
        )
        print(
            f"FAIL: {type(error).__name__}"
            + (f" (HTTP {status})" if status else "")
            + f": {detail}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
