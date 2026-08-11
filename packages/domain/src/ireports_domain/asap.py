"""ASAP delivery envelope, outbox message, and delivery receipt.

Blueprint §10.6-10.7, ADR-010.

**This envelope is our proposal, not an agreed interface.** The authoritative ASAP ingestion
contract is not available to this project (Q-04). Contract tests pin our side so that the delta
is measurable when the real specification lands, rather than discovered during integration.

Two deliberate divergences from blueprint §10.6:

1. **Evidence is embedded as bounded excerpts *plus* stable references** (ADR-010). The
   blueprint's example uses `evidence_mode: "references_only"`. Embedded excerpts make a
   delivered finding reviewable without a second lookup and without depending on ASAP's ability
   to resolve references into our stores.
2. **`model_alias`, never a model ID** (ADR-008).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

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
    IngestionId,
    MessageId,
    ModelAlias,
    NonEmptyStr,
    PolicyCitationId,
    PolicyPackId,
    ReceiptId,
    RunId,
    Sha256,
    SubjectId,
    UtcDatetime,
)
from .document import SourceReliability
from .finding import FindingClassification, InformationGap, ReviewUrgency

EnvelopeVersion = Literal["1.0.0"]
"""The envelope's own version, versioned independently of the contract set.

Separate from `ContractVersion` on purpose: when Q-04 resolves and the real ASAP specification
lands, the envelope will almost certainly change while the internal contracts do not. Coupling
the two would force an unrelated major bump across every contract.
"""

ENVELOPE_VERSION: EnvelopeVersion = "1.0.0"

MAX_EXCERPT_CHARS = 2000
"""Upper bound on an embedded excerpt.

"Bounded" in ADR-010 needs a number or it is not a constraint. This one is a starting value, not
a researched threshold — it is large enough to carry a cited passage with context and small
enough that an envelope cannot become a copy of the case file. Revisit against real ASAP payload
limits when Q-04 resolves.
"""


class EvidenceExcerpt(ContractModel):
    """A bounded excerpt plus the reference needed to retrieve the full span.

    Both, not either. The excerpt makes the finding reviewable on arrival; the reference keeps
    our store authoritative and lets ASAP re-fetch under its own authorization.
    """

    evidence_id: EvidenceId
    excerpt: NonEmptyStr = Field(
        max_length=MAX_EXCERPT_CHARS,
        description="Verbatim, truncated to MAX_EXCERPT_CHARS. Never a model paraphrase.",
    )
    truncated: bool = Field(
        default=False, description="True when the source span exceeded MAX_EXCERPT_CHARS."
    )
    text_sha256: Sha256 = Field(description="Hash of the *full* span, not the excerpt.")
    document_reference: NonEmptyStr = Field(description="Stable, authorization-checked reference.")
    page_number: int | None = Field(default=None, ge=1)
    source_reliability: SourceReliability = SourceReliability.UNDETERMINED


class DeliveredFinding(ContractModel):
    """One human-approved finding, as ASAP receives it.

    `machine_proposal_finding_id` is retained so the delivered record traces back to the
    immutable proposal (ADR-011). `human_disposition` is required — there is no shape of this
    object that represents an undispositioned finding.
    """

    finding_id: FindingId
    machine_proposal_finding_id: FindingId
    decision_domain: DecisionDomain
    policy_pack_id: PolicyPackId
    policy_id: NonEmptyStr
    criterion_id: NonEmptyStr
    policy_citations: list[PolicyCitationId] = Field(min_length=1)

    classification: FindingClassification
    title: DecisionSupportText = Field(max_length=200)
    observation: DecisionSupportText
    policy_relevance: DecisionSupportText
    recommended_officer_action: DecisionSupportText

    supporting_evidence: list[EvidenceExcerpt] = Field(default_factory=list)
    mitigating_evidence: list[EvidenceExcerpt] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceExcerpt] = Field(default_factory=list)

    aggravating_factors: list[DecisionSupportText] = Field(default_factory=list)
    mitigating_factors: list[DecisionSupportText] = Field(default_factory=list)
    information_gaps: list[InformationGap] = Field(default_factory=list)

    evidence_confidence: Confidence
    analysis_confidence: Confidence
    urgency: ReviewUrgency

    human_disposition: NonEmptyStr = Field(
        description="The DispositionKind value. Required — delivery presupposes a disposition."
    )
    reviewer_modified: bool = Field(
        description="True when the officer changed the wording. Both versions are retained by us."
    )


class EnvelopeCase(ContractModel):
    case_id: CaseId
    program_id: NonEmptyStr
    subject_id: SubjectId
    ingestion_id: IngestionId


class EnvelopeAnalysis(ContractModel):
    """The analysis section.

    Note the absent field. Blueprint §10.6's example has a free-text `summary`; a run-level
    narrative is the most likely place for an aggregate characterization of a person to
    reappear, which ADR-014 forbids. It is present here only as a reviewer-authored,
    language-guarded optional field, and it is never machine-generated.
    """

    run_id: RunId
    policy_pack_ids: list[PolicyPackId] = Field(min_length=1)
    model_aliases: list[ModelAlias] = Field(min_length=1)
    findings: list[DeliveredFinding] = Field(min_length=1)
    reviewer_summary: DecisionSupportText | None = Field(
        default=None, description="Reviewer-authored only. Never machine-generated."
    )
    machine_generated: Literal[True] = True
    human_reviewed: Literal[True] = Field(
        default=True,
        description=(
            "Structurally pinned. An envelope is only constructible for a reviewed run, so "
            "`false` has no valid meaning here (ADR-011)."
        ),
    )


class EnvelopeIntegrity(ContractModel):
    payload_sha256: Sha256
    signature: NonEmptyStr | None = Field(
        default=None, description="Mechanism to be agreed with ASAP. Q-04."
    )


class ASAPEnvelope(ContractModel):
    """One versioned envelope per approved run (blueprint §10.6)."""

    envelope_version: EnvelopeVersion = ENVELOPE_VERSION
    schema_version: ContractVersion = CONTRACT_VERSION
    message_id: MessageId
    idempotency_key: NonEmptyStr = Field(
        description=(
            "Stable across retries and unique per approved payload. Blueprint's convention is "
            "'{case_id}:{run_id}:approved-v{n}'. Delivery correctness depends on this being "
            "derived, never random."
        )
    )
    created_at: UtcDatetime
    source_system: NonEmptyStr = "asap-ireports"
    destination_system: NonEmptyStr = "asap"

    case: EnvelopeCase
    analysis: EnvelopeAnalysis
    integrity: EnvelopeIntegrity

    @model_validator(mode="after")
    def _envelope_is_traceable(self) -> ASAPEnvelope:
        if self.idempotency_key.startswith(self.case.case_id) is False:
            raise ValueError(
                "idempotency_key must begin with the case_id so a delivery can be traced to its "
                "case without parsing the payload"
            )
        finding_ids = [f.finding_id for f in self.analysis.findings]
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("envelope contains duplicate finding_ids")
        return self


# ---------------------------------------------------------------------------
# Transactional outbox (blueprint §10.7)
# ---------------------------------------------------------------------------


class OutboxStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class OutboxMessage(ContractModel):
    """A delivery intent, written in the same transaction that records the approval.

    Blueprint §10.7. The envelope is never sent from a model node and never before the human
    gate — the outbox is the only path, and it is written by the packager after review.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    message_id: MessageId
    run_id: RunId
    case_id: CaseId
    idempotency_key: NonEmptyStr
    payload_sha256: Sha256

    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    leased_until: UtcDatetime | None = None
    next_attempt_at: UtcDatetime | None = None
    last_error: NonEmptyStr | None = None
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _lease_is_consistent(self) -> OutboxMessage:
        if self.status is OutboxStatus.LEASED and self.leased_until is None:
            raise ValueError("a leased message must carry leased_until or it cannot be reclaimed")
        if self.status is OutboxStatus.DEAD_LETTER and not self.last_error:
            raise ValueError("dead-lettered messages must record why, for human correction")
        return self


class DeliveryReceipt(ContractModel):
    """What ASAP said, recorded for reconciliation (blueprint §10.8)."""

    schema_version: ContractVersion = CONTRACT_VERSION
    receipt_id: ReceiptId
    message_id: MessageId
    run_id: RunId
    idempotency_key: NonEmptyStr

    http_status: int = Field(ge=100, le=599)
    response_body_sha256: Sha256 | None = None
    remote_receipt_id: NonEmptyStr | None = None
    attempt: int = Field(ge=1)
    delivered_at: UtcDatetime
    retriable: bool = Field(
        description=(
            "Classification of the outcome, not a raw status echo. A 409 on a duplicate "
            "idempotency key is a success for our purposes; a 422 is a dead-letter."
        )
    )
