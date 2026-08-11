"""The decision-support boundary, asserted against the contracts.

`CLAUDE.md` states the boundary as non-negotiable and lists concrete constraints on the code.
This module turns each of those constraints into a test, so that a change which reopens one
fails here rather than in a review someone might not do.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from ireports_domain import (
    ROOT_CONTRACTS,
    Confidence,
    DecisionDomain,
    DispositionKind,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    HumanDisposition,
    ModelAlias,
    ProposedFinding,
    ReasonCode,
    ReviewerRole,
    RunStatus,
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
# ADR-011 — the human review gate has no bypass
# ---------------------------------------------------------------------------


def test_no_path_reaches_delivery_without_human_review() -> None:
    """Walk the state machine and prove the gate is unavoidable.

    Asserting the validator alone would not be enough: a transition table that let
    VALIDATING jump straight to PACKAGING would satisfy every field-level check while
    reopening exactly the bypass ADR-011 forbids.
    """
    gate = RunStatus.AWAITING_HUMAN_REVIEW
    reachable_without_gate: set[RunStatus] = {RunStatus.INITIALIZING}
    frontier = [RunStatus.INITIALIZING]
    while frontier:
        current = frontier.pop()
        for nxt in LEGAL_TRANSITIONS[current]:
            if nxt is gate or nxt in reachable_without_gate:
                continue
            reachable_without_gate.add(nxt)
            frontier.append(nxt)

    delivery_side = {
        RunStatus.REVIEW_RECORDED,
        RunStatus.PACKAGING,
        RunStatus.DELIVERING,
        RunStatus.DELIVERED,
    }
    leaked = delivery_side & reachable_without_gate
    assert not leaked, (
        f"states {sorted(s.value for s in leaked)} are reachable without passing through "
        f"{gate.value}; ADR-011 requires the review gate to be unavoidable"
    )


def test_budget_exhaustion_routes_to_review_not_to_silent_failure() -> None:
    """Blueprint §8.5: a budget stop must be visible to a reviewer."""
    assert RunStatus.AWAITING_HUMAN_REVIEW in LEGAL_TRANSITIONS[RunStatus.INCOMPLETE_DUE_TO_BUDGET]


def test_rejected_findings_cannot_be_released() -> None:
    with pytest.raises(ValidationError, match="release_to_asap is not permitted"):
        HumanDisposition(
            disposition_id="dsp_01",
            finding_id="fnd_01",
            run_id="run_01",
            reviewer_id="officer-42",
            reviewer_role=ReviewerRole.AUTHORIZED_ADJUDICATIVE_OFFICER,
            reviewed_at=NOW,
            disposition=DispositionKind.REJECTED,
            reason_codes=[ReasonCode.UNSUPPORTED_BY_EVIDENCE],
            reviewer_summary="The cited span does not support the stated observation.",
            release_to_asap=True,
        )


def test_there_is_no_auto_approval_disposition() -> None:
    """Every disposition must describe an action a human took."""
    values = {d.value for d in DispositionKind}
    assert not any("auto" in v or "system" in v for v in values), values
