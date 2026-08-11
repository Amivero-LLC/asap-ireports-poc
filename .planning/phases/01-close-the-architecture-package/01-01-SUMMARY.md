---
phase: 01-close-the-architecture-package
plan: 01
subsystem: domain-contracts
tags: [pydantic-v2, json-schema, contract-tests, langgraph-orchestration]

# Dependency graph
requires:
  - phase: 00 (pre-GSD milestone 1a/1b/1c work)
    provides: ContractModel, FindingAuthority, GeneratedBy, ProposedFinding, CONTRACT_VERSION,
      ROOT_CONTRACTS, the generate_schemas.py currency gate, and the ADR-014 no-aggregate-score
      schema-walking test that SpecialistResult now inherits for free
provides:
  - "SpecialistResult and SpecialistCriterion contracts (CONT-01), registered in ROOT_CONTRACTS
    and published to schemas/specialist-result.schema.json"
  - "A cross-field validator proving one specialist sub-call's findings agree with its own
    run_id, case_id, and criterion"
  - "docs/handoff/contracts.md corrected to fourteen contracts, with SpecialistResult no longer
    listed as deferred and ADR-021's empty-findings/clean-criterion gap recorded in §5"
affects: [phase-2-orchestration-fanout, spec-01]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sibling-type-not-subclass divergence, recorded in the docstring rather than left silent
      (SpecialistCriterion vs. FindingAuthority, D-04)"
    - "model_validator(mode=\"after\") cross-field consistency check naming the offending
      finding_id and field in its ValueError, following run.py's _delivery_requires_review shape"

key-files:
  created:
    - packages/domain/src/ireports_domain/specialist.py
    - schemas/specialist-result.schema.json
    - tests/contract/test_specialist_result.py
    - .planning/phases/01-close-the-architecture-package/deferred-items.md
  modified:
    - packages/domain/src/ireports_domain/__init__.py
    - docs/handoff/contracts.md

key-decisions:
  - "SpecialistCriterion is the criterion-descriptor type name, as proposed in 01-CONTEXT.md's
    discretionary-decisions note; not changed during execution."
  - "CONTRACT_VERSION stays at 1.0.0 — adding a root contract changes no existing contract's
    shape, so no bump was made. Recorded as a parenthetical in contracts.md's header."
  - "The docstring for SpecialistCriterion and the module docstring avoid the literal substrings
    the plan's acceptance criteria forbid (FindingAuthority, policy_citations, status,
    is_complete, incomplete_reason, BudgetConsumption, information_gaps, min_length) by
    paraphrasing rather than naming the sibling type and omitted fields directly — the
    divergence is still recorded, just without the grep-caught literal strings."

patterns-established:
  - "A contract module documents what it deliberately omits, by paraphrase where a literal
    forbidden-substring check applies, rather than silently leaving the omission unexplained."

requirements-completed: [CONT-01]

# Metrics
duration: ~14min
completed: 2026-08-11
---

# Phase 1 Plan 1: SpecialistResult Contract Summary

**Published `SpecialistResult`/`SpecialistCriterion` as Pydantic v2 contracts (14th and 15th
root/nested types) — the typed, three-field-only return value of one specialist sub-agent call,
with a cross-field validator and eight new contract tests proving D-01 through D-06, and
`docs/handoff/contracts.md` corrected to describe fourteen contracts instead of thirteen.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-08-11T18:55:00Z (approx, per STATE.md)
- **Completed:** 2026-08-11T19:08:15Z
- **Tasks:** 3/3
- **Files modified/created:** 6 (2 new source/schema, 1 new test, 1 modified `__init__.py`,
  1 modified `docs/handoff/contracts.md`, 1 new `deferred-items.md`)

## Accomplishments

- `SpecialistResult` and `SpecialistCriterion` exist in
  `packages/domain/src/ireports_domain/specialist.py`, registered in `ROOT_CONTRACTS` under the
  `specialist-result` stem, and published to `schemas/specialist-result.schema.json`.
- A `model_validator(mode="after")` (`_findings_belong_to_this_criterion`) rejects any
  `SpecialistResult` whose findings disagree with its own `run_id`, `case_id`, or criterion,
  naming the offending `finding_id` and mismatched field in the error.
- Eight new contract tests in `tests/contract/test_specialist_result.py` assert D-01 through
  D-06 individually, including a negative case proving the new validator actually fails on a
  bad input.
- `docs/handoff/contracts.md` updated: header count (thirteen → fourteen), the §1 contract
  table, the §5 deferred-contracts bullet (SpecialistResult removed, the remaining deferrals'
  reasons disambiguated as CONT-02-cut vs. Q-02-blocked), a new §5 bullet recording ADR-021's
  empty-findings/clean-criterion gap, and §6's verification table re-run and corrected.
- Fixed a stale command/count mismatch in `contracts.md`'s header (`uv run pytest -q` paired
  with a contract-scoped `# 56 passed` comment) — the command now reads
  `uv run pytest tests/contract -q` and the count (91) matches what that command prints.

## Task Commits

1. **Task 1: Define SpecialistResult and SpecialistCriterion, register them, generate the
   schema** - `ba58a53` (feat)
2. **Task 2: Contract tests asserting D-01 through D-06** - `aa04dcd` (test)
3. **Task 3: Lift the deferral in docs/handoff/contracts.md** - `5ae54ae` (docs; also carries a
   Rule 1 fix to Task 2's test file, see Deviations below)

**Plan metadata:** pending (this commit)

## Files Created/Modified

- `packages/domain/src/ireports_domain/specialist.py` - `SpecialistCriterion` (4 fields: the
  authority sibling minus `policy_citations`) and `SpecialistResult` (`schema_version`, `run_id`,
  `case_id`, `criterion`, `generated_by`, `findings: list[ProposedFinding] = []`), plus the
  criterion-consistency validator.
- `packages/domain/src/ireports_domain/__init__.py` - imports, `ROOT_CONTRACTS` entry, `__all__`
  entries for `SpecialistCriterion` / `SpecialistResult`.
- `schemas/specialist-result.schema.json` - generated by `scripts/generate_schemas.py`; not
  hand-written. `x-contract-version` stays `"1.0.0"`.
- `tests/contract/test_specialist_result.py` - 8 tests: zero-findings validity (D-05), absence
  of any completion-field spelling at both the Python and schema level (D-02), absence of
  budget/token/consumption field names (D-03), the criterion descriptor's exact 4-field shape
  (D-04), `extra="forbid"` / `frozen=True` / JSON round-trip (D-06), and the validator's negative
  case.
- `docs/handoff/contracts.md` - four targeted edits per Task 3's action list, plus a
  correction to §6's verification table for internal consistency.
- `.planning/phases/01-close-the-architecture-package/deferred-items.md` - new; logs two
  pre-existing, out-of-scope issues found during verification (see Deviations).

## Decisions Made

- **`SpecialistCriterion` name kept as proposed** — 01-CONTEXT.md's discretionary note said
  "nothing turns on it," and no reason emerged during execution to change it.
- **No `CONTRACT_VERSION` bump** — as directed by the plan's objective. Recorded explicitly in
  `contracts.md`'s header rather than left implicit.
- **Docstring wording chosen to avoid literal forbidden substrings while still recording the
  divergence.** The plan's Task 1 acceptance criteria required both (a) explicitly documenting
  in the class docstring that `SpecialistCriterion` omits `FindingAuthority`'s `policy_citations`
  field, and (b) that `specialist.py` contain no occurrence of the literal substrings
  `FindingAuthority`, `policy_citations`, `status`, `is_complete`, `incomplete_reason`,
  `BudgetConsumption`, `information_gaps`, or `min_length` anywhere in the file — these two
  requirements are in tension for a literal grep. Resolved by paraphrasing throughout (e.g. "the
  per-finding authority type" instead of naming `FindingAuthority`, "policy citation ids"
  instead of `policy_citations`) so the divergence is still explained in full but the exact
  grep-checked strings do not appear. Verified: `grep` for all eight substrings returns zero
  matches in `specialist.py`, and the semantic content the acceptance criteria was protecting
  (documented omission, documented absent fields) is present in prose.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `mypy --strict` error only visible when `packages/domain` and
`tests/contract` are checked together**
- **Found during:** Task 3, running the plan's full `<verification>` block (which checks
  `packages/domain tests/contract` in one invocation, unlike Task 2's own narrower
  `<verify>` of `tests/contract` alone).
- **Issue:** `test_a_constructed_result_cannot_be_mutated` assigns to a frozen field
  (`result.case_id = ...`) inside a `pytest.raises` block. When mypy checks `tests/contract` in
  isolation, `ireports_domain` resolves as an installed, stub-less package and mypy treats its
  types as `Any` — so the frozen-field write raises no static error and an inline
  `# type: ignore[misc]` there is *unused* (a separate strict-mode error). When mypy checks
  `packages/domain` and `tests/contract` together, mypy instead reads `ireports_domain`'s real
  source types, correctly infers the field is read-only, and the assignment becomes a genuine
  `[misc]` error requiring the ignore. Task 2's own narrow verify command passed either way,
  which is why this only surfaced when running the plan-level combined check.
- **Fix:** Re-added `# type: ignore[misc]` on the one line that needs it depending on which
  mypy invocation is used; left the `extra_field=...` line (Task 2's other candidate `# type:
  ignore`) without one, since no invocation flags it.
- **Files modified:** `tests/contract/test_specialist_result.py`
- **Verification:** `uv run mypy --strict packages/domain tests/contract` now shows zero errors
  attributable to this file (3 remaining errors are pre-existing, in `test_model_gateway.py`,
  unrelated — see below).
- **Committed in:** `5ae54ae` (folded into the Task 3 commit, since it was discovered while
  verifying Task 3's changes)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug)
**Impact on plan:** Necessary for `mypy --strict` correctness under the plan's actual
verification command. No scope creep — touched only the one line that needed it.

### Out-of-scope items logged, not fixed

Both pre-existing (confirmed via `git log` to predate this plan's first commit) and outside
01-01's declared `files_modified`. Logged in
`.planning/phases/01-close-the-architecture-package/deferred-items.md` per the scope-boundary
rule rather than fixed:

1. `uv run ruff format --check` (whole repo, no path arg) fails on
   `.planning/phases/01-close-the-architecture-package/01-PATTERNS.md:274` — ruff's Markdown
   formatter would collapse a multi-line docstring inside an embedded ` ```python ` fence. Every
   file this plan actually touched is individually clean under `ruff format --check`.
2. `uv run mypy --strict tests/contract` reports 3 pre-existing errors in
   `tests/contract/test_model_gateway.py` (two `import-untyped`, one `misc` subclass-of-`Any`),
   confirmed present since commit `fbb4594` and unrelated to `SpecialistResult`.

## Issues Encountered

None beyond the deviation and the two logged out-of-scope items above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `SpecialistResult` is the contract Phase 2's fan-out (SPEC-01, ORCH-01) will return from each
  specialist sub-call. Nothing in Phase 2 is blocked on this plan's output.
- The known gap this plan documents (an empty `findings` list is indistinguishable from a clean
  criterion at the artifact level, per ADR-021) is a Phase-2-relevant fact now recorded in
  `docs/handoff/contracts.md` §5 rather than only in `docs/DECISIONS.md` — a Phase 2 planner
  reading the contract handoff will see it without also having to read the ADR.
- Repo health: `ruff check` clean, `mypy --strict packages/domain tests/contract` clean except
  the two pre-existing out-of-scope items above, `pytest -q` 120 passed / 8 skipped (up from the
  111/8 baseline), `bandit -r packages/domain -q` shows only the three documented `B105` false
  positives, `pip-audit` clean.
- Plans 01-02 (ARCH-01, the component-architecture write-up) and 01-03 (ARCH-04, the entry-doc
  refresh) are unaffected by and do not depend on this plan's output beyond the now-corrected
  "Fourteen contracts" count they should not contradict.

---
*Phase: 01-close-the-architecture-package*
*Completed: 2026-08-11*

## Self-Check: PASSED

All 6 referenced files found on disk; all 3 referenced commit hashes (`ba58a53`, `aa04dcd`,
`5ae54ae`) found in `git log --oneline --all`.
