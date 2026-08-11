"""CLI entry point. Every candidate's `__main__` is this shape and nothing more.

Argument handling lives in the harness so no candidate can advantage itself with a different
invocation, and so the conformance suite has exactly one contract to drive.
"""

from __future__ import annotations

import sys

from ireports_spike_harness import main

from .orchestrator import HandRolledOrchestrator

if __name__ == "__main__":
    sys.exit(main(HandRolledOrchestrator()))
