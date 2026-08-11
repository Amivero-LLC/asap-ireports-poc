"""The contracts, exercised as one chain: case → evidence → finding → disposition → envelope.

Field-level tests prove each contract is internally consistent. They do not prove the set
composes, which is the actual question Milestone 1a has to answer — the contracts are the
interface the orchestration decision has to satisfy, so they need to carry a whole run end to
end before a framework is chosen against them.

This is also the worked example. If a handoff reader wants to know what a run's data looks like,
this file is the answer, and it cannot go stale because it is executed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ireports_domain import (
    Actor,
    ApprovedFindingText,
    ASAPEnvelope,
    AuthorityRoute,
    AuthorityRoutingResult,
    Budgets,
    CaseContext,
    CaseManifest,
    Confidence,
    DecisionDomain,
    DeliveredFinding,
    DispositionedFinding,
    DispositionKind,
    DocumentExpectation,
    EnvelopeAnalysis,
    EnvelopeCase,
    EnvelopeIntegrity,
    EvidenceExcerpt,
    EvidenceRecord,
    EvidenceSpan,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    HumanDisposition,
    ModelAlias,
    OutboxMessage,
    PersonStatus,
    PolicyPackRef,
    PolicyPackStatus,
    PositionRiskLevel,
    PositionSensitivity,
    ProposedFinding,
    ReasonCode,
    RetrievalMode,
    RetrievalProvenance,
    ReviewerRole,
    ReviewSummary,
    ReviewUrgency,
    RoutingBasis,
    RunManifest,
    RunStatus,
    ServiceType,
    SourceReliability,
    Subject,
    ValidationOutcome,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CASE_ID = "AMI-SYN-MIX-003"
RUN_ID = "run_01J8ZQ"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


@pytest.fixture
def case() -> CaseManifest:
    return CaseManifest(
        case_id=CASE_ID,
        case_name="Foreign Ties, Outside Business, and Delinquent Debt",
        tenant_id="AMIVERO-SYNTHETIC",
        program_id="AMILENS-DEMO",
        subject=Subject(
            subject_id="SUBJ-003",
            display_name="Jordan Reyes",
            citizenship=["United States"],
        ),
        case_context=CaseContext(
            person_status=PersonStatus.APPLICANT,
            service_type=ServiceType.COMPETITIVE_SERVICE,
            position_title="Cybersecurity Program Manager",
            position_risk_level=PositionRiskLevel.HIGH_RISK_PUBLIC_TRUST,
            position_sensitivity=PositionSensitivity.CRITICAL_SENSITIVE,
            piv_required=True,
            conditional_offer_date=datetime(2026, 5, 14, tzinfo=UTC),
            agency_component="SYNTHETIC-AGENCY",
        ),
        requested_analyses=[
            DecisionDomain.SUITABILITY,
            DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        ],
        policy_pack_ids=["federal-core-2026-07-30", "sead4-current"],
        document_expectations=[
            DocumentExpectation.SECURITY_QUESTIONNAIRE,
            DocumentExpectation.REPORT_OF_INVESTIGATION,
            DocumentExpectation.SUBJECT_INTERVIEW,
        ],
        created_at=NOW,
        created_by="synthetic-fixture-builder",
    )


@pytest.fixture
def routing() -> AuthorityRoutingResult:
    """Every authority gets an explicit decision — including the two that do not apply."""
    return AuthorityRoutingResult(
        routes=[
            AuthorityRoute(
                decision_domain=DecisionDomain.SUITABILITY,
                applies=True,
                basis=RoutingBasis.EXPLICIT_CASE_METADATA,
                policy_pack_ids=["federal-core-2026-07-30"],
                rationale="competitive_service applicant with a designated position risk level",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
                applies=True,
                basis=RoutingBasis.EXPLICIT_CASE_METADATA,
                policy_pack_ids=["sead4-current"],
                rationale="position_sensitivity is critical_sensitive",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.FITNESS,
                applies=False,
                basis=RoutingBasis.DECLINED_NOT_APPLICABLE,
                rationale="no excepted-service or contractor fitness determination requested",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.PIV_CREDENTIALING,
                applies=False,
                basis=RoutingBasis.DECLINED_NOT_APPLICABLE,
                rationale="PIV credentialing is out of scope for the first release (ADR-003)",
            ),
        ],
        routed_at=NOW,
    )


@pytest.fixture
def evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="ev_101",
        case_id=CASE_ID,
        ingestion_id="ing_01J8ZP",
        span=EvidenceSpan(
            document_id="doc_roi_001",
            document_sha256=HASH_A,
            extractor_version="docling-2.14.0",
            page_number=12,
            block_index=4,
            char_start=1840,
            char_end=2104,
        ),
        text="Subject reported continuing contact with two siblings residing abroad.",
        text_sha256=HASH_B,
        source_reliability=SourceReliability.INVESTIGATOR_FINDING,
        retrieval=RetrievalProvenance(
            retrieval_mode=RetrievalMode.HYBRID,
            query_id="q_foreign_influence_001",
            rank=1,
            score=0.82,
            embedding_model_id="intfloat/e5-base-v2",
            embedding_model_revision="rev-2024-03",
            embedding_dimension=768,
        ),
        snapshot_at=NOW,
    )


@pytest.fixture
def finding() -> ProposedFinding:
    return ProposedFinding(
        finding_id="fnd_01J8ZR",
        run_id=RUN_ID,
        case_id=CASE_ID,
        authority=FindingAuthority(
            decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
            policy_pack_id="sead4-current",
            policy_id="SEAD-4",
            criterion_id="GUIDELINE-B",
            policy_citations=["pol_sead4_b_12", "pol_sead4_b_21"],
        ),
        classification=FindingClassification.POTENTIAL_ISSUE,
        title="Continuing foreign family and financial ties require officer review",
        observation=(
            "The record describes continuing contact with close relatives abroad and a "
            "minority interest in a foreign family business."
        ),
        policy_relevance=(
            "These facts may be relevant to foreign influence because they could create "
            "competing interests; the record also contains significant mitigating facts."
        ),
        supporting_evidence=["ev_101", "ev_114"],
        mitigating_evidence=["ev_122", "ev_124"],
        aggravating_factors=[
            "The business interest was omitted from the initial form and added during interview."
        ],
        mitigating_factors=[
            "Contacts were otherwise reported.",
            "The interest is noncontrolling and divestiture documentation is present.",
        ],
        evidence_confidence=Confidence.HIGH,
        analysis_confidence=Confidence.MODERATE,
        urgency=ReviewUrgency.NORMAL_REVIEW,
        recommended_officer_action=(
            "Review the cited records and resolve the open information gaps before disposition."
        ),
        generated_by=GeneratedBy(
            node="foreign_influence_specialist",
            model_alias=ModelAlias.THINKING,
            prompt_version="foreign-v4",
        ),
        validation=FindingValidation(
            schema_check=ValidationOutcome.PASSED,
            citations=ValidationOutcome.PASSED,
            policy_effective_date=ValidationOutcome.PASSED,
            protected_attribute_check=ValidationOutcome.PASSED,
            prohibited_language_check=ValidationOutcome.PASSED,
        ),
        proposed_at=NOW,
    )


@pytest.fixture
def policy_pack() -> PolicyPackRef:
    return PolicyPackRef(
        policy_pack_id="sead4-current",
        version="2026.07",
        content_sha256=HASH_C,
        status=PolicyPackStatus.APPROVED,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        decision_domains=[DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY],
    )


def _run(status: RunStatus, policy_pack: PolicyPackRef, **overrides: object) -> RunManifest:
    base: dict[str, object] = {
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "ingestion_id": "ing_01J8ZP",
        "started_at": NOW,
        "actor": Actor(actor_id="reviewer-17", roles=["case_analyst"]),
        "profile": "local_bedrock",
        "policy_packs": [policy_pack],
        "model_aliases": [ModelAlias.ORCHESTRATOR, ModelAlias.THINKING],
        "prompt_registry_version": "2026.08.1",
        "application_version": "0.1.0",
        "configuration_sha256": HASH_A,
        "budgets": Budgets(
            max_input_tokens=200_000, max_output_tokens=16_000, max_wall_clock_seconds=600
        ),
        "status": status,
    }
    return RunManifest(**(base | overrides))


# ---------------------------------------------------------------------------


def test_case_routes_to_two_authorities(
    case: CaseManifest, routing: AuthorityRoutingResult
) -> None:
    applied = {r.decision_domain for r in routing.routes if r.applies}
    assert applied == set(case.requested_analyses)
    assert not routing.has_blocking_gap


def test_missing_routing_metadata_produces_a_blocking_gap() -> None:
    """Blueprint §10.2: routing is never inferred from document content."""
    route = AuthorityRoute(
        decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        applies=False,
        basis=RoutingBasis.BLOCKED_MISSING_METADATA,
        rationale="position_sensitivity absent from case metadata",
        blocking_gap="position_sensitivity is required to route SEAD-4 and was not supplied",
    )
    assert route.blocking_gap
    with pytest.raises(ValidationError, match="requires a blocking_gap"):
        route.model_copy(update={"blocking_gap": None}).model_validate(
            route.model_dump() | {"blocking_gap": None}
        )


def test_policy_effectivity_is_a_date_comparison(policy_pack: PolicyPackRef) -> None:
    assert policy_pack.is_in_force_at(NOW)
    assert not policy_pack.is_in_force_at(datetime(2025, 6, 1, tzinfo=UTC))


def test_an_unapproved_policy_pack_cannot_be_referenced() -> None:
    """The design fails closed (blueprint §2.7)."""
    with pytest.raises(ValidationError, match="only 'approved' packs"):
        PolicyPackRef(
            policy_pack_id="sead4-draft",
            version="draft-1",
            content_sha256=HASH_C,
            status=PolicyPackStatus.DRAFT,
            effective_from=NOW,
            decision_domains=[DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY],
        )


def test_vector_retrieval_records_its_embedding_model(evidence: EvidenceRecord) -> None:
    """ADR-007 / Q-03: parity drift is silent, so provenance is mandatory."""
    assert evidence.retrieval.embedding_model_id == "intfloat/e5-base-v2"
    with pytest.raises(ValidationError, match="embedding_model_id"):
        RetrievalProvenance(retrieval_mode=RetrievalMode.HYBRID, query_id="q_1")


def test_a_run_cannot_reach_packaging_without_review(policy_pack: PolicyPackRef) -> None:
    with pytest.raises(ValidationError, match="requires human_review_recorded=True"):
        _run(RunStatus.PACKAGING, policy_pack)


def test_the_machine_proposal_is_immutable(finding: ProposedFinding) -> None:
    """ADR-011 depends on this: both versions are retained only if one cannot be edited."""
    with pytest.raises(ValidationError):
        finding.title = "Something else"  # type: ignore[misc]


@pytest.fixture
def bound(finding: ProposedFinding) -> DispositionedFinding:
    """A finding the officer modified and released — the input the packager consumes."""
    disposition = HumanDisposition(
        disposition_id="dsp_01J8ZS",
        finding_id=finding.finding_id,
        run_id=RUN_ID,
        reviewer_id="officer-42",
        reviewer_role=ReviewerRole.AUTHORIZED_ADJUDICATIVE_OFFICER,
        reviewed_at=NOW,
        disposition=DispositionKind.MODIFIED_AND_ACCEPTED,
        reason_codes=[ReasonCode.MITIGATION_ADDED, ReasonCode.WORDING_NARROWED],
        reviewer_summary=(
            "Retained for review; added evidence of completed divestiture and removed the "
            "unsupported reference to financial dependence."
        ),
        approved_text=ApprovedFindingText(
            version=2,
            title="Continuing foreign family ties require officer review",
            observation="The record describes continuing contact with close relatives abroad.",
            policy_relevance="These facts may be relevant to foreign influence.",
            recommended_officer_action="Review the cited records before disposition.",
        ),
        release_to_asap=True,
    )
    return DispositionedFinding(proposal=finding, disposition=disposition)


def test_modification_retains_both_versions(bound: DispositionedFinding) -> None:
    # The approved wording is what delivery carries...
    assert bound.effective_title == "Continuing foreign family ties require officer review"
    # ...and the machine proposal is still there, unchanged.
    assert (
        bound.proposal.title
        == "Continuing foreign family and financial ties require officer review"
    )
    assert bound.is_releasable


def test_disposition_cannot_be_bound_to_the_wrong_finding(finding: ProposedFinding) -> None:
    other = HumanDisposition(
        disposition_id="dsp_01",
        finding_id="fnd_other",
        run_id=RUN_ID,
        reviewer_id="officer-42",
        reviewer_role=ReviewerRole.AUTHORIZED_ADJUDICATIVE_OFFICER,
        reviewed_at=NOW,
        disposition=DispositionKind.ACCEPTED,
        reason_codes=[ReasonCode.ACCURATE_AS_PROPOSED],
        reviewer_summary="Accurate as proposed.",
        release_to_asap=True,
    )
    with pytest.raises(ValidationError, match="does not match the proposal"):
        DispositionedFinding(proposal=finding, disposition=other)


def _envelope(
    case: CaseManifest, finding: ProposedFinding, bound: DispositionedFinding, **overrides: object
) -> ASAPEnvelope:
    base: dict[str, object] = {
        "message_id": "msg_01J8ZT",
        "idempotency_key": f"{CASE_ID}:{RUN_ID}:approved-v2",
        "created_at": NOW,
        "case": EnvelopeCase(
            case_id=CASE_ID,
            program_id=case.program_id,
            subject_id=case.subject.subject_id,
            ingestion_id="ing_01J8ZP",
        ),
        "analysis": EnvelopeAnalysis(
            run_id=RUN_ID,
            policy_pack_ids=["sead4-current"],
            model_aliases=[ModelAlias.THINKING],
            findings=[
                DeliveredFinding(
                    finding_id=finding.finding_id,
                    machine_proposal_finding_id=finding.finding_id,
                    decision_domain=finding.authority.decision_domain,
                    policy_pack_id=finding.authority.policy_pack_id,
                    policy_id=finding.authority.policy_id,
                    criterion_id=finding.authority.criterion_id,
                    policy_citations=list(finding.authority.policy_citations),
                    classification=finding.classification,
                    title=bound.effective_title,
                    observation=bound.effective_observation,
                    policy_relevance=bound.effective_policy_relevance,
                    recommended_officer_action=bound.effective_officer_action,
                    supporting_evidence=[
                        EvidenceExcerpt(
                            evidence_id="ev_101",
                            excerpt="Subject reported continuing contact with two siblings abroad.",
                            text_sha256=HASH_B,
                            document_reference="/authorized/evidence/ev_101",
                            page_number=12,
                            source_reliability=SourceReliability.INVESTIGATOR_FINDING,
                        )
                    ],
                    evidence_confidence=finding.evidence_confidence,
                    analysis_confidence=finding.analysis_confidence,
                    urgency=finding.urgency,
                    human_disposition=bound.disposition.disposition.value,
                    reviewer_modified=True,
                )
            ],
        ),
        "integrity": EnvelopeIntegrity(payload_sha256=HASH_C),
    }
    return ASAPEnvelope(**(base | overrides))


def test_full_chain_reaches_a_delivered_envelope(
    case: CaseManifest,
    finding: ProposedFinding,
    bound: DispositionedFinding,
    policy_pack: PolicyPackRef,
) -> None:
    """The whole path: reviewed run → releasable finding → envelope → outbox message."""
    review = ReviewSummary(
        run_id=RUN_ID,
        reviewer_id="officer-42",
        reviewer_role=ReviewerRole.AUTHORIZED_ADJUDICATIVE_OFFICER,
        completed_at=NOW,
        dispositions=[bound.disposition],
    )
    assert review.covers([finding.finding_id])
    assert review.releasable_finding_ids == [finding.finding_id]

    run = _run(
        RunStatus.PACKAGING,
        policy_pack,
        human_review_recorded=True,
        proposed_finding_ids=[finding.finding_id],
    )
    assert run.human_review_recorded

    envelope = _envelope(case, finding, bound)

    # ADR-010: excerpts *and* references, so a finding is reviewable without a second lookup.
    excerpt = envelope.analysis.findings[0].supporting_evidence[0]
    assert excerpt.excerpt and excerpt.document_reference

    outbox = OutboxMessage(
        message_id=envelope.message_id,
        run_id=RUN_ID,
        case_id=CASE_ID,
        idempotency_key=envelope.idempotency_key,
        payload_sha256=HASH_C,
        created_at=NOW,
    )
    assert outbox.idempotency_key == envelope.idempotency_key

    # Round-trips through JSON without loss — the contract has to survive a checkpoint.
    assert ASAPEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


def test_idempotency_key_must_be_traceable_to_its_case(
    case: CaseManifest, finding: ProposedFinding, bound: DispositionedFinding
) -> None:
    """A random key would deliver correctly but be untraceable during an incident."""
    with pytest.raises(ValidationError, match="must begin with the case_id"):
        _envelope(case, finding, bound, idempotency_key="random-uuid-value")


def test_an_envelope_cannot_be_built_with_no_findings(
    case: CaseManifest, finding: ProposedFinding, bound: DispositionedFinding
) -> None:
    """An empty envelope would deliver 'nothing found' without a human ever saying so."""
    with pytest.raises(ValidationError, match="at least 1 item"):
        EnvelopeAnalysis(
            run_id=RUN_ID,
            policy_pack_ids=["sead4-current"],
            model_aliases=[ModelAlias.THINKING],
            findings=[],
        )
