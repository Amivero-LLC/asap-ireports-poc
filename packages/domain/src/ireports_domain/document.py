"""Document manifest and canonical document structure.

Blueprint §6.2 stages 1-3. The purpose of the canonical form is to make an evidence span
*resolvable*: a citation names a document, a page, and a block, and that address has to still
mean the same thing when a reviewer opens the document months later. Extraction is therefore
recorded with enough provenance to detect when a re-extraction would move the addresses.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .case import DocumentExpectation
from .common import (
    CONTRACT_VERSION,
    CaseId,
    ContractModel,
    ContractVersion,
    DocumentId,
    IngestionId,
    NonEmptyStr,
    Sha256,
    UtcDatetime,
)


class DocumentType(StrEnum):
    """Classification assigned during ingestion (blueprint §6.2 stage 4).

    `UNCLASSIFIED_BY_SYSTEM` is deliberate: an unrecognized document must remain analysable and
    visibly unclassified rather than being forced into the nearest category.
    """

    SECURITY_QUESTIONNAIRE = "security_questionnaire"
    REPORT_OF_INVESTIGATION = "report_of_investigation"
    SUBJECT_INTERVIEW = "subject_interview"
    SUBJECT_STATEMENT = "subject_statement"
    CREDIT_REPORT = "credit_report"
    LAW_ENFORCEMENT_RECORD = "law_enforcement_record"
    COURT_RECORD = "court_record"
    EMPLOYMENT_RECORD = "employment_record"
    EDUCATION_RECORD = "education_record"
    FINANCIAL_RECORD = "financial_record"
    MEDICAL_OR_TREATMENT_RECORD = "medical_or_treatment_record"
    CORRESPONDENCE = "correspondence"
    OTHER = "other"
    UNCLASSIFIED_BY_SYSTEM = "unclassified_by_system"


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    DOCLING = "docling"
    OCR_TESSERACT = "ocr_tesseract"
    OCR_THEN_DOCLING = "ocr_then_docling"


class SourceReliability(StrEnum):
    """Blueprint §7.6.

    Source reliability is recorded, never inferred at analysis time from the assertion's
    content. A subject's own statement and an investigator's finding carry different weight, and
    a contradiction between them is a finding input rather than something to silently resolve.
    """

    OFFICIAL_RECORD = "official_record"
    INVESTIGATOR_FINDING = "investigator_finding"
    THIRD_PARTY_REPORT = "third_party_report"
    SUBJECT_SELF_REPORT = "subject_self_report"
    UNDETERMINED = "undetermined"


class DocumentManifest(ContractModel):
    """One expected or present document in a case.

    `expectation` links a physical document back to what the case said it should contain, which
    is what lets the completeness checker distinguish "missing" from "present but unreadable" —
    two conditions with different consequences for a reviewer.
    """

    schema_version: ContractVersion = CONTRACT_VERSION
    document_id: DocumentId
    case_id: CaseId
    ingestion_id: IngestionId

    file_name: NonEmptyStr
    media_type: NonEmptyStr
    byte_size: int = Field(ge=0)
    content_sha256: Sha256 = Field(
        description=(
            "Integrity anchor. A changed hash invalidates every evidence span into this document."
        )
    )

    document_type: DocumentType
    expectation: DocumentExpectation | None = Field(
        default=None, description="Which case document_expectation this satisfies, if any."
    )
    source_reliability: SourceReliability = SourceReliability.UNDETERMINED

    page_count: int | None = Field(default=None, ge=0)
    extraction_method: ExtractionMethod | None = None
    extraction_succeeded: bool = Field(
        description=(
            "False means present-but-unreadable. This must reach the reviewer as an information "
            "gap; silently analysing a case with an unreadable document is a failure mode "
            "blueprint §6.2 stage 1 exists to prevent."
        )
    )
    extraction_notes: NonEmptyStr | None = None

    ingested_at: UtcDatetime

    @model_validator(mode="after")
    def _failed_extraction_is_explained(self) -> DocumentManifest:
        if not self.extraction_succeeded and self.extraction_notes is None:
            raise ValueError(
                "extraction_succeeded=False requires extraction_notes: an unreadable document "
                "must carry a reviewable reason"
            )
        return self


class DocumentBlock(ContractModel):
    """An addressable unit of canonical text.

    `block_index` is stable within `(document_id, page_number)` for a given
    `(content_sha256, extraction_method)` pair. That triple is what makes a citation resolvable
    rather than approximate — see `EvidenceSpan`.
    """

    block_index: int = Field(ge=0)
    page_number: int | None = Field(default=None, ge=1)
    text: NonEmptyStr
    char_start: int = Field(ge=0, description="Offset into the canonical document text.")
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _span_is_ordered(self) -> DocumentBlock:
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class CanonicalDocument(ContractModel):
    """Normalized document text, addressable by block (blueprint §6.2 stage 3)."""

    schema_version: ContractVersion = CONTRACT_VERSION
    document_id: DocumentId
    case_id: CaseId
    ingestion_id: IngestionId

    content_sha256: Sha256 = Field(description="Hash of the *source* file this was extracted from.")
    extraction_method: ExtractionMethod
    extractor_version: NonEmptyStr = Field(
        description=(
            "Pinned so that a re-extraction which moves block boundaries is detectable. "
            "Evidence spans are only comparable within one extractor version."
        )
    )
    blocks: list[DocumentBlock] = Field(min_length=1)
    normalized_at: UtcDatetime

    @model_validator(mode="after")
    def _blocks_are_uniquely_indexed(self) -> CanonicalDocument:
        keys = [(b.page_number, b.block_index) for b in self.blocks]
        if len(set(keys)) != len(keys):
            raise ValueError("blocks must be uniquely addressed by (page_number, block_index)")
        return self
