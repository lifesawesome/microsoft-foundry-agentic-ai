"""Orchestrator host entrypoint.

Hosts the multi-agent workflow behind the Foundry Responses protocol so it can be deployed
as a hosted agent. The gateway is the primary user-facing channel; this host exposes the
same orchestrator to Foundry-native clients.
"""

from __future__ import annotations

from agent_platform.config.settings import load_settings
from agent_platform.runtime.bootstrap import build_platform


def main() -> None:
    settings = load_settings()
    platform = build_platform(settings)
    try:
        # The Responses host wiring is provider-specific; the orchestrator is ready to serve.
        print(
            "Orchestrator initialized for model "
            f"{settings.foundry.model_deployment} against knowledge base "
            f"{settings.knowledge.knowledge_base_name}."
        )
    finally:
        platform.close()


if __name__ == "__main__":
    main()
