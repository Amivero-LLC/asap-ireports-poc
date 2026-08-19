"""What the *wrapper* claims, checked offline.

This spike is no longer where the analysis lives. Criteria selection, specialists, synthesis and
both orchestrators graduated to `packages/orchestration/`, and their tests went with them to
`tests/orchestration/`. What remains here is the runnable shell around them — reading a case off
disk, building the envelope, and the Lambda handler — and that is what this file tests.

Everything runs against `StubGateway`, so it is free, deterministic, and safe in CI. The live half
is `run_case.py`, which is opt-in and costs money.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
from time import sleep
from typing import Any
from uuid import uuid4

import pytest
from ireports_domain import ASAPEnvelope, FindingClassification
from ireports_gateway import StubGateway
from ireports_orchestration import CATALOG, ORCHESTRATORS
from ireports_retrieval import InMemoryRetriever, RetrievedSpan
from lambda_demo import handler as handler_module
from lambda_demo.case_loader import load_case
from lambda_demo.package import build_envelope

CASE_DIR = Path(__file__).parent / "cases" / "AMI-SYN-FIN-001"
RUN_ID = "run_test_0001"


@pytest.fixture
def case():
    return load_case(CASE_DIR)


@pytest.fixture
def retriever(case):
    """Every span, ignoring the query — offline and free. Not a retriever; see
    `tests/orchestration/test_orchestration.py`, which says the same thing at more length."""
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


def _finding(**overrides: Any) -> dict[str, Any]:
    """A well-formed finding as a model would emit it, before any override."""
    base: dict[str, Any] = {
        "title": "Foreign family contact reported in the questionnaire",
        "observation": "The record shows regular contact with a parent residing abroad [ev_001].",
        "policy_relevance": "Contact with foreign nationals may be relevant to this criterion.",
        "recommended_officer_action": "Review the reported contact and confirm its frequency.",
        "supporting_evidence": ["ev_001"],
        "mitigating_evidence": ["ev_002"],
        "information_gaps": [],
        "evidence_confidence": "moderate",
        "analysis_confidence": "moderate",
    }
    base.update(overrides)
    return base


SUFFICIENT = json.dumps({"sufficient": True, "missing": "", "next_query": ""})


def _sufficiency_answers() -> dict[str, str]:
    """A sufficiency reply per criterion, for the specialist's evidence loop.

    Without these the stub answers the loop's triage call with its findings JSON, the loop reads
    that as off-schema and stops — correct production behaviour for a broken assessor, and noise
    in a test that is about something else.
    """
    return {f"{c.node_id}:sufficiency": SUFFICIENT for c in CATALOG}


def _gateway(*findings: dict[str, Any]) -> StubGateway:
    return StubGateway(
        responses=_sufficiency_answers(), default=json.dumps({"findings": list(findings)})
    )


class _SlowGateway(StubGateway):
    """A stub that takes long enough for a wall-clock ceiling to be crossed mid-fan-out.

    Not a latency simulation — the only thing it is for is making the budget stop deterministic in
    an offline test, because `Budgets` refuses a ceiling below one second and a stub answers in
    microseconds.
    """

    def __init__(self, delay: float, *findings: dict[str, Any]) -> None:
        super().__init__(
            responses=_sufficiency_answers(), default=json.dumps({"findings": list(findings)})
        )
        self._delay = delay

    def complete(self, request):  # type: ignore[no-untyped-def]
        sleep(self._delay)
        return super().complete(request)


# ---------------------------------------------------------------------------
# Loading a case off disk
# ---------------------------------------------------------------------------


def test_the_case_loader_is_the_only_thing_here_that_knows_about_files() -> None:
    """The boundary this spike exists to hold after the graduation.

    `ireports_orchestration` owns the types; this package owns reading them off a disk, because
    where a case comes from is a property of the deployment (ADR-007). A `Path` or an `open()`
    appearing in the analysis package would put the AWS ingestion path one refactor away.
    """
    package = Path(__file__).parent / "src" / "lambda_demo"
    filesystem_aware = {
        module.name
        for module in package.glob("*.py")
        if "pathlib" in module.read_text() or "open(" in module.read_text()
    }
    assert filesystem_aware <= {"case_loader.py", "handler.py"}, sorted(filesystem_aware)


def test_a_case_with_duplicate_evidence_ids_is_refused(tmp_path: Path) -> None:
    """Ambiguous citations are worse than missing ones: every downstream check would pass."""
    (tmp_path / "case.json").write_text((CASE_DIR / "case.json").read_text())
    spans = json.loads((CASE_DIR / "evidence.json").read_text())["spans"]
    (tmp_path / "evidence.json").write_text(json.dumps({"spans": [spans[0], spans[0]]}))

    with pytest.raises(ValueError, match="duplicate evidence_id"):
        load_case(tmp_path)


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_envelope_is_machine_generated_and_unreviewed(case, retriever) -> None:
    """ADR-022: iReports emits proposals and records no human decision, ever."""
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(_finding()), retriever, RUN_ID)
    envelope = build_envelope(case, result.findings, RUN_ID)

    assert envelope.analysis.machine_generated is True
    dumped = envelope.model_dump(mode="json")
    assert ASAPEnvelope.model_validate(dumped)

    flat = json.dumps(dumped)
    for forbidden in ("disposition", "approval", "human_reviewed", "release_to_asap", "sign_off"):
        assert forbidden not in flat, (
            f"the envelope carries a {forbidden!r} field. No contract in this system models a "
            "human decision — review happens in ASAP (ADR-022)."
        )


def test_no_findings_means_no_envelope(case) -> None:
    """An empty envelope would deliver 'nothing found' as though it were a result."""
    with pytest.raises(ValueError, match="no findings survived"):
        build_envelope(case, (), RUN_ID)


def test_synthesis_findings_reach_the_envelope(case, retriever) -> None:
    """A cross-criterion finding is a `ProposedFinding` like any other, and is delivered like one.

    Giving synthesis a privileged section in the envelope would imply its findings carry more
    weight than a specialist's. They do not.
    """
    gateway = StubGateway(
        responses={
            "synthesis": json.dumps(
                {
                    "contradictions": [
                        {
                            "title": "SF-86 answer conflicts with the interview disclosure",
                            "observation": "The questionnaire records 'No' (ev_003); the interview "
                            "records a 4 percent interest (ev_004). Both cannot describe the same "
                            "holding.",
                            "policy_relevance": "The conflict may be relevant to what the record "
                            "establishes.",
                            "recommended_officer_action": "Review both statements and resolve "
                            "which is accurate.",
                            "criterion_id": "731-202-B-3",
                            "conflicting_evidence": ["ev_003", "ev_004"],
                        }
                    ],
                    "information_gaps": [],
                }
            )
        },
        default=json.dumps({"findings": [_finding()]}),
    )
    result = ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)
    envelope = build_envelope(case, result.findings, RUN_ID)

    delivered = {f.finding_id for f in envelope.analysis.findings}
    contradictions = [
        f for f in result.findings if f.classification is FindingClassification.CONTRADICTION
    ]
    assert len(contradictions) == 1
    assert contradictions[0].finding_id in delivered
    assert ASAPEnvelope.model_validate(envelope.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------


def test_handler_rejects_a_run_id_without_the_prefix(monkeypatch) -> None:
    """The gotcha that cost the most time, made loud.

    A `run_id` missing its `run_` prefix does not fail at the top — it fails on every *finding*,
    because `finding_id` embeds it. The run burns three model calls and reports zero findings,
    which reads exactly like model nondeterminism. Catching it at the door is worth a test.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    with pytest.raises(ValueError, match="must start with 'run_'"):
        handler_module.handler({"case_id": CASE_DIR.name, "run_id": "demo_langgraph"})


def test_handler_refuses_a_candidate_it_was_not_packaged_for() -> None:
    """Each package holds only its own candidate's dependencies, so this cannot be served."""
    other = "langgraph" if handler_module.CANDIDATE != "langgraph" else "hand-rolled"
    with pytest.raises(ValueError, match="invoke the other function"):
        handler_module.handler({"case_id": "AMI-SYN-FIN-001", "candidate": other})


def _offline_retrieval(monkeypatch, retriever) -> None:
    """Stop the handler reaching a real OpenSearch.

    The handler builds its own retriever, so an un-patched handler test silently opened a
    connection to the local cluster — which made an "offline" test depend on a running container
    and on whatever happened to be indexed in it. It passed or failed based on the state of a
    Docker volume. Both the client and the embedder are replaced here.
    """
    monkeypatch.setattr("ireports_retrieval.connect", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(
        "ireports_retrieval.OpenSearchRetriever", lambda *a, **k: retriever, raising=True
    )
    monkeypatch.setattr(
        "ireports_gateway.build_embedding_gateway", lambda *a, **k: None, raising=True
    )


def test_handler_returns_an_envelope(monkeypatch, retriever) -> None:
    """The whole path, offline: event in, validated envelope out."""
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()), raising=True
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["run_id"] == RUN_ID
    assert payload["findings"] == len(CATALOG)  # this case selects the whole catalog
    assert ASAPEnvelope.model_validate(payload["envelope"])


def test_handler_reports_an_empty_run_rather_than_crashing(monkeypatch, retriever) -> None:
    """A run where nothing survives validation still has to return its rejection record.

    That record is the only explanation of *why* nothing survived. Raising here would discard it
    and, under Lambda, trigger an automatic retry that pays for the same model calls again.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway",
        lambda *a, **k: _gateway(_finding(supporting_evidence=["ev_999"])),
        raising=True,
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["envelope"] is None
    assert "no findings survived" in payload["envelope_error"]
    assert payload["rejected"]


# ---------------------------------------------------------------------------
# Durable state across an invocation boundary (LAMB-01)
# ---------------------------------------------------------------------------

DSN = os.environ.get(
    "IREPORTS_SPIKE_DSN",
    "postgresql://ireports:ireports_local_only@localhost:5436/ireports_spike",
)


def test_a_run_without_a_state_dsn_says_so_rather_than_pretending(monkeypatch, retriever) -> None:
    """`durable: false` is the honest answer, and it has to be *in the payload*.

    A Lambda timeout is retried automatically. A function running without durable state is one
    whose retry re-does and re-pays for every model call — correct output, doubled cost, and
    nothing in the response that would let anyone notice.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(handler_module, "STATE_DSN", None)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()), raising=True
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["durable"] is False
    assert payload["model_calls"] is None
    assert payload["resumed_nodes"] == []


def test_the_wall_clock_ceiling_comes_from_configuration(monkeypatch) -> None:
    """The one budget this function overrides, and the only one with a hard reason.

    The shell has to stop before the platform does — that is the only moment a run gets to
    checkpoint. 780s against a 900s Timeout by default; lowering it is how the two-invocation
    resume is demonstrated without waiting thirteen minutes.
    """
    monkeypatch.delenv("IREPORTS_MAX_WALL_CLOCK_SECONDS", raising=False)
    assert handler_module._budgets().max_wall_clock_seconds == 780

    monkeypatch.setenv("IREPORTS_MAX_WALL_CLOCK_SECONDS", "12")
    assert handler_module._budgets().max_wall_clock_seconds == 12


@pytest.mark.requires_postgres
def test_a_second_invocation_finishes_what_the_first_started(monkeypatch, retriever) -> None:
    """**LAMB-01's mechanism, offline and free.**

    Two calls to the handler with one `run_id` and a durable store: the first stopped by a
    wall-clock ceiling below the work required, the second with the normal one. The second must
    restore what the first completed and pay only for what is outstanding.

    This is not the full requirement — that needs two SAM containers, which is
    `run_case.py --resume-demo` and costs money. What it does prove is everything between the
    handler and the database, on the same code path the container runs.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(handler_module, "STATE_DSN", DSN)
    _offline_retrieval(monkeypatch, retriever)

    run_id = f"run_lamb01_{uuid4().hex[:8]}"
    event = {"case_id": CASE_DIR.name, "run_id": run_id}

    # **A slow stub and a one-second ceiling, which is the only shape that works.** `breach()` is
    # checked when a criterion *starts*, and at t=0 nothing has been spent — so the first batch
    # always runs whatever the ceiling is. The criteria queued behind it are reached at
    # t≈one-call, which has to be over the line. `Budgets` forbids a ceiling below 1s, so the call
    # is what gets slowed rather than the limit lowered. Always work done, always work left, which
    # is the shape LAMB-01 needs.
    monkeypatch.setattr(
        "ireports_gateway.build_gateway", lambda *a, **k: _SlowGateway(1.1, _finding())
    )
    monkeypatch.setenv("IREPORTS_MAX_WALL_CLOCK_SECONDS", "1")
    first = handler_module.handler(event)

    assert first["durable"] is True
    assert first["incomplete_due_to_budget"] is True
    skipped = [c for c in first["criteria"] if c["status"] == "skipped_budget"]
    assert skipped, "nothing was left for the second invocation to do"
    completed = [c for c in first["criteria"] if c["status"] == "completed"]
    assert completed, "nothing was completed, so there is nothing to resume"

    second_gateway = _gateway(_finding())
    monkeypatch.setattr("ireports_gateway.build_gateway", lambda *a, **k: second_gateway)
    monkeypatch.delenv("IREPORTS_MAX_WALL_CLOCK_SECONDS", raising=False)
    second = handler_module.handler(event)

    assert second["incomplete_due_to_budget"] is False
    assert len(second["resumed_nodes"]) == len(completed), (
        f"the first invocation completed {len(completed)} criteria and the second restored "
        f"{second['resumed_nodes']} — the difference was re-executed"
    )
    # Analysis calls only; the evidence loop's triage sub-calls carry a suffixed node id.
    specialist_calls = [
        c for c in second_gateway.calls if c.node_id != "synthesis" and ":" not in c.node_id
    ]
    assert len(specialist_calls) == len(skipped), (
        f"the second invocation ran {len(specialist_calls)} specialists for {len(skipped)} "
        "outstanding criteria — it either redid restored work or skipped outstanding work"
    )
    assert second["envelope"] is not None, "the resumed run produced no envelope"


# ---------------------------------------------------------------------------
# The deadline watchdog (ORCH-03's cancellation driver)
# ---------------------------------------------------------------------------


class _Context:
    """Just enough of a Lambda context: the one method the watchdog reads."""

    def __init__(self, remaining_seconds: float) -> None:
        self._remaining = remaining_seconds

    def get_remaining_time_in_millis(self) -> int:
        return int(self._remaining * 1000)


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_environment_variable_is_not_an_absent_one(monkeypatch, value: str) -> None:
    """**The bug a live run found, and it cost an invocation to find.**

    Every variable in `template.yaml` is declared with an empty default, because `sam local invoke
    --env-vars` only overrides variables the template already declares. So in the container the
    name is *present and blank* — and `os.environ.get(name, "60")` applies its default only when
    the name is absent. `float("")` raised at module scope, before the handler ran, and Lambda
    reported `ValueError` with no variable name and no case id.

    Every other configuration read in this file already used `or`. This one did not, and nothing
    tested it because no offline test had ever set the variable to blank.
    """
    monkeypatch.setenv("IREPORTS_DEADLINE_RESERVE_SECONDS", value)
    assert handler_module._deadline_reserve() == handler_module.DEFAULT_DEADLINE_RESERVE_SECONDS

    monkeypatch.setenv("IREPORTS_DEADLINE_RESERVE_SECONDS", "12")
    assert handler_module._deadline_reserve() == 12


@pytest.mark.parametrize("value", ["", "  "])
def test_a_blank_wall_clock_ceiling_falls_back_to_the_default(monkeypatch, value: str) -> None:
    """The same check on the other numeric variable, which got it right by accident of style."""
    monkeypatch.setenv("IREPORTS_MAX_WALL_CLOCK_SECONDS", value)
    assert handler_module._budgets().max_wall_clock_seconds == 780


def test_a_run_with_no_time_left_is_cancelled_before_it_spends_anything(
    monkeypatch, retriever
) -> None:
    """**The clause that would otherwise be vacuous.**

    SPEC-01's tool allowlist is unmet because nothing can exercise it, and this repo says so rather
    than claiming it. Cancellation would be in the same position if nothing ever cancelled — so it
    is driven by the platform's own clock, and this is the proof that the wiring runs.

    A context reporting less time than the reserve cancels before the first criterion, so the run
    returns having spent nothing and having said why.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(handler_module, "STATE_DSN", None)
    _offline_retrieval(monkeypatch, retriever)
    gateway = _gateway(_finding())
    monkeypatch.setattr("ireports_gateway.build_gateway", lambda *a, **k: gateway)

    payload = handler_module.handler(
        {"case_id": CASE_DIR.name, "run_id": RUN_ID},
        _Context(handler_module._deadline_reserve() - 1),
    )

    assert payload["cancelled"] is True
    assert "reserve" in (payload["cancel_reason"] or "")
    assert not gateway.calls, "a run cancelled before it started still paid for calls"
    # Cancelled is not a budget breach, and the payload keeps them apart.
    assert payload["incomplete_due_to_budget"] is False
    assert payload["not_analysed"], "a cancelled run did not say which criteria it skipped"


def test_a_run_with_time_to_spare_is_not_cancelled(monkeypatch, retriever) -> None:
    """The control. Without it the test above passes on a watchdog that cancels everything."""
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(handler_module, "STATE_DSN", None)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr("ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()))

    payload = handler_module.handler(
        {"case_id": CASE_DIR.name, "run_id": RUN_ID},
        _Context(handler_module._deadline_reserve() + 300),
    )

    assert payload["cancelled"] is False
    assert payload["cancel_reason"] is None
    assert payload["envelope"] is not None
    assert not payload["not_analysed"]


def test_no_lambda_context_leaves_the_wall_clock_budget_in_charge(monkeypatch, retriever) -> None:
    """A host run, or a test, has no `get_remaining_time_in_millis`. That is not an error — the
    budget is the backstop, and the watchdog simply does not arm."""
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(handler_module, "STATE_DSN", None)
    _offline_retrieval(monkeypatch, retriever)
    monkeypatch.setattr("ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()))

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID}, object())

    assert payload["cancelled"] is False
    assert payload["envelope"] is not None


# ---------------------------------------------------------------------------
# The Lambda package
# ---------------------------------------------------------------------------


def _build_module() -> Any:
    """Load `build.py` by explicit path.

    Not `import build`: `spikes/lambda_fit/` has a `build.py` too, and which one a bare import
    resolves to depends on how pytest happened to order `sys.path`.
    """
    spec = importlib.util.spec_from_file_location(
        "lambda_demo_build", Path(__file__).parent / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_stages_every_package_the_handler_imports() -> None:
    """A package staged short one dependency fails at *import time inside the container*.

    `build.py` copies our pure-Python packages in by path rather than pip-installing them, so
    adding a package to the workspace does not add it to the Lambda build. Graduating orchestration
    out of this spike is exactly the change that could have missed it — the demo would still pass
    every test here and fail on the first `sam local invoke`.

    Loaded by explicit path rather than `import build`: `spikes/lambda_fit/` has a `build.py` too,
    and which one a bare import resolves to depends on how pytest happened to order sys.path.
    """
    module = _build_module()

    staged = {name for _src, name in module.SHARED_SOURCE}
    assert staged >= {
        "ireports_domain",
        "ireports_gateway",
        "ireports_orchestration",
        "ireports_retrieval",
        "lambda_demo",
    }
    for src, _name in module.SHARED_SOURCE:
        assert src.is_dir(), f"{src} is staged by build.py and does not exist"


def test_the_package_carries_the_driver_its_durability_depends_on() -> None:
    """A lazily-imported driver is a driver the build will forget.

    `PostgresCallStore` and `PostgresCheckpointStore` both import `psycopg` inside their methods,
    so a package built without it imports fine, passes every offline test, and fails on the first
    invocation that tried to be durable — which is the invocation that mattered. The LangGraph
    candidate needs a different package for the same job, which is ADR-026 showing up in a
    requirements file.
    """
    module = _build_module()

    assert any(r.startswith("psycopg") for r in module.BASE_REQUIREMENTS), module.BASE_REQUIREMENTS
    assert any(
        r.startswith("langgraph-checkpoint-postgres") for r in module.CANDIDATES["langgraph"]
    ), module.CANDIDATES["langgraph"]
    assert not module.CANDIDATES["handrolled"], (
        "the hand-rolled candidate grew a dependency; it checkpoints through checkpoint.py and "
        "the psycopg above, and 'adds nothing to the dependency tree' is one of its measurements"
    )


HOST_ONLY = frozenset({"IREPORTS_DEMO_CASES_DIR"})
"""Variables the handler reads that a *deployed* function must never need.

`build.py` stages `cases/` beside the module, so the packaged default is always correct inside the
container; this override exists only for running the handler on a host. Declaring it in the
template would say the opposite — that a Lambda might be pointed at some other directory — and the
cases are baked into the package, so it could not be.

An allowlist rather than a loosened check: a *new* undeclared variable is still a failure.
"""


def test_the_template_declares_every_variable_the_handler_reads() -> None:
    """**`sam local invoke --env-vars` only overrides variables the template already declares.**

    An undeclared one is dropped without a word, and the function then fails inside the container
    reporting a missing variable that is plainly set in your shell — which reads as a credentials
    problem and is not one. That cost an hour once (`docs/LESSONS.md`); this makes it cost a test
    run.

    Derived from the handler's source rather than a list here, so adding a variable to the handler
    and forgetting the template is a failure rather than a surprise.
    """
    handler_source = (Path(__file__).parent / "src" / "lambda_demo" / "handler.py").read_text()
    pattern = r'os\.environ\.get\(\s*"(IREPORTS_[A-Z0-9_]+)"'
    read_by_handler = set(re.findall(pattern, handler_source))
    template = (Path(__file__).parent / "template.yaml").read_text()
    declared = set(re.findall(r"^\s*(IREPORTS_[A-Z0-9_]+)\s*:", template, re.MULTILINE))

    assert read_by_handler, "the scan found nothing, so it is not checking anything"
    assert read_by_handler - HOST_ONLY <= declared, sorted(read_by_handler - HOST_ONLY - declared)
    assert HOST_ONLY.isdisjoint(declared), (
        f"{sorted(HOST_ONLY & declared)} is declared in the template, which says a deployed "
        "function might set it. If that is now true, take it out of HOST_ONLY."
    )
