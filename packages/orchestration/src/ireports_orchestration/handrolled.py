"""No orchestration framework. A thread pool and a loop.

The control arm of ADR-024. Kept honest by running the same case through the same shared
specialist as `langgraph_adapter.py` and being asserted to produce identical output.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from ireports_gateway.port import ModelGateway
from ireports_retrieval import Retriever

from .case import LoadedCase
from .criteria import Criterion, criteria_for
from .port import MAX_PARALLEL, RunResult, join_and_sort, should_synthesize
from .specialist import SpecialistOutcome, analyze
from .synthesis import synthesize


class HandRolledOrchestrator:
    """A thread pool and a loop.

    Runtime-width fan-out changed **nothing** here: `pool.map` never cared how long the list was.
    That is the finding, and it is worth stating before reading the LangGraph version, which had
    to be rebuilt around a different primitive to do the same thing.
    """

    name = "hand-rolled"

    def run(
        self, case: LoadedCase, gateway: ModelGateway, retriever: Retriever, run_id: str
    ) -> RunResult:
        started = datetime.now(UTC)
        criteria = criteria_for(case.manifest)

        def one(criterion: Criterion) -> SpecialistOutcome:
            return analyze(criterion, case, gateway, retriever, run_id)

        # `pool.map` is the barrier. The second stage needs every specialist's findings, and
        # exiting the context manager is what guarantees they are all in — one line, no primitive.
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            outcomes = list(pool.map(one, criteria))

        # The routing decision, as an `if`. That is the whole of it on this path.
        synthesis = (
            synthesize(case, tuple(outcomes), criteria, gateway, run_id)
            if should_synthesize(outcomes)
            else None
        )

        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
        )
