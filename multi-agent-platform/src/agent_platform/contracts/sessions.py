"""Session reference contracts."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionRef(BaseModel):
    """Identifies a conversation and the authenticated principal that owns it."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    # Stable identifier for the authenticated end user (never a raw channel handle).
    principal_id: str = Field(min_length=1)
    channel: str = Field(default="rest")
    created_at: datetime = Field(default_factory=_utcnow)
