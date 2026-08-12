"""Bake-off candidate: a bounded, checkpointed state machine over PostgreSQL. No framework.

The honest baseline (ADR-012). If this lands small and resumes correctly, that is the finding —
and it carries no framework lifecycle risk, no mandatory vendor telemetry client, and no
external advisory surface to track.

The pattern is one idea repeated: **skip what is already committed, run what is not, commit
immediately.** Resume is not a special code path — `start` on an existing run *is* the resume
path, which is why leg 1 and leg 3 both use it. A separate resume path would be a second thing
to get right and a place for the two to diverge.

Deliberately absent: retries around anything but a model call, a scheduler, and a supervisor.
Blueprint §8.5's no-progress and duplicate-query detectors are also absent. Those are real
requirements for Milestone 2, and their absence here is part of the honest accounting — the
line count below is a floor, not a finished orchestrator.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from ireports_domain import ASAPEnvelope, ProposedFinding, RunManifest
from ireports_spike_harness import port, scenario
from ireports_spike_harness.bakeoff_v1_contracts import (
    BakeoffRunStatus as RunStatus,
)
from ireports_spike_harness.bakeoff_v1_contracts import (
    DispositionedFinding,
    HumanDisposition,
)
from ireports_spike_harness.bakeoff_v1_contracts import (
    bakeoff_is_legal_transition as is_legal_transition,
)
from ireports_spike_harness.gateway import ModelTimeoutError, StubModelGateway

from . import checkpoint

MAX_MODEL_ATTEMPTS = 2
"""Bounded retry per specialist (blueprint §8.5).

Two, not "until it works". An unbounded retry turns a persistent outage into an unbounded bill
and hides a real failure behind latency. When attempts are exhausted the node raises and the run
stops with its completed work intact — which is what leg 3 measures.
"""


class HandRolledOrchestrator:
    name = "hand-rolled"

    def __init__(self) -> None:
        checkpoint.init_schema()

    # -- helpers -----------------------------------------------------------

    def _advance(self, state: checkpoint.RunState, status: RunStatus) -> None:
        """Move the run's status, refusing illegal transitions.

        The run state machine is enforced here rather than trusted. `is_legal_transition` comes
        from the domain package, so every candidate is held to the same table — a framework
        cannot pass a leg by inventing a shortcut edge.
        """
        if state.status is not status and not is_legal_transition(state.status, status):
            raise RuntimeError(f"illegal transition {state.status.value} -> {status.value}")
        checkpoint.set_status(state, status)

    def _run_specialist(
        self, node_id: str, run_id: str, gateway: StubModelGateway
    ) -> list[ProposedFinding]:
        last: Exception | None = None
        for _ in range(MAX_MODEL_ATTEMPTS):
            try:
                return scenario.specialist(node_id, run_id, gateway)
            except ModelTimeoutError as exc:
                last = exc
        raise RuntimeError(f"{node_id} exhausted {MAX_MODEL_ATTEMPTS} attempts") from last

    # -- the graph ---------------------------------------------------------

    def start(self, run_id: str, crash_after: str | None = None) -> port.RunOutcome:
        state = checkpoint.load(run_id) or checkpoint.RunState(run_id=run_id)
        gateway = StubModelGateway(run_id)
        case = scenario.build_case()

        if not state.has("initialize"):
            manifest = scenario.initialize(case, run_id)
            checkpoint.commit_node(state, "initialize", json.loads(manifest.model_dump_json()))
            self._advance(state, RunStatus.ROUTING)
            if crash_after == "initialize":
                port.die_hard()

        if not state.has("route"):
            routing = scenario.route(case)
            checkpoint.commit_node(state, "route", json.loads(routing.model_dump_json()))
            self._advance(state, RunStatus.RETRIEVING)
            if crash_after == "route":
                port.die_hard()

        # -- bounded parallel fan-out (leg 4) ------------------------------
        if state.status is RunStatus.RETRIEVING:
            self._advance(state, RunStatus.ANALYZING)

        pending = [n for n in scenario.SPECIALIST_NODES if not state.has(n)]
        if pending:
            manifest = RunManifest.model_validate(state.result("initialize"))
            limit = manifest.budgets.max_parallel_specialists
            with ThreadPoolExecutor(max_workers=min(limit, len(pending))) as pool:
                futures = {
                    pool.submit(self._run_specialist, node, run_id, gateway): node
                    for node in pending
                }
                # `as_completed`, not submission order. Iterating `futures` directly walks the
                # dict in submission order and blocks on `future.result()`, so a specialist that
                # finished *second in the dict but first in wall-clock* stays uncommitted while
                # we wait on the one ahead of it. Crash in that window and its model call — paid
                # for, completed — is re-executed on resume.
                #
                # This is not hypothetical: it is what the 1c bake-off measured the hand-rolled
                # candidate doing, and it is why leg 1 now asserts on every specialist rather
                # than only the one named by `--crash-after`. Correctness survived it (the run
                # still produced three findings), which is precisely why it needed the durable
                # call log to surface.
                for future in as_completed(futures):
                    node = futures[future]
                    findings = future.result()
                    # Commit as each completes, not after all complete. This is the line that
                    # makes leg 1 pass: a crash here keeps whichever specialist finished.
                    checkpoint.commit_node(
                        state, node, [json.loads(f.model_dump_json()) for f in findings]
                    )
                    if crash_after == node:
                        port.die_hard()

        # -- join, de-duplicate, validate ----------------------------------
        if not state.has("join"):
            batches = [
                [ProposedFinding.model_validate(f) for f in state.result(node)]
                for node in scenario.SPECIALIST_NODES
            ]
            joined = scenario.join_and_dedupe(batches)
            checkpoint.commit_node(state, "join", [json.loads(f.model_dump_json()) for f in joined])
            self._advance(state, RunStatus.SYNTHESIZING)
            if crash_after == "join":
                port.die_hard()

        if not state.has("validate"):
            joined = [ProposedFinding.model_validate(f) for f in state.result("join")]
            validated = scenario.validate(joined)
            checkpoint.commit_node(
                state, "validate", [json.loads(f.model_dump_json()) for f in validated]
            )
            self._advance(state, RunStatus.VALIDATING)
            if crash_after == "validate":
                port.die_hard()

        # -- the human review gate (ADR-011) -------------------------------
        # The run stops. It does not poll, block, or auto-approve. The disposition arrives out
        # of band, in a later process, via `resume`.
        self._advance(state, RunStatus.AWAITING_HUMAN_REVIEW)
        reviewed = tuple(ProposedFinding.model_validate(f) for f in state.result("validate"))
        return port.RunOutcome(run_id=run_id, status=state.status, proposed_findings=reviewed)

    def resume(self, run_id: str, dispositions: tuple[HumanDisposition, ...]) -> port.RunOutcome:
        state = checkpoint.load(run_id)
        if state is None:
            raise RuntimeError(f"no checkpoint for run {run_id!r}; nothing to resume")
        if state.status is not RunStatus.AWAITING_HUMAN_REVIEW:
            raise RuntimeError(
                f"run {run_id!r} is {state.status.value!r}, not awaiting review; "
                "delivery requires a recorded disposition (ADR-011)"
            )

        proposals = {
            f.finding_id: f
            for f in (ProposedFinding.model_validate(f) for f in state.result("validate"))
        }
        if set(dispositions and [d.finding_id for d in dispositions]) != set(proposals):
            raise RuntimeError(
                "every proposed finding needs a disposition before the run may proceed"
            )

        bound = [
            DispositionedFinding(proposal=proposals[d.finding_id], disposition=d)
            for d in dispositions
        ]
        self._advance(state, RunStatus.REVIEW_RECORDED)

        self._advance(state, RunStatus.PACKAGING)
        envelope = scenario.package(scenario.build_case(), run_id, bound)
        checkpoint.commit_node(state, "package", json.loads(envelope.model_dump_json()))

        self._advance(state, RunStatus.DELIVERING)
        # Delivery is out of scope for the bake-off — the ASAP mock is Milestone 2. What is in
        # scope is that the run cannot arrive here without passing the gate above.
        self._advance(state, RunStatus.DELIVERED)

        return port.RunOutcome(
            run_id=run_id,
            status=state.status,
            proposed_findings=tuple(proposals.values()),
            envelope=ASAPEnvelope.model_validate(state.result("package")),
        )

    # -- measurement -------------------------------------------------------

    def checkpoint_bytes(self, run_id: str) -> int:
        state = checkpoint.load(run_id)
        return state.serialized_bytes() if state else 0


def utc_now() -> datetime:
    return datetime.now(UTC)
