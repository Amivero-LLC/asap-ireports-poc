"""A deliberately broken candidate, kept permanently as the harness's negative control.

The bake-off's central claim is that leg 1 can tell durable *execution resume* from mere
*conversation restore*. That claim is worth exactly as much as our confidence that the leg would
fail a candidate which gets it wrong — a test that has never failed is not evidence.

So this module implements the wrong thing on purpose. It persists state, reloads it after a
crash, reports the correct final status, and produces the correct findings. Everything a casual
inspection would check, it passes. The one thing it does not do is skip completed work: on
resume it re-runs every node from the start.

`test_negative_control` asserts that leg 1 fails it and that legs 2 and 4 still pass. That
combination is the important part — it shows leg 1 is detecting re-execution specifically,
rather than the candidate being broken in some way that would trip any assertion.

This is also, per `docs/handoff/orchestration-landscape.md` §5.2, the precise behaviour a third
party alleges of one of the real candidates. If that turns out to be true, this is what it will
look like in the report.
"""

from __future__ import annotations

import json
import sys

from ireports_domain import (
    ASAPEnvelope,
    DispositionedFinding,
    HumanDisposition,
    ProposedFinding,
    RunStatus,
)

from ireports_spike_harness import port, scenario
from ireports_spike_harness.gateway import DEFAULT_DSN, StubModelGateway, connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS negative_control_state (
    run_id   TEXT PRIMARY KEY,
    status   TEXT  NOT NULL,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb
);
"""


class NegativeControlOrchestrator:
    """Restores state, then re-executes everything anyway."""

    name = "negative-control"

    def __init__(self) -> None:
        with connect(DEFAULT_DSN) as conn:
            conn.execute(SCHEMA)

    def _save(self, run_id: str, status: RunStatus, findings: list[ProposedFinding]) -> None:
        with connect(DEFAULT_DSN) as conn:
            conn.execute(
                "INSERT INTO negative_control_state (run_id, status, findings) "
                "VALUES (%s, %s, %s) ON CONFLICT (run_id) DO UPDATE "
                "SET status = EXCLUDED.status, findings = EXCLUDED.findings",
                (
                    run_id,
                    status.value,
                    json.dumps([json.loads(f.model_dump_json()) for f in findings]),
                ),
            )

    def _load(self, run_id: str) -> list[ProposedFinding]:
        with connect(DEFAULT_DSN) as conn:
            row = conn.execute(
                "SELECT findings FROM negative_control_state WHERE run_id = %s", (run_id,)
            ).fetchone()
        if row is None:
            return []
        return [ProposedFinding.model_validate(f) for f in row["findings"]]

    def start(self, run_id: str, crash_after: str | None = None) -> port.RunOutcome:
        gateway = StubModelGateway(run_id)

        # State *is* reloaded — and then ignored for the purpose of deciding what to run.
        # This is the bug, and it is a single-line-looking one: the loaded findings are used
        # as a starting accumulator rather than as a record of what is already done.
        self._load(run_id)

        batches = []
        for node in scenario.SPECIALIST_NODES:
            batches.append(scenario.specialist(node, run_id, gateway))
            if crash_after == node:
                self._save(run_id, RunStatus.ANALYZING, [f for b in batches for f in b])
                port.die_hard()

        findings = scenario.validate(scenario.join_and_dedupe(batches))
        self._save(run_id, RunStatus.AWAITING_HUMAN_REVIEW, findings)
        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.AWAITING_HUMAN_REVIEW,
            proposed_findings=tuple(findings),
        )

    def resume(self, run_id: str, dispositions: tuple[HumanDisposition, ...]) -> port.RunOutcome:
        proposals = {f.finding_id: f for f in self._load(run_id)}
        bound = [
            DispositionedFinding(proposal=proposals[d.finding_id], disposition=d)
            for d in dispositions
        ]
        envelope = scenario.package(scenario.build_case(), run_id, bound)
        self._save(run_id, RunStatus.DELIVERED, list(proposals.values()))
        return port.RunOutcome(
            run_id=run_id,
            status=RunStatus.DELIVERED,
            proposed_findings=tuple(proposals.values()),
            envelope=ASAPEnvelope.model_validate(json.loads(envelope.model_dump_json())),
        )


if __name__ == "__main__":
    sys.exit(port.main(NegativeControlOrchestrator()))
