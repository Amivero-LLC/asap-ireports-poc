"""Proposed findings and information gaps.

Blueprint §10.4. This is the contract ADR-014 and the decision-support boundary constrain most
tightly, so the constraints are structural rather than documentary:

- There is no aggregate risk score, risk level, or overall recommendation field, at any level
  (ADR-014). `tests/contract/test_no_aggregate_score.py` asserts this against the generated
  schemas so it cannot reappear under a new name.
- A finding is *proposed* until a human records a disposition (ADR-011). The type is named for
  that, and delivery is gated on a disposition, not on a flag.
- Every material claim carries a resolvable citation, enforced here rather than requested in a
  prompt (`CLAUDE.md`, "evidence before inference").
- Narrative fields use `DecisionSupportText`, which rejects determinative language.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    CaseId,
    Confidence,
    ContractModel,
    ContractVersion,
    DecisionDomain,
    DecisionSupportText,
    EvidenceId,
    FindingId,
    GapId,
    ModelAlias,
    NonEmptyStr,
    PolicyCitationId,
    PolicyPackId,
    RunId,
    UtcDatetime,
    ValidationOutcome,
)


class FindingClassification(StrEnum):
    """What kind of thing this finding is.

    Every member is a statement about the *record*, not about the person. There is deliberately
    no member meaning "adverse", "disqualifying", or "cleared" — those are determinations.
    """

    POTENTIAL_ISSUE = "potential_issue"
    MITIGATING_INFORMATION = "mitigating_information"
    CONTRADICTION = "contradiction"
    INFORMATION_GAP = "information_gap"
    NO_ISSUE_IDENTIFIED = "no_issue_identified"


class ReviewUrgency(StrEnum):
    """Sequencing hint for the reviewer's queue.

    This is not a severity score and must not become one. It says how soon a human should look,
    not how serious the underlying conduct is — the latter is an adjudicative judgment. It is
    per-finding and is never aggregated across findings or across a person (ADR-014).
    """

    ROUTINE = "routine"
    NORMAL_REVIEW = "normal_review"
    PROMPT_REVIEW = "prompt_review"


class FindingAuthority(ContractModel):
    """The single authority and criterion this finding is analysed under.

    One authority per finding, always. Blueprint §2.1: collapsing distinct authorities produces
    analysis that is wrong in a way that is hard to detect. If the same conduct is relevant under
    both 5 CFR 731 and SEAD-4, that is two findings with two criteria, joined at synthesis by
    de-duplication that preserves both — not one finding with a merged rationale.
    """

    decision_domain: DecisionDomain
    policy_pack_id: PolicyPackId
    policy_id: NonEmptyStr
    criterion_id: NonEmptyStr
    policy_citations: list[PolicyCitationId] = Field(
        min_length=1,
        description=(
            "At least one. A policy-relevance claim with no resolvable policy citation is "
            "exactly what the deterministic validator exists to reject."
        ),
    )


class GeneratedBy(ContractModel):
    """Provenance of the machine proposal.

    `model_alias` is an alias, never a model ID (ADR-008). Blueprint §10.4's example carries a
    concrete model name; this is a deliberate divergence so that a partition or model-generation
    change stays a LiteLLM config change.
    """

    node: NonEmptyStr
    model_alias: ModelAlias
    prompt_version: NonEmptyStr


class FindingValidation(ContractModel):
    """Results of the deterministic validators (blueprint §8.1, §10.4).

    The model does not decide whether its own output is valid — `CLAUDE.md`, "deterministic
    shell around probabilistic reasoning". These outcomes are written by validator code.
    """

    schema_check: ValidationOutcome = Field(
        description=(
            "Named `schema_check` rather than blueprint §10.4's `schema`, which would shadow a "
            "BaseModel attribute. Divergence is cosmetic."
        )
    )
    citations: ValidationOutcome = Field(
        description="Every cited evidence and policy id resolved against the run's snapshots."
    )
    policy_effective_date: ValidationOutcome
    protected_attribute_check: ValidationOutcome
    prohibited_language_check: ValidationOutcome

    @property
    def passed(self) -> bool:
        return all(
            outcome in (ValidationOutcome.PASSED, ValidationOutcome.NOT_APPLICABLE)
            for outcome in (
                self.schema_check,
                self.citations,
                self.policy_effective_date,
                self.protected_attribute_check,
                self.prohibited_language_check,
            )
        )


class InformationGap(ContractModel):
    """A question for the reviewer.

    Blueprint §8.4: the `propose_information_gap` tool records a question — it does not authorize
    external investigation or contact. Nothing in this contract carries an action to take.
    """

    gap_id: GapId
    question: DecisionSupportText
    why_it_matters: DecisionSupportText
    related_evidence_ids: list[EvidenceId] = Field(default_factory=list)
    blocking: bool = Field(
        default=False,
        description=(
            "True when analysis under this criterion cannot be completed without an answer."
        ),
    )


class ProposedFinding(ContractModel):
    """A machine-proposed finding, pending human disposition.

    Immutable by construction (`ContractModel` is frozen). ADR-011 requires that both the machine
    proposal and the human-approved version are retained, which only works if the proposal cannot
    be edited in place.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    finding_id: FindingId
    run_id: RunId
    case_id: CaseId

    authority: FindingAuthority
    classification: FindingClassification
    title: DecisionSupportText = Field(max_length=200)

    observation: DecisionSupportText = Field(
        description="What the record indicates. Descriptive, and fully supported by cited evidence."
    )
    policy_relevance: DecisionSupportText = Field(
        description=(
            "Why this may be relevant under the cited criterion. 'May be relevant' is the "
            "ceiling — relevance is proposed, applicability is the officer's call."
        )
    )

    supporting_evidence: list[EvidenceId] = Field(default_factory=list)
    mitigating_evidence: list[EvidenceId] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceId] = Field(default_factory=list)

    aggravating_factors: list[DecisionSupportText] = Field(default_factory=list)
    mitigating_factors: list[DecisionSupportText] = Field(
        default_factory=list,
        description=(
            "Whole-person and mitigation analysis is required, not optional (blueprint §8.3.6). "
            "A finding that records only aggravating factors is a red flag in evaluation."
        ),
    )
    information_gaps: list[InformationGap] = Field(default_factory=list)

    evidence_confidence: Confidence = Field(
        description="How solid the underlying record is — source reliability and corroboration."
    )
    analysis_confidence: Confidence = Field(
        description="How confident the analysis is that the criterion is implicated at all."
    )
    urgency: ReviewUrgency = ReviewUrgency.NORMAL_REVIEW

    recommended_officer_action: DecisionSupportText = Field(
        description=(
            "What the officer should *review*, never what they should decide. "
            "'Review the cited records and resolve the gaps' is in bounds; any recommended "
            "adjudicative outcome is rejected by the language guard."
        )
    )

    generated_by: GeneratedBy
    validation: FindingValidation
    proposed_at: UtcDatetime

    @model_validator(mode="after")
    def _material_claims_are_cited(self) -> ProposedFinding:
        """Evidence before inference, enforced structurally.

        A `potential_issue` or `contradiction` asserts something about the record and must cite
        it. `no_issue_identified` and `information_gap` assert an absence, which cannot be
        evidenced the same way — requiring citations there would push nodes toward citing
        irrelevant spans to satisfy a validator.
        """
        needs_support = {
            FindingClassification.POTENTIAL_ISSUE,
            FindingClassification.MITIGATING_INFORMATION,
            FindingClassification.CONTRADICTION,
        }
        if self.classification in needs_support and not self.supporting_evidence:
            raise ValueError(
                f"classification {self.classification.value!r} asserts something about the "
                "record and must cite at least one supporting evidence span"
            )
        if (
            self.classification is FindingClassification.CONTRADICTION
            and len(self.supporting_evidence) + len(self.contradicting_evidence) < 2
        ):
            raise ValueError(
                "a contradiction must cite at least two spans — the assertions that conflict"
            )
        if (
            self.classification is FindingClassification.INFORMATION_GAP
            and not self.information_gaps
        ):
            raise ValueError("an information_gap finding must carry at least one InformationGap")
        return self

    @model_validator(mode="after")
    def _evidence_ids_are_not_reused_across_roles(self) -> ProposedFinding:
        """One span cannot be both the support for a concern and its mitigation.

        This catches a real and subtle failure mode: a node that pads all three lists with the
        same retrieved spans produces a finding that looks thoroughly evidenced and is not.
        """
        roles = {
            "supporting": set(self.supporting_evidence),
            "mitigating": set(self.mitigating_evidence),
            "contradicting": set(self.contradicting_evidence),
        }
        names = list(roles)
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                overlap = roles[first] & roles[second]
                if overlap:
                    raise ValueError(
                        f"evidence {sorted(overlap)} appears as both {first} and {second}; "
                        "a span serves one role in a finding"
                    )
        return self
