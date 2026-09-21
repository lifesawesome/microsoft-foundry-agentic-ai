# Architecture

The multi-agent platform hosts several specialized agents behind a single orchestrator,
grounds them on a persistent Foundry IQ / Azure AI Search knowledge base, and exposes them
through a protected streaming gateway and an embeddable web widget.

## Components

| Component | Path | Responsibility |
| --- | --- | --- |
| Contracts | `src/agent_platform/contracts` | Channel-neutral message, streaming, citation, tool, session, and error models |
| Interfaces | `src/agent_platform/interfaces` | Extension points: knowledge, tools, sessions, channels, delegated identity |
| Runtime | `src/agent_platform/runtime` | Agent Framework workflow (router, knowledge, action, response executors) + the streaming orchestrator |
| Knowledge | `src/agent_platform/knowledge` | Foundry IQ / Azure AI Search retrieval provider |
| Tools | `src/agent_platform/tools` | Policy-gated registry, read-only web search, simulated side-effecting action, delegated-identity plumbing |
| Sessions | `src/agent_platform/sessions` | Conversation persistence (in-memory today; Redis next) |
| Gateway | `apps/gateway` | Authenticated SSE API; owns session lifecycle |
| Orchestrator host | `apps/orchestrator` | Hosts the workflow behind the Foundry Responses protocol |
| Widget | `apps/widget` | Dependency-free embeddable browser chat |

## Request flow

1. The browser widget calls `POST /chat` on the gateway (authenticated; no Azure creds in
   the browser).
2. The gateway resolves the principal, enforces rate limits, and resolves or creates a
   session.
3. The orchestrator runs one turn on an Agent Framework workflow: the router picks a route
   (respond, ground, or use a tool), the knowledge specialist retrieves from Foundry IQ or
   the action specialist invokes a policy-gated tool, and the response specialist streams
   the grounded answer. Executors emit events in real time through the turn's `emit`
   callback.
4. Events (`session`, `activity`, `text_delta`, `citations`, `completed`, `error`) stream
   back as Server-Sent Events.

## Key design rules

- **Channel neutrality.** Core agents depend only on `contracts`; channels translate to and
  from them via `ChannelAdapter`.
- **Grounding first.** Substantive turns require retrieval; empty model output is a
  structured `upstream_unavailable` error, never a silent success.
- **Delegated identity by design.** "Act on behalf of the user" is modeled as an identity
  problem (`DelegatedIdentityProvider`, OAuth OBO / Entra Agent ID). Side-effecting tools
  require a delegated token plus a policy allow decision. The MVP ships the boundary with a
  simulated provider; real actions are added without re-architecture.
- **Tools are additive.** Read-only tools (e.g., web search) run with the platform identity;
  side-effecting tools require a delegated token. New Bing/MCP/social/external-API tools plug
  into the same `ToolProvider` and policy gate without changing the workflow.
- **Persistent knowledge.** The runtime consumes a pre-provisioned knowledge base and never
  creates or deletes Search resources per request.

## Deferred adapters (interfaces already in place)

Teams channel, SharePoint / OneDrive, Blob / ADLS, Data Lake Data Agents, real Bing search,
external MCP servers, and social / external-API action tools plug into the existing
`ChannelAdapter`, `KnowledgeProvider`, and `ToolProvider` contracts.
