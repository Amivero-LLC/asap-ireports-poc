"""Entry point. Argument handling lives in the harness so no candidate can differ."""

import sys

from ireports_spike_harness import main

from .orchestrator import StrandsOrchestrator

sys.exit(main(StrandsOrchestrator()))
