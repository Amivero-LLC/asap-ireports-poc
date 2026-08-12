"""Contract types as they stood during the Milestone 1c bake-off, vendored here.

**These are frozen historical artifacts, not live contracts. Nothing outside `spikes/` may
import them, and nothing here should be treated as the current shape of anything.**

The bake-off that produced ADR-012 ran against contract set v1.0.0, in which human review was an
in-run pause (ADR-011): a run stopped in `AWAITING_HUMAN_REVIEW`, an officer recorded a
`HumanDisposition`, and the run resumed. Leg 2 of the four-leg conformance suite —
`2-human-interrupt` — exercised exactly that.

ADR-022 removed the pause and the disposition contracts from `packages/domain/`, because iReports
has no human interaction: it runs unattended and review happens afterwards in ASAP. That left the
three spike orchestrators importing types that no longer exist.

The choice was between rewriting the spikes and vendoring what they were built against. Rewriting
would have been dishonest: the bake-off is **recorded evidence of a measurement that already
happened**, and quietly re-pointing leg 2 at a different scenario would make the retained code
stop matching `docs/handoff/orchestration-scorecard.md`. So the removed types live here instead,
and every candidate's control flow, checkpoint shape, and resume behaviour — the things the
scorecard actually measured — are untouched.

One immaterial drift is worth naming rather than hiding: the shared packaging helper in
`scenario.py` no longer passes `human_disposition` and `reviewer_modified` when building a
`DeliveredFinding`, because ADR-022 removed those two fields from the live contract. No leg
asserts on either, and neither appears in any measurement. Everything else runs as it ran.

**What this does and does not mean for ADR-012.** Leg 2 tested a workflow the architecture no
longer has, so as a forward-looking requirement it is obsolete. ADR-012 does not reopen: all three
candidates passed all four legs, and the decision was made on cost and dependency surface rather
than on any leg's outcome (`orchestration-scorecard.md` §1). Removing leg 2's relevance changes
none of the numbers the decision rested on. What survives as a live requirement is leg 1,
`1-durable-resume` — interrupt and resume across a process boundary is still exactly what
crash-and-resume needs (ORCH-02, Phase 2).
"""

from __future__ import annotations

from enum import StrEnum

from ireports_domain import InformationGap, ProposedFinding
from ireports_domain.common import (
    ActorId,
    ContractModel,
    DecisionSupportText,
    DispositionId,
    FindingId,
    RunId,
    UtcDatetime,
)
from pydantic import Field, model_validator


class BakeoffRunStatus(StrEnum):
    """The v1.0.0 run state machine, including the two states ADR-022 removed.

    `AWAITING_HUMAN_REVIEW` and `REVIEW_RECORDED` are the reason this enum is vendored rather than
    imported; every other member still exists in `ireports_domain.RunStatus` with the same value.
    """

    INITIALIZING = "initializing"
    ROUTING = "routing"
    RETRIEVING = "retrieving"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    VALIDATING = "validating"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REVIEW_RECORDED = "review_recorded"
    PACKAGING = "packaging"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE_DUE_TO_BUDGET = "incomplete_due_to_budget"


class ReviewerRole(StrEnum):
    AUTHORIZED_ADJUDICATIVE_OFFICER = "authorized_adjudicative_officer"


class DispositionKind(StrEnum):
    ACCEPTED = "accepted"
    MODIFIED_AND_ACCEPTED = "modified_and_accepted"
    REJECTED = "rejected"
    DEFERRED_PENDING_INFORMATION = "deferred_pending_information"


class ReasonCode(StrEnum):
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
    """The officer-approved wording, held separately from the machine proposal (v1.0.0)."""

    version: int = Field(ge=1)
    title: DecisionSupportText = Field(max_length=200)
    observation: DecisionSupportText
    policy_relevance: DecisionSupportText
    recommended_officer_action: DecisionSupportText
    information_gaps: tuple[InformationGap, ...] = Field(default_factory=tuple)


class HumanDisposition(ContractModel):
    """One officer decision about one proposed finding, as v1.0.0 defined it.

    The validators are kept because leg 2 constructed real instances; a stripped-down stand-in
    would not have exercised the same serialization cost the scorecard measured.
    """

    disposition_id: DispositionId
    finding_id: FindingId
    run_id: RunId

    reviewer_id: ActorId
    reviewer_role: ReviewerRole
    reviewed_at: UtcDatetime

    disposition: DispositionKind
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    reviewer_summary: DecisionSupportText

    approved_text: ApprovedFindingText | None = None
    release_to_asap: bool = False

    @model_validator(mode="after")
    def _disposition_is_internally_consistent(self) -> HumanDisposition:
        if self.disposition is DispositionKind.MODIFIED_AND_ACCEPTED and self.approved_text is None:
            raise ValueError("MODIFIED_AND_ACCEPTED requires approved_text")
        if self.disposition is DispositionKind.ACCEPTED and self.approved_text is not None:
            raise ValueError("ACCEPTED means the proposal stands as written")
        if self.release_to_asap and self.disposition in (
            DispositionKind.REJECTED,
            DispositionKind.DEFERRED_PENDING_INFORMATION,
        ):
            raise ValueError(
                f"release_to_asap is not permitted with disposition {self.disposition.value!r}"
            )
        return self


class DispositionedFinding(ContractModel):
    """A v1.0.0 proposal bound to its disposition — what the packager consumed at bake-off time."""

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


BAKEOFF_LEGAL_TRANSITIONS: dict[BakeoffRunStatus, frozenset[BakeoffRunStatus]] = {
    BakeoffRunStatus.INITIALIZING: frozenset(
        {BakeoffRunStatus.ROUTING, BakeoffRunStatus.FAILED, BakeoffRunStatus.CANCELLED}
    ),
    BakeoffRunStatus.ROUTING: frozenset(
        {
            BakeoffRunStatus.RETRIEVING,
            BakeoffRunStatus.AWAITING_HUMAN_REVIEW,
            BakeoffRunStatus.FAILED,
            BakeoffRunStatus.CANCELLED,
        }
    ),
    BakeoffRunStatus.RETRIEVING: frozenset(
        {
            BakeoffRunStatus.ANALYZING,
            BakeoffRunStatus.FAILED,
            BakeoffRunStatus.CANCELLED,
            BakeoffRunStatus.INCOMPLETE_DUE_TO_BUDGET,
        }
    ),
    BakeoffRunStatus.ANALYZING: frozenset(
        {
            BakeoffRunStatus.SYNTHESIZING,
            BakeoffRunStatus.FAILED,
            BakeoffRunStatus.CANCELLED,
            BakeoffRunStatus.INCOMPLETE_DUE_TO_BUDGET,
        }
    ),
    BakeoffRunStatus.SYNTHESIZING: frozenset(
        {BakeoffRunStatus.VALIDATING, BakeoffRunStatus.FAILED, BakeoffRunStatus.CANCELLED}
    ),
    BakeoffRunStatus.VALIDATING: frozenset(
        {
            BakeoffRunStatus.AWAITING_HUMAN_REVIEW,
            BakeoffRunStatus.ANALYZING,
            BakeoffRunStatus.FAILED,
            BakeoffRunStatus.CANCELLED,
        }
    ),
    BakeoffRunStatus.AWAITING_HUMAN_REVIEW: frozenset(
        {BakeoffRunStatus.REVIEW_RECORDED, BakeoffRunStatus.CANCELLED}
    ),
    BakeoffRunStatus.REVIEW_RECORDED: frozenset(
        {BakeoffRunStatus.PACKAGING, BakeoffRunStatus.CANCELLED}
    ),
    BakeoffRunStatus.PACKAGING: frozenset(
        {BakeoffRunStatus.DELIVERING, BakeoffRunStatus.FAILED, BakeoffRunStatus.CANCELLED}
    ),
    BakeoffRunStatus.DELIVERING: frozenset({BakeoffRunStatus.DELIVERED, BakeoffRunStatus.FAILED}),
    BakeoffRunStatus.DELIVERED: frozenset(),
    BakeoffRunStatus.FAILED: frozenset(),
    BakeoffRunStatus.CANCELLED: frozenset(),
    BakeoffRunStatus.INCOMPLETE_DUE_TO_BUDGET: frozenset(
        {BakeoffRunStatus.AWAITING_HUMAN_REVIEW, BakeoffRunStatus.CANCELLED}
    ),
}
"""The v1.0.0 transition table, with the review gate the bake-off's leg 2 walked through."""


def bakeoff_is_legal_transition(current: BakeoffRunStatus, proposed: BakeoffRunStatus) -> bool:
    return proposed in BAKEOFF_LEGAL_TRANSITIONS[current]
