"""Error contracts used across channels and the runtime."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    """Stable, channel-neutral error categories."""

    INVALID_REQUEST = "invalid_request"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    TOOL_POLICY_DENIED = "tool_policy_denied"
    DELEGATION_REQUIRED = "delegation_required"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class PlatformError(BaseModel):
    """A structured error surfaced to callers without leaking internals."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    # Correlates this error with telemetry; safe to show to end users.
    correlation_id: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class PlatformException(Exception):
    """Raised inside the runtime; carries a `PlatformError` for the boundary to emit."""

    def __init__(self, error: PlatformError) -> None:
        super().__init__(error.message)
        self.error = error

    @classmethod
    def of(
        cls,
        code: ErrorCode,
        message: str,
        *,
        correlation_id: str | None = None,
        details: dict[str, str] | None = None,
    ) -> "PlatformException":
        return cls(
            PlatformError(
                code=code,
                message=message,
                correlation_id=correlation_id,
                details=details or {},
            )
        )
