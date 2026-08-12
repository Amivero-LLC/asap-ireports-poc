"""Entry point. Argument handling lives in the harness so no candidate can differ.

The one extra line relative to the other candidates is `pin_tracing_closed()`, and it is here
rather than in `orchestrator.py` on purpose: a process-wide telemetry global is an entry-point
concern, in the same way and for the same reason that `.env` loading is (ADR-016).
"""

from __future__ import annotations

import sys

from ireports_spike_harness import main

from .orchestrator import LangGraphOrchestrator
from .telemetry import pin_tracing_closed

if __name__ == "__main__":
    pin_tracing_closed()
    sys.exit(main(LangGraphOrchestrator()))
