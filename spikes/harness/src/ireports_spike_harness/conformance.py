"""The four legs, asserted identically against every candidate.

ADR-012 scores candidates on dimensions that only mean something if each candidate did the same
thing. This module is that guarantee: one implementation of the four legs, driven through the
CLI contract in `port.py`, applied unchanged to every spike.

The legs, and what each is really asking:

1. **Durable checkpoint and resume in a separate process.** Not "can state be reloaded" but
   *did completed work stay completed*. Measured against the gateway's durable call log, which
   is written outside the framework and cannot be influenced by it.
2. **Human-in-the-loop interrupt.** The run must stop with proposals in hand, accept a
   disposition recorded out of band, and finish. ADR-011 makes this a state transition with no
   bypass, so a candidate that cannot pause here cannot implement the architecture at all.
3. **Timeout survival.** A simulated gateway timeout must not lose or duplicate completed work.
4. **Bounded parallel fan-out, join, de-duplicate.**

Leg 1 is the one the landscape scan singled out. `docs/handoff/orchestration-landscape.md` §5.2
records an unconfirmed third-party claim that Strands restores *conversation* rather than
resuming *execution*; `assert_leg1_durable_resume` is how that claim gets settled with evidence
instead of citation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from ireports_domain import (
    DispositionKind,
    HumanDisposition,
    ProposedFinding,
    ReasonCode,
    ReviewerRole,
    RunStatus,
)

from . import gateway as gw
from . import port, scenario


@dataclass
class LegResult:
    leg: str
    passed: bool
    detail: str
    measurements: Mapping[str, object] = field(default_factory=dict)


@dataclass
class ConformanceReport:
    candidate: str
    legs: list[LegResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(leg.passed for leg in self.legs)

    def summary(self) -> str:
        lines = [f"{self.candidate}: {'PASS' if self.passed else 'FAIL'}"]
        for leg in self.legs:
            lines.append(f"  [{'ok' if leg.passed else 'XX'}] {leg.leg} — {leg.detail}")
        return "\n".join(lines)


def _dispositions_for(findings: tuple[ProposedFinding, ...]) -> list[dict[str, object]]:
    """Record an accept-and-release disposition for every proposal.

    Built here rather than inside a candidate so that the review step is genuinely *out of
    band* — the disposition arrives as data from outside the orchestrator, which is what
    ADR-011 describes and what a real officer action would look like.
    """
    dispositions = []
    for index, finding in enumerate(findings):
        disposition = HumanDisposition(
            disposition_id=f"dsp_{index:04d}",
            finding_id=finding.finding_id,
            run_id=finding.run_id,
            reviewer_id="officer-42",
            reviewer_role=ReviewerRole.AUTHORIZED_ADJUDICATIVE_OFFICER,
            reviewed_at=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
            disposition=DispositionKind.ACCEPTED,
            reason_codes=[ReasonCode.ACCURATE_AS_PROPOSED],
            reviewer_summary="Accurate as proposed; released for the spike.",
            release_to_asap=True,
        )
        dispositions.append(json.loads(disposition.model_dump_json()))
    return dispositions


def _fresh(leg: str) -> tuple[str, gw.StubModelGateway]:
    """A run id no previous execution can have used, and an observer scoped to it.

    Unique per invocation rather than a fixed `run_leg1`. Fixed ids leak durable state between
    executions — a leg that ended in `delivered` leaves a checkpoint that the next execution
    resumes into, and the candidate correctly refuses an illegal transition. That failure looks
    exactly like a candidate defect and is entirely the harness's fault.

    Uniqueness also means legs can run concurrently and that a failed run's rows survive for
    inspection instead of being truncated by the next one.
    """
    gw.init_schema()
    run_id = f"run_{leg}_{uuid4().hex[:12]}"
    return run_id, gw.StubModelGateway(run_id)


# ---------------------------------------------------------------------------
# Leg 1 — durable checkpoint and resume in a separate process
# ---------------------------------------------------------------------------


def assert_leg1_durable_resume(module: str) -> LegResult:
    """Crash after the first specialist, restart, and check what re-executed.

    The assertion that matters is `specialist_suitability == 1`. A candidate that reloads state
    and re-runs the finished specialist will show 2, and that is the difference between durable
    execution and restored conversation — invisible in any documentation, obvious here.
    """
    run_id, observer = _fresh("leg1")

    first = port.invoke(
        module, "start", "--run-id", run_id, "--crash-after", "specialist_suitability"
    )
    if not first.crashed:
        return LegResult(
            leg="1-durable-resume",
            passed=False,
            detail=(
                f"expected a hard crash (exit {port.CRASH_EXIT_CODE}), got {first.returncode}. "
                f"stderr:\n{first.stderr}"
            ),
        )

    calls_before = observer.call_counts()
    crashed_pids = observer.distinct_processes()

    second = port.invoke(module, "start", "--run-id", run_id)
    outcome = second.outcome()
    calls_after = observer.call_counts()
    all_pids = observer.distinct_processes()

    measurements = {
        "calls_before_crash": calls_before,
        "calls_after_resume": calls_after,
        "distinct_processes": len(all_pids),
    }

    if len(all_pids) < 2 or not (all_pids - crashed_pids):
        return LegResult(
            leg="1-durable-resume",
            passed=False,
            detail="resume did not run in a new process; leg 1 was not actually exercised",
            measurements=measurements,
        )

    repeated = calls_after.get("specialist_suitability", 0)
    if repeated != 1:
        return LegResult(
            leg="1-durable-resume",
            passed=False,
            detail=(
                f"specialist_suitability ran {repeated} times across the crash. "
                "Completed work was re-executed: this is conversation restore, not execution "
                "resume."
            ),
            measurements=measurements,
        )

    if outcome.status is not RunStatus.AWAITING_HUMAN_REVIEW:
        return LegResult(
            leg="1-durable-resume",
            passed=False,
            detail=f"resumed run reached {outcome.status.value!r}, expected awaiting_human_review",
            measurements=measurements,
        )

    if len(outcome.proposed_findings) != scenario.EXPECTED_FINDING_COUNT:
        return LegResult(
            leg="1-durable-resume",
            passed=False,
            detail=(
                f"resumed run produced {len(outcome.proposed_findings)} findings, expected "
                f"{scenario.EXPECTED_FINDING_COUNT}; work was lost or duplicated across the crash"
            ),
            measurements=measurements,
        )

    return LegResult(
        leg="1-durable-resume",
        passed=True,
        detail="completed work survived a hard crash and was not re-executed",
        measurements=measurements,
    )


# ---------------------------------------------------------------------------
# Leg 2 — human-in-the-loop interrupt
# ---------------------------------------------------------------------------


def assert_leg2_human_interrupt(module: str) -> LegResult:
    """Pause with proposals, take a disposition from outside, finish in a third process."""
    run_id, observer = _fresh("leg2")

    started = port.invoke(module, "start", "--run-id", run_id).outcome()
    if started.status is not RunStatus.AWAITING_HUMAN_REVIEW:
        return LegResult(
            leg="2-human-interrupt",
            passed=False,
            detail=f"start reached {started.status.value!r}, expected a pause for review",
        )
    if started.envelope is not None:
        return LegResult(
            leg="2-human-interrupt",
            passed=False,
            detail="an envelope was produced before any disposition was recorded (ADR-011)",
        )

    dispositions = _dispositions_for(started.proposed_findings)
    resumed = port.invoke(
        module, "resume", "--run-id", run_id, "--dispositions", json.dumps(dispositions)
    ).outcome()

    if resumed.envelope is None:
        return LegResult(
            leg="2-human-interrupt",
            passed=False,
            detail="resume after disposition produced no envelope",
        )
    if resumed.status is not RunStatus.DELIVERED:
        return LegResult(
            leg="2-human-interrupt",
            passed=False,
            detail=f"resumed run reached {resumed.status.value!r}, expected delivered",
        )

    specialist_calls = sum(
        count for node, count in observer.call_counts().items() if node.startswith("specialist_")
    )
    if specialist_calls != len(scenario.SPECIALIST_NODES):
        return LegResult(
            leg="2-human-interrupt",
            passed=False,
            detail=(
                f"{specialist_calls} specialist calls across the interrupt, expected "
                f"{len(scenario.SPECIALIST_NODES)}; the pause re-ran analysis"
            ),
            measurements={"call_counts": observer.call_counts()},
        )

    return LegResult(
        leg="2-human-interrupt",
        passed=True,
        detail="paused for review, accepted an out-of-band disposition, delivered on resume",
        measurements={
            "call_counts": observer.call_counts(),
            "distinct_processes": len(observer.distinct_processes()),
        },
    )


# ---------------------------------------------------------------------------
# Leg 3 — survive a simulated model timeout
# ---------------------------------------------------------------------------


def assert_leg3_timeout_survival(module: str) -> LegResult:
    """Arm a one-shot timeout on one specialist; the run must still complete correctly.

    Two failure shapes are being separated here. Losing the *other* specialist's completed work
    is a checkpointing failure. Producing extra findings is a duplication failure. Both look
    like "it survived" if you only check that the process exited zero.
    """
    run_id, observer = _fresh("leg3")
    observer.arm_timeout("specialist_national_security")

    result = port.invoke(module, "start", "--run-id", run_id)
    if result.returncode != 0:
        # A candidate with no retry may need a second invocation; the fault is one-shot and
        # already fired, so this second attempt is the "resume after transient failure" path.
        result = port.invoke(module, "start", "--run-id", run_id)
        if result.returncode != 0:
            return LegResult(
                leg="3-timeout-survival",
                passed=False,
                detail=f"did not recover from a one-shot timeout.\nstderr:\n{result.stderr}",
                measurements={"call_counts": observer.call_counts()},
            )

    outcome = result.outcome()
    counts = observer.call_counts()
    measurements = {"call_counts": counts}

    if len(outcome.proposed_findings) != scenario.EXPECTED_FINDING_COUNT:
        return LegResult(
            leg="3-timeout-survival",
            passed=False,
            detail=(
                f"produced {len(outcome.proposed_findings)} findings, expected "
                f"{scenario.EXPECTED_FINDING_COUNT}; the timeout lost or duplicated work"
            ),
            measurements=measurements,
        )

    if counts.get("specialist_suitability", 0) != 1:
        return LegResult(
            leg="3-timeout-survival",
            passed=False,
            detail=(
                "the unaffected specialist re-ran while recovering from the other's timeout; "
                "completed work was discarded"
            ),
            measurements=measurements,
        )

    return LegResult(
        leg="3-timeout-survival",
        passed=True,
        detail="recovered from a one-shot timeout without losing or duplicating completed work",
        measurements=measurements,
    )


# ---------------------------------------------------------------------------
# Leg 4 — bounded parallel fan-out, join, de-duplicate
# ---------------------------------------------------------------------------


def assert_leg4_bounded_fanout(module: str) -> LegResult:
    """Both specialists run exactly once; the join de-duplicates without losing an authority."""
    run_id, observer = _fresh("leg4")

    outcome = port.invoke(module, "start", "--run-id", run_id).outcome()
    counts = observer.call_counts()
    measurements = {"call_counts": counts}

    for node in scenario.SPECIALIST_NODES:
        if counts.get(node, 0) != 1:
            return LegResult(
                leg="4-bounded-fanout",
                passed=False,
                detail=f"{node} ran {counts.get(node, 0)} times, expected exactly 1",
                measurements=measurements,
            )

    findings = outcome.proposed_findings
    if len(findings) != scenario.EXPECTED_FINDING_COUNT:
        return LegResult(
            leg="4-bounded-fanout",
            passed=False,
            detail=(
                f"join produced {len(findings)} findings, expected "
                f"{scenario.EXPECTED_FINDING_COUNT} (one duplicate must be removed)"
            ),
            measurements=measurements,
        )

    domains = {f.authority.decision_domain for f in findings}
    if len(domains) != 2:
        return LegResult(
            leg="4-bounded-fanout",
            passed=False,
            detail=(
                f"join collapsed authorities: {sorted(d.value for d in domains)}. The same "
                "conduct under two authorities must survive as two findings (blueprint §2.1)"
            ),
            measurements=measurements,
        )

    ids = [f.finding_id for f in findings]
    if ids != sorted(ids):
        return LegResult(
            leg="4-bounded-fanout",
            passed=False,
            detail="join output is not deterministically ordered",
            measurements=measurements,
        )

    return LegResult(
        leg="4-bounded-fanout",
        passed=True,
        detail="both specialists ran once; join de-duplicated while preserving both authorities",
        measurements=measurements,
    )


LEGS = (
    assert_leg1_durable_resume,
    assert_leg2_human_interrupt,
    assert_leg3_timeout_survival,
    assert_leg4_bounded_fanout,
)


def run_all(candidate: str, module: str) -> ConformanceReport:
    return ConformanceReport(candidate=candidate, legs=[leg(module) for leg in LEGS])
