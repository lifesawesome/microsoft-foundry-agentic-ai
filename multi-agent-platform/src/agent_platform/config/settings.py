"""Typed configuration loaded from the environment.

Validates required settings at startup so misconfiguration fails fast with a clear
message instead of surfacing as an obscure runtime error.
"""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class FoundrySettings(BaseModel):
    """Microsoft Foundry project and model settings."""

    model_config = ConfigDict(frozen=True)

    project_endpoint: str
    model_deployment: str


class KnowledgeSettings(BaseModel):
    """Persistent Foundry IQ / Azure AI Search knowledge settings."""

    model_config = ConfigDict(frozen=True)

    search_endpoint: str
    knowledge_base_name: str
    search_knowledge_api_version: str = "2025-11-01-Preview"


class SessionSettings(BaseModel):
    """Session store configuration."""

    model_config = ConfigDict(frozen=True)

    # "memory" for local dev, "redis" for shared/production state.
    backend: str = "memory"
    redis_url: str | None = None


class RuntimeLimits(BaseModel):
    """Bounds that keep orchestration deterministic and safe."""

    model_config = ConfigDict(frozen=True)

    max_turns: int = Field(default=6, ge=1, le=50)
    request_timeout_seconds: float = Field(default=60.0, gt=0)


class Settings(BaseModel):
    """Top-level application settings."""

    model_config = ConfigDict(frozen=True)

    foundry: FoundrySettings
    knowledge: KnowledgeSettings
    sessions: SessionSettings
    limits: RuntimeLimits
    applicationinsights_connection_string: str | None = None


def _require(values: dict[str, str | None]) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(sorted(missing))}"
        )


def load_settings() -> Settings:
    """Load and validate settings from the environment (and a discovered .env)."""
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)

    project_endpoint = os.getenv("AI_FOUNDRY_PROJECT_ENDPOINT")
    model_deployment = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    search_endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
    knowledge_base_name = os.getenv("AZURE_SEARCH_KNOWLEDGE_BASE_NAME")

    _require(
        {
            "AI_FOUNDRY_PROJECT_ENDPOINT": project_endpoint,
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_deployment,
            "AZURE_AI_SEARCH_ENDPOINT": search_endpoint,
            "AZURE_SEARCH_KNOWLEDGE_BASE_NAME": knowledge_base_name,
        }
    )

    backend = os.getenv("SESSION_BACKEND", "memory").lower()
    redis_url = os.getenv("REDIS_URL")
    if backend == "redis" and not redis_url:
        raise RuntimeError("REDIS_URL is required when SESSION_BACKEND is 'redis'.")

    # Narrow types after _require guarantees these are present.
    assert project_endpoint and model_deployment
    assert search_endpoint and knowledge_base_name

    return Settings(
        foundry=FoundrySettings(
            project_endpoint=project_endpoint,
            model_deployment=model_deployment,
        ),
        knowledge=KnowledgeSettings(
            search_endpoint=search_endpoint,
            knowledge_base_name=knowledge_base_name,
            search_knowledge_api_version=os.getenv(
                "AZURE_SEARCH_KNOWLEDGE_API_VERSION", "2025-11-01-Preview"
            ),
        ),
        sessions=SessionSettings(backend=backend, redis_url=redis_url),
        limits=RuntimeLimits(
            max_turns=int(os.getenv("RUNTIME_MAX_TURNS", "6")),
            request_timeout_seconds=float(
                os.getenv("RUNTIME_REQUEST_TIMEOUT_SECONDS", "60")
            ),
        ),
        applicationinsights_connection_string=os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING"
        ),
    )
