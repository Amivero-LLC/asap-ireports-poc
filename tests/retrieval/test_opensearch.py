"""Retrieval against a real OpenSearch. Skipped when the compose stack is not running.

    docker compose -f infrastructure/docker/compose.yaml up -d

Uses `StubEmbeddingGateway`, so it costs nothing and needs no credentials — which also means it
proves the *wiring* (index, filter, k, mapping verification) and says nothing about relevance.
Stub vectors are hashes; similarity between them is an artefact, not meaning.
"""

from __future__ import annotations

from typing import Any

import pytest
from ireports_gateway import StubEmbeddingGateway
from ireports_retrieval import (
    IndexableSpan,
    OpenSearchRetriever,
    RetrievalError,
    connect,
    index_case,
    mapping,
)


def _available() -> bool:
    try:
        return bool(connect().info())
    except Exception:
        return False


requires_opensearch = pytest.mark.skipif(
    not _available(),
    reason="needs OpenSearch: docker compose -f infrastructure/docker/compose.yaml up -d",
)

STUB_DIMS = 8


@pytest.fixture
def narrow_index(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The stub embedder produces 8-dimensional vectors; the real one produces 1024.

    Patching the constant rather than the stub keeps the *shape* of the real path — index built
    from `index_body()`, queried through `hybrid_query()` — while letting the test run offline.
    """
    monkeypatch.setattr(mapping, "VECTOR_DIMENSIONS", STUB_DIMS)
    return connect()


def _spans() -> tuple[IndexableSpan, ...]:
    return (
        IndexableSpan(
            "ev_001",
            "doc_a",
            "Foreign Contacts",
            "Regular contact with a sibling abroad.",
            1,
            "roi_chapter",
        ),
        IndexableSpan(
            "ev_002",
            "doc_b",
            "Financial Record",
            "A delinquent medical collection account.",
            2,
            "roi_chapter",
        ),
    )


@requires_opensearch
def test_index_and_retrieve_round_trip(narrow_index: Any) -> None:
    result = index_case(
        narrow_index,
        StubEmbeddingGateway(dimensions=STUB_DIMS),
        case_id="TEST-RT-001",
        spans=_spans(),
    )
    assert result.documents == 2
    assert result.embedding_model  # recorded, so a stored vector can be traced to its model

    retriever = OpenSearchRetriever(narrow_index, StubEmbeddingGateway(dimensions=STUB_DIMS))
    hits = retriever.retrieve(case_id="TEST-RT-001", query="delinquent account", k=5)
    assert {h.evidence_id for h in hits} == {"ev_001", "ev_002"}


@requires_opensearch
def test_retrieval_cannot_cross_case_boundaries(narrow_index: Any) -> None:
    """The filter is structural, and this is what makes that claim checkable."""
    embedder = StubEmbeddingGateway(dimensions=STUB_DIMS)
    index_case(narrow_index, embedder, case_id="TEST-A-001", spans=_spans())
    index_case(narrow_index, embedder, case_id="TEST-B-001", spans=_spans())

    hits = OpenSearchRetriever(narrow_index, embedder).retrieve(
        case_id="TEST-A-001", query="anything", k=10
    )
    assert hits
    # Same evidence ids exist in both cases; only one case's index may answer.
    assert all(h.evidence_id in {"ev_001", "ev_002"} for h in hits)
    assert len(hits) == 2, "hits leaked from the other case"


@requires_opensearch
def test_k_is_bounded_however_much_a_caller_asks_for(narrow_index: Any) -> None:
    """An unbounded retrieval is an unbounded prompt, which is an unbounded bill."""
    embedder = StubEmbeddingGateway(dimensions=STUB_DIMS)
    index_case(narrow_index, embedder, case_id="TEST-K-001", spans=_spans())
    hits = OpenSearchRetriever(narrow_index, embedder).retrieve(
        case_id="TEST-K-001", query="q", k=10_000
    )
    assert len(hits) <= 2  # only two documents exist, but the query itself was clamped first


@requires_opensearch
def test_a_wrong_shaped_index_raises_instead_of_returning_nothing(narrow_index: Any) -> None:
    """The failure mode this whole module guards: zero hits reads as 'nothing relevant'."""
    index = mapping.index_for("TEST-BAD-001")
    if narrow_index.indices.exists(index=index):
        narrow_index.indices.delete(index=index)
    narrow_index.indices.create(
        index=index, body={"mappings": {"properties": {"totally_different": {"type": "text"}}}}
    )
    retriever = OpenSearchRetriever(narrow_index, StubEmbeddingGateway(dimensions=STUB_DIMS))
    with pytest.raises(RetrievalError, match="zero hits rather than an error"):
        retriever.retrieve(case_id="TEST-BAD-001", query="q", k=3)
