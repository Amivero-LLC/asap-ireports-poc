"""When each node ran — the run's own evidence that it fanned out and branched.

**Every claim this project makes about its orchestration was, until this module, a test
assertion.** That is worth something and it is not the same as evidence: a reader of the handoff
has to trust that the tests mean what their names say, and a fully *serial* implementation passes
every fan-out test in the suite, because they assert width (`5 outcomes for 5 criteria`) and a
ceiling (`never more than 3 at once`) and never once assert that two specialists overlapped in
time.

So a run now records when each node started and stopped, and carries it in `RunResult`. Three
things fall out of that, and all three are the kind a reader can check rather than believe:

* **Fan-out is concurrent, not a loop.** `peak_concurrency()` over a five-criterion case is 3, not
  1 — the same number on both orchestration paths, and equal to `MAX_PARALLEL` rather than to the
  fan-out width, which is the bound doing its job.
* **The barrier is real.** Synthesis starts after the last specialist ends, every time. That is the
  fan-in property stated as data instead of inferred from a call count.
* **The branch was taken, not merely not-taken.** A run with a synthesis span branched one way; a
  run without one branched the other. `synthesis is None` alone is equally consistent with a node
  that was never wired.

**Identifiers and timings only — never case text** (`CLAUDE.md`). A node id, two floats. Nothing
here can carry evidence, a finding, or a query, and nothing should ever be added that could.

Offsets are seconds from the start of the run, on a monotonic clock. Absolute timestamps would be
larger, less readable, and would move when the system clock did.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class NodeSpan:
    """One node's occupancy of the run's timeline."""

    node_id: str
    started: float
    ended: float

    @property
    def duration(self) -> float:
        return self.ended - self.started

    def overlaps(self, other: NodeSpan) -> bool:
        """Strictly — touching endpoints are not an overlap.

        Two nodes that ran back to back share an instant, and counting that as concurrency would
        make a serial implementation look parallel, which is the single thing this module exists
        to be able to tell apart.
        """
        return self.started < other.ended and other.started < self.ended


class RunTrace:
    """Thread-safe recorder of node timings.

    **Thread-safe for the same reason `BudgetLedger` is**: the hand-rolled path fans out through a
    `ThreadPoolExecutor` and several specialists finish at once. An unlocked append is the kind of
    race that loses a span quietly, and a trace missing a span understates concurrency — it would
    fail toward "this system is more serial than it is", which is the wrong direction for a
    document whose purpose is to show that it is not.

    The clock is injectable so a test can assert on exact offsets without sleeping.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started = clock()
        self._lock = Lock()
        self._spans: list[NodeSpan] = []

    @contextmanager
    def span(self, node_id: str) -> Iterator[None]:
        """Record one node's run.

        Recorded in a `finally`, so a node that raises still leaves a span. A crash is exactly when
        the timeline is most worth having, and a trace that only records successes would show a
        failed fan-out as one that never started.
        """
        started = self._clock() - self._started
        try:
            yield
        finally:
            with self._lock:
                self._spans.append(
                    NodeSpan(node_id=node_id, started=started, ended=self._clock() - self._started)
                )

    def spans(self) -> tuple[NodeSpan, ...]:
        with self._lock:
            return tuple(sorted(self._spans, key=lambda s: (s.started, s.node_id)))


def peak_concurrency(spans: tuple[NodeSpan, ...]) -> int:
    """The most nodes that were ever running at once.

    **This is the number that distinguishes a fan-out from a loop**, and it is the whole reason the
    timings are recorded. A sweep over start and end events rather than a pairwise comparison: the
    pairwise version is what people write first and it answers a different question — "did any two
    overlap" rather than "how many at once".

    Ends are processed before starts at the same instant, so two nodes that ran back to back count
    as one, not two. Same reasoning as `NodeSpan.overlaps`.
    """
    if not spans:
        return 0
    events = sorted(
        [(s.started, 1) for s in spans] + [(s.ended, -1) for s in spans],
        key=lambda e: (e[0], e[1]),
    )
    live = peak = 0
    for _at, delta in events:
        live += delta
        peak = max(peak, live)
    return peak


def timeline(spans: tuple[NodeSpan, ...], width: int = 44) -> list[str]:
    """The trace as something a person can read, for `run_case.py` and the handoff.

    A table of floats is evidence nobody checks. A bar chart of the same numbers is evidence
    someone glances at and immediately sees three specialists starting together — which is the
    claim being made.
    """
    if not spans:
        return []
    span_end = max(s.ended for s in spans) or 1.0
    label = max(len(s.node_id) for s in spans)
    rows = []
    for s in spans:
        start_col = int(s.started / span_end * width)
        # At least one cell, so a node too fast to measure still appears. A span rendered as an
        # empty row reads as a node that did not run.
        cells = max(1, int(s.duration / span_end * width))
        bar = " " * start_col + "#" * min(cells, width - start_col)
        rows.append(f"  {s.node_id:<{label}}  |{bar:<{width}}| {s.started:6.2f}-{s.ended:.2f}s")
    return rows


__all__ = ["NodeSpan", "RunTrace", "peak_concurrency", "timeline"]
