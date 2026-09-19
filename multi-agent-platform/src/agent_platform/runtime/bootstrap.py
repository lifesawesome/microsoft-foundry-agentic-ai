"""Composition root: builds a live orchestrator from settings.

Kept separate from the runtime so tests can assemble orchestrators from fakes without
touching Azure. Only imported by the deployable apps.
"""

from __future__ import annotations

from dataclasses import dataclass

from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

from agent_platform.config.settings import Settings
from agent_platform.knowledge.foundry_iq import FoundryIQKnowledgeProvider
from agent_platform.runtime.foundry_model import FoundryChatModel
from agent_platform.runtime.orchestrator import Orchestrator
from agent_platform.sessions.memory import InMemorySessionStore


@dataclass
class Platform:
    """Assembled runtime with the resources it owns, for lifecycle management."""

    orchestrator: Orchestrator
    _project_client: AIProjectClient
    _knowledge: FoundryIQKnowledgeProvider
    _credential: DefaultAzureCredential

    def close(self) -> None:
        self._knowledge.close()
        self._project_client.close()
        self._credential.close()


def build_platform(settings: Settings) -> Platform:
    """Construct a live `Orchestrator` and the clients backing it."""
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=settings.foundry.project_endpoint,
        credential=credential,
    )
    model = FoundryChatModel(
        project_client.get_openai_client(),
        model=settings.foundry.model_deployment,
    )
    knowledge = FoundryIQKnowledgeProvider(
        endpoint=settings.knowledge.search_endpoint,
        knowledge_base_name=settings.knowledge.knowledge_base_name,
        credential=credential,
    )
    sessions = _build_sessions(settings)
    orchestrator = Orchestrator(
        model=model,
        knowledge=knowledge,
        sessions=sessions,
        request_timeout_seconds=settings.limits.request_timeout_seconds,
    )
    return Platform(
        orchestrator=orchestrator,
        _project_client=project_client,
        _knowledge=knowledge,
        _credential=credential,
    )


def _build_sessions(settings: Settings):
    if settings.sessions.backend == "redis":
        # Redis-backed sessions are added in a later phase; fail loudly if requested now.
        raise NotImplementedError(
            "Redis session backend is not yet implemented; set SESSION_BACKEND=memory."
        )
    return InMemorySessionStore()


__all__ = ["Platform", "build_platform", "AzureKeyCredential"]
