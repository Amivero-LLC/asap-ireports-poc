"""Versioned data contracts for asap-ireports.

Contracts come before the orchestration decision on purpose (ROADMAP 1a): they are the interface
the orchestration choice has to satisfy. A framework that cannot carry this state cheaply through
a checkpoint, or cannot pause between a proposal and its disposition, is disqualified by these
types rather than by opinion.

`ROOT_CONTRACTS` is the set published as JSON Schema. It is also what the ADR-014 guard test
walks, so adding a contract here automatically brings it under that check.
"""

from __future__ import annotations

from .asap import (
    ENVELOPE_VERSION,
    MAX_EXCERPT_CHARS,
    ASAPEnvelope,
    DeliveredFinding,
    DeliveryReceipt,
    EnvelopeAnalysis,
    EnvelopeCase,
    EnvelopeIntegrity,
    EvidenceExcerpt,
    OutboxMessage,
    OutboxStatus,
)
from .case import (
    CaseContext,
    CaseManifest,
    ClearanceRequirement,
    DocumentExpectation,
    PersonStatus,
    PositionRiskLevel,
    PositionSensitivity,
    ServiceType,
    Subject,
)
from .common import (
    CONTRACT_VERSION,
    Confidence,
    ContractModel,
    DataClassification,
    DecisionDomain,
    DecisionSupportText,
    ModelAlias,
    ValidationOutcome,
    reject_determinative_language,
)
from .disposition import (
    ApprovedFindingText,
    DispositionedFinding,
    DispositionKind,
    HumanDisposition,
    ReasonCode,
    ReviewerRole,
    ReviewSummary,
)
from .document import (
    CanonicalDocument,
    DocumentBlock,
    DocumentManifest,
    DocumentType,
    ExtractionMethod,
    SourceReliability,
)
from .evidence import (
    ContradictionRecord,
    EvidenceRecord,
    EvidenceSpan,
    RetrievalMode,
    RetrievalProvenance,
)
from .finding import (
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    InformationGap,
    ProposedFinding,
    ReviewUrgency,
)
from .policy import (
    AuthorityRoute,
    AuthorityRoutingResult,
    PolicyCitation,
    PolicyPackRef,
    PolicyPackStatus,
    RoutingBasis,
)
from .run import (
    LEGAL_TRANSITIONS,
    Actor,
    BudgetConsumption,
    Budgets,
    RunError,
    RunManifest,
    RunStatus,
    is_legal_transition,
)

ROOT_CONTRACTS: dict[str, type[ContractModel]] = {
    "case": CaseManifest,
    "document": DocumentManifest,
    "canonical-document": CanonicalDocument,
    "evidence": EvidenceRecord,
    "contradiction": ContradictionRecord,
    "authority-routing": AuthorityRoutingResult,
    "finding": ProposedFinding,
    "run": RunManifest,
    "human-disposition": HumanDisposition,
    "review-summary": ReviewSummary,
    "asap-envelope": ASAPEnvelope,
    "outbox-message": OutboxMessage,
    "delivery-receipt": DeliveryReceipt,
}
"""Contracts published to `schemas/` as JSON Schema. Keys are the schema file stems."""

__all__ = [
    "CONTRACT_VERSION",
    "ENVELOPE_VERSION",
    "LEGAL_TRANSITIONS",
    "MAX_EXCERPT_CHARS",
    "ROOT_CONTRACTS",
    "ASAPEnvelope",
    "Actor",
    "ApprovedFindingText",
    "AuthorityRoute",
    "AuthorityRoutingResult",
    "BudgetConsumption",
    "Budgets",
    "CanonicalDocument",
    "CaseContext",
    "CaseManifest",
    "ClearanceRequirement",
    "Confidence",
    "ContractModel",
    "ContradictionRecord",
    "DataClassification",
    "DecisionDomain",
    "DecisionSupportText",
    "DeliveredFinding",
    "DeliveryReceipt",
    "DispositionKind",
    "DispositionedFinding",
    "DocumentBlock",
    "DocumentExpectation",
    "DocumentManifest",
    "DocumentType",
    "EnvelopeAnalysis",
    "EnvelopeCase",
    "EnvelopeIntegrity",
    "EvidenceExcerpt",
    "EvidenceRecord",
    "EvidenceSpan",
    "ExtractionMethod",
    "FindingAuthority",
    "FindingClassification",
    "FindingValidation",
    "GeneratedBy",
    "HumanDisposition",
    "InformationGap",
    "ModelAlias",
    "OutboxMessage",
    "OutboxStatus",
    "PersonStatus",
    "PolicyCitation",
    "PolicyPackRef",
    "PolicyPackStatus",
    "PositionRiskLevel",
    "PositionSensitivity",
    "ProposedFinding",
    "ReasonCode",
    "RetrievalMode",
    "RetrievalProvenance",
    "ReviewSummary",
    "ReviewUrgency",
    "ReviewerRole",
    "RoutingBasis",
    "RunError",
    "RunManifest",
    "RunStatus",
    "ServiceType",
    "SourceReliability",
    "Subject",
    "ValidationOutcome",
    "is_legal_transition",
    "reject_determinative_language",
]
