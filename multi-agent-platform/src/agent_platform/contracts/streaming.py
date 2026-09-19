"""Streaming event contracts for incremental responses."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.citations import Citation
from agent_platform.contracts.errors import PlatformError


class StreamEventType(str, Enum):
    """Discriminator for streamed events."""

    SESSION = "session"
    ACTIVITY = "activity"
    TEXT_DELTA = "text_delta"
    CITATIONS = "citations"
    COMPLETED = "completed"
    ERROR = "error"


class AgentActivity(BaseModel):
    """A human-readable status update describing what the runtime is doing."""

    model_config = ConfigDict(frozen=True)

    agent: str
    action: str
    detail: str | None = None


class StreamEvent(BaseModel):
    """A single event emitted while a response is generated.

    Exactly one payload field is populated, selected by `type`.
    """

    model_config = ConfigDict(frozen=True)

    type: StreamEventType
    session_id: str | None = None
    text: str | None = None
    activity: AgentActivity | None = None
    citations: tuple[Citation, ...] = ()
    error: PlatformError | None = None

    @classmethod
    def session(cls, session_id: str) -> "StreamEvent":
        return cls(type=StreamEventType.SESSION, session_id=session_id)

    @classmethod
    def text_delta(cls, text: str) -> "StreamEvent":
        return cls(type=StreamEventType.TEXT_DELTA, text=text)

    @classmethod
    def agent_activity(cls, activity: AgentActivity) -> "StreamEvent":
        return cls(type=StreamEventType.ACTIVITY, activity=activity)

    @classmethod
    def with_citations(cls, citations: tuple[Citation, ...]) -> "StreamEvent":
        return cls(type=StreamEventType.CITATIONS, citations=citations)

    @classmethod
    def completed(cls) -> "StreamEvent":
        return cls(type=StreamEventType.COMPLETED)

    @classmethod
    def failure(cls, error: PlatformError) -> "StreamEvent":
        return cls(type=StreamEventType.ERROR, error=error)
