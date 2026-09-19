"""Specialist agents composing the orchestrated workflow.

The MVP runs specialists in one process. Each has a single, well-defined responsibility so
the workflow stays deterministic and traceable:

- Router: decide whether a turn needs grounded knowledge.
- Knowledge: retrieve grounded context and citations from a `KnowledgeProvider`.
- Response: stream the final grounded answer via the `ChatModel`.
"""

from __future__ import annotations

from agent_platform.contracts.citations import Citation
from agent_platform.interfaces.knowledge import (
    KnowledgeProvider,
    KnowledgeQuery,
    KnowledgeResult,
)

_GREETING_PREFIXES = ("hi", "hello", "hey", "thanks", "thank you")


class RouterSpecialist:
    """Decides whether a user turn requires knowledge retrieval."""

    def needs_knowledge(self, text: str) -> bool:
        stripped = text.strip().lower()
        if not stripped:
            return False
        # Short social messages don't need grounding; everything else does.
        if len(stripped.split()) <= 3 and stripped.startswith(_GREETING_PREFIXES):
            return False
        return True


class KnowledgeSpecialist:
    """Retrieves grounded content from the configured knowledge provider."""

    def __init__(self, provider: KnowledgeProvider, *, max_results: int = 5) -> None:
        self._provider = provider
        self._max_results = max_results

    async def gather(self, text: str, principal_id: str) -> KnowledgeResult:
        return await self._provider.retrieve(
            KnowledgeQuery(
                text=text,
                max_results=self._max_results,
                principal_id=principal_id,
            )
        )


class ResponseSpecialist:
    """Builds the grounded instructions used to produce the final answer."""

    BASE_INSTRUCTIONS = (
        "You are a helpful assistant. Answer using only the provided context when it is "
        "present. Cite sources inline using their source id in brackets. If the context "
        "does not contain the answer, say so plainly instead of guessing."
    )

    def build_instructions(self, context: str | None) -> str:
        if not context:
            return self.BASE_INSTRUCTIONS
        return f"{self.BASE_INSTRUCTIONS}\n\n## Context\n{context}"

    def merge_citations(
        self, citations: tuple[Citation, ...]
    ) -> tuple[Citation, ...]:
        seen: dict[str, Citation] = {}
        for citation in citations:
            seen.setdefault(citation.source_id, citation)
        return tuple(seen.values())
