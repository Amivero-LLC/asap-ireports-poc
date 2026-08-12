"""The Lambda entry point — one invocation runs one case start to finish.

ADR-023's target shape, made executable: **one invocation per run, with in-process fan-out.** The
orchestrator and every specialist call happen inside this one handler. There is no Step Function,
no Lambda per node, and no queue between specialists. `spikes/lambda_fit/` measured whether that
shape *packages*; this runs a real case through it.

`CANDIDATE` selects the orchestrator, exactly as in `lambda_fit`, and it comes from the function's
environment rather than from the event. That is not a style choice: each staged package contains
only its own candidate's dependency set, so a `handrolled` package has no LangGraph to import. An
event that asks for a candidate this function was not built for is rejected rather than silently
served by the wrong one.

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
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .case_loader import available_cases, load_case
from .orchestrator import ORCHESTRATORS
from .package import build_envelope

CANDIDATE = os.environ.get("CANDIDATE", "hand-rolled")

CASES_DIR = Path(os.environ.get("IREPORTS_DEMO_CASES_DIR") or Path(__file__).parent / "cases")
"""Where the staged cases live. `build.py` copies `cases/` in beside this module, so the packaged
default is correct inside the container; the override exists for running the handler on a host."""

_INIT_STARTED = time.perf_counter()

# Import the framework at module scope, where a real handler would have it, even though
# `LangGraphOrchestrator` imports it lazily inside `run()`. The lazy import is what lets a package
# built without LangGraph still import this module — but leaving it lazy here would move the cost
# from Lambda's init phase to the first invocation, which is a different billing and latency story
# and would quietly misrepresent the shape `lambda_fit` measured.
if CANDIDATE == "langgraph":
    import langgraph.graph  # noqa: F401  paid at init, deliberately

_INIT_SECONDS = time.perf_counter() - _INIT_STARTED

_RUN_ID = re.compile(r"^run_[A-Za-z0-9][A-Za-z0-9_\-]{0,62}$")


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
    from ireports_gateway import build_gateway

    gateway = build_gateway()

    result = ORCHESTRATORS[CANDIDATE].run(case, gateway, run_id)
    _log(
        "run_complete",
        run_id=run_id,
        wall_seconds=round(result.wall_seconds, 2),
        findings=len(result.findings),
        rejected=len(result.rejected),
        tokens=result.total_tokens,
    )

    payload: dict[str, Any] = {
        "candidate": CANDIDATE,
        "run_id": run_id,
        "case_id": case_id,
        "init_seconds": round(_INIT_SECONDS, 4),
        "wall_seconds": round(result.wall_seconds, 2),
        "findings": len(result.findings),
        "tokens": {
            "input": sum(o.input_tokens for o in result.outcomes),
            "output": sum(o.output_tokens for o in result.outcomes),
            "total": result.total_tokens,
        },
        # The rejections are part of the result, not an error log. They are the deterministic
        # shell doing its job, and a demo that hid them would put the safety story out of view.
        "rejected": list(result.rejected),
        "resolved_models": sorted({o.resolved_model for o in result.outcomes}),
        "criteria": [
            {
                "node_id": o.criterion.node_id,
                "criterion_id": o.criterion.criterion_id,
                "findings": len(o.findings),
                "rejected": len(o.rejected),
            }
            for o in result.outcomes
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
