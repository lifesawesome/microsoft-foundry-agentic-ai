"""One-time provisioning of a persistent Foundry IQ knowledge base.

Creates (idempotently) a stable Azure AI Search index, knowledge source, and knowledge
base that the multi-agent platform consumes at runtime. Unlike the workshop notebook,
these resources use fixed names and are not deleted, so the platform can rely on them.

Reuses the workshop `.env`:
  AZURE_AI_SEARCH_ENDPOINT, AZURE_OPENAI_ENDPOINT, EMBEDDING_MODEL_DEPLOYMENT_NAME,
  SEARCH_AUTHENTICATION_METHOD, and optionally AZURE_AI_SEARCH_API_KEY.

Usage:
  python scripts/provision_knowledge_base.py                 # create + seed samples
  python scripts/provision_knowledge_base.py --no-seed       # create empty
  python scripts/provision_knowledge_base.py --name my-kb    # custom stable name

On success it prints the exact line to add to your .env:
  AZURE_SEARCH_KNOWLEDGE_BASE_NAME=<name>
"""

from __future__ import annotations

import argparse
import os

from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    KnowledgeBase,
    KnowledgeSourceReference,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchIndexFieldReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.knowledgebases.models import (
    KnowledgeRetrievalMinimalReasoningEffort,
    KnowledgeRetrievalOutputMode,
)
from dotenv import find_dotenv, load_dotenv
from openai import AzureOpenAI

# text-embedding-3-large produces 3072-dimensional vectors.
_EMBEDDING_DIMENSIONS = 3072

# Small, clearly-marked sample corpus so retrieval works on first run. Replace with your
# own documents by re-running with --no-seed and uploading through your own pipeline.
_SEED_DOCUMENTS = [
    {
        "id": "sample-001",
        "title": "Platform Overview",
        "content": (
            "The multi-agent platform routes user questions to specialized agents and "
            "grounds answers on this knowledge base. Replace these sample documents with "
            "your own enterprise content."
        ),
    },
    {
        "id": "sample-002",
        "title": "Grounding and Citations",
        "content": (
            "Answers are grounded on retrieved passages and include citations back to the "
            "source document so users can verify the information."
        ),
    },
    {
        "id": "sample-003",
        "title": "Adding Your Own Knowledge",
        "content": (
            "To use your own data, upload documents with 'id', 'title', and 'content' "
            "fields to the platform knowledge index, then re-run retrieval. The knowledge "
            "base automatically serves the latest indexed content."
        ),
    },
]


def _strip_openai_suffix(endpoint: str) -> str:
    for suffix in ("/openai/v1", "/openai", "/v1"):
        if endpoint.endswith(suffix):
            return endpoint[: -len(suffix)]
    return endpoint


def _require(values: dict[str, str | None]) -> None:
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(
            "Missing required environment variables: " + ", ".join(sorted(missing))
        )


def _build_index(index_name: str, openai_endpoint: str, embedding_deployment: str) -> SearchIndex:
    return SearchIndex(
        name=index_name,
        fields=[
            SearchField(name="id", type=SearchFieldDataType.String, key=True),
            SearchField(name="title", type=SearchFieldDataType.String, searchable=True),
            SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=_EMBEDDING_DIMENSIONS,
                vector_search_profile_name="vector-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[
                VectorSearchProfile(
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config",
                    vectorizer_name="openai-vectorizer",
                )
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="openai-vectorizer",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=openai_endpoint,
                        deployment_name=embedding_deployment,
                        model_name=embedding_deployment,
                    ),
                )
            ],
        ),
        semantic_search=SemanticSearch(
            default_configuration_name="semantic-config",
            configurations=[
                SemanticConfiguration(
                    name="semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")]
                    ),
                )
            ],
        ),
    )


def _seed(
    search_endpoint: str,
    index_name: str,
    search_credential: AzureKeyCredential | AzureCliCredential,
    aoai_client: AzureOpenAI,
    embedding_deployment: str,
) -> int:
    texts = [doc["content"] for doc in _SEED_DOCUMENTS]
    response = aoai_client.embeddings.create(input=texts, model=embedding_deployment)
    documents = [
        {**doc, "content_vector": item.embedding}
        for doc, item in zip(_SEED_DOCUMENTS, response.data, strict=True)
    ]
    with SearchClient(
        endpoint=search_endpoint,
        index_name=index_name,
        credential=search_credential,
    ) as client:
        results = client.upload_documents(documents)
    failures = [f"{r.key}: {r.error_message}" for r in results if not r.succeeded]
    if failures:
        raise SystemExit("Seed upload failures:\n" + "\n".join(failures))
    return len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        default=os.getenv("AZURE_SEARCH_KNOWLEDGE_BASE_NAME", "platform-kb"),
        help="Stable knowledge base name (default: platform-kb or existing env value).",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Create the resources without uploading sample documents.",
    )
    args = parser.parse_args()

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)

    search_endpoint = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
    openai_endpoint = _strip_openai_suffix(os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    embedding_deployment = os.getenv("EMBEDDING_MODEL_DEPLOYMENT_NAME")
    search_auth = os.getenv("SEARCH_AUTHENTICATION_METHOD", "azure-ad").lower()
    search_api_key = os.getenv("AZURE_AI_SEARCH_API_KEY")

    _require(
        {
            "AZURE_AI_SEARCH_ENDPOINT": search_endpoint,
            "AZURE_OPENAI_ENDPOINT": openai_endpoint,
            "EMBEDDING_MODEL_DEPLOYMENT_NAME": embedding_deployment,
        }
    )
    assert search_endpoint and openai_endpoint and embedding_deployment

    kb_name = args.name
    index_name = f"{kb_name}-index"
    ks_name = f"{kb_name}-ks"

    credential = AzureCliCredential()
    if search_auth == "api-search-key":
        if not search_api_key:
            raise SystemExit(
                "AZURE_AI_SEARCH_API_KEY is required when SEARCH_AUTHENTICATION_METHOD "
                "is 'api-search-key'."
            )
        search_credential: AzureKeyCredential | AzureCliCredential = AzureKeyCredential(
            search_api_key
        )
    else:
        search_credential = credential

    index_client = SearchIndexClient(endpoint=search_endpoint, credential=search_credential)
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    aoai_client = AzureOpenAI(
        api_version="2024-02-01",
        azure_endpoint=openai_endpoint,
        azure_ad_token_provider=token_provider,
    )

    try:
        print(f"Creating index '{index_name}'...")
        index_client.create_or_update_index(
            _build_index(index_name, openai_endpoint, embedding_deployment)
        )

        if not args.no_seed:
            print("Uploading sample documents...")
            count = _seed(
                search_endpoint,
                index_name,
                search_credential,
                aoai_client,
                embedding_deployment,
            )
            print(f"Uploaded {count} sample documents.")

        print(f"Creating knowledge source '{ks_name}'...")
        index_client.create_or_update_knowledge_source(
            SearchIndexKnowledgeSource(
                name=ks_name,
                description="Platform knowledge source over the persistent index",
                search_index_parameters=SearchIndexKnowledgeSourceParameters(
                    search_index_name=index_name,
                    source_data_fields=[
                        SearchIndexFieldReference(name="content"),
                        SearchIndexFieldReference(name="title"),
                    ],
                ),
            )
        )

        print(f"Creating knowledge base '{kb_name}'...")
        index_client.create_or_update_knowledge_base(
            knowledge_base=KnowledgeBase(
                name=kb_name,
                description="Persistent knowledge base for the multi-agent platform",
                knowledge_sources=[KnowledgeSourceReference(name=ks_name)],
                output_mode=KnowledgeRetrievalOutputMode.EXTRACTIVE_DATA,
                retrieval_reasoning_effort=KnowledgeRetrievalMinimalReasoningEffort(),
            )
        )
    finally:
        aoai_client.close()
        index_client.close()
        credential.close()

    print("\nDone. Add this line to your .env:")
    print(f"AZURE_SEARCH_KNOWLEDGE_BASE_NAME={kb_name}")


if __name__ == "__main__":
    main()
