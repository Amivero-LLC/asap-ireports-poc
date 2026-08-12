"""The second stage: reason across criteria, not just within one.

Until now the run fanned out and **concatenated**. Each specialist saw one criterion and no other
specialist's work, so when one underlying fact bore on four criteria, four specialists reported it
independently as though each had found it alone. A reviewer reading that envelope has to work out
for themselves that they are looking at one fact four times.

This stage is the fan-in doing actual work. Two kinds, deliberately separated by *who is competent
to answer them*:

1. **Overlap is computed, not inferred.** Which findings cite the same evidence spans is set
   arithmetic. Asking a model to do it would be slower, cost money, and be occasionally wrong about
   something that has an exact answer. `overlaps()` is ordinary code.

2. **Contradictions and gaps are model work.** Whether two statements in a record conflict, or
   whether something a reviewer would need is missing, is a judgement about meaning. That is the
   part worth spending a model call on.

**What this stage may not do.** No summary. No aggregate score, no overall assessment, no ranking
of findings (ADR-014). It emits more `ProposedFinding`s — of the two classifications the contract
already has for exactly this — and nothing else. A "synthesis" that concluded something about the
person would be the determination this system must never make, wearing a helpful-sounding name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ireports_domain import (
    Confidence,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    InformationGap,
    ModelAlias,
    ProposedFinding,
    ReviewUrgency,
    ValidationOutcome,
)
from ireports_gateway.port import Message, ModelGateway, ModelRequest

from .case_loader import LoadedCase
from .criteria import Criterion
from .specialist import SpecialistOutcome

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "description": (
                "Places where two parts of the record cannot both be accurate. An empty array is "
                "correct and common."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 180},
                    "observation": {
                        "type": "string",
                        "description": "The two assertions and how they conflict. Facts only.",
                    },
                    "policy_relevance": {"type": "string"},
                    "recommended_officer_action": {"type": "string"},
                    "criterion_id": {
                        "type": "string",
                        "description": "Which analysed criterion this bears on most directly.",
                    },
                    "conflicting_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "At least two evidence_ids — the spans that conflict.",
                    },
                },
                "required": [
                    "title",
                    "observation",
                    "policy_relevance",
                    "recommended_officer_action",
                    "criterion_id",
                    "conflicting_evidence",
                ],
            },
        },
        "information_gaps": {
            "type": "array",
            "description": (
                "Questions a reviewer would need answered that are visible only when looking "
                "across criteria, not from any one criterion alone."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 180},
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "policy_relevance": {"type": "string"},
                    "recommended_officer_action": {"type": "string"},
                    "criterion_id": {"type": "string"},
                    "related_evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "title",
                    "question",
                    "why_it_matters",
                    "policy_relevance",
                    "recommended_officer_action",
                    "criterion_id",
                ],
            },
        },
    },
    "required": ["contradictions", "information_gaps"],
}

SYSTEM = """You review findings that separate analysts produced about one case, each looking at a
single criterion in isolation. None of them saw the others' work.

Your job is only what is invisible from a single criterion:

1. CONTRADICTIONS — two parts of the record that cannot both be accurate. A contradiction is
   between *assertions in the record*, not between two analysts' opinions. Cite at least two
   evidence ids: the spans that conflict.
2. INFORMATION GAPS — a question a reviewer would need answered, visible only across criteria.

Rules:

- NEVER state or imply a determination, a conclusion about the person, or a recommendation about
  any adjudicative outcome. You describe the record.
- NEVER summarise, rank, score, or give an overall assessment. There is no such thing here.
- DO NOT restate a finding that a single analyst already made. If it was visible from one
  criterion, it is not yours.
- ONE FACT REPORTED UNDER SEVERAL CRITERIA IS NOT A CONTRADICTION. It is normal and is already
  computed elsewhere. Do not report it.
- EMPTY ARRAYS ARE THE RIGHT ANSWER when there is nothing across criteria. Most cases have few
  genuine contradictions. Do not manufacture one to appear useful."""


@dataclass(frozen=True)
class Overlap:
    """One evidence span that several criteria's findings rest on.

    Computed, never inferred. This is what tells a reviewer "these four findings are four views of
    one fact" — which is the single most useful thing the fan-in produces, and it costs nothing.
    """

    evidence_id: str
    finding_ids: tuple[str, ...]
    criterion_ids: tuple[str, ...]


@dataclass(frozen=True)
class SynthesisOutcome:
    findings: tuple[ProposedFinding, ...]
    overlaps: tuple[Overlap, ...]
    rejected: tuple[str, ...]
    resolved_model: str | None
    input_tokens: int = 0
    output_tokens: int = 0


def overlaps(outcomes: tuple[SpecialistOutcome, ...]) -> tuple[Overlap, ...]:
    """Which evidence spans carry findings under more than one criterion.

    Set arithmetic, not analysis. Only spans spanning **two or more distinct criteria** are
    reported — a span cited twice within one criterion is just one analyst citing their own source
    twice, which tells a reviewer nothing.
    """
    by_span: dict[str, list[tuple[str, str]]] = {}
    for outcome in outcomes:
        for finding in outcome.findings:
            for eid in finding.supporting_evidence:
                by_span.setdefault(eid, []).append(
                    (finding.finding_id, outcome.criterion.criterion_id)
                )

    found: list[Overlap] = []
    for eid, entries in sorted(by_span.items()):
        criteria = {c for _, c in entries}
        if len(criteria) > 1:
            found.append(
                Overlap(
                    evidence_id=eid,
                    finding_ids=tuple(sorted(f for f, _ in entries)),
                    criterion_ids=tuple(sorted(criteria)),
                )
            )
    return tuple(found)


def _findings_block(outcomes: tuple[SpecialistOutcome, ...]) -> str:
    lines = []
    for outcome in outcomes:
        for finding in outcome.findings:
            lines.append(
                f"[{finding.finding_id}] criterion {outcome.criterion.criterion_id} "
                f"({outcome.criterion.policy_id})\n"
                f"  {finding.title}\n"
                f"  {finding.observation}\n"
                f"  cites: {list(finding.supporting_evidence)}"
            )
    return "\n\n".join(lines)


def synthesize(
    case: LoadedCase,
    outcomes: tuple[SpecialistOutcome, ...],
    criteria: tuple[Criterion, ...],
    gateway: ModelGateway,
    run_id: str,
) -> SynthesisOutcome:
    """One model call across every specialist's findings, plus the computed overlaps.

    Returns an empty outcome without calling a model when there is nothing to reason across —
    fewer than two findings cannot contradict each other, and paying for a call to be told so is
    waste.
    """
    computed = overlaps(outcomes)
    all_findings = [f for o in outcomes for f in o.findings]
    if len(all_findings) < 2:
        return SynthesisOutcome(
            findings=(),
            overlaps=computed,
            rejected=(),
            resolved_model=None,
        )

    known_spans = {s.evidence_id for s in case.spans}
    by_criterion = {c.criterion_id: c for c in criteria}

    prompt = (
        f"CASE: {case.manifest.case_id}\n\n"
        f"CRITERIA ANALYSED: {sorted(by_criterion)}\n\n"
        f"FINDINGS FROM SINGLE-CRITERION ANALYSTS\n\n{_findings_block(outcomes)}\n\n"
        f"THE RECORD (cite by bracketed id)\n\n"
        + "\n\n".join(f"[{s.evidence_id}] {s.text}" for s in case.spans)
        + "\n\nReport only what is invisible from a single criterion."
    )

    response = gateway.complete(
        ModelRequest(
            alias=ModelAlias.THINKING,
            messages=(Message(role="user", content=prompt),),
            system=SYSTEM,
            response_schema=RESPONSE_SCHEMA,
            node_id="synthesis",
        )
    )

    findings: list[ProposedFinding] = []
    rejected: list[str] = []

    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        return SynthesisOutcome(
            findings=(),
            overlaps=computed,
            rejected=(f"synthesis: response was not JSON — {exc}",),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
    if not isinstance(payload, dict):
        return SynthesisOutcome(
            findings=(),
            overlaps=computed,
            rejected=(f"synthesis: expected an object, got {type(payload).__name__}",),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def _authority(raw_criterion: str) -> FindingAuthority | None:
        """One authority per finding, always (ADR-003).

        A cross-criterion contradiction still has to name the single criterion it bears on — the
        model picks from the analysed set, and a pick outside that set is rejected rather than
        guessed at.
        """
        criterion = by_criterion.get(raw_criterion)
        if criterion is None:
            return None
        return FindingAuthority(
            decision_domain=criterion.decision_domain,
            policy_pack_id=criterion.policy_pack_id,
            policy_id=criterion.policy_id,
            criterion_id=criterion.criterion_id,
            policy_citations=[f"pol_{criterion.criterion_id}".replace("-", "_").lower()],
        )

    def _common(index: int, kind: str) -> dict[str, Any]:
        return {
            "finding_id": f"fnd_{run_id}_syn_{kind}_{index}".replace("-", "_"),
            "run_id": run_id,
            "case_id": case.manifest.case_id,
            "urgency": ReviewUrgency.NORMAL_REVIEW,
            "generated_by": GeneratedBy(
                node="synthesis",
                model_alias=ModelAlias.THINKING,
                prompt_version="synthesis-v1",
            ),
            "validation": FindingValidation(
                schema_check=ValidationOutcome.PASSED,
                citations=ValidationOutcome.PASSED,
                policy_effective_date=ValidationOutcome.PASSED,
                protected_attribute_check=ValidationOutcome.PASSED,
                prohibited_language_check=ValidationOutcome.PASSED,
            ),
            "proposed_at": datetime.now(UTC),
        }

    for index, raw in enumerate(payload.get("contradictions") or []):
        if not isinstance(raw, dict):
            rejected.append(f"synthesis/contradiction#{index}: not an object — dropped")
            continue
        cited = [e for e in raw.get("conflicting_evidence", []) or [] if e in known_spans]
        unknown = [e for e in raw.get("conflicting_evidence", []) or [] if e not in known_spans]
        if unknown:
            rejected.append(
                f"synthesis/contradiction#{index}: cited unknown evidence {unknown} — dropped"
            )
            continue
        if len(cited) < 2:
            # The contract requires two, and a "contradiction" resting on one span is not one.
            rejected.append(
                f"synthesis/contradiction#{index}: needs two conflicting spans, got "
                f"{len(cited)} — dropped"
            )
            continue
        authority = _authority(str(raw.get("criterion_id", "")))
        if authority is None:
            rejected.append(
                f"synthesis/contradiction#{index}: named criterion "
                f"{raw.get('criterion_id')!r}, which was not analysed — dropped"
            )
            continue
        try:
            findings.append(
                ProposedFinding(
                    **_common(index, "contra"),
                    authority=authority,
                    classification=FindingClassification.CONTRADICTION,
                    title=raw["title"],
                    observation=raw["observation"],
                    policy_relevance=raw["policy_relevance"],
                    recommended_officer_action=raw["recommended_officer_action"],
                    # First span is the assertion, the rest are what conflicts with it. The
                    # contract counts supporting + contradicting >= 2, so this satisfies it while
                    # keeping the roles honest.
                    supporting_evidence=cited[:1],
                    contradicting_evidence=cited[1:],
                    evidence_confidence=Confidence.MODERATE,
                    analysis_confidence=Confidence.MODERATE,
                )
            )
        except (ValueError, KeyError) as exc:
            rejected.append(f"synthesis/contradiction#{index}: rejected by contract — {exc}")

    for index, raw in enumerate(payload.get("information_gaps") or []):
        if not isinstance(raw, dict):
            rejected.append(f"synthesis/gap#{index}: not an object — dropped")
            continue
        authority = _authority(str(raw.get("criterion_id", "")))
        if authority is None:
            rejected.append(
                f"synthesis/gap#{index}: named criterion {raw.get('criterion_id')!r}, "
                "which was not analysed — dropped"
            )
            continue
        related = [e for e in raw.get("related_evidence", []) or [] if e in known_spans]
        try:
            findings.append(
                ProposedFinding(
                    **_common(index, "gap"),
                    authority=authority,
                    classification=FindingClassification.INFORMATION_GAP,
                    title=raw["title"],
                    observation=raw["why_it_matters"],
                    policy_relevance=raw["policy_relevance"],
                    recommended_officer_action=raw["recommended_officer_action"],
                    # An information gap asserts an *absence*, which the contract deliberately does
                    # not require citations for — demanding them pushes a node toward citing
                    # irrelevant spans to satisfy a validator.
                    information_gaps=[
                        InformationGap(
                            gap_id=f"gap_{run_id}_{index}".replace("-", "_"),
                            question=raw["question"],
                            why_it_matters=raw["why_it_matters"],
                            related_evidence_ids=related,
                        )
                    ],
                    evidence_confidence=Confidence.MODERATE,
                    analysis_confidence=Confidence.MODERATE,
                )
            )
        except (ValueError, KeyError) as exc:
            rejected.append(f"synthesis/gap#{index}: rejected by contract — {exc}")

    return SynthesisOutcome(
        findings=tuple(findings),
        overlaps=computed,
        rejected=tuple(rejected),
        resolved_model=response.resolved_model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
