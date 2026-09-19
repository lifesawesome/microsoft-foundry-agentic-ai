"""FastAPI application wiring for the gateway."""

from __future__ import annotations

import json
from typing import AsyncIterator, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_platform.contracts.errors import ErrorCode, PlatformError, PlatformException
from agent_platform.contracts.sessions import SessionRef
from agent_platform.contracts.streaming import StreamEvent
from agent_platform.interfaces.sessions import SessionStore
from agent_platform.runtime.orchestrator import Orchestrator
from agent_platform_gateway.auth import Principal, require_principal
from agent_platform_gateway.rate_limit import RateLimiter


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatBody(BaseModel):
    text: str = Field(min_length=1)
    session_id: str | None = None


def create_app(
    *,
    orchestrator: Orchestrator,
    sessions: SessionStore,
    rate_limiter: RateLimiter | None = None,
    principal_dependency: Callable[..., object] = require_principal,
    allowed_origins: tuple[str, ...] = (),
) -> FastAPI:
    """Build the gateway app around an assembled orchestrator and session store."""
    app = FastAPI(title="Multi-Agent Platform Gateway", version="0.1.0")
    limiter = rate_limiter or RateLimiter()

    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    def _error_response(error: PlatformError, status: int) -> JSONResponse:
        return JSONResponse(status_code=status, content=error.model_dump(mode="json"))

    @app.exception_handler(PlatformException)
    async def _handle_platform_exception(_: Request, exc: PlatformException):
        return _error_response(exc.error, _status_for(exc.error.code))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", response_model=CreateSessionResponse)
    async def create_session(
        principal: Principal = Depends(principal_dependency),
    ) -> CreateSessionResponse:
        session = await sessions.create(principal.principal_id, channel="rest")
        return CreateSessionResponse(session_id=session.session_id)

    @app.post("/chat")
    async def chat(
        body: ChatBody,
        principal: Principal = Depends(principal_dependency),
    ) -> StreamingResponse:
        if not limiter.allow(principal.principal_id):
            raise PlatformException.of(
                ErrorCode.RATE_LIMITED, "Too many requests; please slow down."
            )
        session = await _resolve_session(sessions, body.session_id, principal)
        stream = orchestrator.run(text=body.text, session=session)
        return StreamingResponse(
            _to_sse(stream, session_id=session.session_id),
            media_type="text/event-stream",
        )

    @app.get("/sessions/{session_id}/history")
    async def history(
        session_id: str,
        principal: Principal = Depends(principal_dependency),
    ) -> dict[str, object]:
        session = await sessions.get(session_id)
        if session is None or session.principal_id != principal.principal_id:
            raise PlatformException.of(ErrorCode.NOT_FOUND, "Session not found.")
        messages = await sessions.history(session_id)
        return {"messages": [m.model_dump(mode="json") for m in messages]}

    return app


async def _resolve_session(
    sessions: SessionStore, session_id: str | None, principal: Principal
) -> SessionRef:
    if session_id is None:
        return await sessions.create(principal.principal_id, channel="rest")
    existing = await sessions.get(session_id)
    if existing is None or existing.principal_id != principal.principal_id:
        raise PlatformException.of(ErrorCode.NOT_FOUND, "Session not found.")
    return existing


async def _to_sse(
    events: AsyncIterator[StreamEvent], *, session_id: str
) -> AsyncIterator[bytes]:
    yield _sse(StreamEvent.session(session_id))
    async for event in events:
        yield _sse(event)


def _sse(event: StreamEvent) -> bytes:
    data = json.dumps(event.model_dump(mode="json"))
    return f"event: {event.type.value}\ndata: {data}\n\n".encode()


def _status_for(code: ErrorCode) -> int:
    return {
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.UNAUTHENTICATED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.DELEGATION_REQUIRED: 403,
        ErrorCode.TOOL_POLICY_DENIED: 403,
        ErrorCode.TIMEOUT: 504,
        ErrorCode.UPSTREAM_UNAVAILABLE: 502,
        ErrorCode.CANCELLED: 499,
        ErrorCode.INTERNAL: 500,
    }.get(code, 500)
