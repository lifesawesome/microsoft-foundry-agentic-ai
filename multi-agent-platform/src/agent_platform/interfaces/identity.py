"""Delegated identity interface for acting on behalf of a user.

This boundary models per-user consent and OAuth On-Behalf-Of / token exchange (the Entra
Agent ID pattern). The MVP wires the boundary and a simulated action; real external
side-effecting actions are added later without changing this contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class DelegatedToken(BaseModel):
    """A short-lived token scoped to act on behalf of a specific user."""

    model_config = ConfigDict(frozen=True)

    principal_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1, repr=False)
    scopes: tuple[str, ...] = ()
    expires_at: datetime


@runtime_checkable
class DelegatedIdentityProvider(Protocol):
    """Exchanges an authenticated user's context for a delegated action token."""

    async def has_consent(self, principal_id: str, scopes: tuple[str, ...]) -> bool:
        """Return whether the user has consented to the requested scopes."""
        ...

    async def acquire_token(
        self,
        principal_id: str,
        scopes: tuple[str, ...],
    ) -> DelegatedToken:
        """Return a delegated token for the requested scopes.

        Raises if consent is missing or the exchange fails.
        """
        ...
