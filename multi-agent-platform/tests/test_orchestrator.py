"""Unit tests for the streaming orchestrator."""

from __future__ import annotations

import pytest

from agent_platform.contracts.streaming import StreamEventType
from agent_platform.runtime.orchestrator import Orchestrator
from agent_platform.sessions.memory import InMemorySessionStore
from tests.fakes import EmptyChatModel, FakeChatModel, FakeKnowledgeProvider


async def _collect(orchestrator: Orchestrator, text: str):
    sessions = orchestrator._sessions  # noqa: SLF001 - test setup
    session = await sessions.create("user-1", "rest")
    return [event async for event in orchestrator.run(text=text, session=session)], session


async def test_grounded_turn_streams_text_citations_and_completion() -> None:
    model = FakeChatModel("grounded answer here")
    knowledge = FakeKnowledgeProvider()
    sessions = InMemorySessionStore()
    orchestrator = Orchestrator(model=model, knowledge=knowledge, sessions=sessions)

    events, session = await _collect(orchestrator, "How do money mules operate?")
    types = [event.type for event in events]

    assert StreamEventType.CITATIONS in types
    assert StreamEventType.TEXT_DELTA in types
    assert types[-1] is StreamEventType.COMPLETED
    assert knowledge.calls, "knowledge provider should be queried for a substantive turn"

    history = await sessions.history(session.session_id)
    assert history[-1].content == "grounded answer here"


async def test_greeting_skips_knowledge_retrieval() -> None:
    model = FakeChatModel("hello there")
    knowledge = FakeKnowledgeProvider()
    orchestrator = Orchestrator(
        model=model, knowledge=knowledge, sessions=InMemorySessionStore()
    )

    events, _ = await _collect(orchestrator, "hi")
    types = [event.type for event in events]

    assert StreamEventType.CITATIONS not in types
    assert not knowledge.calls


async def test_empty_model_output_raises_structured_error() -> None:
    orchestrator = Orchestrator(
        model=EmptyChatModel(),
        knowledge=FakeKnowledgeProvider(),
        sessions=InMemorySessionStore(),
    )

    events, _ = await _collect(orchestrator, "Explain synthetic identity fraud")
    error_events = [e for e in events if e.type is StreamEventType.ERROR]

    assert error_events
    assert error_events[0].error is not None
    assert error_events[0].error.correlation_id


async def test_context_is_injected_into_instructions() -> None:
    model = FakeChatModel()
    orchestrator = Orchestrator(
        model=model, knowledge=FakeKnowledgeProvider(), sessions=InMemorySessionStore()
    )

    await _collect(orchestrator, "What are money mule indicators?")

    assert model.last_instructions is not None
    assert "Context" in model.last_instructions
    assert "Money mule" in model.last_instructions


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
