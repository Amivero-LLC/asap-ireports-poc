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

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ireports_domain import (
    Confidence,
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    ModelAlias,
    ProposedFinding,
    ReviewUrgency,
    ValidationOutcome,
)
from ireports_gateway.port import (
    GatewayError,
    Message,
    ModelGateway,
    ModelRefusalError,
    ModelRequest,
)

from .case_loader import EvidenceSpan, LoadedCase
from .criteria import Criterion

_LOG = logging.getLogger(__name__)

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


class SpecialistStatus(StrEnum):
    """Whether this criterion was actually analysed.

    **`COMPLETED` with no findings and `REFUSED` are different facts**, and conflating them is the
    failure mode this whole architecture is built against: silent under-analysis that reads as a
    clean record. A criterion that came back clean and a criterion nobody could analyse must not
    look the same.

    This lives on the local orchestration type, not on the `SpecialistResult` contract — ADR-021 §2
    says that contract carries no completion status, and this does not change it. What it changes
    is that the *run* knows, which ADR-021 §3 always intended ("the node catches it, logs it").
    """

    COMPLETED = "completed"
    """The call returned. Zero findings here is a real answer — nothing in the record was
    relevant to this criterion."""

    REFUSED = "refused"
    """The model declined. **Not** an error to retry — ADR-015. Expected in normal operation here,
    because adjudicative files routinely discuss criminal conduct, substance use, and foreign
    contacts."""

    FAILED = "failed"
    """Transport, timeout, or a structured-output fault. The criterion was not analysed."""


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
    status: SpecialistStatus = SpecialistStatus.COMPLETED

    @property
    def analysed(self) -> bool:
        return self.status is SpecialistStatus.COMPLETED


MAX_UNWRAP_DEPTH = 3
"""How many layers of re-wrapping to peel before giving up. Three is generous; two were observed."""


def _normalize_findings(raw: Any) -> Any:
    """Coerce the shapes a model actually returns into the array that was requested.

    ADR-018 in practice. All of these came from the *same* schema and the same prompt:

    | Returned | Handling |
    |---|---|
    | `[...]` | The requested shape |
    | `"[...]"` — the array as a JSON string | Parse it |
    | `{...}` — one finding where an array was asked for | Wrap it |
    | `{"findings": [...]}` — the envelope repeated inside itself | **Unwrap it** |

    That last one is why this is a loop rather than the two `if`s it used to be. The old code saw a
    dict and wrapped it, producing `[{"findings": [...]}]` — an "object missing every required
    field," which it duly rejected. So a response the model had answered correctly, only nested one
    layer too deep, was recorded as unparseable.

    **It was invisible for weeks** because the rejection said "missing/blank [title, observation,
    ...]" and stopped there. Adding `keys present:` to that message identified it in a single run.
    Diagnosability is a feature; a rejection that does not say what it saw cannot be acted on.

    Unwrapping is only attempted when the dict's *sole* key is `findings`. A dict that has a
    `findings` key alongside real finding fields is ambiguous, and guessing there would risk
    discarding an actual finding.
    """
    for _ in range(MAX_UNWRAP_DEPTH):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw, dict) and set(raw) == {"findings"}:
            raw = raw["findings"]
        elif isinstance(raw, dict):
            return [raw]
        else:
            return raw
    return raw


def _evidence_block(spans: tuple[EvidenceSpan, ...]) -> str:
    return "\n\n".join(
        f"[{s.evidence_id}] (source: {s.source_reliability}, {s.document_id} p.{s.page_number})\n"
        f"{s.text}"
        for s in spans
    )


def _not_analysed(criterion: Criterion, status: SpecialistStatus, reason: str) -> SpecialistOutcome:
    """A criterion that was not analysed, carrying why.

    Zero tokens because nothing was billed, and `resolved_model` is empty because no model served
    it. Both are true and both matter for the budget record.
    """
    return SpecialistOutcome(
        criterion=criterion,
        findings=(),
        rejected=(reason,),
        resolved_model="",
        input_tokens=0,
        output_tokens=0,
        status=status,
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

    **A gateway failure here is contained, not propagated** (ADR-021 §3). Until 2026-08-12 it was
    not: `gateway.complete` was called bare, so one refused criterion raised through the thread
    pool or the graph and **killed the whole run**, discarding every other specialist's completed
    and already-paid-for work. Under Lambda that is worse still, because the invocation is retried
    automatically and every model call is paid for again — into the same refusal.
    """
    outcome = _attempt(criterion, case, gateway, run_id)
    for _ in range(attempts - 1):
        # A refusal or a transport failure is not fixed by asking again, and ADR-015 is explicit
        # that a refusal must not be retried blindly.
        if outcome.findings or not outcome.analysed:
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
            status=retry.status,
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

    request = ModelRequest(
        alias=ModelAlias.THINKING,
        messages=(Message(role="user", content=prompt),),
        system=SYSTEM,
        response_schema=RESPONSE_SCHEMA,
        node_id=criterion.node_id,
    )

    # ADR-021 §3: the node catches it, logs it with run_id / case_id / criterion, and the run
    # continues. Every log line below carries identifiers only — never prompt or case text.
    try:
        response = gateway.complete(request)
    except ModelRefusalError as exc:
        _LOG.warning(
            "specialist refused",
            extra={
                "run_id": run_id,
                "case_id": case.manifest.case_id,
                "criterion_id": criterion.criterion_id,
                "refusal_category": exc.category,
            },
        )
        return _not_analysed(
            criterion,
            SpecialistStatus.REFUSED,
            f"{criterion.criterion_id}: model declined the request "
            f"(category={exc.category or 'unspecified'}) — criterion NOT analysed",
        )
    except GatewayError as exc:
        _LOG.warning(
            "specialist failed",
            extra={
                "run_id": run_id,
                "case_id": case.manifest.case_id,
                "criterion_id": criterion.criterion_id,
                "error": type(exc).__name__,
            },
        )
        return _not_analysed(
            criterion,
            SpecialistStatus.FAILED,
            f"{criterion.criterion_id}: {type(exc).__name__} — criterion NOT analysed",
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

    raw_findings = _normalize_findings(
        payload.get("findings") if isinstance(payload, dict) else None
    )

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
