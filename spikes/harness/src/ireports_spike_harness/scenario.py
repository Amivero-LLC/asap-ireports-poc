"""The bake-off scenario: shared node bodies, identical across all candidates.

Every candidate wires *these* functions. None of them reimplements the work.

That is the whole design. ADR-012 scores "framework-specific lines of code", and that number is
meaningless if each spike also carries its own slightly different node implementations — the
count would measure how verbosely each author wrote a specialist, not how much orchestration
scaffolding the framework demands. With the bodies shared, a candidate's line count is exactly
its wiring, and its output is exactly comparable to the others'.

The nodes are pure with respect to orchestration: they take their inputs and the gateway, and
return contract objects. They do not checkpoint, retry, branch, or decide what runs next. That
is the deterministic shell's job (`CLAUDE.md`), and it is the thing under measurement.

Identifiers are derived, never random. A resumed run must produce the same `finding_id` for the
same criterion, or de-duplication and idempotency both become untestable — and a candidate that
loses work would be indistinguishable from one that merely renamed it.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ireports_domain import (
    Actor,
    ASAPEnvelope,
    AuthorityRoute,
    AuthorityRoutingResult,
    Budgets,
    CaseContext,
    CaseManifest,
    Confidence,
    DecisionDomain,
    DeliveredFinding,
    EnvelopeAnalysis,
    EnvelopeCase,
    EnvelopeIntegrity,
    EvidenceExcerpt,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    ModelAlias,
    PersonStatus,
    PolicyPackRef,
    PolicyPackStatus,
    PositionRiskLevel,
    PositionSensitivity,
    ProposedFinding,
    RoutingBasis,
    RunManifest,
    ServiceType,
    SourceReliability,
    Subject,
    ValidationOutcome,
)

from ireports_spike_harness.bakeoff_v1_contracts import BakeoffRunStatus as RunStatus
from ireports_spike_harness.bakeoff_v1_contracts import DispositionedFinding

from .gateway import StubModelGateway

FIXED_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
"""Frozen clock.

Test determinism is a scored dimension. A wall clock would make serialized checkpoint bytes
differ between runs, which would turn "serialized state size" into noise and make byte-level
comparison of a resumed checkpoint impossible.
"""

CASE_ID = "AMI-SYN-MIX-003"
SUITABILITY_PACK = "federal-core-2026-07-30"
SEAD4_PACK = "sead4-current"
HASH_ZERO = "0" * 64

SPECIALIST_NODES: tuple[str, ...] = (
    "specialist_suitability",
    "specialist_national_security",
)
"""The bounded parallel fan-out (leg 4). Two, because two is enough to expose a join bug."""

DOMAIN_FOR_NODE: dict[str, DecisionDomain] = {
    "specialist_suitability": DecisionDomain.SUITABILITY,
    "specialist_national_security": DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
}

PACK_FOR_DOMAIN: dict[DecisionDomain, str] = {
    DecisionDomain.SUITABILITY: SUITABILITY_PACK,
    DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY: SEAD4_PACK,
}

POLICY_ID_FOR_DOMAIN: dict[DecisionDomain, str] = {
    DecisionDomain.SUITABILITY: "5-CFR-731",
    DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY: "SEAD-4",
}


def _derived_id(prefix: str, *parts: str) -> str:
    """A stable identifier derived from its content."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}_{digest}"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def build_case() -> CaseManifest:
    """The single synthetic case the bake-off runs. Routes to two authorities."""
    return CaseManifest(
        case_id=CASE_ID,
        case_name="Foreign Ties, Outside Business, and Delinquent Debt",
        tenant_id="AMIVERO-SYNTHETIC",
        program_id="AMILENS-DEMO",
        subject=Subject(subject_id="SUBJ-003", display_name="Jordan Reyes"),
        case_context=CaseContext(
            person_status=PersonStatus.APPLICANT,
            service_type=ServiceType.COMPETITIVE_SERVICE,
            position_title="Cybersecurity Program Manager",
            position_risk_level=PositionRiskLevel.HIGH_RISK_PUBLIC_TRUST,
            position_sensitivity=PositionSensitivity.CRITICAL_SENSITIVE,
            agency_component="SYNTHETIC-AGENCY",
        ),
        requested_analyses=[
            DecisionDomain.SUITABILITY,
            DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        ],
        policy_pack_ids=[SUITABILITY_PACK, SEAD4_PACK],
        created_at=FIXED_NOW,
        created_by="spike-harness",
    )


def policy_packs() -> list[PolicyPackRef]:
    return [
        PolicyPackRef(
            policy_pack_id=SUITABILITY_PACK,
            version="2026.07",
            content_sha256=HASH_ZERO,
            status=PolicyPackStatus.APPROVED,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            decision_domains=[DecisionDomain.SUITABILITY, DecisionDomain.FITNESS],
        ),
        PolicyPackRef(
            policy_pack_id=SEAD4_PACK,
            version="2026.07",
            content_sha256=HASH_ZERO,
            status=PolicyPackStatus.APPROVED,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            decision_domains=[DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY],
        ),
    ]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def initialize(case: CaseManifest, run_id: str) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        case_id=case.case_id,
        ingestion_id="ing_spike",
        started_at=FIXED_NOW,
        actor=Actor(actor_id="spike-harness", roles=["case_analyst"]),
        profile="spike_stub_gateway",
        policy_packs=policy_packs(),
        model_aliases=[ModelAlias.ORCHESTRATOR, ModelAlias.THINKING],
        prompt_registry_version="spike.1",
        application_version="0.1.0",
        configuration_sha256=HASH_ZERO,
        budgets=Budgets(
            max_input_tokens=100_000,
            max_output_tokens=8_000,
            max_wall_clock_seconds=120,
            max_parallel_specialists=2,
        ),
        status=RunStatus.INITIALIZING,
    )


def route(case: CaseManifest) -> AuthorityRoutingResult:
    """Deterministic authority routing — ordinary code, never a model call.

    Note there is no gateway parameter. `CLAUDE.md`: the model reasons, it does not decide
    control flow. Routing decides which specialists run, so it cannot be a model's job.
    """
    ctx = case.case_context
    return AuthorityRoutingResult(
        routes=[
            AuthorityRoute(
                decision_domain=DecisionDomain.SUITABILITY,
                applies=ctx.position_risk_level is not None,
                basis=RoutingBasis.EXPLICIT_CASE_METADATA,
                policy_pack_ids=[SUITABILITY_PACK] if ctx.position_risk_level else [],
                rationale="position_risk_level is designated in explicit case metadata",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
                applies=ctx.position_sensitivity is not None,
                basis=RoutingBasis.EXPLICIT_CASE_METADATA,
                policy_pack_ids=[SEAD4_PACK] if ctx.position_sensitivity else [],
                rationale="position_sensitivity is designated in explicit case metadata",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.FITNESS,
                applies=False,
                basis=RoutingBasis.DECLINED_NOT_APPLICABLE,
                rationale="no fitness determination requested for a competitive-service applicant",
            ),
            AuthorityRoute(
                decision_domain=DecisionDomain.PIV_CREDENTIALING,
                applies=False,
                basis=RoutingBasis.DECLINED_NOT_APPLICABLE,
                rationale="PIV credentialing is out of scope for the first release (ADR-003)",
            ),
        ],
        routed_at=FIXED_NOW,
    )


def specialist(node_id: str, run_id: str, gateway: StubModelGateway) -> list[ProposedFinding]:
    """One criterion specialist. Calls the gateway once, returns typed proposals.

    This is the only node that touches a model, and it is the one the fan-out runs twice.
    """
    domain = DOMAIN_FOR_NODE[node_id]
    response = gateway.complete(node_id)

    findings: list[ProposedFinding] = []
    for observation in response["observations"]:
        criterion_id = observation["criterion_id"]
        findings.append(
            ProposedFinding(
                finding_id=_derived_id("fnd", run_id, domain.value, criterion_id),
                run_id=run_id,
                case_id=CASE_ID,
                authority=FindingAuthority(
                    decision_domain=domain,
                    policy_pack_id=PACK_FOR_DOMAIN[domain],
                    policy_id=POLICY_ID_FOR_DOMAIN[domain],
                    criterion_id=criterion_id,
                    policy_citations=[_derived_id("pol", domain.value, criterion_id)],
                ),
                classification=FindingClassification.POTENTIAL_ISSUE,
                title=observation["title"],
                observation=observation["observation"],
                policy_relevance=observation["policy_relevance"],
                supporting_evidence=observation["supporting_evidence"],
                mitigating_evidence=observation["mitigating_evidence"],
                evidence_confidence=Confidence.HIGH,
                analysis_confidence=Confidence.MODERATE,
                recommended_officer_action=(
                    "Review the cited records and resolve any open gaps before disposition."
                ),
                generated_by=GeneratedBy(
                    node=node_id,
                    model_alias=ModelAlias.THINKING,
                    prompt_version="spike-v1",
                ),
                validation=FindingValidation(
                    schema_check=ValidationOutcome.PASSED,
                    citations=ValidationOutcome.PASSED,
                    policy_effective_date=ValidationOutcome.PASSED,
                    protected_attribute_check=ValidationOutcome.PASSED,
                    prohibited_language_check=ValidationOutcome.PASSED,
                ),
                proposed_at=FIXED_NOW,
            )
        )
    return findings


def join_and_dedupe(results: list[list[ProposedFinding]]) -> list[ProposedFinding]:
    """Fan-in (leg 4).

    De-duplicates on `finding_id`, which is derived from `(run_id, domain, criterion)`. That
    keys de-duplication on the *authority*, so the same underlying conduct analysed under both
    5 CFR 731 and SEAD-4 correctly survives as two findings. A dedupe keyed on the conduct alone
    would silently drop one authority's view — the exact failure blueprint §2.1 warns about, and
    the reason this node is worth measuring rather than stubbing.

    Sorted output, because an unordered join makes checkpoint bytes non-deterministic and would
    let a candidate that reorders work on resume look identical to one that does not.
    """
    seen: dict[str, ProposedFinding] = {}
    for batch in results:
        for finding in batch:
            seen.setdefault(finding.finding_id, finding)
    return sorted(seen.values(), key=lambda f: f.finding_id)


def validate(findings: list[ProposedFinding]) -> list[ProposedFinding]:
    """The deterministic validator gate.

    Trivial here on purpose. Real citation and effectivity validation is Milestone 2; the spike
    only needs a node between fan-in and the human gate so that candidates must model a
    sequential step after a parallel one.
    """
    return [f for f in findings if f.validation.passed]


def package(
    case: CaseManifest, run_id: str, dispositioned: list[DispositionedFinding]
) -> ASAPEnvelope:
    """Build the delivery envelope from human-approved findings only (ADR-011)."""
    releasable = [d for d in dispositioned if d.is_releasable]
    if not releasable:
        raise ValueError("package called with no released findings; the review gate did not pass")

    return ASAPEnvelope(
        message_id=_derived_id("msg", run_id),
        idempotency_key=f"{case.case_id}:{run_id}:approved-v1",
        created_at=FIXED_NOW,
        case=EnvelopeCase(
            case_id=case.case_id,
            program_id=case.program_id,
            subject_id=case.subject.subject_id,
            ingestion_id="ing_spike",
        ),
        analysis=EnvelopeAnalysis(
            run_id=run_id,
            policy_pack_ids=[SUITABILITY_PACK, SEAD4_PACK],
            model_aliases=[ModelAlias.THINKING],
            findings=[
                DeliveredFinding(
                    finding_id=d.proposal.finding_id,
                    machine_proposal_finding_id=d.proposal.finding_id,
                    decision_domain=d.proposal.authority.decision_domain,
                    policy_pack_id=d.proposal.authority.policy_pack_id,
                    policy_id=d.proposal.authority.policy_id,
                    criterion_id=d.proposal.authority.criterion_id,
                    policy_citations=list(d.proposal.authority.policy_citations),
                    classification=d.proposal.classification,
                    title=d.effective_title,
                    observation=d.effective_observation,
                    policy_relevance=d.effective_policy_relevance,
                    recommended_officer_action=d.effective_officer_action,
                    supporting_evidence=[
                        EvidenceExcerpt(
                            evidence_id=evidence_id,
                            excerpt="Synthetic excerpt for the orchestration spike.",
                            text_sha256=HASH_ZERO,
                            document_reference=f"/authorized/evidence/{evidence_id}",
                            source_reliability=SourceReliability.INVESTIGATOR_FINDING,
                        )
                        for evidence_id in d.proposal.supporting_evidence
                    ],
                    evidence_confidence=d.proposal.evidence_confidence,
                    analysis_confidence=d.proposal.analysis_confidence,
                    urgency=d.proposal.urgency,
                    # `human_disposition` and `reviewer_modified` were passed here until
                    # ADR-022 removed them from DeliveredFinding. No leg asserts on either.
                )
                for d in sorted(releasable, key=lambda d: d.proposal.finding_id)
            ],
        ),
        integrity=EnvelopeIntegrity(payload_sha256=HASH_ZERO),
    )


EXPECTED_FINDING_COUNT = 3
"""Suitability 731.202(b)(4) (de-duplicated from two), SEAD-4 Guideline F, SEAD-4 Guideline B.

Asserted by the conformance suite. If a candidate produces two, it dropped an authority in the
join; if four, it failed to de-duplicate; if six, it re-ran a specialist and merged both passes.
"""
