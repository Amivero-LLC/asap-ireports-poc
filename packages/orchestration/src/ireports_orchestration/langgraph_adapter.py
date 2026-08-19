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

**Checkpointing is what this file was built for**, and it is the fifth and largest asymmetry.
Three things are worth reading before the code:

1. **`PostgresSaver` really is first-party, and it really does save work.** `setup()` creates and
   migrates its own tables. Nothing here writes SQL. Against `checkpoint.py`'s hand-rolled store
   that is a genuine saving, and it is the thing ADR-012 chose LangGraph for.
2. **Turning on the security setting ORCH-01 requires costs you the type safety.** Under strict
   deserialization LangGraph does not *refuse* to load a dataclass — it silently hands back a
   `dict`, on the resume path only. So the state channels below carry plain JSON produced by
   `checkpoint.py`'s codec, which is the framework-free code the hand-rolled path also uses. The
   first-party checkpointer does not save you from writing the codec; it saves you from writing
   the *store*.
3. **A node that returns is a node LangGraph will never re-run.** That is correct for a crash and
   wrong for a budget stop: a criterion skipped because the run ran out of wall clock is the work
   the next invocation exists to do. So the budget path here *raises* (`_BudgetStop`) where the
   hand-rolled path returns a value, and `run()` reconstructs the skipped outcomes afterwards so
   both paths still report the same thing. Measured: five dispatches, one raising — the four
   completed siblings' writes survive, and only the raiser re-runs.

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
`ThreadPoolExecutor` over a function with ordinary annotations. Recorded, not editorialised.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict

from ireports_domain import Budgets
from ireports_gateway.port import ModelGateway
from ireports_retrieval import Retriever

from .case import LoadedCase
from .checkpoint import (
    SYNTHESIS_NODE,
    Checkpointing,
    outcome_from_json,
    outcome_to_json,
    synthesis_from_json,
    synthesis_to_json,
)
from .criteria import criteria_for
from .gather import CancellationToken
from .port import (
    MAX_PARALLEL,
    RunResult,
    join_and_sort,
    new_ledger,
    should_synthesize,
    stop_reason,
    unstarted,
)
from .specialist import SpecialistStatus, analyze
from .synthesis import SynthesisOutcome, synthesize

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import BaseCheckpointSaver


DURABILITY: Literal["sync"] = "sync"
"""When LangGraph makes a completed task's output durable. **The ORCH-01 clause, and the default
is wrong for us.**

LangGraph submits `put_writes` to a background executor, so persistence normally runs concurrently
with the next node — a process killed in that window loses a write it appears to have made. Under
Lambda the process is killed on a timer, which makes that window the one that matters.

A module constant rather than a literal at the call site, for the same reason `strict_serde` is a
function: a security- or durability-relevant setting that appears once inside a method is a setting
nobody can assert on. `tests/orchestration/test_checkpoint.py` asserts this value.
"""


class FanOutState(TypedDict):
    """LangGraph state for the fan-out.

    Module level, not nested in the method, and that is not cosmetic: `from __future__ import
    annotations` makes every annotation a string, and LangGraph resolves them with
    `get_type_hints`. A `TypedDict` defined inside a function has no resolvable scope for
    `Annotated`, so it raises `NameError` at graph construction. The failure looks like a
    LangGraph bug and is not one.

    The `operator.add` reducer is the load-bearing part: several branches write `outcomes`
    concurrently, and without it LangGraph rejects the concurrent update.

    **Both channels carry plain JSON dicts rather than our own types, and that is forced.**
    `strict_serde()` restricts checkpoint deserialization to an allowlist, and a type not on it is
    not rejected — it comes back as a `dict`. A `SpecialistOutcome` written to state would resume
    as a dict, `join_and_sort` would fail on `.findings`, and it would fail *only after a crash*,
    which is the worst possible time to discover a type error. Encoding on the way in makes the
    round trip lossless and the failure impossible.

    `synthesis` is a list holding at most one item, which looks odd and is deliberate: it is
    written by a single node, but every key in a fan-out state still needs a reducer that can
    merge, and a list with `operator.add` is the honest way to say "appended to, not overwritten."
    """

    outcomes: Annotated[list[dict[str, Any]], operator.add]
    synthesis: Annotated[list[dict[str, Any]], operator.add]


class _StopWork(Exception):  # noqa: N818 — a control signal, not an error
    """Raised by a specialist node when the run should stop and this criterion is not done.

    **Not an error, and not how the hand-rolled path spells this.** There it is a `return`, because
    a returned value is just a value. Here a returned value is a *completed task*, and LangGraph
    will never re-run a completed task — so returning a budget skip or a cancellation would tell
    the checkpoint that the criterion is done, and the next invocation whose entire job is to
    finish it would find nothing to do.

    Raising leaves the task pending. Its completed siblings' writes are already durable under
    `durability="sync"`, so the resume re-runs exactly the criteria nobody got to.

    It carries only a message: `run()` re-derives *why* from the ledger and the token, using the
    same `stop_reason` both paths share, so the two cannot disagree about which fact stopped a run.
    """

    def __init__(self, why: str) -> None:
        super().__init__(why)


def strict_serde() -> Any:
    """The checkpoint serializer, with deserialization restricted to an allowlist. **ORCH-01.**

    **This is not a precaution against a hypothetical.** `langgraph/checkpoint/serde/_msgpack.py`
    states it first-party: *"Set `LANGGRAPH_STRICT_MSGPACK=true` to restrict checkpoint
    deserialization to the types listed in `SAFE_MSGPACK_TYPES`. Without this, any Python callable
    stored in checkpoint data will be imported and executed on load."* The default is permissive.

    `allowed_msgpack_modules=None` selects the same strict mode as that environment variable, and
    selects it **in code**, so it cannot be lost by an environment that forgot to set it.
    `pickle_fallback` already defaults to `False`; it is passed explicitly so that a future default
    change is visible in a diff.

    **What it costs, measured.** Under this setting a `@dataclass` or a Pydantic model does not
    fail to load — it comes back as a plain `dict`, with a warning on stderr and no exception. See
    `FanOutState`: the state channels carry JSON for exactly this reason. Full reasoning:
    `docs/handoff/checkpoint-threat-model.md`.
    """
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)


def _saver(checkpointing: Checkpointing) -> BaseCheckpointSaver[Any]:
    """LangGraph's own checkpointer, built from the shared `Checkpointing` vocabulary.

    **The asymmetry `Checkpointing` documents, in code.** The hand-rolled path takes a
    `CheckpointStore`; this takes a `BaseCheckpointSaver`, which `checkpoint.py` may not name
    because no analysis module may import the framework. All the two can share is a connection
    string — so `dsn` builds a `PostgresSaver` and no dsn builds an `InMemorySaver`, which proves
    the skip and not the durability.
    """
    if checkpointing.saver is not None:
        # Handed in by a caller that needs the checkpointer to outlive one `run()` — a test
        # resuming in-process, most obviously. `Checkpointing.saver` is `Any` because this
        # package's other modules may not name a LangGraph type.
        saver: BaseCheckpointSaver[Any] = checkpointing.saver
        return saver

    if checkpointing.dsn is None:
        from langgraph.checkpoint.memory import InMemorySaver

        # **Fresh per run, and therefore useless for resuming.** An `InMemorySaver` built here
        # dies with the call that built it, so this configuration checkpoints into a bucket
        # nobody reads. It exists so that a graph is always compiled the same way; a caller that
        # actually intends to resume passes `saver` or `dsn`.
        return InMemorySaver(serde=strict_serde())

    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    # `dict_row` is required by `PostgresSaver`, not a preference — it reads rows by name.
    conn = psycopg.connect(checkpointing.dsn, autocommit=True, row_factory=dict_row)
    saver = PostgresSaver(conn, serde=strict_serde())
    # Creates and migrates its own tables, and is idempotent. **This is the saving that is
    # actually real**: `checkpoint.py` had to write its schema, its upsert, and its read.
    saver.setup()
    return saver


class LangGraphOrchestrator:
    """The LangGraph arm of ADR-024, fanning out on runtime data, checkpointed per node.

    Three consequences worth knowing before you copy this:

    1. **A `Send` node receives the sent payload, not the graph state.** `specialist_node` takes a
       `Criterion`, not a `FanOutState`. This is easy to miss and type checkers will not catch it,
       because the node signature is whatever you wrote.
    2. **The reducer is still load-bearing and still silent when wrong.** Every dispatch writes
       `outcomes` concurrently. Without `operator.add` LangGraph raises on the concurrent update;
       with a plain (unreduced) value the dispatches clobber one another and you lose findings with
       no error at all.
    3. **Resuming is `invoke(None, config)`, not `invoke(payload, config)`.** Passing the initial
       payload again on a resume merges it back into state through the reducers — which for
       `operator.add` means appending an empty list, harmless here and not harmless in general.
       `run()` therefore asks the saver whether this thread already exists before deciding.

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
        checkpointing: Checkpointing | None = None,
        cancel: CancellationToken | None = None,
    ) -> RunResult:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send

        started = datetime.now(UTC)
        criteria = criteria_for(case.manifest)
        ledger = new_ledger(budgets)
        by_node = {c.node_id: c for c in criteria}

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

            **The payload is a `node_id`, not the `Criterion`, and that is not a style choice.**
            A `Send` payload is checkpointed as a pending write, so it goes through the same strict
            deserialization as the state channels — and comes back as a `dict`. Dispatching the
            dataclass works perfectly until the first resume, then fails inside `analyze` with
            `'dict' object has no attribute 'question'`. Measured, on the first run of the
            cross-process test. The identifier round-trips as itself; the criterion is looked up
            from the case.
            """
            return [Send("specialist", criterion.node_id) for criterion in criteria]

        def specialist_node(node_id: str) -> dict[str, list[dict[str, Any]]]:
            # Takes the sent payload, not FanOutState — see the class docstring.
            criterion = by_node[node_id]
            #
            # **There is no "have I already done this?" check here**, and its absence is the
            # clearest thing this file has to say. LangGraph does not dispatch a task whose writes
            # it already holds, so a resumed run never enters this function for a completed
            # criterion. The hand-rolled path has to ask; this one cannot be asked.
            breach, cancel_reason = stop_reason(ledger, cancel)
            if breach is not None or cancel_reason:
                # **The same stop, spelled two ways, and the branch is the finding.** A returned
                # value here is simultaneously "the partial result" and "this task is finished",
                # and a budget stop needs those separated: it wants to report the skip *and* leave
                # the work pending. LangGraph gives one mechanism for both, so which one is
                # correct depends on whether anything is going to resume.
                #
                # Checkpointed: raise, leaving the task pending for the next invocation. The
                # completed siblings' writes are already durable, and `run()` reads them back.
                # Not checkpointed: return the skip, because nothing will resume and a raise would
                # throw away every other specialist's completed, paid-for work — which is the
                # containment failure ADR-021 §3 already cost this project once.
                #
                # The hand-rolled path needs one spelling for both cases: a `return` there is only
                # ever a value.
                if checkpointing is not None:
                    raise _StopWork(cancel_reason or str(breach))
                stopped = unstarted(
                    (criterion,), set(), case.manifest.case_id, run_id, breach, cancel_reason
                )
                return {"outcomes": [outcome_to_json(o) for o in stopped]}
            outcome = analyze(
                criterion, case, gateway, retriever, run_id, ledger=ledger, cancel=cancel
            )
            if outcome.status is SpecialistStatus.CANCELLED and checkpointing is not None:
                # Cancelled *inside* the node, after the pre-check passed. Same reasoning: a
                # returned value would mark it done, and it is not done.
                raise _StopWork(cancel_reason or "cancelled mid-node")
            # Encoded on the way into state, decoded on the way out — see `FanOutState`. The
            # checkpointer persists whatever this returns, so this *is* the checkpoint write.
            return {"outcomes": [outcome_to_json(outcome)]}

        def synthesis_node(state: FanOutState) -> dict[str, list[dict[str, Any]]]:
            """The second stage. Reads every specialist's output from accumulated state.

            **The barrier is free here.** LangGraph runs in supersteps, so this node does not start
            until every `Send` dispatched above has finished — no join primitive, no waiting code.
            The hand-rolled path gets the same guarantee from exiting the `ThreadPoolExecutor`
            context, which is also one line. Neither is harder; they are the same idea spelled
            differently.
            """
            outcomes = tuple(outcome_from_json(p, by_node[p["node_id"]]) for p in state["outcomes"])
            return {
                "synthesis": [
                    synthesis_to_json(synthesize(case, outcomes, criteria, gateway, run_id))
                ]
            }

        def join(_state: FanOutState) -> dict[str, list[dict[str, Any]]]:
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
            if ledger.breach() is not None or (cancel is not None and cancel.cancelled):
                return END
            if state["synthesis"]:
                # Restored from a checkpoint by a resumed run. Paying for it again would be the
                # exact failure this module was built to prevent.
                return END
            counted = [outcome_from_json(p, by_node[p["node_id"]]) for p in state["outcomes"]]
            return "synthesis" if should_synthesize(counted) else END

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

        # **`max_concurrency` is how the fan-out bound reaches this path, and its absence was a
        # real bug.** `MAX_PARALLEL` bounds the hand-rolled path by being the `ThreadPoolExecutor`'s
        # `max_workers`; a `Send` fan-out has no such argument, and without this LangGraph runs
        # every dispatch at once — measured at 8 of 8. Unbounded fan-out over paid model calls is
        # the failure budgets exist to prevent, and it is worse under Lambda, where a timed-out
        # invocation is retried automatically and pays for the whole width again.
        #
        # It is also what makes a wall-clock stop possible at all: if every criterion starts at
        # t=0, none of them ever sees a crossed ceiling, and the run has nothing to leave for the
        # next invocation.
        if checkpointing is None:
            compiled = graph.compile()
            final: dict[str, Any] = compiled.invoke(
                {"outcomes": [], "synthesis": []}, config={"max_concurrency": MAX_PARALLEL}
            )
            resumed: tuple[str, ...] = ()
        else:
            saver = _saver(checkpointing)
            config: RunnableConfig = {
                "configurable": {"thread_id": run_id},
                "max_concurrency": MAX_PARALLEL,
            }
            compiled = graph.compile(checkpointer=saver)

            existing = saver.get_tuple(config) is not None
            # **`get_state`, not the raw checkpoint row, and the difference is the crash case.**
            # A task that finished before its sibling died leaves a *pending write*, which is not
            # yet folded into any checkpoint's `channel_values`. Reading the row directly reports
            # nothing completed and the resume redoes everything — silently, and only after a
            # crash. `get_state` applies pending writes, which is what the resume itself will do.
            resumed = _completed_nodes(compiled.get_state(config).values) if existing else ()
            # `None` resumes; a payload starts. Passing the payload to a resume would re-merge it
            # through the reducers, which for `operator.add` appends an empty list — harmless
            # here, and the kind of harmless that stops being harmless when a channel changes.
            start: dict[str, Any] | None = None if existing else {"outcomes": [], "synthesis": []}
            try:
                # `DURABILITY` is the ORCH-01 clause; see the constant for why the default loses
                # writes a crashed process appears to have made.
                final = compiled.invoke(start, config=config, durability=DURABILITY)
            except _StopWork:
                # The graph stopped with work still pending, which is the point. Read back what
                # did complete; the pending criteria are the next invocation's job.
                final = dict(compiled.get_state(config).values)

        outcomes = [outcome_from_json(p, by_node[p["node_id"]]) for p in final.get("outcomes", ())]
        # Criteria that never produced an outcome were left pending by `_BudgetStop`. The
        # hand-rolled path returns these as values; here they are reconstructed so that both paths
        # report the same run — a truncated analysis must be visibly truncated on either.
        # Criteria that never produced an outcome were left pending by `_StopWork`. The
        # hand-rolled path returns these as values; here they are reconstructed through the same
        # shared helper, so a truncated run is visibly truncated the same way on either path.
        # Empty on the un-checkpointed path, where the node returned its own stopped outcome.
        analysed = {o.criterion.node_id for o in outcomes}
        breach, cancel_reason = stop_reason(ledger, cancel)
        outcomes.extend(
            unstarted(criteria, analysed, case.manifest.case_id, run_id, breach, cancel_reason)
        )
        outcomes.sort(key=lambda o: o.criterion.node_id)

        raw_synthesis = final.get("synthesis") or ()
        synthesis: SynthesisOutcome | None = (
            synthesis_from_json(raw_synthesis[0]) if raw_synthesis else None
        )
        return RunResult(
            run_id=run_id,
            candidate=self.name,
            findings=join_and_sort(outcomes, synthesis),
            outcomes=tuple(outcomes),
            wall_seconds=(datetime.now(UTC) - started).total_seconds(),
            criteria=criteria,
            synthesis=synthesis,
            consumption=ledger.consumption(),
            resumed_nodes=resumed,
            breach=breach,
        )


def _completed_nodes(values: Any) -> tuple[str, ...]:
    """Which nodes a resumed run will not re-execute, read off the stored state.

    **The measurement, and it has to be taken before `invoke`.** LangGraph skips completed tasks
    silently — that is the feature — so afterwards there is nothing to count. `resumed_nodes` on
    the hand-rolled path is counted by the code doing the skipping; here it has to be inferred from
    the state, which is a small, real difference in how observable the two are.
    """
    if not values:
        return ()
    recorded = values.get("outcomes") or []
    nodes = [str(p["node_id"]) for p in recorded if isinstance(p, dict) and "node_id" in p]
    if values.get("synthesis"):
        nodes.append(SYNTHESIS_NODE)
    return tuple(nodes)
