"""The Lambda entry point — one invocation runs one case start to finish.

ADR-023's target shape, made executable: **one invocation per run, with in-process fan-out.** The
orchestrator and every specialist call happen inside this one handler. There is no Step Function,
no Lambda per node, and no queue between specialists. `spikes/lambda_fit/` measured whether that
shape *packages*; this runs a real case through it.

`CANDIDATE` selects the orchestrator and comes from the function's environment rather than from the
event, so an event asking for one this function was not built for is rejected rather than silently
served by the wrong one. There is one today (ADR-029 removed the LangGraph adapter); the mechanism
stays because a deployment may add its own implementation behind `Orchestrator`, and each staged
package carries only its own candidate's dependencies.

**Nothing here waits for a human** (ADR-022). The invocation returns an envelope of *proposals*;
an authorized officer reviews them in ASAP afterwards, with ASAP's tooling. There is no pause, no
disposition field, and nothing in the response that records what anyone decided.

**What reaches the logs.** The `log` lines below carry identifiers, counts, and timings only —
never evidence text (`CLAUDE.md`). Case text does appear in the *return value*, because the return
value is the `ASAPEnvelope`, and bounded evidence excerpts are what ADR-010 requires an envelope to
carry so a finding is reviewable on arrival. Delivering the payload and logging the payload are
different acts; this does the first.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ireports_domain import Budgets
from ireports_orchestration import ORCHESTRATORS, Checkpointing
from ireports_orchestration.budget import DEFAULT_BUDGETS
from ireports_orchestration.gather import CancellationToken

from .case_loader import available_cases, load_case
from .package import build_envelope

CANDIDATE = os.environ.get("CANDIDATE", "hand-rolled")

STATE_DSN = os.environ.get("IREPORTS_STATE_DSN") or None
"""Where paid calls and completed nodes are recorded, so a *second invocation* can use them.

**This is the whole of LAMB-01's mechanism.** A Lambda timeout kills the process, and the platform
retries the invocation — so everything the first attempt learned has to be somewhere that outlived
it. Unset means no durable state: the run works, and a retry redoes and re-pays for all of it.

Read from the environment rather than the event because it is deployment configuration, not a
property of the case (ADR-016). Inside a SAM container `localhost` is the container, so a local
database is reached at `host.docker.internal` — the same footgun as `IREPORTS_OPENSEARCH_URL`.
"""

CASES_DIR = Path(os.environ.get("IREPORTS_DEMO_CASES_DIR") or Path(__file__).parent / "cases")
"""Where the staged cases live. `build.py` copies `cases/` in beside this module, so the packaged
default is correct inside the container; the override exists for running the handler on a host."""

_INIT_STARTED = time.perf_counter()

# **Nothing to import here, and that is the measurement.** This block used to import an
# orchestration framework at module scope so its cost landed in Lambda's init phase where a real
# handler would pay it. The orchestrator now adds nothing to the dependency tree, so init is the
# standard library, `pydantic`, and the SDKs the gateway and retriever need.
_INIT_SECONDS = time.perf_counter() - _INIT_STARTED

_RUN_ID = re.compile(r"^run_[A-Za-z0-9][A-Za-z0-9_\-]{0,62}$")


def _budgets() -> Budgets:
    """The run's ceilings, from configuration.

    Only the wall clock is overridable here, and it is the one that matters: **the shell has to
    stop before the platform does, because that is the only moment it gets to checkpoint.** The
    default is 780s against this function's 900s timeout. Lowering it below the work required is
    how LAMB-01 is demonstrated without waiting thirteen minutes for a real ceiling.
    """
    # `.strip()`, not just a falsiness check: a variable set to whitespace is as absent as one
    # set to "" and `float("  ")` raises just as loudly. Found by a test, not by a live run — the
    # live run only paid for the empty-string half.
    raw = (os.environ.get("IREPORTS_MAX_WALL_CLOCK_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_BUDGETS
    return Budgets(
        max_input_tokens=DEFAULT_BUDGETS.max_input_tokens,
        max_output_tokens=DEFAULT_BUDGETS.max_output_tokens,
        max_wall_clock_seconds=float(raw),
    )


DEFAULT_DEADLINE_RESERVE_SECONDS = 60.0
"""How long before Lambda's own deadline the run is asked to stop. **ORCH-03's cancellation
driver, and the reason that clause is not vacuous.**

`max_wall_clock_seconds` is a *guess* at how long is safe — 780s against a 900s timeout, chosen
once and wrong for every function configured differently. `context.get_remaining_time_in_millis()`
is the platform's own answer, it accounts for time already spent in this invocation, and it is
correct whatever the function's timeout is set to. The budget stays as the backstop for every
caller that has no Lambda context at all.
"""


def _deadline_reserve() -> float:
    """Read at call time, and `or` rather than a `get` default. **Both halves cost a live run.**

    Every variable in `template.yaml` is declared with an **empty** default, because
    `sam local invoke --env-vars` only overrides variables the template already declares. So inside
    the container the variable is present and empty — and `os.environ.get(name, "60")` returns the
    default only when a name is *absent*, never when it is blank. `float("")` then raises.

    It raised at **module scope**, which is the second half: the handler's own docstring already
    says configuration is read inside the function so a bad value surfaces as this invocation's
    error rather than as an init failure Lambda reports without a message. This constant was
    written at module scope and did exactly that — `errorType: ValueError`, no case id, no
    variable name, before a single line of the handler ran.
    """
    raw = (os.environ.get("IREPORTS_DEADLINE_RESERVE_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_DEADLINE_RESERVE_SECONDS
    return float(raw)


def _deadline_watchdog(context: object, token: CancellationToken) -> threading.Timer | None:
    """Cancel the run shortly before Lambda would kill it.

    **A timeout is not a graceful stop.** The platform kills the process, the invocation is
    retried, and everything the run had in memory is gone — the checkpoint from a node that was
    mid-flight, most importantly. Stopping *ourselves* first is what turns a kill into a resume,
    and it is the same argument `max_wall_clock_seconds` makes with a worse clock.

    Returns the timer so the caller can cancel it; a daemon thread would not hold the process open,
    but leaving a live timer behind in a warm container means a later invocation inherits it.
    """
    remaining_ms = getattr(context, "get_remaining_time_in_millis", None)
    if remaining_ms is None:
        # No Lambda context — a host run, or a test. The wall-clock budget still applies.
        return None

    reserve = _deadline_reserve()
    delay = remaining_ms() / 1000 - reserve
    if delay <= 0:
        token.cancel("less than the reserve remained when the invocation started")
        return None

    reason = f"within {reserve:.0f}s of the Lambda deadline"
    timer = threading.Timer(delay, lambda: token.cancel(reason))
    timer.daemon = True
    timer.start()
    return timer


def _new_run_id(candidate: str) -> str:
    """A fresh run id.

    The `run_` prefix is not decoration — `RunId` rejects anything without it, and because
    `finding_id` embeds the run id, a bad one fails validation on *every finding* rather than at
    the top. The failure then looks exactly like the model producing unusable output.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{candidate.replace('-', '')}_{stamp}"


def _log(event: str, **fields: object) -> None:
    """One structured line. Identifiers, counts and timings only — never case text."""
    print(json.dumps({"event": event, "candidate": CANDIDATE, **fields}))


def handler(event: dict[str, Any] | None, context: object = None) -> dict[str, Any]:
    """Run one case through this function's orchestrator and return its envelope.

    Event fields:
      * `case_id`   — required; a directory under the packaged `cases/`
      * `candidate` — optional; must match this function's `CANDIDATE` if given
      * `run_id`    — optional; must carry the `run_` prefix

    Returns the envelope alongside the run's accounting. A run whose findings all fail validation
    returns `envelope: null` with the reason rather than raising: an empty envelope would assert
    "nothing found", which is a claim the run cannot make, and a crash would lose the rejection
    record that explains *why* nothing survived.
    """
    event = event or {}

    if CANDIDATE not in ORCHESTRATORS:
        raise ValueError(
            f"CANDIDATE={CANDIDATE!r} is not one of {sorted(ORCHESTRATORS)}; "
            "the function's environment is wrong, not the event"
        )

    requested = event.get("candidate")
    if requested and requested != CANDIDATE:
        raise ValueError(
            f"this function runs {CANDIDATE!r} and the event asked for {requested!r}. "
            "Each candidate is packaged with only its own dependencies — invoke the other function."
        )

    case_id = event.get("case_id")
    if not case_id:
        if not CASES_DIR.is_dir():
            raise ValueError(
                f"event needs a 'case_id', and {CASES_DIR} does not exist — build.py did not "
                "stage the cases into this package"
            )
        raise ValueError(
            f"event needs a 'case_id'. Available in this package: {available_cases(CASES_DIR)}"
        )

    run_id = event.get("run_id") or _new_run_id(CANDIDATE)
    if not _RUN_ID.match(run_id):
        raise ValueError(
            f"run_id {run_id!r} is not a valid RunId — it must start with 'run_'. Without the "
            "prefix every finding fails validation, which reads as a model problem and is not one."
        )

    case = load_case(CASES_DIR / case_id)
    _log("case_loaded", case_id=case_id, run_id=run_id, spans=len(case.spans))

    # Built here, not at module scope: a missing or malformed model configuration should surface
    # as this invocation's error, with the offending variable named, rather than as an init
    # failure that Lambda reports without the message.
    from ireports_gateway import build_embedding_gateway, build_gateway
    from ireports_orchestration.idempotency import IdempotentGateway, PostgresCallStore
    from ireports_retrieval import OpenSearchRetriever, connect

    gateway = build_gateway()
    # `IREPORTS_OPENSEARCH_URL` matters here: inside a SAM container `localhost` is the container,
    # not the host, so a local cluster is reached at `host.docker.internal`. Left to configuration
    # rather than detected, because the same code has to point at an AWS collection unchanged.
    retriever = OpenSearchRetriever(connect(), build_embedding_gateway())

    # **The two halves of surviving a timeout, and they are separate on purpose.** The call store
    # wraps the *gateway*, so a second invocation replays what the first paid for and neither
    # orchestrator knows it happened. The checkpoint is the *orchestrator's*, so a second
    # invocation skips nodes the first completed. The first saves money; the second saves wall
    # clock, and under a 15-minute ceiling wall clock is the resource actually in short supply.
    idempotent: IdempotentGateway | None = None
    checkpointing: Checkpointing | None = None
    if STATE_DSN:
        # `CREATE TABLE IF NOT EXISTS` on every invocation. Cheap, and the alternative is a
        # migration step this spike does not have.
        idempotent = IdempotentGateway(gateway, PostgresCallStore(STATE_DSN), run_id)
        gateway = idempotent
        checkpointing = Checkpointing(dsn=STATE_DSN)

    # The platform's clock, not ours. Cancels the run with time left to checkpoint and return.
    cancel = CancellationToken()
    watchdog = _deadline_watchdog(context, cancel)
    try:
        result = ORCHESTRATORS[CANDIDATE].run(
            case,
            gateway,
            retriever,
            run_id,
            budgets=_budgets(),
            checkpointing=checkpointing,
            cancel=cancel,
        )
    finally:
        # A warm container is reused, and a live timer left behind would cancel someone else's run.
        if watchdog is not None:
            watchdog.cancel()
    _log(
        "run_complete",
        run_id=run_id,
        wall_seconds=round(result.wall_seconds, 2),
        findings=len(result.findings),
        rejected=len(result.rejected),
        tokens=result.total_tokens,
        resumed=len(result.resumed_nodes),
        peak_concurrency=result.peak_concurrency,
        replayed_calls=idempotent.calls_replayed if idempotent else 0,
        cancelled=cancel.cancelled,
    )

    payload: dict[str, Any] = {
        "candidate": CANDIDATE,
        "run_id": run_id,
        "case_id": case_id,
        "init_seconds": round(_INIT_SECONDS, 4),
        "wall_seconds": round(result.wall_seconds, 2),
        "findings": len(result.findings),
        # A criterion nobody could analyse is not a criterion that came back clean. Surfaced at
        # the top of the payload because a reader scanning for "did this run actually work"
        # should not have to total up a per-criterion table to find out.
        "not_analysed": [o.criterion.criterion_id for o in result.outcomes if not o.analysed],
        "tokens": {
            "input": sum(o.input_tokens for o in result.outcomes),
            "output": sum(o.output_tokens for o in result.outcomes),
            "total": result.total_tokens,
        },
        # The rejections are part of the result, not an error log. They are the deterministic
        # shell doing its job, and a demo that hid them would put the safety story out of view.
        # A truncated run must be visibly truncated. `RunStatus.INCOMPLETE_DUE_TO_BUDGET` routes
        # to PACKAGING rather than FAILED (ADR-025 predates this; see `run.py`), so a run that hit
        # a ceiling still delivers what it has — and has to say so at the top, next to the other
        # facts a reader scans for "did this run actually cover the case".
        "incomplete_due_to_budget": result.breach is not None,
        "budget_breach": str(result.breach) if result.breach else None,
        # Cancelled and over-budget are different facts and the payload keeps them apart, for the
        # reason `SpecialistStatus.CANCELLED` exists: one is a decision, the other is a ceiling.
        "cancelled": cancel.cancelled,
        "cancel_reason": cancel.reason or None,
        # **What a second invocation of this run id would find, and what this one inherited.**
        # `durable` false means neither: the run is correct and a Lambda retry would re-do and
        # re-pay for every call, which is the failure LAMB-01 exists to close.
        "durable": STATE_DSN is not None,
        "resumed_nodes": list(result.resumed_nodes),
        # **The run's own evidence that it fanned out and branched.** Node ids and offsets in
        # seconds, nothing else — no case text ever reaches a trace (`CLAUDE.md`). A reader can
        # check that three specialists overlapped and that synthesis waited for all five, rather
        # than take a test name's word for it.
        "peak_concurrency": result.peak_concurrency,
        "trace": [
            {"node_id": s.node_id, "started": round(s.started, 3), "ended": round(s.ended, 3)}
            for s in result.trace
        ],
        "model_calls": (
            {
                # The LAMB-01 number: on a resumed invocation `paid` must cover only outstanding
                # work, and every call the first invocation completed must appear under `replayed`.
                "paid": idempotent.calls_made,
                "replayed": idempotent.calls_replayed,
            }
            if idempotent
            else None
        ),
        "consumption": (result.consumption.model_dump(mode="json") if result.consumption else None),
        "rejected": list(result.rejected),
        "resolved_models": sorted({o.resolved_model for o in result.outcomes}),
        "criteria": [
            {
                "node_id": o.criterion.node_id,
                "criterion_id": o.criterion.criterion_id,
                "status": o.status.value,
                "retrieved": list(o.retrieved),
                "findings": len(o.findings),
                "rejected": len(o.rejected),
            }
            for o in result.outcomes
        ],
    }

    if result.synthesis is not None:
        payload["synthesis"] = {
            "ran": result.synthesis.resolved_model is not None,
            "failed": result.synthesis.failed,
            "findings": len(result.synthesis.findings),
            "rejected": list(result.synthesis.rejected),
            # Computed, not inferred — which findings rest on the same span. This is the part that
            # tells a reviewer "these are several views of one fact."
            "overlaps": [
                {
                    "evidence_id": o.evidence_id,
                    "criterion_ids": list(o.criterion_ids),
                    "finding_ids": list(o.finding_ids),
                }
                for o in result.synthesis.overlaps
            ],
        }

    try:
        envelope = build_envelope(case, result.findings, run_id)
    except ValueError as exc:
        payload["envelope"] = None
        payload["envelope_error"] = str(exc)
        _log("envelope_skipped", run_id=run_id, reason="no findings survived validation")
        return payload

    payload["envelope"] = envelope.model_dump(mode="json")
    _log("envelope_built", run_id=run_id, message_id=envelope.message_id)
    return payload
