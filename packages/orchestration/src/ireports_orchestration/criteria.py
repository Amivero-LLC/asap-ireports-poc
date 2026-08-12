"""Which criteria a case gets analyzed against — derived from the case, not hard-coded.

The fan-out used to be a constant: three `Criterion` objects, the same three for every case. That
made the graph shape a compile-time fact, which is both wrong about the domain and useless for
comparing orchestrators — a fixed-width fan-out is trivial in any framework.

`CaseManifest` already carries `requested_analyses` and `policy_pack_ids`. Selection reads those,
so **the number of specialists is runtime data** and two different cases produce two differently
shaped runs.

**This is a stub for authority routing (ROUT-01), and the difference matters.** The contract says
`requested_analyses` is "a request, not an authorization" — real routing validates each request
against `case_context` and may *decline* one that does not legally apply or *add* one the requester
omitted. This does neither. It intersects what was asked with what the catalog offers, which is
honest for a proof of concept and must not be mistaken for the router.

The catalog is also hand-written here rather than loaded from an approved policy pack, because
approved policy content does not exist yet. When it does, this module reads it instead — the
selection logic is the part worth keeping.
"""

from __future__ import annotations

from dataclasses import dataclass

from ireports_domain import CaseManifest, DecisionDomain


@dataclass(frozen=True)
class Criterion:
    """One thing being checked, under one named authority.

    Every finding names exactly one decision domain (ADR-003) — suitability, fitness, PIV
    credentialing, and national-security eligibility are distinct legal authorities, and collapsing
    them produces analysis that is wrong in a way that is hard to detect.
    """

    node_id: str
    decision_domain: DecisionDomain
    policy_pack_id: str
    policy_id: str
    criterion_id: str
    question: str


CATALOG: tuple[Criterion, ...] = (
    Criterion(
        node_id="foreign_influence_specialist",
        decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        policy_pack_id="sead4-current",
        policy_id="SEAD-4",
        criterion_id="GUIDELINE-B",
        question=(
            "Foreign influence: contacts with foreign nationals, foreign financial interests, "
            "and any resulting divided loyalties or vulnerability to coercion."
        ),
    ),
    Criterion(
        node_id="personal_conduct_specialist",
        decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
        policy_pack_id="sead4-current",
        policy_id="SEAD-4",
        criterion_id="GUIDELINE-E",
        question=(
            "Personal conduct: concealment, omission, or falsification in the security process, "
            "and any conduct creating vulnerability to exploitation or duress."
        ),
    ),
    Criterion(
        node_id="financial_considerations_specialist",
        decision_domain=DecisionDomain.SUITABILITY,
        policy_pack_id="federal-core-2026-07-30",
        policy_id="5-CFR-731",
        criterion_id="731-202-B-4",
        question=(
            "Financial responsibility: delinquent debt, unexplained affluence, and whether the "
            "record shows a pattern or an explained and resolving isolated event."
        ),
    ),
    Criterion(
        node_id="candor_specialist",
        decision_domain=DecisionDomain.SUITABILITY,
        policy_pack_id="federal-core-2026-07-30",
        policy_id="5-CFR-731",
        criterion_id="731-202-B-3",
        question=(
            "Candor: material omissions or inconsistencies between what the subject reported "
            "and what the record shows, and whether the record explains them."
        ),
    ),
    Criterion(
        node_id="criminal_conduct_specialist",
        decision_domain=DecisionDomain.SUITABILITY,
        policy_pack_id="federal-core-2026-07-30",
        policy_id="5-CFR-731",
        criterion_id="731-202-B-2",
        question=(
            "Criminal or dishonest conduct: arrests, charges, or conduct involving dishonesty, "
            "and the recency, seriousness, and circumstances of any such conduct."
        ),
    ),
)
"""The criteria this demo can analyse against.

Deliberately wider than any one case needs. A catalog that exactly matches the demo case would make
selection look like a formality — and it would hide the result worth having, which is that a
criterion with nothing in the record **returns nothing**. A specialist that manufactures a finding
to appear thorough is the failure mode hardest to detect downstream, and the only way to see it is
to ask questions the evidence does not answer.
"""


class NoApplicableCriteriaError(ValueError):
    """The case asked for analyses this catalog cannot serve.

    Raised rather than returning an empty tuple: a run with no criteria would complete successfully
    having analysed nothing, which is indistinguishable from a case where every criterion came back
    clean. That confusion is the one this system can least afford.
    """


def criteria_for(manifest: CaseManifest) -> tuple[Criterion, ...]:
    """The criteria this case gets analysed against.

    Intersects the requested decision domains with the requested policy packs. Order follows
    `CATALOG` so two runs of the same case fan out in the same order — not required for
    correctness, since the join sorts, but it makes two runs readable side by side.
    """
    requested = set(manifest.requested_analyses)
    packs = set(manifest.policy_pack_ids)

    selected = tuple(
        criterion
        for criterion in CATALOG
        if criterion.decision_domain in requested and criterion.policy_pack_id in packs
    )

    if not selected:
        raise NoApplicableCriteriaError(
            f"case {manifest.case_id} requested "
            f"{sorted(d.value for d in requested)} under packs {sorted(packs)}, and the catalog "
            f"has no criterion matching both. Nothing would be analysed."
        )
    return selected
