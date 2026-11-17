"""Knowledge provider interface for grounded retrieval."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_platform.contracts.citations import Citation


class KnowledgeQuery(BaseModel):
    """A retrieval request against a knowledge provider."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    max_results: int = Field(default=5, ge=1, le=50)
    # Optional principal used by providers that enforce document-level security.
    principal_id: str | None = None


class KnowledgeResult(BaseModel):
    """Normalized retrieval output with source attribution."""

    model_config = ConfigDict(frozen=True)

    content: str
    citations: tuple[Citation, ...] = ()


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Retrieves grounded content for the knowledge specialist.

    Implementations target persistent, pre-provisioned resources; they must not create
    or delete backing resources during a request.
    """

    @property
    def name(self) -> str:
        """Stable provider name used in citations and telemetry."""
        ...

    async def retrieve(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Return grounded content and citations for the query."""
        ...

    async def health(self) -> None:
        """Raise if the provider's backing resources are unreachable."""
        ...
