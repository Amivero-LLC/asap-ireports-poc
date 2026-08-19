"""The orchestrator, by name.

**One entry, and it used to be two.** ADR-027 chose custom Python and retained a LangGraph adapter
as a conformance arm; ADR-029 removed it, because the retention was a hedge that did not survive
being questioned — the second implementation never found a defect in shared code, only defects in
itself, which is a circular justification for carrying a framework, three dependencies, and a
telemetry client into everything that ships.

The mapping stays rather than collapsing into a direct import, for two reasons that outlive the
comparison: an entry point selects by *name* from configuration, and a team building the production
system may add their own implementation behind `Orchestrator`. `docs/handoff/build-guide.md` §5
describes that seam.
"""

from __future__ import annotations

from .handrolled import HandRolledOrchestrator
from .port import Orchestrator

ORCHESTRATORS: dict[str, Orchestrator] = {
    "hand-rolled": HandRolledOrchestrator(),
}

DEFAULT_ORCHESTRATOR = "hand-rolled"
"""What an entry point uses when configuration does not say.

Named rather than implied by `next(iter(ORCHESTRATORS))`, so adding a second implementation cannot
silently change which one a deployment gets."""
