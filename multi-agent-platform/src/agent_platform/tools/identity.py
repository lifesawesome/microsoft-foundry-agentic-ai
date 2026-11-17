"""Simulated delegated identity provider.

Wires the "act on behalf of the user" boundary without performing a real OAuth
On-Behalf-Of / token exchange. It records requested consent and issues a clearly-marked
simulated token so downstream policy and audit paths are exercised end to end. Replace
with a real Entra Agent ID / OBO implementation to enable production actions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_platform.interfaces.identity import DelegatedToken


class SimulatedDelegatedIdentityProvider:
    """A development-only `DelegatedIdentityProvider`.

    Consent is granted for scopes explicitly allow-listed at construction time; all other
    scope requests are treated as not consented.
    """

    def __init__(self, consented_scopes: frozenset[str] | None = None) -> None:
        self._consented = consented_scopes or frozenset()

    async def has_consent(self, principal_id: str, scopes: tuple[str, ...]) -> bool:
        return bool(scopes) and all(scope in self._consented for scope in scopes)

    async def acquire_token(
        self,
        principal_id: str,
        scopes: tuple[str, ...],
    ) -> DelegatedToken:
        if not await self.has_consent(principal_id, scopes):
            raise PermissionError(
                f"User {principal_id} has not consented to scopes: {', '.join(scopes)}"
            )
        return DelegatedToken(
            principal_id=principal_id,
            access_token=f"simulated-obo-token::{principal_id}",
            scopes=scopes,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
