"""Node-level checkpointing: a resume must skip completed work, not repeat it.

**What this measures, and what it deliberately does not.** `test_idempotency.py` already proves a
resumed run pays for nothing it already bought — 0 duplicate paid calls, both paths. So money is
not the variable here; **wall clock** is. A resumed run that re-executes four completed specialists
to reach the fifth spends four specialists' worth of time it does not have under Lambda's ceiling,
and the number below that matters is how many nodes did *not* execute.

The comparison is the deliverable (ADR-024): the hand-rolled store in `checkpoint.py` against
LangGraph's first-party `PostgresSaver`. Every behavioural test here is parameterised over both,
because a claim about one path is not a claim about the system.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Lock
from time import sleep
from typing import Any
from uuid import uuid4

import pytest
from ireports_domain import Budgets, CaseManifest
from ireports_gateway import StubGateway
from ireports_gateway.port import ModelRequest
from ireports_orchestration import (
    CATALOG,
    MAX_PARALLEL,
    ORCHESTRATORS,
    Checkpointing,
    EvidenceSpan,
    InMemoryCheckpointStore,
    LoadedCase,
    RunCheckpoint,
    SpecialistStatus,
)
from ireports_orchestration.budget import BudgetLedger
from ireports_orchestration.checkpoint import (
    CHECKPOINT_VERSION,
    RESUMABLE_STATUSES,
    SYNTHESIS_NODE,
    outcome_from_json,
    outcome_to_json,
    synthesis_from_json,
    synthesis_to_json,
)
from ireports_orchestration.langgraph_adapter import DURABILITY, strict_serde
from ireports_retrieval import InMemoryRetriever, RetrievedSpan

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASE_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "cases" / "AMI-SYN-FIN-001"
BOTH = ["hand-rolled", "langgraph"]

DSN = os.environ.get(
    "IREPORTS_SPIKE_DSN",
    "postgresql://ireports:ireports_local_only@localhost:5436/ireports_spike",
)


@pytest.fixture
def case() -> LoadedCase:
    manifest = CaseManifest.model_validate(json.loads((CASE_DIR / "case.json").read_text()))
    raw = json.loads((CASE_DIR / "evidence.json").read_text())
    spans = tuple(
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
    )
    return LoadedCase(manifest=manifest, spans=spans, root=CASE_DIR)


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


def _finding() -> dict[str, Any]:
    return {
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


SUFFICIENT = json.dumps({"sufficient": True, "missing": "", "next_query": ""})


def _sufficiency_answers(answer: str = SUFFICIENT) -> dict[str, str]:
    """A sufficiency reply per criterion, keyed the way `StubGateway` keys responses.

    Without these the stub answers the sufficiency call with its findings JSON, the loop reads it
    as off-schema, and every criterion in every test picks up a rejection line about it. That is
    the *correct* production behaviour for a broken assessor and it is noise here — an unconfigured
    double should not make every unrelated test assert around it.
    """
    return {f"{c.node_id}:sufficiency": answer for c in CATALOG}


def _gateway() -> StubGateway:
    return StubGateway(
        responses={
            "synthesis": json.dumps({"contradictions": [], "information_gaps": []}),
            **_sufficiency_answers(),
        },
        default=json.dumps({"findings": [_finding()]}),
    )


class _CrashAfter(StubGateway):
    """Fails the run after N successful calls — a crash mid-fan-out, made deterministic.

    Raises `RuntimeError` rather than a `GatewayError`: a gateway error is *contained* by the
    specialist and turned into a not-analysed criterion, which is the opposite of a crash. This has
    to escape the node the way a process death would. Same double as `test_idempotency.py` uses,
    for the same reason.
    """

    def __init__(self, crash_after: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.crash_after = crash_after
        self._analysis_calls = 0

    def complete(self, request: ModelRequest) -> Any:
        # Counted on *analysis* calls only. Crashing on the Nth call of any kind would make the
        # crash point depend on how many triage calls the evidence loop happened to make, so the
        # parameterisation would no longer mean "after N completed specialists".
        if ":" not in request.node_id and self._analysis_calls >= self.crash_after:
            raise RuntimeError("simulated process death mid-fan-out")
        if ":" not in request.node_id:
            self._analysis_calls += 1
        return super().complete(request)


def _specialist_calls(gateway: StubGateway) -> int:
    """Calls that were a specialist *analysing* a criterion.

    Excludes synthesis, and excludes the evidence loop's sufficiency triage — those are real paid
    calls and they are counted by the ledger, but they are not the unit "how many criteria did this
    run analyse" is measured in. `node_id` carries the distinction: an analysis call is the bare
    node id, a sub-call is suffixed.
    """
    return sum(1 for c in gateway.calls if c.node_id != "synthesis" and ":" not in c.node_id)


def _run_id(tag: str) -> str:
    """A fresh id per test, because a checkpoint is scoped to a run and Postgres rows outlive a
    test session. Two tests sharing an id would make the second one resume the first."""
    return f"run_{tag}_{uuid4().hex[:8]}"


def _in_memory(name: str) -> Checkpointing:
    """One checkpointer per path, both ephemeral, both surviving between two `run()` calls.

    **The two arguments are not interchangeable and that is the point.** `store` is a map of node
    id to result; `saver` is LangGraph's superstep bookkeeping. They are not two implementations
    of one interface, so `Checkpointing` carries a slot for each — see its docstring.
    """
    if name == "langgraph":
        from langgraph.checkpoint.memory import InMemorySaver

        return Checkpointing(saver=InMemorySaver(serde=strict_serde()))
    return Checkpointing(store=InMemoryCheckpointStore())


# ---------------------------------------------------------------------------
# The measurement — a resume skips completed nodes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", BOTH)
@pytest.mark.parametrize("crash_after", [1, 2, 3, 4])
def test_a_resumed_run_does_not_re_execute_a_completed_node(
    case: LoadedCase, retriever: InMemoryRetriever, name: str, crash_after: int
) -> None:
    """**The number this whole module exists to move.**

    Crash the run after N specialist calls, then resume over the same checkpoint. Every specialist
    that finished before the crash must be restored rather than run again — because under Lambda
    the resumed invocation has the same 15-minute ceiling as the one that died, and re-doing four
    specialists to reach the fifth may simply not fit.

    Parameterised over every crash point, because a scheme that restores only the first node would
    pass a single-point test and lose most of the saving in production.
    """
    run_id = _run_id(f"resume_{crash_after}")
    checkpointing = _in_memory(name)

    crashing = _CrashAfter(
        crash_after,
        responses=_sufficiency_answers(),
        default=json.dumps({"findings": [_finding()]}),
    )
    with pytest.raises(RuntimeError):
        ORCHESTRATORS[name].run(case, crashing, retriever, run_id, checkpointing=checkpointing)

    completed_before = _specialist_calls(crashing)
    assert completed_before == crash_after, "the harness did not crash where it said it would"

    resumed_gateway = _gateway()
    result = ORCHESTRATORS[name].run(
        case, resumed_gateway, retriever, run_id, checkpointing=checkpointing
    )

    restored = len(result.resumed_nodes)
    if name == "hand-rolled":
        # **Exact, every time.** The commit happens inside the worker, synchronously, before
        # `analyze` returns — so a call that was paid for is a durable checkpoint before any
        # sibling's exception can matter.
        assert restored == completed_before, (
            f"{completed_before} specialist(s) finished before the crash and {restored} were "
            "restored — the difference is re-executed work"
        )
    else:
        # **A bound, not an equality, and the gap is a measured result rather than flakiness.**
        # LangGraph persists a task's writes from the *runner*, after the task returns. When a
        # sibling raises, the executor shuts down and a completed task's write can no longer be
        # submitted — `RuntimeError: cannot schedule new futures after shutdown`, visible in the
        # captured log of any trial that loses one. `durability="sync"` narrows that window; it
        # cannot close it, because the write still happens outside the node.
        #
        # Measured over the same 24-trial shape the bake-off used: hand-rolled 0 lost writes,
        # LangGraph 8. It costs wall clock and not money — the gateway's call store means the
        # re-executed specialist is replayed rather than re-bought — which is exactly the
        # resource checkpointing exists to buy back. See `docs/LESSONS.md`.
        assert restored <= completed_before, (
            f"{restored} nodes restored from {completed_before} completed calls — a checkpoint "
            "appeared for work that never happened"
        )

    assert _specialist_calls(resumed_gateway) == len(result.criteria) - restored, (
        f"{name}: the resumed run made {_specialist_calls(resumed_gateway)} specialist calls "
        f"with {restored} restored out of {len(result.criteria)} criteria — it either redid "
        "restored work or skipped outstanding work"
    )
    assert len(result.outcomes) == len(result.criteria), "the resumed run lost a criterion"
    assert result.findings, "the resumed run produced nothing, so the restore proved nothing"


@pytest.mark.parametrize("name", BOTH)
def test_a_resumed_run_is_the_same_run(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """Restoring must not change the answer, only what it cost to get it.

    A checkpoint that produced *different* findings on resume would be worse than no checkpoint at
    all: the run a reviewer sees would depend on whether the process happened to survive.
    """
    clean = ORCHESTRATORS[name].run(case, _gateway(), retriever, _run_id("clean"))

    run_id = _run_id("crashed")
    checkpointing = _in_memory(name)
    with pytest.raises(RuntimeError):
        ORCHESTRATORS[name].run(
            case,
            _CrashAfter(
                2,
                responses=_sufficiency_answers(),
                default=json.dumps({"findings": [_finding()]}),
            ),
            retriever,
            run_id,
            checkpointing=checkpointing,
        )
    resumed = ORCHESTRATORS[name].run(
        case, _gateway(), retriever, run_id, checkpointing=checkpointing
    )

    assert [f.title for f in resumed.findings] == [f.title for f in clean.findings]
    assert {o.criterion.criterion_id for o in resumed.outcomes} == {
        o.criterion.criterion_id for o in clean.outcomes
    }


@pytest.mark.parametrize("name", BOTH)
def test_a_completed_synthesis_is_not_paid_for_twice(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """The second stage is a paid call like any other, and re-running it is a second charge.

    Worth its own test because synthesis is the one node that is not part of the fan-out — a
    checkpoint scheme that covered only the `Send`-dispatched work would look correct on every
    specialist assertion above and quietly re-buy this.
    """
    run_id = _run_id("synth")
    checkpointing = _in_memory(name)

    first = _gateway()
    ORCHESTRATORS[name].run(case, first, retriever, run_id, checkpointing=checkpointing)
    assert any(c.node_id == "synthesis" for c in first.calls), "synthesis did not run at all"

    second = _gateway()
    result = ORCHESTRATORS[name].run(case, second, retriever, run_id, checkpointing=checkpointing)

    assert not second.calls, f"{name} re-ran {len(second.calls)} call(s) on a completed run"
    assert SYNTHESIS_NODE in result.resumed_nodes
    assert result.synthesis is not None, "the restored run lost its synthesis findings"


@pytest.mark.parametrize("name", BOTH)
def test_a_run_without_checkpointing_re_executes_everything(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """The negative control.

    Without it, every assertion above is also satisfied by a system that simply never calls the
    model twice for an unrelated reason. `resumed_nodes` must be empty and the work must be redone.
    """
    run_id = _run_id("nocheckpoint")
    ORCHESTRATORS[name].run(case, _gateway(), retriever, run_id)

    second = _gateway()
    result = ORCHESTRATORS[name].run(case, second, retriever, run_id)

    assert result.resumed_nodes == ()
    assert _specialist_calls(second) == len(result.criteria)


# ---------------------------------------------------------------------------
# The LAMB-01 shape: a budget stop leaves work for the next invocation
# ---------------------------------------------------------------------------


def _budgets(**overrides: Any) -> Budgets:
    base: dict[str, Any] = {
        "max_input_tokens": 400_000,
        "max_output_tokens": 200_000,
        "max_wall_clock_seconds": 780,
    }
    base.update(overrides)
    return Budgets(**base)


@pytest.mark.parametrize("name", BOTH)
def test_a_criterion_skipped_on_budget_is_done_by_the_next_invocation(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**LAMB-01 in miniature, and the trap that makes it hard.**

    A criterion nobody attempted because the run ran out of wall clock is precisely the work the
    *next* invocation exists to do. Checkpointing it as complete would make the first invocation's
    stop permanent — the resumed run would find nothing outstanding and report a truncated case as
    a finished one.

    The two paths have to prevent that differently, which is the finding
    (`docs/LESSONS.md`): the hand-rolled store filters on `RESUMABLE_STATUSES`, while the LangGraph
    node has to *raise*, because there a returned value is what marks a task complete.
    """
    run_id = _run_id("budget")
    checkpointing = _in_memory(name)

    first = _gateway()
    truncated = ORCHESTRATORS[name].run(
        case,
        first,
        retriever,
        run_id,
        budgets=_budgets(max_output_tokens=1),
        checkpointing=checkpointing,
    )
    skipped = [o for o in truncated.outcomes if o.status is SpecialistStatus.SKIPPED_BUDGET]
    assert skipped, f"{name} spent the whole budget without skipping anything"
    assert truncated.breach is not None
    assert len(truncated.outcomes) == len(truncated.criteria), (
        "a truncated run must still account for every criterion"
    )

    second = _gateway()
    finished = ORCHESTRATORS[name].run(case, second, retriever, run_id, checkpointing=checkpointing)

    assert finished.breach is None, "the second invocation inherited the first one's ceiling"
    assert not [o for o in finished.outcomes if o.status is SpecialistStatus.SKIPPED_BUDGET], (
        f"{name}: the budget-skipped criteria were checkpointed as done, so the invocation whose "
        "whole job was to finish them found nothing outstanding"
    )
    assert _specialist_calls(second) == len(skipped), (
        f"{name}: the second invocation ran {_specialist_calls(second)} specialists for "
        f"{len(skipped)} outstanding criteria — it either redid completed work or skipped some"
    )
    assert len(finished.resumed_nodes) == len(finished.criteria) - len(skipped)


def test_a_budget_skip_is_never_written_to_the_checkpoint(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """The rule above, asserted on the rows rather than on the behaviour.

    The behavioural test would still pass if the row were written and something downstream happened
    to ignore it. This looks at the store.
    """
    store = InMemoryCheckpointStore()
    run_id = _run_id("rows")
    result = ORCHESTRATORS["hand-rolled"].run(
        case,
        _gateway(),
        retriever,
        run_id,
        budgets=_budgets(max_output_tokens=1),
        checkpointing=Checkpointing(store=store),
    )

    skipped = {
        o.criterion.node_id for o in result.outcomes if o.status is SpecialistStatus.SKIPPED_BUDGET
    }
    assert skipped
    assert skipped.isdisjoint(store.completed(run_id)), (
        "a criterion nobody attempted was recorded as completed work"
    )


def test_a_ledger_remembers_the_moment_work_stopped() -> None:
    """**One fact, one pair of numbers, wherever it is quoted.**

    `breach()` is asked once per criterion, again before synthesis, and again when the result is
    assembled. Measuring the wall clock afresh each time answers a different question each time,
    and a live run duly reported `18.5 of 10` on its skipped criteria and `34.4 of 10` in its
    summary — same payload, same event. A reader has no way to tell which one stopped the work.

    Tested on the ledger with an injected clock rather than through a run: through a run the two
    measurements are microseconds apart against a stub gateway, so an assertion there passes
    whether or not the property holds. A test that cannot fail is worse than no test.
    """
    now = [0.0]
    ledger = BudgetLedger(_budgets(max_wall_clock_seconds=10), clock=lambda: now[0])

    assert ledger.breach() is None

    now[0] = 12.0
    first = ledger.breach()
    assert first is not None
    assert first.reached == 12.0

    now[0] = 40.0
    assert ledger.breach() == first, "the breach moved; a later reader would quote a different stop"
    # Elapsed time genuinely keeps running, and this is where that belongs — here it means what it
    # says, rather than standing in for when the work stopped.
    assert ledger.consumption().wall_clock_seconds == 40.0


def test_every_skipped_criterion_quotes_the_run_s_breach(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """The same property seen from the payload a reader actually gets.

    Not the regression guard — see above for why it cannot be — but it is what would fail if a
    rejection line were ever built from a *different* ceiling than the one the run reports.
    """
    result = ORCHESTRATORS["hand-rolled"].run(
        case,
        _gateway(),
        retriever,
        _run_id("onebreach"),
        budgets=_budgets(max_output_tokens=1),
    )

    assert result.breach is not None
    quoted = str(result.breach)
    skipped = [o for o in result.outcomes if o.status is SpecialistStatus.SKIPPED_BUDGET]
    assert skipped
    for outcome in skipped:
        assert any(quoted in reason for reason in outcome.rejected), (
            f"a skipped criterion quotes a different breach than the run does:\n"
            f"  run:       {quoted}\n  criterion: {outcome.rejected}"
        )


def test_only_work_that_happened_is_resumable() -> None:
    """`RESUMABLE_STATUSES` spelled out, so the reasoning survives a refactor of the enum.

    `REFUSED` belongs here and is the one people remove: a refusal is a *result* that was paid for,
    and ADR-015 says it must not be re-asked. `FAILED` does not, because a transport fault may not
    recur and freezing it would deny the resume its whole purpose.
    """
    assert {SpecialistStatus.COMPLETED, SpecialistStatus.REFUSED} == RESUMABLE_STATUSES
    assert SpecialistStatus.SKIPPED_BUDGET not in RESUMABLE_STATUSES
    assert SpecialistStatus.FAILED not in RESUMABLE_STATUSES


@pytest.mark.parametrize("name", BOTH)
def test_the_fan_out_never_runs_wider_than_max_parallel(
    case: LoadedCase, retriever: InMemoryRetriever, name: str
) -> None:
    """**Unbounded fan-out over paid model calls is the failure budgets exist to prevent.**

    `MAX_PARALLEL` bounds the hand-rolled path for free — it is the `ThreadPoolExecutor`'s
    `max_workers`. A `Send` fan-out has no such argument, and until `max_concurrency` was set on
    the config LangGraph ran every dispatch at once: measured 8 of 8 on an 8-way probe. It is worse
    under Lambda, where a timed-out invocation is retried automatically and re-pays for the whole
    width.

    It is also what makes a wall-clock stop possible: a run where every criterion starts at t=0 has
    nothing left to leave for the next invocation.
    """
    live = 0
    peak = 0
    lock = Lock()

    class _Counting(StubGateway):
        def complete(self, request: ModelRequest) -> Any:
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            try:
                sleep(0.05)
                return super().complete(request)
            finally:
                with lock:
                    live -= 1

    gateway = _Counting(
        responses=_sufficiency_answers(), default=json.dumps({"findings": [_finding()]})
    )
    result = ORCHESTRATORS[name].run(case, gateway, retriever, _run_id("width"))

    assert len(result.criteria) > MAX_PARALLEL, "the case cannot exercise the bound"
    assert peak <= MAX_PARALLEL, (
        f"{name} ran {peak} specialists at once against a bound of {MAX_PARALLEL}"
    )


# ---------------------------------------------------------------------------
# The codec — JSON in both directions, re-validated through the contracts
# ---------------------------------------------------------------------------


def test_an_outcome_round_trips_through_json_and_re_enters_its_contract(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """Stored as data, never as a pickled object.

    A checkpoint blob that deserializes into live objects is a code-execution surface. This
    round-trips through `json` and re-enters `SpecialistResult` through the ordinary constructor,
    so a tampered row produces a bad value rather than a running one.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(), retriever, _run_id("codec"))
    original = result.outcomes[0]

    # Through a real serialization boundary, not just the dict: a value that is not JSON-encodable
    # would pass an in-memory round trip and fail against Postgres.
    payload = json.loads(json.dumps(outcome_to_json(original)))
    restored = outcome_from_json(payload, original.criterion)

    assert restored.result == original.result
    assert restored.status is original.status
    assert restored.retrieved == original.retrieved
    assert [f.finding_id for f in restored.findings] == [f.finding_id for f in original.findings]


def test_synthesis_round_trips_through_json(case: LoadedCase, retriever: InMemoryRetriever) -> None:
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(), retriever, _run_id("codecsyn"))
    assert result.synthesis is not None

    restored = synthesis_from_json(json.loads(json.dumps(synthesis_to_json(result.synthesis))))

    assert restored.overlaps == result.synthesis.overlaps
    assert restored.rejected == result.synthesis.rejected
    assert restored.failed is result.synthesis.failed


def test_a_row_written_for_another_criterion_is_refused(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """The integrity check the criterion's absence from the row makes possible.

    The `Criterion` is re-derived from the case rather than stored, so a mismatched row cannot
    smuggle in an authority the case never selected — but it could still deliver one criterion's
    findings under another's, which is what this refuses.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(), retriever, _run_id("mismatch"))
    payload = outcome_to_json(result.outcomes[0])
    other = result.outcomes[1].criterion

    with pytest.raises(ValueError, match="under another's authority"):
        outcome_from_json(payload, other)


def test_a_row_from_an_older_format_is_refused(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """A stale row must fail loudly rather than be read by the wrong reader.

    Re-executing a node is only slow. Restoring a row this code misunderstands is wrong, and wrong
    in a way that reaches a reviewer.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(), retriever, _run_id("stale"))
    payload = outcome_to_json(result.outcomes[0])
    payload["v"] = "0"

    with pytest.raises(ValueError, match="format version"):
        outcome_from_json(payload, result.outcomes[0].criterion)
    assert CHECKPOINT_VERSION == "1"


def test_a_tampered_row_fails_validation_rather_than_restoring(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """**The half of the trust boundary that re-validation actually covers.**

    Row integrity is *not* addressed — a tampered row that still parses would be restored as though
    the model produced it, and that is the largest known gap in this design
    (`docs/handoff/checkpoint-threat-model.md`). What re-validating through the contract does cover
    is a row that no longer satisfies them: determinative language, a broken id, a bad enum. This
    asserts that half and does not pretend to the other.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(), retriever, _run_id("tamper"))
    payload = outcome_to_json(result.outcomes[0])
    payload["result"]["findings"][0]["observation"] = "The subject is unsuitable for access."

    with pytest.raises(ValueError):
        outcome_from_json(payload, result.outcomes[0].criterion)


def test_the_store_keeps_the_first_answer(case: LoadedCase, retriever: InMemoryRetriever) -> None:
    """`ON CONFLICT DO NOTHING`, and the in-memory store agrees with it.

    Two stores that disagreed about re-recording would make the offline tests above prove something
    the durable path does not do.
    """
    store = InMemoryCheckpointStore()
    run_id = _run_id("firstwins")
    result = ORCHESTRATORS["hand-rolled"].run(
        case, _gateway(), retriever, run_id, checkpointing=Checkpointing(store=store)
    )
    node = result.outcomes[0].criterion.node_id

    store.record(run_id, node, {"v": CHECKPOINT_VERSION, "node_id": node, "later": True})

    assert "later" not in store.completed(run_id)[node]


def test_a_checkpoint_is_scoped_to_one_run(case: LoadedCase, retriever: InMemoryRetriever) -> None:
    """Restore is per run, never across runs — the same rule `idempotency.py` holds for replay.

    A second run restoring the first's nodes would make its provenance a lie about which call
    produced its findings. Re-analysis has to cost time.
    """
    store = InMemoryCheckpointStore()
    checkpointing = Checkpointing(store=store)
    ORCHESTRATORS["hand-rolled"].run(
        case, _gateway(), retriever, _run_id("first"), checkpointing=checkpointing
    )

    second = _gateway()
    result = ORCHESTRATORS["hand-rolled"].run(
        case, second, retriever, _run_id("second"), checkpointing=checkpointing
    )

    assert result.resumed_nodes == ()
    assert _specialist_calls(second) == len(result.criteria)


def test_a_run_checkpoint_reports_what_it_restored(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """`resumed` is the measurement, so it is asserted directly rather than only through a run."""
    store = InMemoryCheckpointStore()
    run_id = _run_id("count")
    result = ORCHESTRATORS["hand-rolled"].run(
        case, _gateway(), retriever, run_id, checkpointing=Checkpointing(store=store)
    )

    fresh = RunCheckpoint(run_id, store)
    assert fresh.resumed == ()
    for outcome in result.outcomes:
        assert fresh.restore_specialist(outcome.criterion) is not None
    assert set(fresh.resumed) == {o.criterion.node_id for o in result.outcomes}


def test_checkpointing_without_a_store_or_a_dsn_refuses_to_pretend() -> None:
    """Silently falling back to no checkpointing is how a resume discovers there is nothing to
    resume from, at the moment it is least able to do anything about it."""
    with pytest.raises(ValueError, match="nowhere durable"):
        Checkpointing().run_checkpoint("run_nowhere")


# ---------------------------------------------------------------------------
# ORCH-01's checkpoint clauses, set in code
# ---------------------------------------------------------------------------


def test_durability_is_sync() -> None:
    """**ORCH-01, and LangGraph's default is wrong for us.**

    `put_writes` is submitted to a background executor, so persistence normally runs concurrently
    with the next node — a process killed in that window loses a write it appears to have made.
    Under Lambda the process is killed on a timer, which is exactly that window.

    Asserted on a named constant because a durability setting written once inside a method is a
    setting nobody can check.
    """
    assert DURABILITY == "sync"


def test_checkpoint_deserialization_is_strict_and_never_unpickles() -> None:
    """**ORCH-01's other clause.** The permissive default imports and executes any callable stored
    in checkpoint data on load — LangGraph says so itself in
    `langgraph/checkpoint/serde/_msgpack.py`. Selected in code, not by an environment variable,
    so an environment that forgot to set it cannot lose it.
    """
    serde = strict_serde()

    assert serde.pickle_fallback is False
    # Private, and asserted anyway: this is the setting whose *default* imports and executes
    # arbitrary callables, so "we set it" is worth more than "we did not reach into the object".
    assert serde._allowed_msgpack_modules is None


def test_strict_deserialization_silently_downgrades_our_types_to_dicts() -> None:
    """**The measured trap that decides how the LangGraph state channels are shaped.**

    Under strict mode a type outside the allowlist is not *rejected* — it comes back as a plain
    `dict`, with a warning on stderr and no exception. And it only happens on the resume path,
    because a run that never crashes never deserializes. A `SpecialistOutcome` in a state channel
    would therefore work perfectly until the first crash in production and then fail on
    `.findings`.

    That is why `FanOutState` carries JSON and why `checkpoint.py`'s codec — written for the
    hand-rolled path — is imported by the LangGraph one too. The first-party checkpointer saves you
    the store, not the codec.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Typed:
        a: str

    serde = strict_serde()
    restored = serde.loads_typed(serde.dumps_typed(_Typed(a="x")))

    assert restored == {"a": "x"}
    assert not isinstance(restored, _Typed), (
        "strict deserialization returned the real type — if LangGraph has started raising or "
        "preserving instead, the JSON state channels can be reconsidered"
    )


# ---------------------------------------------------------------------------
# Durability — the half InMemoryCheckpointStore cannot prove
# ---------------------------------------------------------------------------


@pytest.mark.requires_postgres
def test_a_checkpoint_survives_a_real_process_boundary(
    case: LoadedCase, retriever: InMemoryRetriever, tmp_path: Path
) -> None:
    """**The claim `InMemoryCheckpointStore` cannot make.**

    Everything above proves the mechanism inside one process. A Lambda timeout kills the process,
    so what matters for LAMB-01 is whether a *second* process can restore what the first completed.
    This writes here and reads in a genuinely separate interpreter — not a fresh object, a fresh
    runtime.
    """
    run_id = _run_id("durable")
    result = ORCHESTRATORS["hand-rolled"].run(
        case, _gateway(), retriever, run_id, checkpointing=Checkpointing(dsn=DSN)
    )
    expected = [*(o.criterion.node_id for o in result.outcomes), SYNTHESIS_NODE]

    reader = tmp_path / "read_it.py"
    reader.write_text(
        "import json, sys\n"
        "from ireports_orchestration import PostgresCheckpointStore\n"
        f"rows = PostgresCheckpointStore({DSN!r}, create_schema=False).completed({run_id!r})\n"
        "sys.stdout.write(json.dumps(sorted(rows)))\n"
    )
    proc = subprocess.run(
        [sys.executable, str(reader)], capture_output=True, text=True, check=False
    )

    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout) == sorted(expected), (
        "a second process could not see the nodes the first completed — a resumed Lambda "
        "invocation would redo all of them, which is the whole failure this exists to prevent"
    )


@pytest.mark.requires_postgres
@pytest.mark.parametrize("name", BOTH)
def test_a_resume_across_processes_skips_completed_nodes(
    case: LoadedCase, retriever: InMemoryRetriever, name: str, tmp_path: Path
) -> None:
    """**The end-to-end durability claim, both paths, across two interpreters.**

    The first process crashes mid-fan-out and dies. A second process — not a second object — runs
    the same run id and must skip what the first completed. This is LAMB-01's mechanism without
    Lambda; `spikes/lambda_demo/` puts it behind an invocation boundary.
    """
    run_id = _run_id(f"xproc_{name.replace('-', '')}")
    script = tmp_path / "leg.py"
    script.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from test_checkpoint import (_CrashAfter, _finding, _gateway, _load_case,\n"
        "                             _retriever, _sufficiency_answers)\n"
        "from ireports_orchestration import ORCHESTRATORS, Checkpointing\n"
        "name, run_id, dsn, crash = sys.argv[1:5]\n"
        "case = _load_case()\n"
        "cp = Checkpointing(dsn=dsn)\n"
        "gw = (_CrashAfter(int(crash), responses=_sufficiency_answers(),\n"
        "                  default=json.dumps({'findings': [_finding()]}))\n"
        "      if int(crash) >= 0 else _gateway())\n"
        "try:\n"
        "    r = ORCHESTRATORS[name].run(case, gw, _retriever(case), run_id, checkpointing=cp)\n"
        "except RuntimeError:\n"
        "    sys.stdout.write(json.dumps({'crashed': True}))\n"
        "    raise SystemExit(0)\n"
        "sys.stdout.write(json.dumps({'resumed': list(r.resumed_nodes),\n"
        "                             'calls': [c.node_id for c in gw.calls],\n"
        "                             'criteria': len(r.criteria)}))\n"
    )

    first = subprocess.run(
        [sys.executable, str(script), name, run_id, DSN, "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr[-3000:]
    assert json.loads(first.stdout)["crashed"] is True

    second = subprocess.run(
        [sys.executable, str(script), name, run_id, DSN, "-1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr[-3000:]
    payload = json.loads(second.stdout)

    restored = len(payload["resumed"])
    # `== 2` for the hand-rolled path, `<= 2` for LangGraph, for the reason the in-process test
    # spells out: a write submitted from the runner after the task returns can be lost when a
    # sibling's exception shuts the executor down.
    assert restored == 2 if name == "hand-rolled" else restored <= 2, (
        f"{name}: a second *process* restored {payload['resumed']} from two completed specialists"
    )
    assert restored > 0, (
        f"{name}: a second process restored nothing — the checkpoint did not survive the first "
        "process at all, which is the whole claim"
    )
    # Analysis calls only — the evidence loop's triage sub-calls are real and are not the unit
    # "how many criteria did this process analyse" is counted in. See `_specialist_calls`.
    specialists = [n for n in payload["calls"] if n != "synthesis" and ":" not in n]
    assert len(specialists) == payload["criteria"] - restored


def _load_case() -> LoadedCase:
    """Importable by the subprocess above, which cannot use a pytest fixture."""
    manifest = CaseManifest.model_validate(json.loads((CASE_DIR / "case.json").read_text()))
    raw = json.loads((CASE_DIR / "evidence.json").read_text())
    spans = tuple(
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
    )
    return LoadedCase(manifest=manifest, spans=spans, root=CASE_DIR)


def _retriever(loaded: LoadedCase) -> InMemoryRetriever:
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
            for s in loaded.spans
        )
    )
