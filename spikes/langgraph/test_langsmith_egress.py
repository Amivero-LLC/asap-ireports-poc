"""The LangSmith egress-deny test — a required deliverable if LangGraph is selected.

ADR-012 and `docs/handoff/orchestration-landscape.md` §5.1 make this a spike deliverable rather
than a footnote, on this reasoning: `langsmith` is a **mandatory** transitive dependency of
`langchain-core`, so it is in the dependency tree whether or not we use it; tracing is opt-in and
the default is not egress; but a client library capable of exporting run content out of a system
that may carry CUI must be *pinned closed and proven closed*, not trusted.

Four scenarios, and the second is the one that makes the other three mean anything.

- `test_langsmith_is_a_mandatory_dependency` — the premise, checked: `langchain-core` requires
  `langsmith` unconditionally, so we neither import it nor can remove it.
- `test_default_is_closed` — clean environment: tracing off, **zero** egress attempts during a
  full run.
- `test_misconfiguration_is_not_benign` — **the negative control.** `LANGSMITH_TRACING=true` with
  no pin: the run attempts egress to `api.smith.langchain.com`, and still returns three findings,
  because LangSmith swallows the failure.
- `test_the_pin_holds_against_a_hostile_environment` — the same hostile variable, with
  `pin_tracing_closed()`: tracing off, **zero** attempts.

The negative control follows the same principle as `harness/negative_control.py`: a control that
has never caught anything is not evidence. Without it, "zero egress attempts" would be equally
consistent with the guard being inert. With it, we know the guard sees traffic when there is
traffic to see.

**What the negative control actually found**, and why it is the most important line in this file:
the export is a `POST /runs/multipart` carrying roughly 90 KB — the whole graph state, including
every proposed finding's observation text — and when it fails, **the run still succeeds**.
LangSmith logs and continues. So a misconfigured deployment leaks silently, and a blocked one
gives the operator no signal either. That is why the control is an explicit, verified,
fail-closed call at the entry point rather than an absent environment variable.

Each scenario runs in its own subprocess. `langsmith.configure` sets a process-wide global and
`get_env_var` is `lru_cache`d, so scenarios sharing an interpreter would contaminate each other —
and this pytest process has already loaded the `langsmith` pytest plugin, which is exactly the
kind of ambient state the measurement must not depend on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from ireports_spike_harness.gateway import DEFAULT_DSN, connect

PROBE = Path(__file__).parent / "egress_probe.py"
LANGSMITH_HOST = "api.smith.langchain.com"


def _postgres_available() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(),
    reason=(
        f"PostgreSQL unreachable at {DEFAULT_DSN}. "
        "Start it: docker compose -f infrastructure/docker/compose.yaml up -d"
    ),
)


def _probe(**env: str) -> dict[str, Any]:
    """Run one full analysis in a fresh process under the guard, and return what it saw."""
    environment = {k: v for k, v in os.environ.items() if not k.startswith("LANGSMITH_")}
    environment.update(env)
    completed = subprocess.run(
        [sys.executable, str(PROBE)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise AssertionError(f"probe exited {completed.returncode}\n{completed.stderr}")
    parsed: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    return parsed


def test_langsmith_is_a_mandatory_dependency() -> None:
    """The premise, checked rather than quoted.

    If a future `langchain-core` drops the requirement, this test fails and the whole control
    becomes unnecessary — which is a result worth being told about rather than discovering by
    reading a changelog.
    """
    from importlib.metadata import requires

    from packaging.requirements import Requirement

    parsed = [Requirement(r) for r in requires("langchain-core") or []]
    # Mandatory means unconditional: not behind an extra, and not behind an environment marker.
    mandatory = {r.name for r in parsed if r.marker is None}

    assert "langsmith" in mandatory, (
        "langchain-core no longer requires langsmith unconditionally; re-examine whether this "
        f"control is still needed. Current mandatory set: {sorted(mandatory)}"
    )


@requires_postgres
def test_default_is_closed() -> None:
    """No LangSmith variables set: tracing off, nothing leaves the process."""
    result = _probe()
    assert result["tracing_enabled"] is False
    assert result["attempts"] == [], result["attempts"]
    assert result["findings"] == 3


@requires_postgres
def test_misconfiguration_is_not_benign() -> None:
    """Negative control: without the pin, a hostile environment variable does cause egress.

    Also asserts the run still returns three findings. That is not incidental — it is the finding.
    A leak here is not accompanied by a failure, so nothing downstream would ever notice.
    """
    result = _probe(LANGSMITH_TRACING="true", LANGSMITH_API_KEY="lsv2_not_a_real_key")

    assert result["tracing_enabled"] is True
    assert LANGSMITH_HOST in result["hosts"], (
        "expected the unpinned run to attempt LangSmith egress; if it no longer does, this "
        "control's evidence is stale and the guard may now be inert"
    )
    assert result["findings"] == 3, (
        "the run should still succeed — a silently swallowed export failure is the reason the "
        "pin has to be explicit and verified"
    )


@requires_postgres
def test_the_pin_holds_against_a_hostile_environment() -> None:
    """`pin_tracing_closed()` beats an inherited `LANGSMITH_TRACING=true`.

    This is the property an environment variable of our own could not give us: `tracing_is_enabled`
    consults the process-global before the environment, so the API-level pin wins regardless of
    what a base image, a task definition, or a developer's shell set.
    """
    result = _probe(
        PROBE_PIN="1", LANGSMITH_TRACING="true", LANGSMITH_API_KEY="lsv2_not_a_real_key"
    )

    assert result["tracing_enabled"] is False
    assert result["attempts"] == [], result["attempts"]
    assert result["findings"] == 3
