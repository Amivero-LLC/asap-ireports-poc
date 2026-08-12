"""The decision-support boundary, asserted against the contracts.

`CLAUDE.md` states the boundary as non-negotiable and lists concrete constraints on the code.
This module turns each of those constraints into a test, so that a change which reopens one
fails here rather than in a review someone might not do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, get_args, get_origin

import pytest
from ireports_domain import (
    ROOT_CONTRACTS,
    ASAPEnvelope,
    Confidence,
    DecisionDomain,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    ModelAlias,
    ProposedFinding,
    RunStatus,
    SpecialistCriterion,
    SpecialistResult,
    ValidationOutcome,
    reject_determinative_language,
)
from ireports_domain.run import LEGAL_TRANSITIONS
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ADR-014 — no universal person-risk score
# ---------------------------------------------------------------------------

FORBIDDEN_FIELD_SUBSTRINGS = (
    "risk_score",
    "risk_level",
    "risk_rating",
    "overall_score",
    "overall_rating",
    "overall_risk",
    "composite_score",
    "aggregate_score",
    "total_score",
    "suitability_score",
    "trust_score",
    "threat_score",
    "person_score",
    "final_recommendation",
    "overall_recommendation",
    "adjudicative_recommendation",
    "determination",
)
"""Field names that would function as an aggregate score, whatever they are named.

`CLAUDE.md`: "Schema review must reject any field that functions as an aggregate score, whatever
it is named." A human reviewer cannot be relied on to catch this every time, so the check is
mechanical. Note the deliberate exception below for `position_risk_level`, which is a *position*
designation under 5 CFR 731 — a property of the job, set by the agency before any analysis — and
not an assessment of the person.
"""

ALLOWED_EXCEPTIONS = frozenset({"position_risk_level"})


def _walk_property_names(schema: dict[str, Any], defs: dict[str, Any]) -> set[str]:
    """Collect every property name reachable from a schema, following $defs."""
    seen_defs: set[str] = set()
    names: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                key = ref.removeprefix("#/$defs/")
                if key not in seen_defs:
                    seen_defs.add(key)
                    visit(defs.get(key, {}))
            props = node.get("properties")
            if isinstance(props, dict):
                names.update(props.keys())
                for value in props.values():
                    visit(value)
            for key, value in node.items():
                if key not in ("properties", "$ref"):
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(schema)
    return names


@pytest.mark.parametrize("stem,model", sorted(ROOT_CONTRACTS.items()))
def test_no_contract_carries_an_aggregate_score(stem: str, model: type[BaseModel]) -> None:
    schema = model.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    offenders = {
        name
        for name in names
        if name not in ALLOWED_EXCEPTIONS
        and any(bad in name.lower() for bad in FORBIDDEN_FIELD_SUBSTRINGS)
    }
    assert not offenders, (
        f"contract {stem!r} carries field(s) {sorted(offenders)} that function as an aggregate "
        f"score or a determination. ADR-014 forbids this in any contract, under any name."
    )


def test_the_guard_actually_catches_something() -> None:
    """A guard that cannot fail is not a guard.

    Without this, a refactor that broke `_walk_property_names` would leave every ADR-014 test
    passing vacuously.
    """
    schema: dict[str, Any] = {
        "properties": {"harmless": {}, "subject_risk_score": {}},
        "$defs": {},
    }
    names = _walk_property_names(schema, {})
    offenders = {n for n in names if any(bad in n.lower() for bad in FORBIDDEN_FIELD_SUBSTRINGS)}
    assert offenders == {"subject_risk_score"}


def test_guard_reaches_nested_definitions() -> None:
    """The walk must follow $defs, or nested contracts go unchecked."""
    schema: dict[str, Any] = {
        "properties": {"nested": {"$ref": "#/$defs/Inner"}},
        "$defs": {"Inner": {"properties": {"overall_risk": {}}}},
    }
    names = _walk_property_names(schema, schema["$defs"])
    assert "overall_risk" in names


# ---------------------------------------------------------------------------
# Prohibited language (blueprint §10.4)
# ---------------------------------------------------------------------------

PROHIBITED = [
    "The subject is unsuitable for the position.",
    "The applicant is ineligible for access.",
    "Eligibility should be denied based on this record.",
    "The clearance should be revoked.",
    "The subject violated SEAD-4 Guideline B.",
    "The subject is deceptive about the foreign contacts.",
    "The individual will reoffend without intervention.",
    "We recommend denial of the security clearance.",
]

PERMITTED = [
    "The record indicates continuing contact with relatives abroad.",
    "These facts may be relevant to foreign influence and require officer review.",
    "Review the cited records and resolve the two information gaps before disposition.",
    "Mitigating evidence indicates the interest is noncontrolling.",
    "This is a potential issue under the cited criterion.",
    "An information gap remains regarding the frequency of recent contact.",
    # Near-misses. A guard that blocks these is over-broad and would push nodes toward
    # vaguer, less useful language — the record's own history is exactly what a finding
    # is supposed to describe.
    "The record indicates a security clearance was granted in 2019 and renewed in 2024.",
    "The officer should review the cited records; access was granted in 2019 per the record.",
    "The record indicates the prior suspension was administrative and later withdrawn.",
]


@pytest.mark.parametrize("text", PROHIBITED)
def test_determinative_language_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="decision-support boundary"):
        reject_determinative_language(text)


@pytest.mark.parametrize("text", PERMITTED)
def test_decision_support_language_is_accepted(text: str) -> None:
    assert reject_determinative_language(text) == text


def _finding(**overrides: object) -> ProposedFinding:
    base: dict[str, object] = {
        "finding_id": "fnd_01",
        "run_id": "run_01",
        "case_id": "AMI-SYN-MIX-003",
        "authority": FindingAuthority(
            decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
            policy_pack_id="sead4-current",
            policy_id="SEAD-4",
            criterion_id="GUIDELINE-B",
            policy_citations=["pol_sead4_b_12"],
        ),
        "classification": FindingClassification.POTENTIAL_ISSUE,
        "title": "Continuing foreign ties require officer review",
        "observation": "The record describes continuing contact with close relatives abroad.",
        "policy_relevance": "These facts may be relevant to foreign influence.",
        "supporting_evidence": ["ev_101"],
        "evidence_confidence": Confidence.HIGH,
        "analysis_confidence": Confidence.MODERATE,
        "recommended_officer_action": "Review the cited records before disposition.",
        "generated_by": GeneratedBy(
            node="foreign_influence_specialist",
            model_alias=ModelAlias.THINKING,
            prompt_version="foreign-v4",
        ),
        "validation": FindingValidation(
            schema_check=ValidationOutcome.PASSED,
            citations=ValidationOutcome.PASSED,
            policy_effective_date=ValidationOutcome.PASSED,
            protected_attribute_check=ValidationOutcome.PASSED,
            prohibited_language_check=ValidationOutcome.PASSED,
        ),
        "proposed_at": NOW,
    }
    return ProposedFinding(**(base | overrides))


def test_a_finding_cannot_state_a_determination() -> None:
    with pytest.raises(ValidationError, match="decision-support boundary"):
        _finding(observation="The subject is unsuitable for a high risk public trust position.")


def test_a_finding_cannot_recommend_an_adjudicative_action() -> None:
    with pytest.raises(ValidationError, match="decision-support boundary"):
        _finding(recommended_officer_action="Eligibility should be denied.")


def test_a_valid_finding_constructs() -> None:
    finding = _finding()
    assert finding.classification is FindingClassification.POTENTIAL_ISSUE
    assert finding.generated_by.model_alias is ModelAlias.THINKING


# ---------------------------------------------------------------------------
# Evidence before inference
# ---------------------------------------------------------------------------


def test_a_potential_issue_must_cite_evidence() -> None:
    with pytest.raises(ValidationError, match="must cite at least one supporting evidence"):
        _finding(supporting_evidence=[])


def test_a_span_cannot_serve_two_roles() -> None:
    with pytest.raises(ValidationError, match="serves one role"):
        _finding(supporting_evidence=["ev_101"], mitigating_evidence=["ev_101"])


def test_a_finding_must_cite_policy() -> None:
    with pytest.raises(ValidationError):
        FindingAuthority(
            decision_domain=DecisionDomain.SUITABILITY,
            policy_pack_id="federal-core-2026-07-30",
            policy_id="5-CFR-731",
            criterion_id="731.202(b)(4)",
            policy_citations=[],
        )


# ---------------------------------------------------------------------------
# ADR-008 — no hard-coded model IDs
# ---------------------------------------------------------------------------


def test_model_reference_must_be_an_alias() -> None:
    with pytest.raises(ValidationError):
        GeneratedBy(
            node="specialist",
            model_alias="anthropic.claude-sonnet-4-6",
            prompt_version="v1",
        )


def test_the_three_aliases_are_the_whole_set() -> None:
    assert {a.value for a in ModelAlias} == {
        "ireports-orchestrator",
        "ireports-thinking",
        "ireports-fast",
    }


# ---------------------------------------------------------------------------
# ADR-022 — iReports has no human interaction; review happens in ASAP
# ---------------------------------------------------------------------------

REVIEW_FIELD_SUBSTRINGS = (
    "disposition",
    "human_review",
    "human_reviewed",
    "reviewer_modified",
    "approved_by",
    "approval",
    "release_to_asap",
    "signed_off",
)
"""Field names that would mean iReports had modelled the review it does not perform.

ADR-022 puts review in ASAP, after a run finishes. A field here would either be dead weight or —
worse — an invitation for the handoff team to build a reviewer workflow into iReports that belongs
in ASAP. `reviewer_summary` is deliberately absent from this list only because no contract carries
it any more; if one reappears, the substring "reviewer" is not banned outright because
`recommended_officer_action` and `ReviewUrgency` are legitimate: they describe what iReports
proposes *for* a reviewer, not a decision it recorded.
"""


@pytest.mark.parametrize("stem,model", sorted(ROOT_CONTRACTS.items()))
def test_no_contract_models_a_human_decision(stem: str, model: type[BaseModel]) -> None:
    """iReports proposes; it does not record what anyone decided.

    The mirror image of the ADR-014 guard above. That one forbids the system from *making* a
    determination; this one forbids it from *claiming* a human made one.
    """
    schema = model.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    offenders = {
        name for name in names if any(bad in name.lower() for bad in REVIEW_FIELD_SUBSTRINGS)
    }
    assert not offenders, (
        f"contract {stem!r} carries field(s) {sorted(offenders)} that model a human decision. "
        f"ADR-022: review happens in ASAP, after iReports has finished. What an officer decides "
        f"is ASAP's contract to define, not ours to guess at."
    )


def test_no_run_state_waits_for_a_person() -> None:
    """A run must be able to go start to finish unattended.

    Under ADR-011 the state machine deliberately contained a state a run could not leave without
    human action. ADR-022 removed it, because iReports has no reviewer-facing surface at all.
    """
    stalled = {s for s in RunStatus if "review" in s.value or "await" in s.value}
    assert not stalled, (
        f"run states {sorted(s.value for s in stalled)} imply a run waits for a person; "
        f"iReports runs unattended (ADR-022)"
    )


def test_every_state_can_reach_a_terminal_state_unattended() -> None:
    """The property the removed gate would have broken, asserted directly.

    Walking the transition table matters more than checking the enum: a state whose only exit
    needed an out-of-band actor would strand a run without any field-level check noticing.
    """
    terminal = {RunStatus.DELIVERED, RunStatus.FAILED, RunStatus.CANCELLED}
    for start in RunStatus:
        reachable: set[RunStatus] = set()
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for nxt in LEGAL_TRANSITIONS[current]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    frontier.append(nxt)
        assert reachable & terminal or start in terminal, (
            f"{start.value!r} cannot reach a terminal state; a run that starts must be able to "
            f"finish without anyone intervening"
        )


def test_delivery_is_reachable_without_any_human_step() -> None:
    """The positive case: an unattended run can get all the way to DELIVERED."""
    reachable: set[RunStatus] = {RunStatus.INITIALIZING}
    frontier = [RunStatus.INITIALIZING]
    while frontier:
        current = frontier.pop()
        for nxt in LEGAL_TRANSITIONS[current]:
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)
    assert RunStatus.DELIVERED in reachable


def test_budget_exhaustion_still_reaches_a_reviewer() -> None:
    """Blueprint §8.5 survives ADR-022 with a different mechanism.

    The requirement was never that a budget stop pause in-run — it was that a truncated analysis
    stay visible instead of vanishing. It now reaches ASAP by being packaged and delivered like
    any other run, which is why the route is to PACKAGING rather than to FAILED.
    """
    exits = LEGAL_TRANSITIONS[RunStatus.INCOMPLETE_DUE_TO_BUDGET]
    assert RunStatus.PACKAGING in exits
    assert RunStatus.FAILED not in exits


def test_the_envelope_never_claims_to_have_been_reviewed() -> None:
    """An envelope is what gets reviewed, not the product of a review (ADR-022)."""
    schema = ASAPEnvelope.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    assert "human_reviewed" not in names
    assert "machine_generated" in names, (
        "the envelope must still assert positively that it is machine output; removing "
        "human_reviewed without keeping machine_generated would leave its status unstated"
    )


# ---------------------------------------------------------------------------
# ADR-011 — the machine proposal cannot be edited in place
# ---------------------------------------------------------------------------

MUTABLE_ORIGINS = (list, set, dict)
"""Container types whose *contents* stay mutable under Pydantic's `frozen=True`.

`frozen=True` blocks attribute rebinding, not mutation of the object an attribute already
points at. A `list` field on a frozen model is therefore still appendable, which silently
defeats any cross-field validator that ran at construction. `CLAUDE.md` requires that both the
original machine proposal stays exactly as the machine produced it; a contract whose
sequence field can be appended to after validation does not retain the original.

`tuple[X, ...]` serializes to the same JSON Schema (`{"type": "array", ...}`), so this costs
nothing at the boundary — it only removes the mutation path.
"""


def _mutable_container_fields(model: type[BaseModel], seen: set[type] | None = None) -> set[str]:
    """Every `Contract.field` in `model`'s tree whose annotation is a mutable container."""
    seen = set() if seen is None else seen
    if model in seen:
        return set()
    seen.add(model)

    offenders: set[str] = set()

    def inspect(annotation: object, label: str) -> None:
        origin = get_origin(annotation)
        if origin in MUTABLE_ORIGINS:
            offenders.add(label)
            return
        for arg in get_args(annotation):
            inspect(arg, label)
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            offenders.update(_mutable_container_fields(annotation, seen))

    for name, field in model.model_fields.items():
        inspect(field.annotation, f"{model.__name__}.{name}")
    return offenders


@pytest.mark.parametrize("stem,model", sorted(ROOT_CONTRACTS.items()))
def test_no_contract_field_is_a_mutable_container(stem: str, model: type[BaseModel]) -> None:
    offenders = _mutable_container_fields(model)
    assert not offenders, (
        f"contract {stem!r} carries mutable container field(s) {sorted(offenders)}. "
        f"`frozen=True` does not freeze container contents, so these can be mutated after "
        f"validation — defeating ADR-011's guarantee that the machine proposal is retained "
        f"unedited. Use `tuple[X, ...]`, which emits identical JSON Schema."
    )


def test_the_mutability_guard_actually_catches_something() -> None:
    """A guard that cannot fail is not a guard (same reasoning as the ADR-014 control)."""

    class Mutable(BaseModel):
        xs: list[int] = []

    assert _mutable_container_fields(Mutable) == {"Mutable.xs"}


def test_a_validated_result_cannot_be_given_another_cases_finding() -> None:
    """The concrete failure this guard exists to prevent.

    `SpecialistResult._findings_belong_to_this_criterion` rejects a foreign finding at
    construction. Before `findings` became a tuple, appending one afterwards bypassed that
    validator entirely and a case-A result could be made to carry a case-B finding.
    """
    result = SpecialistResult(
        run_id="run_01J9AA",
        case_id="AMI-SYN-MIX-004",
        criterion=SpecialistCriterion(
            decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
            policy_pack_id="sead4-current",
            policy_id="SEAD-4",
            criterion_id="GUIDELINE-B",
        ),
        generated_by=GeneratedBy(
            node="foreign_influence_specialist",
            model_alias=ModelAlias.THINKING,
            prompt_version="foreign-v4",
        ),
        findings=[],
    )
    assert not hasattr(result.findings, "append")
    with pytest.raises(AttributeError):
        result.findings.append(object())  # type: ignore[attr-defined]
