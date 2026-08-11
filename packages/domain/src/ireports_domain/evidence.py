"""Evidence records — the resolvable anchor under every factual claim.

Blueprint §7.4 and §7.5. `CLAUDE.md`'s "evidence before inference" rule means every material
factual statement in a finding carries a resolvable citation to a case evidence span, and
deterministic validators reject unsupported citations before a human ever sees them. This module
is the "resolvable" half of that: an `EvidenceSpan` is an address that can be independently
re-read, not a paraphrase the model produced.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    CaseId,
    ChunkId,
    ContractModel,
    ContractVersion,
    DocumentId,
    EvidenceId,
    IngestionId,
    NonEmptyStr,
    Sha256,
    UtcDatetime,
)
from .document import SourceReliability


class RetrievalMode(StrEnum):
    LEXICAL = "lexical"
    VECTOR_KNN = "vector_knn"
    HYBRID = "hybrid"
    DIRECT_LOOKUP = "direct_lookup"


class EvidenceSpan(ContractModel):
    """A citable address inside a canonical document.

    The address is `(document_id, page, block, char range)` qualified by
    `(document_sha256, extractor_version)`. Both qualifiers are required: without them a span
    silently means something different after a re-extraction, which is how a citation that once
    resolved starts pointing at the wrong sentence.
    """

    document_id: DocumentId
    document_sha256: Sha256
    extractor_version: NonEmptyStr

    page_number: int | None = Field(default=None, ge=1)
    block_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _span_is_ordered(self) -> EvidenceSpan:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class RetrievalProvenance(ContractModel):
    """How this evidence came to be in front of the model.

    Recorded so a run is reconstructable without replay (ADR-009). Note that the embedding model
    identity is captured per retrieval: ADR-007's Q-03 parity risk is silent — a mismatch between
    our query-time embedding model and the one the AWS pipeline indexed with does not error, it
    just retrieves worse. Recording it per-record is what makes drift detectable after the fact.
    """

    retrieval_mode: RetrievalMode
    query_id: NonEmptyStr = Field(description="Links back to the bounded retrieval request.")
    rank: int | None = Field(default=None, ge=1)
    score: float | None = None
    embedding_model_id: NonEmptyStr | None = Field(
        default=None,
        description="Required when retrieval_mode involves vectors. See ADR-007, Q-03.",
    )
    embedding_model_revision: NonEmptyStr | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    chunk_id: ChunkId | None = None

    @model_validator(mode="after")
    def _vector_retrieval_records_its_model(self) -> RetrievalProvenance:
        if (
            self.retrieval_mode in (RetrievalMode.VECTOR_KNN, RetrievalMode.HYBRID)
            and not self.embedding_model_id
        ):
            raise ValueError(
                "vector retrieval must record embedding_model_id: without it, Q-03 "
                "embedding-parity drift is undetectable"
            )
        return self


class EvidenceRecord(ContractModel):
    """A snapshot of evidence as it was presented to a node.

    `text` is a *snapshot*, and that is intentional (blueprint §7.4): the finding must remain
    reviewable against exactly what the model saw, even if the underlying index is later
    re-built. `CLAUDE.md` constrains where this may travel — evidence text lives in
    access-controlled stores only, and never reaches a log or a trace.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    evidence_id: EvidenceId
    case_id: CaseId
    ingestion_id: IngestionId

    span: EvidenceSpan
    text: NonEmptyStr = Field(
        description="Verbatim snapshot of the cited span. Never emitted to logs or traces."
    )
    text_sha256: Sha256 = Field(
        description=(
            "Lets a reviewer confirm the snapshot was not altered between proposal and review."
        )
    )

    source_reliability: SourceReliability = SourceReliability.UNDETERMINED
    retrieval: RetrievalProvenance
    snapshot_at: UtcDatetime


class ContradictionRecord(ContractModel):
    """Two pieces of case evidence that cannot both be true.

    Blueprint §7.6. A contradiction is surfaced, never resolved by the system — resolving it is
    an officer judgment about credibility, which sits outside the decision-support boundary.
    AmiLens's recorded gap (no cross-referencing of subject statements against investigator
    findings) is exactly what this contract exists to close (ADR-002).
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    contradiction_id: NonEmptyStr
    case_id: CaseId
    topic: NonEmptyStr
    assertion_evidence_ids: list[EvidenceId] = Field(min_length=2)
    description: NonEmptyStr = Field(
        description="Neutral statement of what conflicts. Not an assessment of who is truthful."
    )
    resolved: Literal[False] = Field(
        default=False,
        description=(
            "Structurally unresolvable by the system. Credibility resolution is reserved to the "
            "reviewing officer."
        ),
    )
