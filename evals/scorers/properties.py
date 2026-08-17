"""Invariants that hold for any correct run, checked without ground truth.

**Every check here descends from a bug that actually happened.** That is the selection rule, and it
is what separates this from a wishlist of things one could assert. A check nobody has ever needed
is a check nobody maintains; a check that would have caught a real incident earns its place and
keeps earning it.

- `citations_resolve` — a model citing evidence it was never shown. A lucky hallucination is
  indistinguishable from analysis unless the check is scoped to the retrieved set.
- `no_determinative_language` — the prompt asks and the type enforces; this re-asks at the
  envelope, which is the artifact that actually ships.
- `no_aggregate_score` — ADR-014. No risk level, no ranking, no total, under any name.
- `classification_is_not_a_constant` — 2026-08-17: every finding on a clean record labelled
  `potential_issue`, because the specialist hard-coded it and the schema never asked.
- `rejections_are_bounded` — 2026-08-12: 4,547 one-character rejections, from a JSON string
  parsed as an array.
- `every_criterion_is_accounted_for` — "completed with no findings" and "refused" must never
  look alike.
- `excerpt_integrity` — an excerpt whose hash does not match its source cites something that no
  longer exists.
- `one_role_per_span` — models routinely cite one span as both supporting and mitigating.
- `synthesis_state_is_unambiguous` — a stage that ran and failed, reported as "skipped — nothing
  to reason across".

**These are necessary, not sufficient.** Passing every one of them says the run is well-formed and
internally honest. It says nothing about whether the analysis is *right* — that needs ground truth
(`agreement.py`) or a rubric. A green board here is the floor, not the ceiling, and reading it as
the ceiling would be its own version of the failure this project is built against.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from ireports_domain import reject_determinative_language

MAX_REASONABLE_REJECTIONS = 60
"""Above this, a run is reporting a malformed *response shape*, not a record with that many
problems. The orchestration caps its own lists at 50 plus a summary line; this sits just above that
so the check fires on an uncapped path rather than on the cap working."""

SCORE_LIKE = re.compile(
    r"(risk[_ ]?(score|level|rating)|overall[_ ]?(score|rating|assessment)|"
    r"total[_ ]?score|composite|rank(ing)?|severity[_ ]?score|priority[_ ]?score)",
    re.IGNORECASE,
)
"""Names an aggregate would plausibly hide behind.

Deliberately matches on *field names*, not on narrative text — an observation may legitimately
quote a credit score from the record.

**No word-boundary anchors, and that is the fix rather than the oversight.** The first version
anchored each alternative and did not fire on `overall_risk_score`: an underscore is a word
character, so there is no boundary between `overall_` and `risk`, and the one field name an
aggregate is most likely to use was the one it could not see. Its own negative control caught it.
"""


@dataclass(frozen=True)
class Check:
    """One question, answered, with enough detail to act on a failure.

    Three outcomes, not two. **A check that cannot tell "violated" from "not applicable" produces
    a board nobody reads** — which is the same failure as the 4,547 rejections one layer up. The
    saved runs span several weeks of schema change: the earliest predate retrieval, per-criterion
    status, and the synthesis stage entirely. Scoring those as failures would put twenty-odd red
    lines on the board that mean "this file is old", and the two lines that mean "this is wrong"
    would be unfindable among them.
    """

    name: str
    passed: bool
    detail: str
    incident: str
    """The bug this check descends from. Present so that a check can be *retired* honestly: if the
    incident is impossible by construction now, say so and delete it, rather than accumulating
    assertions nobody understands the reason for."""

    skipped: bool = False
    """Not applicable to this run — the field it inspects did not exist when the run was made.
    Never counted as a pass; a skipped check has told you nothing."""

    @property
    def mark(self) -> str:
        if self.skipped:
            return "SKIP"
        return "PASS" if self.passed else "FAIL"


def _skip(name: str, incident: str, why: str) -> Check:
    return Check(
        name=name, passed=True, detail=f"not applicable — {why}", incident=incident, skipped=True
    )


def _has_retrieval(run: dict[str, Any]) -> bool:
    return any("retrieved" in c for c in run.get("criteria", []))


def _has_status(run: dict[str, Any]) -> bool:
    """Whether this run is new enough to carry per-criterion status.

    Used as the marker for "produced after the conditional-routing work", which is the same commit
    that introduced the synthesis stage. A version stamp on the payload would be better than a
    field probe, and is worth adding the next time the payload changes — inferring a schema
    generation from which keys happen to be present is exactly the guesswork this project avoids
    everywhere else.
    """
    return any("status" in c for c in run.get("criteria", []))


def _findings(run: dict[str, Any]) -> list[dict[str, Any]]:
    envelope = run.get("envelope")
    if not envelope:
        return []
    return list(envelope["analysis"]["findings"])


def _all_excerpts(finding: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        excerpt
        for role in ("supporting_evidence", "mitigating_evidence", "contradicting_evidence")
        for excerpt in finding.get(role, [])
    ]


def citations_resolve(run: dict[str, Any], case_spans: dict[str, str] | None = None) -> Check:
    """Every cited evidence id resolves to a span the specialist was shown.

    Scoped to the **retrieved** set per criterion, not to the whole case. With retrieval those
    differ, and validating against the case would pass a model that cited a span it never saw —
    which is a lucky hallucination wearing the shape of analysis.
    """
    if not _has_retrieval(run):
        return _skip(
            "citations_resolve",
            "a model citing evidence it was never shown",
            "this run predates retrieval, so there is no record of what each specialist was shown",
        )

    shown: dict[str, set[str]] = {
        c["criterion_id"]: set(c.get("retrieved", [])) for c in run.get("criteria", [])
    }
    unresolvable: list[str] = []
    for finding in _findings(run):
        criterion = finding["criterion_id"]
        # Synthesis findings name a criterion but were shown the cited spans of every specialist,
        # so they are checked against the union rather than one criterion's retrieved set.
        allowed = shown.get(criterion, set()) if criterion in shown else set()
        union = set().union(*shown.values()) if shown else set()
        for excerpt in _all_excerpts(finding):
            eid = excerpt["evidence_id"]
            if eid not in allowed and eid not in union:
                unresolvable.append(f"{finding['finding_id']} cites {eid}")

    return Check(
        name="citations_resolve",
        passed=not unresolvable,
        detail=(
            "every cited span was shown to the run"
            if not unresolvable
            else f"{len(unresolvable)} unresolvable: {unresolvable[:5]}"
        ),
        incident="a model citing evidence it was never shown",
    )


def no_determinative_language(run: dict[str, Any]) -> Check:
    """The decision-support boundary, re-asked at the artifact that ships.

    The guard already runs when a `ProposedFinding` is constructed, so this should never fire —
    which is exactly why it is worth running. It is checking the *envelope*, one layer downstream
    of where the guard lives, and a boundary that is only enforced at construction is a boundary
    that any future code path writing an envelope directly would bypass silently.
    """
    offences: list[str] = []
    for finding in _findings(run):
        for field in ("title", "observation", "policy_relevance", "recommended_officer_action"):
            try:
                reject_determinative_language(finding[field])
            except ValueError as exc:
                offences.append(f"{finding['finding_id']}.{field}: {exc}")

    return Check(
        name="no_determinative_language",
        passed=not offences,
        detail=(
            "no narrative field states or implies a determination"
            if not offences
            else f"{len(offences)} offending fields: {offences[:3]}"
        ),
        incident="the prompt asks; the type enforces — this re-asks at the envelope",
    )


def no_aggregate_score(run: dict[str, Any]) -> Check:
    """ADR-014: no risk level, no ranking, no total, under any name.

    Walks field *names* throughout the envelope rather than narrative text, because an observation
    may legitimately quote a credit score that appears in the record.
    """
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if SCORE_LIKE.search(key):
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(run.get("envelope") or {}, "envelope")
    return Check(
        name="no_aggregate_score",
        passed=not found,
        detail="no aggregate field" if not found else f"aggregate-looking fields: {found}",
        incident="ADR-014 — an aggregate person-risk score is a determination",
    )


def rejections_are_bounded(run: dict[str, Any]) -> Check:
    """A rejection list in the thousands reports a malformed response, not a bad record.

    Rejections are output, and output has to stay readable to be worth anything. The run that
    produced 4,547 of them had two that mattered, and they were unfindable.
    """
    count = len(run.get("rejected", []))
    return Check(
        name="rejections_are_bounded",
        passed=count <= MAX_REASONABLE_REJECTIONS,
        detail=f"{count} rejections",
        incident="4,547 single-character rejections from a JSON string parsed as an array",
    )


def every_criterion_is_accounted_for(run: dict[str, Any]) -> Check:
    """Each criterion either completed or is named as not analysed, with a reason.

    A criterion nobody could analyse and a criterion that came back clean both have zero findings.
    If the run cannot tell them apart, it reports silent under-analysis as a clean record.
    """
    if not _has_status(run):
        return _skip(
            "every_criterion_is_accounted_for",
            "'completed with no findings' and 'refused' looking alike",
            "this run predates per-criterion status",
        )

    problems: list[str] = []
    for criterion in run.get("criteria", []):
        status = criterion.get("status")
        if status is None:
            problems.append(f"{criterion.get('criterion_id')} has no status")
        elif status != "completed" and not criterion.get("rejected"):
            problems.append(f"{criterion['criterion_id']} is {status} with no reason recorded")

    not_analysed = set(run.get("not_analysed", []))
    reported = {
        c["criterion_id"] for c in run.get("criteria", []) if c.get("status") != "completed"
    }
    if not_analysed != reported:
        problems.append(f"not_analysed {sorted(not_analysed)} disagrees with {sorted(reported)}")

    return Check(
        name="every_criterion_is_accounted_for",
        passed=not problems,
        detail="; ".join(problems) if problems else f"{len(run.get('criteria', []))} accounted for",
        incident="'completed with no findings' and 'refused' looking alike",
    )


def excerpt_integrity(run: dict[str, Any], case_spans: dict[str, str] | None = None) -> Check:
    """Each delivered excerpt hashes to the source text it claims to come from.

    Skipped rather than faked when the case text is not supplied — a check that silently passes
    because it had nothing to compare against is worse than one that says it did not run.
    """
    if case_spans is None:
        return _skip(
            "excerpt_integrity",
            "an excerpt whose hash does not match its source",
            "no case text was supplied to hash against",
        )

    mismatches: list[str] = []
    for finding in _findings(run):
        for excerpt in _all_excerpts(finding):
            source = case_spans.get(excerpt["evidence_id"])
            if source is None:
                mismatches.append(f"{excerpt['evidence_id']} is not in the case")
                continue
            if hashlib.sha256(source.encode()).hexdigest() != excerpt["text_sha256"]:
                mismatches.append(f"{excerpt['evidence_id']} hash mismatch")

    return Check(
        name="excerpt_integrity",
        passed=not mismatches,
        detail="every excerpt hashes to its source" if not mismatches else str(mismatches[:5]),
        incident="an excerpt whose hash does not match its source",
    )


def one_role_per_span(run: dict[str, Any]) -> Check:
    """Within one finding, a span is supporting or mitigating, never both.

    The contract enforces this at construction; models produce it constantly. Checked here because
    the envelope is what a reviewer reads, and a span arguing both ways in one finding is not a
    citation, it is a shrug.
    """
    offences: list[str] = []
    for finding in _findings(run):
        support = {e["evidence_id"] for e in finding.get("supporting_evidence", [])}
        mitigating = {e["evidence_id"] for e in finding.get("mitigating_evidence", [])}
        both = support & mitigating
        if both:
            offences.append(f"{finding['finding_id']}: {sorted(both)}")

    return Check(
        name="one_role_per_span",
        passed=not offences,
        detail="no span serves two roles" if not offences else str(offences),
        incident="models routinely cite the same span as supporting and mitigating",
    )


def synthesis_state_is_unambiguous(run: dict[str, Any]) -> Check:
    """Ran-and-found-nothing, ran-and-failed, and did-not-run are three different facts.

    They were inferred from one null once, and the run summary duly reported a hard failure as
    "skipped — nothing to reason across".
    """
    if not _has_status(run):
        return _skip(
            "synthesis_state_is_unambiguous",
            "a stage that ran and failed reported as skipped",
            "this run predates the synthesis stage",
        )

    synthesis = run.get("synthesis")
    if synthesis is None:
        # **The payload states this by omission, which is weaker than it should be.** An absent
        # key means "routing skipped the stage" for a modern run and "the stage did not exist" for
        # an old one, and only the status probe above separates them. Two facts sharing one null
        # is the exact shape this check exists to catch, one level up in the reporting.
        return Check(
            name="synthesis_state_is_unambiguous",
            passed=True,
            detail="did not run — routing skipped it, stated by omission",
            incident="a stage that ran and failed reported as skipped",
        )

    ran, failed = synthesis.get("ran"), synthesis.get("failed")
    if ran is None or failed is None:
        return Check(
            name="synthesis_state_is_unambiguous",
            passed=False,
            detail="synthesis block carries no explicit ran/failed state",
            incident="a stage that ran and failed reported as skipped",
        )
    state = "ran and failed" if failed else ("ran" if ran else "did not run")
    return Check(
        name="synthesis_state_is_unambiguous",
        passed=True,
        detail=f"{state}; {synthesis.get('findings', 0)} findings",
        incident="a stage that ran and failed reported as skipped",
    )


# ---------------------------------------------------------------------------
# Corpus-level — the checks a single run cannot make about itself
# ---------------------------------------------------------------------------


def classification_is_not_a_constant(runs: list[dict[str, Any]]) -> Check:
    """Across a corpus, the specialist stage must exercise more than one classification.

    **This is the check that would have caught the bug of 2026-08-17 for free**, and it needs no
    ground truth at all — only more than one case. `specialist.py` set the classification as a
    constant and the response schema never asked for one, so `MITIGATING_INFORMATION` and
    `NO_ISSUE_IDENTIFIED` were unreachable. Every individual run looked fine; the corpus did not.

    The general form is worth stating: **a constant that is usually right is indistinguishable
    from a decision until you look across cases.** Any enum a node "chooses" from is a candidate
    for this check.

    Synthesis findings are excluded — that stage legitimately emits exactly two classifications by
    construction, and counting them would mask a specialist stuck on one.
    """
    specialist_classes: set[str] = set()
    cases: set[str] = set()
    for run in runs:
        if not _has_status(run):
            continue  # predates the current specialist; its labels say nothing about today's code
        cases.add(str(run.get("case_id")))
        for finding in _findings(run):
            if not finding["finding_id"].startswith(f"fnd_{run.get('run_id')}_syn_"):
                specialist_classes.add(finding["classification"])

    enough_cases = len(cases) > 1
    passed = not enough_cases or len(specialist_classes) > 1
    return Check(
        name="classification_is_not_a_constant",
        passed=passed,
        detail=(
            f"{len(cases)} case(s), specialist classifications seen: {sorted(specialist_classes)}"
            + ("" if enough_cases else " — inconclusive, needs more than one case")
            + (
                ""
                if passed
                else ". A single value across differing records means the field is hard-coded, "
                "not chosen."
            )
        ),
        incident="2026-08-17: every finding on a clean record labelled potential_issue",
    )


SINGLE_RUN_CHECKS = (
    citations_resolve,
    no_determinative_language,
    no_aggregate_score,
    rejections_are_bounded,
    every_criterion_is_accounted_for,
    one_role_per_span,
    synthesis_state_is_unambiguous,
)


def score_run(run: dict[str, Any], case_spans: dict[str, str] | None = None) -> list[Check]:
    """Every single-run check, in a stable order."""
    checks = [
        check(run) if check is not citations_resolve else check(run, case_spans)
        for check in SINGLE_RUN_CHECKS
    ]
    checks.append(excerpt_integrity(run, case_spans))
    return checks
