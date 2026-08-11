"""Enforces the build-state tables in `docs/handoff/component-architecture.md` (D-11).

`CLAUDE.md`'s state narrative went stale in this repository once already and nothing caught it —
that is the entire reason this test exists. It parses every four-column build-state table in the
component-architecture write-up and fails if a `BUILT` row's path does not resolve, a `PLANNED`
row's path already exists, an unrecognised marker appears, a marker is missing entirely, or a
`DESIGNED-NOT-BUILT` row does not name the requirement it cuts.

Path handling is the one place this test touches untrusted-shaped input (T-01-10): the document is
repo-controlled, not attacker-controlled, but a path string parsed out of prose is still contained
rather than trusted. An absolute path or one containing a `..` segment is reported as a problem
before it is ever resolved; a resolved path is checked with `Path.is_relative_to(repo_root)`; and
the only filesystem operation ever performed on a resolved path is `Path.exists()`. Nothing here
reads, imports, executes, or globs the contents of what it finds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/architecture/test_build_state_table.py -> tests/architecture -> tests -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOC_PATH = REPO_ROOT / "docs" / "handoff" / "component-architecture.md"

HEADER_LINE = "| Component | Build state | Path | Notes |"
SEPARATOR_PREFIX = "|---|---|---|---|"

VALID_MARKERS = frozenset({"BUILT", "PLANNED", "NOT OURS", "DESIGNED-NOT-BUILT"})

PLANNED_PHASE_PATTERN = re.compile(r"Phase \d")
REQUIREMENT_ID_PATTERN = re.compile(r"[A-Z]{3,5}-\d{2}")

# One row: (component, marker, path, notes, source_line_number). A plain tuple rather than a
# named type, so this module adds no import beyond the standard library and pytest.
Row = tuple[str, str, str, str, int]


def _strip_cell(cell: str) -> str:
    cell = cell.strip()
    if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`"):
        cell = cell[1:-1]
    return cell


def parse_build_state_rows(text: str) -> list[Row]:
    """Line-based parser for every table whose header is the D-11 build-state header, verbatim.

    Finds each occurrence of `HEADER_LINE`, skips the following separator line if present, then
    reads subsequent `|`-prefixed lines as rows until a line that is not `|`-prefixed. Uses only
    string splitting — no markdown table library, consistent with this repo's preference for
    ordinary code over machinery.
    """
    rows: list[Row] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() != HEADER_LINE:
            i += 1
            continue

        j = i + 1
        if j < len(lines) and lines[j].strip().startswith(SEPARATOR_PREFIX):
            j += 1

        while j < len(lines) and lines[j].startswith("|"):
            cells = lines[j].split("|")
            # A well-formed row "| a | b | c | d |" splits into
            # ['', ' a ', ' b ', ' c ', ' d ', ''] — six or more fields.
            if len(cells) >= 6:
                rows.append(
                    (
                        _strip_cell(cells[1]),
                        _strip_cell(cells[2]),
                        _strip_cell(cells[3]),
                        _strip_cell(cells[4]),
                        j + 1,
                    )
                )
            j += 1
        i = j

    return rows


def _is_unsafe_path(path: str) -> bool:
    """Absolute, or containing a `..` segment. Checked before any resolution is attempted."""
    if not path or path.startswith("/"):
        return True
    return ".." in Path(path).parts


def check_rows(rows: list[Row], repo_root: Path) -> list[str]:
    """Return one human-readable problem string per violation; empty when the table is honest."""
    problems: list[str] = []

    for _component, marker, path, notes, line_number in rows:
        if marker not in VALID_MARKERS:
            problems.append(
                f"line {line_number}: marker {marker!r} is not one of {sorted(VALID_MARKERS)}"
            )
            continue

        if marker == "BUILT":
            if _is_unsafe_path(path):
                problems.append(
                    f"line {line_number}: BUILT path {path!r} is absolute or contains '..'"
                )
                continue
            resolved = (repo_root / path).resolve()
            if not resolved.is_relative_to(repo_root):
                problems.append(
                    f"line {line_number}: BUILT path {path!r} resolves outside the repo root"
                )
                continue
            if not resolved.exists():
                problems.append(
                    f"line {line_number}: BUILT path {path!r} does not resolve to a real "
                    "file or directory"
                )

        elif marker == "PLANNED":
            if _is_unsafe_path(path):
                problems.append(
                    f"line {line_number}: PLANNED path {path!r} is absolute or contains '..'"
                )
                continue
            resolved = (repo_root / path).resolve()
            if not resolved.is_relative_to(repo_root):
                problems.append(
                    f"line {line_number}: PLANNED path {path!r} resolves outside the repo root"
                )
                continue
            if resolved.exists():
                problems.append(
                    f"line {line_number}: PLANNED path {path!r} already exists; it must be "
                    "flipped to BUILT in the commit that creates it"
                )
            if not PLANNED_PHASE_PATTERN.search(notes):
                problems.append(
                    f"line {line_number}: PLANNED row's notes do not name a phase "
                    "(expected 'Phase N')"
                )

        else:  # NOT OURS or DESIGNED-NOT-BUILT
            if path != "—":
                problems.append(
                    f"line {line_number}: {marker} row's path must be an em dash, got {path!r}"
                )
            if not notes:
                problems.append(f"line {line_number}: {marker} row has no notes")
            if marker == "DESIGNED-NOT-BUILT" and not REQUIREMENT_ID_PATTERN.search(notes):
                problems.append(
                    f"line {line_number}: DESIGNED-NOT-BUILT row's notes do not name a "
                    "requirement id"
                )

    return problems


def _load_document_rows() -> list[Row]:
    if not DOC_PATH.exists():
        pytest.fail(f"expected the build-state document at {DOC_PATH}, but it does not exist")
    return parse_build_state_rows(DOC_PATH.read_text())


def test_every_built_row_resolves() -> None:
    """A BUILT row whose path does not resolve is a false claim (ROADMAP Phase 1 criterion 3)."""
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    built_problems = [p for p in problems if "BUILT path" in p]
    assert not built_problems, "\n".join(built_problems)


def test_no_planned_row_already_exists() -> None:
    """A PLANNED row whose path already exists must be flipped to BUILT in that commit."""
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    planned_problems = [p for p in problems if "already exists" in p]
    assert not planned_problems, "\n".join(planned_problems)


def test_every_marker_is_one_of_the_four() -> None:
    """No marker outside the D-10 vocabulary: BUILT, PLANNED, NOT OURS, DESIGNED-NOT-BUILT."""
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    marker_problems = [p for p in problems if "is not one of" in p]
    assert not marker_problems, "\n".join(marker_problems)


def test_all_four_markers_are_present() -> None:
    """At least one row of each marker exists, so DESIGNED-NOT-BUILT can't be quietly dropped."""
    rows = _load_document_rows()
    markers = {marker for _, marker, _, _, _ in rows}
    assert markers == VALID_MARKERS, markers


def test_designed_not_built_rows_name_a_requirement() -> None:
    """Every DESIGNED-NOT-BUILT row's notes carry a requirement id — a cut cannot go unnamed."""
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    requirement_problems = [p for p in problems if "do not name a requirement id" in p]
    assert not requirement_problems, "\n".join(requirement_problems)


def test_the_check_actually_catches_a_bad_row() -> None:
    """A build-state check with no failing example in its own suite cannot be trusted to work."""
    bad_doc = """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Missing path | `BUILT` | `packages/does_not_exist/` | never created |
| Already built | `PLANNED` | `packages/domain/` | Phase 2, TEST-01 |
| Bad marker | `SOMEDAY` | — | not one of the four |
| Traversal attempt | `BUILT` | `../outside_repo` | should be rejected before resolving |
"""
    rows = parse_build_state_rows(bad_doc)
    assert len(rows) == 4

    problems = check_rows(rows, REPO_ROOT)
    assert len(problems) >= 4
    assert any("does not resolve" in p for p in problems)
    assert any("already exists" in p for p in problems)
    assert any("is not one of" in p for p in problems)
    assert any("absolute or contains" in p for p in problems)
