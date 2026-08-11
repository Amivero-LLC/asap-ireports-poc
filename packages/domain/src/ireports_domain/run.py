"""Run manifest and run state.

Blueprint §8.2 and §10.3. Two properties matter more than the field list:

- **The status enum is the human review gate.** ADR-011 makes review a state transition, not a
  UI convention, so `AWAITING_HUMAN_REVIEW` is a state a run must pass *through*. There is no
  status that reaches delivery without it, and no bypass in any profile.
- **State carries identifiers, not transcripts.** Blueprint §8.2 is explicit: large evidence text
  stays in the evidence store and is referenced by id. That keeps checkpoints small and keeps
  case text out of anything that gets serialized widely — which matters directly for the
  checkpoint-store threat model the M1b scan raised.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    ActorId,
    CaseId,
    ContractModel,
    ContractVersion,
    EvidenceId,
    FindingId,
    IngestionId,
    ModelAlias,
    NonEmptyStr,
    RunId,
    SemVer,
    Sha256,
    UtcDatetime,
)
from .policy import AuthorityRoutingResult, PolicyPackRef


class RunStatus(StrEnum):
    """The run state machine.

    The ordering below is the legal progression. `AWAITING_HUMAN_REVIEW` is not skippable:
    `_delivery_requires_review` enforces that any delivered run recorded a review, and
    `LEGAL_TRANSITIONS` encodes that no path reaches `DELIVERED` without passing through it.
    """

    INITIALIZING = "initializing"
    ROUTING = "routing"
    RETRIEVING = "retrieving"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    VALIDATING = "validating"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REVIEW_RECORDED = "review_recorded"
    PACKAGING = "packaging"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCOMPLETE_DUE_TO_BUDGET = "incomplete_due_to_budget"


LEGAL_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.INITIALIZING: frozenset({RunStatus.ROUTING, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.ROUTING: frozenset(
        {
            RunStatus.RETRIEVING,
            RunStatus.AWAITING_HUMAN_REVIEW,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RETRIEVING: frozenset(
        {
            RunStatus.ANALYZING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INCOMPLETE_DUE_TO_BUDGET,
        }
    ),
    RunStatus.ANALYZING: frozenset(
        {
            RunStatus.SYNTHESIZING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INCOMPLETE_DUE_TO_BUDGET,
        }
    ),
    RunStatus.SYNTHESIZING: frozenset(
        {RunStatus.VALIDATING, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.VALIDATING: frozenset(
        {
            RunStatus.AWAITING_HUMAN_REVIEW,
            RunStatus.ANALYZING,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.AWAITING_HUMAN_REVIEW: frozenset({RunStatus.REVIEW_RECORDED, RunStatus.CANCELLED}),
    RunStatus.REVIEW_RECORDED: frozenset({RunStatus.PACKAGING, RunStatus.CANCELLED}),
    RunStatus.PACKAGING: frozenset({RunStatus.DELIVERING, RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.DELIVERING: frozenset({RunStatus.DELIVERED, RunStatus.FAILED}),
    RunStatus.DELIVERED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.INCOMPLETE_DUE_TO_BUDGET: frozenset(
        {RunStatus.AWAITING_HUMAN_REVIEW, RunStatus.CANCELLED}
    ),
}
"""Legal state transitions.

`INCOMPLETE_DUE_TO_BUDGET` routes to human review rather than to failure: blueprint §8.5 requires
that a budget stop produce a visible incomplete result rather than silently omitting work. A
reviewer must be told the analysis was truncated.
"""


def is_legal_transition(current: RunStatus, proposed: RunStatus) -> bool:
    return proposed in LEGAL_TRANSITIONS[current]


class Actor(ContractModel):
    """Who initiated or acted on a run."""

    actor_id: ActorId
    roles: tuple[NonEmptyStr, ...] = Field(min_length=1)


class Budgets(ContractModel):
    """Loop limits and termination controls (blueprint §8.5).

    These are enforced by the deterministic shell, not requested of the model. A node that hits a
    ceiling produces `incomplete_due_to_budget`; it does not quietly return less work.
    """

    max_model_calls_per_node: int = Field(default=5, ge=1, le=20)
    max_tool_calls_per_node: int = Field(default=12, ge=1, le=50)
    max_evidence_per_node: int = Field(default=40, ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    max_wall_clock_seconds: int = Field(ge=1)
    max_parallel_specialists: int = Field(default=4, ge=1, le=16)


class BudgetConsumption(ContractModel):
    """What a run actually used, recorded for evaluation and cost work."""

    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    wall_clock_seconds: float = Field(default=0.0, ge=0)


class RunError(ContractModel):
    node: NonEmptyStr
    error_type: NonEmptyStr
    message: NonEmptyStr = Field(
        description=(
            "Must not contain case text. `CLAUDE.md`: raw case text never reaches logs or "
            "traces, and error messages propagate to both."
        )
    )
    occurred_at: UtcDatetime
    retriable: bool


class RunManifest(ContractModel):
    """Everything needed to reconstruct why a run produced what it produced.

    ADR-009 declines an offline replay profile, so reproducibility rests entirely on this record:
    model aliases, prompt registry version, policy pack hashes, configuration hash, and
    application version. If a field needed to explain a past result is missing here, it is not
    recoverable anywhere else.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    run_id: RunId
    case_id: CaseId
    ingestion_id: IngestionId

    started_at: UtcDatetime
    completed_at: UtcDatetime | None = None
    actor: Actor
    profile: NonEmptyStr = Field(
        description="e.g. 'local_bedrock'. See ADR-009 — no offline profile."
    )

    policy_packs: tuple[PolicyPackRef, ...] = Field(min_length=1)
    authority_routing: AuthorityRoutingResult | None = None

    model_aliases: tuple[ModelAlias, ...] = Field(
        min_length=1,
        description=(
            "Aliases only, never model IDs (ADR-008). Diverges from blueprint §10.3 deliberately."
        ),
    )
    prompt_registry_version: NonEmptyStr
    application_version: SemVer
    configuration_sha256: Sha256

    budgets: Budgets
    consumption: BudgetConsumption = Field(default_factory=BudgetConsumption)

    status: RunStatus
    evidence_snapshot_ids: tuple[EvidenceId, ...] = Field(default_factory=tuple)
    proposed_finding_ids: tuple[FindingId, ...] = Field(default_factory=tuple)
    errors: tuple[RunError, ...] = Field(default_factory=tuple)

    human_review_recorded: bool = Field(
        default=False,
        description=(
            "Set only by the review gate when a disposition exists for every proposed finding. "
            "ADR-011: there is no bypass, in any profile, including local development."
        ),
    )

    @model_validator(mode="after")
    def _delivery_requires_review(self) -> RunManifest:
        """The hard gate (ADR-011), expressed as a validation error.

        A `RunManifest` in a delivery-side state with `human_review_recorded=False` is not a
        valid object. This makes the gate impossible to bypass by constructing the state
        directly, which is the failure mode a config flag would leave open.
        """
        post_review = {
            RunStatus.REVIEW_RECORDED,
            RunStatus.PACKAGING,
            RunStatus.DELIVERING,
            RunStatus.DELIVERED,
        }
        if self.status in post_review and not self.human_review_recorded:
            raise ValueError(
                f"run status {self.status.value!r} requires human_review_recorded=True; "
                "nothing reaches ASAP without a recorded human disposition (ADR-011)"
            )
        return self

    @model_validator(mode="after")
    def _completion_is_consistent(self) -> RunManifest:
        terminal = {RunStatus.DELIVERED, RunStatus.FAILED, RunStatus.CANCELLED}
        if self.status in terminal and self.completed_at is None:
            raise ValueError(f"terminal status {self.status.value!r} requires completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at precedes started_at")
        return self
