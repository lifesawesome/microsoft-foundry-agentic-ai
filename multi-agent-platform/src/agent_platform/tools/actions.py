"""Side-effecting action tools (the "act on behalf of the user" capability).

These are classified `SIDE_EFFECTING`, so the policy gate requires a delegated user token
scoped to the acting principal before they run. The bundled `create_case` tool simulates
the external write; replace its handler with a real API call (guarded by the same gate) to
enable production actions without changing the orchestration or policy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent_platform.contracts.tools import ToolCall, ToolKind, ToolResult
from agent_platform.interfaces.tools import ToolDefinition
from agent_platform.tools.registry import RegisteredTool

CREATE_CASE_TOOL_NAME = "create_case"
CREATE_CASE_SCOPES: tuple[str, ...] = ("Cases.ReadWrite",)


def build_create_case_tool() -> RegisteredTool:
    """Build a registrable side-effecting tool that opens a support case (simulated)."""

    async def _handler(call: ToolCall) -> ToolResult:
        summary = str(call.arguments.get("summary", "")).strip()
        if not summary:
            return ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                succeeded=False,
                error="Missing required argument: summary.",
            )
        case_id = f"CASE-{uuid4().hex[:8].upper()}"
        return ToolResult(
            tool_name=call.tool_name,
            call_id=call.call_id,
            succeeded=True,
            output={
                "case_id": case_id,
                "status": "created (simulated)",
                "summary": summary,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    definition = ToolDefinition(
        name=CREATE_CASE_TOOL_NAME,
        description="Open a support case on behalf of the signed-in user.",
        kind=ToolKind.SIDE_EFFECTING,
        parameters_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    )
    return RegisteredTool(definition=definition, handler=_handler)
