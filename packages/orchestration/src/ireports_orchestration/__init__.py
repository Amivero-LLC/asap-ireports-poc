"""Orchestration: criteria selection, specialists, synthesis, and two orchestrators behind one port.

The published surface deliberately does not name either adapter class. Callers pick an
orchestrator by name from `ORCHESTRATORS`, which is what keeps ADR-024's "both paths live" from
turning into "every caller knows about both frameworks."
"""

from __future__ import annotations

from .case import EvidenceSpan, LoadedCase
from .criteria import CATALOG, Criterion, NoApplicableCriteriaError, criteria_for
from .port import MAX_PARALLEL, Orchestrator, RunResult, join_and_sort, should_synthesize
from .registry import ORCHESTRATORS
from .specialist import SpecialistOutcome, SpecialistStatus, analyze
from .synthesis import Overlap, SynthesisOutcome, overlaps, synthesize

__all__ = [
    "CATALOG",
    "MAX_PARALLEL",
    "ORCHESTRATORS",
    "Criterion",
    "EvidenceSpan",
    "LoadedCase",
    "NoApplicableCriteriaError",
    "Orchestrator",
    "Overlap",
    "RunResult",
    "SpecialistOutcome",
    "SpecialistStatus",
    "SynthesisOutcome",
    "analyze",
    "criteria_for",
    "join_and_sort",
    "overlaps",
    "should_synthesize",
    "synthesize",
]
