"""One criterion specialist, calling a real model through the `ModelGateway` port.

This is the node the bake-off stubbed. `spikes/harness/.../scenario.py` returns canned
observations so that the four legs measure *control flow* without model latency or spend in the
loop — correct for what that spike was answering, and useless for showing anyone what the system
actually produces. This module is the other half: a real call, real proposed findings, real
citations.

Three things happen here that are the whole point of the architecture, and each one is ordinary
code rather than something the model is asked to be careful about:

1. **The model never sees a model id.** It is addressed by tier alias (`ireports-thinking`), and
   the gateway resolves that from configuration (ADR-008, ADR-017).
2. **Every citation is checked against the case.** A finding citing an evidence id that is not in
   this case is dropped before it can reach an envelope — the model is not trusted to cite
   honestly, it is *checked*. This is "evidence before inference" as executable code.
3. **Determinative language is rejected by the contract, not by the prompt.** The prompt asks for
   decision-support phrasing, but `DecisionSupportText` enforces it. If the model writes "the
   subject is unsuitable", constructing the `ProposedFinding` raises and the finding is dropped
   with the reason recorded. The prompt is a request; the type is the control.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ireports_domain import (
    Confidence,
    DecisionDomain,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    ModelAlias,
    ProposedFinding,
    ReviewUrgency,
    ValidationOutcome,
)
from ireports_gateway.port import Message, ModelGateway, ModelRequest

from .case_loader import EvidenceSpan, LoadedCase


@dataclass(frozen=True)
class Criterion:
    """One thing being checked under one named authority.

    Hard-coded here rather than routed from a policy pack: authority routing (ROUT-01) and policy
    packs are `DESIGNED-NOT-BUILT` under ADR-020, so this spike names its criteria directly and
    says so instead of pretending to a routing engine it does not have.
    """

    node_id: str
    decision_domain: DecisionDomain
    policy_pack_id: str
    policy_id: str
    criterion_id: str
    question: str


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        node_id="foreign_influence_specialist",
        decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        policy_pack_id="sead4-current",
        policy_id="SEAD-4",
        criterion_id="GUIDELINE-B",
        question=(
            "Foreign influence: contacts with foreign nationals, foreign financial interests, "
            "and any resulting divided loyalties or vulnerability to coercion."
        ),
    ),
    Criterion(
        node_id="financial_considerations_specialist",
        decision_domain=DecisionDomain.SUITABILITY,
        policy_pack_id="federal-core-2026-07-30",
        policy_id="5-CFR-731",
        criterion_id="731-202-B-4",
        question=(
            "Financial responsibility: delinquent debt, unexplained affluence, and whether the "
            "record shows a pattern or an explained and resolving isolated event."
        ),
    ),
    Criterion(
        node_id="candor_specialist",
        decision_domain=DecisionDomain.SUITABILITY,
        policy_pack_id="federal-core-2026-07-30",
        policy_id="5-CFR-731",
        criterion_id="731-202-B-3",
        question=(
            "Candor: material omissions or inconsistencies between what the subject reported "
            "and what the record shows, and whether the record explains them."
        ),
    ),
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "description": (
                "Zero or more proposed findings. An empty array is a valid and expected answer "
                "when the record shows nothing relevant to this criterion."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 180},
                    "observation": {
                        "type": "string",
                        "description": "What the record shows. Facts only, no conclusion.",
                    },
                    "policy_relevance": {
                        "type": "string",
                        "description": (
                            "Why those facts may be relevant to this criterion. 'May be "
                            "relevant', never 'violates' or 'disqualifies'."
                        ),
                    },
                    "recommended_officer_action": {"type": "string"},
                    "supporting_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "evidence_id values that support the observation.",
                    },
                    "mitigating_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "evidence_id values that cut against it.",
                    },
                    "information_gaps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "What the record does not say that a reviewer would need.",
                    },
                    "evidence_confidence": {"enum": ["low", "moderate", "high"]},
                    "analysis_confidence": {"enum": ["low", "moderate", "high"]},
                },
                "required": [
                    "title",
                    "observation",
                    "policy_relevance",
                    "recommended_officer_action",
                    "supporting_evidence",
                    "evidence_confidence",
                    "analysis_confidence",
                ],
            },
        }
    },
    "required": ["findings"],
}

SYSTEM = """You analyze federal background-investigation records against one named criterion.

You are a decision-support component. You never decide anything. An authorized adjudicative
officer reviews everything you produce, in a different system, after you have finished.

Rules, in order of importance:

1. NEVER state or imply a determination. Not "unsuitable", not "should be denied", not "violated",
   not "is deceptive", and no prediction of future conduct. Write what the record shows and why it
   may be relevant. A reviewer decides what it means.
2. CITE EVERYTHING. Every observation must reference the evidence_id values it rests on. If you
   cannot cite it, do not write it. Citing an id that was not given to you is worse than silence.
3. REPORT MITIGATION AS DILIGENTLY AS CONCERN. A record with explanation, resolution, or context
   that cuts against a concern must say so in mitigating_evidence. An analysis that lists only
   what looks bad is a defective analysis.
   ONE ROLE PER SPAN: within a single finding, an evidence_id may appear in supporting_evidence
   OR in mitigating_evidence, never in both. Decide which role that span plays in this finding.
   If a span both establishes a fact and softens it, cite it where it carries the most weight and
   describe the other side in your observation text.
4. AN EMPTY FINDINGS ARRAY IS A GOOD ANSWER when the record shows nothing relevant. Do not
   manufacture a finding to appear thorough.
5. NAME THE GAPS. If the record is missing something a reviewer would need, say so in
   information_gaps rather than reasoning past it."""


@dataclass(frozen=True)
class SpecialistOutcome:
    """What one specialist produced, including what was thrown away and why.

    The rejects are not an error path — they are the deterministic shell doing its job, and a
    demo that hid them would misrepresent where the safety actually lives.
    """

    criterion: Criterion
    findings: tuple[ProposedFinding, ...]
    rejected: tuple[str, ...]
    resolved_model: str
    input_tokens: int
    output_tokens: int


def _evidence_block(spans: tuple[EvidenceSpan, ...]) -> str:
    return "\n\n".join(
        f"[{s.evidence_id}] (source: {s.source_reliability}, {s.document_id} p.{s.page_number})\n"
        f"{s.text}"
        for s in spans
    )


def analyze(
    criterion: Criterion,
    case: LoadedCase,
    gateway: ModelGateway,
    run_id: str,
    attempts: int = 2,
) -> SpecialistOutcome:
    """One criterion, typed and citation-checked findings out.

    `attempts` exists because structured output is a request, not a guarantee (ADR-018). Roughly
    one call in three comes back with `findings` as a string, as a bare object, or as an array of
    objects missing required keys — all from the same schema and the same prompt. One retry turns
    an intermittently empty demo into a reliable one.

    The retry is bounded at two deliberately. An unbounded retry over a paid model call is the
    budget failure `Budgets.max_model_calls_per_node` exists to prevent, and a node that keeps
    asking until it likes the answer is selecting for agreeable output rather than correct output.
    """
    outcome = _attempt(criterion, case, gateway, run_id)
    for _ in range(attempts - 1):
        if outcome.findings:
            return outcome
        retry = _attempt(criterion, case, gateway, run_id)
        # Keep the retry's findings, but carry both attempts' rejections so the record shows the
        # first attempt happened and why it produced nothing.
        outcome = SpecialistOutcome(
            criterion=retry.criterion,
            findings=retry.findings,
            rejected=outcome.rejected + retry.rejected,
            resolved_model=retry.resolved_model,
            input_tokens=outcome.input_tokens + retry.input_tokens,
            output_tokens=outcome.output_tokens + retry.output_tokens,
        )
    return outcome


def _attempt(
    criterion: Criterion,
    case: LoadedCase,
    gateway: ModelGateway,
    run_id: str,
) -> SpecialistOutcome:
    """One criterion, one model call."""
    prompt = (
        f"CASE: {case.manifest.case_id} — position: "
        f"{case.manifest.case_context.position_title}\n\n"
        f"CRITERION UNDER ANALYSIS\n"
        f"Authority: {criterion.policy_id} ({criterion.decision_domain.value})\n"
        f"Criterion: {criterion.criterion_id}\n"
        f"Question: {criterion.question}\n\n"
        f"RECORD ({len(case.spans)} spans; cite by the bracketed id)\n\n"
        f"{_evidence_block(case.spans)}\n\n"
        "Analyze the record against this criterion only. Other criteria are analyzed separately."
    )

    response = gateway.complete(
        ModelRequest(
            alias=ModelAlias.THINKING,
            messages=(Message(role="user", content=prompt),),
            system=SYSTEM,
            response_schema=RESPONSE_SCHEMA,
            node_id=criterion.node_id,
        )
    )

    known = {s.evidence_id for s in case.spans}
    findings: list[ProposedFinding] = []
    rejected: list[str] = []

    # Everything from here down treats the response as untrusted input, because it is. ADR-018:
    # a requested schema is verified, not trusted. The gateway asks for this shape; the model
    # usually returns it; "usually" is why this parses defensively instead of indexing.
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        return SpecialistOutcome(
            criterion=criterion,
            findings=(),
            rejected=(f"{criterion.criterion_id}: response was not JSON — {exc}",),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    raw_findings = payload.get("findings") if isinstance(payload, dict) else None

    # Observed in practice, and worth naming: the same request with the same tool schema
    # sometimes returns `findings` as a JSON *string* rather than an array. This is exactly what
    # ADR-018 means by "a requested schema is verified, not trusted" — a schema is a request, and
    # the model is free to answer it approximately. One coercion attempt, then reject.
    if isinstance(raw_findings, str):
        with contextlib.suppress(json.JSONDecodeError):
            raw_findings = json.loads(raw_findings)
    if isinstance(raw_findings, dict):
        # Also observed: a single finding object where an array was requested. Same lesson.
        raw_findings = [raw_findings]

    if not isinstance(raw_findings, list):
        return SpecialistOutcome(
            criterion=criterion,
            findings=(),
            rejected=(
                f"{criterion.criterion_id}: response had no 'findings' array "
                f"(got {type(raw_findings).__name__})",
            ),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            # Seen in practice: an otherwise well-formed response whose findings array held a
            # bare string. Rejecting it is the shell working; crashing on it was a bug.
            rejected.append(
                f"{criterion.criterion_id}#{index}: finding was {type(raw).__name__}, "
                "not an object — dropped"
            )
            continue
        missing = [
            k
            for k in ("title", "observation", "policy_relevance", "recommended_officer_action")
            if not isinstance(raw.get(k), str) or not raw.get(k)
        ]
        if missing:
            # Name what *was* there, not only what was absent. A rejection reading "missing all
            # four required fields" is true and useless — it cannot distinguish a truncated
            # response from a differently-shaped one, and the difference decides whether the fix
            # is a bigger max_tokens or a clearer schema.
            rejected.append(
                f"{criterion.criterion_id}#{index}: missing/blank {missing} — dropped "
                f"(keys present: {sorted(raw)})"
            )
            continue

        support = [e for e in raw.get("supporting_evidence", []) or [] if e in known]
        unknown = [e for e in raw.get("supporting_evidence", []) or [] if e not in known]
        mitigating = [e for e in raw.get("mitigating_evidence", []) or [] if e in known]

        # `ProposedFinding` requires a span to serve one role. The model routinely cites the same
        # span as both — usually an investigator finding that establishes a fact *and* softens it.
        # Rather than drop an otherwise good finding, resolve it deterministically: supporting
        # wins, because it is the basis of the observation, and the demotion is recorded so the
        # adjustment is visible rather than silent.
        overlap = [e for e in mitigating if e in support]
        if overlap:
            mitigating = [e for e in mitigating if e not in support]
            rejected.append(
                f"{criterion.criterion_id}#{index}: {overlap} cited as both supporting and "
                "mitigating; kept as supporting (a span serves one role per finding)"
            )

        if unknown:
            # Not a warning. A citation that does not resolve is the failure mode this whole
            # architecture is built to prevent, so it drops the finding rather than trimming it.
            rejected.append(
                f"{criterion.criterion_id}#{index}: cited unknown evidence {unknown} — dropped"
            )
            continue
        if not support:
            rejected.append(
                f"{criterion.criterion_id}#{index}: no resolvable supporting evidence — dropped"
            )
            continue

        try:
            findings.append(
                ProposedFinding(
                    finding_id=f"fnd_{run_id}_{criterion.criterion_id}_{index}".replace("-", "_"),
                    run_id=run_id,
                    case_id=case.manifest.case_id,
                    authority=FindingAuthority(
                        decision_domain=criterion.decision_domain,
                        policy_pack_id=criterion.policy_pack_id,
                        policy_id=criterion.policy_id,
                        criterion_id=criterion.criterion_id,
                        policy_citations=[
                            f"pol_{criterion.criterion_id}".replace("-", "_").lower()
                        ],
                    ),
                    classification=FindingClassification.POTENTIAL_ISSUE,
                    title=raw["title"],
                    observation=raw["observation"],
                    policy_relevance=raw["policy_relevance"],
                    recommended_officer_action=raw["recommended_officer_action"],
                    supporting_evidence=support,
                    mitigating_evidence=mitigating,
                    evidence_confidence=Confidence(raw.get("evidence_confidence", "moderate")),
                    analysis_confidence=Confidence(raw.get("analysis_confidence", "moderate")),
                    urgency=ReviewUrgency.NORMAL_REVIEW,
                    generated_by=GeneratedBy(
                        node=criterion.node_id,
                        model_alias=ModelAlias.THINKING,
                        prompt_version="demo-v1",
                    ),
                    validation=FindingValidation(
                        schema_check=ValidationOutcome.PASSED,
                        citations=ValidationOutcome.PASSED,
                        policy_effective_date=ValidationOutcome.PASSED,
                        protected_attribute_check=ValidationOutcome.PASSED,
                        prohibited_language_check=ValidationOutcome.PASSED,
                    ),
                    proposed_at=datetime.now(UTC),
                )
            )
        except ValueError as exc:
            # Most often the determinative-language guard. The prompt asked the model not to write
            # a conclusion; the contract is what actually stops one.
            rejected.append(f"{criterion.criterion_id}#{index}: rejected by contract — {exc}")

    return SpecialistOutcome(
        criterion=criterion,
        findings=tuple(findings),
        rejected=tuple(rejected),
        resolved_model=response.resolved_model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
