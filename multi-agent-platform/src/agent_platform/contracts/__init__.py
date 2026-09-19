"""Channel-neutral contracts shared across the platform.

These models are the boundary between user channels (web widget, Teams, MCP clients)
and the agent runtime. Channels translate their native payloads to and from these
types so that core agent code never depends on a specific channel.
"""

from agent_platform.contracts.citations import Citation
from agent_platform.contracts.errors import ErrorCode, PlatformError
from agent_platform.contracts.messages import (
    ChatRequest,
    ChatResponse,
    Message,
    Role,
)
from agent_platform.contracts.sessions import SessionRef
from agent_platform.contracts.streaming import (
    AgentActivity,
    StreamEvent,
    StreamEventType,
)
from agent_platform.contracts.tools import ToolCall, ToolKind, ToolResult

__all__ = [
    "AgentActivity",
    "ChatRequest",
    "ChatResponse",
    "Citation",
    "ErrorCode",
    "Message",
    "PlatformError",
    "Role",
    "SessionRef",
    "StreamEvent",
    "StreamEventType",
    "ToolCall",
    "ToolKind",
    "ToolResult",
]
