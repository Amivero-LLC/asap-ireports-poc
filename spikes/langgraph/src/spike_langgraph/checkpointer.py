"""The checkpointer: LangGraph's first-party `PostgresSaver`, plus a crash hook and a ruler.

ADR-012 lists LangGraph as "the only candidate where a PostgreSQL checkpointer is a first-party
package rather than something we build." That claim is what this file tests, and the striking part
is how little is here: the hand-rolled candidate needs a 56-line checkpoint store and Strands needs
a 159-line `SessionRepository`, while LangGraph needs a subclass whose only overrides exist for the
*spike*, not for the architecture. `PostgresSaver.setup()` creates and migrates its own tables.

**Where the crash goes, and why it is the only defensible place.** Leg 1 asks what survives a hard
kill, and the answer depends entirely on where the process dies relative to the durable write. Both
other candidates kill immediately after their durable write commits — the hand-rolled one after
`commit_node`, Strands inside `update_multi_agent`. The equivalent point here is immediately after
`put_writes` returns, because that is the call in which LangGraph makes a completed task's output
durable. Killing anywhere else would measure our hook placement rather than the framework's
durability.

**A property worth knowing before reading the numbers.** `put_writes` is *not* called on the thread
that ran the node. `langgraph/pregel/_loop.py` submits it to a `BackgroundExecutor`, so persistence
runs concurrently with the next node. That is why `durability` is a real setting and not a
formality — see `orchestrator.DURABILITY`.

**Identifying the node.** The kill fires on the `completed` marker each node writes, not on
`task_path`. LangGraph does pass a `task_path` like `'~__pregel_pull, specialist_suitability'`, and
parsing it would work today, but its format is internal — keying the spike's most load-bearing hook
to an undocumented string would make a framework upgrade look like a durability regression.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ireports_spike_harness import port
from ireports_spike_harness.gateway import DEFAULT_DSN, connect
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

COMPLETED_CHANNEL = "completed"
"""The channel every node appends its own id to. Read by the crash hook; also the cheapest
answer to "what has this run actually done", which is a scored dimension (state inspectability)."""


def strict_serde() -> JsonPlusSerializer:
    """The checkpoint serializer, with deserialization restricted to an allowlist.

    **This is not a precaution against a hypothetical.** `langgraph/checkpoint/serde/_msgpack.py`
    states it first-party: *"Set `LANGGRAPH_STRICT_MSGPACK=true` to restrict checkpoint
    deserialization to the types listed in `SAFE_MSGPACK_TYPES`. Without this, any Python callable
    stored in checkpoint data will be imported and executed on load."* The default is permissive.

    `allowed_msgpack_modules=None` selects the same strict mode as that environment variable, and
    selects it *in code*, so it cannot be lost by an environment that forgot to set it — the same
    reasoning as `telemetry.pin_tracing_closed`. `pickle_fallback` already defaults to `False` and
    is left there; it is passed explicitly so a future default change is visible in a diff.

    This costs us nothing: the state channels carry plain JSON (`orchestrator.SpikeState`), and
    everything LangGraph itself round-trips — `Interrupt`, `Send`, `Command` — is on the allowlist.
    Full reasoning: `docs/handoff/checkpoint-threat-model.md`.
    """
    return JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)


class CrashingPostgresSaver(PostgresSaver):
    """`PostgresSaver`, with `--crash-after` honoured at the durable-write boundary."""

    def __init__(self, conn: Any, crash_after: str | None = None) -> None:
        super().__init__(conn, serde=strict_serde())
        self._crash_after = crash_after

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)

        # The row above is committed, so whatever LangGraph chose to persist for this task is
        # durable, and nothing after this line runs. `os._exit` skips `finally`, atexit, and
        # destructors — a graceful shutdown would let the framework flush on the way out, which
        # is exactly what a crash must not be able to rely on.
        if self._crash_after is None:
            return
        for channel, value in writes:
            if channel == COMPLETED_CHANNEL and self._crash_after in (value or []):
                port.die_hard()


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def state_bytes(run_id: str, dsn: str = DEFAULT_DSN) -> dict[str, int]:
    """Serialized state at the current point of the run — an ADR-012 scored dimension.

    Reported two ways, because LangGraph's storage model differs from the other candidates' in a
    way a single number would hide.

    - `latest_checkpoint` is the comparable figure: the newest checkpoint row plus the channel
      blobs that checkpoint's `channel_versions` actually references, plus its pending writes.
      This is "what has to exist to resume from here", which is what the hand-rolled candidate's
      16 KB row and Strands' 24 KB row both measure.
    - `thread_total` is every row LangGraph keeps for the thread. The hand-rolled and Strands
      candidates overwrite one row per run; LangGraph retains **every superstep**, plus a blob per
      channel per version. That history is a genuine feature — time travel, replay, and
      `get_state_history` are scored under state inspectability — but it is not free, and a
      comparison that quoted only the first number would flatter it.
    """
    with connect(dsn) as conn:
        row = conn.execute(
            """
            SELECT checkpoint_id,
                   checkpoint,
                   octet_length(checkpoint::text) + octet_length(metadata::text) AS row_bytes
            FROM checkpoints
            WHERE thread_id = %s
            ORDER BY (metadata->>'step')::int DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return {"latest_checkpoint": 0, "thread_total": 0}

        checkpoint = row["checkpoint"]
        if isinstance(checkpoint, str):
            checkpoint = json.loads(checkpoint)
        versions: dict[str, Any] = checkpoint.get("channel_versions", {})

        blob_bytes = 0
        if versions:
            blob_row = conn.execute(
                """
                SELECT COALESCE(SUM(octet_length(blob)), 0) AS n
                FROM checkpoint_blobs
                WHERE thread_id = %s AND (channel, version) IN (
                    SELECT * FROM unnest(%s::text[], %s::text[])
                )
                """,
                (run_id, list(versions), [str(v) for v in versions.values()]),
            ).fetchone()
            blob_bytes = int(blob_row["n"]) if blob_row else 0

        writes_row = conn.execute(
            "SELECT COALESCE(SUM(octet_length(blob)), 0) AS n FROM checkpoint_writes "
            "WHERE thread_id = %s AND checkpoint_id = %s",
            (run_id, row["checkpoint_id"]),
        ).fetchone()

        total_row = conn.execute(
            """
            SELECT
              (SELECT COALESCE(
                        SUM(octet_length(checkpoint::text) + octet_length(metadata::text)), 0)
                 FROM checkpoints WHERE thread_id = %(t)s)
            + (SELECT COALESCE(SUM(octet_length(blob)), 0)
                 FROM checkpoint_blobs WHERE thread_id = %(t)s)
            + (SELECT COALESCE(SUM(octet_length(blob)), 0)
                 FROM checkpoint_writes WHERE thread_id = %(t)s) AS n
            """,
            {"t": run_id},
        ).fetchone()

    # Both aggregates use COALESCE, so a row is always returned; the guard is for the type
    # checker and for the day someone edits the SQL into something that can return nothing.
    writes_bytes = int(writes_row["n"]) if writes_row else 0
    total_bytes = int(total_row["n"]) if total_row else 0

    return {
        "latest_checkpoint": int(row["row_bytes"]) + blob_bytes + writes_bytes,
        "thread_total": total_bytes,
    }
