"""The multi-step specialist: retrieve, ask whether that was enough, retrieve again.

Roadmap item 6, and it folds in ORCH-03's two remaining clauses — a no-progress detector and
cancellation — because both are meaningless in a node that cannot loop.

**Everything here is offline and free.** The retriever is scripted per query, so a refinement can
be made to surface new evidence, the same evidence, or nothing, deterministically. What is *not*
tested here is whether a real model asks useful follow-up questions; that needs a live run, and
`docs/ROADMAP.md` records what one showed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ireports_domain import Budgets, CaseManifest, ModelAlias
from ireports_gateway import ModelRefusalError, StubGateway
from ireports_gateway.port import GatewayError, ModelRequest
from ireports_orchestration import (
    CATALOG,
    ORCHESTRATORS,
    Checkpointing,
    Criterion,
    EvidenceSpan,
    InMemoryCheckpointStore,
    LoadedCase,
    SpecialistStatus,
)
from ireports_orchestration.budget import BudgetLedger
from ireports_orchestration.gather import (
    CancellationToken,
    GatherStop,
    gather_evidence,
)
from ireports_retrieval import InMemoryRetriever, RetrievalError, RetrievedSpan

CRITERION: Criterion = CATALOG[0]
CASE_ID = "AMI-SYN-FIN-001"


def _budgets(**overrides: Any) -> Budgets:
    base: dict[str, Any] = {
        "max_input_tokens": 400_000,
        "max_output_tokens": 200_000,
        "max_wall_clock_seconds": 780,
    }
    base.update(overrides)
    return Budgets(**base)


def _span(evidence_id: str) -> RetrievedSpan:
    return RetrievedSpan(
        evidence_id=evidence_id,
        document_id="doc_001",
        title=f"Span {evidence_id}",
        text=f"The record for {evidence_id} says something about the subject's circumstances.",
        page_number=1,
        source_type="case_document",
        score=1.0,
    )


class _ScriptedRetriever:
    """Different spans for different queries — which `InMemoryRetriever` cannot express.

    `InMemoryRetriever` returns everything and ignores the query, which is right for tests about
    what a specialist does with evidence and useless for tests about *gathering* it: a loop whose
    second query returns the same thing as its first is indistinguishable from one that never ran.
    """

    def __init__(self, script: dict[str, list[str]], default: list[str] | None = None) -> None:
        self._script = script
        self._default = default if default is not None else []
        self.queries: list[str] = []

    def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]:
        self.queries.append(query)
        ids = self._script.get(query, self._default)
        return tuple(_span(i) for i in ids[:k])


def _assessor(*answers: dict[str, Any]) -> StubGateway:
    """A gateway whose sufficiency call answers `answers` in order, one per call."""

    class _Sequenced(StubGateway):
        def __init__(self) -> None:
            super().__init__(default=json.dumps({"findings": []}))
            self._remaining = list(answers)

        def complete(self, request: ModelRequest) -> Any:
            if request.node_id.endswith(":sufficiency"):
                self.calls.append(request)
                payload = self._remaining.pop(0) if self._remaining else {"sufficient": True}
                return StubGateway(default=json.dumps(payload)).complete(request)
            return super().complete(request)

    return _Sequenced()


def _gather(retriever: Any, gateway: Any, **kwargs: Any) -> Any:
    params: dict[str, Any] = {"k": 6, "budgets": _budgets()}
    params.update(kwargs)
    return gather_evidence(CRITERION, CASE_ID, retriever, gateway, **params)


# ---------------------------------------------------------------------------
# The loop itself
# ---------------------------------------------------------------------------


def test_a_refinement_surfaces_evidence_the_first_query_missed() -> None:
    """**The blind spot the loop exists to close.**

    The criterion asks about "contacts with foreign nationals"; the record says "my wife's parents
    live abroad". One hop, and one hop is exactly what a single query does not make. The assessor
    names what is missing, the second query goes after it, and the analysis sees the union.
    """
    retriever = _ScriptedRetriever(
        {CRITERION.question: ["ev_001", "ev_002"], "in-laws living abroad": ["ev_002", "ev_009"]}
    )
    gateway = _assessor({"sufficient": False, "next_query": "in-laws living abroad"})

    gathered = _gather(retriever, gateway)

    assert [s.evidence_id for s in gathered.spans] == ["ev_001", "ev_002", "ev_009"]
    assert len(gathered.steps) == 2
    assert gathered.steps[1].new_span_ids == ("ev_009",)
    assert gathered.assessments == 1
    assert retriever.queries == [CRITERION.question, "in-laws living abroad"]


def test_a_sufficient_record_is_not_searched_twice() -> None:
    """The assessor's whole job is to decline a second paid round when one is not warranted."""
    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]})
    gateway = _assessor({"sufficient": True})

    gathered = _gather(retriever, gateway)

    assert gathered.stopped is GatherStop.SUFFICIENT
    assert len(retriever.queries) == 1
    assert not gathered.rejected


def test_a_refinement_that_surfaces_nothing_new_stops_the_loop() -> None:
    """**ORCH-03's no-progress detector**, and the stop that fires most in practice.

    A refined query that returns only what is already held will keep returning it. On a corpus this
    size that is the common case, not the edge case — which is why the detector matters more than
    the step limit it sits inside.
    """
    retriever = _ScriptedRetriever(
        {CRITERION.question: ["ev_001", "ev_002"], "try again": ["ev_002", "ev_001"]}
    )
    gateway = _assessor({"sufficient": False, "next_query": "try again"})

    gathered = _gather(retriever, gateway, max_steps=4)

    assert gathered.stopped is GatherStop.NO_PROGRESS
    assert len(retriever.queries) == 2, "the loop kept querying after it stopped learning"
    assert any("surfaced no new evidence" in r for r in gathered.rejected)


def test_the_step_limit_is_reported_as_a_different_fact_from_sufficiency() -> None:
    """Running out of rounds is not the same as deciding there was enough.

    Both end the loop with a record to analyse, and only one of them is an answer. A run that
    conflated them would report "we looked and it was fine" when what happened was "we stopped".
    """
    retriever = _ScriptedRetriever(
        {CRITERION.question: ["ev_001"], "more": ["ev_002"]}, default=["ev_003"]
    )
    gateway = _assessor({"sufficient": False, "next_query": "more"})

    gathered = _gather(retriever, gateway, max_steps=2)

    assert gathered.stopped is GatherStop.STEP_LIMIT
    assert len(gathered.steps) == 2


# ---------------------------------------------------------------------------
# Cancellation — ORCH-03
# ---------------------------------------------------------------------------


def test_a_cancelled_token_stops_the_loop_before_it_spends_anything() -> None:
    """**ORCH-03's cancellation clause.** Checked before the first retrieval, not only between
    rounds — a run cancelled while a criterion was still queued must not start it."""
    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]})
    gateway = _assessor()
    token = CancellationToken()
    token.cancel("deadline approaching")

    gathered = _gather(retriever, gateway, cancel=token)

    assert gathered.stopped is GatherStop.CANCELLED
    assert not retriever.queries, "a cancelled run still ran a query"
    assert not gateway.calls
    assert any("deadline approaching" in r for r in gathered.rejected)


def test_cancelling_between_rounds_keeps_what_was_already_retrieved() -> None:
    """Cancellation is cooperative, so it stops the *next* round rather than discarding this one.

    Throwing away round one's spans would waste a retrieval that already happened and, worse, turn
    a cancelled criterion into one indistinguishable from a criterion with no evidence.
    """
    token = CancellationToken()

    class _CancelsAfterAssessing(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            if request.node_id.endswith(":sufficiency"):
                self.calls.append(request)
                token.cancel("cancelled mid-loop")
                return StubGateway(
                    default=json.dumps({"sufficient": False, "next_query": "more"})
                ).complete(request)
            return super().complete(request)

    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]}, default=["ev_002"])
    gathered = _gather(retriever, _CancelsAfterAssessing(default="{}"), max_steps=4, cancel=token)

    assert gathered.stopped is GatherStop.CANCELLED
    assert [s.evidence_id for s in gathered.spans] == ["ev_001"]
    assert len(retriever.queries) == 1


def test_a_token_keeps_the_first_reason_it_was_given() -> None:
    """Cancellation is idempotent and the first reason wins.

    Several nodes can race to cancel a run. If the last writer won, the reason a reader sees would
    depend on thread scheduling — which is the same class of bug as a breach measured on every read.
    """
    token = CancellationToken()
    token.cancel("lambda deadline")
    token.cancel("something else entirely")

    assert token.cancelled
    assert token.reason == "lambda deadline"


# ---------------------------------------------------------------------------
# Ceilings — the ones a loop can actually reach
# ---------------------------------------------------------------------------


def test_gathering_cannot_spend_the_budget_the_analysis_needs() -> None:
    """**`max_model_calls_per_node` finally means something.**

    It was previously described as enforced by the bounded retry in `analyze` — true, and thin: two
    calls against a limit of five. A loop can reach it, and a node that spends its whole allowance
    deciding what to read and then cannot afford to read it has failed in a way that looks like
    success. `calls_reserved` is what the caller still intends to spend.
    """
    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]}, default=["ev_002"])
    gateway = _assessor({"sufficient": False, "next_query": "more"})

    gathered = _gather(
        retriever,
        gateway,
        max_steps=5,
        budgets=_budgets(max_model_calls_per_node=3),
        calls_reserved=2,
    )

    assert gathered.stopped is GatherStop.CALL_BUDGET
    assert gathered.assessments == 0, "the loop assessed with no budget left to act on the answer"
    assert gathered.spans, "the criterion was left with no evidence at all"


def test_a_run_level_ceiling_stops_a_loop_already_in_flight() -> None:
    """Before item 6 a crossed ceiling stopped the run from *starting* criteria and could not
    touch work already running. A loop is the first thing long enough for that to matter."""
    now = [0.0]
    ledger = BudgetLedger(_budgets(max_wall_clock_seconds=10), clock=lambda: now[0])

    class _AdvancesTheClock(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            now[0] = 99.0
            return StubGateway(
                default=json.dumps({"sufficient": False, "next_query": "more"})
            ).complete(request)

    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]}, default=["ev_002"])
    gathered = _gather(retriever, _AdvancesTheClock(), max_steps=4, ledger=ledger)

    assert gathered.stopped is GatherStop.RUN_BUDGET
    assert len(retriever.queries) == 1


def test_gathering_stops_at_max_evidence_per_node() -> None:
    """A ceiling on evidence is a ceiling on prompt size, which is a ceiling on cost."""
    retriever = _ScriptedRetriever(
        {CRITERION.question: ["ev_001", "ev_002", "ev_003"]}, default=["ev_004"]
    )
    gateway = _assessor({"sufficient": False, "next_query": "more"})

    gathered = _gather(
        retriever, gateway, max_steps=4, k=3, budgets=_budgets(max_evidence_per_node=3)
    )

    assert len(gathered.spans) == 3
    assert any("max_evidence_per_node" in r for r in gathered.rejected)


# ---------------------------------------------------------------------------
# When the assessor is the thing that is broken
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "answer"),
    [
        ("unparseable", "not json at all"),
        ("off-schema", json.dumps({"verdict": "maybe"})),
        ("gap with no query", json.dumps({"sufficient": False, "next_query": "  "})),
    ],
)
def test_an_unusable_assessment_stops_the_loop_and_keeps_the_criterion(
    label: str, answer: str
) -> None:
    """**Stopping is the fail-safe direction, and it is chosen deliberately.**

    The alternative is to keep querying when the thing that decides whether to keep querying is
    broken — paid calls on the strength of an answer nobody got. The criterion is still analysed,
    on what round one retrieved, which is exactly what a single-step specialist would have had.
    """

    class _Unusable(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            if request.node_id.endswith(":sufficiency"):
                self.calls.append(request)
                return StubGateway(default=answer).complete(request)
            return super().complete(request)

    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]}, default=["ev_002"])
    gathered = _gather(retriever, _Unusable(default="{}"), max_steps=4)

    assert gathered.stopped is GatherStop.ASSESSOR_UNAVAILABLE, label
    assert [s.evidence_id for s in gathered.spans] == ["ev_001"]
    assert gathered.rejected, "the loop stopped for a reason nobody recorded"


@pytest.mark.parametrize("failure", [ModelRefusalError(category="sensitive"), GatewayError("down")])
def test_an_assessor_that_refuses_or_fails_does_not_take_the_criterion_down(
    failure: Exception,
) -> None:
    """ADR-021 §3, one layer further in. A triage call is the least important call in the run and
    must not be able to cost a criterion its analysis."""

    class _Broken(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            if request.node_id.endswith(":sufficiency"):
                raise failure
            return super().complete(request)

    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]}, default=["ev_002"])
    gathered = _gather(retriever, _Broken(default="{}"), max_steps=4)

    assert gathered.stopped is GatherStop.ASSESSOR_UNAVAILABLE
    assert gathered.spans


def test_a_first_round_retrieval_failure_is_reported_as_a_failure() -> None:
    """Nothing was ever retrieved, so the criterion cannot be analysed — which is not the same as
    a criterion whose record had nothing in it."""

    class _Broken:
        def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]:
            raise RetrievalError("index unavailable")

    gathered = _gather(_Broken(), _assessor())

    assert gathered.failed is not None
    assert not gathered.spans


def test_a_later_round_retrieval_failure_keeps_what_the_earlier_ones_found() -> None:
    """One round failing is survivable; discarding round one's evidence over it is not."""

    class _FailsOnRefinement:
        def __init__(self) -> None:
            self.calls = 0

        def retrieve(self, *, case_id: str, query: str, k: int) -> tuple[RetrievedSpan, ...]:
            self.calls += 1
            if self.calls > 1:
                raise RetrievalError("index unavailable")
            return (_span("ev_001"),)

    gathered = _gather(
        _FailsOnRefinement(),
        _assessor({"sufficient": False, "next_query": "more"}),
        max_steps=4,
    )

    assert gathered.failed is None
    assert [s.evidence_id for s in gathered.spans] == ["ev_001"]
    assert any("analysed on what was already retrieved" in r for r in gathered.rejected)


# ---------------------------------------------------------------------------
# What the loop costs, and where that shows up
# ---------------------------------------------------------------------------


def test_the_triage_call_is_on_the_fast_tier() -> None:
    """Paying thinking-tier rates to decide whether to pay thinking-tier rates is how a loop stops
    being worth having."""
    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]})
    gateway = _assessor({"sufficient": True})

    _gather(retriever, gateway, max_steps=2)

    assert [c.alias for c in gateway.calls] == [ModelAlias.FAST]


def test_the_loop_s_spend_reaches_the_criterion_and_the_run() -> None:
    """A stage whose cost is invisible per node is a stage nobody can decide is worth keeping.

    The ledger bounds the *run*; `GatheredEvidence` carries the same spend back to the criterion,
    and `analyze` folds it into the outcome's own token counts.
    """
    ledger = BudgetLedger(_budgets())
    retriever = _ScriptedRetriever({CRITERION.question: ["ev_001"]})
    gateway = _assessor({"sufficient": True})

    gathered = _gather(retriever, gateway, max_steps=2, ledger=ledger)

    assert gathered.input_tokens > 0
    assert ledger.consumption().input_tokens == gathered.input_tokens
    assert ledger.consumption().model_calls == 1


def test_a_cancelled_criterion_is_its_own_status_end_to_end() -> None:
    """`CANCELLED` reaches the outcome rather than being flattened into the nearest neighbour.

    A criterion the run was told to stop is not one that broke, not one that came back clean, and
    not one that ran out of budget. `RESUMABLE_STATUSES` excludes it for the same reason it
    excludes a budget skip: cancelled work is work still to do.
    """
    from ireports_orchestration.checkpoint import RESUMABLE_STATUSES

    assert SpecialistStatus.CANCELLED not in RESUMABLE_STATUSES
    assert SpecialistStatus.CANCELLED is not SpecialistStatus.SKIPPED_BUDGET


# ---------------------------------------------------------------------------
# Cancellation at the orchestrator, on both paths
# ---------------------------------------------------------------------------
#
# **The one place item 6 could have discriminated between the paths.** The loop itself is inside a
# node, so neither orchestrator can see it; `docs/ROADMAP.md` predicted before building that if
# anything separated them here it would be cancellation crossing the node boundary. These tests are
# where that is measured, and they are parameterised over both for exactly that reason.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASE_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "cases" / "AMI-SYN-FIN-001"
BOTH = ["hand-rolled", "langgraph"]


@pytest.fixture
def loaded_case() -> LoadedCase:
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
def whole_record(loaded_case: LoadedCase) -> InMemoryRetriever:
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
            for s in loaded_case.spans
        )
    )


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


def _run_gateway(token: CancellationToken, cancel_after: int) -> StubGateway:
    """Cancels the run partway through the fan-out, the way a deadline watchdog would."""

    class _Cancels(StubGateway):
        def __init__(self) -> None:
            super().__init__(
                responses={
                    "synthesis": json.dumps({"contradictions": [], "information_gaps": []}),
                    **{
                        f"{c.node_id}:sufficiency": json.dumps({"sufficient": True})
                        for c in CATALOG
                    },
                },
                default=json.dumps({"findings": [_FINDING]}),
            )
            self.analysed = 0

        def complete(self, request: ModelRequest) -> Any:
            if ":" not in request.node_id and request.node_id != "synthesis":
                self.analysed += 1
                if self.analysed > cancel_after:
                    token.cancel("lambda deadline approaching")
            return super().complete(request)

    return _Cancels()


@pytest.mark.parametrize("name", BOTH)
def test_a_cancelled_run_returns_what_it_has_and_says_what_it_did_not_do(
    loaded_case: LoadedCase, whole_record: InMemoryRetriever, name: str
) -> None:
    """**A cancelled run delivers, it does not vanish.**

    Same reasoning as a budget stop: `INCOMPLETE_DUE_TO_BUDGET` routes to packaging rather than
    failure, because a truncated analysis a reviewer can see is truncated is worth more than one
    that silently disappears. Every criterion is still accounted for, and the ones nobody reached
    say so.
    """
    token = CancellationToken()
    gateway = _run_gateway(token, cancel_after=1)

    result = ORCHESTRATORS[name].run(
        loaded_case, gateway, whole_record, "run_cancel_0001", cancel=token
    )

    statuses = {o.status for o in result.outcomes}
    assert SpecialistStatus.CANCELLED in statuses, f"{name} ran to completion despite cancellation"
    assert len(result.outcomes) == len(result.criteria), (
        "a cancelled criterion went unaccounted for"
    )
    assert result.breach is None, "cancellation was reported as a budget ceiling"
    assert any("run cancelled" in r for r in result.rejected)
    assert result.synthesis is None, "a cancelled run paid for a second stage"
    assert result.findings, "the completed criteria's work was discarded"


@pytest.mark.parametrize("name", BOTH)
def test_cancelled_criteria_are_left_for_the_next_run(
    loaded_case: LoadedCase, whole_record: InMemoryRetriever, name: str
) -> None:
    """Cancelled work is work still to do — the same rule a budget skip follows, and the reason
    both are kept out of `RESUMABLE_STATUSES`.

    On the LangGraph path this is the `_StopWork` raise doing its job: a returned value would have
    marked the task complete, and the resumed run would report a deliberately truncated case as a
    finished one.
    """
    if name == "langgraph":
        from ireports_orchestration.langgraph_adapter import strict_serde
        from langgraph.checkpoint.memory import InMemorySaver

        checkpointing = Checkpointing(saver=InMemorySaver(serde=strict_serde()))
    else:
        checkpointing = Checkpointing(store=InMemoryCheckpointStore())

    token = CancellationToken()
    run_id = "run_cancel_0002"
    first = ORCHESTRATORS[name].run(
        loaded_case,
        _run_gateway(token, cancel_after=1),
        whole_record,
        run_id,
        cancel=token,
        checkpointing=checkpointing,
    )
    stopped = [o for o in first.outcomes if o.status is SpecialistStatus.CANCELLED]
    assert stopped

    resumed_gateway = _run_gateway(CancellationToken(), cancel_after=99)
    second = ORCHESTRATORS[name].run(
        loaded_case, resumed_gateway, whole_record, run_id, checkpointing=checkpointing
    )

    assert not [o for o in second.outcomes if o.status is SpecialistStatus.CANCELLED], (
        f"{name}: the cancelled criteria were checkpointed as done, so the run that was meant to "
        "finish them found nothing outstanding"
    )
    assert resumed_gateway.analysed == len(stopped), (
        f"{name}: analysed {resumed_gateway.analysed} criteria for {len(stopped)} outstanding"
    )
