---
phase: 01-close-the-architecture-package
plan: 02
subsystem: handoff-documentation
tags: [mermaid, build-state-table, adr-020, adr-021, decision-support-boundary, pytest]

# Dependency graph
requires:
  - phase: 01-01
    provides: SpecialistResult/SpecialistCriterion contracts (CONT-01), the fourteen-contract
      count, and the corrected docs/handoff/contracts.md this document had to agree with
provides:
  - "docs/handoff/component-architecture.md (ARCH-01) — two Mermaid levels (packages/external
    systems, and the orchestrator's inner workflow steps), six build-state tables covering every
    component with BUILT/PLANNED/NOT OURS/DESIGNED-NOT-BUILT, sixteen DESIGNED-NOT-BUILT rows
    accounting for every ADR-020/ADR-021 cut individually, and the Q-01/Q-02/Q-03 blast-radius
    account with none described as cleared"
  - "tests/architecture/test_build_state_table.py (D-11) — parses the build-state tables and
    fails if a BUILT row's path does not resolve, a PLANNED row's path already exists, an
    unrecognised marker appears, a marker is missing, or a DESIGNED-NOT-BUILT row does not name
    its requirement id; proves on in-memory input that it can fail"
affects: [phase-1-arch-04, phase-2-orchestration, phase-3-handoff-reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mermaid fences inline in a handoff document, canonical there and never exported to an
      image file (D-09) — the first use of Mermaid in this repository's docs/handoff/ tree"
    - "Two independent tag vocabularies used side by side in one legend block: claim-confidence
      tags ([measured]/[first-party]/[secondary]/[unverified]) and build-state markers
      (BUILT/PLANNED/NOT OURS/DESIGNED-NOT-BUILT), stated as distinct rather than conflated"
    - "A markdown-table-as-contract test: a line-based parser (no markdown library dependency)
      plus a pure check_rows(rows, repo_root) -> list[str] problem-reporting function, tested
      both on the real document and on a deliberately bad in-memory table"
    - "Row plain-tuple type alias instead of dataclass/NamedTuple, to keep the test module's
      imports confined to the standard library plus pytest"

key-files:
  created:
    - docs/handoff/component-architecture.md
    - tests/architecture/test_build_state_table.py
  modified: []

key-decisions:
  - "Six build-state tables (contracts+gateway; orchestration+retrieval; review+delivery;
    evidence-base+handoff docs; not-ours; and the §5 designed-not-built table), all sharing the
    identical header row the test parses on, rather than one giant table — matches the plan's
    'one per subsystem' allowance and keeps each table's scope readable."
  - "packages/retrieval/ is used as the PLANNED path for both RETR-01 (mapping module) and
    RETR-02 (local ingestion), since ADR-021 groups both under Phase 2 without prescribing
    separate module boundaries; CLAUDE.md's target layout separately lists workers/ for
    ingestion, but that split is a Phase 2 planning decision, not one this document commits to."
  - "Row is a plain tuple[str, str, str, str, int] type alias rather than a dataclass or
    NamedTuple, so the test module's imports stay confined to pathlib, re, __future__, and
    pytest per the plan's acceptance criterion."

patterns-established:
  - "A build-state legend distinct from the claim-tagging legend, both stated in blockquotes
    before the first section heading, with an explicit sentence that the two vocabularies are
    used side by side rather than merged."
  - "A DESIGNED-NOT-BUILT table row always opens its Notes cell with the requirement id, so the
    id-presence check (and a human skim) can find it without parsing prose."

requirements-completed: [ARCH-01]

# Metrics
duration: ~20min
completed: 2026-08-11
---

# Phase 1 Plan 2: Component-Architecture Write-Up Summary

**Published `docs/handoff/component-architecture.md` — the last item blocking Milestone 1a
program sign-off — with two Mermaid diagrams, six build-state tables naming every component
BUILT/PLANNED/NOT OURS/DESIGNED-NOT-BUILT, all sixteen ADR-020/ADR-021 cuts accounted for
individually, and a parser-plus-checker test (`tests/architecture/test_build_state_table.py`)
that fails if any BUILT path doesn't resolve or any PLANNED path already exists.**

## Performance

- **Duration:** ~20 min (commits span 16:59–17:04 local; reading and drafting preceded that)
- **Started:** 2026-08-11 (approx, per STATE.md session continuity)
- **Completed:** 2026-08-11T21:04:32Z
- **Tasks:** 3/3
- **Files modified/created:** 2 (both new)

## Accomplishments

- `docs/handoff/component-architecture.md` exists, 381 lines, with exactly two `mermaid` fences
  (the outer package/external-system level and the inner orchestrator workflow level), no
  reference to any exported diagram file, and no concrete model id anywhere in the text.
- §2's outer diagram draws three explicit boundaries — iReports/AWS ingestion, iReports/ASAP,
  iReports/the human reviewer — with each boundary named again in one sentence of prose
  immediately after the diagram, satisfying ROADMAP Phase 1 success criterion 1.
- §3's inner diagram opens the orchestrator into its seven workflow steps (load, fan out,
  retrieve, call the gateway, checkpoint, pause for review, resume and emit), followed by prose
  on the deterministic shell, the durability invariants (`durability="sync"`, strict
  deserialization), and two honest notes on unbuilt-but-owed properties (model-call idempotency,
  ORCH-02; the refused-vs-clean ambiguity, ADR-021 Consequence 2).
- §4 carries six build-state tables covering contracts, the gateway and its three adapters,
  orchestration and retrieval, review and delivery, the evidence base and handoff documents, and
  the four not-ours systems.
- §5 accounts for all sixteen ADR-020/ADR-021 cut requirements (ORCH-05, BAKE-01, ARCH-03,
  ARCH-05, ARCH-02, CKPT-01..03, RETR-03, CONT-02, ROUT-01..02, VAL-01, DEL-01, HAND-02..03) as
  individual `DESIGNED-NOT-BUILT` rows, each naming its requirement id and reason, plus three
  weighted paragraphs (CKPT-01, ARCH-03, HAND-03) and an explicit sentence that RETR-01/RETR-02
  are `PLANNED` rather than cut (ADR-021).
- §6 states Q-01, Q-02, and Q-03 with their blast radius; none is described as cleared, closed,
  or resolved anywhere in the document.
- `tests/architecture/test_build_state_table.py` — `parse_build_state_rows` and `check_rows` as
  pure functions, six tests, all passing; imports confined to `pathlib`, `re`, `__future__`, and
  `pytest`; no `tests/architecture/__init__.py`; `pyproject.toml` untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: The write-up's narrative and both Mermaid diagrams (§1–§3)** - `5a4e66a` (docs)
2. **Task 2: The build-state tables and the designed-not-built account (§4–§7)** - `bece74a` (docs)
3. **Task 3: The test that keeps the build-state table honest** - `f302c52` (test)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `docs/handoff/component-architecture.md` - New. 381 lines. Header, two legend blockquotes
  (claim tagging and build-state), §1 scope/decision-support-boundary/spine statement, §2 outer
  system-context diagram + boundary prose, §3 inner orchestrator-workflow diagram + deterministic
  shell/durability/honest-notes prose, §4 six build-state tables, §5 sixteen designed-not-built
  rows + three weighted paragraphs, §6 Q-01/Q-02/Q-03 account, §7 eleven numbered sources.
- `tests/architecture/test_build_state_table.py` - New. 226 lines. `parse_build_state_rows(text)`
  (line-based table parser, no markdown-library dependency), `check_rows(rows, repo_root)` (pure
  problem-string generator covering marker validity, BUILT resolution, PLANNED non-existence and
  phase-naming, NOT OURS/DESIGNED-NOT-BUILT path/notes/requirement-id requirements, and
  traversal/absolute-path containment), six `test_*` functions including
  `test_the_check_actually_catches_a_bad_row`.

## Decisions Made

- **Six separate build-state tables, one per subsystem grouping, rather than one large table.**
  All six share the identical header row (`| Component | Build state | Path | Notes |`) the test
  parses on; splitting kept each table scannable and matched the plan's explicit "one per
  subsystem" allowance.
- **`packages/retrieval/` used as the shared PLANNED path for both RETR-01 and RETR-02.** ADR-021
  groups both requirements under Phase 2 without prescribing a package split; using one path for
  both is a documentation simplification, not a commitment that Phase 2 must implement them in a
  single module — `CLAUDE.md`'s target layout separately lists `workers/` for ingestion, and that
  question is left to Phase 2 planning.
- **`Row` as a plain `tuple[str, str, str, str, int]` type alias, not a `dataclass` or
  `NamedTuple`.** The plan's acceptance criterion checks that the test module's import lines name
  only `pathlib`, `re`, `__future__`, and `pytest`; a `dataclasses` or `typing` import would have
  added a fifth name to that list even though both are standard library.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' acceptance criteria were verified by
direct command output (grep counts, pytest, mypy, ruff, bandit) before each commit, matching the
plan's stated checks line for line.

### Out-of-scope items encountered, not fixed

- **`uv run ruff format --check` (whole repo, no path argument) still fails on
  `.planning/phases/01-close-the-architecture-package/01-PATTERNS.md:274`** — the same
  pre-existing, out-of-scope issue plan 01-01 logged in
  `.planning/phases/01-close-the-architecture-package/deferred-items.md` (predates this phase,
  committed in `16e94b7`). `uv run ruff format --check` scoped to this plan's two files
  (`docs/handoff/component-architecture.md`, `tests/architecture/test_build_state_table.py`)
  passes clean. Not touched, per the scope-boundary rule.

## Negative Proof (D-11, Task 3 acceptance)

Run by hand as required: temporarily changed the "Human disposition contract" `BUILT` row's path
in `docs/handoff/component-architecture.md` from
`packages/domain/src/ireports_domain/disposition.py` to
`packages/domain/src/ireports_domain/does_not_exist.py`, ran `uv run pytest tests/architecture -q`,
and confirmed `test_every_built_row_resolves` **failed** with a message naming the broken line and
path. Reverted the edit (`mv ... .orig ...`, verified `git diff` on the doc showed no residual
change) and re-ran the suite — 6 passed, green again.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 01-03 (ARCH-04, the entry-document refresh for `CLAUDE.md` § Current state and
  `README.md` § Status) is unaffected by and does not depend on this plan's output.
- ROADMAP Phase 1 success criteria 1–3 are structurally satisfied by this plan: a reader can point
  at all three boundaries from §2's diagram and prose; every component in §4/§5 carries exactly
  one of the four build-state markers, with all sixteen ADR-020/ADR-021 cuts named individually;
  and `tests/architecture/test_build_state_table.py` enforces both the BUILT-resolves and
  PLANNED-does-not-exist rules, proven able to fail on in-memory input. **Program-leadership
  sign-off itself (ROADMAP criterion 1's human half) remains outside this executor's scope** —
  the document and its enforcement are ready for that review, but the review itself has not
  happened.
- Repo health: `uv run pytest -q` → 126 passed, 8 skipped (up from 120/8 after plan 01-01,
  +6 new architecture tests). `ruff check` clean. `mypy --strict tests/architecture` clean.
  `uv run ruff format --check` clean on every file this plan touched (whole-repo check still
  shows the one pre-existing, unrelated `01-PATTERNS.md` finding logged above). `bandit -r
  tests/architecture -q` — 11 low-severity `B101 assert_used` findings (expected in any pytest
  file; 0 high, 0 medium). `git diff --exit-code pyproject.toml` clean — no test-path
  registration was needed.
- When Phase 2 creates `packages/orchestration/` or `packages/retrieval/`, the corresponding
  `PLANNED` rows in `docs/handoff/component-architecture.md` §4 must flip to `BUILT` in the same
  commit that creates the path — `tests/architecture/test_build_state_table.py` will fail
  otherwise, by design (D-11).

---
*Phase: 01-close-the-architecture-package*
*Completed: 2026-08-11*

## Self-Check: PASSED

All 2 referenced created files found on disk (`docs/handoff/component-architecture.md`,
`tests/architecture/test_build_state_table.py`); all 3 referenced task commit hashes (`5a4e66a`,
`bece74a`, `f302c52`) found in `git log --oneline --all`.
