"""Policy packs, policy citations, and authority routing.

Blueprint §2.7 and §8.1. Two rules from `CLAUDE.md` shape this module:

- *Evidence before inference* — every policy-relevance claim carries a resolvable policy citation.
- *Deterministic shell* — authority routing and policy-pack effectivity are ordinary code. The
  model does not decide which authority applies, and it does not decide whether a pack is in
  force on a given date.

The design fails closed: an expired or unapproved pack cannot be used, and a route that cannot
be determined from explicit metadata produces a blocking gap rather than a default.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    ContractModel,
    ContractVersion,
    DecisionDomain,
    NonEmptyStr,
    PolicyCitationId,
    PolicyPackId,
    Sha256,
    UtcDatetime,
)


class PolicyPackStatus(StrEnum):
    """Only APPROVED may be used in a run.

    Blueprint §2.7 and Q-07: the design fails closed when a pack is expired or unapproved. That
    is only meaningful if an approving office exists, which is Q-07 and remains open.
    """

    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class PolicyPackRef(ContractModel):
    """A pinned reference to an approved policy pack, as used by one run.

    The `sha256` is what makes a run reproducible without replay (ADR-009): the manifest records
    exactly which policy content produced the findings, so a later change to a pack cannot
    silently rewrite the basis of a past analysis.
    """

    policy_pack_id: PolicyPackId
    version: NonEmptyStr
    content_sha256: Sha256
    status: PolicyPackStatus
    effective_from: UtcDatetime
    effective_to: UtcDatetime | None = Field(
        default=None, description="Null means currently in force with no scheduled end."
    )
    decision_domains: list[DecisionDomain] = Field(min_length=1)

    @model_validator(mode="after")
    def _only_approved_packs_are_usable(self) -> PolicyPackRef:
        if self.status is not PolicyPackStatus.APPROVED:
            raise ValueError(
                f"policy pack {self.policy_pack_id!r} has status {self.status.value!r}; "
                "only 'approved' packs may be referenced by a run (fail closed, blueprint §2.7)"
            )
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self

    def is_in_force_at(self, moment: UtcDatetime) -> bool:
        """Effectivity is a deterministic date comparison, never a model judgment."""
        if moment < self.effective_from:
            return False
        return self.effective_to is None or moment < self.effective_to


class PolicyCitation(ContractModel):
    """A resolvable pointer into approved policy text.

    Deliberately not free text. A finding's policy-relevance claim must be checkable against the
    pack that was in force, which requires an address, not a quotation the model composed.
    """

    citation_id: PolicyCitationId
    policy_pack_id: PolicyPackId
    policy_id: NonEmptyStr = Field(description="e.g. 'SEAD-4' or '5-CFR-731'.")
    criterion_id: NonEmptyStr = Field(description="e.g. 'GUIDELINE-B' or '731.202(b)(4)'.")
    section_path: NonEmptyStr | None = None
    text_sha256: Sha256 | None = Field(
        default=None, description="Hash of the cited passage, for tamper detection at review time."
    )


class RoutingBasis(StrEnum):
    """Why an authority was or was not routed.

    Blueprint §10.2: the system may not infer routing from document content. `INFERRED` is
    absent from this enum on purpose — there is no legitimate value for it.
    """

    EXPLICIT_CASE_METADATA = "explicit_case_metadata"
    POLICY_PACK_APPLICABILITY = "policy_pack_applicability"
    REQUESTED_AND_VALIDATED = "requested_and_validated"
    DECLINED_NOT_APPLICABLE = "declined_not_applicable"
    BLOCKED_MISSING_METADATA = "blocked_missing_metadata"


class AuthorityRoute(ContractModel):
    """One routing determination: this authority applies to this case, or it does not, and why.

    ADR-003: routing is implemented, not stubbed, from day one. Building it after the fact is a
    refactor of every analysis path.

    A route with `applies=False` is retained rather than dropped. A reviewer needs to see that
    national-security eligibility was considered and declined, and on what basis — an absent
    route is indistinguishable from an oversight.
    """

    decision_domain: DecisionDomain
    applies: bool
    basis: RoutingBasis
    policy_pack_ids: list[PolicyPackId] = Field(default_factory=list)
    rationale: NonEmptyStr = Field(
        description="Deterministic explanation of the routing rule that fired. Not model prose."
    )
    blocking_gap: NonEmptyStr | None = Field(
        default=None,
        description=(
            "Set when routing could not be determined from explicit metadata. Blueprint §10.2: "
            "missing or inconsistent routing fields produce a blocking information gap."
        ),
    )

    @model_validator(mode="after")
    def _routing_is_internally_consistent(self) -> AuthorityRoute:
        if self.basis is RoutingBasis.BLOCKED_MISSING_METADATA:
            if self.applies:
                raise ValueError("a blocked route cannot also be marked as applying")
            if not self.blocking_gap:
                raise ValueError("BLOCKED_MISSING_METADATA requires a blocking_gap description")
        if self.applies and not self.policy_pack_ids:
            raise ValueError(
                "an applicable authority must name the policy pack(s) that supply its criteria"
            )
        return self


class AuthorityRoutingResult(ContractModel):
    """The complete routing decision for a run — every domain considered, none omitted."""

    schema_version: ContractVersion = CONTRACT_VERSION
    routes: list[AuthorityRoute] = Field(min_length=1)
    routed_at: UtcDatetime

    @model_validator(mode="after")
    def _every_domain_considered_once(self) -> AuthorityRoutingResult:
        domains = [r.decision_domain for r in self.routes]
        if len(set(domains)) != len(domains):
            raise ValueError("each decision_domain may be routed at most once")
        missing = set(DecisionDomain) - set(domains)
        if missing:
            raise ValueError(
                "routing must record an explicit decision for every authority, including those "
                f"that do not apply; missing: {sorted(d.value for d in missing)}"
            )
        return self

    @property
    def has_blocking_gap(self) -> bool:
        return any(r.blocking_gap for r in self.routes)
