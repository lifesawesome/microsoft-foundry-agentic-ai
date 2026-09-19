"""Citation and source-attribution contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """A reference to a knowledge source that grounded part of a response."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    title: str | None = None
    snippet: str | None = None
    url: str | None = None
    # Name of the knowledge source or provider that produced this citation.
    provider: str | None = None
    score: float | None = None
