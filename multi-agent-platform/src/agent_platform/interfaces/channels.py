"""Channel adapter interface for user-facing surfaces.

Adapters translate a channel's native payloads to and from the platform contracts. The
MVP ships the REST/web channel; Teams and other channels implement this same interface.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.messages import ChatRequest
from agent_platform.contracts.streaming import StreamEvent


class InboundMessage(BaseModel):
    """A channel's native inbound payload, before normalization."""

    model_config = ConfigDict(frozen=True)

    channel: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    session_id: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class ChannelAdapter(Protocol):
    """Bridges a specific channel to the shared platform contracts."""

    @property
    def channel(self) -> str:
        """Stable channel identifier (e.g., 'rest', 'teams')."""
        ...

    def to_request(self, inbound: InboundMessage) -> ChatRequest:
        """Normalize a native inbound payload into a `ChatRequest`."""
        ...

    async def emit(self, events: AsyncIterator[StreamEvent]) -> None:
        """Deliver streamed events back to the channel in its native form."""
        ...
