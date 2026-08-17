"""The scorer's own guards. **A wrong scorer is worse than no scorer.**

A check that cannot fire is indistinguishable from a check that passes, and a board of green
lines that cannot go red is the most expensive artifact this project could produce — it is the
silent-under-analysis failure, one level up, aimed at the people reviewing the system rather than
the people reviewing the case.

So every check gets a negative control: a crafted run that must make it fail. `test_every_check_
has_a_failing_example` asserts the set of controls covers the set of checks, which means adding a
check without a control is itself a test failure. The same mechanism `tests/architecture/
test_build_state_table.py` uses, for the same reason it needed it.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from evals.scorers.properties import (
    SINGLE_RUN_CHECKS,
    Check,
    citations_resolve,
    classification_is_not_a_constant,
    every_criterion_is_accounted_for,
    excerpt_integrity,
    score_run,
    synthesis_state_is_unambiguous,
)

TEXT = "Section 20A: Subject answered 'No' to holding any financial interest in a foreign business."


def _excerpt(evidence_id: str = "ev_001", text: str = TEXT) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "excerpt": text,
        "truncated": False,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "document_reference": "synthetic://CASE/doc_001",
        "page_number": 1,
    }


def _finding(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "finding_id": "fnd_run_x_GUIDELINE_B_0",
        "criterion_id": "GUIDELINE-B",
        "classification": "potential_issue",
        "title": "Foreign family contact reported in the questionnaire",
        "observation": "The record shows regular contact with a parent residing abroad [ev_001].",
        "policy_relevance": "Contact with foreign nationals may be relevant to this criterion.",
        "recommended_officer_action": "Review the reported contact and confirm its frequency.",
        "supporting_evidence": [_excerpt()],
        "mitigating_evidence": [],
        "contradicting_evidence": [],
    }
    base.update(overrides)
    return base


def _run(**overrides: Any) -> dict[str, Any]:
    """A well-formed modern run. Every negative control below is this, with one thing broken."""
    base: dict[str, Any] = {
        "case_id": "CASE-A",
        "run_id": "run_x",
        "candidate": "hand-rolled",
        "findings": 1,
        "not_analysed": [],
        "rejected": [],
        "criteria": [
            {
                "criterion_id": "GUIDELINE-B",
                "status": "completed",
                "retrieved": ["ev_001"],
                "findings": 1,
                "rejected": 0,
            }
        ],
        "synthesis": {"ran": True, "failed": False, "findings": 0, "rejected": [], "overlaps": []},
        "envelope": {"analysis": {"findings": [_finding()]}},
    }
    base.update(overrides)
    return base


def _by_name(checks: list[Check], name: str) -> Check:
    return next(c for c in checks if c.name == name)


# ---------------------------------------------------------------------------
# A healthy run is green
# ---------------------------------------------------------------------------


def test_a_well_formed_run_passes_everything() -> None:
    """The baseline. If this ever fails, the controls below prove nothing."""
    checks = score_run(_run(), {"ev_001": TEXT})
    failures = [c for c in checks if not c.passed]
    assert not failures, [(c.name, c.detail) for c in failures]
    assert not [c for c in checks if c.skipped], "nothing should be skipped on a modern run"


# ---------------------------------------------------------------------------
# Negative controls — one per check
# ---------------------------------------------------------------------------

BAD_RUNS: dict[str, dict[str, Any]] = {
    "citations_resolve": _run(
        envelope={
            "analysis": {"findings": [_finding(supporting_evidence=[_excerpt("ev_999")])]},
        }
    ),
    "no_determinative_language": _run(
        envelope={
            "analysis": {
                "findings": [
                    _finding(
                        policy_relevance="The record shows the subject violated SEAD-4 Guideline B."
                    )
                ]
            }
        }
    ),
    "no_aggregate_score": _run(
        envelope={"analysis": {"findings": [_finding()], "overall_risk_score": 7}}
    ),
    "rejections_are_bounded": _run(rejected=[f"reason {i}" for i in range(4547)]),
    "every_criterion_is_accounted_for": _run(
        criteria=[
            {"criterion_id": "GUIDELINE-B", "status": "refused", "retrieved": [], "rejected": 0}
        ],
        not_analysed=[],
    ),
    "one_role_per_span": _run(
        envelope={
            "analysis": {
                "findings": [
                    _finding(supporting_evidence=[_excerpt()], mitigating_evidence=[_excerpt()])
                ]
            }
        }
    ),
    "synthesis_state_is_unambiguous": _run(synthesis={"findings": 0, "rejected": []}),
    "excerpt_integrity": _run(
        envelope={
            "analysis": {
                "findings": [_finding(supporting_evidence=[_excerpt(text="not the source text")])]
            }
        }
    ),
}


@pytest.mark.parametrize("name", sorted(BAD_RUNS))
def test_every_check_has_a_failing_example(name: str) -> None:
    """No check may be dead code.

    A check computed and never asserted is the shape of bug that made
    `test_build_state_table.py` grow the same guard: five of its nine categories matched no
    assertion and were thrown away silently.
    """
    check = _by_name(score_run(BAD_RUNS[name], {"ev_001": TEXT}), name)
    assert not check.passed, f"{name} did not fire on its negative control: {check.detail}"
    assert not check.skipped, f"{name} skipped instead of failing"
    assert check.incident, f"{name} does not say which incident it descends from"


def test_the_controls_cover_every_single_run_check() -> None:
    """Adding a check without a negative control is itself a failure."""
    covered = set(BAD_RUNS)
    implemented = {c.__name__ for c in SINGLE_RUN_CHECKS} | {"excerpt_integrity"}
    assert covered == implemented, {
        "checks with no control": sorted(implemented - covered),
        "controls for unknown checks": sorted(covered - implemented),
    }


# ---------------------------------------------------------------------------
# Skip is not pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("check", "name"),
    [
        (citations_resolve, "citations_resolve"),
        (every_criterion_is_accounted_for, "every_criterion_is_accounted_for"),
        (synthesis_state_is_unambiguous, "synthesis_state_is_unambiguous"),
    ],
)
def test_a_run_predating_a_field_is_skipped_not_failed(check: Any, name: str) -> None:
    """The distinction that took the board from 25 red lines to 5.

    The earliest saved runs predate retrieval, per-criterion status, and the synthesis stage.
    Scoring those as violations buries the two lines that mean "this is wrong" among twenty that
    mean "this file is old" — the same readability failure as the 4,547 rejections.
    """
    ancient = _run(criteria=[{"criterion_id": "GUIDELINE-B", "findings": 1}], synthesis=None)
    result = check(ancient) if check is not citations_resolve else check(ancient, None)
    assert result.skipped, f"{name} should be skipped on a run that predates its field"
    assert "not applicable" in result.detail


def test_a_skipped_check_is_never_counted_as_a_pass() -> None:
    """`skipped` carries `passed=True` so callers need not special-case it, and every caller must
    still exclude it from a green count. Asserted here so the convention is not merely documented.
    """
    ancient = _run(criteria=[{"criterion_id": "GUIDELINE-B", "findings": 1}], synthesis=None)
    checks = score_run(ancient, None)
    genuinely_green = [c for c in checks if c.passed and not c.skipped]
    assert any(c.skipped for c in checks)
    assert all(not c.skipped for c in genuinely_green)


def test_excerpt_integrity_skips_rather_than_faking_a_pass() -> None:
    """A check with nothing to compare against must say so, not report success."""
    result = excerpt_integrity(_run(), None)
    assert result.skipped
    assert "no case text" in result.detail


# ---------------------------------------------------------------------------
# The corpus check — the one a single run cannot make about itself
# ---------------------------------------------------------------------------


def test_a_constant_classification_is_caught_across_cases() -> None:
    """The 2026-08-17 bug, caught mechanically and for free.

    Each run in isolation looks fine — `potential_issue` is a legitimate classification. Only the
    corpus shows that no other value is ever reachable. This needs no ground truth, no model call,
    and no expected output; it needs more than one case.
    """
    runs = [_run(case_id="CASE-A"), _run(case_id="CASE-B")]
    result = classification_is_not_a_constant(runs)
    assert not result.passed
    assert "hard-coded" in result.detail


def test_one_case_is_inconclusive_rather_than_failing() -> None:
    """A corpus of one cannot distinguish a constant from a record that only warranted one value.

    Reporting that as a failure would train people to ignore it, which is how a check dies.
    """
    result = classification_is_not_a_constant([_run(case_id="CASE-A")])
    assert result.passed
    assert "inconclusive" in result.detail


def test_a_varied_corpus_passes() -> None:
    varied = [
        _run(case_id="CASE-A"),
        _run(
            case_id="CASE-B",
            envelope={
                "analysis": {
                    "findings": [
                        _finding(
                            finding_id="fnd_run_x_GUIDELINE_B_1",
                            classification="mitigating_information",
                        )
                    ]
                }
            },
        ),
    ]
    assert classification_is_not_a_constant(varied).passed


def test_synthesis_findings_do_not_mask_a_constant_specialist() -> None:
    """Synthesis emits exactly two classifications by construction.

    Counting them would make the corpus look varied while every specialist finding stayed stuck on
    one value — the check would pass on precisely the corpus that exposed the bug.
    """
    runs = [
        _run(case_id="CASE-A"),
        _run(
            case_id="CASE-B",
            run_id="run_x",
            envelope={
                "analysis": {
                    "findings": [
                        _finding(),
                        _finding(
                            finding_id="fnd_run_x_syn_contra_0", classification="contradiction"
                        ),
                    ]
                }
            },
        ),
    ]
    result = classification_is_not_a_constant(runs)
    assert not result.passed, "synthesis classifications masked a constant specialist"
