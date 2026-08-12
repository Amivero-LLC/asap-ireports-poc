"""Turn proposed findings into a validated `ASAPEnvelope` — the run's actual output.

This is where the decision-support boundary becomes visible in the artifact rather than in prose.
The envelope is pinned `machine_generated: true`, carries no field claiming review or approval,
and every finding in it is a proposal (ADR-022). An officer reviews it in ASAP afterwards.

Two shortcuts are taken here and both are named rather than hidden:

- **Evidence excerpts are read from the case file, not from an evidence store.** ADR-010 requires
  bounded excerpts *plus* stable references so a finding is reviewable on arrival. The excerpts
  are real; the `document_reference` is synthesised from the case path because there is no
  authorization-checked store to reference yet.
- **`payload_sha256` is computed over the envelope's own analysis section.** Real integrity
  signing is agreed with ASAP under Q-04, which is open.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ireports_domain import (
    ASAPEnvelope,
    DeliveredFinding,
    EnvelopeAnalysis,
    EnvelopeCase,
    EnvelopeIntegrity,
    EvidenceExcerpt,
    ModelAlias,
    ProposedFinding,
)
from ireports_domain.asap import MAX_EXCERPT_CHARS

from .case_loader import LoadedCase


def _excerpts(case: LoadedCase, evidence_ids: tuple[str, ...]) -> list[EvidenceExcerpt]:
    by_id = {s.evidence_id: s for s in case.spans}
    out: list[EvidenceExcerpt] = []
    for eid in evidence_ids:
        span = by_id.get(eid)
        if span is None:
            # Unreachable via the specialist, which drops unresolvable citations before a finding
            # is constructed. Kept because "unreachable" is a claim about today's callers.
            continue
        text = span.text
        out.append(
            EvidenceExcerpt(
                evidence_id=span.evidence_id,
                excerpt=text[:MAX_EXCERPT_CHARS],
                truncated=len(text) > MAX_EXCERPT_CHARS,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                document_reference=f"synthetic://{case.manifest.case_id}/{span.document_id}",
                page_number=span.page_number,
            )
        )
    return out


def build_envelope(
    case: LoadedCase,
    findings: tuple[ProposedFinding, ...],
    run_id: str,
) -> ASAPEnvelope:
    """One envelope per completed run. Raises if `findings` is empty — see below."""
    if not findings:
        # `EnvelopeAnalysis.findings` has min_length=1, deliberately: an empty envelope would
        # deliver "nothing found" as though it were a result. A run with no findings should not
        # produce an envelope at all, and the caller decides what to do about that.
        raise ValueError(
            "no findings survived validation, so there is no envelope to build. An empty "
            "envelope would assert 'nothing found', which is a claim this run cannot make."
        )

    delivered = [
        DeliveredFinding(
            finding_id=f.finding_id,
            machine_proposal_finding_id=f.finding_id,
            decision_domain=f.authority.decision_domain,
            policy_pack_id=f.authority.policy_pack_id,
            policy_id=f.authority.policy_id,
            criterion_id=f.authority.criterion_id,
            policy_citations=list(f.authority.policy_citations),
            classification=f.classification,
            title=f.title,
            observation=f.observation,
            policy_relevance=f.policy_relevance,
            recommended_officer_action=f.recommended_officer_action,
            supporting_evidence=_excerpts(case, f.supporting_evidence),
            mitigating_evidence=_excerpts(case, f.mitigating_evidence),
            evidence_confidence=f.evidence_confidence,
            analysis_confidence=f.analysis_confidence,
            urgency=f.urgency,
        )
        for f in findings
    ]

    analysis = EnvelopeAnalysis(
        run_id=run_id,
        policy_pack_ids=sorted({f.authority.policy_pack_id for f in findings}),
        model_aliases=[ModelAlias.THINKING],
        findings=delivered,
    )

    payload = analysis.model_dump_json().encode()
    return ASAPEnvelope(
        message_id=f"msg_{run_id}",
        idempotency_key=f"{case.manifest.case_id}:{run_id}:v1",
        created_at=datetime.now(UTC),
        case=EnvelopeCase(
            case_id=case.manifest.case_id,
            program_id=case.manifest.program_id,
            subject_id=case.manifest.subject.subject_id,
            ingestion_id=f"ing_{case.manifest.case_id}",
        ),
        analysis=analysis,
        integrity=EnvelopeIntegrity(payload_sha256=hashlib.sha256(payload).hexdigest()),
    )
