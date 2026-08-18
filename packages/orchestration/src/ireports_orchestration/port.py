"""This project's own orchestration interface — what an orchestrator is, and what it returns.

ADR-024 keeps custom Python and LangGraph both live until there is evidence to choose between
them. The protection against either becoming lock-in is that nodes depend on **this** interface
and never on a framework — easy to assert, and only meaningful because a second implementation
genuinely runs the same case and produces the same shape of answer.

Everything shared by both paths lives here: the `RunResult` they both return, the routing policy
they must not disagree about, and the fan-in that makes their outputs comparable. The two
implementations are `handrolled.py` and `langgraph_adapter.py`, and neither type appears outside
its own module — `registry.py` is the only place both are named.

**The fan-out width comes from the case** (`criteria_for`), not from a constant. That is what
makes this a comparison at all: a fixed-width fan-out is one line in any framework, so a fixed one
measures nothing. With the width decided at runtime the two implementations stop being the same
program — see `langgraph_adapter.py`, where it forces a different graph construction entirely.

The no-import rule is enforced rather than described: `test_no_analysis_module_imports_langgraph`
in `tests/orchestration/test_orchestration.py` fails if any module here except the adapter and the
registry grows a LangGraph reference.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from ireports_domain import BudgetConsumption, Budgets, ProposedFinding
from ireports_gateway.port import ModelGateway
from ireports_retrieval import Retriever

from .budget import DEFAULT_BUDGETS, BudgetBreach, BudgetLedger
from .case import LoadedCase
from .criteria import Criterion
from .specialist import SpecialistOutcome
from .synthesis import SynthesisOutcome

MAX_PARALLEL = int(os.environ.get("IREPORTS_MAX_PARALLEL", "3"))
"""Bounded fan-out. `Budgets.max_parallel_specialists` defaults to 4 and caps at 16; this mirrors
that rather than inventing a second concept. Unbounded fan-out over paid model calls is the
failure mode budgets exist to prevent."""


@dataclass(frozen=True)
class RunResult:
    """What one orchestration produced.

    Identical shape from both implementations — that is the point.
    """

    run_id: str
    candidate: str
    findings: tuple[ProposedFinding, ...]
    outcomes: tuple[SpecialistOutcome, ...]
    wall_seconds: float
    criteria: tuple[Criterion, ...] = ()
    """Which criteria this case actually selected. Recorded because the fan-out width is now
    runtime data — without it, a run of four specialists and a run of two are indistinguishable
    after the fact, and "why did this case get analysed differently" is unanswerable."""

    synthesis: SynthesisOutcome | None = None
    """The cross-criterion stage. None when it did not run (fewer than two findings to reason
    across)."""

    consumption: BudgetConsumption | None = None
    """What the run actually spent, as the published contract.

    Separate from the `total_tokens` property below, which sums what individual outcomes reported.
    Those two should agree; if they ever disagree, the ledger is right — it counts every model call
    that returned, including calls whose findings were then dropped by validation. Money spent is
    spent whether or not the finding survived."""

    breach: BudgetBreach | None = None
    """Which ceiling stopped the run early, if one did.

    `None` on a run that finished its work. A run that hit a ceiling still packages and delivers
    what it has — `RunStatus.INCOMPLETE_DUE_TO_BUDGET` routes to `PACKAGING`, not to `FAILED`,
    because a truncated analysis that silently vanishes is worse than one a reviewer can see is
    truncated."""

    @property
    def rejected(self) -> tuple[str, ...]:
        found = tuple(r for o in self.outcomes for r in o.rejected)
        return found + (self.synthesis.rejected if self.synthesis else ())

    @property
    def total_tokens(self) -> int:
        spent = sum(o.input_tokens + o.output_tokens for o in self.outcomes)
        if self.synthesis:
            spent += self.synthesis.input_tokens + self.synthesis.output_tokens
        return spent


class Orchestrator(Protocol):
    """The port. Neither implementation's type appears anywhere outside its own module."""

    name: str

    def run(
        self,
        case: LoadedCase,
        gateway: ModelGateway,
        retriever: Retriever,
        run_id: str,
        budgets: Budgets | None = None,
    ) -> RunResult: ...


def should_synthesize(outcomes: list[SpecialistOutcome]) -> bool:
    """Whether the second stage has anything to reason across.

    Shared by both paths deliberately: this is a *policy* decision about the run, and if each
    orchestrator decided it separately they would drift, and the drift would show up as two runs
    of the same case producing different envelopes for reasons nobody could see.

    Fewer than two findings cannot contradict each other, so the call would be paid for and
    guaranteed useless.
    """
    return sum(len(o.findings) for o in outcomes) >= 2


def join_and_sort(
    outcomes: list[SpecialistOutcome],
    synthesis: SynthesisOutcome | None = None,
) -> tuple[ProposedFinding, ...]:
    """Fan-in.

    Sorted by finding_id so that two implementations producing the same findings produce the same
    *order*, which is what makes their outputs comparable at all. An unordered join would make
    every diff noise.

    Synthesis findings join the same pool rather than living in a separate section: they are
    `ProposedFinding`s like any other, and giving them a privileged place in the envelope would
    imply they carry more weight than a specialist's. They do not.
    """
    seen: dict[str, ProposedFinding] = {}
    for outcome in outcomes:
        for finding in outcome.findings:
            seen.setdefault(finding.finding_id, finding)
    for finding in synthesis.findings if synthesis else ():
        seen.setdefault(finding.finding_id, finding)
    return tuple(sorted(seen.values(), key=lambda f: f.finding_id))


def new_ledger(budgets: Budgets | None) -> BudgetLedger:
    """One ledger per run, shared by every specialist in it.

    Both orchestrators call this rather than each constructing their own, for the reason
    `should_synthesize` is shared: a policy both paths implement separately is a policy they will
    eventually disagree about, and the disagreement shows up as two runs of the same case
    truncating differently.
    """
    return BudgetLedger(budgets or DEFAULT_BUDGETS)
