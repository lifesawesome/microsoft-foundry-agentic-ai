"""The streaming orchestrator.

Coordinates the specialists for a single turn and yields channel-neutral `StreamEvent`s.
Enforces a per-request timeout, supports cancellation, requires non-empty grounded output,
and maps failures to structured platform errors.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from agent_platform.contracts.errors import ErrorCode, PlatformError, PlatformException
from agent_platform.contracts.messages import Message, Role
from agent_platform.contracts.sessions import SessionRef
from agent_platform.contracts.streaming import AgentActivity, StreamEvent
from agent_platform.interfaces.knowledge import KnowledgeProvider
from agent_platform.interfaces.sessions import SessionStore
from agent_platform.runtime.model import ChatModel, ModelMessage
from agent_platform.runtime.specialists import (
    KnowledgeSpecialist,
    ResponseSpecialist,
    RouterSpecialist,
)
from agent_platform.runtime.telemetry import new_correlation_id, span


class Orchestrator:
    """Runs the multi-agent workflow for one user turn."""

    def __init__(
        self,
        *,
        model: ChatModel,
        knowledge: KnowledgeProvider,
        sessions: SessionStore,
        request_timeout_seconds: float = 60.0,
        max_history: int = 20,
    ) -> None:
        self._model = model
        self._sessions = sessions
        self._router = RouterSpecialist()
        self._knowledge = KnowledgeSpecialist(knowledge)
        self._response = ResponseSpecialist()
        self._timeout = request_timeout_seconds
        self._max_history = max_history

    async def run(
        self,
        *,
        text: str,
        session: SessionRef,
    ) -> AsyncIterator[StreamEvent]:
        """Yield the events for a single turn, guarded by a timeout."""
        correlation_id = new_correlation_id()
        try:
            async for event in _with_timeout(
                self._run(text=text, session=session, correlation_id=correlation_id),
                self._timeout,
            ):
                yield event
        except asyncio.TimeoutError:
            yield StreamEvent.failure(
                PlatformError(
                    code=ErrorCode.TIMEOUT,
                    message="The request timed out.",
                    correlation_id=correlation_id,
                )
            )
        except PlatformException as exc:
            error = exc.error.model_copy(update={"correlation_id": correlation_id})
            yield StreamEvent.failure(error)
        except asyncio.CancelledError:
            yield StreamEvent.failure(
                PlatformError(
                    code=ErrorCode.CANCELLED,
                    message="The request was cancelled.",
                    correlation_id=correlation_id,
                )
            )
            raise
        except Exception:  # noqa: BLE001 - convert to a safe, structured error
            yield StreamEvent.failure(
                PlatformError(
                    code=ErrorCode.INTERNAL,
                    message="An unexpected error occurred.",
                    correlation_id=correlation_id,
                )
            )

    async def _run(
        self,
        *,
        text: str,
        session: SessionRef,
        correlation_id: str,
    ) -> AsyncIterator[StreamEvent]:
        with span("turn", correlation_id=correlation_id, session_id=session.session_id):
            await self._sessions.append(
                session.session_id, Message(role=Role.USER, content=text)
            )

            context: str | None = None
            citations: tuple = ()
            if self._router.needs_knowledge(text):
                yield StreamEvent.agent_activity(
                    AgentActivity(agent="knowledge", action="retrieving")
                )
                with span("knowledge.retrieve", correlation_id=correlation_id):
                    result = await self._knowledge.gather(text, session.principal_id)
                context = result.content or None
                citations = self._response.merge_citations(result.citations)
                if citations:
                    yield StreamEvent.with_citations(citations)

            yield StreamEvent.agent_activity(
                AgentActivity(agent="response", action="generating")
            )
            instructions = self._response.build_instructions(context)
            history = await self._sessions.history(session.session_id)
            messages = _to_model_messages(history, self._max_history)

            collected: list[str] = []
            with span("response.stream", correlation_id=correlation_id):
                async for delta in self._model.stream(
                    messages, instructions=instructions
                ):
                    if delta:
                        collected.append(delta)
                        yield StreamEvent.text_delta(delta)

            answer = "".join(collected).strip()
            if not answer:
                raise PlatformException.of(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "The model returned no output.",
                )

            await self._sessions.append(
                session.session_id,
                Message(role=Role.ASSISTANT, content=answer, citations=citations),
            )
            yield StreamEvent.completed()


def _to_model_messages(
    history: tuple[Message, ...], max_history: int
) -> tuple[ModelMessage, ...]:
    recent = history[-max_history:]
    return tuple(
        ModelMessage(role=message.role, content=message.content) for message in recent
    )


async def _with_timeout(
    source: AsyncIterator[StreamEvent], timeout: float
) -> AsyncIterator[StreamEvent]:
    """Yield from an async iterator, enforcing a wall-clock deadline across the stream."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    iterator = source.__aiter__()
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise asyncio.TimeoutError
        try:
            event = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        yield event
