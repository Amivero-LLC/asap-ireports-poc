"""The typed return value of one specialist sub-call (CONT-01).

Blueprint §10.1, narrowed by ADR-021. The orchestrator says "check this case against 5 CFR 731
financial considerations," the sub-agent runs its RAG search, and this is what comes back. The
contract is thin on purpose (D-01, Phase 1 context): the criterion analyzed, the provenance of
the run, and the proposed findings with their citations. Nothing else.

- There is no field describing whether the sub-call finished, no boolean flag equivalent to
  "done", and no free-text explanation for why a sub-call produced less than expected. An
  earlier five-member enum covering exactly that was proposed during the discussion that
  produced this contract and then explicitly reversed once its purpose was clear: "We should
  LOG things and check the logs, but not require the orchestrator to do anything special"
  (ADR-021 Decision 2). A refused or truncated sub-call still produces a valid
  `SpecialistResult`, just one with fewer findings; the distinction lives in the log, not the
  schema (ADR-021 Consequence 2).
- There is no aggregate score, risk level, or recommendation field, under any name (ADR-014).
  `test_no_contract_carries_an_aggregate_score` walks every contract in `ROOT_CONTRACTS`,
  including this one, and enforces that mechanically.
- There is no per-query accounting of model or tool spend. The existing run-level record on
  `RunManifest` already accumulates that; duplicating it here would let two records disagree
  about what a run spent.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    CaseId,
    ContractModel,
    ContractVersion,
    DecisionDomain,
    NonEmptyStr,
    PolicyPackId,
    RunId,
)
from .finding import GeneratedBy, ProposedFinding


class SpecialistCriterion(ContractModel):
    """The criterion a specialist sub-call was pointed at.

    A sibling to the per-finding authority type used elsewhere in this package — it shares the
    same four identifying fields (`decision_domain`, `policy_pack_id`, `policy_id`,
    `criterion_id`) but deliberately omits that type's fifth field, the list of policy citation
    ids required to have at least one entry (D-04). A query does not cite; a finding does. Policy
    citations belong to the proposed findings this criterion produces, not to the act of asking
    the question. Not a subclass of that type, and it is not imported here.
    """

    decision_domain: DecisionDomain
    policy_pack_id: PolicyPackId
    policy_id: NonEmptyStr
    criterion_id: NonEmptyStr


class SpecialistResult(ContractModel):
    """The return value of one specialist sub-agent call.

    Required, not `Optional` (D-05): `criterion` is populated even when `findings` is empty, so a
    result with zero findings still says what was checked. This is the whole reason the wrapper
    exists rather than returning a bare `list[ProposedFinding]`.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    run_id: RunId
    case_id: CaseId
    criterion: SpecialistCriterion
    generated_by: GeneratedBy
    findings: list[ProposedFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _findings_belong_to_this_criterion(self) -> SpecialistResult:
        """A specialist sub-call analyzes exactly one criterion (the per-finding authority
        type's own docstring: "one authority per finding, always"). Every finding this result
        carries must agree with the result's own `run_id`, `case_id`, and criterion — a
        mismatch is a defect by construction, not a legitimate variation.
        """
        for finding in self.findings:
            if finding.run_id != self.run_id:
                raise ValueError(
                    f"finding {finding.finding_id!r} has run_id {finding.run_id!r}, which does "
                    f"not match this result's run_id {self.run_id!r}"
                )
            if finding.case_id != self.case_id:
                raise ValueError(
                    f"finding {finding.finding_id!r} has case_id {finding.case_id!r}, which does "
                    f"not match this result's case_id {self.case_id!r}"
                )
            authority = finding.authority
            if authority.decision_domain != self.criterion.decision_domain:
                raise ValueError(
                    f"finding {finding.finding_id!r} has authority.decision_domain "
                    f"{authority.decision_domain!r}, which does not match this result's "
                    f"criterion.decision_domain {self.criterion.decision_domain!r}"
                )
            if authority.policy_pack_id != self.criterion.policy_pack_id:
                raise ValueError(
                    f"finding {finding.finding_id!r} has authority.policy_pack_id "
                    f"{authority.policy_pack_id!r}, which does not match this result's "
                    f"criterion.policy_pack_id {self.criterion.policy_pack_id!r}"
                )
            if authority.policy_id != self.criterion.policy_id:
                raise ValueError(
                    f"finding {finding.finding_id!r} has authority.policy_id "
                    f"{authority.policy_id!r}, which does not match this result's "
                    f"criterion.policy_id {self.criterion.policy_id!r}"
                )
            if authority.criterion_id != self.criterion.criterion_id:
                raise ValueError(
                    f"finding {finding.finding_id!r} has authority.criterion_id "
                    f"{authority.criterion_id!r}, which does not match this result's "
                    f"criterion.criterion_id {self.criterion.criterion_id!r}"
                )
        return self
