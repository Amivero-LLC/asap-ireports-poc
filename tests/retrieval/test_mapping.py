"""The mapping module is where a schema mismatch is caught, so it gets tested hardest.

Every one of these is a pure function over a dict — no cluster, no network, safe in CI. The
integration half lives in `test_opensearch.py` and skips without a running cluster.
"""

from __future__ import annotations

from ireports_retrieval import mapping


def test_the_case_filter_is_not_optional() -> None:
    """Retrieval that can cross case boundaries is a data-segregation failure.

    Asserted on the query body rather than on the port's signature, because the guarantee has to
    hold for *every* query this module can build — a caller cannot opt out, because there is no
    parameter to opt out with.
    """
    body = mapping.hybrid_query(case_id="CASE-TEST-001", text="q", vector=[0.0] * 4, k=5)
    filters = body["query"]["bool"]["filter"]
    assert {"term": {mapping.FIELD_CASE_ID: "CASE-TEST-001"}} in filters


def test_the_query_is_both_vector_and_lexical() -> None:
    """ADR-021: vector *and* lexical. Either alone is a different system."""
    body = mapping.hybrid_query(case_id="C-1", text="foreign contacts", vector=[0.1] * 4, k=3)
    clauses = body["query"]["bool"]["should"]
    assert any("knn" in c for c in clauses), "no vector clause"
    assert any("multi_match" in c for c in clauses), "no lexical clause"


def test_the_vector_is_not_echoed_back() -> None:
    body = mapping.hybrid_query(case_id="C-1", text="q", vector=[0.0] * 4, k=1)
    assert mapping.FIELD_VECTOR in body["_source"]["excludes"]


def test_index_definition_enables_knn_at_the_declared_width() -> None:
    body = mapping.index_body()
    assert body["settings"]["index"]["knn"] is True
    vector = body["mappings"]["properties"][mapping.FIELD_VECTOR]
    assert vector["dimension"] == mapping.VECTOR_DIMENSIONS
    # Lucene is what AWS OpenSearch Serverless supports for filtered k-NN. A local index on a
    # different engine would work here and behave differently there.
    assert vector["method"]["engine"] == "lucene"


def test_verify_mapping_catches_the_failure_that_returns_zero_hits() -> None:
    """A missing field does not error — it matches nothing, which reads as 'nothing relevant'."""
    live = {
        "some-index": {"mappings": {"properties": {mapping.FIELD_CASE_ID: {"type": "keyword"}}}}
    }
    problems = mapping.verify_mapping(live, "some-index")
    assert any(mapping.FIELD_TEXT in p for p in problems)
    assert any(mapping.FIELD_VECTOR in p for p in problems)


def test_verify_mapping_catches_a_dimension_mismatch() -> None:
    live = {
        "i": {
            "mappings": {
                "properties": {
                    mapping.FIELD_CASE_ID: {"type": "keyword"},
                    mapping.FIELD_EVIDENCE_ID: {"type": "keyword"},
                    mapping.FIELD_TEXT: {"type": "text"},
                    mapping.FIELD_VECTOR: {"type": "knn_vector", "dimension": 384},
                }
            }
        }
    }
    problems = mapping.verify_mapping(live, "i")
    assert len(problems) == 1
    assert "384" in problems[0] and str(mapping.VECTOR_DIMENSIONS) in problems[0]


def test_a_healthy_index_reports_no_problems() -> None:
    live = {"i": {"mappings": mapping.index_body()["mappings"]}}
    assert mapping.verify_mapping(live, "i") == []


def test_no_field_name_is_written_outside_this_module() -> None:
    """ADR-007's containment rule, enforced rather than described.

    Adapting to the real AWS schema (Q-02) is a one-file change only while it is true that no
    other module names a field. A stray `"case_id"` in a query somewhere else silently breaks
    that promise, and the promise is the entire reason proceeding without the real schema is
    defensible.
    """
    import pathlib

    package = pathlib.Path(mapping.__file__).parent
    literals = {
        mapping.FIELD_VECTOR,
        mapping.FIELD_EMBEDDING_MODEL,
        mapping.FIELD_SOURCE_TYPE,
    }
    for path in package.glob("*.py"):
        if path.name == "mapping.py":
            continue
        source = path.read_text()
        for literal in literals:
            assert f'"{literal}"' not in source, (
                f"{path.name} hard-codes the index field {literal!r}. Field names live in "
                "mapping.py so adapting to the real AWS collection stays a one-file change."
            )
