---
phase: 01-close-the-architecture-package
plan: 03
subsystem: entry-documentation
tags: [claude-md, readme, adr-020, adr-021, arch-04]

# Dependency graph
requires:
  - phase: 01-01
    provides: The fourteen-contract count and the SpecialistResult name both files now cite
  - phase: 01-02
    provides: docs/handoff/component-architecture.md — the build-state table both files now
      defer to instead of duplicating or contradicting
provides:
  - "CLAUDE.md § Current state — measured inventory (14 contracts, 7 handoff docs, 126
    passed / 8 skipped), the ADR-020/ADR-021 three-phase scope paragraph, and a § Target
    layout / § Stack that defer to docs/handoff/component-architecture.md instead of reading
    as a build commitment"
  - "README.md § Status — closed Milestone 1a with SpecialistResult and the linked write-up,
    the same three-phase scope paragraph, the measured test count, and a § Start here row
    pointing a program reader at component-architecture.md before contracts.md"
affects: [phase-1-arch-04, program-sign-off]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - CLAUDE.md
    - README.md

key-decisions:
  - "Verified before planning any edit that ARCH-04's two headline stale claims (CLAUDE.md
    saying application code does not exist; either file implying the orchestration framework
    is undecided) were already fixed in commit 4de0ad1, which predates 01-CONTEXT.md. This
    plan's real scope was ROADMAP criterion 5's third clause (the three-phase scope
    statement) plus the staleness that 01-01 and 01-02 introduced by landing, plus D-12's
    flagged Target-layout/Stack contradiction — not the two claims ARCH-04 was originally
    written against."
  - "CLAUDE.md's scope paragraph states 'eighteen requirements moved to v2' (ADR-020's
    original move, matching PROJECT.md's own wording) while README's states 'sixteen
    requirements moved to v2' (the current count in REQUIREMENTS.md § v2 § Cut by ADR-020,
    after ADR-021 struck RETR-01/RETR-02 back out as restored). Both numbers are correct for
    what each describes — verified by counting REQUIREMENTS.md's table rows, not carried
    over from either document at face value."
  - "CLAUDE.md's milestone framing line changed from 'Milestone 1 is nearly closed' to
    'Milestone 1 is closed — 1a, 1b, and 1c are all done,' and README's changed from
    'Milestone 1 in progress' to 'Milestone 1 is complete' — checked against STATE.md's
    per-milestone status (1a closes with this plan and 01-02's write-up; 1b closed
    2026-08-10; 1c closed 2026-08-11) rather than assumed."

requirements-completed: [ARCH-04]

# Metrics
duration: ~15min
completed: 2026-08-11
---

# Phase 1 Plan 3: Entry-Document Refresh Summary

**Made `CLAUDE.md` § Current state and `README.md` § Status true and mutually consistent:
both now carry the measured post-Phase-1 inventory (fourteen contracts, seven handoff
documents, 126 passed / 8 skipped), state ADR-020/ADR-021's three-phase spine scope in
`.planning/PROJECT.md`'s own words, and defer to `docs/handoff/component-architecture.md`
as the authority on what is built, planned, and designed-not-built instead of contradicting
their own scope or duplicating the build-state table.**

## Performance

- **Duration:** ~15 min (reading and verification-first per the plan's own framing;
  commits span 17:11:43–17:13:34 local)
- **Completed:** 2026-08-11T21:13:45Z
- **Tasks:** 2/2
- **Files modified:** 2 (both existing, no new files)

## Important finding, restated per the plan's `<output>` instruction

**ARCH-04's two headline stale claims were already fixed before this plan ran.** Commit
`4de0ad1` ("docs: ingest 12 docs into .planning/; fix four stale claims they exposed")
corrected both:

- `CLAUDE.md` § Current state does not say application code does not exist — verified fresh
  against the working tree before any edit, and it already read as a dated inventory table.
- `CLAUDE.md` § Stack already named LangGraph with ADR-012 accepted; `README.md` § Status
  already recorded "1c — orchestration bake-off: done. ADR-012 accepted — the framework is
  LangGraph" before this plan touched either file.

That commit predates the discussion that produced `01-CONTEXT.md`, so `.planning/STATE.md`'s
blocker list and `.planning/REQUIREMENTS.md`'s ARCH-04 acceptance should be understood as
closing on **three** distinct items, only one of which (the three-phase scope statement) was
untouched before this plan, with the other two (the staleness 01-01/01-02 introduced by
landing, and D-12's flagged Target-layout/Stack contradiction) real work this plan did. Not
all three of ARCH-04's originally-cited claims were fixed here — two were already fixed
earlier, and this plan should not be credited with re-fixing them.

## Accomplishments

**Task 1 — `CLAUDE.md`:**
- § Current state's inventory table updated: `packages/domain/` now reads fourteen contracts
  and names `SpecialistResult` / `SpecialistCriterion`; `docs/handoff/` now reads seven
  documents and names `component-architecture.md` as the seventh; `Tests` now reads 126
  passed / 8 skipped, both counts read directly off `uv run pytest -q` rather than carried
  over from a summary.
- The "Outstanding before M1 sign-off" line rewritten: the component-architecture write-up
  is no longer listed as outstanding (it landed in 01-02); what remains is cold start under
  SAM local, unmeasured, with no scheduled phase because ARCH-03 was cut by ADR-020, still
  the one number that could reopen ADR-012 — `spikes/test_scorecard.py`'s fail-until-measured
  framing kept.
- A new paragraph states the ADR-020/ADR-021 scope: "Three phases, not nine," reusing
  `.planning/PROJECT.md`'s wording verbatim; eighteen requirements moved to v2 with
  acceptance intact; ADR-021 restored retrieval while RETR-03 and CONT-02 stay cut; ADR-011
  and ADR-014 explicitly kept and NON-NEGOTIABLE; and a pointer to
  `docs/handoff/component-architecture.md`, enforced by
  `tests/architecture/test_build_state_table.py`, as the per-component authority.
- § Target layout's preamble replaced (D-12's flagged contradiction): the fenced directory
  listing is now framed as blueprint-derived and wider than the buildable scope, naming
  `policy/`, `delivery/`, `workers/`, `policy-packs/`, and `evals/` as designed-not-built and
  pointing at the build-state table — the fence itself is untouched (verified byte-identical
  via `git diff`).
- § Stack gets one added sentence beneath the decided-choices table pointing at the same
  build-state table for what is actually built; no table row changed.

**Task 2 — `README.md`:**
- § Status's 1a bullet rewritten as closed: fourteen contracts, `SpecialistResult` named and
  described as the typed return value of one specialist sub-call, and the write-up linked as
  `docs/handoff/component-architecture.md` (ARCH-01).
- The milestone framing line changed from "Milestone 1 in progress" to "Milestone 1 is
  complete" — checked against all three bullets (1a now closed by this plan and 01-02; 1b and
  1c already closed) rather than assumed.
- A new paragraph after the three bullets states the same ADR-020 scope sentence, "nothing
  was deleted," and points at `component-architecture.md` for the designed-not-built account.
- The bash block's comment updated from `# 111 passed, 8 skipped` to `# 126 passed, 8
  skipped`, read off the same `uv run pytest -q` invocation used for `CLAUDE.md`.
- § Start here gained a row for `docs/handoff/component-architecture.md`, placed above the
  `docs/handoff/contracts.md` row per the plan's ordering rationale (boundaries before
  contracts).
- § Decision-support boundary, § The central question, § Stack (decided), and § Data are
  byte-for-byte unchanged, confirmed via `git diff`.

## Task Commits

1. **Task 1: `CLAUDE.md` — current inventory, ADR-020 scope, target-layout contradiction** -
   `b7af8a8` (docs)
2. **Task 2: `README.md` — closed Milestone 1a and the narrowed scope** - `4c5d0b9` (docs)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `CLAUDE.md` - Modified. Four targeted edits within § Current state, § Target layout
  preamble, and one added sentence under § Stack. No other section touched.
- `README.md` - Modified. Four targeted edits within § Status (the 1a bullet, the milestone
  framing line, the new scope paragraph, the bash-block comment) and one new row in §
  Start here. No other section touched.

## Decisions Made

- **CLAUDE.md's scope paragraph states "eighteen requirements" (ADR-020's original move,
  matching `.planning/PROJECT.md`'s own wording); README's states "sixteen requirements"
  (the current live count in `.planning/REQUIREMENTS.md` § v2 § Cut by ADR-020, after
  ADR-021 struck RETR-01/RETR-02 back out as restored).** Counted directly from
  `REQUIREMENTS.md`'s table (18 rows, 2 struck through as restored = 16 currently cut)
  rather than assumed from either plan instruction or either document's prior wording — both
  numbers are correct for what each sentence actually describes.
- **Milestone framing changed in both files** from "nearly closed" / "in progress" to
  "closed" / "complete," checked against `.planning/STATE.md`'s explicit per-milestone
  status (1a closes with 01-02 and this plan; 1b closed 2026-08-10; 1c closed 2026-08-11)
  rather than assumed from the plan's own framing.
- **No `CONTRACT_VERSION`, schema, code, or test file touched** — `git diff --stat
  --exit-code -- packages tests schemas scripts pyproject.toml` confirmed clean before and
  after both commits.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' acceptance criteria were verified by
direct command output (`grep -c`, `grep -ci`, `git diff`, `uv run pytest -q`, `uv run ruff
check`, `uv run mypy --strict`) before each commit, matching the plan's stated checks line
for line.

### Out-of-scope items encountered, not fixed

None newly encountered. The pre-existing `uv run ruff format --check` finding on
`.planning/phases/01-close-the-architecture-package/01-PATTERNS.md:274`, logged by plan
01-01 and reconfirmed by 01-02, was not re-checked here since this plan touches no code and
`ruff format --check` was not part of this plan's own verification block.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- ROADMAP Phase 1 success criterion 5 is now TRUE and provable by grep: neither file asserts
  application code does not exist or that the orchestration framework is undecided, and both
  state ADR-020's three-phase scope in `.planning/PROJECT.md`'s own words.
- With this plan, all three Phase 1 deliverables (ARCH-01, CONT-01, ARCH-04) are complete.
  `.planning/REQUIREMENTS.md`'s ARCH-04 entry and `.planning/STATE.md`'s blocker list can now
  be closed — accurately, per the finding above, as closing the third of three originally
  described issues rather than all three being fixed by this plan alone.
- Repo health: `uv run pytest -q` → 126 passed, 8 skipped, unchanged from the end of plan
  01-02. `ruff check` clean. `mypy --strict packages tests` clean (22 source files, no
  issues). `git diff --stat --exit-code -- packages tests schemas scripts pyproject.toml`
  exits 0 both times — no code was touched by this plan.
- Phase 1 is structurally complete pending the human half of ROADMAP criterion 1
  (program-leadership sign-off on the component-architecture write-up), which remains
  outside any executor's scope.

---
*Phase: 01-close-the-architecture-package*
*Completed: 2026-08-11*

## Self-Check: PASSED

Both referenced modified files found on disk (`CLAUDE.md`, `README.md`); both referenced
task commit hashes (`b7af8a8`, `4c5d0b9`) found in `git log --oneline --all`.
