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
from ireports_domain import ASAPEnvelope, DecisionDomain, FindingClassification
from ireports_gateway import ModelRefusalError, StubGateway
from ireports_retrieval import InMemoryRetriever, RetrievedSpan
from lambda_demo import handler as handler_module
from lambda_demo.case_loader import LoadedCase, load_case
from lambda_demo.criteria import CATALOG, NoApplicableCriteriaError, criteria_for
from lambda_demo.orchestrator import ORCHESTRATORS
from lambda_demo.package import build_envelope
from lambda_demo.specialist import SpecialistStatus, analyze

CASE_DIR = Path(__file__).parent / "cases" / "AMI-SYN-FIN-001"
RUN_ID = "run_test_0001"


@pytest.fixture
def case():
    return load_case(CASE_DIR)


@pytest.fixture
def retriever(case):
    """Every span, ignoring the query.

    **Not a retriever, and no test here may claim otherwise.** It returns the whole case, which is
    exactly the behaviour retrieval replaced — so it keeps orchestration tests offline and free,
    and proves nothing about relevance. Retrieval behaviour is tested in `tests/retrieval/`,
    against a real cluster.
    """
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


def test_both_orchestrators_produce_the_same_findings(case, retriever) -> None:
    """Same case, same stub, two orchestrators, identical output.

    With a real model the two candidates return different analyses — they are two runs of a
    probabilistic process, not two evaluations of a function. Pinning the model response is what
    turns "similar" into "identical" and makes the port's claim checkable at all.
    """
    results = {
        name: orchestrator.run(case, _gateway(_finding()), retriever, RUN_ID)
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


def test_both_orchestrators_fan_out_to_the_width_the_case_asks_for(case, retriever) -> None:
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
        result = orchestrator.run(narrowed, _gateway(_finding()), retriever, RUN_ID)
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


def test_unresolvable_citation_drops_the_finding(case, retriever) -> None:
    """Evidence before inference. A citation that does not resolve is not trimmed — it is fatal.

    Trimming would leave an observation standing on evidence nobody can open, which is precisely
    the failure this architecture exists to prevent.
    """
    outcome = analyze(
        CATALOG[0],
        case,
        _gateway(_finding(supporting_evidence=["ev_001", "ev_999"])),
        retriever,
        RUN_ID,
    )
    assert outcome.findings == ()
    assert any("ev_999" in reason for reason in outcome.rejected)


def test_determinative_language_is_rejected_by_the_contract(case, retriever) -> None:
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
        retriever,
        RUN_ID,
    )
    assert outcome.findings == ()
    assert any("rejected by contract" in reason for reason in outcome.rejected)


def test_a_span_cited_in_both_roles_is_demoted_and_recorded(case, retriever) -> None:
    """Observed behaviour, resolved deterministically rather than by dropping a good finding.

    Supporting wins because it is the basis of the observation, and the adjustment is written
    into the rejection record so it is visible rather than silent.
    """
    outcome = analyze(
        CATALOG[0],
        case,
        _gateway(_finding(supporting_evidence=["ev_001"], mitigating_evidence=["ev_001"])),
        retriever,
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
def test_malformed_model_output_never_crashes_the_shell(case, payload: str, retriever) -> None:
    """A requested schema is verified, not trusted (ADR-018).

    Every shape here has been returned by a real model against this exact schema. None of them
    may take the run down: a specialist that crashes loses the other specialists' work too. Each
    one must also leave a reason behind — a silently empty result is indistinguishable from a
    clean analysis, which is the worst outcome this system can produce.
    """
    outcome = analyze(CATALOG[0], case, StubGateway(default=payload), retriever, RUN_ID, attempts=1)
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
def test_the_two_observed_shape_coercions(
    case, payload: str | None, expected: int, retriever
) -> None:
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
    outcome = analyze(CATALOG[0], case, StubGateway(default=text), retriever, RUN_ID, attempts=1)
    assert len(outcome.findings) == expected


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
# Synthesis — the second stage
# ---------------------------------------------------------------------------


def _synth_gateway(contradictions=(), gaps=(), findings=None) -> StubGateway:
    """A stub that answers specialists and the synthesis node differently.

    Keyed on `node_id`, which is what makes this possible at all: the synthesis node asks a
    different question and gets a different schema back, and a single canned response could not
    stand in for both.
    """
    return StubGateway(
        responses={
            "synthesis": json.dumps(
                {"contradictions": list(contradictions), "information_gaps": list(gaps)}
            )
        },
        default=json.dumps({"findings": [findings or _finding()]}),
    )


def _contradiction(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "SF-86 answer conflicts with the interview disclosure",
        "observation": "The questionnaire records 'No' (ev_003); the interview records a 4 percent"
        " interest (ev_004). Both cannot describe the same holding.",
        "policy_relevance": "The conflict may be relevant to what the record establishes.",
        "recommended_officer_action": "Review both statements and resolve which is accurate.",
        "criterion_id": "731-202-B-3",
        "conflicting_evidence": ["ev_003", "ev_004"],
    }
    base.update(overrides)
    return base


def test_overlap_is_computed_not_inferred(case, retriever) -> None:
    """The most useful thing the fan-in produces, and it costs nothing.

    Which findings rest on the same span is set arithmetic. Asking a model would be slower, cost
    money, and be occasionally wrong about something with an exact answer.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _synth_gateway(), retriever, RUN_ID)
    assert result.synthesis is not None

    # The stub gives every criterion the same finding on ev_001, so ev_001 spans every criterion.
    found = {o.evidence_id: o for o in result.synthesis.overlaps}
    assert "ev_001" in found
    assert len(found["ev_001"].criterion_ids) == len(result.criteria) > 1


def test_synthesis_findings_reach_the_envelope(case, retriever) -> None:
    result = ORCHESTRATORS["hand-rolled"].run(
        case, _synth_gateway(contradictions=[_contradiction()]), retriever, RUN_ID
    )
    contradictions = [
        f for f in result.findings if f.classification is FindingClassification.CONTRADICTION
    ]
    assert len(contradictions) == 1
    # First span is the assertion, the rest are what conflicts with it — the contract counts
    # supporting + contradicting >= 2.
    assert contradictions[0].supporting_evidence == ("ev_003",)
    assert contradictions[0].contradicting_evidence == ("ev_004",)
    assert ASAPEnvelope.model_validate(
        build_envelope(case, result.findings, RUN_ID).model_dump(mode="json")
    )


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        pytest.param(
            {"conflicting_evidence": ["ev_003"]}, "needs two conflicting spans", id="one-span"
        ),
        pytest.param(
            {"conflicting_evidence": ["ev_003", "ev_999"]},
            "cited unknown evidence",
            id="unknown-span",
        ),
        pytest.param(
            {"criterion_id": "GUIDELINE-Z"}, "which was not analysed", id="uninvolved-criterion"
        ),
    ],
)
def test_synthesis_is_validated_like_everything_else(
    case, override, expected: str, retriever
) -> None:
    """The second stage gets no more trust than the first.

    A contradiction naming a criterion nobody analysed, or resting on one span, or citing evidence
    that is not in the case, is dropped with a reason — same shell, same rules.
    """
    result = ORCHESTRATORS["hand-rolled"].run(
        case, _synth_gateway(contradictions=[_contradiction(**override)]), retriever, RUN_ID
    )
    assert result.synthesis is not None
    assert not result.synthesis.findings
    assert any(expected in reason for reason in result.synthesis.rejected)


def test_both_orchestrators_synthesize_identically(case, retriever) -> None:
    """The second stage is a real graph edge in one and a second statement in the other."""
    shapes = {}
    for name, orchestrator in ORCHESTRATORS.items():
        result = orchestrator.run(
            case, _synth_gateway(contradictions=[_contradiction()]), retriever, RUN_ID
        )
        assert result.synthesis is not None, name
        shapes[name] = (
            [f.finding_id for f in result.synthesis.findings],
            [(o.evidence_id, o.criterion_ids) for o in result.synthesis.overlaps],
        )
    assert shapes["hand-rolled"] == shapes["langgraph"]


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------


class _RefusesOne(StubGateway):
    """Refuses one named criterion. Every other criterion would succeed."""

    def __init__(self, node_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._refuse = node_id
        self.refusals = 0
        """Counted here rather than read from `gateway.calls`: this raises *before* delegating,
        so a refused attempt never reaches the stub's own call log."""

    def complete(self, request):  # type: ignore[no-untyped-def]
        if request.node_id == self._refuse:
            self.refusals += 1
            raise ModelRefusalError(category="sensitive_content")
        return super().complete(request)


def test_one_refusal_does_not_kill_the_run(case, retriever) -> None:
    """Regression. Until 2026-08-12 it did, on both paths.

    `gateway.complete` was called bare, so a refusal raised through the thread pool or the graph
    and discarded every other specialist's completed, already-paid-for work. Under Lambda that is
    worse: the invocation is retried automatically and every model call is paid for again, into
    the same refusal.
    """
    for name, orchestrator in ORCHESTRATORS.items():
        result = orchestrator.run(
            case,
            _RefusesOne("candor_specialist", default=json.dumps({"findings": [_finding()]})),
            retriever,
            RUN_ID,
        )
        assert len(result.outcomes) == len(result.criteria), name
        assert result.findings, f"{name} lost the surviving specialists' work"


def test_a_refused_criterion_is_not_a_clean_one(case, retriever) -> None:
    """The distinction the architecture exists to protect.

    A criterion nobody could analyse and a criterion that came back clean both have zero findings.
    If they look the same, the run reports silent under-analysis as a clean record.
    """
    result = ORCHESTRATORS["hand-rolled"].run(
        case,
        _RefusesOne("candor_specialist", default=json.dumps({"findings": [_finding()]})),
        retriever,
        RUN_ID,
    )
    by_node = {o.criterion.node_id: o for o in result.outcomes}

    refused = by_node["candor_specialist"]
    assert refused.status is SpecialistStatus.REFUSED
    assert not refused.analysed
    assert any("NOT analysed" in reason for reason in refused.rejected)

    # And a criterion that genuinely found nothing is still COMPLETED, not conflated with it.
    clean = ORCHESTRATORS["hand-rolled"].run(
        case, StubGateway(default=json.dumps({"findings": []})), retriever, RUN_ID
    )
    assert all(o.status is SpecialistStatus.COMPLETED for o in clean.outcomes)
    assert all(o.analysed for o in clean.outcomes)


def test_a_refusal_is_not_retried(case, retriever) -> None:
    """ADR-015: a refusal is not a transport failure and must not be retried blindly."""
    gateway = _RefusesOne("candor_specialist", default=json.dumps({"findings": []}))
    ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)
    assert gateway.refusals == 1, "a refused criterion was asked again"


def test_synthesis_runs_once_not_once_per_specialist(case, retriever) -> None:
    """The trap that cost a `join` node, and would have been silent.

    A conditional edge leaving a `Send`-dispatched node fires **once per dispatch**, and each
    firing sees only that dispatch's own state contribution. Measured directly: five dispatches
    gave five router calls, each seeing one outcome, never five. Routing on the aggregate of a
    fan-out therefore has to happen after an explicit join, or every branch decides on a run that
    does not exist.

    No error, no warning — just a decision made on one-fifth of the evidence.
    """
    for name, orchestrator in ORCHESTRATORS.items():
        gateway = StubGateway(
            responses={"synthesis": json.dumps({"contradictions": [], "information_gaps": []})},
            default=json.dumps({"findings": [_finding()]}),
        )
        orchestrator.run(case, gateway, retriever, RUN_ID)
        calls = [c for c in gateway.calls if c.node_id == "synthesis"]
        assert len(calls) == 1, f"{name} ran synthesis {len(calls)} times"


def test_both_paths_skip_synthesis_on_the_same_condition(case, retriever) -> None:
    """The routing policy is shared code, so the two paths cannot drift.

    If each orchestrator decided this separately, two runs of the same case would produce
    different envelopes for a reason nobody could see.
    """
    for name, orchestrator in ORCHESTRATORS.items():
        gateway = StubGateway(default=json.dumps({"findings": []}))
        result = orchestrator.run(case, gateway, retriever, RUN_ID)
        assert result.synthesis is None, f"{name} ran synthesis with nothing to reason across"
        assert not any(c.node_id == "synthesis" for c in gateway.calls), name


def test_a_citation_to_an_unretrieved_span_is_dropped(case) -> None:
    """Citations are checked against what the specialist was **shown**, not what the case holds.

    With retrieval these differ, and the distinction is the whole point. A model that cites a span
    it was never given has not recalled the record — it has guessed, and a guess that happens to
    name a real evidence id is indistinguishable from analysis unless this check is scoped to the
    retrieved set.

    Here the case contains ev_002 and retrieval deliberately does not surface it.
    """
    shown = InMemoryRetriever(
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
            if s.evidence_id == "ev_001"
        )
    )
    assert any(s.evidence_id == "ev_002" for s in case.spans), "fixture no longer proves anything"

    outcome = analyze(
        CATALOG[0],
        case,
        _gateway(_finding(supporting_evidence=["ev_002"])),
        shown,
        RUN_ID,
        attempts=1,
    )
    assert outcome.findings == ()
    assert any("ev_002" in reason for reason in outcome.rejected)
    assert outcome.retrieved == ("ev_001",)


def test_the_run_records_what_each_specialist_was_shown(case, retriever) -> None:
    """Provenance. Two specialists on one case now read different records.

    "Why did the financial criterion miss this?" is unanswerable without knowing what it was given,
    and the answer is often that retrieval never surfaced the span.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(_finding()), retriever, RUN_ID)
    assert all(o.retrieved for o in result.outcomes if o.analysed)
