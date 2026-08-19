"""The multi-step half of a specialist: retrieve, ask whether that was enough, retrieve again.

**A specialist used to get one query and whatever it returned.** That is the right first version
and it has a specific blind spot: the criterion's own text is the only query ever run, so evidence
that answers the criterion in different words is invisible. On this corpus a foreign-influence
criterion asks about "contacts with foreign nationals" and the record says "my wife's parents live
in Ankara" — one hop away, and one hop is exactly what a single query does not make.

So: retrieve, ask a cheap model whether the retrieved record is sufficient to assess this criterion
and what is missing, retrieve again on that answer, then analyse. Bounded at every edge.

**Three things stop this loop, and they are different facts.** Roadmap item 6 folds in ORCH-03's
two remaining clauses, and both only became buildable here — a no-progress detector and
cancellation are meaningless in a node that cannot loop.

* **No progress.** A step that surfaces no evidence the previous steps did not already have is a
  step that will keep not surfacing it. This is the detector ORCH-03 asks for, and it is the one
  that actually fires in practice: a refined query on a small corpus very often returns the same
  ranked spans.
* **Cancellation.** A cooperative token, checked between steps. Its real driver is not an operator
  pressing a button — it is the run-level wall clock. Before this, a crossed ceiling stopped the
  run from *starting* new criteria and had no way to stop work already in flight; under Lambda,
  where the platform kills the process on a timer, in-flight work is exactly what has to stop.
* **A ceiling.** `max_model_calls_per_node` finally means something. It was previously described as
  "enforced by the bounded retry in `analyze`", which was true and thin: two calls against a limit
  of five. A loop can actually reach it, so it is enforced here, and the analysis attempts that
  follow are counted against the same budget.

**This is deliberately not a tool surface.** The loop re-queries the same `Retriever` with a
refined query and can do nothing else, so SPEC-01's tool-allowlist clause stays *vacuous* rather
than becoming satisfied — a specialist still has no tool to allowlist. That clause becomes real the
day a specialist can choose between capabilities, and it is not this day.

**It is also framework-free, and that is a prediction rather than a hedge.** `docs/ROADMAP.md`
item 6 expected this to be where a graph framework earns its keep. Built as a loop *inside* a node,
neither orchestrator can see it — so if it turns out to discriminate between them at all, it will be
through cancellation crossing the node boundary, not through the loop. Recorded before measuring so
the result is not read backwards.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from threading import Event
from typing import Any

from ireports_domain import Budgets, ModelAlias
from ireports_gateway.port import (
    GatewayError,
    Message,
    ModelGateway,
    ModelRefusalError,
    ModelRequest,
)
from ireports_retrieval import RetrievalError, RetrievedSpan, Retriever

from .budget import BudgetLedger
from .criteria import Criterion

_LOG = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = 2
"""Retrieval rounds per criterion, including the first.

Two means *one* refinement, and it is a judgement rather than a measurement. The value of a second
query is highest when the first was phrased in policy language and the record is in plain language,
which is one hop; a third round on a corpus this size reliably re-surfaces what round two already
had, and the no-progress detector then stops it anyway. Raising this is cheap to try and should be
measured before it is kept.
"""

SUFFICIENCY_PROMPT_VERSION = "sufficiency-v1"

SUBCALL_SEPARATOR = ":"
"""What marks a model call as a specialist's *sub-call* rather than its analysis.

**Owned here because this module creates it.** Four files were reverse-engineering `":" in node_id`
to tell a triage call from an analysis call — a format spread across the code that constructs it,
the code that reads it, and three test files, none of which agreed in writing that it was a format
at all. `spikes/langgraph/checkpointer.py` records the same trap from the other side: keying a
load-bearing check to a string another component happens to produce is how a rename becomes a
silent behaviour change.
"""


def subcall_node_id(node_id: str, kind: str) -> str:
    """The node id for a sub-call made on a specialist's behalf.

    Distinct from the specialist's own id so that the two are separable everywhere they are
    counted — the budget ledger, the idempotency fingerprint, and every test that asks "how many
    criteria did this run analyse".
    """
    return f"{node_id}{SUBCALL_SEPARATOR}{kind}"


def is_subcall(node_id: str | None) -> bool:
    """Whether a model call was a sub-call rather than a node's own work.

    Takes `str | None` because `ModelRequest.node_id` is optional; an unlabelled call is not a
    sub-call, which is the safe reading — it counts toward the run's analysis rather than being
    quietly excluded from it.
    """
    return SUBCALL_SEPARATOR in (node_id or "")


EXCERPT_CHARS = 600
"""How much of a span the sufficiency check sees.

It is answering "is this the right *kind* of evidence, and what is missing" — a question the title
and opening of a span answers. Sending whole chapters would make the cheap call the expensive one,
which is how the synthesis stage once exhausted `max_tokens` while thinking (`docs/LESSONS.md`).
"""

SUFFICIENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sufficient": {
            "type": "boolean",
            "description": (
                "True when the retrieved record is enough to assess this criterion — including "
                "when it is enough to conclude the record says nothing relevant. False only when "
                "a further search would plausibly surface something material."
            ),
        },
        "missing": {
            "type": "string",
            "description": "What is absent, in one sentence. Empty when sufficient.",
        },
        "next_query": {
            "type": "string",
            "description": (
                "A search query for the missing material, phrased in the plain language a case "
                "record would use rather than in policy language. Empty when sufficient."
            ),
        },
    },
    "required": ["sufficient"],
}

SUFFICIENCY_SYSTEM = (
    "You decide whether a set of retrieved case excerpts is sufficient to assess one "
    "adjudicative criterion. You do not analyse the record and you do not reach any conclusion "
    "about the subject. You answer two questions: is there enough here, and if not, what search "
    "would find the rest.\n\n"
    "Say sufficient=true when the record is adequate — including when it adequately shows that "
    "nothing relevant to this criterion is present. An absence that the record establishes is a "
    "real answer, not a gap.\n\n"
    "Ask for more only when a further search would plausibly surface something material. Asking "
    "reflexively costs a paid call and returns the same spans."
)


class GatherStop(StrEnum):
    """Why the loop ended. Every value is a *different fact* about the run.

    Collapsing any two of these is the failure this project keeps re-learning: `completed with no
    findings` versus `refused`, `skipped` versus `ran and failed`. A criterion whose evidence
    gathering was cut short by a ceiling did not decide it had enough.
    """

    SUFFICIENT = "sufficient"
    """The assessor said the record was adequate. The only stop that is a positive answer."""

    STEP_LIMIT = "step_limit"
    """`max_steps` rounds ran. More evidence might exist; nobody looked."""

    NO_PROGRESS = "no_progress"
    """A round surfaced nothing new. **ORCH-03's detector**, and the one that fires most."""

    CALL_BUDGET = "call_budget"
    """`max_model_calls_per_node` was reached by the gathering itself."""

    RUN_BUDGET = "run_budget"
    """A run-level ceiling was crossed while this criterion was in flight."""

    CANCELLED = "cancelled"
    """Someone or something asked the run to stop. **ORCH-03's cancellation clause.**"""

    ASSESSOR_UNAVAILABLE = "assessor_unavailable"
    """The sufficiency call failed, refused, or answered unusably.

    **Stopping is the fail-safe direction and it is chosen deliberately.** The alternative — keep
    querying when the thing that decides whether to keep querying is broken — spends paid calls on
    the strength of an answer nobody got. The criterion is still analysed, on what round one
    retrieved, which is exactly what a single-step specialist would have had.
    """


class CancellationToken:
    """Cooperative cancellation, checked between steps. **ORCH-03.**

    A `threading.Event` and a reason, and deliberately nothing more. It is framework-free so both
    orchestration paths use the identical object, and cooperative because the alternative — killing
    a thread mid-call — loses the record of a model call that was already paid for.

    "Cooperative" also bounds what it can promise: this stops the loop between steps, not a model
    call already in flight. The gateway's own timeout is what bounds that.
    """

    def __init__(self) -> None:
        self._event = Event()
        self._reason = ""

    def cancel(self, reason: str) -> None:
        """Ask every checking node to stop. Idempotent; the first reason given is the one kept."""
        if not self._event.is_set():
            self._reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason


@dataclass(frozen=True)
class GatherStep:
    """One retrieval round, recorded so the loop is auditable rather than merely bounded."""

    query: str
    """What was asked. Round one is the criterion's own question."""

    span_ids: tuple[str, ...]
    """Everything this round returned."""

    new_span_ids: tuple[str, ...]
    """What this round added. Empty on any round after the first means no progress."""


@dataclass(frozen=True)
class GatheredEvidence:
    """What the loop found, and the account of how.

    `spans` is the deliverable. Everything else exists because a bounded loop that cannot say why
    it stopped is indistinguishable from one that found everything — the same reason rejections are
    output rather than log lines.
    """

    spans: tuple[RetrievedSpan, ...]
    steps: tuple[GatherStep, ...]
    stopped: GatherStop
    rejected: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    failed: RetrievalError | None = None
    """Set when retrieval itself failed, which is not the same as finding nothing."""

    assessments: int = 0
    """Sufficiency calls made. Counted rather than derived from `len(steps)`: the two differ
    whenever the loop stops on a ceiling between retrieving and assessing, and a spend figure
    inferred from a step count is the kind of number that is quietly wrong."""


def _excerpt_block(spans: tuple[RetrievedSpan, ...]) -> str:
    return "\n\n".join(
        f"[{s.evidence_id}] {s.title} ({s.document_id}, p.{s.page_number})\n"
        f"{s.text[:EXCERPT_CHARS]}{'…' if len(s.text) > EXCERPT_CHARS else ''}"
        for s in spans
    )


@dataclass(frozen=True)
class _Assessment:
    sufficient: bool
    next_query: str = ""
    rejection: str = ""
    """Non-empty when the answer could not be used; the caller then stops."""

    input_tokens: int = 0
    output_tokens: int = 0
    """Carried back rather than only recorded on the ledger. The ledger bounds the *run*; these
    reach the criterion's own token counts, and a stage whose spend is invisible per node is a
    stage nobody can decide is worth keeping."""


def _assess(
    criterion: Criterion,
    case_id: str,
    spans: tuple[RetrievedSpan, ...],
    gateway: ModelGateway,
    ledger: BudgetLedger | None,
) -> _Assessment:
    """Is this enough, and if not what should be searched for.

    **On the fast tier, not the thinking tier.** This is a triage question, and paying
    thinking-tier rates to decide whether to pay thinking-tier rates is how a loop stops being
    worth having.
    """
    request = ModelRequest(
        alias=ModelAlias.FAST,
        messages=(
            Message(
                role="user",
                content=(
                    f"CRITERION\n"
                    f"Authority: {criterion.policy_id} ({criterion.decision_domain.value})\n"
                    f"Question: {criterion.question}\n\n"
                    f"RETRIEVED SO FAR ({len(spans)} excerpts)\n\n"
                    f"{_excerpt_block(spans)}\n\n"
                    "Is this sufficient to assess the criterion? If not, what single search would "
                    "find what is missing?"
                ),
            ),
        ),
        system=SUFFICIENCY_SYSTEM,
        response_schema=SUFFICIENCY_SCHEMA,
        node_id=subcall_node_id(criterion.node_id, "sufficiency"),
    )

    try:
        response = gateway.complete(request)
    except ModelRefusalError as exc:
        # A refusal here is cheap to absorb: the criterion is still analysed on what round one
        # found. ADR-015 forbids retrying it, and there is nothing to retry it *for*.
        return _Assessment(
            sufficient=True,
            rejection=f"{criterion.criterion_id}: sufficiency check refused ({exc.category})",
        )
    except GatewayError as exc:
        _LOG.warning(
            "sufficiency check failed",
            extra={
                "case_id": case_id,
                "criterion_id": criterion.criterion_id,
                "error": type(exc).__name__,
            },
        )
        return _Assessment(
            sufficient=True,
            rejection=(
                f"{criterion.criterion_id}: sufficiency check failed ({type(exc).__name__})"
            ),
        )

    if ledger is not None:
        ledger.record(response.usage.input_tokens, response.usage.output_tokens)
    spent_in = response.usage.input_tokens
    spent_out = response.usage.output_tokens

    try:
        answer = json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        return _Assessment(
            sufficient=True,
            rejection=(f"{criterion.criterion_id}: sufficiency check returned unparseable output"),
            input_tokens=spent_in,
            output_tokens=spent_out,
        )
    if not isinstance(answer, dict) or "sufficient" not in answer:
        return _Assessment(
            sufficient=True,
            rejection=f"{criterion.criterion_id}: sufficiency check answered off-schema",
            input_tokens=spent_in,
            output_tokens=spent_out,
        )

    if answer.get("sufficient"):
        return _Assessment(sufficient=True, input_tokens=spent_in, output_tokens=spent_out)
    query = str(answer.get("next_query") or "").strip()
    if not query:
        # "Not sufficient" with nothing to search for is not actionable, and looping on the
        # previous query would re-buy the identical spans.
        return _Assessment(
            sufficient=True,
            rejection=(
                f"{criterion.criterion_id}: sufficiency check reported a gap and no query for it"
            ),
            input_tokens=spent_in,
            output_tokens=spent_out,
        )
    return _Assessment(
        sufficient=False, next_query=query, input_tokens=spent_in, output_tokens=spent_out
    )


def gather_evidence(
    criterion: Criterion,
    case_id: str,
    retriever: Retriever,
    gateway: ModelGateway,
    *,
    k: int,
    budgets: Budgets,
    max_steps: int = DEFAULT_MAX_STEPS,
    ledger: BudgetLedger | None = None,
    cancel: CancellationToken | None = None,
    calls_reserved: int = 0,
) -> GatheredEvidence:
    """Retrieve until the record is sufficient, the ceiling is reached, or nothing new turns up.

    `calls_reserved` is how many model calls the caller still intends to make after this returns —
    the analysis attempts. Counted against `max_model_calls_per_node` here so that gathering cannot
    consume the budget the analysis needs. A node that spends its whole allowance deciding what to
    read and then cannot afford to read it has failed in a way that looks like success.
    """
    seen: dict[str, RetrievedSpan] = {}
    steps: list[GatherStep] = []
    rejected: list[str] = []
    tokens_in = tokens_out = 0
    assessments = 0
    query = criterion.question
    stopped = GatherStop.STEP_LIMIT

    for step in range(max_steps):
        if cancel is not None and cancel.cancelled:
            stopped = GatherStop.CANCELLED
            rejected.append(
                f"{criterion.criterion_id}: evidence gathering cancelled ({cancel.reason})"
            )
            break
        if ledger is not None and ledger.breach() is not None:
            stopped = GatherStop.RUN_BUDGET
            break

        try:
            found = retriever.retrieve(case_id=case_id, query=query, k=k)
        except RetrievalError as exc:
            if not seen:
                # Nothing was ever retrieved, so the criterion cannot be analysed at all. Raised
                # to the caller as data rather than an exception, for the containment reason
                # ADR-021 §3 gives: one criterion's failure must not take the run down.
                return GatheredEvidence(
                    spans=(), steps=tuple(steps), stopped=GatherStop.STEP_LIMIT, failed=exc
                )
            # A later round failing is survivable: analyse what earlier rounds found.
            rejected.append(
                f"{criterion.criterion_id}: refinement query {step + 1} failed "
                f"({type(exc).__name__}) — analysed on what was already retrieved"
            )
            break

        new = tuple(s.evidence_id for s in found if s.evidence_id not in seen)
        for span in found:
            seen.setdefault(span.evidence_id, span)
        steps.append(
            GatherStep(query=query, span_ids=tuple(s.evidence_id for s in found), new_span_ids=new)
        )

        if step > 0 and not new:
            # **ORCH-03's no-progress detector.** A refined query that returns only what is
            # already held will keep returning it; another round is a paid call for a known answer.
            stopped = GatherStop.NO_PROGRESS
            rejected.append(
                f"{criterion.criterion_id}: refinement query {step + 1} surfaced no new evidence "
                "— gathering stopped"
            )
            break

        if len(seen) >= budgets.max_evidence_per_node:
            stopped = GatherStop.STEP_LIMIT
            rejected.append(
                f"{criterion.criterion_id}: reached max_evidence_per_node "
                f"({budgets.max_evidence_per_node}) — gathering stopped"
            )
            break

        if step + 1 >= max_steps:
            stopped = GatherStop.STEP_LIMIT
            break

        # One assessment call, plus whatever the caller has reserved for the analysis itself.
        if len(steps) + calls_reserved >= budgets.max_model_calls_per_node:
            stopped = GatherStop.CALL_BUDGET
            break

        assessment = _assess(criterion, case_id, tuple(seen.values()), gateway, ledger)
        assessments += 1
        tokens_in += assessment.input_tokens
        tokens_out += assessment.output_tokens
        if assessment.rejection:
            rejected.append(assessment.rejection)
            stopped = GatherStop.ASSESSOR_UNAVAILABLE
            break
        if assessment.sufficient:
            stopped = GatherStop.SUFFICIENT
            break
        query = assessment.next_query

    return GatheredEvidence(
        spans=tuple(seen.values()),
        steps=tuple(steps),
        stopped=stopped,
        rejected=tuple(rejected),
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        assessments=assessments,
    )


__all__ = [
    "DEFAULT_MAX_STEPS",
    "SUBCALL_SEPARATOR",
    "CancellationToken",
    "GatherStep",
    "GatherStop",
    "GatheredEvidence",
    "gather_evidence",
    "is_subcall",
    "subcall_node_id",
]
