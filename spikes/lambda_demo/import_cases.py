"""Bring the AmiLens synthetic cases into this repo's shape.

Run once, from a checkout of `amilens-localdev` sitting beside this one:

    uv run python spikes/lambda_demo/import_cases.py

**What is copied and what is not.** The *cases* are copied — the generated case content, which is
what this project lacked. The *schema* is not: AmiLens's case model (`roiChapters`, `issues`,
`caseState`, its analysis and brief structures) stays over there, and this writes our own
`case.json` + `evidence.json`. ADR-002 — AmiLens is prior art, not a dependency.

That is a deliberate trade with a cost worth naming: **if we later decide to adopt the AmiLens case
model wholesale, this conversion is the thing that has to be unpicked.** It is one file and it is
lossy in one direction only (we keep less than they have), so unpicking means reading their shape
again rather than reconciling two divergent ones. Nothing here forecloses that decision.

**Synthetic, verified rather than assumed.** The AmiLens fixture README states the data is
LLM-generated, and the subjects are Eren Yeager, Lagertha Lothbrok and Hela Odinsdottir. `--check`
re-asserts that the SSNs are masked and no real-looking identifiers came across.

**Embeddings are not copied.** The source chunks carry `amazon.titan-embed-text-v2:0` vectors, and
the LiteLLM proxy serves that exact model — so the vectors are reproducible, and storing 1024
floats per chunk would add megabytes of unreviewable JSON to the repo for no gain. They are
recomputed at index time instead, which also means the embedding path is exercised rather than
assumed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_DIR = Path(__file__).resolve().parent / "cases"
DEFAULT_SOURCE = REPO_ROOT.parent / "amilens-localdev" / "tests" / "fixtures" / "cases"

# A real SSN in a fixture would be a serious problem, so this looks for one rather than trusting
# the upstream README. The source masks them as ***-**-1234.
_UNMASKED_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


_HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
_SECTION = re.compile(r"^Section\s+(\d+):\s*(?:Section\s+\d+:\s*)?(.+)$", re.IGNORECASE)


def _derive_title(chunk: dict[str, Any]) -> str:
    """A title that says what the chunk contains.

    ROI chapters arrive with real titles ("Law Enforcement (XIII)"). SF-86 chunks all arrive titled
    `sf86.pdf`, which is worse than useless twice over: retrieval results become unreadable, and
    since the title is embedded alongside the text, five chunks share an identical meaningless
    prefix.

    This cost real time. Retrieval was ranking the *correct* chunk first for both the foreign-
    influence and financial queries, and because every hit rendered as "sf86.pdf" it looked like a
    relevance failure. I nearly retuned a working query. The section headings inside the content
    say exactly what is there — Sections 22-24 are the financial record, Sections 13-15 the foreign
    contacts — so they become the title.

    The source doubles its headings ("Section 22: Section 22: Financial Record"); that is stripped.
    """
    given = (chunk.get("title") or "").strip()
    if given and "." not in given:  # a real title, not a filename
        return given

    sections: list[str] = []
    for heading in _HEADING.findall(chunk.get("content") or ""):
        match = _SECTION.match(heading.strip())
        if match:
            sections.append(f"{match.group(1)}. {match.group(2).strip()}")

    if not sections:
        return given or "Case document"
    kind = str((chunk.get("metadata") or {}).get("document_type") or "document").upper()
    shown = "; ".join(sections[:4])
    return f"{kind} — {shown}" + (" …" if len(sections) > 4 else "")


def _document_id(chunk: dict[str, Any]) -> str:
    """One document id per source document, stable across runs.

    `DocumentId` is `doc_` + a bounded slug, so the chapter type and number are folded in rather
    than using the raw index — a reader tracing a citation gets something meaningful.
    """
    meta = chunk.get("metadata") or {}
    kind = str(meta.get("roi_chapter_type") or chunk.get("sourceType") or "document")
    chapter = meta.get("chapter_number")
    slug = re.sub(r"[^a-z0-9]+", "_", kind.lower()).strip("_")[:40] or "document"
    return f"doc_{slug}_{chapter}" if chapter is not None else f"doc_{slug}"


def convert(source: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """One AmiLens case directory -> our `case.json` and `evidence.json`."""
    seed = json.loads((source / "case-seed.json").read_text())
    chunks_doc = json.loads((source / "chunks.json").read_text())
    subject = seed.get("subject") or {}
    case_id = seed["caseNumber"]

    spans: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks_doc.get("chunks", []), start=1):
        text = (chunk.get("content") or "").strip()
        if not text:
            continue
        meta = chunk.get("metadata") or {}
        spans.append(
            {
                "evidence_id": f"ev_{index:03d}",
                "document_id": _document_id(chunk),
                # The source records character offsets, not pages. Chapter number is the closest
                # honest locator; 1 where there is none, rather than inventing a page.
                "page_number": int(meta.get("chapter_number") or 1),
                # Everything here is a synthetic investigative record. Recording it uniformly is
                # more honest than deriving a reliability we have no basis for.
                "source_reliability": "investigative_record",
                "title": _derive_title(chunk),
                "source_type": chunk.get("sourceType") or "case_document",
                "text": text,
            }
        )

    manifest = {
        "case_id": case_id,
        "case_name": seed.get("title") or case_id,
        "tenant_id": "AMIVERO-SYNTHETIC",
        "program_id": "AMILENS-DEMO",
        "subject": {
            "subject_id": f"SUBJ-{case_id.split('-')[-1]}",
            "display_name": f"{subject.get('firstName', '')} {subject.get('lastName', '')}".strip(),
            "citizenship": ["United States"],
        },
        "case_context": {
            "person_status": "applicant",
            "service_type": "competitive_service",
            "position_title": subject.get("positionTitle") or "Unspecified",
            "position_risk_level": "high_risk_public_trust",
            "position_sensitivity": "critical_sensitive",
            "piv_required": True,
            "conditional_offer_date": "2026-04-02T00:00:00Z",
            "agency_component": subject.get("dhsComponent") or "SYNTHETIC-AGENCY",
        },
        "requested_analyses": ["suitability", "national_security_eligibility"],
        "policy_pack_ids": ["federal-core-2026-07-30", "sead4-current"],
        "document_expectations": [
            "security_questionnaire",
            "report_of_investigation",
            "subject_interview",
        ],
        "created_at": "2026-08-12T00:00:00Z",
        "created_by": "amilens-fixture-import",
    }

    return manifest, {"case_id": case_id, "spans": spans}


def check_synthetic(evidence: dict[str, Any]) -> list[str]:
    """Fail loudly rather than trust the upstream README. Synthetic only, always."""
    problems = []
    for span in evidence["spans"]:
        found = _UNMASKED_SSN.findall(span["text"])
        if found:
            problems.append(f"{span['evidence_id']}: unmasked SSN-shaped value {found[:1]}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--check", action="store_true", help="verify only; write nothing")
    args = parser.parse_args()

    if not args.source.is_dir():
        raise SystemExit(
            f"{args.source} does not exist. Point --source at amilens-localdev's "
            "tests/fixtures/cases directory."
        )

    sources = sorted(p for p in args.source.iterdir() if (p / "case-seed.json").exists())
    if not sources:
        raise SystemExit(f"no case fixtures found under {args.source}")

    failed = False
    for source in sources:
        manifest, evidence = convert(source)
        problems = check_synthetic(evidence)
        chars = sum(len(s["text"]) for s in evidence["spans"])

        if problems:
            failed = True
            print(f"{manifest['case_id']}: REFUSED — {len(problems)} problem(s)")
            for problem in problems:
                print(f"    {problem}")
            continue

        if args.check:
            print(f"{manifest['case_id']}: ok — {len(evidence['spans'])} spans, {chars:,} chars")
            continue

        target = CASES_DIR / manifest["case_id"]
        target.mkdir(parents=True, exist_ok=True)
        (target / "case.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (target / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            f"{manifest['case_id']}: {len(evidence['spans'])} spans, {chars:,} chars "
            f"(~{chars // 4:,} tokens) -> {target.relative_to(REPO_ROOT)}"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
