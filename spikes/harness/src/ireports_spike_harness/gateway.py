"""The stub model gateway — and the bake-off's primary measuring instrument.

Two jobs, and the second is the important one.

**Job one: stand in for LiteLLM.** Deterministic responses keyed by node, so a candidate's
output does not vary between runs and test determinism is a property of the framework rather
than of the model. ADR-009 declines an offline profile for the *system*; it also says unit and
contract tests mock at the gateway boundary, which is exactly what this is. None of the four
spike legs needs a real model — leg 3 is a *simulated* timeout by definition.

**Job two: record what actually executed, durably.** Every model call is written to PostgreSQL
before the response is returned. That makes the call log survive the process being killed, which
is what lets the conformance suite answer the question the landscape scan could not:

    After a resume, did completed work re-execute?

This is the distinction between durable *execution* and restored *conversation* that §5.2 of
`docs/handoff/orchestration-landscape.md` flags as the highest-value measurement in the bake-off.
A framework that reloads state and then re-runs a finished node will show a second call here. No
framework can hide it, because the log is written by us, outside the framework, in a separate
transaction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

DEFAULT_DSN = os.environ.get(
    "IREPORTS_SPIKE_DSN",
    "postgresql://ireports:ireports_local_only@localhost:5436/ireports_spike",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS spike_model_calls (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT        NOT NULL,
    node_id     TEXT        NOT NULL,
    process_id  INTEGER     NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS spike_model_calls_run ON spike_model_calls (run_id);

-- Fault state must be durable too. A fault that resets when the process dies would make
-- leg 3 untestable: the resumed process would sail through the call that was supposed to
-- have already failed, and every candidate would appear to survive.
CREATE TABLE IF NOT EXISTS spike_faults (
    run_id    TEXT    NOT NULL,
    node_id   TEXT    NOT NULL,
    kind      TEXT    NOT NULL,
    fired     BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (run_id, node_id)
);
"""


class ModelTimeoutError(RuntimeError):
    """A simulated gateway timeout (ADR-012 spike leg 3).

    Deliberately *not* a subclass of anything a framework is likely to retry automatically.
    We want to observe each candidate's declared retry behaviour, not have it hidden inside a
    library's exception hierarchy.
    """


@dataclass(frozen=True)
class ModelCall:
    node_id: str
    process_id: int


def connect(dsn: str = DEFAULT_DSN) -> psycopg.Connection[Any]:
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=True)


def init_schema(dsn: str = DEFAULT_DSN) -> None:
    with connect(dsn) as conn:
        conn.execute(SCHEMA)


def reset(dsn: str = DEFAULT_DSN) -> None:
    """Clear all spike observation state. Called between conformance runs."""
    with connect(dsn) as conn:
        conn.execute("TRUNCATE spike_model_calls, spike_faults")


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_RESPONSES: dict[str, dict[str, Any]] = {
    "specialist_suitability": {
        "observations": [
            {
                "criterion_id": "731.202(b)(4)",
                "title": "Delinquent federal debt requires officer review",
                "observation": (
                    "The record indicates a federal tax balance that remained unpaid past its "
                    "due date and a payment plan entered after the conditional offer."
                ),
                "policy_relevance": (
                    "This may be relevant to financial responsibility under the cited factor."
                ),
                "supporting_evidence": ["ev_201"],
                "mitigating_evidence": ["ev_205"],
            },
            # Emitted twice on purpose. Leg 4's join must de-duplicate within an authority
            # without collapsing findings that differ only by authority — a real failure mode,
            # since a naive dedupe keyed on conduct alone would silently drop the SEAD-4 view.
            {
                "criterion_id": "731.202(b)(4)",
                "title": "Delinquent federal debt requires officer review",
                "observation": (
                    "The record indicates a federal tax balance that remained unpaid past its "
                    "due date and a payment plan entered after the conditional offer."
                ),
                "policy_relevance": (
                    "This may be relevant to financial responsibility under the cited factor."
                ),
                "supporting_evidence": ["ev_201"],
                "mitigating_evidence": ["ev_205"],
            },
        ]
    },
    "specialist_national_security": {
        "observations": [
            {
                "criterion_id": "GUIDELINE-F",
                "title": "Financial considerations require officer review",
                "observation": (
                    "The record indicates a federal tax balance that remained unpaid past its "
                    "due date."
                ),
                "policy_relevance": (
                    "This may be relevant to financial considerations under the cited guideline."
                ),
                "supporting_evidence": ["ev_201"],
                "mitigating_evidence": ["ev_205"],
            },
            {
                "criterion_id": "GUIDELINE-B",
                "title": "Continuing foreign family ties require officer review",
                "observation": (
                    "The record describes continuing contact with two relatives residing abroad."
                ),
                "policy_relevance": (
                    "This may be relevant to foreign influence under the cited guideline."
                ),
                "supporting_evidence": ["ev_101"],
                "mitigating_evidence": ["ev_122"],
            },
        ]
    },
}


class StubModelGateway:
    """Deterministic, observable, fault-injectable stand-in for the LiteLLM gateway."""

    def __init__(self, run_id: str, dsn: str = DEFAULT_DSN) -> None:
        self.run_id = run_id
        self.dsn = dsn

    # -- fault injection ---------------------------------------------------

    def arm_timeout(self, node_id: str) -> None:
        """Arm a one-shot timeout on the next call to `node_id`.

        One-shot, and the fired flag is persisted: the point of leg 3 is that the *retry or
        resume* succeeds. A fault that fired forever would measure nothing but our own patience.
        """
        with connect(self.dsn) as conn:
            conn.execute(
                "INSERT INTO spike_faults (run_id, node_id, kind) VALUES (%s, %s, 'timeout') "
                "ON CONFLICT (run_id, node_id) DO UPDATE SET fired = FALSE",
                (self.run_id, node_id),
            )

    def _maybe_fire(self, node_id: str) -> None:
        with connect(self.dsn) as conn:
            row = conn.execute(
                "UPDATE spike_faults SET fired = TRUE "
                "WHERE run_id = %s AND node_id = %s AND fired = FALSE "
                "RETURNING kind",
                (self.run_id, node_id),
            ).fetchone()
        if row is not None and row["kind"] == "timeout":
            raise ModelTimeoutError(f"simulated gateway timeout in {node_id!r}")

    # -- the call ----------------------------------------------------------

    def complete(self, node_id: str) -> dict[str, Any]:
        """Record the call, then honour any armed fault, then return the canned response.

        Order matters. The call is logged *before* the fault fires, because a node that
        attempted work and failed still consumed a model call — that is exactly what a budget
        manager has to count, and hiding it would flatter every candidate's budget enforcement.
        """
        with connect(self.dsn) as conn:
            conn.execute(
                "INSERT INTO spike_model_calls (run_id, node_id, process_id) VALUES (%s, %s, %s)",
                (self.run_id, node_id, os.getpid()),
            )
        self._maybe_fire(node_id)
        if node_id not in _RESPONSES:
            raise KeyError(f"no canned response for node {node_id!r}")
        return _RESPONSES[node_id]

    # -- observation -------------------------------------------------------

    def calls(self) -> list[ModelCall]:
        with connect(self.dsn) as conn:
            rows = conn.execute(
                "SELECT node_id, process_id FROM spike_model_calls WHERE run_id = %s ORDER BY id",
                (self.run_id,),
            ).fetchall()
        return [ModelCall(node_id=r["node_id"], process_id=r["process_id"]) for r in rows]

    def call_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for call in self.calls():
            counts[call.node_id] = counts.get(call.node_id, 0) + 1
        return counts

    def distinct_processes(self) -> set[int]:
        """Proves a resume genuinely happened in a different process, rather than in-memory."""
        return {c.process_id for c in self.calls()}
