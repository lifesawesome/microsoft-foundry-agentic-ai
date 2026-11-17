"""Tests for Agent Framework routing and the tool/action paths."""

from __future__ import annotations

import pytest

from agent_platform.contracts.streaming import StreamEventType
from agent_platform.runtime.orchestrator import Orchestrator
from agent_platform.sessions.memory import InMemorySessionStore
from agent_platform.tools.actions import CREATE_CASE_SCOPES, build_create_case_tool
from agent_platform.tools.identity import SimulatedDelegatedIdentityProvider
from agent_platform.tools.policy import DefaultToolPolicy
from agent_platform.tools.registry import InMemoryToolProvider
from agent_platform.tools.web_search import (
    SimulatedWebSearchBackend,
    build_web_search_tool,
)
from tests.fakes import FakeChatModel, FakeKnowledgeProvider


def _tool_provider() -> InMemoryToolProvider:
    policy = DefaultToolPolicy()
    provider = InMemoryToolProvider(
        lambda definition, call, principal, token: policy.evaluate(
            definition, call, principal_id=principal, delegated_token=token
        )
    )
    provider.register(build_web_search_tool(SimulatedWebSearchBackend()))
    provider.register(build_create_case_tool())
    return provider


def _orchestrator(*, consented: bool) -> Orchestrator:
    identity = SimulatedDelegatedIdentityProvider(
        frozenset(CREATE_CASE_SCOPES) if consented else frozenset()
    )
    return Orchestrator(
        model=FakeChatModel("done"),
        knowledge=FakeKnowledgeProvider(),
        sessions=InMemorySessionStore(),
        tools=_tool_provider(),
        identity=identity,
    )


def _orchestrator(
    *,
    consented: bool,
    model: FakeChatModel | None = None,
    knowledge: FakeKnowledgeProvider | None = None,
) -> Orchestrator:
    identity = SimulatedDelegatedIdentityProvider(
        frozenset(CREATE_CASE_SCOPES) if consented else frozenset()
    )
    return Orchestrator(
        model=model or FakeChatModel("done"),
        knowledge=knowledge or FakeKnowledgeProvider(),
        sessions=InMemorySessionStore(),
        tools=_tool_provider(),
        identity=identity,
    )


async def _collect(orchestrator: Orchestrator, text: str):
    sessions = orchestrator._sessions  # noqa: SLF001 - test setup
    session = await sessions.create("user-1", "rest")
    return [event async for event in orchestrator.run(text=text, session=session)]


async def test_web_search_route_uses_tool_and_streams_citations() -> None:
    knowledge = FakeKnowledgeProvider()
    orchestrator = _orchestrator(consented=True, knowledge=knowledge)

    events = await _collect(orchestrator, "Please search the web for outage reports")
    types = [event.type for event in events]

    assert StreamEventType.CITATIONS in types
    assert types[-1] is StreamEventType.COMPLETED
    assert not knowledge.calls, "web-search route must not hit the knowledge provider"
    citation_event = next(e for e in events if e.type is StreamEventType.CITATIONS)
    assert citation_event.citations
    assert citation_event.citations[0].provider == "web_search"


async def test_side_effecting_action_runs_with_consent() -> None:
    model = FakeChatModel("done")
    orchestrator = _orchestrator(consented=True, model=model)

    events = await _collect(orchestrator, "Please create a case for the delivery delay")
    types = [event.type for event in events]

    assert types[-1] is StreamEventType.COMPLETED
    assert StreamEventType.ERROR not in types
    assert model.last_instructions is not None
    # The simulated case result was grounded into the model's instructions.
    assert "case-" in model.last_instructions.lower()


async def test_side_effecting_action_without_consent_is_reported_not_crashed() -> None:
    model = FakeChatModel("acknowledged")
    orchestrator = _orchestrator(consented=False, model=model)

    events = await _collect(orchestrator, "Please open a case about the outage")
    types = [event.type for event in events]

    # The turn completes gracefully; the denial is surfaced as context to the model.
    assert types[-1] is StreamEventType.COMPLETED
    assert StreamEventType.ERROR not in types
    assert model.last_instructions is not None
    assert "consent" in model.last_instructions.lower()


async def test_knowledge_route_still_grounds_when_no_tool_matches() -> None:
    orchestrator = _orchestrator(consented=True)

    events = await _collect(orchestrator, "How do money mule accounts operate?")
    types = [event.type for event in events]

    assert StreamEventType.CITATIONS in types
    assert types[-1] is StreamEventType.COMPLETED


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
