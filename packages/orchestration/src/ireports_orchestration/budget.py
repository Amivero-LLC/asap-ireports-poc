"""Ceilings that change what the run does, not just what it records.

**A budget that is only reported is not a budget.** The distinction this module exists to make is
between accounting — which the run already had, as token totals on `RunResult` — and control flow.
A ledger nobody consults before spending is a receipt.

Two reasons this matters here beyond cost.

*The stopping condition has to be code.* `CLAUDE.md`: the model reasons, it does not decide control
flow. An agentic system that influences its own control flow can loop indefinitely, and that rule
only holds while the thing that stops it is ordinary program logic the model has no say in.

*Lambda retries automatically.* The 15-minute ceiling kills the process mid-flight, and the
invocation is retried — re-paying for every model call already made. **The shell has to stop at its
own wall clock first, because that is the only moment it ever gets to checkpoint.** Without this
module, LAMB-01 is not buildable; with it, the checkpoint has a place to happen.

**What is enforced here, and what is not.** `Budgets` carries seven ceilings. Three are run-level
and live in this ledger: wall clock, input tokens, output tokens. The rest are already enforced
where they belong — `max_parallel_specialists` by the fan-out width, `max_evidence_per_node` by the
retrieval `k`, `max_model_calls_per_node` by the bounded retry in `analyze`.

**`Budgets` has no per-run model-call ceiling**, only a per-node one. With runtime fan-out width,
per-node ceilings do not bound a run: five criteria at five calls each is twenty-five calls, and
nothing in the contract says otherwise. Wall clock and tokens do bound it, so the gap is covered in
practice rather than by design. Adding `max_model_calls_per_run` is a contract change and wants an
ADR rather than a quiet field.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from ireports_domain import BudgetConsumption, Budgets


@dataclass(frozen=True)
class BudgetBreach:
    """Which ceiling stopped the run, and by how much.

    Carries the numbers because "the run stopped early" is not actionable and "the run stopped
    after 118.4s against a 120s wall-clock ceiling" is. A breach reaches the run's output, not a
    log — same reasoning as rejections.
    """

    ceiling: str
    limit: float
    reached: float

    def __str__(self) -> str:
        return (
            f"{self.ceiling} ceiling reached: {self.reached:,.1f} of {self.limit:,.0f} — "
            "remaining work was not attempted"
        )


class BudgetLedger:
    """Run-level consumption, and whether a ceiling has been crossed.

    **Thread-safe, and that is load-bearing rather than defensive.** The hand-rolled path fans out
    through a `ThreadPoolExecutor`, so several specialists record usage concurrently. An unlocked
    `+=` on a shared int is the kind of race that produces a total that is quietly slightly wrong,
    which for a spend figure is worse than one that is obviously wrong.

    The clock is injectable so that a test can prove early termination without sleeping through a
    real ceiling. It defaults to `time.monotonic`, never wall-clock time: elapsed measurement must
    not move when the system clock does.
    """

    def __init__(self, budgets: Budgets, clock: Callable[[], float] = time.monotonic) -> None:
        self._budgets = budgets
        self._clock = clock
        self._started = clock()
        self._lock = Lock()
        self._model_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._first_breach: BudgetBreach | None = None

    @property
    def budgets(self) -> Budgets:
        return self._budgets

    def elapsed_seconds(self) -> float:
        return self._clock() - self._started

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """One model call's usage. Called after the call returns, by whoever made it."""
        with self._lock:
            self._model_calls += 1
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens

    def consumption(self) -> BudgetConsumption:
        """What the run actually spent, as the published contract.

        `tool_calls` stays zero because a specialist has no tool surface — see SPEC-01, whose
        allowlist clause is vacuous for the same reason. Reporting a fabricated count would be
        worse than reporting the truth that there is nothing to count.
        """
        with self._lock:
            return BudgetConsumption(
                model_calls=self._model_calls,
                tool_calls=0,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                wall_clock_seconds=self.elapsed_seconds(),
            )

    def breach(self) -> BudgetBreach | None:
        """The first ceiling crossed, or `None`.

        **Checked before spending, never after.** A ceiling consulted only once the call has
        returned records an overspend rather than preventing one.

        Wall clock is checked first deliberately: it is the ceiling that has to fire before
        Lambda's does, and reporting a token breach when the real problem is elapsed time would
        send someone to tune the wrong number.

        **The first breach is remembered and returned forever after, and that is not a cache.**
        This is asked many times during a run — once per criterion, again before synthesis, again
        when the result is assembled — and a freshly measured wall clock answers a different
        question each time. A run once reported `18.5 of 10` on its skipped criteria and
        `34.4 of 10` in its summary, in the same payload, for the same event. One fact, two
        numbers, and a reader has no way to tell which is the one that stopped the work. The
        remembered breach is the moment work stopped; elapsed time keeps running afterwards and is
        available from `consumption()`, where it means what it says.
        """
        with self._lock:
            if self._first_breach is not None:
                return self._first_breach

        found: BudgetBreach | None = None
        elapsed = self.elapsed_seconds()
        if elapsed >= self._budgets.max_wall_clock_seconds:
            found = BudgetBreach("wall_clock", self._budgets.max_wall_clock_seconds, elapsed)
        else:
            with self._lock:
                if self._input_tokens >= self._budgets.max_input_tokens:
                    found = BudgetBreach(
                        "input_tokens", self._budgets.max_input_tokens, self._input_tokens
                    )
                elif self._output_tokens >= self._budgets.max_output_tokens:
                    found = BudgetBreach(
                        "output_tokens", self._budgets.max_output_tokens, self._output_tokens
                    )
        if found is None:
            return None
        with self._lock:
            # Two threads can cross the line together; whichever records first wins, so every
            # subsequent reader — and every rejection line — quotes the same numbers.
            if self._first_breach is None:
                self._first_breach = found
            return self._first_breach


DEFAULT_BUDGETS = Budgets(
    max_input_tokens=400_000,
    max_output_tokens=200_000,
    max_wall_clock_seconds=780,
)
"""What a run gets when the caller does not say.

`Budgets` has no defaults for these three, correctly — a ceiling nobody chose is a ceiling nobody
owns. But an orchestrator needs *some* number, and refusing to run without one would make budgets
a configuration burden rather than a safety net.

**780 seconds is the only number here with a hard reason.** The Lambda function's timeout is 900
(`template.yaml`), and the shell must stop before the platform does — that is the whole point.
Two minutes of headroom is enough to checkpoint and return, and when checkpointing exists (ORCH-02)
this is the number it will depend on.

The token ceilings are judgements sized against observed runs: a 35,000-token case costs roughly
70k input and 26k output, so these allow several such runs before firing. They are a backstop
against a loop, not a cost-control mechanism, and tuning them against three cases would be fitting
noise.
"""
