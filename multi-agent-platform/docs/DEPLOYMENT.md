# Deployment & Operations

## Prerequisites

- A Microsoft Foundry project and a chat model deployment (e.g., `gpt-4o`).
- A persistent Azure AI Search knowledge base (see the Foundry IQ notebook
  `azure-ai-agents/8-foundry-IQ-agents.ipynb` for the resource shapes; provision these once,
  outside request handling).
- Azure Developer CLI (`azd`) and Docker for container builds.
- Managed identity with least-privilege roles: `Search Index Data Reader` on the search
  service and `Cognitive Services OpenAI User` where retrieval calls Azure OpenAI.

## Configuration

Copy `.env.example` to `.env` and set the required values:

| Variable | Purpose |
| --- | --- |
| `AI_FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Chat model deployment |
| `AZURE_AI_SEARCH_ENDPOINT` | Search service endpoint |
| `AZURE_SEARCH_KNOWLEDGE_BASE_NAME` | Pre-provisioned knowledge base |
| `SESSION_BACKEND` | `memory` (dev) or `redis` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional tracing |

## Local development

```powershell
cd multi-agent-platform
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe apps/gateway/main.py     # serves on :8080
```

Open `apps/widget/index.html` (served from any static host) to exercise the gateway.

## Deploy

```powershell
cd multi-agent-platform
azd auth login
azd up
```

Both `gateway` and `orchestrator` build from the solution root so each image includes the
shared `src/agent_platform` library.

## Runbooks

| Symptom | First checks |
| --- | --- |
| 401 from `/chat` | Confirm the auth proxy injects `X-MS-CLIENT-PRINCIPAL-NAME`. |
| 502 `upstream_unavailable` | Model deployment reachable; retrieval returning text; role assignments propagated. |
| Empty / ungrounded answers | Knowledge base name correct; documents indexed; `KnowledgeProvider.health()` passes. |
| 429 `rate_limited` | Expected under load; tune `RateLimiter` capacity/refill. |
| 504 `timeout` | Raise `RUNTIME_REQUEST_TIMEOUT_SECONDS` or investigate slow retrieval/model. |
| Delegated action denied | Expected in MVP: real OBO/token exchange is not yet enabled. |

## Rollback

`azd deploy <service>` redeploys a single service; use container app revisions to roll back
to a previous known-good image.
