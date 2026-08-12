"""Two orchestrators behind one port, both fanning out on runtime data.

ADR-024 keeps custom Python and LangGraph both live until there is evidence to choose between
them. The protection against either becoming lock-in is that nodes depend on **our** interface and
never on a framework — easy to assert, and only meaningful because a second implementation
genuinely runs the same case and produces the same shape of answer.

`analyze` in `specialist.py` is shared by both, untouched. Neither orchestrator knows what a
criterion means; neither specialist knows what a graph is.

**The fan-out width comes from the case** (`criteria_for`), not from a constant. That is what makes
this a comparison at all: a fixed-width fan-out is one line in any framework, so a fixed one
measures nothing. With the width decided at runtime the two implementations stop being the same
program — see `LangGraphOrchestrator`, where it forces a different graph construction entirely.

The no-import rule is enforced rather than described: `test_nodes_do_not_import_langgraph` in
`spikes/lambda_demo/test_demo.py` fails if an analysis module ever grows a LangGraph import.
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
from ireports_retrieval import Retriever

from .case_loader import LoadedCase
from .criteria import Criterion, criteria_for
from .specialist import SpecialistOutcome, analyze
from .synthesis import SynthesisOutcome, synthesize

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
    criteria: tuple[Criterion, ...] = ()
    """Which criteria this case actually selected. Recorded because the fan-out width is now
    runtime data — without it, a run of four specialists and a run of two are indistinguishable
    after the fact, and "why did this case get analysed differently" is unanswerable."""

    synthesis: SynthesisOutcome | None = None
    """The cross-criterion stage. None when it did not run (fewer than two findings to reason
    across)."""

    @property
    def rejected(self) -> tuple[str, ...]:
        found = tuple(r for o in self.outcomes for r in o.rejected)
        return found + (self.synthesis.rejected if self.synthesis else ())

    @property
    def total_tokens(self) -> int:
        spent = sum(o.input_tokens + o.output_tokens for o in self.outcomes)
        if self.synthesis:
            spent += self.synthesis.input_tokens + self.synthesis.output_tokens
        return spent


class FanOutState(TypedDict):
    """LangGraph state for the fan-out.

    Module level, not nested in the method, and that is not cosmetic: `from __future__ import
    annotations` makes every annotation a string, and LangGraph resolves them with
    `get_type_hints`. A `TypedDict` defined inside a function has no resolvable scope for
    `Annotated`, so it raises `NameError` at graph construction. The failure looks like a
    LangGraph bug and is not one.

    The `operator.add` reducer is the load-bearing part: several branches write `outcomes`
    concurrently, and without it LangGraph rejects the concurrent update.

    `synthesis` is a list holding at most one item, which looks odd and is deliberate: it is
    written by a single node, but every key in a fan-out state still needs a reducer that can
    merge, and a list with `operator.add` is the honest way to say "appended to, not overwritten."
    """

    outcomes: Annotated[list[SpecialistOutcome], operator.add]
    synthesis: Annotated[list[SynthesisOutcome], operator.add]


class Orchestrator(Protocol):
    """The port. Neither implementation's type appears anywhere outside its own module."""

    name: str

    def run(
        self, case: LoadedCase, gateway: ModelGateway, retriever: Retriever, run_id: str
    ) -> RunResult: ...


def should_synthesize(outcomes: list[SpecialistOutcome]) -> bool:
    """Whether the second stage has anything to reason across.

    Shared by both paths deliberately: this is a *policy* decision about the run, and if each
    orchestrator decided it separately they would drift, and the drift would show up as two runs
    of the same case producing different envelopes for reasons nobody could see.

    Fewer than two findings cannot contradict each other, so the call would be paid for and
    guaranteed useless.
    """
    return sum(len(o.findings) for o in outcomes) >= 2


def _join_and_sort(
    outcomes: list[SpecialistOutcome],
    synthesis: SynthesisOutcome | None = None,
) -> tuple[ProposedFinding, ...]:
    """Fan-in.

    Sorted by finding_id so that two implementations producing the same findings produce the same
    *order*, which is what makes their outputs comparable at all. An unordered join would make
    every diff noise.

    Synthesis findings join the same pool rather than living in a separate section: they are
    `ProposedFinding`s like any other, and giving them a privileged place in the envelope would
    imply they carry more weight than a specialist's. They do not.
    """
    seen: dict[str, ProposedFinding] = {}
    for outcome in outcomes:
        for finding in outcome.findings:
            seen.setdefault(finding.finding_id, finding)
    for finding in synthesis.findings if synthesis else ():
        seen.setdefault(finding.finding_id, finding)
    return tuple(sorted(seen.values(), key=lambda f: f.finding_id))


class HandRolledOrchestrator:
    """No orchestration framework. A thread pool and a loop.

    Runtime-width fan-out changed **nothing** here: `pool.map` never cared how long the list was.
    That is the finding, and it is worth stating before the LangGraph version below, which had to
    be rebuilt around a different primitive to do the same thing.
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
            findings=_join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
        )


class LangGraphOrchestrator:
    """The same run as a LangGraph graph, fanning out on runtime data.

    **This is where the two paths stop being the same program.** The previous version added one
    node per criterion at construction time, which only works when the criteria are known before
    the graph is built. They are not: `criteria_for` reads the case. A graph cannot be built per
    case without rebuilding it per case — and rebuilding a graph you intend to checkpoint is a
    problem, because the checkpoint refers to node names that must still exist on resume.

    So this uses `Send`, LangGraph's dynamic-dispatch primitive: **one** node, dispatched N times
    from a conditional edge, where N is decided at runtime. The graph shape is now constant while
    the work is variable, which is the property a checkpoint needs.

    Two consequences worth knowing before you copy this:

    1. **A `Send` node receives the sent payload, not the graph state.** `specialist_node` takes a
       `Criterion`, not a `FanOutState`. This is easy to miss and type checkers will not catch it,
       because the node signature is whatever you wrote.
    2. **The reducer is still load-bearing and still silent when wrong.** Every dispatch writes
       `outcomes` concurrently. Without `operator.add` LangGraph raises on the concurrent update;
       with a plain (unreduced) value the dispatches clobber one another and you lose findings with
       no error at all.

    The import stays local to this method so a package built without LangGraph can still import
    this module and run the hand-rolled path — which is what "the framework is one adapter behind a
    port" has to mean when you actually try to package it.
    """

    name = "langgraph"

    def run(
        self, case: LoadedCase, gateway: ModelGateway, retriever: Retriever, run_id: str
    ) -> RunResult:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send

        started = datetime.now(UTC)
        criteria = criteria_for(case.manifest)

        def fan_out(_state: FanOutState):
            """One dispatch per criterion. The list length is the fan-out width.

            **The return type is deliberately unannotated.** Writing `-> list[Send]` raises
            `NameError: name 'Send' is not defined` at graph construction: `from __future__ import
            annotations` turns it into a string, LangGraph resolves it with `get_type_hints`, and
            `Send` is imported in this method's scope rather than at module level. `_state` is fine
            because `FanOutState` *is* module level.

            The general rule, of which the `FanOutState` placement is the other half: **every type
            named in a signature LangGraph inspects must be resolvable from module scope.** A lazy
            framework import and postponed annotations are individually reasonable and collide
            here.
            """
            return [Send("specialist", criterion) for criterion in criteria]

        def specialist_node(criterion: Criterion) -> dict[str, list[SpecialistOutcome]]:
            # Takes a Criterion, not FanOutState — see the class docstring.
            return {"outcomes": [analyze(criterion, case, gateway, retriever, run_id)]}

        def synthesis_node(state: FanOutState) -> dict[str, list[SynthesisOutcome]]:
            """The second stage. Reads every specialist's output from accumulated state.

            **The barrier is free here.** LangGraph runs in supersteps, so this node does not start
            until every `Send` dispatched above has finished — no join primitive, no waiting code.
            The hand-rolled path gets the same guarantee from exiting the `ThreadPoolExecutor`
            context, which is also one line. Neither is harder; they are the same idea spelled
            differently.
            """
            return {
                "synthesis": [synthesize(case, tuple(state["outcomes"]), criteria, gateway, run_id)]
            }

        def join(_state: FanOutState) -> dict[str, list[SpecialistOutcome]]:
            """A node that does nothing, and is required.

            **A conditional edge leaving a `Send`-dispatched node fires once per dispatch, and
            each firing sees only that dispatch's own state contribution — not the merged state.**
            Measured: five dispatches produced five router calls, each seeing exactly one outcome,
            never five. So a routing decision about the *aggregate* of a fan-out cannot be made on
            the edge leaving the fan-out node; every branch reads `len(outcomes) == 1` and decides
            on a run that does not exist.

            A *plain* edge behaves differently — it joins, and the target runs once. So this node
            exists purely to be that join point, and the conditional edge leaves it instead.

            The failure mode is the dangerous kind: no error, no warning, just a routing decision
            made on one-fifth of the evidence. `test_synthesis_runs_once_not_once_per_specialist`
            is what stops it coming back.
            """
            return {}

        def route_after_specialists(state: FanOutState):  # return type unannotated; see fan_out
            """Skip the second stage when there is nothing to reason across.

            Safe here, and only here, because `join` has already collapsed the fan-out — this sees
            every specialist's output.
            """
            return "synthesis" if should_synthesize(state["outcomes"]) else END

        graph: StateGraph = StateGraph(FanOutState)
        graph.add_node("specialist", specialist_node)
        graph.add_node("join", join)
        graph.add_node("synthesis", synthesis_node)
        graph.add_conditional_edges(START, fan_out, ["specialist"])
        graph.add_edge("specialist", "join")  # plain edge: joins, runs once
        graph.add_conditional_edges("join", route_after_specialists, ["synthesis", END])
        graph.add_edge("synthesis", END)

        final = graph.compile().invoke({"outcomes": [], "synthesis": []})
        outcomes = list(final["outcomes"])
        synthesis = final["synthesis"][0] if final["synthesis"] else None
        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=_join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
        )


ORCHESTRATORS: dict[str, Orchestrator] = {
    "hand-rolled": HandRolledOrchestrator(),
    "langgraph": LangGraphOrchestrator(),
}
