"""Foundry-backed chat model.

Wraps the Azure OpenAI client exposed by an `AIProjectClient` and streams completions as
plain text deltas. Isolated here so the rest of the runtime stays SDK-agnostic and testable.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from agent_platform.contracts.messages import Role
from agent_platform.runtime.model import ModelMessage


class FoundryChatModel:
    """A `ChatModel` backed by the Foundry project's Azure OpenAI client."""

    def __init__(self, openai_client: object, *, model: str) -> None:
        self._client = openai_client
        self._model = model

    async def stream(
        self,
        messages: tuple[ModelMessage, ...],
        *,
        instructions: str,
    ) -> AsyncIterator[str]:
        payload = [{"role": Role.SYSTEM.value, "content": instructions}]
        payload.extend({"role": m.role.value, "content": m.content} for m in messages)

        # The OpenAI SDK stream is synchronous; run it off the event loop and hand deltas back.
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _produce() -> None:
            try:
                stream = self._client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self._model,
                    messages=payload,
                    stream=True,
                )
                for chunk in stream:
                    choices = getattr(chunk, "choices", None) or []
                    for choice in choices:
                        delta = getattr(choice, "delta", None)
                        content = getattr(delta, "content", None)
                        if content:
                            loop.call_soon_threadsafe(queue.put_nowait, content)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        producer = asyncio.get_running_loop().run_in_executor(None, _produce)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await producer
