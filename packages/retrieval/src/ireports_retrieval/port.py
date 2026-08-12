"""The retrieval port — how a specialist gets evidence, and the only way it may.

Before this existed, specialists were handed every span in the case. That works up to a point and
the point is small: the demo case was 430 tokens. A real case is ~35,000, and pasting all of it
into five parallel prompts costs 175,000 input tokens per run to make five specialists read four
chapters each that have nothing to do with their criterion.

**Retrieval is what makes a sub-agent a sub-agent** (ADR-021). A specialist that receives a fixture
demonstrates a fan-out; a specialist that asks its own question of the record is the architecture.

Two rules the port enforces so callers cannot get them wrong:

1. **The case filter is mandatory and structural.** It is not a parameter a caller passes; it is
   built from the `case_id` on every query. Retrieval that can cross case boundaries is a
   data-segregation failure in a system holding personnel-security material.
2. **K is bounded.** An unbounded retrieval is an unbounded prompt, which is an unbounded bill.

Nothing here names an index field. Those live in `mapping.py`, one file, because the AWS
collection's real schema is unconfirmed (Q-02).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ireports_gateway import EmbeddingGateway

from . import mapping

_LOG = logging.getLogger(__name__)

MAX_K = 20
"""Hard ceiling on hits per query, whatever a caller asks for.

Not a tuning knob. Twenty spans of investigative record is already a large prompt, and the reason
to bound it is the same reason budgets exist: the cost of a mistake here is paid per specialist,
per run, in tokens."""


class RetrievalError(RuntimeError):
    """Retrieval failed. Distinct from "retrieved nothing", which is an answer."""


@dataclass(frozen=True)
class RetrievedSpan:
    """One span the index returned, with its provenance.

    `score` is carried but deliberately not interpreted anywhere: it is a relevance signal from an
    untuned hybrid query over a small corpus, and treating it as a confidence would be inventing a
    number. It is here so a human debugging retrieval can see the ordering.
    """

    evidence_id: str
    document_id: str
    title: str
    text: str
    page_number: int
    source_type: str
    score: float


@runtime_checkable
class Retriever(Protocol):
    """What a specialist depends on. Never an OpenSearch client."""

    def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]: ...


class OpenSearchRetriever:
    """Hybrid vector + lexical retrieval against a local OpenSearch or an AWS collection.

    The client is constructed by the caller so this class does not own connection policy — AWS
    needs SigV4 request signing and a local cluster does not, and burying that choice here would
    make the AWS path a code change rather than a wiring one.
    """

    def __init__(
        self,
        client: Any,
        embedder: EmbeddingGateway,
        *,
        verify: bool = True,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._verify = verify
        self._verified: set[str] = set()

    def _check_index(self, index: str) -> None:
        """Assert the index looks like what `mapping.py` expects, once per index per process.

        Skipping this would be tempting — it is a round trip — and wrong, because the failure it
        catches returns *zero hits* rather than an error. A specialist would then report that the
        record contains nothing relevant to its criterion, which is a sentence that reads like
        analysis and is actually a schema mismatch.
        """
        if not self._verify or index in self._verified:
            return
        problems = mapping.verify_mapping(self._client.indices.get_mapping(index=index), index)
        if problems:
            raise RetrievalError(
                "the index does not match what this code expects, and a mismatch returns zero "
                "hits rather than an error:\n  " + "\n  ".join(problems)
            )
        self._verified.add(index)

    def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]:
        bounded = max(1, min(k, MAX_K))
        index = mapping.index_for(case_id)
        self._check_index(index)

        embedded = self._embedder.embed((query,))
        if not embedded.vectors:
            raise RetrievalError("the embedder returned no vector for the query")

        body = mapping.hybrid_query(
            case_id=case_id,
            text=query,
            vector=list(embedded.vectors[0]),
            k=bounded,
        )
        try:
            response = self._client.search(index=index, body=body)
        except Exception as exc:  # opensearch-py raises a family of transport errors
            raise RetrievalError(f"search failed against {index}: {type(exc).__name__}") from exc

        hits = response.get("hits", {}).get("hits", [])
        # Identifiers and counts only — never the query text or the retrieved content.
        _LOG.debug(
            "retrieved", extra={"case_id": case_id, "index": index, "hits": len(hits), "k": bounded}
        )

        return tuple(
            RetrievedSpan(
                evidence_id=hit["_source"][mapping.FIELD_EVIDENCE_ID],
                document_id=hit["_source"].get(mapping.FIELD_DOCUMENT_ID, ""),
                title=hit["_source"].get(mapping.FIELD_TITLE, ""),
                text=hit["_source"][mapping.FIELD_TEXT],
                page_number=int(hit["_source"].get(mapping.FIELD_PAGE, 1)),
                source_type=hit["_source"].get(mapping.FIELD_SOURCE_TYPE, ""),
                score=float(hit.get("_score", 0.0)),
            )
            for hit in hits
        )


class InMemoryRetriever:
    """Every span, ignoring the query. For offline tests only.

    **This is not a retriever and must never stand in for one in a test about retrieval.** It
    returns the whole case, which is precisely the behaviour retrieval was built to replace, so a
    test that passes against it has demonstrated nothing about relevance. It exists so that tests
    about *orchestration* do not need a running OpenSearch.
    """

    def __init__(self, spans: tuple[RetrievedSpan, ...]) -> None:
        self._spans = spans

    def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]:
        return self._spans[: max(1, min(k, MAX_K))]
