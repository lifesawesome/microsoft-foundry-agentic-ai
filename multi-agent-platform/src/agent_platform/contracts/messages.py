"""Conversation message contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.citations import Citation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, Enum):
    """Originator of a message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """A single conversation message exchanged with the platform."""

    model_config = ConfigDict(frozen=True)

    role: Role
    content: str
    citations: tuple[Citation, ...] = ()
    created_at: datetime = Field(default_factory=_utcnow)


class ChatRequest(BaseModel):
    """A user's request to the platform, independent of the originating channel."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    session_id: str | None = None
    channel: str = Field(default="rest")
    # Opaque per-channel identifiers (e.g., Teams UPN); never used for authorization.
    user_hint: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """A completed, non-streamed response to a `ChatRequest`."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    text: str
    citations: tuple[Citation, ...] = ()
    created_at: datetime = Field(default_factory=_utcnow)
