"""Tool provider and policy interfaces.

A tool is either read-only or side-effecting. Side-effecting tools act on behalf of the
user and must be gated by both a `ToolPolicy` decision and a delegated identity token.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.tools import ToolCall, ToolKind, ToolResult
from agent_platform.interfaces.identity import DelegatedToken


class ToolDefinition(BaseModel):
    """Metadata describing a registered tool."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str
    kind: ToolKind
    parameters_schema: dict[str, object] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    """Outcome of a policy evaluation for a tool call."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str | None = None


@runtime_checkable
class ToolPolicy(Protocol):
    """Decides whether a tool call may proceed."""

    def evaluate(
        self,
        definition: ToolDefinition,
        call: ToolCall,
        *,
        principal_id: str,
        delegated_token: DelegatedToken | None,
    ) -> PolicyDecision:
        """Return whether the call is permitted for this principal."""
        ...


@runtime_checkable
class ToolProvider(Protocol):
    """Registers and executes tools available to the action specialist."""

    def list_tools(self) -> tuple[ToolDefinition, ...]:
        """Return all registered tool definitions."""
        ...

    async def invoke(
        self,
        call: ToolCall,
        *,
        principal_id: str,
        delegated_token: DelegatedToken | None,
    ) -> ToolResult:
        """Execute a tool call after policy and delegation checks pass."""
        ...
