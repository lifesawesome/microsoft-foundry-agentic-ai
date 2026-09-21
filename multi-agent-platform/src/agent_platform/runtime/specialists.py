"""Specialist agents composing the orchestrated workflow.

Specialists run in one process behind the Agent Framework workflow. Each has a single,
well-defined responsibility so the workflow stays deterministic and traceable:

- Router: pick the route for a turn (respond directly, ground, or use a tool).
- Knowledge: retrieve grounded context and citations from a `KnowledgeProvider`.
- Action: select and invoke a tool through the policy-gated `ToolProvider`.
- Response: stream the final answer via the `ChatModel`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_platform.contracts.citations import Citation
from agent_platform.contracts.errors import PlatformException
from agent_platform.contracts.tools import ToolCall, ToolResult
from agent_platform.interfaces.identity import DelegatedIdentityProvider
from agent_platform.interfaces.knowledge import (
    KnowledgeProvider,
    KnowledgeQuery,
    KnowledgeResult,
)
from agent_platform.interfaces.tools import ToolProvider

_GREETING_PREFIXES = ("hi", "hello", "hey", "thanks", "thank you")
_WEB_SEARCH_CUES = (
    "search the web",
    "web search",
    "search online",
    "look up online",
    "latest news",
    "current news",
)
_CREATE_CASE_CUES = (
    "create a case",
    "open a case",
    "file a case",
    "raise a ticket",
    "create a ticket",
    "log a case",
)


class RouterSpecialist:
    """Decides how a user turn should be handled."""

    def is_social(self, text: str) -> bool:
        """Return True for short greetings/pleasantries that need no work."""
        stripped = text.strip().lower()
        if not stripped:
            return True
        return len(stripped.split()) <= 3 and stripped.startswith(_GREETING_PREFIXES)

    def needs_knowledge(self, text: str) -> bool:
        """Legacy helper: everything non-social is grounded by default."""
        return not self.is_social(text)


class KnowledgeSpecialist:
    """Retrieves grounded content from the configured knowledge provider."""

    def __init__(self, provider: KnowledgeProvider, *, max_results: int = 5) -> None:
        self._provider = provider
        self._max_results = max_results

    async def gather(self, text: str, principal_id: str) -> KnowledgeResult:
        return await self._provider.retrieve(
            KnowledgeQuery(
                text=text,
                max_results=self._max_results,
                principal_id=principal_id,
            )
        )


class ResponseSpecialist:
    """Builds the grounded instructions used to produce the final answer."""

    BASE_INSTRUCTIONS = (
        "You are a helpful assistant. Answer using only the provided context when it is "
        "present. Cite sources inline using their source id in brackets. If the context "
        "does not contain the answer, say so plainly instead of guessing."
    )

    def build_instructions(self, context: str | None) -> str:
        if not context:
            return self.BASE_INSTRUCTIONS
        return f"{self.BASE_INSTRUCTIONS}\n\n## Context\n{context}"

    def merge_citations(
        self, citations: tuple[Citation, ...]
    ) -> tuple[Citation, ...]:
        seen: dict[str, Citation] = {}
        for citation in citations:
            seen.setdefault(citation.source_id, citation)
        return tuple(seen.values())


@dataclass(frozen=True)
class ToolIntent:
    """A detected intent to invoke a specific tool."""

    tool_name: str
    arguments: dict[str, Any]
    # Delegated scopes required to run the tool; empty for read-only tools.
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionOutcome:
    """The result of an action, normalized for the response specialist."""

    context: str
    citations: tuple[Citation, ...] = ()
    succeeded: bool = True


class ActionSpecialist:
    """Selects and invokes a tool through the policy-gated `ToolProvider`.

    Read-only tools (e.g., web search) run with the platform identity. Side-effecting tools
    require a delegated user token, which is acquired only when the user has consented. A
    denied action is reported back as context rather than crashing the turn, so the
    response can explain what is needed (e.g., consent or approval).
    """

    def __init__(
        self,
        tools: ToolProvider,
        identity: DelegatedIdentityProvider | None = None,
    ) -> None:
        self._tools = tools
        self._identity = identity

    def detect(self, text: str) -> ToolIntent | None:
        """Map a user turn to a tool intent, or None when no tool applies."""
        lowered = text.strip().lower()
        if any(cue in lowered for cue in _CREATE_CASE_CUES):
            from agent_platform.tools.actions import (
                CREATE_CASE_SCOPES,
                CREATE_CASE_TOOL_NAME,
            )

            return ToolIntent(
                tool_name=CREATE_CASE_TOOL_NAME,
                arguments={"summary": text.strip()},
                scopes=CREATE_CASE_SCOPES,
            )
        if any(cue in lowered for cue in _WEB_SEARCH_CUES):
            from agent_platform.tools.web_search import WEB_SEARCH_TOOL_NAME

            return ToolIntent(
                tool_name=WEB_SEARCH_TOOL_NAME,
                arguments={"query": text.strip()},
            )
        return None

    def can_handle(self, text: str) -> bool:
        return self.detect(text) is not None

    async def run(self, intent: ToolIntent, principal_id: str) -> ActionOutcome:
        token = None
        if intent.scopes:
            if self._identity is None or not await self._identity.has_consent(
                principal_id, intent.scopes
            ):
                return ActionOutcome(
                    context=(
                        f"The action '{intent.tool_name}' needs the user's consent for "
                        f"scopes {', '.join(intent.scopes)} before it can run. Ask the user "
                        "to grant consent and, if required, approve the change."
                    ),
                    succeeded=False,
                )
            token = await self._identity.acquire_token(principal_id, intent.scopes)

        try:
            result = await self._tools.invoke(
                ToolCall(tool_name=intent.tool_name, arguments=intent.arguments),
                principal_id=principal_id,
                delegated_token=token,
            )
        except PlatformException as exc:
            return ActionOutcome(
                context=(
                    f"The action '{intent.tool_name}' was blocked: {exc.error.message}"
                ),
                succeeded=False,
            )
        return _outcome_from_result(intent, result)


def _outcome_from_result(intent: ToolIntent, result: ToolResult) -> ActionOutcome:
    if not result.succeeded:
        return ActionOutcome(
            context=f"The tool '{intent.tool_name}' failed: {result.error or 'unknown error'}.",
            succeeded=False,
        )

    output = result.output
    if isinstance(output, list):
        lines: list[str] = []
        citations: list[Citation] = []
        for index, item in enumerate(output, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", f"Result {index}"))
            url = item.get("url")
            snippet = str(item.get("snippet", ""))
            lines.append(f"[{index}] {title}: {snippet}")
            citations.append(
                Citation(
                    source_id=str(url or f"{intent.tool_name}-{index}"),
                    title=title,
                    snippet=snippet,
                    url=url if isinstance(url, str) else None,
                    provider=intent.tool_name,
                )
            )
        return ActionOutcome(context="\n".join(lines), citations=tuple(citations))

    if isinstance(output, dict):
        rendered = ", ".join(f"{key}: {value}" for key, value in output.items())
        return ActionOutcome(context=f"Tool '{intent.tool_name}' result — {rendered}")

    return ActionOutcome(context=f"Tool '{intent.tool_name}' completed.")
