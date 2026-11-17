"""In-memory tool registry.

Empty by default: the MVP registers no external side-effecting actions. It exists so that
Bing, MCP, social, and external-API tools can be added later without changing the
orchestrator. Every invocation passes through the policy gate first, and side-effecting
tools additionally require a delegated token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from agent_platform.contracts.errors import ErrorCode, PlatformException
from agent_platform.contracts.tools import ToolCall, ToolResult
from agent_platform.interfaces.identity import DelegatedToken
from agent_platform.interfaces.tools import PolicyDecision, ToolDefinition

ToolHandler = Callable[[ToolCall], Awaitable[ToolResult]]
PolicyEvaluator = Callable[
    [ToolDefinition, ToolCall, str, DelegatedToken | None], PolicyDecision
]


@dataclass(frozen=True)
class RegisteredTool:
    """A tool definition paired with its async handler."""

    definition: ToolDefinition
    handler: ToolHandler


class InMemoryToolProvider:
    """A `ToolProvider` holding registered tools and enforcing the policy gate."""

    def __init__(self, policy_evaluator: PolicyEvaluator) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._evaluate = policy_evaluator

    def register(self, tool: RegisteredTool) -> None:
        if tool.definition.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.definition.name}")
        self._tools[tool.definition.name] = tool

    def list_tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition for tool in self._tools.values())

    async def invoke(
        self,
        call: ToolCall,
        *,
        principal_id: str,
        delegated_token: DelegatedToken | None,
    ) -> ToolResult:
        tool = self._tools.get(call.tool_name)
        if tool is None:
            raise PlatformException.of(
                ErrorCode.NOT_FOUND, f"Unknown tool: {call.tool_name}"
            )

        decision = self._evaluate(tool.definition, call, principal_id, delegated_token)
        if not decision.allowed:
            code = (
                ErrorCode.DELEGATION_REQUIRED
                if delegated_token is None
                else ErrorCode.TOOL_POLICY_DENIED
            )
            raise PlatformException.of(
                code,
                decision.reason or "Tool call denied by policy.",
                details={"tool": call.tool_name},
            )

        return await tool.handler(call)
