"""Run one LangGraph analysis under a network guard and report what it tried to reach.

Driven by `test_langsmith_egress.py`, which runs it in a **subprocess** per scenario. That is not
fastidiousness: `langsmith.configure(enabled=False)` sets a process-wide global and
`langsmith.utils.get_env_var` is `lru_cache`d, so two scenarios in one interpreter would
contaminate each other and the second would report the first's state. A subprocess per scenario
also matches how the control is actually applied — at an entry point, once, before any work.

The guard denies at name resolution and at `connect`, records every attempt, and lets
`localhost` through so PostgreSQL still works. That is deliberately the *weakest* place to put a
deny — inside the process, where the library could in principle bypass it. In a deployment the
control belongs in the VPC egress policy. This probe answers "does the workload try", which is
the question a network policy cannot answer for you.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import uuid

LOCAL = {"localhost", "127.0.0.1", "::1"}
ATTEMPTS: list[list[object]] = []

_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


def _guard_getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
    if host not in LOCAL:
        ATTEMPTS.append(["getaddrinfo", str(host), port])
        raise OSError(f"egress denied: getaddrinfo {host}:{port}")
    return _real_getaddrinfo(host, port, *args, **kwargs)


def _guard_connect(self, address):  # type: ignore[no-untyped-def]
    host = address[0] if isinstance(address, tuple) else str(address)
    if host not in LOCAL:
        ATTEMPTS.append(["connect", str(host), address[1] if isinstance(address, tuple) else None])
        raise OSError(f"egress denied: connect {address}")
    return _real_connect(self, address)


def main() -> int:
    socket.getaddrinfo = _guard_getaddrinfo
    socket.socket.connect = _guard_connect  # type: ignore[method-assign]

    if os.environ.get("PROBE_PIN") == "1":
        from spike_langgraph.telemetry import pin_tracing_closed

        pin_tracing_closed()

    from ireports_spike_harness.gateway import init_schema
    from langsmith.utils import tracing_is_enabled
    from spike_langgraph.orchestrator import LangGraphOrchestrator

    tracing = bool(tracing_is_enabled())

    init_schema()
    outcome = LangGraphOrchestrator().start(f"run_egress_{uuid.uuid4().hex[:12]}")

    # LangSmith exports on a background thread. Give it a generous window before concluding that
    # nothing was sent — "we did not wait long enough" and "it did not try" look identical.
    time.sleep(3.0)

    print(
        json.dumps(
            {
                "tracing_enabled": tracing,
                "findings": len(outcome.proposed_findings),
                "attempts": ATTEMPTS,
                "hosts": sorted({str(a[1]) for a in ATTEMPTS}),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
