"""Bake-off candidate: the same scenario wired as a LangGraph `StateGraph`.

ADR-012 calls LangGraph "the blueprint's recommendation and the incumbent to beat", and the 1b
landscape scan (§5.1) confirmed the three properties that put it there: a first-party
MIT-licensed PostgreSQL checkpointer, interrupt-based human-in-the-loop against a persistent
thread id, and a written semver stability commitment. This file exists to hold those claims to the
same four legs the other two candidates passed.

**How the framework is used.** A real `StateGraph` compiled with `PostgresSaver`. LangGraph owns
node scheduling, the parallel super-step, the reducer that joins the fan-out, checkpoint writing,
what re-executes after a crash, retry on a failed node, and the interrupt. What we supply is a
state schema, eight one-line node wrappers around the shared scenario functions, and the edges.
Nothing here re-implements scheduling or resume; a candidate that did would be the hand-rolled
baseline wearing a framework's name.

**Where the review gate lives.** ADR-011 makes human review a state transition with no bypass, so
it is modelled with LangGraph's own `interrupt()`: the `review` node suspends, the process exits,
and the disposition arrives in a later process as `Command(resume=...)` from outside. `resume`
refuses to deliver a run that is not parked at the gate, so the ADR-011 guard is ours even though
the suspension mechanism is the framework's.

**What is deliberately absent**, and must be read alongside the line count: the domain run-status
machine (`is_legal_transition`) is not enforced here, exactly as it is not in the Strands
candidate — both frameworks own run status, and mirroring the hand-rolled candidate's enforcement
would add lines that measure our diligence rather than the framework's. Blueprint §8.5's
no-progress and duplicate-query detectors, tool allowlists, cancellation, and OTel spans are
absent in all three.
"""

from __future__ import annotations

import json
import operator
import os
from typing import Annotated, Any, TypedDict

from ireports_domain import ASAPEnvelope, ProposedFinding
from ireports_spike_harness import port, scenario
from ireports_spike_harness.bakeoff_v1_contracts import BakeoffRunStatus as RunStatus
from ireports_spike_harness.bakeoff_v1_contracts import DispositionedFinding, HumanDisposition
from ireports_spike_harness.gateway import DEFAULT_DSN, ModelTimeoutError, StubModelGateway, connect
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, interrupt

from .checkpointer import COMPLETED_CHANNEL, CrashingPostgresSaver, state_bytes

DURABILITY = os.environ.get("IREPORTS_SPIKE_LANGGRAPH_DURABILITY", "sync")
"""LangGraph 1.x persistence mode. **We choose `sync`; the library's default is `async`.**

`langgraph/pregel/main.py` documents three modes and defaults to `async` `[first-party]`:

| Mode | What it does |
|---|---|
| `sync` | Waits for the checkpoint write before the next super-step starts |
| `async` | Writes the checkpoint in the background while the next super-step runs |
| `exit` | Writes only when the graph exits — `put_writes` is skipped entirely |

**What the bake-off measured, stated at the confidence it earned.** All four legs pass under both
`sync` and `async`. Under `exit` leg 1 cannot be measured at all: the crash hook lives in
`put_writes`, which `exit` mode never calls (`_loop.py`: `if self.durability != "exit" ...`) — and
that absence *is* the finding, since nothing is durable mid-run in that mode. Crashing after a
sequential node's durable write redid no model calls in 24 of 24 trials under `sync`; under
`async` it redid work in 2 of 6 trials in one early round and in 0 of 30 afterwards, which is
consistent with a real race that our harness does not reliably reproduce, not with a clean result.

So the choice of `sync` is **not** justified by a measured failure of `async`. It is justified by
the source: `async` does not await the checkpoint future, so the window exists whether or not we
can provoke it, and closing it costs one keyword on a run whose latency budget is minutes
(ADR-013). Overridable by environment so the measurement is repeatable.
"""

SPECIALIST_RETRY = RetryPolicy(
    max_attempts=2,
    initial_interval=0.05,
    retry_on=(ModelTimeoutError,),
)
"""Bounded retry per specialist (blueprint §8.5), declared rather than written.

Two attempts, matching the hand-rolled candidate's `MAX_MODEL_ATTEMPTS`, so leg 3 measures the
same policy in both. `retry_on` is explicit: LangGraph's `default_retry_on` decides by exception
type, and a bounded-agentic system must not have its retry surface widen because a library changed
its default. The interval is short only because the fault here is simulated.
"""


class SpikeState(TypedDict, total=False):
    """The graph's state, carrying JSON rather than model instances.

    Contract objects are dumped on the way in and re-validated on the way out. That costs a
    serialize/parse at each boundary, and it is the deliberate choice: the checkpoint blob is a
    deserialization trust boundary (`docs/handoff/checkpoint-threat-model.md`), and LangGraph's
    `JsonPlusSerializer` will happily round-trip richer objects. Storing plain JSON and
    re-validating through the domain contracts keeps a tampered row a validation failure rather
    than an execution.

    The channel set mirrors what the hand-rolled candidate stores, so the byte comparison is
    like-for-like: a manifest, a routing result, each specialist's raw output, the joined set, and
    the validated set — the same three copies of each finding.
    """

    run_id: str
    manifest: dict[str, Any]
    routing: dict[str, Any]
    batches: Annotated[list[list[dict[str, Any]]], operator.add]
    joined: list[dict[str, Any]]
    validated: list[dict[str, Any]]
    dispositions: list[dict[str, Any]]
    envelope: dict[str, Any]
    completed: Annotated[list[str], operator.add]


class LangGraphOrchestrator:
    name = "langgraph"

    # -- graph construction ------------------------------------------------

    def _build(self, run_id: str, crash_after: str | None = None) -> Any:
        gateway = StubModelGateway(run_id)
        case = scenario.build_case()

        def initialize(state: SpikeState) -> dict[str, Any]:
            manifest = scenario.initialize(case, run_id)
            return {
                "manifest": json.loads(manifest.model_dump_json()),
                COMPLETED_CHANNEL: ["initialize"],
            }

        def route(state: SpikeState) -> dict[str, Any]:
            return {
                "routing": json.loads(scenario.route(case).model_dump_json()),
                COMPLETED_CHANNEL: ["route"],
            }

        def specialist(node_id: str) -> Any:
            def run(state: SpikeState) -> dict[str, Any]:
                findings = scenario.specialist(node_id, run_id, gateway)
                return {
                    "batches": [[json.loads(f.model_dump_json()) for f in findings]],
                    COMPLETED_CHANNEL: [node_id],
                }

            return run

        def join(state: SpikeState) -> dict[str, Any]:
            batches = [
                [ProposedFinding.model_validate(f) for f in batch]
                for batch in state.get("batches", [])
            ]
            joined = scenario.join_and_dedupe(batches)
            return {
                "joined": [json.loads(f.model_dump_json()) for f in joined],
                COMPLETED_CHANNEL: ["join"],
            }

        def validate(state: SpikeState) -> dict[str, Any]:
            joined = [ProposedFinding.model_validate(f) for f in state.get("joined", [])]
            return {
                "validated": [json.loads(f.model_dump_json()) for f in scenario.validate(joined)],
                COMPLETED_CHANNEL: ["validate"],
            }

        def review(state: SpikeState) -> dict[str, Any]:
            """The ADR-011 gate, as a LangGraph interrupt.

            `interrupt()` raises out of the node and out of `invoke`; the run does not poll,
            block, or auto-approve. The disposition arrives in a later process as
            `Command(resume=...)`, which is what makes "recorded out of band" literally true.
            """
            dispositions = interrupt(
                {"reason": "an authorized officer must disposition every proposed finding"}
            )
            return {"dispositions": dispositions, COMPLETED_CHANNEL: ["review"]}

        def package(state: SpikeState) -> dict[str, Any]:
            proposals = {
                f.finding_id: f
                for f in (ProposedFinding.model_validate(f) for f in state.get("validated", []))
            }
            dispositions = [
                HumanDisposition.model_validate(d) for d in state.get("dispositions", [])
            ]
            if {d.finding_id for d in dispositions} != set(proposals):
                raise RuntimeError(
                    "every proposed finding needs a disposition before the run may proceed"
                )
            bound = [
                DispositionedFinding(proposal=proposals[d.finding_id], disposition=d)
                for d in dispositions
            ]
            envelope = scenario.package(case, run_id, bound)
            return {
                "envelope": json.loads(envelope.model_dump_json()),
                COMPLETED_CHANNEL: ["package"],
            }

        builder = StateGraph(SpikeState)
        builder.add_node("initialize", initialize)
        builder.add_node("route", route)
        for node_id in scenario.SPECIALIST_NODES:
            builder.add_node(node_id, specialist(node_id), retry_policy=SPECIALIST_RETRY)
        builder.add_node("join", join)
        builder.add_node("validate", validate)
        builder.add_node("review", review)
        builder.add_node("package", package)

        builder.add_edge(START, "initialize")
        builder.add_edge("initialize", "route")
        for node_id in scenario.SPECIALIST_NODES:
            # The bounded parallel fan-out (leg 4). Two edges out of `route` put both specialists
            # in one super-step; two edges into `join` make LangGraph wait for both. The
            # concurrency, the barrier, and the `operator.add` reducer that merges their output
            # are the framework's, not ours.
            builder.add_edge("route", node_id)
            builder.add_edge(node_id, "join")
        builder.add_edge("join", "validate")
        builder.add_edge("validate", "review")
        builder.add_edge("review", "package")
        builder.add_edge("package", END)

        saver = CrashingPostgresSaver(connect(DEFAULT_DSN), crash_after=crash_after)
        saver.setup()
        return builder.compile(checkpointer=saver)

    @staticmethod
    def _config(run_id: str) -> dict[str, Any]:
        # `PostgresSaver` stores `thread_id` in a length-limited column (1b scan §5.1: keep it
        # under 255 characters). Run ids are short here; a production id scheme must check.
        return {"configurable": {"thread_id": run_id}}

    # -- the port ----------------------------------------------------------

    def start(self, run_id: str, crash_after: str | None = None) -> port.RunOutcome:
        """Run to the review gate. On an existing run this *is* the resume path.

        Deliberately one entry point for a fresh run and a crashed one, matching both other
        candidates: `invoke(None, config)` tells LangGraph to continue from whatever it has, and
        LangGraph decides what to re-execute. That decision is the thing leg 1 measures, so it
        must not be pre-empted by us tracking our own "what is done" set.
        """
        graph = self._build(run_id, crash_after)
        config = self._config(run_id)

        started = graph.get_state(config).created_at is not None
        graph.invoke(
            None if started else {"run_id": run_id},
            config,
            durability=DURABILITY,
        )

        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.AWAITING_HUMAN_REVIEW,
            proposed_findings=self._proposals(graph, config),
        )

    def resume(self, run_id: str, dispositions: tuple[HumanDisposition, ...]) -> port.RunOutcome:
        graph = self._build(run_id)
        config = self._config(run_id)

        if not graph.get_state(config).interrupts:
            raise RuntimeError(
                f"run {run_id!r} is not parked at the review gate; "
                "delivery requires a recorded disposition (ADR-011)"
            )

        payload = [json.loads(d.model_dump_json()) for d in dispositions]
        values = graph.invoke(Command(resume=payload), config, durability=DURABILITY)

        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.DELIVERED,
            proposed_findings=self._proposals(graph, config),
            envelope=ASAPEnvelope.model_validate(values["envelope"]),
        )

    # -- reading results ---------------------------------------------------

    def _proposals(self, graph: Any, config: dict[str, Any]) -> tuple[ProposedFinding, ...]:
        validated = graph.get_state(config).values.get("validated", [])
        return tuple(ProposedFinding.model_validate(f) for f in validated)

    # -- measurement -------------------------------------------------------

    def checkpoint_bytes(self, run_id: str) -> int:
        return state_bytes(run_id)["latest_checkpoint"]
