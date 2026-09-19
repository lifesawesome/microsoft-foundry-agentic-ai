# Hosted Agents — Contoso Assistant (Microsoft Foundry)

A **solid, self-contained** hosted agent you can demo to customers in minutes. It shows
the thing customers care about most: **tool calling**. The model decides when to call
local Python functions and grounds its answers in real data instead of guessing — with
**no Bing, no external APIs, and no extra Azure connections**, so it behaves identically
on a laptop and in Foundry.

Built on the current **Microsoft Agent Framework** (`agent-framework-foundry`) and the
**Responses** hosting runtime (`ResponsesHostServer`), deployed with `azd ai agent`.

## What it does (the demo)

The agent (`src/AssistantAgent/main.py`) exposes three tools:

| Tool | What it shows the customer |
|------|----------------------------|
| `get_weather(location)` | Calling a tool for information the base model can't know |
| `get_current_time(timezone)` | Grounding in **live** data (real current time) |
| `search_product_catalog(query)` | Grounding in **enterprise data** (price + stock lookup) |

Great demo prompts (each triggers one or more tool calls):

- "What's the weather in Seattle and what time is it there right now?"
- "How much is the Contoso Laptop 16 and is it in stock?"
- "Compare the two Contoso laptops and tell me which ships today."

## Prerequisites

- **Azure Developer CLI `azd` ≥ 1.27.1** with the `azure.ai.agents` extension ≥ 1.0.0-beta.9.
  > ⚠️ Older `azd` (e.g. 1.26.0) is **incompatible** with the current agent extensions.
  > Upgrade first: `winget upgrade Microsoft.Azd` (Windows) or `brew upgrade azd` (macOS),
  > then `azd extension upgrade --all`.
- An Azure subscription and `azd auth login`.
- **Region:** Hosted Agents (preview) run in **North Central US**. `azd provision` below
  creates a fresh project there, so you don't need an existing one.

## Option A — Deploy to Foundry (recommended)

```powershell
cd hosted-agents
azd auth login

# Create a fresh Foundry project + gpt-4o deployment in North Central US
azd env new assistant-agent
azd env set AZURE_LOCATION northcentralus
azd provision

# Deploy the agent code and smoke-test it
azd deploy
azd ai agent invoke "What's the weather in Seattle and how much is the Contoso Mouse?"
```

`azd ai agent show` prints the status, endpoints, and Playground URL. Open the Playground
to chat with the agent.

## Option B — Run locally first (fastest inner loop)

You still need a Foundry project + model for the LLM calls, and `az login` for
`DefaultAzureCredential`. After `azd provision` (Option A), grab the values:

```powershell
azd env get-values      # copy FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME

cd src/AssistantAgent
Copy-Item .env.example .env    # then edit .env with the two values above
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py                  # serves the Responses API on http://localhost:8088
```

In another terminal:

```powershell
curl -X POST http://localhost:8088/responses `
  -H "Content-Type: application/json" `
  -d '{"input": "What time is it in Tokyo and is the Contoso Monitor 27 in stock?"}'
```

## Customize it

- **Change the behavior:** edit the `instructions` in [src/AssistantAgent/main.py](src/AssistantAgent/main.py).
- **Add a tool:** write a function, decorate it with `@tool(...)`, and add it to the
  `tools=[...]` list. That's the whole extension model.
- **Swap the model:** edit `services.ai-project.deployments[]` in [azure.yaml](azure.yaml)
  before `azd provision`.
- **Real web search:** add a *Grounding with Bing Search* connection to the project and a
  Bing tool — kept out of this sample on purpose so the demo needs zero setup.

## Cleanup

```powershell
azd down
```

## Project structure

```
hosted-agents/
├── azure.yaml                 # azd project: ai-project (model) + AssistantAgent (agent), code-deploy
└── src/AssistantAgent/
    ├── main.py                # Agent + 3 @tool functions + ResponsesHostServer
    ├── requirements.txt       # agent-framework-foundry + hosting runtime
    ├── .env.example           # local-run env template
    └── .agentignore           # excludes .venv/.env from the deployed zip
```

> The old `WebSearchAgent` example was removed: it claimed to search the web but had **no
> web-search tool**, and used outdated `agent-framework` packages. This replacement is a
> working, tool-enabled agent on current libraries.
