"""Indexing — local only, and that is a decision rather than a limitation.

**AWS owns chunking and embedding in production** (ADR-007). The ingestion pipeline extracts,
chunks, embeds, and populates the collection; iReports queries it. So this module exists to give
a developer something to query locally, not to be the production indexer, and it should never grow
into one.

What it does do faithfully is *record what embedded each document*. A collection whose vectors came
from two different models is not detectably broken — it just retrieves worse — so the model is
stored per document and checked at query time (Q-03).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ireports_gateway import EmbeddingGateway

from . import mapping

_LOG = logging.getLogger(__name__)

BATCH = 16
"""Texts per embedding call. Small enough to stay well inside any request-size limit, large enough
that indexing 34 chunks is three calls rather than thirty-four."""


@dataclass(frozen=True)
class IndexableSpan:
    evidence_id: str
    document_id: str
    title: str
    text: str
    page_number: int
    source_type: str


@dataclass(frozen=True)
class IndexResult:
    index: str
    documents: int
    embedding_model: str
    dimensions: int
    total_tokens: int


def index_case(
    client: Any,
    embedder: EmbeddingGateway,
    *,
    case_id: str,
    spans: tuple[IndexableSpan, ...],
    recreate: bool = True,
) -> IndexResult:
    """Embed and index one case's spans.

    `recreate=True` by default: a partially-updated index is worse than no index, because it
    answers queries with a mixture of old and new content and nothing about the answer says so.
    For a local developer corpus, dropping and rebuilding is both cheap and honest.
    """
    index = mapping.index_for(case_id)
    if recreate and client.indices.exists(index=index):
        client.indices.delete(index=index)
    if not client.indices.exists(index=index):
        client.indices.create(index=index, body=mapping.index_body())

    model = ""
    dimensions = 0
    tokens = 0
    actions: list[dict[str, Any]] = []

    for start in range(0, len(spans), BATCH):
        batch = spans[start : start + BATCH]
        # Title and text together: a chapter heading like "Law Enforcement (XIII)" carries real
        # signal about what the chunk is, and embedding the body alone throws it away.
        embedded = embedder.embed(tuple(f"{s.title}\n\n{s.text}".strip() for s in batch))
        model = embedded.model
        dimensions = embedded.dimensions
        tokens += embedded.total_tokens

        if dimensions != mapping.VECTOR_DIMENSIONS:
            raise ValueError(
                f"{model} produces {dimensions}-dimensional vectors and the index expects "
                f"{mapping.VECTOR_DIMENSIONS}. Fix mapping.VECTOR_DIMENSIONS or the embedding "
                "model — indexing a mismatch makes every later query fail."
            )

        for span, vector in zip(batch, embedded.vectors, strict=True):
            actions.append({"index": {"_index": index, "_id": span.evidence_id}})
            actions.append(
                {
                    mapping.FIELD_CASE_ID: case_id,
                    mapping.FIELD_EVIDENCE_ID: span.evidence_id,
                    mapping.FIELD_DOCUMENT_ID: span.document_id,
                    mapping.FIELD_TITLE: span.title,
                    mapping.FIELD_TEXT: span.text,
                    mapping.FIELD_PAGE: span.page_number,
                    mapping.FIELD_SOURCE_TYPE: span.source_type,
                    mapping.FIELD_EMBEDDING_MODEL: model,
                    mapping.FIELD_VECTOR: list(vector),
                }
            )

    if actions:
        response = client.bulk(body=actions, refresh=True)
        if response.get("errors"):
            failed = [
                item["index"]["error"]
                for item in response.get("items", [])
                if item.get("index", {}).get("error")
            ]
            raise ValueError(f"bulk index reported {len(failed)} failure(s): {failed[:2]}")

    _LOG.info("indexed", extra={"case_id": case_id, "documents": len(spans), "index": index})
    return IndexResult(
        index=index,
        documents=len(spans),
        embedding_model=model,
        dimensions=dimensions,
        total_tokens=tokens,
    )
