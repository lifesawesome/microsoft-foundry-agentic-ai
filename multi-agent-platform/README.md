# Multi-Agent Platform

A production-oriented multi-agent solution built on the Microsoft Agent Framework and
Microsoft Foundry. It hosts multiple specialized agents behind a single orchestrator,
grounds them on a persistent Foundry IQ / Azure AI Search knowledge layer, and exposes
them to users through a protected streaming REST API and an embeddable web widget.

This solution is separate from the workshop learning material:

- `azure-ai-agents/`, `agent-framework/`, and `observability-and-evaluations/` remain
  tutorial notebooks.
- `hosted-agents/` remains a focused single-agent deployment sample.
- `multi-agent-platform/` (this folder) is the deployable, extensible application.

## Architecture

```
Browser widget ─┐
                ├─▶ Gateway API ─▶ Orchestrator ─▶ Specialist agents
Other channels ─┘   (auth, SSE)    (routing)        ├─ Knowledge specialist ─▶ Foundry IQ / AI Search
                                                     ├─ Action specialist ────▶ Tool registry (policy-gated)
                                                     └─ Response specialist
                                     Session store (Redis) · Telemetry (App Insights)
```

### Design boundaries

| Concern | Interface | MVP implementation | Deferred |
| --- | --- | --- | --- |
| Enterprise data | `KnowledgeProvider` | Foundry IQ / Azure AI Search | SharePoint, OneDrive, Blob, ADLS, Data Lake Data Agents |
| Tools & actions | `ToolProvider` | Empty registry + policy gate | Bing, MCP, social, external APIs |
| User channels | `ChannelAdapter` | REST API + web widget | Microsoft Teams |
| Conversation state | `SessionStore` | Redis (in-memory for dev) | — |
| Acting on behalf of a user | `DelegatedIdentityProvider` | Boundary wired, simulated action | Real OBO / token-exchange actions |

The delegated-identity boundary is designed in from the start so that "perform actions on
behalf of the user" can be added later without re-architecting authentication. Side-effecting
tools are classified separately and require a delegated user token plus policy approval.

## Layout

```
multi-agent-platform/
├── apps/
│   ├── orchestrator/     # Agent Framework workflow + Responses host
│   ├── gateway/          # Authenticated streaming REST API
│   └── widget/           # Embeddable browser chat client
├── src/agent_platform/   # Shared library: contracts, interfaces, runtime
├── tests/                # Unit, contract, integration, evaluation tests
├── azure.yaml            # Multi-service deployment definition
└── .env.example          # Required configuration
```

## Getting started

```powershell
cd multi-agent-platform
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
copy .env.example .env   # then fill in your Foundry / Search values
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for provisioning and deployment steps.

> Status: Phase 1 (contracts and interfaces) is being scaffolded. Runtime, gateway, and
> widget land in subsequent phases.
