"""What the demo claims, checked offline.

Everything here runs against `StubGateway`, so the whole file is free, deterministic, and safe in
CI. The live half — real model calls through a real LiteLLM proxy — is `run_case.py`, which is
opt-in and costs money. The split is deliberate: what these tests assert is that the
**deterministic shell** behaves, and the shell is exactly the part that must not depend on what a
model happened to return.

The rejection tests are the important ones. Each feeds the pipeline a response a real model has
actually produced — an unresolvable citation, a determinative conclusion, a span cited in two
roles at once — and asserts the finding does not survive. `CLAUDE.md`: the model reasons; it does
not decide whether its own output is valid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ireports_domain import ASAPEnvelope, DecisionDomain
from ireports_gateway import StubGateway
from lambda_demo import handler as handler_module
from lambda_demo.case_loader import LoadedCase, load_case
from lambda_demo.criteria import CATALOG, NoApplicableCriteriaError, criteria_for
from lambda_demo.orchestrator import ORCHESTRATORS
from lambda_demo.package import build_envelope
from lambda_demo.specialist import analyze

CASE_DIR = Path(__file__).parent / "cases" / "AMI-SYN-FIN-001"
RUN_ID = "run_test_0001"


@pytest.fixture
def case():
    return load_case(CASE_DIR)


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


def _gateway(*findings: dict[str, Any]) -> StubGateway:
    """A stub returning the same findings payload for every node."""
    return StubGateway(default=json.dumps({"findings": list(findings)}))


# ---------------------------------------------------------------------------
# The port holds
# ---------------------------------------------------------------------------


def test_nodes_do_not_import_langgraph() -> None:
    """ADR-012 chose LangGraph; this is what keeps that from becoming lock-in.

    A source scan rather than an import check, because an import check passes for the wrong
    reason: `orchestrator.py` imports LangGraph lazily, so a specialist that imported it too
    would still not fail at collection time. The claim is about the *source*, so the source is
    what gets read.

    `orchestrator.py` and `handler.py` are deliberately absent from the list. They are the two
    places the framework is *allowed* to appear — one is the adapter, the other is the packaging
    entry point that pays for the import at init. The rule is that nothing which analyzes a case
    knows a framework exists.
    """
    package = Path(__file__).parent / "src" / "lambda_demo"
    for module in ("specialist.py", "case_loader.py", "package.py"):
        source = (package / module).read_text()
        assert "langgraph" not in source.lower(), (
            f"{module} references LangGraph. Nodes depend on our port, never on the framework — "
            "that is the whole protection against ADR-012 becoming lock-in."
        )


def test_both_orchestrators_produce_the_same_findings(case) -> None:
    """Same case, same stub, two orchestrators, identical output.

    With a real model the two candidates return different analyses — they are two runs of a
    probabilistic process, not two evaluations of a function. Pinning the model response is what
    turns "similar" into "identical" and makes the port's claim checkable at all.
    """
    results = {
        name: orchestrator.run(case, _gateway(_finding()), RUN_ID)
        for name, orchestrator in ORCHESTRATORS.items()
    }
    shapes = {
        name: [(f.finding_id, f.title, f.supporting_evidence) for f in result.findings]
        for name, result in results.items()
    }
    assert shapes["hand-rolled"] == shapes["langgraph"]
    assert len(shapes["hand-rolled"]) == len(criteria_for(case.manifest))


# ---------------------------------------------------------------------------
# The fan-out width comes from the case
# ---------------------------------------------------------------------------


def _manifest(case, **overrides):
    return case.manifest.model_copy(update=overrides)


def test_criteria_come_from_the_case_not_a_constant(case) -> None:
    """Different requests select different criteria. This is the whole point of the change.

    A fan-out whose width is fixed at import time is one line in any framework, so it cannot
    distinguish two orchestrators. Width as runtime data is what makes the comparison real.
    """
    both = criteria_for(case.manifest)
    suitability_only = criteria_for(
        _manifest(case, requested_analyses=(DecisionDomain.SUITABILITY,))
    )

    assert len(suitability_only) < len(both)
    assert {c.decision_domain for c in suitability_only} == {DecisionDomain.SUITABILITY}
    # Narrowing the pack list narrows the selection too — both dimensions are live.
    assert len(criteria_for(_manifest(case, policy_pack_ids=("sead4-current",)))) < len(both)


def test_both_orchestrators_fan_out_to_the_width_the_case_asks_for(case) -> None:
    """The runtime width reaches both implementations, not just the selection function.

    Asserted on `outcomes` rather than `findings`: a criterion that produces no findings still ran,
    and the count that matters here is how many specialists were dispatched.
    """
    narrowed = LoadedCase(
        manifest=_manifest(case, requested_analyses=(DecisionDomain.SUITABILITY,)),
        spans=case.spans,
        root=case.root,
    )
    expected = len(criteria_for(narrowed.manifest))
    assert expected < len(CATALOG)  # otherwise this test proves nothing

    for name, orchestrator in ORCHESTRATORS.items():
        result = orchestrator.run(narrowed, _gateway(_finding()), RUN_ID)
        assert len(result.outcomes) == expected, f"{name} fanned out to the wrong width"
        assert result.criteria == criteria_for(narrowed.manifest)


def test_a_case_with_no_applicable_criteria_raises(case) -> None:
    """Better than a successful run that analysed nothing.

    An empty selection would complete, emit no findings, and be indistinguishable from a case where
    every criterion came back clean — the one confusion this system can least afford.
    """
    with pytest.raises(NoApplicableCriteriaError, match="no criterion matching both"):
        criteria_for(_manifest(case, policy_pack_ids=("some-pack-we-do-not-have",)))


# ---------------------------------------------------------------------------
# The shell rejects what it should
# ---------------------------------------------------------------------------


def test_unresolvable_citation_drops_the_finding(case) -> None:
    """Evidence before inference. A citation that does not resolve is not trimmed — it is fatal.

    Trimming would leave an observation standing on evidence nobody can open, which is precisely
    the failure this architecture exists to prevent.
    """
    outcome = analyze(
        CATALOG[0], case, _gateway(_finding(supporting_evidence=["ev_001", "ev_999"])), RUN_ID
    )
    assert outcome.findings == ()
    assert any("ev_999" in reason for reason in outcome.rejected)


def test_determinative_language_is_rejected_by_the_contract(case) -> None:
    """The prompt asks; the type enforces.

    ADR-022 removed the in-run review gate, so `reject_determinative_language` and the
    `ProposedFinding` type now carry the decision-support boundary alone. This is that guard
    firing on text the prompt explicitly asked the model not to write.
    """
    outcome = analyze(
        CATALOG[0],
        case,
        _gateway(
            _finding(
                policy_relevance="The record shows the subject violated SEAD-4 Guideline B.",
            )
        ),
        RUN_ID,
    )
    assert outcome.findings == ()
    assert any("rejected by contract" in reason for reason in outcome.rejected)


def test_a_span_cited_in_both_roles_is_demoted_and_recorded(case) -> None:
    """Observed behaviour, resolved deterministically rather than by dropping a good finding.

    Supporting wins because it is the basis of the observation, and the adjustment is written
    into the rejection record so it is visible rather than silent.
    """
    outcome = analyze(
        CATALOG[0],
        case,
        _gateway(_finding(supporting_evidence=["ev_001"], mitigating_evidence=["ev_001"])),
        RUN_ID,
    )
    assert len(outcome.findings) == 1
    assert outcome.findings[0].mitigating_evidence == ()
    assert any("one role per finding" in reason for reason in outcome.rejected)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="not-json"),
        pytest.param('{"findings": [42]}', id="a-number-where-a-finding-goes"),
        pytest.param('{"answer": "no"}', id="no-findings-key"),
        pytest.param('{"findings": "[{\\"title\\": \\"x\\"}]"}', id="a-string-holding-a-stub"),
    ],
)
def test_malformed_model_output_never_crashes_the_shell(case, payload: str) -> None:
    """A requested schema is verified, not trusted (ADR-018).

    Every shape here has been returned by a real model against this exact schema. None of them
    may take the run down: a specialist that crashes loses the other specialists' work too. Each
    one must also leave a reason behind — a silently empty result is indistinguishable from a
    clean analysis, which is the worst outcome this system can produce.
    """
    outcome = analyze(CATALOG[0], case, StubGateway(default=payload), RUN_ID, attempts=1)
    assert outcome.findings == ()
    assert outcome.rejected  # rejected with a reason, not silently empty


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param('{"findings": "[]"}', 0, id="empty-array-as-a-string"),
        pytest.param(None, 1, id="a-bare-object-where-an-array-was-asked-for"),
        pytest.param("NESTED", 1, id="the-envelope-repeated-inside-itself"),
        pytest.param("NESTED_EMPTY", 0, id="a-nested-empty-array-is-genuinely-empty"),
    ],
)
def test_the_two_observed_shape_coercions(case, payload: str | None, expected: int) -> None:
    """`findings` comes back as a JSON string or a bare object roughly one call in three.

    Both are recoverable without guessing at content, so both are coerced rather than rejected —
    and neither is an error, which is why they are tested apart from the malformed shapes above.
    An empty array stays empty: "the record shows nothing relevant" is a valid answer, and
    manufacturing a rejection for it would be as wrong as manufacturing a finding.
    """
    if payload == "NESTED":
        # {"findings": {"findings": [ ... ]}} — observed live 2026-08-12. The old coercion wrapped
        # this instead of unwrapping it and reported "missing every required field".
        text = json.dumps({"findings": {"findings": [_finding()]}})
    elif payload == "NESTED_EMPTY":
        text = json.dumps({"findings": {"findings": []}})
    elif payload is None:
        text = json.dumps({"findings": _finding()})
    else:
        text = payload
    outcome = analyze(CATALOG[0], case, StubGateway(default=text), RUN_ID, attempts=1)
    assert len(outcome.findings) == expected


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_envelope_is_machine_generated_and_unreviewed(case) -> None:
    """ADR-022: iReports emits proposals and records no human decision, ever."""
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(_finding()), RUN_ID)
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


def test_handler_returns_an_envelope(monkeypatch) -> None:
    """The whole path, offline: event in, validated envelope out."""
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway", lambda *a, **k: _gateway(_finding()), raising=True
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["run_id"] == RUN_ID
    assert payload["findings"] == len(CATALOG)  # this case selects the whole catalog
    assert ASAPEnvelope.model_validate(payload["envelope"])


def test_handler_reports_an_empty_run_rather_than_crashing(monkeypatch) -> None:
    """A run where nothing survives validation still has to return its rejection record.

    That record is the only explanation of *why* nothing survived. Raising here would discard it
    and, under Lambda, trigger an automatic retry that pays for the same model calls again.
    """
    monkeypatch.setattr(handler_module, "CASES_DIR", CASE_DIR.parent)
    monkeypatch.setattr(
        "ireports_gateway.build_gateway",
        lambda *a, **k: _gateway(_finding(supporting_evidence=["ev_999"])),
        raising=True,
    )

    payload = handler_module.handler({"case_id": CASE_DIR.name, "run_id": RUN_ID})

    assert payload["envelope"] is None
    assert "no findings survived" in payload["envelope_error"]
    assert payload["rejected"]
