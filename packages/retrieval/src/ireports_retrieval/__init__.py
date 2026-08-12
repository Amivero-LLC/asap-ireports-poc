"""Retrieval against an OpenSearch-compatible vector collection.

Application code imports the port and the types, never an OpenSearch client and never a field
name — those live in `mapping`, one module, because the AWS collection's real schema is
unconfirmed (Q-02) and adapting to it must be a one-file change.

    from ireports_retrieval import OpenSearchRetriever, connect

    retriever = OpenSearchRetriever(connect(), build_embedding_gateway())
    spans = retriever.retrieve(case_id="CASE-TEST-001", query="foreign contacts", k=8)
"""

from __future__ import annotations

from typing import Any

from . import mapping
from .index import BATCH, IndexableSpan, IndexResult, index_case
from .port import (
    MAX_K,
    InMemoryRetriever,
    OpenSearchRetriever,
    RetrievalError,
    RetrievedSpan,
    Retriever,
)

DEFAULT_URL = "http://localhost:9201"
"""The compose stack's OpenSearch. 9201 avoids colliding with any other local cluster."""


def connect(url: str | None = None) -> Any:
    """An OpenSearch client for the local development cluster.

    **Local only.** An AWS collection needs SigV4 request signing (`AWSV4SignerAuth` plus a
    credentials provider), which is a different construction and a different failure surface —
    `OpenSearchRetriever` takes a client rather than a URL precisely so that stays a wiring
    decision instead of a code change here.
    """
    import os

    from opensearchpy import OpenSearch

    return OpenSearch(
        hosts=[url or os.environ.get("IREPORTS_OPENSEARCH_URL") or DEFAULT_URL],
        http_compress=True,
        timeout=30,
    )


__all__ = [
    "BATCH",
    "DEFAULT_URL",
    "MAX_K",
    "InMemoryRetriever",
    "IndexResult",
    "IndexableSpan",
    "OpenSearchRetriever",
    "RetrievalError",
    "RetrievedSpan",
    "Retriever",
    "connect",
    "index_case",
    "mapping",
]
