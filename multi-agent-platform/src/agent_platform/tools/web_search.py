"""Read-only web search tool (the "research" capability).

Registered as a `READ_ONLY` tool so it runs with the platform's own identity and never
requires a delegated user token. The search itself is delegated to a `WebSearchBackend`,
so a real Bing / Foundry web-search backend can replace the bundled simulated one without
touching the registry, policy, or the action specialist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import quote_plus

from agent_platform.contracts.tools import ToolCall, ToolKind, ToolResult
from agent_platform.interfaces.tools import ToolDefinition
from agent_platform.tools.registry import RegisteredTool

WEB_SEARCH_TOOL_NAME = "web_search"


@dataclass(frozen=True)
class WebResult:
    """A single search hit."""

    title: str
    url: str
    snippet: str


@runtime_checkable
class WebSearchBackend(Protocol):
    """Performs the actual web search. Swap for a real Bing / Foundry backend."""

    async def search(self, query: str, *, max_results: int = 3) -> tuple[WebResult, ...]:
        """Return ranked results for the query."""
        ...


class SimulatedWebSearchBackend:
    """Deterministic, offline backend so the research path is demonstrable without keys.

    Clearly marked as simulated; replace with a Bing grounding / Foundry web-search backend
    for production.
    """

    async def search(self, query: str, *, max_results: int = 3) -> tuple[WebResult, ...]:
        trimmed = query.strip()[:80]
        encoded = quote_plus(trimmed)
        return tuple(
            WebResult(
                title=f"[simulated] Result {index} for: {trimmed}",
                url=f"https://example.com/search?q={encoded}&r={index}",
                snippet=(
                    f"Simulated snippet {index}. Replace SimulatedWebSearchBackend with a "
                    "real Bing / Foundry web-search backend to return live results."
                ),
            )
            for index in range(1, max_results + 1)
        )


def build_web_search_tool(
    backend: WebSearchBackend, *, max_results: int = 3
) -> RegisteredTool:
    """Build a registrable read-only web-search tool over the given backend."""

    async def _handler(call: ToolCall) -> ToolResult:
        query = str(call.arguments.get("query", "")).strip()
        if not query:
            return ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                succeeded=False,
                error="Missing required argument: query.",
            )
        results = await backend.search(query, max_results=max_results)
        return ToolResult(
            tool_name=call.tool_name,
            call_id=call.call_id,
            succeeded=True,
            output=[asdict(result) for result in results],
        )

    definition = ToolDefinition(
        name=WEB_SEARCH_TOOL_NAME,
        description="Search the public web for current information and return ranked results.",
        kind=ToolKind.READ_ONLY,
        parameters_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    return RegisteredTool(definition=definition, handler=_handler)
