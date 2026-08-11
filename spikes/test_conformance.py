"""Drive the four ADR-012 legs against every registered candidate.

Adding a candidate is one line in `CANDIDATES`. That is the design working: a new spike gets the
same scenario, the same gateway, the same assertions, and the same scorecard row automatically,
so nothing about the comparison depends on the author of the spike remembering to be fair.

Requires the compose stack:

    docker compose -f infrastructure/docker/compose.yaml up -d
    uv run pytest spikes -v

Skipped, not failed, when PostgreSQL is unreachable — a developer without Docker running should
still get a clean contract-test run.
"""

from __future__ import annotations

import pytest
from ireports_spike_harness import conformance
from ireports_spike_harness.gateway import DEFAULT_DSN, connect, init_schema

CANDIDATES: dict[str, str] = {
    "hand-rolled": "spike_handrolled",
    "langgraph": "spike_langgraph",
    "strands": "spike_strands",
}


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


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    if _postgres_available():
        init_schema()


@requires_postgres
@pytest.mark.parametrize("candidate,module", sorted(CANDIDATES.items()))
@pytest.mark.parametrize("leg", conformance.LEGS, ids=lambda f: f.__name__.removeprefix("assert_"))
def test_leg(candidate: str, module: str, leg: object) -> None:
    result = leg(module)  # type: ignore[operator]
    assert result.passed, f"{candidate} failed {result.leg}: {result.detail}"


@requires_postgres
def test_negative_control_is_caught_by_leg_one() -> None:
    """The harness must fail a candidate that restores state but re-runs completed work.

    Without this, a passing leg 1 would only tell us that no candidate happened to trip it —
    which is not the same as the leg being able to detect the failure. `negative_control` is
    built to be wrong in exactly one way, so a green leg 1 here would mean the assertion is
    inert.

    Legs 2 and 4 are asserted to still pass, which is what distinguishes "leg 1 detects
    re-execution" from "this candidate is broken enough to trip anything."
    """
    module = "ireports_spike_harness.negative_control"

    leg1 = conformance.assert_leg1_durable_resume(module)
    assert not leg1.passed, (
        "leg 1 passed a candidate that re-executes completed work on resume; "
        "the assertion is not measuring what it claims to"
    )
    assert "re-executed" in leg1.detail or "ran 2 times" in leg1.detail, leg1.detail

    assert conformance.assert_leg2_human_interrupt(module).passed, (
        "leg 2 should still pass — the negative control interrupts and resumes correctly, "
        "it only gets durability wrong"
    )
    assert conformance.assert_leg4_bounded_fanout(module).passed


@requires_postgres
@pytest.mark.parametrize("candidate,module", sorted(CANDIDATES.items()))
def test_full_report(candidate: str, module: str) -> None:
    """Run all four legs together and print the report.

    Redundant with `test_leg` on purpose: the per-leg tests give a readable failure, and this
    gives the summary block that goes into the scorecard.
    """
    report = conformance.run_all(candidate, module)
    print("\n" + report.summary())
    assert report.passed, report.summary()
