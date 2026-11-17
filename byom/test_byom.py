"""Offline regression tests; these never authenticate or call Azure."""

import io
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from main import (
    Settings,
    check_connection,
    check_gateway,
    gateway_request,
    run_agent,
    tool_outputs,
)
from main import (
    main as run_cli,
)
from openai import OpenAI


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/demo",
            "FOUNDRY_MODEL_DEPLOYMENT_NAME": "byom-gateway/external-model",
        }

    def test_connection_qualified_model(self):
        settings = Settings.from_env(self.environment)
        self.assertEqual(settings.connection_name, "byom-gateway")
        self.assertEqual(settings.model, "byom-gateway/external-model")

    def test_repository_endpoint_variable_is_supported(self):
        self.environment["AI_FOUNDRY_PROJECT_ENDPOINT"] = self.environment.pop(
            "FOUNDRY_PROJECT_ENDPOINT"
        )
        self.assertTrue(
            Settings.from_env(self.environment).project_endpoint.endswith("/demo")
        )

    def test_explicit_endpoint_takes_precedence(self):
        self.environment["AI_FOUNDRY_PROJECT_ENDPOINT"] = "https://ignored.invalid"
        self.assertIn(
            "example.services", Settings.from_env(self.environment).project_endpoint
        )

    def test_trailing_endpoint_slash_is_normalized(self):
        self.environment["FOUNDRY_PROJECT_ENDPOINT"] += "/"
        self.assertTrue(
            Settings.from_env(self.environment).project_endpoint.endswith("/demo")
        )

    def test_provider_qualified_upstream_model_is_preserved(self):
        self.environment["FOUNDRY_MODEL_DEPLOYMENT_NAME"] = "gateway/provider/model"
        self.assertEqual(
            Settings.from_env(self.environment).model, "gateway/provider/model"
        )

    def test_invalid_models_are_rejected(self):
        for model in (
            "",
            "gpt-4o",
            "/model",
            "connection/",
            "connection//model",
            "connection/model/",
            "connection/a b",
            "<connection>/<model>",
            "connection/model?key=value",
        ):
            with self.subTest(model=model), self.assertRaises(ValueError):
                Settings.from_env(
                    {**self.environment, "FOUNDRY_MODEL_DEPLOYMENT_NAME": model}
                )

    def test_invalid_endpoints_are_rejected(self):
        for endpoint in (
            "",
            "<your-project-endpoint>",
            "http://example.com/api/projects/demo",
            "https://example.com",
            "https://example.com/api/projects/",
            "https://example.com/api/projects/demo/responses",
            "https://user:secret@example.com/api/projects/demo",
            "https://example.com/api/projects/demo?api-key=secret",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                Settings.from_env(
                    {**self.environment, "FOUNDRY_PROJECT_ENDPOINT": endpoint}
                )


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            "https://example.services.ai.azure.com/api/projects/demo", "gateway/model"
        )
        self.project = MagicMock()
        self.project.connections.get.return_value.type = "ApiManagement"
        self.project.agents.create_version.return_value = SimpleNamespace(
            name="byom-test", version="1"
        )
        self.project.agents.get_version.return_value.definition.model = (
            self.settings.model
        )
        self.client = self.project.get_openai_client.return_value.__enter__.return_value
        self.client.conversations.create.return_value.id = "conv_test"
        self.tool_call = SimpleNamespace(
            type="function_call",
            name="get_order_status",
            arguments='{"order_id":"ORDER-1001"}',
            call_id="call_test",
        )

    def response(self, **arguments):
        prompt = arguments["input"]
        if isinstance(prompt, list):
            payload = json.loads(prompt[0]["output"])
            return SimpleNamespace(
                id="resp_final",
                status="completed",
                output_text=f"shipped {payload['verification']}",
                output=[],
            )
        if "exactly this text" in prompt:
            return SimpleNamespace(
                id="resp_prompt",
                status="completed",
                output_text=prompt.split(": ", 1)[1],
                output=[],
            )
        return SimpleNamespace(
            id="resp_tool", status="completed", output_text="", output=[self.tool_call]
        )

    def assert_cleaned_up(self):
        self.client.conversations.delete.assert_called_once_with(
            conversation_id="conv_test"
        )
        self.project.agents.delete_version.assert_called_once_with(
            agent_name="byom-test", agent_version="1"
        )

    def test_connection_lookup_does_not_fetch_credentials(self):
        check_connection(self.project, self.settings)
        self.project.connections.get.assert_called_once_with(
            name="gateway", include_credentials=False
        )

    def test_wrong_connection_type_fails_before_agent_creation(self):
        self.project.connections.get.return_value.type = "AzureOpenAI"
        with self.assertRaises(RuntimeError):
            check_connection(self.project, self.settings)
        self.project.agents.create_version.assert_not_called()

    def test_successful_prompt_and_tool_round_trip(self):
        self.client.responses.create.side_effect = self.response
        result = run_agent(self.project, self.settings)
        self.assertTrue(result["tools_tested"])
        self.assertEqual(self.client.responses.create.call_count, 3)
        definition = self.project.agents.create_version.call_args.kwargs[
            "definition"
        ].as_dict()
        self.assertEqual(definition["model"], "gateway/model")
        self.assertEqual(definition["tools"][0]["name"], "get_order_status")
        self.assertTrue(definition["tools"][0]["strict"])
        for request in self.client.responses.create.call_args_list:
            self.assertEqual(
                request.kwargs["extra_body"]["agent_reference"]["version"], "1"
            )
            self.assertEqual(request.kwargs["conversation"], "conv_test")
        self.assert_cleaned_up()

    def test_text_only_model(self):
        self.client.responses.create.side_effect = self.response
        result = run_agent(self.project, self.settings, with_tools=False)
        self.assertFalse(result["tools_tested"])
        self.assertEqual(self.client.responses.create.call_count, 1)
        self.assertEqual(
            self.project.agents.create_version.call_args.kwargs["definition"].tools, []
        )
        self.assert_cleaned_up()

    def test_real_openai_client_serializes_and_parses_the_flow(self):
        requests_seen = []

        def handle_request(request):
            requests_seen.append(request)
            if request.method == "DELETE":
                return httpx.Response(
                    200,
                    json={
                        "id": "conv_wire",
                        "object": "conversation.deleted",
                        "deleted": True,
                    },
                )
            if request.url.path.endswith("/conversations"):
                return httpx.Response(
                    200,
                    json={
                        "id": "conv_wire",
                        "object": "conversation",
                        "created_at": 1,
                        "metadata": {},
                    },
                )
            body = json.loads(request.content)
            self.assertEqual(
                body["agent_reference"],
                {"name": "byom-test", "version": "1", "type": "agent_reference"},
            )
            self.assertEqual(body["conversation"], "conv_wire")
            if isinstance(body["input"], list):
                tool_result = json.loads(body["input"][0]["output"])
                text = "shipped " + tool_result["verification"]
            elif "exactly this text" in body["input"]:
                text = body["input"].split(": ", 1)[1]
            else:
                return httpx.Response(
                    200,
                    json={
                        "id": "resp_wire_tool",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": "model",
                        "output": [
                            {
                                "type": "function_call",
                                "id": "fc_wire",
                                "call_id": "call_wire",
                                "name": "get_order_status",
                                "arguments": '{"order_id":"ORDER-1001"}',
                            }
                        ],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": "resp_wire",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "model",
                    "output": [
                        {
                            "type": "message",
                            "id": "msg_wire",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {"type": "output_text", "text": text, "annotations": []}
                            ],
                        }
                    ],
                },
            )

        self.project.get_openai_client.return_value = OpenAI(
            api_key="offline-test-key",
            base_url=self.settings.project_endpoint + "/openai/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handle_request)),
            max_retries=0,
        )
        result = run_agent(self.project, self.settings)
        self.assertTrue(result["tools_tested"])
        self.assertEqual(len(requests_seen), 5)
        self.assertEqual(requests_seen[-1].method, "DELETE")
        self.project.agents.delete_version.assert_called_once()

    def test_model_read_back_mismatch_still_deletes_version(self):
        self.project.agents.get_version.return_value.definition.model = "wrong/model"
        with self.assertRaises(RuntimeError):
            run_agent(self.project, self.settings)
        self.project.agents.delete_version.assert_called_once()
        self.client.conversations.create.assert_not_called()

    def test_request_failure_still_cleans_up(self):
        self.client.responses.create.side_effect = RuntimeError("Gateway unavailable")
        with self.assertRaises(RuntimeError):
            run_agent(self.project, self.settings)
        self.assert_cleaned_up()

    def test_conversation_failure_still_deletes_version(self):
        self.client.conversations.create.side_effect = RuntimeError(
            "Cannot create conversation"
        )
        with self.assertRaises(RuntimeError):
            run_agent(self.project, self.settings)
        self.project.agents.delete_version.assert_called_once()

    def test_cleanup_failure_does_not_skip_other_cleanup(self):
        self.client.responses.create.side_effect = self.response
        self.client.conversations.delete.side_effect = RuntimeError(
            "Cannot delete conversation"
        )
        with self.assertRaises(RuntimeError):
            run_agent(self.project, self.settings)
        self.project.agents.delete_version.assert_called_once()

    def test_keep_preserves_resources(self):
        self.client.responses.create.side_effect = self.response
        run_agent(self.project, self.settings, keep=True)
        self.client.conversations.delete.assert_not_called()
        self.project.agents.delete_version.assert_not_called()

    def test_missing_tool_call_is_a_failure(self):
        with self.assertRaisesRegex(RuntimeError, "No function call"):
            tool_outputs(SimpleNamespace(output=[]), "verification")

    def test_untrusted_tool_name_is_rejected(self):
        self.tool_call.name = "delete_order"
        with self.assertRaises(RuntimeError):
            tool_outputs(SimpleNamespace(output=[self.tool_call]), "verification")

    def test_untrusted_tool_arguments_are_rejected(self):
        for arguments in (
            '{"order_id":"OTHER"}',
            '{"order_id":"ORDER-1001","extra":"value"}',
            "not-json",
            "[]",
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.tool_call.arguments = arguments
                tool_outputs(SimpleNamespace(output=[self.tool_call]), "verification")

    def test_incomplete_or_incorrect_responses_fail_and_clean_up(self):
        for status, text in (
            ("incomplete", ""),
            ("failed", ""),
            ("completed", "invented answer"),
        ):
            with self.subTest(status=status, text=text):
                self.setUp()
                self.client.responses.create.return_value = SimpleNamespace(
                    id="resp_bad", status=status, output_text=text
                )
                with self.assertRaises(RuntimeError):
                    run_agent(self.project, self.settings)
                self.assert_cleaned_up()


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            "https://example.services.ai.azure.com/api/projects/demo",
            "gateway/provider/model",
        )
        self.environment = {
            "BYOM_GATEWAY_BASE_URL": "https://example.azure-api.net/openai/v1/",
            "BYOM_GATEWAY_API_KEY": "test-key",
        }

    def test_gateway_request_matches_connection_contract(self):
        url, headers, payload = gateway_request(self.settings, self.environment)
        self.assertEqual(
            url, "https://example.azure-api.net/openai/v1/chat/completions"
        )
        self.assertEqual(headers, {"Ocp-Apim-Subscription-Key": "test-key"})
        self.assertEqual(payload["model"], "provider/model")
        self.assertNotIn("api-version", url)

    def test_bearer_authentication(self):
        self.environment.update(
            BYOM_GATEWAY_KEY_HEADER="Authorization",
            BYOM_GATEWAY_KEY_FORMAT="Bearer {api_key}",
        )
        self.assertEqual(
            gateway_request(self.settings, self.environment)[1],
            {"Authorization": "Bearer test-key"},
        )

    def test_apim_policy_replaces_credentials_and_strips_gateway_key(self):
        policy = ET.parse(Path(__file__).with_name("apim-policy.xml")).getroot()
        self.assertEqual(policy.tag, "policies")
        self.assertEqual(
            policy.find("./inbound/set-backend-service").get("base-url"),
            "{{byom-upstream-base-url}}",
        )
        headers = {
            node.attrib["name"]: node for node in policy.findall("./inbound/set-header")
        }
        self.assertEqual(
            headers["Authorization"].findtext("value"),
            "Bearer {{byom-upstream-api-key}}",
        )
        self.assertEqual(
            headers["Ocp-Apim-Subscription-Key"].get("exists-action"), "delete"
        )

    def test_invalid_base_url_key_or_format_is_rejected(self):
        for overrides in (
            {"BYOM_GATEWAY_BASE_URL": "http://example.com/openai/v1"},
            {"BYOM_GATEWAY_BASE_URL": "https://example.com/openai/v1/chat/completions"},
            {"BYOM_GATEWAY_BASE_URL": "https://example.com/openai/v1?key=secret"},
            {"BYOM_GATEWAY_API_KEY": ""},
            {"BYOM_GATEWAY_KEY_FORMAT": "Bearer"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                gateway_request(self.settings, {**self.environment, **overrides})

    @patch("main.httpx.Client")
    def test_gateway_success(self, client_factory):
        response = client_factory.return_value.__enter__.return_value.post.return_value
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "BYOM_GATEWAY_OK"}}]
        }
        check_gateway(self.settings, self.environment)
        client_factory.assert_called_once_with(timeout=60, follow_redirects=False)

    @patch("main.httpx.Client")
    def test_gateway_authentication_failure_does_not_echo_response_body(
        self, client_factory
    ):
        response = client_factory.return_value.__enter__.return_value.post.return_value
        response.status_code = 401
        response.text = "sensitive-backend-content"
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
            check_gateway(self.settings, self.environment)
        self.assertNotIn("sensitive", str(caught.exception))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/demo",
            "FOUNDRY_MODEL_DEPLOYMENT_NAME": "gateway/model",
        }

    def run_config(self, environment, *extra_arguments):
        with (
            patch.dict("main.os.environ", environment, clear=True),
            patch("main.sys.argv", ["main.py", "--check-config", *extra_arguments]),
            patch("main.load_dotenv") as load_environment,
            patch("main.DefaultAzureCredential") as credential,
            patch("main.httpx.Client") as gateway_client,
            patch("main.sys.stdout", new_callable=io.StringIO),
            patch("main.sys.stderr", new_callable=io.StringIO) as errors,
        ):
            status = run_cli()
            load_environment.assert_called_once_with(
                Path(__file__).resolve().parents[1] / ".env", override=False
            )
            credential.assert_not_called()
            gateway_client.assert_not_called()
            return status, errors.getvalue()

    def test_configuration_check_never_authenticates(self):
        self.assertEqual(self.run_config(self.environment), (0, ""))

    def test_missing_configuration_returns_failure(self):
        status, errors = self.run_config({})
        self.assertEqual(status, 1)
        self.assertIn("FOUNDRY_PROJECT_ENDPOINT", errors)

    def test_gateway_configuration_check_never_calls_gateway(self):
        self.environment.update(
            BYOM_GATEWAY_BASE_URL="https://example.azure-api.net/openai/v1",
            BYOM_GATEWAY_API_KEY="offline-key",
        )
        self.assertEqual(self.run_config(self.environment, "--check-gateway"), (0, ""))

    def test_missing_optional_key_only_fails_when_gateway_check_requested(self):
        self.assertEqual(self.run_config(self.environment)[0], 0)
        self.environment["BYOM_GATEWAY_BASE_URL"] = (
            "https://example.azure-api.net/openai/v1"
        )
        status, errors = self.run_config(self.environment, "--check-gateway")
        self.assertEqual(status, 1)
        self.assertIn("BYOM_GATEWAY_API_KEY", errors)


if __name__ == "__main__":
    unittest.main()
