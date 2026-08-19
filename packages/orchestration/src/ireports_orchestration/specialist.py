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
4. **The return value is the published `SpecialistResult` contract** (CONT-01), not a local shape.
   That is not bookkeeping: constructing it re-checks that every finding's run id, case id, and
   authority agree with the criterion the sub-call was pointed at — a validation pass the demo's
   local dataclass never performed.

**What is deliberately *not* on that contract:** whether the call completed. ADR-021 §2 kept
completion status out of `SpecialistResult` on purpose, so `SpecialistStatus` lives on the local
`SpecialistOutcome` wrapper instead. The consequence is real and is not hidden: a reviewer reading
an envelope in ASAP cannot tell a refused criterion from a clean one. Closing that gap means
superseding ADR-021 deliberately, not widening this contract in passing.
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
    SpecialistCriterion,
    SpecialistResult,
    ValidationOutcome,
)
from ireports_gateway.port import (
    GatewayError,
    Message,
    ModelGateway,
    ModelRefusalError,
    ModelRequest,
)
from ireports_retrieval import RetrievedSpan, Retriever

from .budget import DEFAULT_BUDGETS, BudgetBreach, BudgetLedger
from .case import LoadedCase
from .coercion import cap_rejections, normalize_array
from .criteria import Criterion
from .gather import (
    DEFAULT_MAX_STEPS,
    CancellationToken,
    GatheredEvidence,
    GatherStop,
    gather_evidence,
)

_LOG = logging.getLogger(__name__)

SPECIALIST_CLASSIFICATIONS: dict[str, FindingClassification] = {
    "potential_issue": FindingClassification.POTENTIAL_ISSUE,
    "mitigating_information": FindingClassification.MITIGATING_INFORMATION,
    "no_issue_identified": FindingClassification.NO_ISSUE_IDENTIFIED,
}
"""The three of five classifications a *specialist* may emit.

`CONTRADICTION` and `INFORMATION_GAP` belong to `synthesis.py`, which is competent to see across
criteria and collects the fields those two require — a contradiction needs two conflicting spans,
and an information gap needs an `InformationGap` object. A specialist's schema collects neither.

**Until 2026-08-18 this was a constant.** `classification=POTENTIAL_ISSUE` was hard-coded and the
schema never asked, so `MITIGATING_INFORMATION` and `NO_ISSUE_IDENTIFIED` were unreachable from
this module since it was written. On a record with real concerns the constant is right most of the
time, which is exactly why nothing contradicted it — the first deliberately clean case shipped
seven findings labelled `potential_issue`, including one titled "returned no indicators of criminal
or dishonest conduct". See ADR-025 and `docs/LESSONS.md`.
"""

PROMPT_VERSION = "specialist-v2"
"""Named once and used for both the per-finding provenance and the result's own.

Bumped to v2 when the prompt began asking the model to classify (ADR-025). Provenance that did not
move would make two materially different prompts indistinguishable in the record.

Two literals would drift, and provenance that disagrees with itself about which prompt produced a
finding is worse than none — it reads as authoritative."""

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
                    "classification": {
                        "enum": [
                            "potential_issue",
                            "mitigating_information",
                            "no_issue_identified",
                        ],
                        "description": (
                            "What KIND of thing this is. A statement about the record, never "
                            "about the person. potential_issue: the record shows something a "
                            "reviewer should look at. mitigating_information: the record shows "
                            "something that cuts against a concern - an explanation, a "
                            "resolution, a third-party admission of error. no_issue_identified: "
                            "the record affirmatively establishes an absence, such as a record "
                            "check that returned nothing."
                        ),
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
                    "classification",
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
4. AN EMPTY FINDINGS ARRAY IS A GOOD ANSWER when the record shows nothing relevant to this
   criterion. Do not manufacture a finding to appear thorough, and do not manufacture one just to
   report that you found nothing - if the record says nothing on this criterion, return [].
5. CLASSIFY EVERY FINDING, and classify honestly. The classification says what KIND of thing the
   finding is. It is not a severity and there is no ranking.
   - potential_issue: the record shows something a reviewer should look at.
   - mitigating_information: the record shows something that cuts AGAINST a concern - an
     explanation, a resolution, a documented third-party error, a voluntary disclosure. A record
     whose concerning-looking item is fully explained is mitigating information, not an issue.
   - no_issue_identified: the record affirmatively establishes an absence - a criminal history
     check that returned nothing, a consistency review that found no discrepancy. This is a real
     finding backed by a real span. It is NOT the same as having nothing to say, which is [].
   Labelling resolved or exculpatory material as potential_issue misrepresents the record to a
   reviewer as surely as missing a concern does.
6. NAME THE GAPS. If the record is missing something a reviewer would need, say so in
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

    CANCELLED = "cancelled"
    """The run was asked to stop while this criterion was in flight or waiting.

    **A fifth distinct fact, and the fourth time this enum has grown for the same reason.** A
    criterion nobody analysed because the run was cancelled is not one that broke, not one that
    came back clean, and not one that ran out of budget — cancellation is a *decision*, and the
    others are outcomes. Folding it into `SKIPPED_BUDGET` would report a deliberate stop as a
    ceiling nobody set, and send whoever reads it to tune a number that was never the problem.

    Not recorded in a checkpoint (`RESUMABLE_STATUSES`): cancelled work is work still to do.
    """

    SKIPPED_BUDGET = "skipped_budget"
    """A run-level ceiling was already crossed when this criterion came up, so no call was made.

    **A fourth distinct fact, and the reason it is not folded into `FAILED`.** A criterion that was
    never attempted because the run ran out of wall clock is not one that broke, and it is not one
    that came back clean. Collapsing it into either would misreport a *truncated* analysis as a
    complete one — the failure `RunStatus.INCOMPLETE_DUE_TO_BUDGET` exists to make visible."""


@dataclass(frozen=True)
class SpecialistOutcome:
    """What one specialist produced: the published contract, plus what the run needs around it.

    **`result` is the deliverable; everything else is operational.** `SpecialistResult` (CONT-01)
    is the contract a consumer sees — the criterion analysed, the provenance, and the findings.
    The other fields are facts about *this run of this node* that ADR-021 §2 deliberately kept out
    of that contract: whether the call completed, what the shell threw away, what it cost, and
    which spans it was shown. Putting them here rather than on the contract is the ADR being
    followed, not worked around.

    The rejects are not an error path — they are the deterministic shell doing its job, and a run
    that hid them would misrepresent where the safety actually lives.
    """

    result: SpecialistResult
    criterion: Criterion
    """The *routing* type, not the contract's. Carries `node_id` and the question text, which the
    orchestrator and the prompt need and a consumer of findings does not."""

    rejected: tuple[str, ...]
    resolved_model: str
    input_tokens: int
    output_tokens: int
    status: SpecialistStatus = SpecialistStatus.COMPLETED
    retrieved: tuple[str, ...] = ()
    """The evidence ids this specialist was actually shown.

    Provenance, and it is not decoration: with retrieval, two specialists on the same case read
    different records. "Why did the financial criterion miss this?" is unanswerable without knowing
    what it was given, and the answer is often that retrieval never surfaced the span."""

    @property
    def findings(self) -> tuple[ProposedFinding, ...]:
        """The contract's findings, read through the outcome.

        A property rather than a duplicated field: two copies of the same list is how a result
        and its envelope start disagreeing about what was found."""
        return self.result.findings

    @property
    def analysed(self) -> bool:
        return self.status is SpecialistStatus.COMPLETED


def _specialist_criterion(criterion: Criterion) -> SpecialistCriterion:
    """The routing type, narrowed to the four fields the contract identifies a criterion by.

    `node_id` and `question` do not cross: one is a graph label, the other is prompt text, and
    neither is part of what a finding is answerable to."""
    return SpecialistCriterion(
        decision_domain=criterion.decision_domain,
        policy_pack_id=criterion.policy_pack_id,
        policy_id=criterion.policy_id,
        criterion_id=criterion.criterion_id,
    )


def _outcome(
    criterion: Criterion,
    case_id: str,
    run_id: str,
    findings: tuple[ProposedFinding, ...],
    rejected: tuple[str, ...],
    resolved_model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    status: SpecialistStatus = SpecialistStatus.COMPLETED,
    retrieved: tuple[str, ...] = (),
) -> SpecialistOutcome:
    """Build the contract and wrap it. **Every return from this module goes through here.**

    `SpecialistResult` re-checks that each finding's run id, case id, and authority agree with the
    result's own — a real validation pass the demo's local dataclass never performed. It should
    never fire, because the findings below are constructed from this same criterion; if it does,
    that is a defect in this module.

    It is caught rather than raised for the reason ADR-021 §3 gives one layer up: a specialist
    that raises takes down every *other* specialist's completed, already-paid-for work. So a
    contract violation is demoted to a `FAILED` criterion carrying the message, which is loud in
    the run's rejection record and cheap to see. Losing one criterion to a bug is bad; losing five
    and the money spent on them is worse.
    """
    try:
        result = SpecialistResult(
            run_id=run_id,
            case_id=case_id,
            criterion=_specialist_criterion(criterion),
            generated_by=GeneratedBy(
                node=criterion.node_id,
                model_alias=ModelAlias.THINKING,
                prompt_version=PROMPT_VERSION,
            ),
            findings=findings,
        )
    except ValueError as exc:
        _LOG.error(
            "specialist result failed its own contract",
            extra={
                "run_id": run_id,
                "case_id": case_id,
                "criterion_id": criterion.criterion_id,
                "error": type(exc).__name__,
            },
        )
        return _outcome(
            criterion,
            case_id,
            run_id,
            findings=(),
            rejected=(
                *rejected,
                f"{criterion.criterion_id}: findings did not satisfy SpecialistResult — "
                f"{exc}. This is a defect in the specialist, not the model.",
            ),
            resolved_model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status=SpecialistStatus.FAILED,
            retrieved=retrieved,
        )

    return SpecialistOutcome(
        result=result,
        criterion=criterion,
        rejected=rejected,
        resolved_model=resolved_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        status=status,
        retrieved=retrieved,
    )


def skipped_for_budget(
    criterion: Criterion, case_id: str, run_id: str, breach: BudgetBreach
) -> SpecialistOutcome:
    """A criterion the run never got to, carrying which ceiling stopped it.

    Public because both orchestrators construct it, and a policy decision both paths make must be
    one implementation — the same reasoning as `should_synthesize`. Two copies would drift, and the
    drift would show up as two runs of the same case truncating differently for reasons nobody
    could see.
    """
    return _not_analysed(
        criterion,
        case_id,
        run_id,
        SpecialistStatus.SKIPPED_BUDGET,
        f"{criterion.criterion_id}: {breach} — criterion NOT analysed",
    )


def cancelled(criterion: Criterion, case_id: str, run_id: str, reason: str) -> SpecialistOutcome:
    """A criterion the run was told to stop before analysing. **ORCH-03.**

    Public for the same reason `skipped_for_budget` is: both orchestrators construct it, and a
    policy decision made separately in two places is one they will eventually disagree about.
    """
    return _not_analysed(
        criterion,
        case_id,
        run_id,
        SpecialistStatus.CANCELLED,
        f"{criterion.criterion_id}: run cancelled ({reason}) — criterion NOT analysed",
    )


def _evidence_block(spans: tuple[RetrievedSpan, ...]) -> str:
    """The retrieved record, as the model sees it.

    The title is included because it carries real signal on this corpus — "SF86 — 22. Financial
    Record — Delinquent Debt" tells the model what it is reading in a way the first line of a
    7,000-character chapter does not.
    """
    return "\n\n".join(
        f"[{s.evidence_id}] {s.title} ({s.document_id}, p.{s.page_number})\n{s.text}" for s in spans
    )


def _not_analysed(
    criterion: Criterion, case_id: str, run_id: str, status: SpecialistStatus, *reasons: str
) -> SpecialistOutcome:
    """A criterion that was not analysed, carrying why.

    Still produces a `SpecialistResult` — with no findings, and naming the criterion it was
    pointed at. That is the whole reason CONT-01 wraps findings rather than returning a bare list
    (D-05): a result with zero findings still says what was checked.

    Zero tokens because nothing was billed, and `resolved_model` is empty because no model served
    it. Both are true and both matter for the budget record.
    """
    return _outcome(
        criterion,
        case_id,
        run_id,
        findings=(),
        rejected=reasons,
        status=status,
    )


DEFAULT_K = 6
"""Spans retrieved per criterion.

Six is a judgement, not a measurement. On this corpus a span is a whole ROI chapter — up to ~7,900
characters — so six is already a large prompt, and the ranked list falls off sharply after the
first two or three. Tuning it against a corpus this small would be fitting noise.

What it replaced: every specialist receiving all 34 spans of a 35,000-token case, five
times over."""


def analyze(
    criterion: Criterion,
    case: LoadedCase,
    gateway: ModelGateway,
    retriever: Retriever,
    run_id: str,
    attempts: int = 2,
    k: int = DEFAULT_K,
    ledger: BudgetLedger | None = None,
    cancel: CancellationToken | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
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
    # **Gathering is a bounded loop, and it is outside the retry loop.** A retry exists because the
    # model returned an unusable *shape*, not because the record changed — re-running the queries
    # would cost embedding calls to get the identical spans back.
    #
    # `calls_reserved=attempts` is what stops gathering from eating the analysis's budget. A node
    # that spends its whole allowance deciding what to read and then cannot afford to read it has
    # failed in a way that looks like success.
    gathered = gather_evidence(
        criterion,
        case.manifest.case_id,
        retriever,
        gateway,
        k=k,
        budgets=ledger.budgets if ledger is not None else DEFAULT_BUDGETS,
        max_steps=max_steps,
        ledger=ledger,
        cancel=cancel,
        calls_reserved=attempts,
    )
    if gathered.failed is not None:
        _LOG.warning(
            "retrieval failed",
            extra={
                "run_id": run_id,
                "case_id": case.manifest.case_id,
                "criterion_id": criterion.criterion_id,
                "error": type(gathered.failed).__name__,
            },
        )
        return _not_analysed(
            criterion,
            case.manifest.case_id,
            run_id,
            SpecialistStatus.FAILED,
            f"{criterion.criterion_id}: retrieval failed ({gathered.failed}) — "
            "criterion NOT analysed",
        )

    if gathered.stopped is GatherStop.CANCELLED:
        # **Cancelled is not failed, not clean, and not over budget** (ORCH-03). Nobody analysed
        # this criterion and the reason was a decision rather than a fault, so it gets its own
        # status rather than riding on the nearest one.
        return _not_analysed(
            criterion,
            case.manifest.case_id,
            run_id,
            SpecialistStatus.CANCELLED,
            *gathered.rejected,
        )

    spans = gathered.spans
    if not spans:
        # Not an error, and not silence either: the criterion was asked and the record had nothing
        # to say. Recorded as such so it is distinguishable from a criterion that was never run.
        return _outcome(
            criterion,
            case.manifest.case_id,
            run_id,
            findings=(),
            rejected=(
                f"{criterion.criterion_id}: retrieval returned no spans for this criterion — "
                "nothing in the record matched",
            ),
            status=SpecialistStatus.COMPLETED,
        )

    outcome = _with_gathering(_attempt(criterion, case, spans, gateway, run_id, ledger), gathered)
    for _ in range(attempts - 1):
        # A refusal or a transport failure is not fixed by asking again, and ADR-015 is explicit
        # that a refusal must not be retried blindly.
        if outcome.findings or not outcome.analysed:
            return outcome
        retry = _attempt(criterion, case, spans, gateway, run_id, ledger)
        # Keep the retry's findings, but carry both attempts' rejections so the record shows the
        # first attempt happened and why it produced nothing. The `SpecialistResult` is the
        # retry's, unmodified — it is the answer that stands.
        outcome = SpecialistOutcome(
            result=retry.result,
            criterion=retry.criterion,
            rejected=outcome.rejected + retry.rejected,
            resolved_model=retry.resolved_model,
            input_tokens=outcome.input_tokens + retry.input_tokens,
            output_tokens=outcome.output_tokens + retry.output_tokens,
            status=retry.status,
            retrieved=retry.retrieved,
        )
    return outcome


def _with_gathering(outcome: SpecialistOutcome, gathered: GatheredEvidence) -> SpecialistOutcome:
    """Fold the gathering loop's account into the criterion's outcome.

    **The rejections lead and the tokens add.** A loop that stopped on a ceiling, or because a
    refinement surfaced nothing, or because the assessor was unreachable, has said something about
    how complete this criterion's evidence is — and a reviewer reading the findings has no other
    way to learn it. The sufficiency calls were paid for like any others, so they belong in the
    node's spend rather than only in the run-level ledger.

    `retrieved` is left alone: it already lists every span the analysis was shown, which is the
    union across every round.
    """
    return SpecialistOutcome(
        result=outcome.result,
        criterion=outcome.criterion,
        rejected=gathered.rejected + outcome.rejected,
        resolved_model=outcome.resolved_model,
        input_tokens=outcome.input_tokens + gathered.input_tokens,
        output_tokens=outcome.output_tokens + gathered.output_tokens,
        status=outcome.status,
        retrieved=outcome.retrieved,
    )


def _attempt(
    criterion: Criterion,
    case: LoadedCase,
    spans: tuple[RetrievedSpan, ...],
    gateway: ModelGateway,
    run_id: str,
    ledger: BudgetLedger | None = None,
) -> SpecialistOutcome:
    """One criterion, one model call, over the spans retrieval surfaced for it."""
    prompt = (
        f"CASE: {case.manifest.case_id} — position: "
        f"{case.manifest.case_context.position_title}\n\n"
        f"CRITERION UNDER ANALYSIS\n"
        f"Authority: {criterion.policy_id} ({criterion.decision_domain.value})\n"
        f"Criterion: {criterion.criterion_id}\n"
        f"Question: {criterion.question}\n\n"
        f"RECORD ({len(spans)} spans retrieved for this criterion; cite by the bracketed id)\n\n"
        f"{_evidence_block(spans)}\n\n"
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
            case.manifest.case_id,
            run_id,
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
            case.manifest.case_id,
            run_id,
            SpecialistStatus.FAILED,
            f"{criterion.criterion_id}: {type(exc).__name__} — criterion NOT analysed",
        )

    # Recorded the moment the call returns, including on a run that is about to stop: money spent
    # is spent whether or not the finding survives validation, and a ledger that only counted
    # successful calls would understate the run.
    if ledger is not None:
        ledger.record(response.usage.input_tokens, response.usage.output_tokens)

    # **What the specialist was shown, not what the case contains.** With retrieval these differ,
    # and validating against the whole case would let a model cite a span it never saw — which is
    # indistinguishable from a lucky hallucination and passes silently.
    known = {s.evidence_id for s in spans}
    retrieved_ids = tuple(s.evidence_id for s in spans)
    findings: list[ProposedFinding] = []
    rejected: list[str] = []

    # Everything from here down treats the response as untrusted input, because it is. ADR-018:
    # a requested schema is verified, not trusted. The gateway asks for this shape; the model
    # usually returns it; "usually" is why this parses defensively instead of indexing.
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        return _outcome(
            criterion,
            case.manifest.case_id,
            run_id,
            findings=(),
            rejected=(f"{criterion.criterion_id}: response was not JSON — {exc}",),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            retrieved=retrieved_ids,
        )

    raw_findings = normalize_array(
        payload.get("findings") if isinstance(payload, dict) else None, "findings"
    )

    if not isinstance(raw_findings, list):
        return _outcome(
            criterion,
            case.manifest.case_id,
            run_id,
            findings=(),
            rejected=(
                f"{criterion.criterion_id}: response had no 'findings' array "
                f"(got {type(raw_findings).__name__})",
            ),
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            retrieved=retrieved_ids,
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

        raw_classification = raw.get("classification")
        classification = SPECIALIST_CLASSIFICATIONS.get(str(raw_classification))
        if classification is None:
            # **Defaulted, and said out loud.** Dropping an otherwise good finding over a label
            # would discard real analysis; defaulting silently is how the bug this replaces went
            # unnoticed for weeks. So the finding survives, the label falls back to the most
            # conservative value, and the run records that it was not the model's answer.
            rejected.append(
                f"{criterion.criterion_id}#{index}: classification {raw_classification!r} is not "
                f"one of {sorted(SPECIALIST_CLASSIFICATIONS)} — defaulted to potential_issue, "
                "which may overstate this finding to a reviewer"
            )
            classification = FindingClassification.POTENTIAL_ISSUE

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
        if not support and classification is not FindingClassification.NO_ISSUE_IDENTIFIED:
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
                    classification=classification,
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
                        prompt_version=PROMPT_VERSION,
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

    return _outcome(
        criterion,
        case.manifest.case_id,
        run_id,
        findings=tuple(findings),
        rejected=cap_rejections(rejected),
        resolved_model=response.resolved_model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        retrieved=retrieved_ids,
    )
