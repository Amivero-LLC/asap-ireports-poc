"""The case as orchestration sees it: a manifest plus citable spans.

**The types live here; reading them off a disk does not.** `spikes/lambda_demo/case_loader.py`
holds `load_case()` — the JSON parsing, the directory layout, the duplicate-id check — because
where a case comes from is a property of the deployment, not of the analysis. The AWS path will
hand these in from an ingestion pipeline (ADR-007) with no filesystem anywhere in it, and nothing
in this package should have to change for that.

`EvidenceSpan` is a flat local shape rather than the `EvidenceRecord` contract, and that is
deliberate: `EvidenceRecord` requires retrieval provenance (embedding model, rank, score) that
belongs to a *retrieved* span. These are the spans of the record itself, before anyone has asked
a question of them. Inventing rank and score to satisfy a contract would be exactly the fabricated
provenance this project exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ireports_domain import CaseManifest


@dataclass(frozen=True)
class EvidenceSpan:
    """One citable span of the case record."""

    evidence_id: str
    document_id: str
    page_number: int
    source_reliability: str
    text: str
    title: str = ""
    source_type: str = "case_document"


@dataclass(frozen=True)
class LoadedCase:
    """A case ready to be analysed.

    `root` is provenance — where this case was read from. Nothing in orchestration reads it; it
    exists so that a run can say which fixture it analysed, and so the envelope builder can name
    a document reference. A deployment with no filesystem passes a path that is never opened.
    """

    manifest: CaseManifest
    spans: tuple[EvidenceSpan, ...]
    root: Path
