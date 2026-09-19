"""In-memory session store for local development and tests.

Not suitable for production or multi-replica deployments; use the Redis store there.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from agent_platform.contracts.messages import Message
from agent_platform.contracts.sessions import SessionRef


class InMemorySessionStore:
    """A process-local `SessionStore` backed by dictionaries."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRef] = {}
        self._history: dict[str, list[Message]] = {}
        self._lock = asyncio.Lock()

    async def create(self, principal_id: str, channel: str) -> SessionRef:
        async with self._lock:
            session = SessionRef(
                session_id=uuid4().hex,
                principal_id=principal_id,
                channel=channel,
            )
            self._sessions[session.session_id] = session
            self._history[session.session_id] = []
            return session

    async def get(self, session_id: str) -> SessionRef | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def append(self, session_id: str, message: Message) -> None:
        async with self._lock:
            if session_id not in self._history:
                raise KeyError(f"Unknown session: {session_id}")
            self._history[session_id].append(message)

    async def history(self, session_id: str) -> tuple[Message, ...]:
        async with self._lock:
            return tuple(self._history.get(session_id, ()))

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
            self._history.pop(session_id, None)
