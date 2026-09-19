"""Tool-call contracts and the read-only vs. side-effecting classification.

Side-effecting tools act on behalf of the user and therefore require a delegated
identity token plus explicit policy approval before execution. Read-only tools only
retrieve information and never mutate external state.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ToolKind(str, Enum):
    """Classifies a tool by its side effects and authorization requirements."""

    # Retrieval only; safe to run with app/managed identity.
    READ_ONLY = "read_only"
    # Acts on behalf of the user; requires a delegated token and policy approval.
    SIDE_EFFECTING = "side_effecting"


class ToolCall(BaseModel):
    """A request from an agent to invoke a registered tool."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    call_id: str | None = None


class ToolResult(BaseModel):
    """The outcome of a tool invocation."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    call_id: str | None = None
    succeeded: bool
    output: object | None = None
    error: str | None = None
