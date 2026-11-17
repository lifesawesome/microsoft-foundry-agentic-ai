"""Authentication boundary for the gateway.

Resolves an authenticated principal from the request. The default implementation trusts a
signed upstream identity header (for local dev and reverse-proxy auth); production should
replace it with Entra ID / JWT validation. The browser is never given Azure credentials.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from agent_platform.contracts.errors import ErrorCode, PlatformException


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    principal_id: str


async def require_principal(
    x_ms_client_principal_name: str | None = Header(default=None),
) -> Principal:
    """Resolve the authenticated principal or reject the request.

    Uses the `X-MS-CLIENT-PRINCIPAL-NAME` header populated by Azure App Service / Container
    Apps authentication. Replace with full token validation for standalone deployments.
    """
    if not x_ms_client_principal_name:
        raise PlatformException.of(
            ErrorCode.UNAUTHENTICATED, "Authentication is required."
        )
    return Principal(principal_id=x_ms_client_principal_name)
