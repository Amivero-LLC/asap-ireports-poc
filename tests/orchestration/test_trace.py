"""Proof that the fan-out fans out and the branch branches.

**Every other orchestration test in this suite passes on a fully serial implementation.** They
assert *width* (five outcomes for five criteria) and a *ceiling* (never more than three at once)
and never once assert that two specialists overlapped in time. That is a real gap in a document
whose central claim is that the orchestration is real, and this file closes it.

The evidence is the run's own trace — node ids and offsets, recorded by the orchestrator — so the
same numbers a test asserts on are the numbers `run_case.py` prints and the Lambda handler returns.
A reader of the handoff can check the claim rather than trust the test name.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import sleep
from typing import Any

import pytest
from ireports_domain import CaseManifest, DecisionDomain
from ireports_gateway import StubGateway
from ireports_gateway.port import ModelRequest
from ireports_orchestration import (
    CATALOG,
    MAX_PARALLEL,
    ORCHESTRATORS,
    EvidenceSpan,
    LoadedCase,
    NodeSpan,
    RunTrace,
    criteria_for,
    is_subcall,
    peak_concurrency,
    subcall_node_id,
    timeline,
)
from ireports_retrieval import InMemoryRetriever, RetrievedSpan

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASE_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "cases" / "AMI-SYN-FIN-001"
BOTH = ["hand-rolled"]
"""One implementation since ADR-029. Kept as a list so a team adding their own behind
`Orchestrator` inherits this suite by adding one name."""
RUN_ID = "run_trace_0001"

_FINDING = {
    "title": "Foreign family contact reported in the questionnaire",
    "observation": "The record shows contact with a parent abroad [ev_001].",
    "policy_relevance": "Contact with foreign nationals may be relevant here.",
    "recommended_officer_action": "Review the reported contact.",
    "supporting_evidence": ["ev_001"],
    "mitigating_evidence": [],
    "classification": "potential_issue",
    "evidence_confidence": "moderate",
    "analysis_confidence": "moderate",
}


@pytest.fixture
def case() -> LoadedCase:
    manifest = CaseManifest.model_validate(json.loads((CASE_DIR / "case.json").read_text()))
    raw = json.loads((CASE_DIR / "evidence.json").read_text())
    return LoadedCase(
        manifest=manifest,
        spans=tuple(
            EvidenceSpan(
                evidence_id=s["evidence_id"],
                document_id=s["document_id"],
                page_number=int(s["page_number"]),
                source_reliability=s["source_reliability"],
                text=s["text"],
                title=s.get("title", ""),
                source_type=s.get("source_type", "case_document"),
            )
            for s in raw["spans"]
        ),
        root=CASE_DIR,
    )


@pytest.fixture
def retriever(case: LoadedCase) -> InMemoryRetriever:
    return InMemoryRetriever(
        tuple(
            RetrievedSpan(
                evidence_id=s.evidence_id,
                document_id=s.document_id,
                title=s.title,
                text=s.text,
                page_number=s.page_number,
                source_type=s.source_type,
                score=1.0,
            )
            for s in case.spans
        )
    )


def _slow(findings: list[dict[str, Any]], delay: float = 0.08) -> StubGateway:
    """A stub slow enough for overlap to be measurable.

    **The delay is the test.** Against an instant stub every span is a point, nothing overlaps
    anything, and a genuinely parallel fan-out is indistinguishable from a serial one — the
    measurement would report 1 and the code would be fine. Concurrency can only be observed in work
    that takes time.
    """

    class _Slow(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            if not is_subcall(request.node_id):  # analysis and synthesis, not the triage sub-call
                sleep(delay)
            return super().complete(request)

    return _Slow(
        responses={
            "synthesis": json.dumps({"contradictions": [], "information_gaps": []}),
            **{
                subcall_node_id(c.node_id, "sufficiency"): json.dumps({"sufficient": True})
                for c in CATALOG
            },
        },
        default=json.dumps({"findings": findings}),
    )


# ---------------------------------------------------------------------------
# The fan-out is concurrent, not a loop
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", BOTH)
def test_specialists_actually_run_at_the_same_time(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**The assertion the whole suite was missing.**

    `test_both_orchestrators_fan_out_to_the_width_the_case_asks_for` proves five outcomes came back
    for five criteria, which a `for` loop also achieves. `test_the_fan_out_never_runs_wider_than_
    max_parallel` proves no more than three ran at once, which a `for` loop also achieves. Neither
    of them, nor anything else in this repository before this file, distinguished a fan-out from a
    loop.
    """
    result = ORCHESTRATORS[name].run(case, _slow([_FINDING]), retriever, RUN_ID)

    assert len(result.criteria) > 1, "the case cannot exercise a fan-out"
    assert result.peak_concurrency > 1, (
        f"{name} ran {result.peak_concurrency} node(s) at a time — the fan-out is a loop"
    )


@pytest.mark.parametrize("name", BOTH)
def test_the_fan_out_saturates_the_bound_rather_than_the_width(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """Concurrency is `MAX_PARALLEL`, not the number of criteria — the bound doing its job.

    Both halves matter. Reaching the bound shows the pool is genuinely saturated rather than
    incidentally overlapping two nodes; not exceeding it shows the ceiling holds. On the LangGraph
    path the ceiling is `max_concurrency` on the config, which was absent until 2026-08-18 and let
    `Send` dispatch all five at once.
    """
    result = ORCHESTRATORS[name].run(case, _slow([_FINDING]), retriever, RUN_ID)

    assert len(result.criteria) > MAX_PARALLEL, "the case cannot exercise the bound"
    assert result.peak_concurrency == MAX_PARALLEL, f"{name}: {result.peak_concurrency}"


@pytest.mark.parametrize("name", BOTH)
def test_the_two_paths_fan_out_to_the_same_shape(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """Same criteria, same width, same peak — the comparison ADR-024 rests on is like-for-like.

    A trace is the only place this is checkable. Two runs producing the same findings could still
    have reached them one node at a time versus three at a time, and every existing assertion about
    "identical output" would hold.
    """
    result = ORCHESTRATORS[name].run(case, _slow([_FINDING]), retriever, RUN_ID)

    analysed = {s.node_id for s in result.trace if s.node_id != "synthesis"}
    assert analysed == {c.node_id for c in criteria_for(case.manifest)}
    assert result.peak_concurrency == MAX_PARALLEL


@pytest.mark.parametrize("name", BOTH)
def test_a_narrower_case_fans_out_narrower(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**Width is runtime data**, and the trace is where that stops being a claim about
    `criteria_for` and becomes one about what actually ran."""
    narrowed = LoadedCase(
        manifest=case.manifest.model_copy(
            update={"requested_analyses": (DecisionDomain.SUITABILITY,)}
        ),
        spans=case.spans,
        root=case.root,
    )
    expected = criteria_for(narrowed.manifest)
    assert len(expected) < len(CATALOG), "the narrowing did not narrow anything"

    result = ORCHESTRATORS[name].run(narrowed, _slow([_FINDING]), retriever, RUN_ID)

    assert {s.node_id for s in result.trace if s.node_id != "synthesis"} == {
        c.node_id for c in expected
    }


# ---------------------------------------------------------------------------
# The branch is taken, and the barrier holds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", BOTH)
def test_synthesis_starts_only_after_every_specialist_has_finished(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**The fan-in barrier, as data rather than as an inference from a call count.**

    `test_synthesis_runs_once_not_once_per_specialist` proves the second stage was not invoked five
    times. It does not prove it waited: a synthesis that started alongside the third specialist and
    reasoned over two findings would satisfy it exactly. The timeline is what settles that.
    """
    result = ORCHESTRATORS[name].run(case, _slow([_FINDING]), retriever, RUN_ID)

    spans = {s.node_id: s for s in result.trace}
    assert "synthesis" in spans, f"{name} did not run the second stage at all"
    specialists = [s for s in result.trace if s.node_id != "synthesis"]
    assert specialists

    last_end = max(s.ended for s in specialists)
    assert spans["synthesis"].started >= last_end, (
        f"{name}: synthesis started at {spans['synthesis'].started:.3f}s, before the last "
        f"specialist finished at {last_end:.3f}s — it reasoned over a partial fan-out"
    )
    assert not any(spans["synthesis"].overlaps(s) for s in specialists)


@pytest.mark.parametrize("name", BOTH)
def test_the_same_graph_takes_both_branches(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**This is what "branching" means, and nothing asserted it before.**

    One orchestrator, two runs, two different routes — proven by the presence and absence of a
    synthesis span on the timeline. `result.synthesis is None` on its own is equally consistent
    with a router that chose `END` and with a second stage that was never wired up at all; only
    seeing the *other* run take it distinguishes them.
    """
    took_it = ORCHESTRATORS[name].run(case, _slow([_FINDING]), retriever, RUN_ID)
    # Nothing to reason across — `should_synthesize` requires two findings.
    skipped_it = ORCHESTRATORS[name].run(case, _slow([]), retriever, RUN_ID)

    assert "synthesis" in {s.node_id for s in took_it.trace}
    assert took_it.synthesis is not None

    assert "synthesis" not in {s.node_id for s in skipped_it.trace}, (
        f"{name} ran the second stage on a run with nothing to reason across"
    )
    assert skipped_it.synthesis is None
    # Both runs analysed every criterion, so the difference really is the branch and not the width.
    assert len(took_it.outcomes) == len(skipped_it.outcomes) == len(took_it.criteria)


# ---------------------------------------------------------------------------
# The measurement's own guards
# ---------------------------------------------------------------------------


def test_peak_concurrency_counts_overlap_not_adjacency() -> None:
    """Back-to-back nodes are not concurrent, and an off-by-one here would fake the headline.

    Every proof in this file rests on this function. If touching endpoints counted, a perfectly
    serial run would report a peak of 2 and `test_specialists_actually_run_at_the_same_time` would
    pass on the implementation it exists to rule out.
    """
    serial = (
        NodeSpan("a", 0.0, 1.0),
        NodeSpan("b", 1.0, 2.0),
        NodeSpan("c", 2.0, 3.0),
    )
    assert peak_concurrency(serial) == 1

    overlapping = (NodeSpan("a", 0.0, 1.0), NodeSpan("b", 0.5, 1.5), NodeSpan("c", 0.9, 2.0))
    assert peak_concurrency(overlapping) == 3

    assert peak_concurrency(()) == 0
    assert not NodeSpan("a", 0.0, 1.0).overlaps(NodeSpan("b", 1.0, 2.0))
    assert NodeSpan("a", 0.0, 1.0).overlaps(NodeSpan("b", 0.99, 2.0))


def test_a_node_that_raises_still_leaves_a_span() -> None:
    """A crash is when the timeline is most worth having.

    Recording only successful nodes would draw a failed fan-out as one that never started, which is
    the opposite of what someone debugging it needs to see.
    """
    trace = RunTrace()
    with pytest.raises(RuntimeError), trace.span("exploding_specialist"):
        raise RuntimeError("boom")

    assert [s.node_id for s in trace.spans()] == ["exploding_specialist"]


def test_the_trace_carries_identifiers_and_timings_and_nothing_else() -> None:
    """`CLAUDE.md`: raw case text never reaches logs or traces.

    Asserted on the type rather than on an instance, so a field that could carry evidence text
    fails here the moment it is added rather than the first time a real case flows through it.
    """
    assert {f.name for f in NodeSpan.__dataclass_fields__.values()} == {
        "node_id",
        "started",
        "ended",
    }


def test_the_timeline_renders_every_span_visibly() -> None:
    """A node too fast to measure must still appear as a row.

    An empty bar reads as a node that did not run, which for a fan-out diagram is precisely the
    wrong lie to tell.
    """
    rows = timeline((NodeSpan("slow", 0.0, 1.0), NodeSpan("instant", 0.5, 0.5)))

    assert len(rows) == 2
    assert all("#" in row for row in rows)
    assert any("instant" in row for row in rows)
