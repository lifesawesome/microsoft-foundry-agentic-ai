"""Foundry IQ / Azure AI Search knowledge provider.

Retrieves grounded content from a persistent, pre-provisioned knowledge base using the
Azure AI Search knowledge base retrieval API. This provider never creates or deletes
Search resources; provisioning is a separate one-time step (see scripts/provision).
"""

from __future__ import annotations

import asyncio
from typing import Any

from azure.core.credentials import AzureKeyCredential, TokenCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalSemanticIntent,
)

from agent_platform.contracts.citations import Citation
from agent_platform.interfaces.knowledge import KnowledgeQuery, KnowledgeResult


class FoundryIQKnowledgeProvider:
    """A `KnowledgeProvider` backed by an Azure AI Search knowledge base."""

    def __init__(
        self,
        *,
        endpoint: str,
        knowledge_base_name: str,
        credential: AzureKeyCredential | TokenCredential,
        name: str = "foundry-iq",
    ) -> None:
        self._name = name
        self._knowledge_base_name = knowledge_base_name
        self._client = KnowledgeBaseRetrievalClient(
            endpoint=endpoint,
            credential=credential,
            knowledge_base_name=knowledge_base_name,
        )

    @property
    def name(self) -> str:
        return self._name

    async def retrieve(self, query: KnowledgeQuery) -> KnowledgeResult:
        request = KnowledgeBaseRetrievalRequest(
            intents=[KnowledgeRetrievalSemanticIntent(search=query.text)],
            max_output_documents=query.max_results,
        )
        response = await asyncio.to_thread(self._client.retrieve, request)
        content = _extract_text(response)
        citations = _extract_citations(response, provider=self._name)
        return KnowledgeResult(content=content, citations=citations)

    async def health(self) -> None:
        request = KnowledgeBaseRetrievalRequest(
            intents=[KnowledgeRetrievalSemanticIntent(search="health check")],
            max_output_documents=1,
        )
        await asyncio.to_thread(self._client.retrieve, request)

    def close(self) -> None:
        self._client.close()


def _extract_text(response: Any) -> str:
    parts: list[str] = []
    for message in getattr(response, "response", None) or []:
        for item in getattr(message, "content", None) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _extract_citations(response: Any, *, provider: str) -> tuple[Citation, ...]:
    citations: list[Citation] = []
    for reference in getattr(response, "references", None) or []:
        source_id = (
            getattr(reference, "doc_key", None)
            or getattr(reference, "id", None)
            or "unknown"
        )
        source_data = getattr(reference, "source_data", None) or {}
        title = source_data.get("title") if isinstance(source_data, dict) else None
        snippet = source_data.get("content") if isinstance(source_data, dict) else None
        citations.append(
            Citation(
                source_id=str(source_id),
                title=title,
                snippet=snippet,
                url=getattr(reference, "citation_url", None),
                provider=provider,
                score=getattr(reference, "reranker_score", None),
            )
        )
    return tuple(citations)
