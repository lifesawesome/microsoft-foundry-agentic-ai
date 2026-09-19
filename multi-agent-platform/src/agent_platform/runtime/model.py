"""Chat model abstraction used by specialists.

Decouples orchestration from a specific SDK so the runtime is testable without Azure. A
real implementation wraps the Foundry / Azure OpenAI client; tests supply a fake.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from agent_platform.contracts.messages import Role


class ModelMessage(BaseModel):
    """A minimal message passed to the chat model."""

    model_config = ConfigDict(frozen=True)

    role: Role
    content: str


@runtime_checkable
class ChatModel(Protocol):
    """Streams a completion for a sequence of messages."""

    async def stream(
        self,
        messages: tuple[ModelMessage, ...],
        *,
        instructions: str,
    ) -> AsyncIterator[str]:
        """Yield text deltas for the assistant's reply."""
        ...
