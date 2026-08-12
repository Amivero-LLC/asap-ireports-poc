"""Bake-off candidate: the same scenario wired as a Strands `Graph`.

ADR-012 lists Strands for AWS alignment and documented Lambda packaging. The 1b landscape scan
confirmed both, found a real interrupt primitive, and flagged one thing it could not settle by
reading — a third-party claim that Strands persists *conversation state* rather than *execution
state*, so that a crashed run restores its history and then re-runs the work. That claim is the
single highest-value unknown in the milestone, and this file exists to settle it by measurement.

**How the framework is used.** The graph is a real `strands.multiagent.Graph`: Strands owns node
scheduling, the parallel batch, the interrupt, and — through `RepositorySessionManager` — when
state is written. What we supply is the `SessionRepository` over PostgreSQL that Strands does not
ship (`session_repository.py`), and the encode/decode of typed contracts into the only container
Strands persists (`nodes.py`). Nothing here re-implements scheduling or resume; a candidate that
did would be the hand-rolled baseline wearing a framework's name.

**Where the review gate lives.** ADR-011 makes human review a state transition with no bypass, so
it is modelled with Strands' own `Interrupt` rather than by stopping the graph ourselves: the
`review` node returns `INTERRUPTED` when it has no disposition, and the disposition arrives on
resume as an `interruptResponse` from outside the process.

**What is deliberately absent**, and must be read alongside the line count: the domain run-status
machine (`is_legal_transition`) is not enforced here the way the hand-rolled candidate enforces it,
because Strands owns status. Blueprint §8.5's no-progress and duplicate-query detectors, tool
allowlists, cancellation, and OTel spans are absent in both candidates.
"""

from __future__ import annotations

import json
from typing import Any

from ireports_domain import ASAPEnvelope, ProposedFinding
from ireports_spike_harness import port, scenario
from ireports_spike_harness.bakeoff_v1_contracts import BakeoffRunStatus as RunStatus
from ireports_spike_harness.bakeoff_v1_contracts import DispositionedFinding, HumanDisposition
from ireports_spike_harness.gateway import StubModelGateway
from strands.interrupt import Interrupt
from strands.multiagent import GraphBuilder
from strands.multiagent.base import MultiAgentResult, Status
from strands.session.repository_session_manager import RepositorySessionManager

from .nodes import ScenarioNode, decode, encode
from .session_repository import PostgresSessionRepository

GRAPH_ID = "ireports_spike_graph"
REVIEW_INTERRUPT_ID = "human-review-gate"


class StrandsOrchestrator:
    name = "strands"

    # -- graph construction ------------------------------------------------

    def _build(self, run_id: str, crash_after: str | None = None) -> Any:
        gateway = StubModelGateway(run_id)
        case = scenario.build_case()
        self._repo = PostgresSessionRepository(crash_after=crash_after)

        def results(node_id: str) -> Any:
            """Read an upstream node's payload out of the graph's own (restored) state."""
            return decode(self._graph.state.results[node_id])

        def initialize(_: dict[str, Any]) -> MultiAgentResult:
            return encode(json.loads(scenario.initialize(case, run_id).model_dump_json()))

        def route(_: dict[str, Any]) -> MultiAgentResult:
            return encode(json.loads(scenario.route(case).model_dump_json()))

        def specialist(node_id: str) -> Any:
            def run(_: dict[str, Any]) -> MultiAgentResult:
                findings = scenario.specialist(node_id, run_id, gateway)
                return encode([json.loads(f.model_dump_json()) for f in findings])

            return run

        def join(_: dict[str, Any]) -> MultiAgentResult:
            batches = [
                [ProposedFinding.model_validate(f) for f in results(node)]
                for node in scenario.SPECIALIST_NODES
            ]
            joined = scenario.join_and_dedupe(batches)
            return encode([json.loads(f.model_dump_json()) for f in joined])

        def validate(_: dict[str, Any]) -> MultiAgentResult:
            joined = [ProposedFinding.model_validate(f) for f in results("join")]
            return encode([json.loads(f.model_dump_json()) for f in scenario.validate(joined)])

        def review(invocation_state: dict[str, Any]) -> MultiAgentResult:
            """The ADR-011 gate, as a Strands interrupt.

            No disposition means the run stops here — it does not poll, block, or auto-approve.
            The disposition arrives in a later process as an `interruptResponse`, which is what
            makes "recorded out of band" literally true rather than a convention.
            """
            dispositions = invocation_state.get("dispositions")
            if not dispositions:
                return MultiAgentResult(
                    status=Status.INTERRUPTED,
                    interrupts=[
                        Interrupt(
                            id=REVIEW_INTERRUPT_ID,
                            name="human_review",
                            reason="an authorized officer must disposition every proposed finding",
                        )
                    ],
                )
            return encode(dispositions)

        def package(_: dict[str, Any]) -> MultiAgentResult:
            proposals = {
                f.finding_id: f
                for f in (ProposedFinding.model_validate(f) for f in results("validate"))
            }
            dispositions = [HumanDisposition.model_validate(d) for d in results("review")]
            if {d.finding_id for d in dispositions} != set(proposals):
                raise RuntimeError(
                    "every proposed finding needs a disposition before the run may proceed"
                )
            bound = [
                DispositionedFinding(proposal=proposals[d.finding_id], disposition=d)
                for d in dispositions
            ]
            envelope = scenario.package(case, run_id, bound)
            return encode(json.loads(envelope.model_dump_json()))

        builder = GraphBuilder()
        builder.set_graph_id(GRAPH_ID)
        builder.set_session_manager(
            RepositorySessionManager(session_id=run_id, session_repository=self._repo)
        )

        nodes = {
            "initialize": ScenarioNode("initialize", initialize),
            "route": ScenarioNode("route", route),
            "join": ScenarioNode("join", join),
            "validate": ScenarioNode("validate", validate),
            "review": ScenarioNode("review", review),
            "package": ScenarioNode("package", package),
        }
        for node_id in scenario.SPECIALIST_NODES:
            nodes[node_id] = ScenarioNode(node_id, specialist(node_id))

        for node_id, executor in nodes.items():
            builder.add_node(executor, node_id)

        builder.set_entry_point("initialize")
        builder.add_edge("initialize", "route")
        for node_id in scenario.SPECIALIST_NODES:
            # The bounded parallel fan-out (leg 4). Strands schedules the batch; we only declare
            # that both depend on `route` and that `join` depends on both.
            builder.add_edge("route", node_id)
            builder.add_edge(node_id, "join")
        builder.add_edge("join", "validate")
        builder.add_edge("validate", "review")
        builder.add_edge("review", "package")

        self._graph = builder.build()
        return self._graph

    # -- the port ----------------------------------------------------------

    def _persisted_status(self, run_id: str) -> str | None:
        payload = PostgresSessionRepository().read_multi_agent(run_id, GRAPH_ID)
        return None if payload is None else str(payload.get("status"))

    def start(self, run_id: str, crash_after: str | None = None) -> port.RunOutcome:
        """Run to the review gate. On an existing run this *is* the resume path.

        Deliberately the same entry point for a fresh run and a crashed one, matching the
        hand-rolled candidate: a separate resume path would be a second thing to get right and a
        place for the two to diverge. Strands decides what to re-execute, which is the point.
        """
        if self._persisted_status(run_id) == Status.INTERRUPTED.value:
            # Already parked at the gate. Re-invoking would hand a plain task to a graph whose
            # interrupt state is active, which Strands correctly rejects — it wants interrupt
            # responses. Report the gate instead.
            graph = self._build(run_id, crash_after)
            return port.RunOutcome(
                run_id=run_id,
                status=RunStatus.AWAITING_HUMAN_REVIEW,
                proposed_findings=self._proposals(graph),
            )

        graph = self._build(run_id, crash_after)
        graph("analyse the case", invocation_state={})
        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.AWAITING_HUMAN_REVIEW,
            proposed_findings=self._proposals(graph),
        )

    def resume(self, run_id: str, dispositions: tuple[HumanDisposition, ...]) -> port.RunOutcome:
        if self._persisted_status(run_id) != Status.INTERRUPTED.value:
            raise RuntimeError(
                f"run {run_id!r} is not parked at the review gate; "
                "delivery requires a recorded disposition (ADR-011)"
            )

        graph = self._build(run_id)
        payload = [json.loads(d.model_dump_json()) for d in dispositions]
        graph(
            [{"interruptResponse": {"interruptId": REVIEW_INTERRUPT_ID, "response": payload}}],
            invocation_state={"dispositions": payload},
        )

        envelope = ASAPEnvelope.model_validate(decode(graph.state.results["package"]))
        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.DELIVERED,
            proposed_findings=self._proposals(graph),
            envelope=envelope,
        )

    # -- reading results ---------------------------------------------------

    def _proposals(self, graph: Any) -> tuple[ProposedFinding, ...]:
        result = graph.state.results.get("validate")
        if result is None:
            return ()
        return tuple(ProposedFinding.model_validate(f) for f in decode(result))

    # -- measurement -------------------------------------------------------

    def checkpoint_bytes(self, run_id: str) -> int:
        return PostgresSessionRepository().serialized_bytes(run_id, GRAPH_ID)
