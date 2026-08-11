"""Case manifest — the routing metadata a run is initialized from.

Blueprint §10.2. The important property of this contract is that authority routing is driven by
*explicit metadata*, never inferred from document content. Blueprint §10.2's routing rules make
that a requirement; the types here make it structural.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    ActorId,
    CaseId,
    ContractModel,
    ContractVersion,
    DataClassification,
    DecisionDomain,
    NonEmptyStr,
    PolicyPackId,
    SubjectId,
    UtcDatetime,
)


class PersonStatus(StrEnum):
    APPLICANT = "applicant"
    APPOINTEE = "appointee"
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"


class ServiceType(StrEnum):
    COMPETITIVE_SERVICE = "competitive_service"
    EXCEPTED_SERVICE = "excepted_service"
    SENIOR_EXECUTIVE_SERVICE = "senior_executive_service"
    CONTRACTOR_POSITION = "contractor_position"


class PositionRiskLevel(StrEnum):
    """5 CFR part 731 position risk designation (blueprint §2.6)."""

    LOW_RISK = "low_risk"
    MODERATE_RISK_PUBLIC_TRUST = "moderate_risk_public_trust"
    HIGH_RISK_PUBLIC_TRUST = "high_risk_public_trust"


class PositionSensitivity(StrEnum):
    """National-security position sensitivity designation."""

    NON_SENSITIVE = "non_sensitive"
    NONCRITICAL_SENSITIVE = "noncritical_sensitive"
    CRITICAL_SENSITIVE = "critical_sensitive"
    SPECIAL_SENSITIVE = "special_sensitive"


class ClearanceRequirement(StrEnum):
    NONE = "none"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"
    TOP_SECRET_SCI = "top_secret_sci"


class DocumentExpectation(StrEnum):
    """Documents the case is expected to contain.

    Drives the completeness checker (blueprint §8.1). An expectation that is not satisfied
    becomes an information gap, not a silent omission.
    """

    SECURITY_QUESTIONNAIRE = "security_questionnaire"
    REPORT_OF_INVESTIGATION = "report_of_investigation"
    SUBJECT_INTERVIEW = "subject_interview"
    CREDIT_REPORT = "credit_report"
    LAW_ENFORCEMENT_CHECK = "law_enforcement_check"
    EMPLOYMENT_VERIFICATION = "employment_verification"
    EDUCATION_VERIFICATION = "education_verification"
    REFERENCE_INTERVIEW = "reference_interview"
    SUBJECT_STATEMENT = "subject_statement"


class Subject(ContractModel):
    """The person the case concerns.

    `protected_attributes_included` is a declaration, not a container. Blueprint §10.2 requires
    that protected attributes not be included unless needed for a legitimate, approved purpose,
    and blueprint §13.7 prohibits their use in analysis. This contract carries no field in which
    a protected attribute could be placed, so the flag exists to assert their *absence* and to
    let a validator fail closed if an ingestion path ever tries to introduce them.
    """

    subject_id: SubjectId
    display_name: NonEmptyStr = Field(
        description="Synthetic name only. See DataClassification — this repo holds no real cases."
    )
    citizenship: tuple[NonEmptyStr, ...] = Field(
        default_factory=tuple,
        description=(
            "Relevant to SEAD-4 Guidelines A-C analysis. Present because it is a "
            "criterion input under a named authority, not a general demographic attribute."
        ),
    )
    protected_attributes_included: Literal[False] = Field(
        default=False,
        description=(
            "Structurally pinned false. If a legitimate, approved purpose ever requires "
            "protected attributes, that is a contract major version and a policy decision, "
            "not a runtime flag."
        ),
    )


class CaseContext(ContractModel):
    """Explicit routing metadata.

    Every field here is an input to authority routing. Blueprint §10.2: the system may not infer
    service type, person status, or position sensitivity from document content when explicit
    metadata is required. Fields that routing needs but that may be genuinely unknown are
    optional here and produce a *blocking information gap* at routing time rather than a guess.
    """

    person_status: PersonStatus
    service_type: ServiceType
    position_title: NonEmptyStr
    position_risk_level: PositionRiskLevel | None = Field(
        default=None,
        description=(
            "Required to route suitability/fitness. Absence is a blocking gap, not a default."
        ),
    )
    position_sensitivity: PositionSensitivity | None = Field(
        default=None,
        description="Required to route national-security eligibility. Absence is a blocking gap.",
    )
    clearance_requirement: ClearanceRequirement | None = None
    piv_required: bool | None = None
    conditional_offer_date: UtcDatetime | None = Field(
        default=None,
        description=(
            "Fair Chance Act process control (blueprint §2.5): criminal-history inquiry timing "
            "is evaluated relative to this date."
        ),
    )
    entry_on_duty_date: UtcDatetime | None = None
    agency_component: NonEmptyStr


class CaseManifest(ContractModel):
    """The case as the system is asked to analyse it.

    Blueprint §10.2. Note what is absent: no aggregate risk field, no overall assessment, no
    prior determination. ADR-014 forbids the first; the others would prejudice the analysis.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    case_id: CaseId
    case_name: NonEmptyStr
    tenant_id: NonEmptyStr
    program_id: NonEmptyStr
    data_classification: DataClassification = DataClassification.SYNTHETIC_NO_PII

    subject: Subject
    case_context: CaseContext

    requested_analyses: tuple[DecisionDomain, ...] = Field(
        min_length=1,
        description=(
            "A request, not an authorization. Blueprint §10.2: requested_analyses cannot "
            "override legal applicability — the authority router validates each request against "
            "case_context and may decline one or add one the requester omitted."
        ),
    )
    policy_pack_ids: tuple[PolicyPackId, ...] = Field(min_length=1)
    document_expectations: tuple[DocumentExpectation, ...] = Field(default_factory=tuple)
    documents_root: NonEmptyStr = "documents"

    created_at: UtcDatetime
    created_by: ActorId

    @model_validator(mode="after")
    def _no_duplicate_requests(self) -> CaseManifest:
        if len(set(self.requested_analyses)) != len(self.requested_analyses):
            raise ValueError("requested_analyses contains duplicates")
        if len(set(self.policy_pack_ids)) != len(self.policy_pack_ids):
            raise ValueError("policy_pack_ids contains duplicates")
        return self
