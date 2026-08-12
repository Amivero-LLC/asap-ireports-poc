"""The scorecard — blueprint §9.4's dimensions, as a contract rather than a table someone types.

Making this a typed model matters for the same reason the conformance suite matters: the
bake-off's output is a *comparison*, and a comparison assembled by hand from three authors'
notes is not one. A candidate's row is either complete or it fails validation.

Fields split into three kinds:

- **Measured** — produced by tooling. `framework_lines_of_code`, `serialized_state_bytes`,
  `distributions`, `installed_megabytes`, `known_vulnerabilities`.
- **Observed** — produced by the conformance suite. The four leg results.
- **Judged** — a human's assessment, recorded with its reasoning. Kept explicitly separate so a
  reader can see which numbers are facts and which are opinions.

`developer_comprehension` is the honest one. Blueprint §9.4 asks for it after a short onboarding
exercise, and it will be the softest number on the page. It is retained because a framework the
program's team cannot reason about is a real risk, and omitting the dimension would not make
that risk go away — it would just make it undiscussable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from ireports_domain import ContractModel
from pydantic import Field, model_validator

ScorecardVersion = Literal["1.0.0"]
SCORECARD_VERSION: ScorecardVersion = "1.0.0"


class LegOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


class Judgement(StrEnum):
    """A deliberately coarse scale.

    Three levels, not ten. A finer scale on a subjective dimension invites false precision and
    lets a close call be settled by a rounding decision rather than by argument.
    """

    POOR = "poor"
    ADEQUATE = "adequate"
    GOOD = "good"


class LegScore(ContractModel):
    leg: str
    outcome: LegOutcome
    detail: str = Field(description="What happened, in one sentence. Required even on a pass.")


class MeasuredFootprint(ContractModel):
    """Tooling output. No judgement in this block."""

    framework_lines_of_code: int = Field(
        ge=0,
        description=(
            "Wiring only. Node bodies are shared via the harness scenario module, so this "
            "counts orchestration scaffolding and nothing else."
        ),
    )
    serialized_state_bytes: int = Field(
        ge=0, description="Size of one checkpoint at the human-review interrupt."
    )
    distributions: int = Field(ge=0, description="Installed distributions in a clean environment.")
    installed_megabytes: int = Field(ge=0)
    known_vulnerabilities: int = Field(
        ge=0, description="Open advisories against the pinned versions at scoring time."
    )
    cold_start_seconds: float | None = Field(
        default=None, description="Under SAM local. Null until the packaging leg is run."
    )


class JudgedQualities(ContractModel):
    """Human assessment. Each score carries its reasoning; a bare grade is not admissible."""

    budget_and_allowlist_enforcement: Judgement
    budget_and_allowlist_rationale: str
    state_inspectability: Judgement
    state_inspectability_rationale: str
    test_determinism: Judgement
    test_determinism_rationale: str
    developer_comprehension: Judgement
    developer_comprehension_rationale: str = Field(
        description="After the onboarding exercise. Name what was confusing, not just how it felt."
    )


class CandidateScore(ContractModel):
    """One candidate's complete row."""

    schema_version: ScorecardVersion = SCORECARD_VERSION
    candidate: str
    module: str
    framework_version: str = Field(description="Exact pinned version, so the row is reproducible.")

    legs: list[LegScore] = Field(min_length=4)
    footprint: MeasuredFootprint
    judged: JudgedQualities

    disqualifying_findings: list[str] = Field(
        default_factory=list,
        description=(
            "Anything that rules the candidate out regardless of its scores — a licence "
            "problem, an unfixable constraint conflict, an abandoned project."
        ),
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _all_four_legs_reported(self) -> CandidateScore:
        legs = {leg.leg for leg in self.legs}
        if len(legs) != len(self.legs):
            raise ValueError("a leg is reported more than once")
        if len(legs) < 4:
            raise ValueError("all four ADR-012 legs must be reported, including failures")
        return self

    @property
    def legs_passed(self) -> int:
        return sum(1 for leg in self.legs if leg.outcome is LegOutcome.PASSED)


class Scorecard(ContractModel):
    """The Milestone 1c deliverable.

    A recommendation is required, and so is `why_not_the_others`. ADR-001 makes the rejected
    candidates part of the handoff — a scorecard that records only the winner throws away the
    more useful half of the exercise.
    """

    schema_version: ScorecardVersion = SCORECARD_VERSION
    scored_on: str = Field(description="ISO date the bake-off was run.")
    candidates: list[CandidateScore] = Field(min_length=2)
    recommendation: str = Field(description="Candidate name.")
    recommendation_rationale: str
    why_not_the_others: dict[str, str] = Field(
        description="One entry per non-recommended candidate. Required, not optional."
    )

    @model_validator(mode="after")
    def _recommendation_is_defended(self) -> Scorecard:
        names = {c.candidate for c in self.candidates}
        if len(names) != len(self.candidates):
            raise ValueError("duplicate candidate names")
        if self.recommendation not in names:
            raise ValueError(f"recommendation {self.recommendation!r} is not among {sorted(names)}")
        missing = names - {self.recommendation} - set(self.why_not_the_others)
        if missing:
            raise ValueError(
                f"every rejected candidate needs a recorded reason; missing: {sorted(missing)}"
            )
        return self
