"""Two orchestrators behind one port — the architectural claim, made runnable.

ADR-012 chose LangGraph, and the protection against that choice becoming lock-in is that nodes
depend on **our** interface and never on LangGraph. That is easy to assert and only meaningful if
someone can run the same case through a second implementation and get the same shape of answer
out. So there are two here: a hand-rolled one with no orchestration framework at all, and a
LangGraph one.

`analyze_case` in `specialist.py` is shared by both, untouched. Neither orchestrator knows what a
criterion is; neither specialist knows what a graph is. That separation is the thing being shown.

The no-import rule is enforced rather than described: `test_nodes_do_not_import_langgraph` in
`spikes/lambda_demo/test_demo.py` fails if the specialist module ever grows a LangGraph import.
"""

from __future__ import annotations

import operator
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Protocol, TypedDict

from ireports_domain import ProposedFinding
from ireports_gateway.port import ModelGateway

from .case_loader import LoadedCase
from .specialist import CRITERIA, Criterion, SpecialistOutcome, analyze

MAX_PARALLEL = int(os.environ.get("IREPORTS_DEMO_MAX_PARALLEL", "3"))
"""Bounded fan-out. `Budgets.max_parallel_specialists` defaults to 4 and caps at 16; this mirrors
that rather than inventing a second concept. Unbounded fan-out over paid model calls is the
failure mode budgets exist to prevent."""


@dataclass(frozen=True)
class RunResult:
    """What one orchestration produced.

    Identical shape from both implementations — that is the point.
    """

    run_id: str
    candidate: str
    findings: tuple[ProposedFinding, ...]
    outcomes: tuple[SpecialistOutcome, ...]
    wall_seconds: float

    @property
    def rejected(self) -> tuple[str, ...]:
        return tuple(r for o in self.outcomes for r in o.rejected)

    @property
    def total_tokens(self) -> int:
        return sum(o.input_tokens + o.output_tokens for o in self.outcomes)


class FanOutState(TypedDict):
    """LangGraph state for the fan-out.

    Module level, not nested in the method, and that is not cosmetic: `from __future__ import
    annotations` makes every annotation a string, and LangGraph resolves them with
    `get_type_hints`. A `TypedDict` defined inside a function has no resolvable scope for
    `Annotated`, so it raises `NameError` at graph construction. The failure looks like a
    LangGraph bug and is not one.

    The `operator.add` reducer is the load-bearing part: several branches write `outcomes`
    concurrently, and without it LangGraph rejects the concurrent update.
    """

    outcomes: Annotated[list[SpecialistOutcome], operator.add]


class Orchestrator(Protocol):
    """The port. Neither implementation's type appears anywhere outside its own module."""

    name: str

    def run(self, case: LoadedCase, gateway: ModelGateway, run_id: str) -> RunResult: ...


def _join_and_sort(outcomes: list[SpecialistOutcome]) -> tuple[ProposedFinding, ...]:
    """Fan-in.

    Sorted by finding_id so that two implementations producing the same findings produce the same
    *order*, which is what makes their outputs comparable at all. An unordered join would make
    every diff noise.
    """
    seen: dict[str, ProposedFinding] = {}
    for outcome in outcomes:
        for finding in outcome.findings:
            seen.setdefault(finding.finding_id, finding)
    return tuple(sorted(seen.values(), key=lambda f: f.finding_id))


class HandRolledOrchestrator:
    """No orchestration framework. A thread pool and a loop.

    Retained as the control for the same reason the bake-off retained it: if the framework version
    produces something this cannot, that is worth knowing, and if it does not, the port is real.
    """

    name = "hand-rolled"

    def run(self, case: LoadedCase, gateway: ModelGateway, run_id: str) -> RunResult:
        started = datetime.now(UTC)
        outcomes: list[SpecialistOutcome] = []

        def one(criterion: Criterion) -> SpecialistOutcome:
            return analyze(criterion, case, gateway, run_id)

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            outcomes = list(pool.map(one, CRITERIA))

        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=_join_and_sort(outcomes),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
        )


class LangGraphOrchestrator:
    """The same run as a LangGraph `StateGraph`.

    The import is local to this method, not module-level, so that a package built without
    LangGraph can still import this module and run the hand-rolled candidate. That is not a trick
    to dodge a dependency — it is what "the framework is one adapter behind a port" means when you
    try to package it.
    """

    name = "langgraph"

    def run(self, case: LoadedCase, gateway: ModelGateway, run_id: str) -> RunResult:
        from typing import TypedDict

        from langgraph.graph import END, START, StateGraph

        started = datetime.now(UTC)

        # The reducer is the whole trick, and getting it wrong is silent. Several branches write
        # to `outcomes` concurrently; without `operator.add` LangGraph raises on the concurrent
        # update, and with a plain dict state the branches clobber one another instead.
        class State(TypedDict):
            outcomes: Annotated[list[SpecialistOutcome], operator.add]

        def make_node(criterion: Criterion):
            def node(_state: State) -> dict[str, list[SpecialistOutcome]]:
                return {"outcomes": [analyze(criterion, case, gateway, run_id)]}

            return node

        graph: StateGraph = StateGraph(State)
        for criterion in CRITERIA:
            graph.add_node(criterion.node_id, make_node(criterion))
            graph.add_edge(START, criterion.node_id)
            graph.add_edge(criterion.node_id, END)

        final = graph.compile().invoke({"outcomes": []})
        outcomes = list(final["outcomes"])
        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=_join_and_sort(outcomes),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
        )


ORCHESTRATORS: dict[str, Orchestrator] = {
    "hand-rolled": HandRolledOrchestrator(),
    "langgraph": LangGraphOrchestrator(),
}
