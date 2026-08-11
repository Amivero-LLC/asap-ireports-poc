---
phase: 01-close-the-architecture-package
verified: 2026-08-11T22:16:31Z
status: human_needed
score: 4/5 must-haves verified (1 human-only; the prior structural gap is closed)
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: "3/5 clean, 1 human-only, 1 failed"
  gaps_closed:
    - "SpecialistResult is published to schemas/ with contract tests, carrying no aggregate score field, and its immutability claims hold (D-06)."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Program leadership reviews docs/handoff/component-architecture.md §2/§3 diagrams and prose and signs off on the component boundaries (where iReports ends and AWS ingestion, ASAP, and the human reviewer begin)."
    expected: "Program leadership formally signs off on the boundaries as drawn."
    why_human: "ROADMAP Phase 1 success criterion 1 explicitly requires program-leadership sign-off — this is a decision only a human stakeholder can make, and it has not yet happened. No artifact in the repo records this sign-off."
---

# Phase 1: Close the architecture package — Re-Verification Report

**Phase Goal:** Program leadership can sign off on Milestone 1a's component boundaries, the build
has the contract it needs, and the repository's entry documents stop asserting things that are no
longer true.
**Verified:** 2026-08-11T22:16:31Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (commits `898e694`, `782c6a4`)

## Scope of this pass

The prior verification (2026-08-11, `gaps_found`) failed exactly one must-have: `SpecialistResult`'s
`findings` field was a mutable `list[ProposedFinding]` on a `frozen=True` model, silently defeating
the `_findings_belong_to_this_criterion` cross-field validator after construction, while
`docs/handoff/contracts.md` claimed `frozen=True` alone made "the machine proposal... cannot be
edited in place." This gap was independently re-derived from first principles against the current
codebase, not accepted from the SUMMARY/commit-message narration.

CR-01 and CR-02 (`01-REVIEW.md`, D-11 build-state guard completeness) are unrelated to CR-03 and
untouched by the two gap-closure commits (`git diff` across both commits touches zero lines of
`tests/architecture/test_build_state_table.py` or `component-architecture.md`). Per instructions,
they are noted but not re-litigated here — they do not falsify any ROADMAP Phase 1 success criterion
as written.

## Independent Verification of the Closed Gap

### 1. Live mutation attempt

Constructed a `SpecialistResult`, then tried every realistic mutation vector against `.findings`:

```
findings type: <class 'tuple'>
append blocked: 'tuple' object has no attribute 'append'
item assignment blocked: TypeError 'tuple' object does not support item assignment
attr reassign blocked: ValidationError — "Instance is frozen [type=frozen_instance]"
```

All three vectors fail. `.findings` is a `tuple[ProposedFinding, ...]`
(`packages/domain/src/ireports_domain/specialist.py:71`), confirmed live, not just by reading the
type annotation.

### 2. Is the new guard vacuous?

Reintroduced the exact defect (`findings: list[ProposedFinding] = Field(default_factory=list)`)
directly in the working tree and re-ran the guard tests without any other change:

```
FAILED tests/contract/test_decision_support_boundary.py::test_no_contract_field_is_a_mutable_container[specialist-result-SpecialistResult]
FAILED tests/contract/test_decision_support_boundary.py::test_a_validated_result_cannot_be_given_another_cases_finding
2 failed, 15 passed, 44 deselected
```

Both new tests fail immediately and with a message naming the exact offending field. The guard is
not vacuous. File restored (`git diff` confirms zero residual change) before continuing.

`test_no_contract_field_is_a_mutable_container` is parametrized over all 14 entries of
`ROOT_CONTRACTS` (confirmed by reading `packages/domain/src/ireports_domain/__init__.py:105-120` —
14 keys, matching the claimed count) and recursively follows nested `BaseModel` fields
(`_mutable_container_fields`, `tests/contract/test_decision_support_boundary.py`). A companion
positive control (`test_the_mutability_guard_actually_catches_something`) proves the walker itself
can detect a mutable field on a throwaway model, so the parametrized sweep is not trivially
succeeding by never actually running its detection logic.

### 3. Did the tuple conversion weaken anything?

- **Scope of the fix:** `git show 898e694` converts all 37 `list[X]` sequence fields across all 9
  affected contract modules (`asap.py`, `case.py`, `disposition.py`, `document.py`, `evidence.py`,
  `finding.py`, `policy.py`, `run.py`, `specialist.py`) to `tuple[X, ...]`. `grep -rn "list\[" packages/domain/src/ireports_domain/*.py`
  shows zero remaining `list[...]` field annotations — the three residual matches are method return
  types (`disposition.py:188,217,222`) and a docstring, none of them contract fields.
- **`min_length` constraints:** Live-tested — `FindingAuthority(policy_citations=())` still raises
  `ValidationError` ("too_short" / "at least 1 item"). Constraint intact on the variadic tuple.
- **Serialization round-trip:** Live-tested — `model_dump_json()` → `model_validate_json()` on a
  `SpecialistResult` round-trips to an equal object; `findings` deserializes back to a `tuple`.
- **Schema shape / drift:** `uv run python scripts/generate_schemas.py --check` → `schemas/ is
  current (14 contracts)`. `git diff ea9cd08 HEAD -- schemas/` is empty — the entire `schemas/`
  directory has zero byte of diff across both gap-closure commits. The "identical JSON Schema,
  zero drift" claim is exactly true, not approximately true.
- **Test suite:** `uv run pytest -q` → `142 passed, 8 skipped` (matches the commit message exactly).
  `uv run pytest tests/contract -q` → `107 passed` (matches exactly). `uv run mypy --strict packages
  tests scripts` → clean, 23 source files. `uv run ruff check` → all checks passed. `uv run ruff
  format --check packages tests scripts` → `23 files already formatted`. `uv run bandit -r packages`
  → 0 high, 0 medium, 3 low (the same three known `B105` false positives on `ClearanceRequirement`
  enum members, unchanged). Every one of these figures is what `docs/handoff/contracts.md` §6 now
  claims, independently reproduced, not copied from the commit message.

No weakening found in any of the four checked dimensions.

### 4. Is the refreshed §6 accurate?

Line-by-line reproduction against the running repository — every cell matches:

| Gate (as scoped in `contracts.md` §6) | Doc claims | Independently reproduced |
|---|---|---|
| `ruff check packages tests scripts` | All checks passed | All checks passed |
| `ruff format --check packages tests scripts` | 23 files already formatted | 23 files already formatted |
| `mypy --strict packages tests scripts` | Success: 23 source files | Success: 23 source files |
| `pytest tests/contract` | 107 passed | 107 passed |
| `pytest` (whole suite) | 142 passed, 8 skipped | 142 passed, 8 skipped |
| `generate_schemas.py --check` | schemas/ is current (14 contracts) | schemas/ is current (14 contracts) |
| `bandit -r packages` | 0 high, 0 medium (3 low false positives) | 0 high, 0 medium, 3 low |

§2's revised "`frozen=True` on every contract, and no mutable container fields" paragraph
(`contracts.md:80-92`) now states the mechanism correctly: names the specific gap (`frozen=True`
blocks rebinding, not content mutation), states the concrete fix (`tuple[X, ...]`), names the
enforcing test, and names the negative control. This is an accurate description of what the code
now does, not an overstated claim.

**One residual documentation-accuracy defect found, not present in the original gap list:**
`contracts.md` lines 18 and 24 still read "The rules, asserted. 91 tests." and
`uv run pytest tests/contract -q  # 91 passed` — both stale by 16 (the actual count is 107, per
§6 and per independent reproduction above). These two lines existed before the CR-03 fix (set at
56→91 during the original CONT-01 work) and were not touched by either gap-closure commit, even
though the same 782c6a4 commit explicitly re-verified and refreshed §6's count on the very same
page. This is a small, non-blocking instance of exactly the class of stale-figure problem the
phase exists to eliminate — flagged as a warning, not a gap, because it does not touch any
must-have truth (§1's own count is not part of any ROADMAP success criterion or CONT-01
requirement wording) and does not misstate the immutability fix itself.

## Goal Achievement — Updated Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A reader can point to where our system ends and AWS ingestion, ASAP, and the human reviewer begin, **and program leadership signs off** on those boundaries. | ? HUMAN NEEDED (mechanical half unchanged, still VERIFIED) | Unaffected by this gap closure — the two commits touch only contract field types and `contracts.md`. No sign-off artifact exists anywhere in the repo (`git log`, `.planning/STATE.md` both silent on it). |
| 2 | Every component marked `BUILT`/`PLANNED`/`NOT OURS`, and every ADR-020/021 cut marked `DESIGNED-NOT-BUILT` individually. | ✓ VERIFIED (unchanged) | `component-architecture.md` untouched by this gap closure (`git diff` empty). Regression check: file unchanged, so prior VERIFIED status stands. |
| 3 | A test fails if a `BUILT` row does not resolve, or a `PLANNED` row already exists; the test proves on in-memory input that it can fail. | ✓ VERIFIED (literal wording, unchanged), ⚠ WARNING (guard design, unchanged) | `tests/architecture/test_build_state_table.py` untouched by this gap closure (`git diff` empty, `pytest tests/architecture -q` → 6 passed). CR-01/CR-02 remain open exactly as before — out of scope for this re-verification per task instructions, and they do not falsify the literal SC3 wording. |
| 4 | `SpecialistResult` published to `schemas/` with contract tests, no aggregate score field, **and its immutability claims hold**. | ✓ VERIFIED — **gap closed** | Live mutation blocked on every vector (append, item-assignment, attribute-reassignment). Guard test confirmed non-vacuous by reintroducing the defect and watching it fail, then restoring. All 37 sequence fields across all 14 contracts converted, zero schema drift, `min_length` intact, round-trip intact, all cited figures independently reproduced exact. `contracts.md:80-92` now states the real mechanism. See sections 1-4 above. |
| 5 | `CLAUDE.md` § Current state and `README.md` § Status no longer assert application code does not exist or the framework is undecided, and reflect ADR-020's scope. | ✓ VERIFIED (unchanged) | Neither file touched by this gap closure (`git diff --name-only ea9cd08 HEAD` does not include `CLAUDE.md` or `README.md`). Regression check: files unchanged, prior VERIFIED status stands. |

**Score:** 4/5 truths cleanly VERIFIED (up from 3/5); 1 still requires human sign-off — unchanged and
unaffected by this gap closure, because it is a leadership action, not a code fact.

### Required Artifacts (delta only — full table unchanged from prior report for untouched artifacts)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/domain/src/ireports_domain/specialist.py` | `SpecialistResult`/`SpecialistCriterion` contracts | ✓ VERIFIED, integrity gap closed | `findings: tuple[ProposedFinding, ...]`. `ruff`/`mypy --strict` clean. Live-mutation-proof, confirmed. |
| `packages/domain/src/ireports_domain/{asap,case,disposition,document,evidence,finding,policy,run}.py` | 37 sequence fields immutable | ✓ VERIFIED | `grep -rn "list\[" packages/domain/src/ireports_domain/*.py` returns zero contract-field matches (only method return types and a docstring). |
| `schemas/specialist-result.schema.json` (and all 13 other schemas) | Generated schema, current, zero drift | ✓ VERIFIED | `--check` passes; `git diff ea9cd08 HEAD -- schemas/` is empty. |
| `tests/contract/test_decision_support_boundary.py` | New ADR-011 mutability guard | ✓ VERIFIED, non-vacuous | `test_no_contract_field_is_a_mutable_container` (14-way parametrized), `test_the_mutability_guard_actually_catches_something` (positive control), `test_a_validated_result_cannot_be_given_another_cases_finding` (concrete cross-case repro). All three independently confirmed to fail when the defect is reintroduced. |
| `docs/handoff/contracts.md` | Accurate immutability claim, refreshed §6 | ✓ VERIFIED, ⚠ new minor drift | §2 mechanism paragraph now accurate. §6 figures all independently reproduced exact. Lines 18/24 ("91 tests") are stale by 16 — pre-existing, not touched by the fix, non-blocking (see §4 above). |

### Key Link Verification (delta only)

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/contract/test_decision_support_boundary.py` | `ireports_domain.ROOT_CONTRACTS` | `@pytest.mark.parametrize("stem,model", sorted(ROOT_CONTRACTS.items()))` | ✓ WIRED | Confirmed 14 parametrized cases collected; sweep follows nested `BaseModel` fields via `_mutable_container_fields` recursion. |
| `SpecialistResult.findings` | Pydantic frozen-instance enforcement | `tuple[ProposedFinding, ...]` + `ContractModel(frozen=True)` | ✓ WIRED | Live-tested: append/item-assign/attr-reassign all fail with the expected exception types. |

### Requirements Coverage — Updated

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ARCH-01 | 01-02-PLAN.md | Component-architecture write-up, boundaries + build-state markers | ✓ SATISFIED (mechanical), sign-off pending | Unchanged — untouched by this gap closure. |
| ARCH-04 | 01-03-PLAN.md | Entry documents describe actual current state | ✓ SATISFIED | Unchanged — untouched by this gap closure. |
| CONT-01 | 01-01-PLAN.md | `SpecialistResult` contract published and documented | ✓ SATISFIED — **upgraded from "SATISFIED WITH GAP"** | Contract exists, registered, schema generated, tests pass, and the immutability guarantee the handoff document depends on now actually holds and is mechanically enforced. |

No orphaned requirements. Same three requirements (ARCH-01, ARCH-04, CONT-01) map to Phase 1 in
`.planning/REQUIREMENTS.md`, all three still appear in plan frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `docs/handoff/contracts.md` | 18, 24 | "91 tests" / "91 passed" stale by 16 (actual: 107) | ⚠ Warning (new, minor) | Pre-existing lines not touched by the CR-03 fix, on the same page whose §6 was explicitly refreshed for accuracy in the same commit. Does not misstate the immutability fix; does not touch a must-have truth. Recommend a follow-up one-line fix but does not block phase sign-off. |
| `tests/architecture/test_build_state_table.py` | 150-226 | 5 of 9 `check_rows` categories unasserted (CR-01) | ⚠ Warning (carried forward, unchanged) | Unrelated to CR-03, untouched by this gap closure. Confirmed via `git diff` — zero lines changed. Does not falsify the literal Phase 1 SC3 wording. |
| `tests/architecture/test_build_state_table.py` | 190-194 | Marker-set equality will become unsatisfiable in Phase 3 (CR-02) | ⚠ Warning (carried forward, unchanged) | Same as above — untouched, out of scope for this re-verification. |
| No `TBD`/`FIXME`/`XXX` markers found in any file touched by the gap-closure commits | — | — | — | `grep -n "TBD\|FIXME\|XXX"` across all 12 files in `git diff --name-only ea9cd08 HEAD` returns nothing. |

No debt-marker blocker triggered.

### Human Verification Required

### 1. Program-leadership sign-off on component boundaries

**Test:** Program leadership reads `docs/handoff/component-architecture.md` §1-§3 (both Mermaid
diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS
ingestion, ASAP, and the human reviewer begin.
**Expected:** Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause).
**Why human:** This is a leadership decision, not a code fact. Nothing in this gap-closure pass
changed that — `component-architecture.md` was not touched by either commit, and no sign-off
artifact exists anywhere in the repo.

### Gaps Summary

The one structural gap from the prior verification — `SpecialistResult.findings` mutable after
`frozen=True` validation, defeating `_findings_belong_to_this_criterion` and falsifying
`contracts.md`'s ADR-011 claim — is closed. Independently reproduced, not taken from SUMMARY/commit
narration:

- Live mutation blocked on all three realistic vectors (append, item-assignment, attribute
  reassignment).
- The new guard test is not vacuous: reintroducing the exact defect in the working tree
  (temporarily, then restored — confirmed by `git diff` showing zero residual change) makes both
  new tests fail with a message naming the offending field.
- The fix was applied repo-wide (37 fields, 9 modules, all 14 contracts) rather than to
  `SpecialistResult` alone, which is necessary because `contracts.md` claims frozen-ness for every
  contract — a narrower fix would have left that broader claim false again.
- No weakening: `min_length` constraints, serialization round-trip, and JSON Schema shape are all
  unchanged (`schemas/` has literally zero bytes of diff across both commits).
- Every numeric gate figure the refreshed `contracts.md` §6 now claims (ruff, mypy, bandit, pytest,
  schema check) was independently reproduced and matches exactly.

One new, non-blocking documentation-accuracy defect was found in the course of this re-verification:
`contracts.md` lines 18 and 24 still say "91 tests" / "91 passed", now stale by 16 against the
current 107. This is not part of any ROADMAP success criterion or the CONT-01 requirement text, and
it was not introduced by the fix (the lines were simply not touched), so it is recorded as a warning
for a follow-up commit rather than a gap blocking this phase.

CR-01 and CR-02 (D-11 build-state guard completeness, `01-REVIEW.md`) remain open exactly as they
were in the prior verification. They are unrelated to CR-03, confirmed untouched by either
gap-closure commit (`git diff` across both commits touches zero lines of
`tests/architecture/test_build_state_table.py` or `component-architecture.md`), and per this
re-verification's explicit instructions they are noted, not re-litigated, and do not block this
phase because they do not falsify the literal wording of ROADMAP Phase 1 success criterion 3.

The only remaining item is the human sign-off clause of ROADMAP success criterion 1, which has never
been mechanically verifiable and is unaffected by this gap-closure work. Per the classification
rules for this verification, that alone routes the phase to `human_needed`, not `passed` — all
must-have truths that are code facts are now verified, and no gap remains open in the frontmatter
sense.

---

_Verified: 2026-08-11T22:16:31Z_
_Verifier: Claude (gsd-verifier)_
