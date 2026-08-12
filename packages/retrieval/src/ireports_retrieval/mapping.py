"""**PROVISIONAL — every field name in this file is a guess (Q-02).**

The AWS vector collection this system consumes in production is populated and owned by the
ingestion pipeline (ADR-007). **We have never seen its index mappings.** Field names, the vector
field's dimensions and engine, the filter shape, and whether case data and policy content share
one collection or sit in two — all unconfirmed.

ADR-007's containment rule is what makes proceeding defensible: **every field name, filter, and
facet mapping lives here, in one module, so adapting to the real schema is a one-file change.**
Nothing outside this module may name an index field as a string literal. If you find yourself
writing `"case_id"` in a query somewhere else, that is the bug this file exists to prevent.

**How this goes wrong, and it is not with an exception.** A field-name mismatch against a real
collection does not error — OpenSearch matches nothing, the query returns zero hits, and the
specialist reports that the record contains nothing relevant. Silent under-analysis, again. So
`verify_mapping()` exists to assert the index we query looks like the index we think we are
querying, and the retrieval port calls it rather than trusting.

When the ingestion team supplies real mappings: change the constants here, run the contract tests,
and delete this warning.
"""

from __future__ import annotations

from typing import Any, Final

INDEX_PREFIX: Final = "ireports-case"
"""One index per case.

A guess, and a consequential one. The alternative — a single index with a `case_id` filter — is
what an AWS Serverless collection more likely looks like, since collections are provisioned units
rather than per-case artifacts. Per-case indices are used locally because they make the mandatory
case filter *structural* (you cannot accidentally query across cases if the case is the index),
and because dropping one case's data is a delete rather than a query.

**If AWS turns out to be one shared collection, `index_for()` returns a constant and
`CASE_FILTER` becomes load-bearing instead.** Both paths are already written; only one is
exercised. That is the whole point of keeping this in one file.
"""

# --- field names -----------------------------------------------------------

FIELD_CASE_ID: Final = "case_id"
FIELD_EVIDENCE_ID: Final = "evidence_id"
FIELD_DOCUMENT_ID: Final = "document_id"
FIELD_TITLE: Final = "title"
FIELD_TEXT: Final = "text"
FIELD_SOURCE_TYPE: Final = "source_type"
FIELD_PAGE: Final = "page_number"
FIELD_VECTOR: Final = "text_vector"
FIELD_EMBEDDING_MODEL: Final = "embedding_model"
"""Recorded per document, deliberately.

Q-03: if the model that embeds queries differs from the model that populated the collection,
nothing fails — retrieval quietly gets worse and every downstream number becomes meaningless.
Storing the model per document is what turns that from undetectable into checkable, and
`verify_mapping()` checks it.
"""

VECTOR_DIMENSIONS: Final = 1024
"""`amazon.titan-embed-text-v2:0`. Must equal the query embedder's output width or the k-NN query
is rejected — one of the few failures in this file that *is* loud."""


def index_for(case_id: str) -> str:
    """The index holding one case's evidence."""
    return f"{INDEX_PREFIX}-{case_id.lower()}"


def index_body() -> dict[str, Any]:
    """The index definition: k-NN vector field plus the lexical fields.

    `space_type: cosinesimil` matches how Titan vectors are normally compared, and `engine: lucene`
    is chosen over `nmslib`/`faiss` because it is the engine AWS OpenSearch Serverless supports for
    filtered k-NN — a local index on a different engine would work here and behave differently
    there, which is the exact class of surprise this whole module exists to avoid.
    """
    return {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                # Zero replicas: a single-node cluster cannot allocate them, and a cluster stuck
                # yellow forever makes the health check meaningless.
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                FIELD_CASE_ID: {"type": "keyword"},
                FIELD_EVIDENCE_ID: {"type": "keyword"},
                FIELD_DOCUMENT_ID: {"type": "keyword"},
                FIELD_SOURCE_TYPE: {"type": "keyword"},
                FIELD_EMBEDDING_MODEL: {"type": "keyword"},
                FIELD_PAGE: {"type": "integer"},
                FIELD_TITLE: {"type": "text"},
                FIELD_TEXT: {"type": "text"},
                FIELD_VECTOR: {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIMENSIONS,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                    },
                },
            }
        },
    }


def hybrid_query(
    *,
    case_id: str,
    text: str,
    vector: list[float],
    k: int,
    vector_weight: float = 1.0,
    lexical_weight: float = 1.0,
) -> dict[str, Any]:
    """Vector + lexical in one query, with the case filter mandatory (ADR-021).

    **The case filter is not optional and is not a parameter.** Retrieval that can cross case
    boundaries is a data-segregation failure in a system holding personnel-security material, so
    the filter is constructed here every time rather than passed in by a caller who might forget.

    A `bool.should` over a k-NN clause and a `match` clause, rather than OpenSearch's
    `hybrid` pipeline query: the pipeline needs a search pipeline configured on the cluster, which
    is a deployment-time artifact we would have to create on AWS too and cannot verify (Q-02).
    Score combination is therefore additive and the weights are crude — good enough to show both
    signals contributing, and **not** a tuned relevance function. Tuning against a corpus this
    small would be fitting noise.
    """
    return {
        "size": k,
        "query": {
            "bool": {
                "filter": [{"term": {FIELD_CASE_ID: case_id}}],
                "should": [
                    {
                        "knn": {
                            FIELD_VECTOR: {
                                "vector": vector,
                                "k": k,
                                "boost": vector_weight,
                            }
                        }
                    },
                    {
                        "multi_match": {
                            "query": text,
                            "fields": [f"{FIELD_TITLE}^2", FIELD_TEXT],
                            "boost": lexical_weight,
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
        # The vector is large and echoing it back in every hit wastes bandwidth and makes any
        # logged response unreadable.
        "_source": {"excludes": [FIELD_VECTOR]},
    }


def verify_mapping(mapping: dict[str, Any], index: str) -> list[str]:
    """Check a live index looks like what this module expects. Returns problems, empty if fine.

    Exists because the failure it catches is silent: query a field that is not there and
    OpenSearch returns zero hits rather than an error, and zero hits is indistinguishable from
    "this case contains nothing relevant."
    """
    problems: list[str] = []
    properties = mapping.get(index, {}).get("mappings", {}).get("properties", {}) if mapping else {}
    if not properties:
        return [f"{index}: no mappings found — is this the right index?"]

    for field in (FIELD_CASE_ID, FIELD_EVIDENCE_ID, FIELD_TEXT, FIELD_VECTOR):
        if field not in properties:
            problems.append(
                f"{index}: expected field {field!r}, which is absent. Queries against it will "
                "return zero hits rather than fail — see Q-02."
            )

    vector = properties.get(FIELD_VECTOR, {})
    if vector and vector.get("dimension") != VECTOR_DIMENSIONS:
        problems.append(
            f"{index}: vector field is {vector.get('dimension')}-dimensional and the query "
            f"embedder produces {VECTOR_DIMENSIONS}. k-NN will reject every query."
        )
    return problems
