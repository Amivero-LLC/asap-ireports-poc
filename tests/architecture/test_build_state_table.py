"""Enforces the build-state tables in `docs/handoff/component-architecture.md` (D-11).

`CLAUDE.md`'s state narrative went stale in this repository once already and nothing caught it —
that is the entire reason this test exists. It parses every four-column build-state table in the
component-architecture write-up and fails if a `BUILT` row's path does not resolve, a `PLANNED`
row's path already exists, an unrecognised marker appears, a marker is missing entirely, or a
`DESIGNED-NOT-BUILT` row does not name the requirement it cuts.

Two properties of this module exist because the first version of it failed on both (CR-01, CR-02
in `01-REVIEW.md`):

- **Every problem the checker can report is asserted.** The first version filtered `check_rows`
  output by substring — `"BUILT path" in p` and so on — and five of its nine categories matched no
  filter, so they were computed and thrown away. A `DESIGNED-NOT-BUILT` row with a real path
  instead of an em dash failed nothing. Problems now carry a machine-readable code, the document
  test asserts there are **no problems at all** rather than no problems of a named kind, and
  `test_every_problem_code_has_a_failing_example` proves each code can still fire. A new category
  is covered the moment it is added; forgetting to write its test is itself a test failure.

- **`PLANNED` rows name distinct paths.** The first version let eight rows share
  `packages/orchestration/`. Creating that directory for any one of them would have failed all
  eight at once, and the write-up's own instruction — flip the row to `BUILT` in the same commit —
  would then have produced six false `BUILT` claims. `planned-duplicate-path` forbids the sharing,
  so each row flips independently when its own file lands.

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

# One problem: (code, human-readable message). The code is what tests assert on; the message is
# what a failing developer reads. Filtering on the message text is what CR-01 was.
Problem = tuple[str, str]

INVALID_MARKER = "invalid-marker"
BUILT_UNSAFE_PATH = "built-unsafe-path"
BUILT_OUTSIDE_REPO = "built-outside-repo"
BUILT_MISSING = "built-missing"
PLANNED_UNSAFE_PATH = "planned-unsafe-path"
PLANNED_OUTSIDE_REPO = "planned-outside-repo"
PLANNED_EXISTS = "planned-exists"
PLANNED_NO_PHASE = "planned-no-phase"
PLANNED_DUPLICATE_PATH = "planned-duplicate-path"
PATH_NOT_EM_DASH = "path-not-em-dash"
NO_NOTES = "no-notes"
DNB_NO_REQUIREMENT = "dnb-no-requirement"

ALL_PROBLEM_CODES = frozenset(
    {
        INVALID_MARKER,
        BUILT_UNSAFE_PATH,
        BUILT_OUTSIDE_REPO,
        BUILT_MISSING,
        PLANNED_UNSAFE_PATH,
        PLANNED_OUTSIDE_REPO,
        PLANNED_EXISTS,
        PLANNED_NO_PHASE,
        PLANNED_DUPLICATE_PATH,
        PATH_NOT_EM_DASH,
        NO_NOTES,
        DNB_NO_REQUIREMENT,
    }
)
"""Every code `check_rows` can emit.

`test_every_problem_code_has_a_failing_example` asserts this set is exactly the set of codes the
negative-control table exercises, so a category cannot be added without a test proving it fires.
"""


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


def _contained_path(path: str, repo_root: Path) -> tuple[Path | None, str | None]:
    """Resolve `path` under `repo_root`, or return the code naming why it was refused.

    Shared by the `BUILT` and `PLANNED` branches, which previously carried byte-identical copies
    of this logic (IN-01). Divergence between two copies is how a check ends up applied to one
    marker and not the other — the exact shape of bug this module exists to catch in prose.
    """
    if _is_unsafe_path(path):
        return None, "unsafe"
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        return None, "outside"
    return resolved, None


def check_rows(rows: list[Row], repo_root: Path) -> list[Problem]:
    """Return one `(code, message)` per violation; empty when the tables are honest."""
    problems: list[Problem] = []
    planned_paths_seen: dict[str, int] = {}

    for _component, marker, path, notes, line_number in rows:
        if marker not in VALID_MARKERS:
            problems.append(
                (
                    INVALID_MARKER,
                    f"line {line_number}: marker {marker!r} is not one of {sorted(VALID_MARKERS)}",
                )
            )
            continue

        if marker == "BUILT":
            resolved, refusal = _contained_path(path, repo_root)
            if refusal == "unsafe":
                problems.append(
                    (
                        BUILT_UNSAFE_PATH,
                        f"line {line_number}: BUILT path {path!r} is absolute or contains '..'",
                    )
                )
                continue
            if refusal == "outside":
                problems.append(
                    (
                        BUILT_OUTSIDE_REPO,
                        f"line {line_number}: BUILT path {path!r} resolves outside the repo root",
                    )
                )
                continue
            assert resolved is not None  # narrowed by the two refusal branches above
            if not resolved.exists():
                problems.append(
                    (
                        BUILT_MISSING,
                        f"line {line_number}: BUILT path {path!r} does not resolve to a real "
                        "file or directory",
                    )
                )

        elif marker == "PLANNED":
            resolved, refusal = _contained_path(path, repo_root)
            if refusal == "unsafe":
                problems.append(
                    (
                        PLANNED_UNSAFE_PATH,
                        f"line {line_number}: PLANNED path {path!r} is absolute or contains '..'",
                    )
                )
                continue
            if refusal == "outside":
                problems.append(
                    (
                        PLANNED_OUTSIDE_REPO,
                        f"line {line_number}: PLANNED path {path!r} resolves outside the repo root",
                    )
                )
                continue
            assert resolved is not None  # narrowed by the two refusal branches above

            if path in planned_paths_seen:
                problems.append(
                    (
                        PLANNED_DUPLICATE_PATH,
                        f"line {line_number}: PLANNED path {path!r} is already claimed by the "
                        f"row on line {planned_paths_seen[path]}. Each PLANNED row must name the "
                        "distinct file that will hold it, so that creating one capability flips "
                        "one row rather than falsely implicating every row sharing a directory",
                    )
                )
            else:
                planned_paths_seen[path] = line_number

            if resolved.exists():
                problems.append(
                    (
                        PLANNED_EXISTS,
                        f"line {line_number}: PLANNED path {path!r} already exists; it must be "
                        "flipped to BUILT in the commit that creates it",
                    )
                )
            if not PLANNED_PHASE_PATTERN.search(notes):
                problems.append(
                    (
                        PLANNED_NO_PHASE,
                        f"line {line_number}: PLANNED row's notes do not name a phase "
                        "(expected 'Phase N')",
                    )
                )

        else:  # NOT OURS or DESIGNED-NOT-BUILT
            if path != "—":
                problems.append(
                    (
                        PATH_NOT_EM_DASH,
                        f"line {line_number}: {marker} row's path must be an em dash, got {path!r}",
                    )
                )
            if not notes:
                problems.append((NO_NOTES, f"line {line_number}: {marker} row has no notes"))
            if marker == "DESIGNED-NOT-BUILT" and not REQUIREMENT_ID_PATTERN.search(notes):
                problems.append(
                    (
                        DNB_NO_REQUIREMENT,
                        f"line {line_number}: DESIGNED-NOT-BUILT row's notes do not name a "
                        "requirement id",
                    )
                )

    return problems


def _load_document_rows() -> list[Row]:
    if not DOC_PATH.exists():
        pytest.fail(f"expected the build-state document at {DOC_PATH}, but it does not exist")
    return parse_build_state_rows(DOC_PATH.read_text())


# ---------------------------------------------------------------------------
# The document itself
# ---------------------------------------------------------------------------


def test_the_document_has_no_build_state_problems() -> None:
    """The whole guard, asserted exhaustively.

    Deliberately asserts on *every* problem rather than a filtered subset. The previous version
    ran six tests that between them ignored five of nine categories (CR-01); this one cannot
    develop that gap, because a new category is in scope the moment `check_rows` can emit it.
    """
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    assert not problems, "\n".join(message for _code, message in problems)


def test_designed_not_built_is_never_quietly_dropped() -> None:
    """The section that is easiest to delete and hardest to notice missing.

    Asserts presence of `DESIGNED-NOT-BUILT` specifically, and that no marker outside the
    vocabulary appears. It deliberately does **not** require one row of each of the four markers.
    The previous version asserted set *equality*, which meant that when Phase 3 legitimately
    empties the last `PLANNED` row, the only way to green the suite would be to invent a
    permanently false row (CR-02).
    """
    markers = {marker for _, marker, _, _, _ in _load_document_rows()}
    assert "DESIGNED-NOT-BUILT" in markers, (
        "no DESIGNED-NOT-BUILT row remains — §5 accounts for what ADR-020 and ADR-021 cut, and "
        "dropping it is how a handoff quietly starts reading as complete"
    )
    assert markers <= VALID_MARKERS, sorted(markers - VALID_MARKERS)


def test_planned_rows_name_distinct_paths() -> None:
    """Named separately from the exhaustive test because its failure has a specific remedy.

    Two PLANNED rows sharing a directory means the first commit under that directory fails both,
    and the write-up's flip instruction then invites a false BUILT claim for the row that is not
    actually built (CR-02).
    """
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    duplicates = [m for code, m in problems if code == PLANNED_DUPLICATE_PATH]
    assert not duplicates, "\n".join(duplicates)


# ---------------------------------------------------------------------------
# The guard's own guards — every category must be able to fire
# ---------------------------------------------------------------------------

# One crafted document per problem code. Each must produce its own code; the completeness test
# below asserts this table covers every code in ALL_PROBLEM_CODES.
BAD_DOCUMENTS: dict[str, str] = {
    INVALID_MARKER: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Bad marker | `SOMEDAY` | — | not one of the four |
""",
    BUILT_UNSAFE_PATH: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Traversal | `BUILT` | `../outside_repo` | rejected before resolving |
""",
    BUILT_MISSING: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Missing path | `BUILT` | `packages/does_not_exist/` | never created |
""",
    PLANNED_UNSAFE_PATH: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Traversal | `PLANNED` | `/etc/passwd` | Phase 2, TEST-01 |
""",
    PLANNED_EXISTS: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Already built | `PLANNED` | `packages/domain/` | Phase 2, TEST-01 |
""",
    PLANNED_NO_PHASE: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| No phase named | `PLANNED` | `packages/not_yet/` | TEST-01 |
""",
    PLANNED_DUPLICATE_PATH: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| First claimant | `PLANNED` | `packages/not_yet/thing_a.py` | Phase 2, TEST-01 |
| Second claimant | `PLANNED` | `packages/not_yet/thing_a.py` | Phase 2, TEST-02 |
""",
    PATH_NOT_EM_DASH: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Should be an em dash | `DESIGNED-NOT-BUILT` | `packages/somewhere/` | cut by TEST-01 |
""",
    NO_NOTES: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| No notes | `NOT OURS` | — |  |
""",
    DNB_NO_REQUIREMENT: """
| Component | Build state | Path | Notes |
|---|---|---|---|
| Unnamed cut | `DESIGNED-NOT-BUILT` | — | cut, but no requirement id given |
""",
}


SYMLINK_CODES = frozenset({BUILT_OUTSIDE_REPO, PLANNED_OUTSIDE_REPO})
"""Codes unreachable from document text alone.

Covered by `test_a_symlink_out_of_the_repo_is_caught` instead. Writing the first version of the
negative-control table surfaced this: no path string can reach the `is_relative_to` branch,
because `_is_unsafe_path` rejects absolute paths and `..` segments first. The branch is real
defence — a symlink inside the repo pointing out of it resolves outside without either marker —
but it needs a filesystem to demonstrate, not a string. Recording that here is the point; a
branch nobody can trigger is a branch nobody should trust.
"""


@pytest.mark.parametrize("code", sorted(ALL_PROBLEM_CODES - SYMLINK_CODES))
def test_every_problem_code_has_a_failing_example(code: str) -> None:
    """No category may be dead code.

    CR-01's root cause was five categories that were computed and then matched no assertion. A
    category that cannot be shown to fire is indistinguishable from one that never fires.
    """
    rows = parse_build_state_rows(BAD_DOCUMENTS[code])
    codes = {c for c, _ in check_rows(rows, REPO_ROOT)}
    assert code in codes, f"{code!r} did not fire; got {sorted(codes)}"


@pytest.mark.parametrize(
    "marker,expected",
    [("BUILT", BUILT_OUTSIDE_REPO), ("PLANNED", PLANNED_OUTSIDE_REPO)],
)
def test_a_symlink_out_of_the_repo_is_caught(marker: str, expected: str, tmp_path: Path) -> None:
    """The containment check, demonstrated on the only input that can actually reach it.

    A relative path with no `..` segment still escapes the repository if a directory along it is
    a symlink. `Path.resolve()` follows it; `is_relative_to` is what notices.
    """
    outside = (tmp_path / "outside").resolve()
    outside.mkdir()
    root = (tmp_path / "root").resolve()
    root.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)

    doc = f"""
| Component | Build state | Path | Notes |
|---|---|---|---|
| Escaping symlink | `{marker}` | `escape` | Phase 2, TEST-01 |
"""
    codes = {c for c, _ in check_rows(parse_build_state_rows(doc), root)}
    assert expected in codes, f"{expected!r} did not fire; got {sorted(codes)}"


def test_the_negative_controls_cover_every_code() -> None:
    """Adding a problem code without a failing example is itself a failure.

    This is the mechanism that keeps CR-01 from recurring: the coverage is enforced, not
    remembered. Every code is demonstrated either by a crafted document or by the symlink test.
    """
    covered = set(BAD_DOCUMENTS) | SYMLINK_CODES
    assert covered == ALL_PROBLEM_CODES, {
        "codes with no example": sorted(ALL_PROBLEM_CODES - covered),
        "examples for unknown codes": sorted(covered - ALL_PROBLEM_CODES),
    }
