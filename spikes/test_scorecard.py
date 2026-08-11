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


def test_cold_start_is_null_and_stays_visible() -> None:
    """The largest gap in the scorecard, asserted so it cannot be forgotten quietly.

    When the SAM local packaging leg is run, this test fails and forces the recommendation to be
    re-examined against the new number rather than left standing by default.
    """
    for candidate in SCORECARD.candidates:
        assert candidate.footprint.cold_start_seconds is None, (
            f"{candidate.candidate} now has a cold-start measurement; re-read the ADR-012 "
            "recommendation against it before updating this test"
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
