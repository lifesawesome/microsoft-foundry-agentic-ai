"""Contract tests for the gateway API using fakes (no Azure required)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_platform_gateway.app import create_app
from agent_platform_gateway.auth import Principal
from agent_platform_gateway.rate_limit import RateLimiter
from agent_platform.runtime.orchestrator import Orchestrator
from agent_platform.sessions.memory import InMemorySessionStore
from tests.fakes import FakeChatModel, FakeKnowledgeProvider


def _client(principal_id: str = "user-1", limiter: RateLimiter | None = None) -> TestClient:
    sessions = InMemorySessionStore()
    orchestrator = Orchestrator(
        model=FakeChatModel("grounded reply"),
        knowledge=FakeKnowledgeProvider(),
        sessions=sessions,
    )

    async def _principal() -> Principal:
        return Principal(principal_id=principal_id)

    app = create_app(
        orchestrator=orchestrator,
        sessions=sessions,
        rate_limiter=limiter,
        principal_dependency=_principal,
    )
    return TestClient(app)


def _events(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def test_health_is_open() -> None:
    with _client() as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_unauthenticated_chat_is_rejected() -> None:
    sessions = InMemorySessionStore()
    orchestrator = Orchestrator(
        model=FakeChatModel(), knowledge=FakeKnowledgeProvider(), sessions=sessions
    )
    app = create_app(orchestrator=orchestrator, sessions=sessions)
    with TestClient(app) as client:
        assert client.post("/chat", json={"text": "hi"}).status_code == 401


def test_chat_streams_session_text_and_completion() -> None:
    with _client() as client:
        response = client.post("/chat", json={"text": "How do money mules work?"})
        assert response.status_code == 200
        events = _events(response.text)
        types = [event["type"] for event in events]
        assert types[0] == "session"
        assert "text_delta" in types
        assert types[-1] == "completed"


def test_history_is_scoped_to_owner() -> None:
    with _client(principal_id="owner") as client:
        created = client.post("/sessions").json()
        session_id = created["session_id"]
        client.post("/chat", json={"text": "hello there", "session_id": session_id})
        history = client.get(f"/sessions/{session_id}/history")
        assert history.status_code == 200
        assert history.json()["messages"]


def test_rate_limit_returns_429() -> None:
    limiter = RateLimiter(capacity=1, refill_per_second=0.0)
    with _client(limiter=limiter) as client:
        first = client.post("/chat", json={"text": "one"})
        second = client.post("/chat", json={"text": "two"})
        assert first.status_code == 200
        assert second.status_code == 429


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
