"""The streaming orchestrator.

Drives the Agent Framework turn workflow for a single user turn and yields channel-neutral
`StreamEvent`s. The workflow runs as a task while its executors push events onto a queue
through the turn's `emit` callback; the orchestrator drains that queue in real time. It
enforces a per-request timeout, supports cancellation, requires non-empty grounded output,
and maps failures to structured platform errors.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from agent_platform.contracts.errors import ErrorCode, PlatformError, PlatformException
from agent_platform.contracts.messages import Message, Role
from agent_platform.contracts.sessions import SessionRef
from agent_platform.contracts.streaming import StreamEvent
from agent_platform.interfaces.identity import DelegatedIdentityProvider
from agent_platform.interfaces.knowledge import KnowledgeProvider
from agent_platform.interfaces.sessions import SessionStore
from agent_platform.interfaces.tools import ToolProvider
from agent_platform.runtime.model import ChatModel
from agent_platform.runtime.specialists import (
    ActionSpecialist,
    KnowledgeSpecialist,
    ResponseSpecialist,
    RouterSpecialist,
)
from agent_platform.runtime.telemetry import new_correlation_id, span
from agent_platform.runtime.workflow import (
    ActionExecutor,
    KnowledgeExecutor,
    ResponseExecutor,
    RouterExecutor,
    TurnContext,
    build_turn_workflow,
)


class Orchestrator:
    """Runs the multi-agent workflow for one user turn."""

    def __init__(
        self,
        *,
        model: ChatModel,
        knowledge: KnowledgeProvider,
        sessions: SessionStore,
        tools: ToolProvider | None = None,
        identity: DelegatedIdentityProvider | None = None,
        request_timeout_seconds: float = 60.0,
        max_history: int = 20,
    ) -> None:
        self._sessions = sessions
        self._timeout = request_timeout_seconds

        response = ResponseSpecialist()
        action_specialist = (
            ActionSpecialist(tools, identity) if tools is not None else None
        )
        router_exec = RouterExecutor(
            RouterSpecialist(), action=action_specialist, id="router"
        )
        knowledge_exec = KnowledgeExecutor(
            KnowledgeSpecialist(knowledge), response, id="knowledge"
        )
        response_exec = ResponseExecutor(
            model, response, sessions, max_history, id="response"
        )
        action_exec = (
            ActionExecutor(action_specialist, response, id="action")
            if action_specialist is not None
            else None
        )
        self._workflow = build_turn_workflow(
            router_exec, knowledge_exec, response_exec, action_exec
        )

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

            queue: asyncio.Queue[StreamEvent | object] = asyncio.Queue()
            done = object()

            async def emit(event: StreamEvent) -> None:
                await queue.put(event)

            turn = TurnContext(
                text=text,
                principal_id=session.principal_id,
                session_id=session.session_id,
                correlation_id=correlation_id,
                emit=emit,
            )

            workflow_task = asyncio.create_task(self._workflow.run(turn))

            async def pump() -> None:
                try:
                    await workflow_task
                except BaseException:  # noqa: BLE001 - re-raised via workflow_task below
                    pass
                finally:
                    await queue.put(done)

            pump_task = asyncio.create_task(pump())
            try:
                while True:
                    item = await queue.get()
                    if item is done:
                        break
                    assert isinstance(item, StreamEvent)
                    yield item
                await workflow_task  # surface any workflow error to the outer handler
            finally:
                for task in (workflow_task, pump_task):
                    if not task.done():
                        task.cancel()

            answer = turn.answer.strip()
            if not answer:
                raise PlatformException.of(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "The model returned no output.",
                )

            await self._sessions.append(
                session.session_id,
                Message(role=Role.ASSISTANT, content=answer, citations=turn.citations),
            )
            yield StreamEvent.completed()


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
