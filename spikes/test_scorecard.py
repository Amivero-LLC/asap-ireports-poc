"""The scorecard is a contract, so the suite checks it like one.

Importing `bakeoff_scorecard` already validates it — `Scorecard` refuses a candidate missing a
leg, a judged score without a rationale, or a recommendation that does not carry a recorded reason
for every candidate it beat. These tests exist so that guarantee runs in CI rather than only when
somebody happens to import the module, and so the published JSON cannot silently drift from the
Python that produced it.

No PostgreSQL needed: this asserts on the record of the bake-off, not on the bake-off.
"""

from __future__ import annotations

import json

from bakeoff_scorecard import OUTPUT, SCORECARD
from ireports_spike_harness.scorecard import LegOutcome, Scorecard
from test_conformance import CANDIDATES


def test_every_candidate_that_ran_has_a_row() -> None:
    """The scorecard covers exactly the candidates the conformance suite drives.

    Catches the failure mode where a candidate is added, passes its legs, and never reaches the
    deliverable — which is how a bake-off quietly becomes a comparison of two things.
    """
    assert {c.candidate for c in SCORECARD.candidates} == set(CANDIDATES)
    assert {c.module for c in SCORECARD.candidates} == set(CANDIDATES.values())


def test_all_four_legs_are_reported_for_every_candidate() -> None:
    for candidate in SCORECARD.candidates:
        assert len(candidate.legs) == 4, candidate.candidate
        assert candidate.legs_passed == 4, candidate.candidate
        assert all(leg.outcome is LegOutcome.PASSED for leg in candidate.legs)


def test_no_candidate_was_disqualified() -> None:
    """Recorded explicitly: none of the three was ruled out on a licence, a constraint conflict,
    or an abandoned project. The recommendation is a preference among viable options, and the
    scorecard should not be readable as anything stronger."""
    for candidate in SCORECARD.candidates:
        assert candidate.disqualifying_findings == [], candidate.candidate


COLD_START_CEILING_SECONDS = 3.0
"""The point at which LangGraph's import cost would be worth re-arguing.

Not a performance budget — a tripwire on the *recorded reference figure*, not on live timing. At
roughly 1.6-2.3s against a hand-rolled control of ~0.5s, LangGraph costs one to two seconds of
extra cold start, on a workload where a single specialist model call runs tens of seconds and cold
starts happen on scale-up rather than per request. That is affordable. At 3s it stops being
obviously affordable and the ADR-012 trade deserves a fresh look.

**The stored figure is a low-load reference, not a stable constant.** Repeat runs on a loaded
machine produced LangGraph medians up to 2.3s and individual samples to 5.8s. If you re-measure
and record a higher number, that is the measurement being noisy before it is the dependency tree
getting heavier — check host load before concluding anything.
"""


def test_cold_start_is_measured_and_within_the_ceiling() -> None:
    """The gap ARCH-03 left open, now closed — and kept from silently reopening.

    This test previously asserted `cold_start_seconds is None`, so that recording any figure would
    fail the suite and force the ADR-012 recommendation to be re-read against it. That has now
    happened: `spikes/lambda_fit/` measures import cost under SAM local, the figures are in the
    scorecard, and the recommendation was re-examined and stands (ADR-023).

    The test's job flips accordingly. It no longer guards an absence; it guards the conclusion.
    """
    for candidate in SCORECARD.candidates:
        measured = candidate.footprint.cold_start_seconds
        assert measured is not None, (
            f"{candidate.candidate} has no cold-start figure. ARCH-03 is closed and every "
            "candidate is expected to carry one; regenerate with spikes/lambda_fit/."
        )
        assert measured < COLD_START_CEILING_SECONDS, (
            f"{candidate.candidate} cold start is {measured}s, at or above the "
            f"{COLD_START_CEILING_SECONDS}s ceiling. Re-read the ADR-012 recommendation against "
            "this number before raising the ceiling — that trade was decided at ~1.5s."
        )


def test_langgraph_is_not_disproportionately_heavier_than_the_control() -> None:
    """The specific comparison ADR-012 turns on, asserted rather than remembered.

    ADR-012 chose LangGraph on cost, not correctness — all three candidates passed all four legs.
    Dependency weight was the open risk, and a Lambda cold start is where weight is felt. If that
    ratio grows materially, the reasoning behind the choice is worth revisiting.
    """
    by_name = {c.candidate: c.footprint.cold_start_seconds for c in SCORECARD.candidates}
    control = by_name.get("hand-rolled")
    langgraph = by_name.get("langgraph")
    assert control and langgraph, sorted(by_name)
    ratio = langgraph / control
    assert ratio < 5.0, (
        f"LangGraph imports {ratio:.1f}x slower than the hand-rolled control. Observed range at "
        "the time of ADR-023 was 2.8x-4.0x across runs, so this tripwire has less headroom than "
        "it looks: a reading past 5x is more likely a contended host than a real regression. "
        "Check load, re-measure interleaved, and only then re-argue ADR-012."
    )


def test_published_json_matches_the_python() -> None:
    """The handoff artifact is regenerated, not hand-edited.

    Regenerate with: uv run python spikes/bakeoff_scorecard.py
    """
    assert OUTPUT.exists(), f"{OUTPUT} missing; run: uv run python spikes/bakeoff_scorecard.py"
    published = Scorecard.model_validate(json.loads(OUTPUT.read_text()))
    assert published == SCORECARD, (
        "docs/handoff/orchestration-scorecard.json is stale; regenerate it with "
        "`uv run python spikes/bakeoff_scorecard.py`"
    )
