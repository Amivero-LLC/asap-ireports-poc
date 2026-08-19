"""A model call made twice is a model call paid for twice (ORCH-02).

**Idempotency belongs at the gateway, not in the orchestrator**, and that placement is the first
finding this module produced. The gateway is the only component permitted to call a model
(ADR-015), so wrapping it gives both orchestration paths idempotency in identical, framework-free
code. It is therefore **not** a point of comparison between them — the thing that discriminates
custom Python from LangGraph is resuming *run state*, not avoiding a duplicate call. That is worth
knowing before ADR-024 is decided, because "durable orchestration of paid sub-calls" sounds like
one property and is two, and only one of them is the framework's business.

The measurement this exists to move: the bake-off's crash harness counted **11 of 24** duplicate
paid calls for LangGraph and **12 of 24** hand-rolled. Both candidates owed this and neither built
it. It is the most expensive item ADR-020 retained, retained because durable orchestration of paid
sub-calls is not a real claim if resuming double-pays.

**Two traps, both load-bearing.**

*The retry must not be deduplicated.* `analyze` calls the model twice when the first response comes
back in an unusable shape (ADR-018). Those two calls are byte-identical requests, so a naive
fingerprint would serve the first attempt's bad response to the second attempt forever — turning a
bounded retry into a guaranteed failure that looks like a model problem. `attempt` is therefore part
of the key, and it is the caller's job to increment it.

*A refusal is a result, not an error to retry.* ADR-015 says a refusal must not be retried blindly,
and a refusal costs money like anything else. So a refusal is recorded and replayed as a refusal —
resuming a crashed run must not re-ask a question the model has already declined.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from ireports_domain import ModelAlias
from ireports_gateway.port import (
    ModelGateway,
    ModelRefusalError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)

REPLAY_VERSION = "1"
"""Bumped when the stored shape changes, so an old row cannot be replayed into new code.

A checkpoint is a trust boundary in any design — `docs/handoff/orchestration-landscape.md` records
four deserialization RCEs on one framework's checkpoint path in nine months. This does not make
replay safe on its own; it makes a *stale* row fail loudly rather than deserialize into something
the current code will misread."""


def call_fingerprint(run_id: str, request: ModelRequest, attempt: int) -> str:
    """A deterministic key for one intended model call.

    Everything that changes what the model is asked goes in. `max_tokens` and `effort` are
    included because a call that differs only in effort is a different call and a different price;
    replaying across that difference would silently serve a cheaper answer than the one requested.

    `run_id` scopes the key so two runs of the same case never share responses — a replay across
    runs would make the second run's provenance a lie about which call produced its findings.
    """
    material = {
        "v": REPLAY_VERSION,
        "run_id": run_id,
        "attempt": attempt,
        "node_id": request.node_id,
        "alias": request.alias.value,
        "system": request.system,
        "max_tokens": request.max_tokens,
        "effort": request.effort.value if request.effort else None,
        "messages": [(m.role, m.content) for m in request.messages],
        "response_schema": request.response_schema,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class RecordedCall:
    """What a completed call left behind, as data rather than a pickled object.

    JSON-shaped on purpose. A checkpoint blob that deserializes into live objects is a remote code
    execution surface; this re-validates into a `ModelResponse` through ordinary constructors, so a
    tampered row produces a bad value rather than a running one.
    """

    text: str
    alias: str
    resolved_model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    refusal_category: str | None = None
    """Set when the call was refused. Replaying re-raises rather than returning text."""

    run_id_hint: str = ""
    """Which run paid for this call.

    Named a hint because nothing reads it to make a decision — the key already scopes replay to a
    run. It exists for the operational question that follows a bad run: what did this cost, and
    what is safe to discard."""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> RecordedCall:
        return cls(**json.loads(raw))

    @classmethod
    def of(cls, response: ModelResponse, run_id: str = "") -> RecordedCall:
        return cls(
            run_id_hint=run_id,
            text=response.text,
            alias=response.alias.value,
            resolved_model=response.resolved_model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    def replay(self) -> ModelResponse:
        if self.refusal_category is not None:
            raise ModelRefusalError(category=self.refusal_category)
        return ModelResponse(
            text=self.text,
            alias=ModelAlias(self.alias),
            resolved_model=self.resolved_model,
            usage=ModelUsage(input_tokens=self.input_tokens, output_tokens=self.output_tokens),
            stop_reason=self.stop_reason,
        )


class CallStore(Protocol):
    """Where recorded calls live between attempts, and between processes.

    Narrow on purpose: two methods, no transactions, no iteration. A resume needs to answer exactly
    one question — "have I already paid for this call?" — and a wider interface would invite the
    store to become the run's state, which is PostgreSQL's job and a different module's problem.
    """

    def get(self, key: str) -> RecordedCall | None: ...

    def put(self, key: str, call: RecordedCall) -> None: ...


class InMemoryCallStore:
    """For tests, and for a single-process run that only needs within-run deduplication.

    **Proves the mechanism, not the durability.** Surviving a crash needs a store that outlives the
    process; this one dies with it. `PostgresCallStore` is the one LAMB-01 depends on.
    """

    def __init__(self) -> None:
        self._calls: dict[str, RecordedCall] = {}
        self._lock = Lock()

    def get(self, key: str) -> RecordedCall | None:
        with self._lock:
            return self._calls.get(key)

    def put(self, key: str, call: RecordedCall) -> None:
        with self._lock:
            self._calls[key] = call


class IdempotentGateway:
    """A `ModelGateway` that never pays for the same call twice.

    Wraps another gateway rather than replacing one, so every adapter — `litellm`, `bedrock`, and
    `stub` — gets this without knowing about it, and the tier-alias rule is untouched.

    `attempt` is set by the caller through `next_attempt()` before a retried call. It is not
    inferred, because inferring it would mean guessing whether a repeated identical request is a
    resume (replay it) or a retry (do not), and those want opposite behaviour.
    """

    name = "idempotent"

    def __init__(self, inner: ModelGateway, store: CallStore, run_id: str) -> None:
        self._inner = inner
        self._store = store
        self._run_id = run_id
        self._lock = Lock()
        self._attempt = 0
        self.calls_made = 0
        """Calls that reached the wrapped gateway — the ones that cost money."""

        self.calls_replayed = 0
        """Calls served from the store. **This is the ORCH-02 measurement**: after a crash and
        resume, duplicate *paid* calls is what must be zero, and every replay here is one that
        would otherwise have been paid for again."""

    def next_attempt(self) -> None:
        """Move to a fresh attempt, so a bounded retry is not served its own bad answer."""
        with self._lock:
            self._attempt += 1

    def complete(self, request: ModelRequest) -> ModelResponse:
        key = call_fingerprint(self._run_id, request, self._attempt)

        recorded = self._store.get(key)
        if recorded is not None:
            with self._lock:
                self.calls_replayed += 1
            return recorded.replay()

        try:
            response = self._inner.complete(request)
        except ModelRefusalError as exc:
            # Recorded before re-raising: a refusal was paid for, and resuming must not re-ask a
            # question the model has already declined (ADR-015).
            self._store.put(
                key,
                RecordedCall(
                    text="",
                    alias=request.alias.value,
                    resolved_model="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="refusal",
                    refusal_category=exc.category,
                    run_id_hint=self._run_id,
                ),
            )
            with self._lock:
                self.calls_made += 1
            raise

        self._store.put(key, RecordedCall.of(response, self._run_id))
        with self._lock:
            self.calls_made += 1
        return response


def _typed(gateway: IdempotentGateway) -> ModelGateway:
    """Assert at type-check time that the wrapper satisfies the port it claims to."""
    return gateway


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS ireports_model_calls (
    call_key    TEXT PRIMARY KEY,
    run_id      TEXT        NOT NULL,
    recorded    JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ireports_model_calls_run_id ON ireports_model_calls (run_id);
"""
"""One row per paid call.

`call_key` is the primary key, so a concurrent double-insert of the same call is resolved by the
database rather than by application luck — the fan-out is threaded, and two specialists racing on
the same key is exactly the situation this table exists for.

The `run_id` index is not for the read path, which is always by key. It is for the operational
question that follows a bad run: *what did this run cost, and what is safe to discard.*
"""


class PostgresCallStore:
    """The durable store — the one a resume across processes actually needs.

    `InMemoryCallStore` proves the mechanism and dies with the process. **A Lambda timeout kills
    the process**, so LAMB-01 requires this one or an equivalent: the whole claim is that a second
    invocation replays what the first already paid for, and it can only do that from storage that
    outlived the first.

    Stores JSON and re-validates on read, never a pickle. `docs/handoff/orchestration-landscape.md`
    records four deserialization RCEs on one framework's checkpoint path in nine months; the lesson
    is not that a framework was careless but that **a checkpoint blob is a deserialization trust
    boundary in any design.**

    **Row integrity is not addressed here and is a known gap.** A tampered row that still parses
    into a valid `RecordedCall` would be replayed as though it were the model's answer — the
    largest known security hole in this design, deliberately left for before anything real runs on
    it rather than before the proof of concept works (`docs/handoff/checkpoint-threat-model.md`).
    """

    def __init__(self, dsn: str, *, create_schema: bool = True) -> None:
        # Imported here, not at module scope, so a deployment without the `postgres` extra can
        # still import this module and use `InMemoryCallStore` — the same arrangement the
        # retrieval and gateway adapters use, for the same packaging reason.
        self._dsn = dsn
        if create_schema:
            with self._conn() as conn:
                conn.execute(POSTGRES_SCHEMA)

    def _conn(self) -> Any:
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def get(self, key: str) -> RecordedCall | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT recorded FROM ireports_model_calls WHERE call_key = %s", (key,)
            ).fetchone()
        if row is None:
            return None
        recorded = row[0]
        return RecordedCall(**recorded)

    def put(self, key: str, call: RecordedCall) -> None:
        # ON CONFLICT DO NOTHING, never DO UPDATE. The first recorded answer for a key is the one
        # that was paid for; overwriting it would let a later, cheaper path rewrite history about
        # what produced a finding.
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ireports_model_calls (call_key, run_id, recorded) "
                "VALUES (%s, %s, %s) ON CONFLICT (call_key) DO NOTHING",
                (key, call.run_id_hint, json.dumps(call.__dict__)),
            )


__all__ = [
    "POSTGRES_SCHEMA",
    "CallStore",
    "IdempotentGateway",
    "InMemoryCallStore",
    "PostgresCallStore",
    "RecordedCall",
    "call_fingerprint",
]
