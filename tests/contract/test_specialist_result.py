"""`SpecialistResult` and `SpecialistCriterion`, asserted against D-01 through D-06.

`.planning/phases/01-close-the-architecture-package/01-CONTEXT.md` records six decisions about
this contract. Each test below is named for the decision it guards, following
`test_decision_support_boundary.py`'s one-rule-per-test style — a rule with no test guarding it
by name is a rule a future change can quietly reopen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from ireports_domain import (
    Confidence,
    DecisionDomain,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    ModelAlias,
    ProposedFinding,
    SpecialistCriterion,
    SpecialistResult,
    ValidationOutcome,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
CASE_ID = "AMI-SYN-MIX-004"
RUN_ID = "run_01J9AA"


def _criterion(**overrides: object) -> SpecialistCriterion:
    base: dict[str, object] = {
        "decision_domain": DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        "policy_pack_id": "sead4-current",
        "policy_id": "SEAD-4",
        "criterion_id": "GUIDELINE-B",
    }
    return SpecialistCriterion(**(base | overrides))


def _finding(**overrides: object) -> ProposedFinding:
    base: dict[str, object] = {
        "finding_id": "fnd_01J9AB",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
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
        "supporting_evidence": ["ev_201"],
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


def _result(**overrides: object) -> SpecialistResult:
    base: dict[str, object] = {
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "criterion": _criterion(),
        "generated_by": GeneratedBy(
            node="foreign_influence_specialist",
            model_alias=ModelAlias.THINKING,
            prompt_version="foreign-v4",
        ),
        "findings": [_finding()],
    }
    return SpecialistResult(**(base | overrides))


def _walk_property_names(schema: dict[str, Any], defs: dict[str, Any]) -> set[str]:
    """Collect every property name reachable from a schema, following $defs.

    Mirrors `test_decision_support_boundary.py`'s helper of the same name, so an absence claim
    here is checked at the same depth as the ADR-014 no-aggregate-score guard.
    """
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


# ---------------------------------------------------------------------------
# D-05 — the criterion is present even when zero findings come back
# ---------------------------------------------------------------------------


def test_a_zero_findings_result_validates_and_still_names_its_criterion() -> None:
    """This is the whole reason the wrapper exists rather than a bare list of findings."""
    result = _result(findings=[])
    assert result.findings == []
    assert result.criterion.criterion_id == "GUIDELINE-B"


# ---------------------------------------------------------------------------
# D-02 — no completion field, no boolean "done" flag, no free-text reason
# ---------------------------------------------------------------------------


def test_no_completion_field_exists_by_any_of_its_candidate_names() -> None:
    """An earlier five-member enum for exactly this was proposed and reversed (ADR-021
    Decision 2): "We should LOG things and check the logs, but not require the orchestrator to
    do anything special." None of its candidate spellings may reappear, at the Python level or
    in the published schema.
    """
    forbidden_names = {
        "status",
        "is_complete",
        "complete",
        "completion_status",
        "incomplete_reason",
    }
    assert not forbidden_names & SpecialistResult.model_fields.keys()

    schema = SpecialistResult.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    assert not forbidden_names & names


# ---------------------------------------------------------------------------
# D-03 — no per-query budget accounting
# ---------------------------------------------------------------------------


def test_no_per_query_budget_accounting() -> None:
    """`BudgetConsumption` already accumulates at run level on `RunManifest` (D-03); a
    per-query duplicate here would let two records disagree about what a run spent.
    """
    schema = SpecialistResult.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    offenders = {
        name
        for name in names
        if any(bad in name.lower() for bad in ("budget", "token", "consumption"))
    }
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# D-04 — the criterion descriptor is not the per-finding authority type
# ---------------------------------------------------------------------------


def test_the_criterion_descriptor_omits_citations_and_has_no_extra_fields() -> None:
    """A query does not cite; a finding does. `SpecialistCriterion` is a sibling of the
    per-finding authority type, not that type reused, and carries only the four identifying
    fields.
    """
    assert "policy_citations" not in SpecialistCriterion.model_fields
    assert set(SpecialistCriterion.model_fields.keys()) == {
        "decision_domain",
        "policy_pack_id",
        "policy_id",
        "criterion_id",
    }


# ---------------------------------------------------------------------------
# D-06 — hygiene and round-trip
# ---------------------------------------------------------------------------


def test_an_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _result(extra_field="not part of the contract")


def test_a_constructed_result_cannot_be_mutated() -> None:
    result = _result()
    with pytest.raises(ValidationError):
        result.case_id = "AMI-SYN-MIX-999"


def test_a_result_round_trips_through_json_without_loss() -> None:
    result = _result()
    assert SpecialistResult.model_validate_json(result.model_dump_json()) == result


# ---------------------------------------------------------------------------
# The Task 1 validator actually catches something
# ---------------------------------------------------------------------------


def test_a_finding_under_a_different_criterion_is_rejected() -> None:
    """A rule with no failing example in its own suite is a rule that cannot be trusted to have
    ever run.
    """
    mismatched = _finding(
        authority=FindingAuthority(
            decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
            policy_pack_id="sead4-current",
            policy_id="SEAD-4",
            criterion_id="GUIDELINE-C",
            policy_citations=["pol_sead4_c_01"],
        )
    )
    with pytest.raises(ValidationError, match="fnd_01J9AB"):
        _result(findings=[mismatched])
