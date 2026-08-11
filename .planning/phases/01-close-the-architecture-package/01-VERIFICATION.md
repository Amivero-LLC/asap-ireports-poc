---
phase: 01-close-the-architecture-package
verified: 2026-08-11T00:00:00Z
status: gaps_found
score: 4/5 must-haves verified (1 failed structurally, 1 human-only)
overrides_applied: 0
gaps:
  - truth: "SpecialistResult is published to schemas/ with contract tests, carrying no aggregate score field, and its immutability claims hold (D-06)."
    status: failed
    reason: >
      SpecialistResult.findings is a plain `list[ProposedFinding]`. Pydantic's `frozen=True`
      blocks attribute *reassignment* only — it does not freeze list contents. A constructed,
      validated SpecialistResult can be mutated in place (`result.findings.append(...)`) to carry
      a finding from a different run, case, or criterion, silently defeating the
      `_findings_belong_to_this_criterion` cross-field validator that exists specifically to
      prevent that. docs/handoff/contracts.md line 80-81 states as a settled mechanism: "`frozen=True`
      on every contract. ADR-011's 'both versions are retained' only holds if the machine proposal
      cannot be edited in place." That claim is false for this contract's only list-valued field,
      and CLAUDE.md's non-negotiable decision-support-boundary rule ("both the original machine
      proposal and the human-approved version are retained") is the exact guarantee this defeats.
      Reproduced directly against the running package (see verification report body). Already
      identified as CR-03 (critical) in 01-REVIEW.md and unresolved as of this verification.
    artifacts:
      - path: "packages/domain/src/ireports_domain/specialist.py"
        issue: "`findings: list[ProposedFinding] = Field(default_factory=list)` — mutable collection paired with a construction-time-only cross-field invariant"
      - path: "docs/handoff/contracts.md"
        issue: "Line 80-81 states frozen=True makes every contract's machine proposal un-editable in place; false for SpecialistResult.findings"
    missing:
      - "Make findings immutable at the type level (e.g. `tuple[ProposedFinding, ...]`), or add an explicit note in contracts.md that frozen=True does not extend to collection contents and state the residual risk"
      - "Regenerate schemas/specialist-result.schema.json if the field type changes"
      - "A contract test asserting the mutation is caught (or is now impossible)"
human_verification:
  - test: "Program leadership reviews docs/handoff/component-architecture.md §2/§3 diagrams and prose and signs off on the component boundaries (where iReports ends and AWS ingestion, ASAP, and the human reviewer begin)."
    expected: "Program leadership formally signs off on the boundaries as drawn."
    why_human: "ROADMAP Phase 1 success criterion 1 explicitly requires program-leadership sign-off — this is a decision only a human stakeholder can make, and it has not yet happened. All executor-level SUMMARY and STATE.md entries confirm this remains outside any agent's scope."
---

# Phase 1: Close the architecture package — Verification Report

**Phase Goal:** Program leadership can sign off on Milestone 1a's component boundaries, the build
has the contract it needs, and the repository's entry documents stop asserting things that are no
longer true.
**Verified:** 2026-08-11
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Phase 1 success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A reader can point to where our system ends and AWS ingestion, ASAP, and the human reviewer begin, **and program leadership signs off** on those boundaries. | ? HUMAN NEEDED (mechanical half VERIFIED) | `docs/handoff/component-architecture.md` exists, 381+ lines, exactly 2 `mermaid` fences, three boundaries drawn as subgraphs with prose naming each crossing (§2). Sign-off itself has not happened — no artifact records it, and every SUMMARY.md in this phase explicitly says so. |
| 2 | Every component marked `BUILT`/`PLANNED` (naming phase)/`NOT OURS`, and every ADR-020/021 cut marked `DESIGNED-NOT-BUILT` with the reason, individually. | ✓ VERIFIED | `docs/handoff/component-architecture.md` §4/§5: 6 build-state tables (`grep -c '^| Component | Build state | Path | Notes |$'` = 6), all 16 cut requirement ids present (`ORCH-05, BAKE-01, ARCH-03, ARCH-05, ARCH-02, CKPT-01..03, RETR-03, CONT-02, ROUT-01..02, VAL-01, DEL-01, HAND-02, HAND-03` each ≥1 occurrence), `RETR-01`/`RETR-02` correctly appear as `PLANNED` (line 231-232) with an explicit sentence (line 284) explaining they are not in the cut table. |
| 3 | A test fails if a `BUILT` row does not resolve, or a `PLANNED` row already exists; the test proves on in-memory input that it can fail. | ✓ VERIFIED (literal wording), ⚠ WARNING (guard design) | `tests/architecture/test_build_state_table.py` — `test_every_built_row_resolves`, `test_no_planned_row_already_exists`, and `test_the_check_actually_catches_a_bad_row` all pass today (`uv run pytest tests/architecture -q` → 14 passed). **But** the code review (01-REVIEW.md CR-01, CR-02) found: (a) 5 of 9 problem categories `check_rows` computes are never asserted by any test — an em-dash violation, an empty-notes row, a phase-less `PLANNED` row, or a `..`-path `PLANNED` row would all pass silently; (b) all `PLANNED` rows for Phase 2 share directory-level paths (e.g. 8 rows share `packages/orchestration/`), so the first commit that creates that directory will fail 8 unrelated rows at once, and `test_all_four_markers_are_present` asserts marker-set **equality**, which becomes permanently unsatisfiable once every `PLANNED` row legitimately flips to `BUILT`. This does not falsify the literal SC3 wording today, but it means the guard will force false `BUILT` claims in Phase 2 and cannot stay green through Phase 3 without deletion — the opposite of what D-11 exists to prevent. Confirmed by direct inspection of `test_build_state_table.py:150-226`. |
| 4 | `SpecialistResult` published to `schemas/` with contract tests, no aggregate score field. | ✗ FAILED (integrity claim) | `packages/domain/src/ireports_domain/specialist.py`, `schemas/specialist-result.schema.json`, `tests/contract/test_specialist_result.py` (8 tests, all pass) all exist and are substantively correct for the fields and rules the plan specified — `extra="forbid"` and attribute-level `frozen=True` both verified live. **But** `SpecialistResult.findings` is a mutable `list[ProposedFinding]`; reproduced live: `r.findings.append(...)` succeeds silently after construction and defeats the `_findings_belong_to_this_criterion` validator's guarantee. `docs/handoff/contracts.md:80-81` asserts unqualified that `frozen=True` makes "the machine proposal... cannot be edited in place" for ADR-011 purposes — false for this field. See gap below. |
| 5 | `CLAUDE.md` § Current state and `README.md` § Status no longer assert application code does not exist or that the framework is undecided, and both reflect ADR-020's scope. | ✓ VERIFIED | `grep -i "application code does not exist\|framework is undecided\|framework has not been decided"` on both files returns nothing. Both contain "Three phases, not nine" (`.planning/PROJECT.md` wording, verbatim). `CLAUDE.md` inventory: 14 contracts, 7 handoff docs, 126 passed/8 skipped — matches `uv run pytest -q` output exactly. `README.md` § Status: "Fourteen data contracts," `SpecialistResult` named, `component-architecture.md` linked (3 occurrences, above `contracts.md` row in § Start here), "126 passed, 8 skipped" in the bash block. |

**Score:** 3/5 truths cleanly VERIFIED; 1 requires human sign-off (mechanically ready); 1 FAILED on
an integrity claim that is load-bearing for the decision-support boundary.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/domain/src/ireports_domain/specialist.py` | `SpecialistResult`/`SpecialistCriterion` contracts | ✓ VERIFIED, ⚠ integrity gap | Exists, 117 lines, both classes present, `ruff`/`mypy --strict` clean. `findings` field is mutable (CR-03). |
| `packages/domain/src/ireports_domain/__init__.py` | `SpecialistResult` registered | ✓ VERIFIED | `"specialist-result": SpecialistResult` in `ROOT_CONTRACTS`; both names in `__all__`. |
| `schemas/specialist-result.schema.json` | Generated schema, current | ✓ VERIFIED | `generate_schemas.py --check` passes (confirmed by review and by `uv run pytest -q` green); `x-contract-version` unchanged at `1.0.0`. |
| `tests/contract/test_specialist_result.py` | Contract tests for D-01..D-06 | ✓ VERIFIED, ⚠ incomplete | 8 tests, all pass. Only 1 of the validator's 5 raise branches has a failing example (WR-03, non-blocking). |
| `docs/handoff/contracts.md` | Fourteen contracts, deferral lifted | ✓ VERIFIED, ✗ one false claim | "Fourteen contracts" present, §1 row added, §5 deferral lifted, ADR-021 gap bullet added. Line 80-81's frozen=True/ADR-011 claim is now inaccurate (CR-03). |
| `docs/handoff/component-architecture.md` | Boundaries + build-state write-up | ✓ VERIFIED | 381+ lines, 2 mermaid fences, both legends, all 4 markers, all ADR/requirement ids present, no exported image files, no concrete model id, no Q-01/02/03 "cleared" language. |
| `tests/architecture/test_build_state_table.py` | Enforcing test (D-11) | ✓ VERIFIED, ⚠ under-asserted | Exists, 14 tests pass, negative proof run and recorded in 01-02-SUMMARY.md. Only 4 of 9 `check_rows` problem categories are ever asserted by a named test (CR-01); marker-set equality assertion will become unsatisfiable by end of Phase 3 (CR-02). |
| `CLAUDE.md` | True entry doc | ✓ VERIFIED | Matches repo state exactly as measured. |
| `README.md` | True entry doc, linking write-up | ✓ VERIFIED | Matches repo state, links resolve, sections outside scope untouched (confirmed via git diff in 01-03-SUMMARY.md). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `packages/domain/src/ireports_domain/__init__.py` | `ROOT_CONTRACTS` | `"specialist-result": SpecialistResult` | ✓ WIRED | Confirmed present; this is also what makes `test_no_contract_carries_an_aggregate_score` cover the new contract automatically. |
| `specialist.py` | `finding.py` | `from .finding import GeneratedBy, ProposedFinding` | ✓ WIRED | Confirmed in file; `FindingAuthority` correctly not imported. |
| `tests/architecture/test_build_state_table.py` | `docs/handoff/component-architecture.md` | Parses build-state tables, resolves paths against repo root | ✓ WIRED | `REPO_ROOT` resolved from `__file__`; `DOC_PATH` points at the real file; 14 tests run against it. |
| `docs/handoff/component-architecture.md` | `.planning/REQUIREMENTS.md` § v2 § Cut by ADR-020 | One `DESIGNED-NOT-BUILT` row per cut requirement | ✓ WIRED | All 16 cut requirement ids present with reasons, cross-checked against REQUIREMENTS.md's own table structure. |
| `CLAUDE.md` / `README.md` | `docs/handoff/component-architecture.md` | Pointer for build-state authority | ✓ WIRED | `component-architecture.md` referenced 4x in CLAUDE.md, 3x in README.md; all relative links resolve. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ARCH-01 | 01-02-PLAN.md | Component-architecture write-up, boundaries + build-state markers | ✓ SATISFIED (mechanical), sign-off pending | See truths 1-3 above. |
| ARCH-04 | 01-03-PLAN.md | Entry documents describe actual current state | ✓ SATISFIED | See truth 5 above. |
| CONT-01 | 01-01-PLAN.md | `SpecialistResult` contract published and documented | ⚠ SATISFIED WITH GAP | Contract exists, registered, schema generated, tests pass — but the handoff document's own claim about the immutability guarantee this contract depends on is false (CR-03). |

No orphaned requirements found — `.planning/REQUIREMENTS.md` maps exactly ARCH-01, ARCH-04, CONT-01
to Phase 1, and all three appear in a plan's `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `packages/domain/src/ireports_domain/specialist.py` | 71 | Mutable `list[ProposedFinding]` field on a `frozen=True` model backing a cross-field invariant | 🛑 Blocker | Defeats the validator's guarantee post-construction; contradicts a written ADR-011 claim in `docs/handoff/contracts.md` (CR-03, see gap). |
| `tests/architecture/test_build_state_table.py` | 150-226 | 5 of 9 `check_rows` problem categories have no asserting test | ⚠ Warning | The D-11 guard is less complete than its own docstring and `component-architecture.md`'s "enforced by this test" claim imply (CR-01). Not a Phase 1 blocker; a real risk for Phase 2/3. |
| `tests/architecture/test_build_state_table.py` | 190-194 | `test_all_four_markers_are_present` asserts marker-set equality, not a floor | ⚠ Warning | Guaranteed to force false `BUILT` claims mid-Phase-2 and become permanently unsatisfiable by end of Phase 3 (CR-02). |
| No `TBD`/`FIXME`/`XXX` markers found | — | — | — | Checked all files this phase modified; none present. |

No debt-marker blocker triggered (no unreferenced TBD/FIXME/XXX in phase-modified files).

### Human Verification Required

### 1. Program-leadership sign-off on component boundaries

**Test:** Program leadership reads `docs/handoff/component-architecture.md` §1-§3 (both Mermaid
diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS
ingestion, ASAP, and the human reviewer begin.
**Expected:** Explicit sign-off recorded (this is ROADMAP Phase 1 success criterion 1's second
clause, and the phase's stated top priority).
**Why human:** This is a leadership decision, not a code fact. Every SUMMARY.md in this phase
explicitly defers it and states it is out of executor scope.

### Gaps Summary

One structural gap blocks a clean pass: `SpecialistResult.findings` is a mutable Python list even
though the contract is declared `frozen=True`, and `docs/handoff/contracts.md` states as settled
fact that `frozen=True` is what makes ADR-011's "both versions retained" guarantee hold. That
statement is provably false for this field — verified live by constructing a `SpecialistResult` and
appending a finding from a different run/case/criterion after validation, with no error. Because the
whole reason `_findings_belong_to_this_criterion` exists is to guarantee a `SpecialistResult`'s
findings agree with its own identity, and because CLAUDE.md states the retained-both-versions rule
as NON-NEGOTIABLE, this is not a cosmetic defect — it is exactly the class of unbacked handoff claim
the phase exists to eliminate. It was already identified as CR-03 in `01-REVIEW.md` and remains
unresolved.

Two further defects in the D-11 enforcement guard (`tests/architecture/test_build_state_table.py`)
were found by the code review and independently confirmed here (CR-01: 5 of 9 violation categories
are never asserted by any test; CR-02: directory-granularity `PLANNED` paths plus a marker-set
equality assertion mean the guard will force false `BUILT` claims early in Phase 2 and cannot stay
green through Phase 3). These do not falsify today's literal ROADMAP success criterion 3 wording —
the two specific behaviors that criterion names (`BUILT` doesn't resolve, `PLANNED` already exists)
are both correctly enforced right now — but they represent a real risk that D-11's purpose will be
defeated the moment Phase 2 starts creating the directories its own `PLANNED` rows name. Recorded as
a warning rather than a gap because the literal Phase 1 success criterion is met; strongly
recommended to fix before Phase 2's first commit rather than let the guard start lying on day one.

Everything else checked — the fourteen-contract count, the seven handoff documents, the sixteen
DESIGNED-NOT-BUILT rows, the entry-document refresh, the repo health baseline (126 passed / 8
skipped, `ruff` clean, `mypy --strict` clean apart from the three pre-existing unrelated errors in
`test_model_gateway.py`) — is real and verified against the running repository, not against
SUMMARY.md's narration of it.

---

_Verified: 2026-08-11_
_Verifier: Claude (gsd-verifier)_
