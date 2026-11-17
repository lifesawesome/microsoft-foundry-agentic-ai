"""In-memory fakes used across unit and contract tests."""

from __future__ import annotations

from typing import AsyncIterator

from agent_platform.contracts.citations import Citation
from agent_platform.interfaces.knowledge import KnowledgeQuery, KnowledgeResult
from agent_platform.runtime.model import ModelMessage


class FakeChatModel:
    """A `ChatModel` that streams a scripted reply word by word."""

    def __init__(self, reply: str = "This is a grounded answer.") -> None:
        self._reply = reply
        self.last_instructions: str | None = None
        self.last_messages: tuple[ModelMessage, ...] = ()

    async def stream(
        self,
        messages: tuple[ModelMessage, ...],
        *,
        instructions: str,
    ) -> AsyncIterator[str]:
        self.last_instructions = instructions
        self.last_messages = messages
        for word in self._reply.split():
            yield word + " "


class EmptyChatModel:
    """A `ChatModel` that yields nothing, to exercise the no-output guard."""

    async def stream(
        self,
        messages: tuple[ModelMessage, ...],
        *,
        instructions: str,
    ) -> AsyncIterator[str]:
        return
        yield  # pragma: no cover - makes this an async generator


class FakeKnowledgeProvider:
    """A `KnowledgeProvider` returning a fixed grounded result."""

    def __init__(self, name: str = "fake-kb") -> None:
        self._name = name
        self.calls: list[KnowledgeQuery] = []

    @property
    def name(self) -> str:
        return self._name

    async def retrieve(self, query: KnowledgeQuery) -> KnowledgeResult:
        self.calls.append(query)
        return KnowledgeResult(
            content="Money mule accounts show rapid transfers within 24-48 hours.",
            citations=(
                Citation(source_id="fp-003", title="Money Mule", provider=self._name),
            ),
        )

    async def health(self) -> None:
        return None
