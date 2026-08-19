"""Skip the PostgreSQL-backed tests when there is no PostgreSQL, and say so.

**These tests are evidence, not conveniences.** ORCH-02's call store and the node checkpoint both
make their central claim — that a *second process* can see what the first paid for — against a real
database across a real process boundary. An `InMemory*` store cannot make that claim at all.

So they must actually run somewhere, and this hook is only about *where*. Locally, a developer
without the compose stack gets a named skip instead of a `psycopg.OperationalError` traceback. In
CI they run in the `spikes` job, which has a PostgreSQL service, under the same no-silent-skips
guard the bake-off legs have — because a skipped leg is not a passing leg, and it looks like
evidence.

The connectivity probe runs once per session rather than per test: it opens a socket, and 5 of
those to say the same thing is 5 chances for a flaky answer.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

DSN = os.environ.get(
    "IREPORTS_SPIKE_DSN",
    "postgresql://ireports:ireports_local_only@localhost:5436/ireports_spike",
)


def _reachable() -> bool:
    """A TCP connect, not a `psycopg.connect`.

    Deliberately weaker than the thing being tested: this answers "is there a server there", and
    the tests themselves answer "does it behave". A probe that authenticated and created a schema
    would turn a real defect — bad credentials, a missing extension — into a skip.
    """
    parsed = urlparse(DSN)
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 2):
            return True
    except OSError:
        return False


_AVAILABLE = _reachable()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if _AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason=(
            f"needs PostgreSQL at {urlparse(DSN).netloc}: "
            "docker compose -f infrastructure/docker/compose.yaml up -d"
        )
    )
    for item in items:
        if "requires_postgres" in item.keywords:
            item.add_marker(skip)
