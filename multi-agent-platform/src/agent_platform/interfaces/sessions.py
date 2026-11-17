"""Session store interface for conversation persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_platform.contracts.messages import Message
from agent_platform.contracts.sessions import SessionRef


@runtime_checkable
class SessionStore(Protocol):
    """Persists conversation state keyed by session and principal."""

    async def create(self, principal_id: str, channel: str) -> SessionRef:
        """Create and return a new session for the principal."""
        ...

    async def get(self, session_id: str) -> SessionRef | None:
        """Return the session reference, or None if it does not exist."""
        ...

    async def append(self, session_id: str, message: Message) -> None:
        """Append a message to the session's history."""
        ...

    async def history(self, session_id: str) -> tuple[Message, ...]:
        """Return the ordered message history for the session."""
        ...

    async def delete(self, session_id: str) -> None:
        """Delete the session and its history."""
        ...
