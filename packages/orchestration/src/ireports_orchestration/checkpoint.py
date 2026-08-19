"""Checkpoint completed nodes, so a resume skips work instead of repeating it (ORCH-01/ORCH-02).

**This buys back wall clock, not money, and that is a recent correction.** `idempotency.py` landed
at the *gateway*, so a resumed run already re-pays for nothing — 0 duplicate paid calls, both
paths, every crash point. What a resumed run still spends is *time*: it re-executes every completed
node to reach the one that did not finish. Under Lambda's 15-minute ceiling that is the resource in
short supply, and re-running four completed specialists to reach the fifth may simply not fit. So
this module exists for LAMB-01, and it is the half of durable orchestration that is genuinely the
orchestrator's business rather than the gateway's.

**This was the point where the two orchestration paths stopped being interchangeable**, and the
comparison it produced is recorded in `docs/handoff/orchestration-decision.md` — chiefly that a
first-party checkpointer saves you the *store* and not the *codec*, and the codec is most of what
is below. The LangGraph adapter that made the comparison possible was removed by ADR-029.

**What is stored, and what is deliberately not.** One row per *completed* node, holding the node's
result as JSON re-validated through the ordinary contracts on the way back in. Never a pickle:
`docs/handoff/orchestration-landscape.md` records four deserialization RCEs on one framework's
checkpoint path in nine months, and the lesson is not that a framework was careless but that a
checkpoint blob is a deserialization trust boundary in *any* design.

The `Criterion` is **not** stored. It is re-derived from the case on resume and handed back in, so
a checkpoint cannot smuggle in a criterion the case never selected — and the stored
`criterion_id` is checked against the live one before anything is restored. That is both the
cheaper row and the safer one.

**Row integrity is not addressed here and is the largest known gap.** A tampered row that still
parses into a valid `SpecialistResult` would be restored as though the model had produced it.
Named rather than glossed: `docs/handoff/checkpoint-threat-model.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from ireports_domain import ProposedFinding, SpecialistResult

from .criteria import Criterion
from .specialist import SpecialistOutcome, SpecialistStatus
from .synthesis import Overlap, SynthesisOutcome

CHECKPOINT_VERSION = "1"
"""Bumped when the stored shape changes, so an old row cannot be restored into new code.

Same reasoning as `idempotency.REPLAY_VERSION`, and the same limit: this does not make restore
safe, it makes a *stale* row fail loudly instead of deserializing into something the current code
will misread."""

SYNTHESIS_NODE = "synthesis"
"""The second stage's node id in the checkpoint. A reserved name rather than a criterion's, because
synthesis is not a criterion and giving it one would make it selectable by `criteria_for`."""

RESUMABLE_STATUSES = frozenset({SpecialistStatus.COMPLETED, SpecialistStatus.REFUSED})
"""Which outcomes are worth writing down, and the distinction is load-bearing for LAMB-01.

`COMPLETED` and `REFUSED` are *work that happened* — the call was made and paid for, and ADR-015
says a refusal must not be re-asked. `SKIPPED_BUDGET` is the exact opposite: nobody attempted that
criterion, and it is the work the *next* invocation exists to do. Checkpointing it would make the
first invocation's budget stop permanent, which turns "resume and finish" into "resume and confirm
we never did it."

`FAILED` is left out too, and less obviously. A transport fault or a timeout may not recur, the
gateway's call store means a re-attempt costs nothing if the call actually completed, and recording
a failure as a checkpoint would freeze a transient fault into the run forever.

`CANCELLED` is out for the same reason as `SKIPPED_BUDGET`: a criterion the run was told to stop
before analysing is work still to do, and a resume that treated it as done would deliver a
deliberately truncated case as a complete one.
"""


def _check_version(payload: dict[str, Any], node_id: str) -> None:
    stored = payload.get("v")
    if stored != CHECKPOINT_VERSION:
        raise ValueError(
            f"checkpoint for node {node_id!r} was written by format version {stored!r} and this "
            f"code reads {CHECKPOINT_VERSION!r}. Refusing to restore it: a row read by the wrong "
            "reader is worse than a re-executed node, because the re-execution is only slow."
        )


# ---------------------------------------------------------------------------
# The codec — plain JSON in both directions, and shared by both paths
# ---------------------------------------------------------------------------
#
# **JSON in both directions, re-validated through the ordinary contracts on the way back.**
# A checkpoint blob that deserializes into live objects is a code-execution surface, so nothing here
# round-trips an object — it round-trips data and re-enters the contract through its constructor.
#
# This codec is also the single largest thing the framework comparison produced. A first-party
# checkpointer appears to save you writing one, and under the strict deserialization that any
# CUI-carrying system should require, it does not: the framework silently degraded our types to
# `dict` on the resume path only. See `docs/handoff/orchestration-decision.md` §3.


def outcome_to_json(outcome: SpecialistOutcome) -> dict[str, Any]:
    """One specialist's result, as data.

    `SpecialistResult` is a Pydantic contract, so `model_dump(mode="json")` is the whole of it.
    The rest are the operational fields ADR-021 §2 keeps off that contract, which the *run* needs
    and a consumer of findings does not.
    """
    return {
        "v": CHECKPOINT_VERSION,
        "node_id": outcome.criterion.node_id,
        "criterion_id": outcome.criterion.criterion_id,
        "result": outcome.result.model_dump(mode="json"),
        "rejected": list(outcome.rejected),
        "resolved_model": outcome.resolved_model,
        "input_tokens": outcome.input_tokens,
        "output_tokens": outcome.output_tokens,
        "status": outcome.status.value,
        "retrieved": list(outcome.retrieved),
    }


def outcome_from_json(payload: dict[str, Any], criterion: Criterion) -> SpecialistOutcome:
    """Rebuild a specialist outcome, re-validating everything through the ordinary contracts.

    The `criterion` is passed in from the *case*, not read from the row. A checkpoint therefore
    cannot introduce a criterion the case did not select, and the id check below refuses a row
    that was written for a different one — which is what a mismatched resume would otherwise be:
    one criterion's findings delivered under another's authority.
    """
    _check_version(payload, criterion.node_id)
    stored_id = payload.get("criterion_id")
    if stored_id != criterion.criterion_id:
        raise ValueError(
            f"checkpoint row for node {criterion.node_id!r} carries criterion {stored_id!r} and "
            f"the case selected {criterion.criterion_id!r}. Restoring it would deliver one "
            "criterion's findings under another's authority."
        )
    return SpecialistOutcome(
        result=SpecialistResult.model_validate(payload["result"]),
        criterion=criterion,
        rejected=tuple(payload["rejected"]),
        resolved_model=payload["resolved_model"],
        input_tokens=int(payload["input_tokens"]),
        output_tokens=int(payload["output_tokens"]),
        status=SpecialistStatus(payload["status"]),
        retrieved=tuple(payload["retrieved"]),
    )


def synthesis_to_json(synthesis: SynthesisOutcome) -> dict[str, Any]:
    return {
        "v": CHECKPOINT_VERSION,
        "findings": [f.model_dump(mode="json") for f in synthesis.findings],
        "overlaps": [
            {
                "evidence_id": o.evidence_id,
                "finding_ids": list(o.finding_ids),
                "criterion_ids": list(o.criterion_ids),
            }
            for o in synthesis.overlaps
        ],
        "rejected": list(synthesis.rejected),
        "resolved_model": synthesis.resolved_model,
        "input_tokens": synthesis.input_tokens,
        "output_tokens": synthesis.output_tokens,
        "failed": synthesis.failed,
    }


def synthesis_from_json(payload: dict[str, Any]) -> SynthesisOutcome:
    _check_version(payload, SYNTHESIS_NODE)
    return SynthesisOutcome(
        findings=tuple(ProposedFinding.model_validate(f) for f in payload["findings"]),
        overlaps=tuple(
            Overlap(
                evidence_id=o["evidence_id"],
                finding_ids=tuple(o["finding_ids"]),
                criterion_ids=tuple(o["criterion_ids"]),
            )
            for o in payload["overlaps"]
        ),
        rejected=tuple(payload["rejected"]),
        resolved_model=payload["resolved_model"],
        input_tokens=int(payload["input_tokens"]),
        output_tokens=int(payload["output_tokens"]),
        failed=bool(payload["failed"]),
    )


# ---------------------------------------------------------------------------
# Where the rows live
# ---------------------------------------------------------------------------


class CheckpointStore(Protocol):
    """Two methods, the same narrowness as `idempotency.CallStore` and for the same reason.

    A resume asks exactly one question — "which nodes are already done, and what did they
    produce?" — and a wider interface would invite this to become the run's whole state, which is
    a different module's problem.
    """

    def completed(self, run_id: str) -> dict[str, dict[str, Any]]: ...

    def record(self, run_id: str, node_id: str, payload: dict[str, Any]) -> None: ...


class InMemoryCheckpointStore:
    """For tests, and for proving the mechanism without a database.

    **Proves the skip, not the durability.** It dies with the process, and a Lambda timeout *is*
    the process dying — `PostgresCheckpointStore` is the one LAMB-01 depends on.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = Lock()

    def completed(self, run_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {node: dict(row) for (run, node), row in self._rows.items() if run == run_id}

    def record(self, run_id: str, node_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            # First write wins, mirroring the Postgres store's ON CONFLICT DO NOTHING. Two stores
            # that disagree about re-recording would make an offline test prove the wrong thing.
            self._rows.setdefault((run_id, node_id), dict(payload))


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS ireports_node_checkpoints (
    run_id      TEXT        NOT NULL,
    node_id     TEXT        NOT NULL,
    recorded    JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, node_id)
);
"""
"""**One row per node, not one row per run**, and that is a correction to the bake-off's design.

`spikes/handrolled/.../checkpoint.py` kept a single row holding a `completed` map and rewrote the
whole map from in-process state on every node commit. Under a threaded fan-out that is a
read-modify-write race: two specialists finishing at once each write the map as they last saw it,
and one node's result disappears — silently, into a checkpoint that still looks well-formed.

A row per node has no shared cell to lose, so the write is atomic without the application knowing
anything about concurrency. It is also what makes per-node commit cheap, and per-node commit is
the property that lets a crash mid-fan-out keep the specialists that finished.
"""


class PostgresCheckpointStore:
    """The durable store — the one a resume across processes actually needs.

    Stores JSON and re-validates on read, never a pickle. Follows `PostgresCallStore` deliberately,
    down to `ON CONFLICT DO NOTHING`: the first recorded result for a node is the one that was paid
    for, and letting a later write replace it would rewrite history about what produced a finding.
    """

    def __init__(self, dsn: str, *, create_schema: bool = True) -> None:
        # Imported inside the methods, not at module scope, so a deployment without the `postgres`
        # extra can still import this module and use `InMemoryCheckpointStore` — the same
        # arrangement `idempotency.py` uses, for the same packaging reason.
        self._dsn = dsn
        if create_schema:
            with self._conn() as conn:
                conn.execute(POSTGRES_SCHEMA)

    def _conn(self) -> Any:
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def completed(self, run_id: str) -> dict[str, dict[str, Any]]:
        """Every completed node for this run, in one query.

        Read once at the start of a run rather than per node: the answer cannot change underneath
        a run that is the only writer for its own id, and N queries to learn N answers is the kind
        of thing that looks free locally and is not across a network.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT node_id, recorded FROM ireports_node_checkpoints WHERE run_id = %s",
                (run_id,),
            ).fetchall()
        return {str(node_id): dict(recorded) for node_id, recorded in rows}

    def record(self, run_id: str, node_id: str, payload: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ireports_node_checkpoints (run_id, node_id, recorded) "
                "VALUES (%s, %s, %s) ON CONFLICT (run_id, node_id) DO NOTHING",
                (run_id, node_id, json.dumps(payload)),
            )


# ---------------------------------------------------------------------------
# What an orchestrator is handed
# ---------------------------------------------------------------------------


class RunCheckpoint:
    """One run's completed nodes: loaded once, committed per node.

    **Per-node commit is the load-bearing property.** A node's result is written the moment it
    completes, not batched at the end of a stage, and that is what lets a crash mid-fan-out keep
    the specialists that finished. Batching would be fewer writes and would defeat the purpose.

    `resumed` is the measurement. A run that restores three of five nodes did not spend the wall
    clock those three would have cost, and that number is what LAMB-01 is judged on.
    """

    def __init__(self, run_id: str, store: CheckpointStore) -> None:
        self.run_id = run_id
        self._store = store
        self._completed = store.completed(run_id)
        self._lock = Lock()
        self._resumed: list[str] = []

    @property
    def resumed(self) -> tuple[str, ...]:
        """Node ids restored rather than executed, in the order they were restored."""
        with self._lock:
            return tuple(self._resumed)

    def restore_specialist(self, criterion: Criterion) -> SpecialistOutcome | None:
        payload = self._completed.get(criterion.node_id)
        if payload is None:
            return None
        outcome = outcome_from_json(payload, criterion)
        with self._lock:
            self._resumed.append(criterion.node_id)
        return outcome

    def record_specialist(self, outcome: SpecialistOutcome) -> None:
        """Write a completed node, or decline to.

        The `RESUMABLE_STATUSES` filter is where LAMB-01 lives: a criterion skipped because the
        run ran out of wall clock is the work the *next* invocation exists to do, and recording it
        would make the first invocation's stop permanent.
        """
        if outcome.status not in RESUMABLE_STATUSES:
            return
        self._store.record(self.run_id, outcome.criterion.node_id, outcome_to_json(outcome))

    def restore_synthesis(self) -> SynthesisOutcome | None:
        payload = self._completed.get(SYNTHESIS_NODE)
        if payload is None:
            return None
        outcome = synthesis_from_json(payload)
        with self._lock:
            self._resumed.append(SYNTHESIS_NODE)
        return outcome

    def record_synthesis(self, synthesis: SynthesisOutcome) -> None:
        # A failed synthesis is not written, for the reason a FAILED specialist is not: the stage
        # did not produce an answer, and freezing the failure would mean the resumed run inherits
        # it rather than getting the second chance the resume exists to give.
        if synthesis.failed:
            return
        self._store.record(self.run_id, SYNTHESIS_NODE, synthesis_to_json(synthesis))


@dataclass(frozen=True)
class Checkpointing:
    """Where a run's checkpoints live.

    Two ways to say it, and they are not interchangeable: a `dsn` for a real run, or an explicit
    `store` for a test or a single-process run that only needs the mechanism. Neither given is an
    error rather than a silent fallback — see `_require_dsn`.

    **This type used to carry a third field**, an opaque `saver` for the LangGraph adapter's own
    checkpointer, because that object is not a storage backend: it owns the graph's superstep
    bookkeeping as well as the results, so the two could share a connection string and nothing
    richer. ADR-029 removed the adapter and the field with it. Recorded here because the asymmetry
    is the substance of `docs/handoff/orchestration-decision.md` row 6, and a reader of this file
    should not have to reconstruct why a port once had two slots for one job.
    """

    dsn: str | None = None
    """PostgreSQL connection string. Used to build a `PostgresCheckpointStore` when no explicit
    `store` is given."""

    store: CheckpointStore | None = None
    """An explicit store. Takes precedence over `dsn`, and is how a test inspects the rows."""

    def run_checkpoint(self, run_id: str) -> RunCheckpoint:
        """One run's view of the store, loaded once."""
        store = self.store
        if store is None:
            store = PostgresCheckpointStore(self._require_dsn())
        return RunCheckpoint(run_id, store)

    def _require_dsn(self) -> str:
        if self.dsn is None:
            raise ValueError(
                "Checkpointing has neither a dsn nor a store, so there is nowhere durable to "
                "write. Pass a dsn for a real run, or InMemoryCheckpointStore() for a test."
            )
        return self.dsn


__all__ = [
    "CHECKPOINT_VERSION",
    "POSTGRES_SCHEMA",
    "RESUMABLE_STATUSES",
    "SYNTHESIS_NODE",
    "CheckpointStore",
    "Checkpointing",
    "InMemoryCheckpointStore",
    "PostgresCheckpointStore",
    "RunCheckpoint",
    "outcome_from_json",
    "outcome_to_json",
    "synthesis_from_json",
    "synthesis_to_json",
]
