"""The same run as a LangGraph graph — the one module in this package that names the framework.

**This is where the two paths stop being the same program.** An earlier version added one node per
criterion at construction time, which only works when the criteria are known before the graph is
built. They are not: `criteria_for` reads the case. A graph cannot be built per case without
rebuilding it per case — and rebuilding a graph you intend to checkpoint is a problem, because the
checkpoint refers to node names that must still exist on resume.

So this uses `Send`, LangGraph's dynamic-dispatch primitive: **one** node, dispatched N times from
a conditional edge, where N is decided at runtime. The graph shape is now constant while the work
is variable, which is the property a checkpoint needs.

Nothing that analyses a case is allowed to import LangGraph, and a test asserts it against every
other module in this package. The rule is only meaningful because this file exists — a port with
one implementation proves nothing about lock-in.

**What `mypy --strict` makes of this, which is the fourth asymmetry (`docs/LESSONS.md`).** Moving
this file out of `spikes/` and into a type-checked tree produced five errors, and every one is
LangGraph's typing disagreeing with LangGraph's own documented `Send` pattern:

* `add_node`'s overloads are written around a node that receives the graph **state**. A
  `Send`-dispatched node receives the *sent payload* — a `Criterion` here — so the construction
  LangGraph's own documentation prescribes matches no overload.
* `join` fails overload resolution too, and not for that reason: it takes `FanOutState` like any
  ordinary node. `synthesis_node`, with the same parameter type and a different return type,
  resolves fine. Whatever separates them is not visible from the call site.
* `StateGraph` is generic in four parameters at runtime and is written unparameterised in every
  example.
* The two router callables cannot be given return annotations at all, because `Send` and `END` are
  not resolvable from module scope under `from __future__ import annotations` (see `fan_out`), and
  an unannotated function is a `--strict` error by definition.

So the framework's own idiom is un-typecheckable under the setting this repo runs everywhere else,
and the suppressions are load-bearing rather than lazy. The hand-rolled path needed none: it is a
`ThreadPoolExecutor` over a function with ordinary annotations. Recorded, not editorialised — this
is a cost, not a verdict, and durable checkpointing is still the question that decides ADR-024.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import Annotated, TypedDict

from ireports_domain import Budgets
from ireports_gateway.port import ModelGateway
from ireports_retrieval import Retriever

from .case import LoadedCase
from .criteria import Criterion, criteria_for
from .port import RunResult, join_and_sort, new_ledger, should_synthesize
from .specialist import SpecialistOutcome, analyze, skipped_for_budget
from .synthesis import SynthesisOutcome, synthesize


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


class LangGraphOrchestrator:
    """The LangGraph arm of ADR-024, fanning out on runtime data.

    Two consequences worth knowing before you copy this:

    1. **A `Send` node receives the sent payload, not the graph state.** `specialist_node` takes a
       `Criterion`, not a `FanOutState`. This is easy to miss and type checkers will not catch it,
       because the node signature is whatever you wrote.
    2. **The reducer is still load-bearing and still silent when wrong.** Every dispatch writes
       `outcomes` concurrently. Without `operator.add` LangGraph raises on the concurrent update;
       with a plain (unreduced) value the dispatches clobber one another and you lose findings with
       no error at all.

    The framework import stays local to `run()` so a package built without the `langgraph` extra
    can still import `ireports_orchestration` and run the hand-rolled path — which is what "the
    framework is one adapter behind a port" has to mean when you actually try to package it.
    `spikes/lambda_demo/build.py` builds exactly that split.
    """

    name = "langgraph"

    def run(
        self,
        case: LoadedCase,
        gateway: ModelGateway,
        retriever: Retriever,
        run_id: str,
        budgets: Budgets | None = None,
    ) -> RunResult:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send

        started = datetime.now(UTC)
        criteria = criteria_for(case.manifest)
        ledger = new_ledger(budgets)

        def fan_out(_state: FanOutState):  # type: ignore[no-untyped-def]  # see below
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
            #
            # **The budget check is the same three lines as the hand-rolled path**, and that is
            # the result rather than an implementation detail. `Send` has already dispatched every
            # criterion by the time any node runs, so neither path can withdraw work; both can
            # only make it cheap. Early termination mid-fan-out is a second null result.
            breach = ledger.breach()
            if breach is not None:
                return {
                    "outcomes": [
                        skipped_for_budget(criterion, case.manifest.case_id, run_id, breach)
                    ]
                }
            return {
                "outcomes": [analyze(criterion, case, gateway, retriever, run_id, ledger=ledger)]
            }

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

        def route_after_specialists(  # type: ignore[no-untyped-def]  # see fan_out
            state: FanOutState,
        ):
            """Skip the second stage when there is nothing to reason across.

            Safe here, and only here, because `join` has already collapsed the fan-out — this sees
            every specialist's output.

            The budget clause rides along on the existing conditional edge, which is the one place
            LangGraph is *cheaper* here: the routing point already existed, so declining to pay for
            a second stage costs one boolean rather than a new edge.
            """
            if ledger.breach() is not None:
                return END
            return "synthesis" if should_synthesize(state["outcomes"]) else END

        # `type: ignore` on every one of these, and they are not noise — see the module
        # docstring's "what mypy --strict makes of this".
        graph: StateGraph = StateGraph(FanOutState)  # type: ignore[type-arg]
        graph.add_node("specialist", specialist_node)  # type: ignore[call-overload]
        graph.add_node("join", join)  # type: ignore[call-overload]
        graph.add_node("synthesis", synthesis_node)  # a plain state node; no ignore needed
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
            findings=join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
            consumption=ledger.consumption(),
            breach=ledger.breach(),
        )
