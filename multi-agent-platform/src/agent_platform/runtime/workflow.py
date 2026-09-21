"""The multi-agent turn workflow, built on the Microsoft Agent Framework.

Wires the specialists into a real `agent_framework` graph: a router branches to the
knowledge, action, or response executor via conditional edges, and knowledge/action feed
the terminal response executor. Executors stream channel-neutral `StreamEvent`s in real
time through an `emit` callback carried on the turn, so the orchestrator can surface tokens,
activity, and citations as they happen while the framework drives execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from agent_platform.contracts.citations import Citation
from agent_platform.contracts.streaming import AgentActivity, StreamEvent
from agent_platform.interfaces.sessions import SessionStore
from agent_platform.runtime.model import ChatModel, ModelMessage
from agent_platform.runtime.specialists import (
    ActionSpecialist,
    KnowledgeSpecialist,
    ResponseSpecialist,
    RouterSpecialist,
)

EmitFn = Callable[[StreamEvent], Awaitable[None]]

ROUTE_RESPOND = "respond"
ROUTE_KNOWLEDGE = "knowledge"
ROUTE_ACTION = "action"


@dataclass
class TurnContext:
    """Mutable state threaded through the workflow for a single turn.

    Passed by reference between executors (in-process), so mutations made by upstream
    executors are visible to the orchestrator after the run completes.
    """

    text: str
    principal_id: str
    session_id: str
    correlation_id: str
    emit: EmitFn
    route: str = ROUTE_KNOWLEDGE
    context: str | None = None
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    answer: str = ""


class RouterExecutor(Executor):
    """Picks the route for a turn and forwards it."""

    def __init__(
        self,
        router: RouterSpecialist,
        *,
        action: ActionSpecialist | None,
        id: str = "router",
    ) -> None:
        super().__init__(id=id)
        self._router = router
        self._action = action

    @handler
    async def route(self, turn: TurnContext, ctx: WorkflowContext[TurnContext]) -> None:
        if self._router.is_social(turn.text):
            turn.route = ROUTE_RESPOND
        elif self._action is not None and self._action.can_handle(turn.text):
            turn.route = ROUTE_ACTION
        else:
            turn.route = ROUTE_KNOWLEDGE
        await turn.emit(
            StreamEvent.agent_activity(
                AgentActivity(agent="router", action="routing", detail=turn.route)
            )
        )
        await ctx.send_message(turn)


class KnowledgeExecutor(Executor):
    """Retrieves grounded context and attaches it to the turn."""

    def __init__(
        self,
        knowledge: KnowledgeSpecialist,
        response: ResponseSpecialist,
        *,
        id: str = "knowledge",
    ) -> None:
        super().__init__(id=id)
        self._knowledge = knowledge
        self._response = response

    @handler
    async def gather(self, turn: TurnContext, ctx: WorkflowContext[TurnContext]) -> None:
        await turn.emit(
            StreamEvent.agent_activity(
                AgentActivity(agent="knowledge", action="retrieving")
            )
        )
        result = await self._knowledge.gather(turn.text, turn.principal_id)
        turn.context = result.content or None
        turn.citations = self._response.merge_citations(result.citations)
        if turn.citations:
            await turn.emit(StreamEvent.with_citations(turn.citations))
        await ctx.send_message(turn)


class ActionExecutor(Executor):
    """Selects and runs a tool, attaching its result to the turn."""

    def __init__(
        self,
        action: ActionSpecialist,
        response: ResponseSpecialist,
        *,
        id: str = "action",
    ) -> None:
        super().__init__(id=id)
        self._action = action
        self._response = response

    @handler
    async def act(self, turn: TurnContext, ctx: WorkflowContext[TurnContext]) -> None:
        intent = self._action.detect(turn.text)
        if intent is None:
            await ctx.send_message(turn)
            return
        await turn.emit(
            StreamEvent.agent_activity(
                AgentActivity(agent="action", action="using_tool", detail=intent.tool_name)
            )
        )
        outcome = await self._action.run(intent, turn.principal_id)
        turn.context = outcome.context
        turn.citations = self._response.merge_citations(outcome.citations)
        if turn.citations:
            await turn.emit(StreamEvent.with_citations(turn.citations))
        await ctx.send_message(turn)


class ResponseExecutor(Executor):
    """Terminal executor: streams the grounded answer and yields it as the output."""

    def __init__(
        self,
        model: ChatModel,
        response: ResponseSpecialist,
        sessions: SessionStore,
        max_history: int,
        *,
        id: str = "response",
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._response = response
        self._sessions = sessions
        self._max_history = max_history

    @handler
    async def respond(self, turn: TurnContext, ctx: WorkflowContext[Never, str]) -> None:
        await turn.emit(
            StreamEvent.agent_activity(
                AgentActivity(agent="response", action="generating")
            )
        )
        instructions = self._response.build_instructions(turn.context)
        history = await self._sessions.history(turn.session_id)
        messages = _to_model_messages(history, self._max_history)

        collected: list[str] = []
        async for delta in self._model.stream(messages, instructions=instructions):
            if delta:
                collected.append(delta)
                await turn.emit(StreamEvent.text_delta(delta))

        turn.answer = "".join(collected).strip()
        await ctx.yield_output(turn.answer)


def build_turn_workflow(
    router: RouterExecutor,
    knowledge: KnowledgeExecutor,
    response: ResponseExecutor,
    action: ActionExecutor | None,
):
    """Assemble the conditional turn workflow from its executors."""
    builder = (
        WorkflowBuilder(start_executor=router)
        .add_edge(router, response, condition=lambda t: t.route == ROUTE_RESPOND)
        .add_edge(router, knowledge, condition=lambda t: t.route == ROUTE_KNOWLEDGE)
        .add_edge(knowledge, response)
    )
    if action is not None:
        builder = builder.add_edge(
            router, action, condition=lambda t: t.route == ROUTE_ACTION
        ).add_edge(action, response)
    return builder.build()


def _to_model_messages(
    history: tuple, max_history: int
) -> tuple[ModelMessage, ...]:
    recent = history[-max_history:]
    return tuple(
        ModelMessage(role=message.role, content=message.content) for message in recent
    )
