"""Load a synthetic case from disk into typed contracts.

Deliberately file-based. The bake-off built its case in Python (`scenario.build_case()`), which
is fine for a fixture but means there is nothing a reader can open, edit, and re-run. A case that
lives on disk is the difference between "the architecture works" as an assertion and as something
someone can try with their own input.

These cases are **not** the VAL-03 corpus. VAL-03 (Phase 3) needs analyst-identified expected
findings to measure agreement against; these have no ground truth attached and live under
`spikes/` for that reason. `cases/synthetic/` stays `PLANNED` in the build-state table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ireports_domain import CaseManifest


@dataclass(frozen=True)
class EvidenceSpan:
    """One citable span of the case record.

    A flat local shape rather than the full `EvidenceRecord` contract: that type requires
    retrieval provenance (embedding model, rank, score) which only exists once retrieval is
    built (RETR-01, Phase 2). Inventing those values to satisfy a contract would be the kind of
    fabricated-provenance shortcut this project exists to avoid.
    """

    evidence_id: str
    document_id: str
    page_number: int
    source_reliability: str
    text: str


@dataclass(frozen=True)
class LoadedCase:
    manifest: CaseManifest
    spans: tuple[EvidenceSpan, ...]
    root: Path


def load_case(root: Path) -> LoadedCase:
    """Read `case.json` and `evidence.json` from a case directory."""
    case_file = root / "case.json"
    evidence_file = root / "evidence.json"
    for path in (case_file, evidence_file):
        if not path.exists():
            raise FileNotFoundError(f"expected {path}, which does not exist")

    manifest = CaseManifest.model_validate(json.loads(case_file.read_text()))
    raw = json.loads(evidence_file.read_text())

    spans = tuple(
        EvidenceSpan(
            evidence_id=s["evidence_id"],
            document_id=s["document_id"],
            page_number=int(s["page_number"]),
            source_reliability=s["source_reliability"],
            text=s["text"],
        )
        for s in raw["spans"]
    )
    if not spans:
        raise ValueError(f"{evidence_file} contains no spans; there is nothing to analyze")

    ids = [s.evidence_id for s in spans]
    if len(set(ids)) != len(ids):
        raise ValueError(
            f"{evidence_file} has duplicate evidence_id values; citations would be ambiguous"
        )

    return LoadedCase(manifest=manifest, spans=spans, root=root)


def available_cases(cases_dir: Path) -> list[str]:
    return sorted(p.name for p in cases_dir.iterdir() if (p / "case.json").exists())
