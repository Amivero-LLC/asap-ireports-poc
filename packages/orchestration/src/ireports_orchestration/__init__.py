"""Orchestration: criteria selection, specialists, synthesis, and two orchestrators behind one port.

The published surface deliberately does not name either adapter class. Callers pick an
orchestrator by name from `ORCHESTRATORS`, which is what keeps ADR-024's "both paths live" from
turning into "every caller knows about both frameworks."
"""

from __future__ import annotations

from .case import EvidenceSpan, LoadedCase
from .checkpoint import (
    Checkpointing,
    CheckpointStore,
    InMemoryCheckpointStore,
    PostgresCheckpointStore,
    RunCheckpoint,
)
from .coercion import MAX_REJECTIONS, cap_rejections, normalize_array
from .criteria import CATALOG, Criterion, NoApplicableCriteriaError, criteria_for
from .port import MAX_PARALLEL, Orchestrator, RunResult, join_and_sort, should_synthesize
from .registry import ORCHESTRATORS
from .specialist import SpecialistOutcome, SpecialistStatus, analyze
from .synthesis import Overlap, SynthesisOutcome, overlaps, synthesize
from .trace import NodeSpan, RunTrace, peak_concurrency, timeline

__all__ = [
    "CATALOG",
    "MAX_PARALLEL",
    "MAX_REJECTIONS",
    "ORCHESTRATORS",
    "CheckpointStore",
    "Checkpointing",
    "Criterion",
    "EvidenceSpan",
    "InMemoryCheckpointStore",
    "LoadedCase",
    "NoApplicableCriteriaError",
    "NodeSpan",
    "Orchestrator",
    "Overlap",
    "PostgresCheckpointStore",
    "RunCheckpoint",
    "RunResult",
    "RunTrace",
    "SpecialistOutcome",
    "SpecialistStatus",
    "SynthesisOutcome",
    "analyze",
    "cap_rejections",
    "criteria_for",
    "join_and_sort",
    "normalize_array",
    "overlaps",
    "peak_concurrency",
    "should_synthesize",
    "synthesize",
    "timeline",
]
