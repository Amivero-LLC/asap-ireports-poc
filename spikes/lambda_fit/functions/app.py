"""Lambda handler for the cold-start leg (ARCH-03).

Deliberately does almost nothing at request time. What is being measured is the **init phase** —
the module-level imports Lambda pays for before a handler ever runs — because that is where an
orchestration framework's dependency tree shows up on the bill and in p99 latency.

`CANDIDATE` selects which orchestrator module to import. Each staged build directory contains
exactly one candidate's source, so the import below is the real one, not a stand-in.
"""

from __future__ import annotations

import os
import time

_INIT_STARTED = time.perf_counter()

CANDIDATE = os.environ.get("CANDIDATE", "unknown")

# The expensive part, at module scope exactly as a real handler would have it.
if CANDIDATE == "langgraph":
    from spike_langgraph.orchestrator import LangGraphOrchestrator as _Orchestrator
elif CANDIDATE == "handrolled":
    from spike_handrolled.orchestrator import HandRolledOrchestrator as _Orchestrator
elif CANDIDATE == "strands":
    from spike_strands.orchestrator import StrandsOrchestrator as _Orchestrator
else:  # pragma: no cover - guarded by the build script
    raise RuntimeError(f"unknown CANDIDATE {CANDIDATE!r}")

_IMPORT_SECONDS = time.perf_counter() - _INIT_STARTED


def handler(event: object, context: object) -> dict[str, object]:
    """Report what init cost. The orchestrator is referenced, never run.

    Running a real fan-out here would measure model latency and Postgres round-trips, which are
    not what this leg is about and would drown the signal.
    """
    return {
        "candidate": CANDIDATE,
        "import_seconds": round(_IMPORT_SECONDS, 4),
        "orchestrator": _Orchestrator.__name__,
    }
