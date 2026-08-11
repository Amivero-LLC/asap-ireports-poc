"""Shared, framework-neutral substrate for the Milestone 1c orchestration bake-off.

Everything a candidate needs except the orchestration itself. The split is the point: if a
candidate had to bring its own scenario, its own gateway, or its own assertions, the bake-off
would compare three different experiments and call the result a comparison.

| Module | What it holds |
|---|---|
| `scenario` | The node bodies, identical for every candidate. Only the wiring differs. |
| `gateway` | Deterministic stub gateway with a durable, out-of-band call log. |
| `port` | The orchestration port, plus the subprocess CLI that makes leg 1 real. |
| `conformance` | The four ADR-012 legs, asserted once and applied to all. |
| `scorecard` | The deliverable, as a validated contract rather than a hand-typed table. |
"""

from __future__ import annotations

from .conformance import ConformanceReport, LegResult, run_all
from .gateway import DEFAULT_DSN, ModelTimeoutError, StubModelGateway, init_schema, reset
from .port import Orchestrator, ProcessResult, RunOutcome, die_hard, invoke, main
from .scenario import (
    CASE_ID,
    EXPECTED_FINDING_COUNT,
    FIXED_NOW,
    SPECIALIST_NODES,
    build_case,
    initialize,
    join_and_dedupe,
    package,
    policy_packs,
    route,
    specialist,
    validate,
)
from .scorecard import CandidateScore, LegOutcome, Scorecard

__all__ = [
    "CASE_ID",
    "DEFAULT_DSN",
    "EXPECTED_FINDING_COUNT",
    "FIXED_NOW",
    "SPECIALIST_NODES",
    "CandidateScore",
    "ConformanceReport",
    "LegOutcome",
    "LegResult",
    "ModelTimeoutError",
    "Orchestrator",
    "ProcessResult",
    "RunOutcome",
    "Scorecard",
    "StubModelGateway",
    "build_case",
    "die_hard",
    "init_schema",
    "initialize",
    "invoke",
    "join_and_dedupe",
    "main",
    "package",
    "policy_packs",
    "reset",
    "route",
    "run_all",
    "specialist",
    "validate",
]
