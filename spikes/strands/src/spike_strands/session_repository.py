"""A PostgreSQL `SessionRepository` for Strands — the work the 1b scan predicted.

`docs/handoff/orchestration-landscape.md` §5.2: Strands ships file, S3, and snapshot session
backends and **no PostgreSQL backend**, so meeting ADR-012's C4 (PostgreSQL is the system of
record for workflow state) means implementing `SessionRepository` ourselves. This module is that
work, and its size is part of the scorecard.

Two things are worth knowing before reading it.

**Only the multi-agent half is exercised.** `SessionRepository` is shaped around conversational
agents — sessions own agents, agents own messages. A `Graph` of non-LLM nodes touches none of
that; the framework calls `read_multi_agent` / `create_multi_agent` / `update_multi_agent` and
nothing else. The agent and message methods below are implemented because the abstract base
requires them, not because anything calls them. That ratio is itself a finding: the persistence
interface we must satisfy is wider than the persistence we actually need.

**The crash hook lives here on purpose.** Spike leg 1 asks what survives a hard kill, and the
answer depends entirely on where the process dies *relative to the durable write*. Putting
`--crash-after` anywhere else would measure our hook ordering rather than the framework's
durability, so the kill happens in `update_multi_agent`, immediately after the row commits —
the same position the hand-rolled candidate kills in, right after `commit_node`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ireports_spike_harness import port
from ireports_spike_harness.gateway import DEFAULT_DSN, connect
from strands.session.session_repository import SessionRepository
from strands.types.session import Session, SessionAgent, SessionMessage

if TYPE_CHECKING:
    from strands.multiagent import MultiAgentBase

SCHEMA = """
CREATE TABLE IF NOT EXISTS strands_sessions (
    session_id  TEXT PRIMARY KEY,
    payload     JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The graph's execution state. One row per (session, multi-agent id); this is the row that
-- makes leg 1 answerable, and the only one a Graph of non-LLM nodes ever writes.
CREATE TABLE IF NOT EXISTS strands_multi_agents (
    session_id      TEXT        NOT NULL,
    multi_agent_id  TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, multi_agent_id)
);

-- Required by the interface, unused by a Graph of deterministic nodes. Kept so the
-- implementation is honest about what satisfying `SessionRepository` actually costs.
CREATE TABLE IF NOT EXISTS strands_agents (
    session_id  TEXT  NOT NULL,
    agent_id    TEXT  NOT NULL,
    payload     JSONB NOT NULL,
    PRIMARY KEY (session_id, agent_id)
);

CREATE TABLE IF NOT EXISTS strands_messages (
    session_id  TEXT   NOT NULL,
    agent_id    TEXT   NOT NULL,
    message_id  BIGINT NOT NULL,
    payload     JSONB  NOT NULL,
    PRIMARY KEY (session_id, agent_id, message_id)
);
"""


def init_schema(dsn: str = DEFAULT_DSN) -> None:
    with connect(dsn) as conn:
        conn.execute(SCHEMA)


class PostgresSessionRepository(SessionRepository):
    """`SessionRepository` over PostgreSQL. State is JSON, never a pickled object.

    Same reasoning as the hand-rolled checkpoint store: a checkpoint blob is a deserialization
    trust boundary in *every* design (ADR-012, and the four LangGraph advisories the 1b scan
    catalogued). Storing framework-produced JSON and letting the framework re-validate it keeps
    a tampered row a parse failure rather than an execution.
    """

    def __init__(self, dsn: str = DEFAULT_DSN, crash_after: str | None = None) -> None:
        self.dsn = dsn
        self._crash_after = crash_after
        init_schema(dsn)

    # -- sessions ----------------------------------------------------------

    def create_session(self, session: Session, **kwargs: Any) -> Session:
        with connect(self.dsn) as conn:
            conn.execute(
                "INSERT INTO strands_sessions (session_id, payload) VALUES (%s, %s) "
                "ON CONFLICT (session_id) DO NOTHING",
                (session.session_id, json.dumps(session.to_dict())),
            )
        return session

    def read_session(self, session_id: str, **kwargs: Any) -> Session | None:
        with connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT payload FROM strands_sessions WHERE session_id = %s", (session_id,)
            ).fetchone()
        return None if row is None else Session.from_dict(row["payload"])

    # -- multi-agent state — the part that actually matters ----------------

    def create_multi_agent(
        self, session_id: str, multi_agent: MultiAgentBase, **kwargs: Any
    ) -> None:
        self._write_multi_agent(session_id, multi_agent)

    def read_multi_agent(
        self, session_id: str, multi_agent_id: str, **kwargs: Any
    ) -> dict[str, Any] | None:
        with connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT payload FROM strands_multi_agents "
                "WHERE session_id = %s AND multi_agent_id = %s",
                (session_id, multi_agent_id),
            ).fetchone()
        return None if row is None else dict(row["payload"])

    def update_multi_agent(
        self, session_id: str, multi_agent: MultiAgentBase, **kwargs: Any
    ) -> None:
        payload = self._write_multi_agent(session_id, multi_agent)

        # The crash, positioned deliberately: the row above is committed, so whatever the
        # framework chose to persist is durable, and nothing after this line runs. `os._exit`
        # skips `finally`, atexit, and destructors — a graceful shutdown would let the framework
        # flush on the way out, which is exactly the behaviour a crash must not be able to rely on.
        if self._crash_after and self._crash_after in payload.get("completed_nodes", []):
            port.die_hard()

    def _write_multi_agent(self, session_id: str, multi_agent: MultiAgentBase) -> dict[str, Any]:
        payload = multi_agent.serialize_state()
        with connect(self.dsn) as conn:
            conn.execute(
                """
                INSERT INTO strands_multi_agents (session_id, multi_agent_id, payload, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (session_id, multi_agent_id) DO UPDATE
                    SET payload = EXCLUDED.payload, updated_at = now()
                """,
                (session_id, multi_agent.id, json.dumps(payload)),
            )
        return payload

    def serialized_bytes(self, session_id: str, multi_agent_id: str) -> int:
        """Serialized state size — an ADR-012 scored dimension."""
        payload = self.read_multi_agent(session_id, multi_agent_id)
        return 0 if payload is None else len(json.dumps(payload).encode())

    # -- agents and messages: required by the interface, unused by a Graph --

    def create_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        with connect(self.dsn) as conn:
            conn.execute(
                "INSERT INTO strands_agents (session_id, agent_id, payload) VALUES (%s, %s, %s) "
                "ON CONFLICT (session_id, agent_id) DO UPDATE SET payload = EXCLUDED.payload",
                (session_id, session_agent.agent_id, json.dumps(session_agent.to_dict())),
            )

    def read_agent(self, session_id: str, agent_id: str, **kwargs: Any) -> SessionAgent | None:
        with connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT payload FROM strands_agents WHERE session_id = %s AND agent_id = %s",
                (session_id, agent_id),
            ).fetchone()
        return None if row is None else SessionAgent.from_dict(row["payload"])

    def update_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        self.create_agent(session_id, session_agent)

    def create_message(
        self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs: Any
    ) -> None:
        with connect(self.dsn) as conn:
            conn.execute(
                "INSERT INTO strands_messages (session_id, agent_id, message_id, payload) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (session_id, agent_id, message_id) DO UPDATE "
                "SET payload = EXCLUDED.payload",
                (
                    session_id,
                    agent_id,
                    session_message.message_id,
                    json.dumps(session_message.to_dict()),
                ),
            )

    def read_message(
        self, session_id: str, agent_id: str, message_id: int, **kwargs: Any
    ) -> SessionMessage | None:
        with connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT payload FROM strands_messages "
                "WHERE session_id = %s AND agent_id = %s AND message_id = %s",
                (session_id, agent_id, message_id),
            ).fetchone()
        return None if row is None else SessionMessage.from_dict(row["payload"])

    def update_message(
        self, session_id: str, agent_id: str, session_message: SessionMessage, **kwargs: Any
    ) -> None:
        self.create_message(session_id, agent_id, session_message)

    def list_messages(
        self,
        session_id: str,
        agent_id: str,
        limit: int | None = None,
        offset: int = 0,
        **kwargs: Any,
    ) -> list[SessionMessage]:
        sql = (
            "SELECT payload FROM strands_messages WHERE session_id = %s AND agent_id = %s "
            "ORDER BY message_id OFFSET %s"
        )
        params: list[Any] = [session_id, agent_id, offset]
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        with connect(self.dsn) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [SessionMessage.from_dict(r["payload"]) for r in rows]
