"""No orchestration framework. A thread pool and a loop.

The control arm of ADR-024. Kept honest by running the same case through the same shared
specialist as `langgraph_adapter.py` and being asserted to produce identical output.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from ireports_domain import Budgets
from ireports_gateway.port import ModelGateway
from ireports_retrieval import Retriever

from .case import LoadedCase
from .checkpoint import Checkpointing, RunCheckpoint
from .criteria import Criterion, criteria_for
from .port import MAX_PARALLEL, RunResult, join_and_sort, new_ledger, should_synthesize
from .specialist import SpecialistOutcome, analyze, skipped_for_budget
from .synthesis import synthesize


class HandRolledOrchestrator:
    """A thread pool and a loop.

    Runtime-width fan-out changed **nothing** here: `pool.map` never cared how long the list was.
    That is the finding, and it is worth stating before reading the LangGraph version, which had
    to be rebuilt around a different primitive to do the same thing.

    **Node-level checkpointing is four lines**, and they are visible below: ask the checkpoint
    before working, tell it after. There is no state machine, no resume mode, and no second code
    path — a resumed run is the same run, over a store that already has rows in it. Read
    `langgraph_adapter.py` next; that is where the comparison is.
    """

    name = "hand-rolled"

    def run(
        self,
        case: LoadedCase,
        gateway: ModelGateway,
        retriever: Retriever,
        run_id: str,
        budgets: Budgets | None = None,
        checkpointing: Checkpointing | None = None,
    ) -> RunResult:
        started = datetime.now(UTC)
        criteria = criteria_for(case.manifest)
        ledger = new_ledger(budgets)
        # Loaded once, before any work: the set of already-completed nodes cannot change under a
        # run that is the only writer for its own id.
        checkpoint: RunCheckpoint | None = (
            checkpointing.run_checkpoint(run_id) if checkpointing is not None else None
        )

        def one(criterion: Criterion) -> SpecialistOutcome:
            # **Asked before the budget is.** A restored node costs neither money nor time, so
            # declining to restore it because the run has overspent would mean re-doing work in
            # order to save resources — and worse, it would drop a node the checkpoint says is
            # already done.
            if checkpoint is not None:
                restored = checkpoint.restore_specialist(criterion)
                if restored is not None:
                    return restored

            # **Checked here, per criterion, rather than once before the fan-out.** The pool still
            # schedules every criterion — neither path can un-dispatch work it has already decided
            # to do — so the saving is that a criterion reached after a ceiling costs nothing
            # instead of a model call. With `max_workers` below the fan-out width, later criteria
            # genuinely have not started yet when an earlier one exhausts the budget.
            breach = ledger.breach()
            if breach is not None:
                return skipped_for_budget(criterion, case.manifest.case_id, run_id, breach)

            outcome = analyze(criterion, case, gateway, retriever, run_id, ledger=ledger)
            # Committed here, inside the worker, rather than after the pool joins. That is what
            # lets a crash mid-fan-out keep the specialists that finished; a commit after the
            # barrier would keep none of them.
            if checkpoint is not None:
                checkpoint.record_specialist(outcome)
            return outcome

        # `pool.map` is the barrier. The second stage needs every specialist's findings, and
        # exiting the context manager is what guarantees they are all in — one line, no primitive.
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            outcomes = list(pool.map(one, criteria))

        # The routing decision, as an `if`. That is the whole of it on this path, and the budget
        # adds one clause: a run that has already overspent does not pay for a second stage.
        breach = ledger.breach()
        synthesis = checkpoint.restore_synthesis() if checkpoint is not None else None
        if synthesis is None and breach is None and should_synthesize(outcomes):
            synthesis = synthesize(case, tuple(outcomes), criteria, gateway, run_id)
            if checkpoint is not None:
                checkpoint.record_synthesis(synthesis)

        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
            consumption=ledger.consumption(),
            resumed_nodes=checkpoint.resumed if checkpoint is not None else (),
            breach=ledger.breach(),
        )
