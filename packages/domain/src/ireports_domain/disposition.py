"""Human disposition — the gate between machine proposal and delivery.

Blueprint §10.5, ADR-011. The design commitment is that *both* the machine proposal and the
human-approved version are retained. `HumanDisposition` therefore never edits a `ProposedFinding`;
it references the immutable proposal by id and carries the approved text alongside it. A reviewer
can always see what the machine said and what the officer changed it to.

`ProposedFinding` being frozen is what makes this hold in code rather than by convention.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    ActorId,
    ContractModel,
    ContractVersion,
    DecisionSupportText,
    DispositionId,
    FindingId,
    RunId,
    UtcDatetime,
)
from .finding import InformationGap, ProposedFinding


class ReviewerRole(StrEnum):
    """ADR-011: a single authorized reviewer role in the first release.

    Kept as an enum rather than a free string so that widening the role model later is a visible
    contract change reviewed against Q-07, not an incidental string that appears in production.
    """

    AUTHORIZED_ADJUDICATIVE_OFFICER = "authorized_adjudicative_officer"


class DispositionKind(StrEnum):
    """What the officer did with the proposal.

    Note what is absent. There is no `auto_approved`, and no member that a system could assign to
    itself. Every member describes an action a human took.
    """

    ACCEPTED = "accepted"
    MODIFIED_AND_ACCEPTED = "modified_and_accepted"
    REJECTED = "rejected"
    DEFERRED_PENDING_INFORMATION = "deferred_pending_information"


class ReasonCode(StrEnum):
    """Structured reasons, so reviewer behaviour is measurable.

    Blueprint §12.9 wants human-factors evaluation; free-text-only reasons make that impossible.
    These feed the evaluation harness — a high rate of `UNSUPPORTED_BY_EVIDENCE` on a given
    criterion is a signal about the analysis, not about the reviewer.
    """

    MITIGATION_ADDED = "MITIGATION_ADDED"
    WORDING_NARROWED = "WORDING_NARROWED"
    UNSUPPORTED_BY_EVIDENCE = "UNSUPPORTED_BY_EVIDENCE"
    CITATION_INCORRECT = "CITATION_INCORRECT"
    POLICY_MISAPPLIED = "POLICY_MISAPPLIED"
    DUPLICATE_OF_ANOTHER_FINDING = "DUPLICATE_OF_ANOTHER_FINDING"
    OUT_OF_SCOPE_FOR_AUTHORITY = "OUT_OF_SCOPE_FOR_AUTHORITY"
    GAP_MUST_BE_RESOLVED_FIRST = "GAP_MUST_BE_RESOLVED_FIRST"
    PROTECTED_ATTRIBUTE_CONCERN = "PROTECTED_ATTRIBUTE_CONCERN"
    ACCURATE_AS_PROPOSED = "ACCURATE_AS_PROPOSED"


class ApprovedFindingText(ContractModel):
    """The officer-approved wording, held separately from the machine proposal.

    Subject to the same language guard as the proposal. The boundary applies to the system's
    *output* regardless of who wrote the words — a delivered envelope carrying a determination
    is out of bounds whether a model or a human typed it, and the officer's determination
    authority is exercised in their own system of record, not through this pipeline.
    """

    version: int = Field(
        ge=1, description="Increments per revision; version 1 is the first approved text."
    )
    title: DecisionSupportText = Field(max_length=200)
    observation: DecisionSupportText
    policy_relevance: DecisionSupportText
    recommended_officer_action: DecisionSupportText
    information_gaps: list[InformationGap] = Field(default_factory=list)


class HumanDisposition(ContractModel):
    """One officer decision about one proposed finding.

    `release_to_asap` is the only thing that authorizes delivery, and the validators below make
    it structurally impossible to set on a rejected or deferred finding.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    disposition_id: DispositionId
    finding_id: FindingId = Field(description="References the immutable machine proposal.")
    run_id: RunId

    reviewer_id: ActorId
    reviewer_role: ReviewerRole
    reviewed_at: UtcDatetime

    disposition: DispositionKind
    reason_codes: list[ReasonCode] = Field(min_length=1)
    reviewer_summary: DecisionSupportText

    approved_text: ApprovedFindingText | None = Field(
        default=None,
        description="Required for MODIFIED_AND_ACCEPTED. Never overwrites the machine proposal.",
    )
    release_to_asap: bool = Field(
        default=False,
        description="The delivery authorization. Only an accepted finding may carry it.",
    )

    @model_validator(mode="after")
    def _disposition_is_internally_consistent(self) -> HumanDisposition:
        if self.disposition is DispositionKind.MODIFIED_AND_ACCEPTED and self.approved_text is None:
            raise ValueError(
                "MODIFIED_AND_ACCEPTED requires approved_text: the modification must be recorded "
                "alongside the retained machine proposal (ADR-011)"
            )
        if self.disposition is DispositionKind.ACCEPTED and self.approved_text is not None:
            raise ValueError(
                "ACCEPTED means the proposal stands as written; supply approved_text only with "
                "MODIFIED_AND_ACCEPTED so that 'unchanged' and 'changed' stay distinguishable"
            )
        if self.release_to_asap and self.disposition in (
            DispositionKind.REJECTED,
            DispositionKind.DEFERRED_PENDING_INFORMATION,
        ):
            raise ValueError(
                f"release_to_asap is not permitted with disposition {self.disposition.value!r}"
            )
        return self


class DispositionedFinding(ContractModel):
    """A proposal bound to its disposition — the unit the packager consumes.

    Holding both together is what ADR-011 means by retaining the machine proposal *and* the
    approved version. `effective_*` resolves which wording delivery should carry without ever
    discarding the other.
    """

    proposal: ProposedFinding
    disposition: HumanDisposition

    @model_validator(mode="after")
    def _disposition_matches_proposal(self) -> DispositionedFinding:
        if self.disposition.finding_id != self.proposal.finding_id:
            raise ValueError("disposition.finding_id does not match the proposal it is bound to")
        if self.disposition.run_id != self.proposal.run_id:
            raise ValueError("disposition.run_id does not match the proposal's run")
        return self

    @property
    def is_releasable(self) -> bool:
        return self.disposition.release_to_asap

    @property
    def effective_title(self) -> str:
        text = self.disposition.approved_text
        return text.title if text else self.proposal.title

    @property
    def effective_observation(self) -> str:
        text = self.disposition.approved_text
        return text.observation if text else self.proposal.observation

    @property
    def effective_policy_relevance(self) -> str:
        text = self.disposition.approved_text
        return text.policy_relevance if text else self.proposal.policy_relevance

    @property
    def effective_officer_action(self) -> str:
        text = self.disposition.approved_text
        return text.recommended_officer_action if text else self.proposal.recommended_officer_action

    @property
    def effective_information_gaps(self) -> list[InformationGap]:
        text = self.disposition.approved_text
        return list(text.information_gaps) if text else list(self.proposal.information_gaps)


class ReviewSummary(ContractModel):
    """The run-level review record.

    Exists so the gate can be checked in one place: a run may proceed only when every proposed
    finding has a disposition. A partially-reviewed run is a state, not a rounding error.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    run_id: RunId
    reviewer_id: ActorId
    reviewer_role: ReviewerRole
    completed_at: UtcDatetime
    dispositions: list[HumanDisposition] = Field(min_length=1)
    reviewer_run_summary: DecisionSupportText | None = None

    @model_validator(mode="after")
    def _one_disposition_per_finding(self) -> ReviewSummary:
        finding_ids = [d.finding_id for d in self.dispositions]
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("each finding may carry at most one disposition in a review")
        if any(d.run_id != self.run_id for d in self.dispositions):
            raise ValueError("all dispositions in a review must belong to the same run")
        return self

    def covers(self, proposed_finding_ids: list[str] | set[str]) -> bool:
        """Whether every proposed finding in the run has been dispositioned."""
        return set(proposed_finding_ids) <= {d.finding_id for d in self.dispositions}

    @property
    def releasable_finding_ids(self) -> list[str]:
        return [d.finding_id for d in self.dispositions if d.release_to_asap]
