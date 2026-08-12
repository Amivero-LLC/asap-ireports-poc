"""The checkpoint store: one table, one row per run.

The whole persistence layer for the hand-rolled candidate. It is deliberately boring, and its
size is a measurement — ADR-012 asks whether a bounded, checkpointed state machine over
PostgreSQL is a few hundred lines, and this file is part of the answer.

Two properties are load-bearing.

**Per-node commit.** A node's result is committed the moment it completes, not batched at the
end of a stage. That is what lets a crash mid-fan-out keep the specialist that finished. Batching
would be fewer writes and would fail leg 1.

**The checkpoint is data, not pickled objects.** State is JSON built from Pydantic contracts and
re-validated on load. `docs/handoff/orchestration-landscape.md` §5.1 records four deserialization
RCEs on LangGraph's checkpoint path in nine months; the lesson is not that a framework was
careless but that a checkpoint blob is a deserialization trust boundary in *any* design. Storing
JSON and re-validating through the contracts means a tampered row fails validation rather than
executing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ireports_spike_harness.bakeoff_v1_contracts import BakeoffRunStatus as RunStatus
from ireports_spike_harness.gateway import DEFAULT_DSN, connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS handrolled_checkpoints (
    run_id      TEXT PRIMARY KEY,
    status      TEXT        NOT NULL,
    completed   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass
class RunState:
    """Identifiers and typed node results — never a transcript.

    Blueprint §8.2: large evidence text stays in the evidence store and is referenced by id.
    Keeping the checkpoint small is why `serialized_state_bytes` is a scored dimension, and it
    is also the cheapest mitigation for the trust-boundary problem above: the less that
    round-trips, the less there is to tamper with.
    """

    run_id: str
    status: RunStatus = RunStatus.INITIALIZING
    completed: dict[str, Any] = field(default_factory=dict)

    def has(self, node_id: str) -> bool:
        return node_id in self.completed

    def result(self, node_id: str) -> Any:
        return self.completed[node_id]

    def serialized_bytes(self) -> int:
        return len(json.dumps(self.completed).encode())


def init_schema(dsn: str = DEFAULT_DSN) -> None:
    with connect(dsn) as conn:
        conn.execute(SCHEMA)


def load(run_id: str, dsn: str = DEFAULT_DSN) -> RunState | None:
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT status, completed FROM handrolled_checkpoints WHERE run_id = %s",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return RunState(run_id=run_id, status=RunStatus(row["status"]), completed=row["completed"])


def commit_node(state: RunState, node_id: str, result: Any, dsn: str = DEFAULT_DSN) -> None:
    """Persist one node's result atomically.

    `jsonb_set`-free deliberately: the whole `completed` map is written under a single
    `INSERT ... ON CONFLICT`, so a concurrent fan-out writer cannot interleave a partial update.
    With only two specialists the contention is trivial, but the pattern is the one that scales.
    """
    state.completed[node_id] = result
    _write(state, dsn)


def set_status(state: RunState, status: RunStatus, dsn: str = DEFAULT_DSN) -> None:
    state.status = status
    _write(state, dsn)


def _write(state: RunState, dsn: str) -> None:
    with connect(dsn) as conn:
        conn.execute(
            """
            INSERT INTO handrolled_checkpoints (run_id, status, completed, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (run_id) DO UPDATE
                SET status = EXCLUDED.status,
                    completed = EXCLUDED.completed,
                    updated_at = now()
            """,
            (state.run_id, state.status.value, json.dumps(state.completed)),
        )
