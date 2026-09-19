"""Gateway entrypoint: assembles the live platform and serves the API."""

from __future__ import annotations

import os

import uvicorn

from agent_platform.config.settings import load_settings
from agent_platform.runtime.bootstrap import build_platform
from agent_platform_gateway.app import create_app


def main() -> None:
    settings = load_settings()
    platform = build_platform(settings)
    origins = tuple(
        origin.strip()
        for origin in os.getenv("GATEWAY_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    )
    app = create_app(
        orchestrator=platform.orchestrator,
        sessions=platform.orchestrator._sessions,  # noqa: SLF001 - shared store
        allowed_origins=origins,
    )
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
