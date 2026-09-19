"""Authenticated streaming gateway for the multi-agent platform.

Exposes the orchestrator to browser and REST clients. Responsibilities:
- Authenticate the caller and resolve a stable principal id.
- Own session lifecycle; the browser never sees Foundry/Search/Azure credentials.
- Stream responses as Server-Sent Events.
- Return structured errors and enforce basic rate limiting.
"""

from agent_platform_gateway.app import create_app

__all__ = ["create_app"]
