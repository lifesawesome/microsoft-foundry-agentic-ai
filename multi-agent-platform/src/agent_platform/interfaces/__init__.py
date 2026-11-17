"""Provider interfaces — the platform's extension points.

Only Foundry IQ / Azure AI Search knowledge and the REST/web channel are implemented in
the MVP. These abstractions keep deferred capabilities (Teams, SharePoint, OneDrive, Blob,
ADLS, Data Lake Data Agents, Bing, MCP, social/external-API actions) pluggable without
changing orchestrator or gateway code.
"""

from agent_platform.interfaces.channels import ChannelAdapter, InboundMessage
from agent_platform.interfaces.identity import (
    DelegatedIdentityProvider,
    DelegatedToken,
)
from agent_platform.interfaces.knowledge import (
    KnowledgeProvider,
    KnowledgeQuery,
    KnowledgeResult,
)
from agent_platform.interfaces.sessions import SessionStore
from agent_platform.interfaces.tools import (
    ToolDefinition,
    ToolPolicy,
    ToolProvider,
)

__all__ = [
    "ChannelAdapter",
    "DelegatedIdentityProvider",
    "DelegatedToken",
    "InboundMessage",
    "KnowledgeProvider",
    "KnowledgeQuery",
    "KnowledgeResult",
    "SessionStore",
    "ToolDefinition",
    "ToolPolicy",
    "ToolProvider",
]
