"""What `packages/orchestration/` claims, checked offline.

Everything here runs against `StubGateway`, so the whole file is free, deterministic, and safe in
CI. The live half — real model calls through a real LiteLLM proxy — is
`spikes/lambda_demo/run_case.py`, which is opt-in and costs money. The split is deliberate: what
these tests assert is that the **deterministic shell** behaves, and the shell is exactly the part
that must not depend on what a model happened to return.

The rejection tests are the important ones. Each feeds the pipeline a response a real model has
actually produced — an unresolvable citation, a determinative conclusion, a span cited in two
roles at once — and asserts the finding does not survive. `CLAUDE.md`: the model reasons; it does
not decide whether its own output is valid.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from ireports_domain import (
    CaseManifest,
    DecisionDomain,
    FindingClassification,
    SpecialistResult,
)
from ireports_gateway import ModelRefusalError, StubGateway
from ireports_orchestration import (
    CATALOG,
    MAX_REJECTIONS,
    ORCHESTRATORS,
    EvidenceSpan,
    LoadedCase,
    NoApplicableCriteriaError,
    SpecialistStatus,
    analyze,
    cap_rejections,
    criteria_for,
    normalize_array,
)
from ireports_retrieval import InMemoryRetriever, RetrievedSpan

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE = REPO_ROOT / "packages" / "orchestration" / "src" / "ireports_orchestration"

CASE_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "cases" / "AMI-SYN-FIN-001"
"""**The case fixtures live in the spike and are read from there on purpose.**

They are the same synthetic corpus `build.py` stages into a Lambda package and `index_cases.py`
loads into OpenSearch. A second copy under `tests/` would be a second corpus, and two corpora
drift. When ingestion lands (Phase 3) the cases move once, and this constant follows them.
"""

RUN_ID = "run_test_0001"

FRAMEWORK_AWARE = {"langgraph_adapter.py", "registry.py"}
"""The only two modules permitted to name a framework.

`langgraph_adapter.py` is the adapter itself. `registry.py` names both adapters and their keys,
which is one import line and a dict — kept in its own module precisely so this exemption stays two
files long rather than growing into a list of special cases.
"""


@pytest.fixture
def case() -> LoadedCase:
    """The corpus, read straight off disk.

    **Deliberately not `lambda_demo.case_loader.load_case`.** That function is the spike's, and a
    package's tests importing a spike inverts the dependency the graduation just established — it
    would also drag an unchecked module into a `mypy --strict` tree. Ten lines of `json.loads` is
    the cheaper price. The loader's own behaviour (missing files, duplicate ids) is tested where
    it lives, in `spikes/lambda_demo/test_demo.py`.
    """
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


IMPORTS_LANGGRAPH = re.compile(r"^\s*(?:from|import)\s+langgraph\b", re.MULTILINE)
"""An `import` statement anywhere in the source, at any indentation.

Deliberately a **source** scan rather than an import check on the loaded module: the adapter
imports LangGraph lazily inside `run()`, so a specialist that did the same would not fail at
collection time either. The indentation-tolerant pattern is what makes a lazy import inside a
function as visible as a top-level one.

It matches import statements rather than the bare word, because these modules legitimately *talk*
about LangGraph — the whole point of ADR-024 is documenting where the two paths diverge, and a
scan that forbade naming the framework would forbid explaining it.
"""


def test_no_analysis_module_imports_langgraph() -> None:
    """ADR-012 chose LangGraph; this is what keeps that from becoming lock-in.

    Scans every module in the package rather than a hand-written list. The list is how this test
    quietly stops covering a new module — the previous version named three files, and any fourth
    was unchecked from the day it landed.
    """
    modules = sorted(p for p in PACKAGE.glob("*.py") if p.name not in FRAMEWORK_AWARE)
    assert len(modules) >= 5, "the scan found almost nothing; the package layout moved"

    for module in modules:
        assert not IMPORTS_LANGGRAPH.search(module.read_text()), (
            f"{module.name} imports LangGraph. Nodes depend on our port, never on the "
            "framework — that is the whole protection against ADR-012 becoming lock-in."
        )


def test_the_import_scan_catches_a_lazy_import() -> None:
    """The negative control. A pattern that matches nothing passes every file.

    The lazy form is the one that matters: it is how the adapter imports the framework, and it is
    what an import check on the loaded module would miss entirely.
    """
    assert IMPORTS_LANGGRAPH.search("def run(self):\n    from langgraph.graph import START\n")
    assert IMPORTS_LANGGRAPH.search("import langgraph\n")
    assert not IMPORTS_LANGGRAPH.search("# see langgraph_adapter.py for the other path\n")


def test_the_framework_aware_modules_still_exist() -> None:
    """A rename would empty the exemption list and leave the scan above passing vacuously."""
    for name in FRAMEWORK_AWARE:
        assert (PACKAGE / name).exists(), f"{name} moved; the exemption above now guards nothing"


def test_both_orchestrators_produce_the_same_findings(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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
# The published contract (CONT-01)
# ---------------------------------------------------------------------------


def test_a_specialist_returns_the_published_contract(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """SPEC-01: "the result is a typed `SpecialistResult`, not prose."

    The demo carried a local dataclass with a bare tuple of findings. Returning the published
    contract is not bookkeeping — constructing it re-checks that every finding's run id, case id,
    and authority agree with the criterion the sub-call was pointed at, which nothing did before.
    """
    outcome = analyze(CATALOG[0], case, _gateway(_finding()), retriever, RUN_ID)

    assert isinstance(outcome.result, SpecialistResult)
    assert outcome.result.run_id == RUN_ID
    assert outcome.result.case_id == case.manifest.case_id
    assert outcome.result.criterion.criterion_id == CATALOG[0].criterion_id
    assert outcome.result.criterion.decision_domain is CATALOG[0].decision_domain
    # The outcome's `findings` is the contract's, not a second copy that could disagree with it.
    assert outcome.findings is outcome.result.findings


def test_a_criterion_that_was_not_analysed_still_says_what_was_checked(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """D-05, and the whole reason CONT-01 wraps findings rather than returning a bare list.

    A refused criterion produces a valid result with zero findings that still names the criterion.
    Without the wrapper there would be nothing to name it with, and "nobody analysed Guideline E"
    would be indistinguishable from "Guideline E was never requested."
    """
    refusing = _RefusesOne("candor_specialist", default=json.dumps({"findings": []}))
    candor = next(c for c in CATALOG if c.node_id == "candor_specialist")

    outcome = analyze(candor, case, refusing, retriever, RUN_ID)

    assert outcome.status is SpecialistStatus.REFUSED
    assert outcome.result.findings == ()
    assert outcome.result.criterion.criterion_id == candor.criterion_id


def test_the_contract_carries_no_completion_status(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """ADR-021 §2, asserted rather than trusted to prose.

    Completion status lives on the local `SpecialistOutcome`, never on `SpecialistResult`. The
    consequence is real and deliberate: a reviewer reading an envelope in ASAP cannot tell a
    refused criterion from a clean one. Closing that gap means superseding ADR-021 on purpose, and
    this test is what makes doing it by accident impossible.
    """
    outcome = analyze(CATALOG[0], case, _gateway(_finding()), retriever, RUN_ID)
    fields = set(type(outcome.result).model_fields)

    assert "status" not in fields
    assert not fields & {"completed", "refused", "complete", "outcome", "analysed"}
    assert outcome.status is SpecialistStatus.COMPLETED  # it is on the wrapper, where it belongs


# ---------------------------------------------------------------------------
# The fan-out width comes from the case
# ---------------------------------------------------------------------------


def _manifest(case: LoadedCase, **overrides: Any) -> CaseManifest:
    return case.manifest.model_copy(update=overrides)


def test_criteria_come_from_the_case_not_a_constant(case: LoadedCase) -> None:
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


def test_both_orchestrators_fan_out_to_the_width_the_case_asks_for(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_a_case_with_no_applicable_criteria_raises(case: LoadedCase) -> None:
    """Better than a successful run that analysed nothing.

    An empty selection would complete, emit no findings, and be indistinguishable from a case where
    every criterion came back clean — the one confusion this system can least afford.
    """
    with pytest.raises(NoApplicableCriteriaError, match="no criterion matching both"):
        criteria_for(_manifest(case, policy_pack_ids=("some-pack-we-do-not-have",)))


# ---------------------------------------------------------------------------
# The shell rejects what it should
# ---------------------------------------------------------------------------


def test_unresolvable_citation_drops_the_finding(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_determinative_language_is_rejected_by_the_contract(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_a_span_cited_in_both_roles_is_demoted_and_recorded(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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
def test_malformed_model_output_never_crashes_the_shell(
    case: LoadedCase, payload: str, retriever: InMemoryRetriever
) -> None:
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
    case: LoadedCase, payload: str | None, expected: int, retriever: InMemoryRetriever
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
# Synthesis — the second stage
# ---------------------------------------------------------------------------


def _synth_gateway(
    contradictions: Sequence[dict[str, Any]] = (),
    gaps: Sequence[dict[str, Any]] = (),
    findings: dict[str, Any] | None = None,
) -> StubGateway:
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


def test_overlap_is_computed_not_inferred(case: LoadedCase, retriever: InMemoryRetriever) -> None:
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


def test_a_synthesis_contradiction_splits_its_cited_spans_by_role(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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
    case: LoadedCase,
    override: dict[str, Any],
    expected: str,
    retriever: InMemoryRetriever,
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


def test_both_orchestrators_synthesize_identically(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_one_refusal_does_not_kill_the_run(case: LoadedCase, retriever: InMemoryRetriever) -> None:
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


def test_a_refused_criterion_is_not_a_clean_one(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_a_refusal_is_not_retried(case: LoadedCase, retriever: InMemoryRetriever) -> None:
    """ADR-015: a refusal is not a transport failure and must not be retried blindly."""
    gateway = _RefusesOne("candor_specialist", default=json.dumps({"findings": []}))
    ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)
    assert gateway.refusals == 1, "a refused criterion was asked again"


def test_synthesis_runs_once_not_once_per_specialist(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
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


def test_both_paths_skip_synthesis_on_the_same_condition(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """The routing policy is shared code, so the two paths cannot drift.

    If each orchestrator decided this separately, two runs of the same case would produce
    different envelopes for a reason nobody could see.
    """
    for name, orchestrator in ORCHESTRATORS.items():
        gateway = StubGateway(default=json.dumps({"findings": []}))
        result = orchestrator.run(case, gateway, retriever, RUN_ID)
        assert result.synthesis is None, f"{name} ran synthesis with nothing to reason across"
        assert not any(c.node_id == "synthesis" for c in gateway.calls), name


# ---------------------------------------------------------------------------
# Retrieval scoping
# ---------------------------------------------------------------------------


def test_a_citation_to_an_unretrieved_span_is_dropped(case: LoadedCase) -> None:
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


def test_the_run_records_what_each_specialist_was_shown(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """Provenance. Two specialists on one case now read different records.

    "Why did the financial criterion miss this?" is unanswerable without knowing what it was given,
    and the answer is often that retrieval never surfaced the span.
    """
    result = ORCHESTRATORS["hand-rolled"].run(case, _gateway(_finding()), retriever, RUN_ID)
    assert all(o.retrieved for o in result.outcomes if o.analysed)


# ---------------------------------------------------------------------------
# The shape coercion, shared by both stages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["contradictions", "information_gaps"])
def test_a_synthesis_array_returned_as_a_json_string_is_parsed(
    case: LoadedCase, retriever: InMemoryRetriever, key: str
) -> None:
    """The bug the first post-graduation live run found, pinned.

    The model returned synthesis's arrays as JSON **strings**. The loop enumerated the string
    character by character, producing one rejection per character — 4,547 across the two arrays,
    zero findings, no error, on **both** orchestrators. The specialist path handled the identical
    shape correctly on the same run, because the coercion lived in a private helper there.

    Asserted per array, because fixing one and not the other is precisely how this happened.
    """
    # One array arrives as a JSON string, the other as a real array — so this isolates the
    # coercion to one field at a time, which is the shape the bug had.
    other = "contradictions" if key == "information_gaps" else "information_gaps"
    payload: dict[str, Any] = {
        key: json.dumps([_contradiction()] if key == "contradictions" else []),
        other: [],
    }

    gateway = StubGateway(
        responses={"synthesis": json.dumps(payload)},
        default=json.dumps({"findings": [_finding()]}),
    )
    result = ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)

    assert result.synthesis is not None
    # The give-away is the *count*: one rejection per character is the signature of the bug.
    assert len(result.synthesis.rejected) < 5, result.synthesis.rejected[:5]
    if key == "contradictions":
        assert len(result.synthesis.findings) == 1


def test_an_uncoercible_synthesis_array_is_named_once_not_per_character(
    case: LoadedCase, retriever: InMemoryRetriever
) -> None:
    """A shape that genuinely cannot be coerced gets **one** rejection naming what it was.

    Not one per element of whatever happened to be iterable. "The response was a str" is the fact
    that explains the run; four thousand copies of "not an object" is the fact that hides it.
    """
    gateway = StubGateway(
        responses={
            "synthesis": json.dumps(
                {"contradictions": "this is prose, not JSON at all", "information_gaps": []}
            )
        },
        default=json.dumps({"findings": [_finding()]}),
    )
    result = ORCHESTRATORS["hand-rolled"].run(case, gateway, retriever, RUN_ID)

    assert result.synthesis is not None
    assert len(result.synthesis.rejected) == 1
    assert "could not be coerced" in result.synthesis.rejected[0]


def test_a_pathological_rejection_count_is_capped_and_says_so() -> None:
    """Rejections are output, and output has to stay readable to be worth anything.

    The live run put 4,547 rejection strings into the envelope's accounting payload, burying the
    two that mattered. A cap plus an honest count beats both an unbounded list and a silent
    truncation — a reader must be able to tell "three were dropped" from "four thousand were, and
    you are seeing fifty."
    """
    capped = cap_rejections([f"reason {i}" for i in range(4547)])

    assert len(capped) == MAX_REJECTIONS + 1
    assert capped[-1].startswith("... and 4497 more")
    assert "4547 in total" in capped[-1]
    # Under the cap, nothing is added — the summary line must not appear on a healthy run.
    assert cap_rejections(["one", "two"]) == ("one", "two")


@pytest.mark.parametrize(
    ("raw", "key", "expected"),
    [
        pytest.param([{"a": 1}], "findings", [{"a": 1}], id="already-a-list"),
        pytest.param('[{"a": 1}]', "findings", [{"a": 1}], id="the-array-as-a-json-string"),
        pytest.param({"a": 1}, "findings", [{"a": 1}], id="a-bare-object"),
        pytest.param({"findings": [{"a": 1}]}, "findings", [{"a": 1}], id="envelope-repeated"),
        pytest.param({"findings": []}, "findings", [], id="a-nested-empty-array-stays-empty"),
        pytest.param("prose", "findings", None, id="uncoercible-returns-none-not-empty"),
        pytest.param(
            {"findings": [], "title": "x"},
            "findings",
            [{"findings": [], "title": "x"}],
            id="ambiguous-dict-is-wrapped-not-unwrapped",
        ),
    ],
)
def test_normalize_array_coerces_only_the_documented_shapes(
    raw: Any, key: str, expected: Any
) -> None:
    """**Uncoercible returns `None`, never `[]`.**

    Returning an empty list on failure would turn an unparseable response into a clean empty one,
    which is the silent under-analysis this whole architecture is built against. The caller has to
    be able to tell "the model found nothing" from "the model said something I could not read."
    """
    assert normalize_array(raw, key) == expected
