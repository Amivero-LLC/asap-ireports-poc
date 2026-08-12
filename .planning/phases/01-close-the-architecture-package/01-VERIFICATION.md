---
phase: 01-close-the-architecture-package
verified: 2026-08-12T02:00:44Z
status: gaps_found
score: 4/6 must-haves cleanly verified; 2 failed (both partial regressions, narrower than the prior report); re-verification of commit 77569ff's gap-closure claim
overrides_applied: 0
supersedes:
  report: (this file's own prior contents, verified 2026-08-12T01:47:35Z, status gaps_found)
  reason: >
    Commit 77569ff claims to close all four gaps the prior report found. This is a confirmation
    pass on that claim, not a trust of the commit message: every one of the four gaps was
    independently re-derived from the current codebase. Two are fully closed. Two are only
    partially closed — the headline defect in each is fixed, but a residual, mechanically
    reproducible defect of the exact same kind (stale figures, internal self-contradiction) survives
    in the same files. Status remains gaps_found, on a materially smaller and more precisely scoped
    set of defects than the prior report.
re_verification:
  previous_status: gaps_found
  previous_score: "2/6 cleanly verified; 4 failed"
  gaps_closed:
    - "Gap 2 (schema-currency drift) is fully closed. `uv run python scripts/generate_schemas.py --check` now exits 0: 'schemas/ is current (12 contracts)'. Reproduced live, not taken from the commit message."
    - "Gap 4 (CLAUDE.md / README.md false ARCH-03 / contract-count claims) is fully closed. CLAUDE.md correctly states 12 contracts, ARCH-03 closed by ADR-023, and 160 passing tests (all independently verified against `uv run pytest -q`). README.md correctly states 'Twelve data contracts', cites ADR-023's Lambda-fit closure, and quotes '160 passed, 8 skipped' matching the live run."
    - "The core defect in Gap 3 (component-architecture.md misrepresenting ARCH-03 as unmeasured and unscheduled) is closed: the ARCH-03 row moved out of S5 DESIGNED-NOT-BUILT into a new S4 'Deployment fit' table marked BUILT, citing ADR-023 and spikes/lambda_fit/; the S6 narrative now states 'ARCH-03 is closed... ADR-012 stands' with the measured figures."
    - "The core defect in Gap 1 (contracts.md never updated for ADR-022) is closed: the contract set, version (2.0.0), the S1 table (12 contracts, HumanDisposition/ReviewSummary absent), and the S2 rule/mechanism/test table (rewritten around ADR-022 guards, citing tests that actually exist: test_no_contract_models_a_human_decision, test_no_run_state_waits_for_a_person, etc.) are all now accurate and independently confirmed."
  gaps_remaining:
    - "contracts.md S3 (Deliberate divergences) row 3 (line 131) still lists `reviewer_summary` as a current field ('optional, reviewer-authored only, language-guarded') — that field does not exist anywhere in packages/domain/ (grep confirms zero hits outside historical/removal references). This directly contradicts the file's own line 9, which lists `reviewer_summary` among the fields ADR-022 removed."
    - "contracts.md S2's 'note on the language guard' (lines 116-118) states the validator 'is not a substitute for the human review gate' in the present tense, implying a human review gate currently exists. This contradicts the file's own S5 (lines 192-197), correctly rewritten by the same commit, which states 'ADR-022 removed that gate' and that this validator is now the actual control. The document is self-contradictory about whether a human review gate currently exists."
    - "component-architecture.md line 356 still reads 'Domain contracts (fourteen Pydantic v2 models)' — actual count is 12 (confirmed via `ireports_domain.ROOT_CONTRACTS` and `ls schemas/*.schema.json`, both 12)."
    - "component-architecture.md line 358 still reads '91 tests as of CONT-01' for tests/contract/ — actual is 114 (confirmed via `uv run pytest tests/contract -q`), the same figure contracts.md and CLAUDE.md/README.md correctly carry."
    - "component-architecture.md S7 Sources (item 1) lists ADR-001 through ADR-022 but does not cite ADR-023, despite the document's own body citing ADR-023 five times (lines 409, 468, 496-502) as the source for ARCH-03's closure."
  regressions: []
gaps:
  - truth: "docs/handoff/contracts.md is internally consistent and accurately describes the current (post-ADR-022) contract set and its enforcement mechanisms, satisfying CONT-01's acceptance."
    status: partial
    reason: >
      The headline defect (14-contract v1.0.0 description, removed contracts/mechanisms/tests
      presented as current) is fixed. Two smaller, independently-discovered residual defects
      remain in the same document, both self-contradictions introduced or left in place by the
      same rewrite: (1) the S3 divergence table still lists `reviewer_summary` as an existing
      field when it was removed by ADR-022 (the same commit's own S1 breaking-change note says
      so); (2) S2's language-guard note claims the guard "is not a substitute for the human review
      gate" in the present tense, contradicting S5 of the same document, correctly updated in the
      same commit, which states the gate was removed by ADR-022 and this validator is now the
      actual control.
    artifacts:
      - path: "docs/handoff/contracts.md"
        issue: "Line 131: reviewer_summary presented as a current field; it does not exist. Lines 116-118: implies a human review gate currently exists, contradicting lines 192-197 of the same document."
    missing:
      - "Rewrite S3 row 3 (line 131) to describe the pre-ADR-022 reviewer_summary as historical (it existed under ADR-011; ADR-022 removed it) rather than as the current divergence, or delete the row and note the loss in S1's breaking-change paragraph."
      - "Rewrite lines 116-118 to match the tense and content of lines 192-197: the guard is not a substitute for exhaustive coverage of every possible phrasing, and under ADR-022 there is no longer a human review gate behind it — this validator plus ProposedFinding being the only finding type are what the decision-support boundary now rests on."
  - truth: "docs/handoff/component-architecture.md is accurate throughout, including its evidence-base figures and its Sources list, satisfying ARCH-01's sign-off acceptance."
    status: partial
    reason: >
      The headline defect (ARCH-03 presented as unmeasured/unscheduled, and named the single
      biggest risk to ADR-012) is fixed — S4 now carries a BUILT Deployment-fit row citing
      ADR-023 and spikes/lambda_fit/, and S5/S6 correctly state ARCH-03 is closed with ADR-012
      standing. But the S4 evidence-base table two rows above the fix was not touched: line 356
      still says "fourteen Pydantic v2 models" (actual 12) and line 358 still says "91 tests as of
      CONT-01" (actual 114) — the exact same stale-figure pattern this commit fixed everywhere
      else (contracts.md's own header table, CLAUDE.md, README.md all correctly show 12/114/160).
      Separately, S7 Sources was never updated to cite ADR-023, even though the document's own
      body cites it five times as the authority for ARCH-03's closure.
    artifacts:
      - path: "docs/handoff/component-architecture.md"
        issue: "Line 356: 'fourteen Pydantic v2 models' (actual 12). Line 358: '91 tests as of CONT-01' (actual 114). S7 item 1: ADR list omits ADR-023."
    missing:
      - "Update line 356 to 'twelve Pydantic v2 models' and line 358 to '114 tests' (or the then-current contract-test count)."
      - "Add ADR-023 to S7 Sources item 1's ADR list, alongside a one-line note (matching the existing ADR-022 pattern) that it is the source for ARCH-03's closure."
deferred: []
human_verification:
  - test: "Program leadership reads docs/handoff/component-architecture.md S1-S3 (both Mermaid diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS ingestion, ASAP, and the human reviewer begin, then formally signs off on the boundaries as drawn."
    expected: "Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause)."
    why_human: "Leadership decision, not a code fact — unchanged since the prior report. No sign-off artifact exists anywhere in the repo. Two small residual defects remain in the same document's S4/S7 (stale contract/test counts, missing ADR-023 citation) — cosmetic relative to the prior report's findings, but the document should not go to a signer with wrong numbers in it."
---

# Phase 1: Close the architecture package — Confirmation Pass Verification Report

**Phase Goal:** Program leadership can sign off on Milestone 1a's component boundaries, the build
has the contract it needs, and the repository's entry documents stop asserting things that are no
longer true.
**Verified:** 2026-08-12T02:00:44Z
**Status:** gaps_found
**Re-verification:** Yes — confirmation pass on commit `77569ff`'s claim to close all four gaps
from the prior report (verified 2026-08-12T01:47:35Z)

## Why this is a confirmation pass, not a fresh derivation

Commit `77569ff` claims to close all four gaps found by the prior verification. Per instructions,
that claim is not trusted — every one of the four gaps is independently re-derived against the
current codebase below. **Two of the four are fully closed. Two are partially closed:** the
headline defect that made each gap FAIL is genuinely fixed, but a second, smaller instance of the
*same kind* of defect (a stale figure, or a self-contradiction between two sections of the same
document) survives in the same file, undetected by the commit's own sweep. This is a materially
better state than the prior report — the score improves from 2/6 to 4/6, and the scope of what
remains wrong shrinks from "describes a contract set that does not exist" to "two numbers on one
table row, one citation, and one paragraph that disagrees with another paragraph 80 lines later" —
but it is not yet the state the phase goal describes ("stop asserting things that are no longer
true").

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A reader can point to where our system ends and AWS ingestion, ASAP, and the human reviewer begin (SC1, mechanical half) | ✓ VERIFIED | Unaffected by commit `77569ff` (diff touches only S4/S5/S6). §2/§3 diagrams and boundary prose re-confirmed unchanged and correct. |
| 1b | Program leadership signs off on those boundaries (SC1, human half) | ? HUMAN NEEDED | No sign-off artifact exists anywhere in the repo. Unaffected by this commit. |
| 2 | Every component marked `BUILT`/`PLANNED`/`NOT OURS`/`DESIGNED-NOT-BUILT` correctly, and a reader can sign off on the document as accurate (SC2) | ✗ FAILED (narrower than before) | ARCH-03's *classification* is now correct (moved to a new S4 "Deployment fit" table, `BUILT`, citing ADR-023 and `spikes/lambda_fit/`; S5/S6 correctly state it is closed and ADR-012 stands). But the same document's S4 evidence-base table two rows above still reads "fourteen Pydantic v2 models" (line 356, actual 12) and "91 tests as of CONT-01" (line 358, actual 114), and S7 Sources never added ADR-023 to its citation list despite the body citing it five times. |
| 3 | A test fails if a `BUILT` row does not resolve, or a `PLANNED` row already exists (SC3) | ✓ VERIFIED — no regression | `uv run pytest tests/architecture -q` → 16 passed, unchanged from the prior report. |
| 4 | `SpecialistResult` published to `schemas/` with contract tests, no aggregate score field (SC4), and CONT-01's contracts.md-updated acceptance | ✗ FAILED (narrower than before) | Schema currency gate is now live-clean: `uv run python scripts/generate_schemas.py --check` exits 0, "schemas/ is current (12 contracts)" — the ADR-023 docstring-drift bug is fixed and reproduced fixed, not taken on trust. `docs/handoff/contracts.md`'s headline defect (superseded 14-contract v1.0.0 description) is fixed: 12 contracts, v2.0.0, rule table rewritten around ADR-022 guards, every cited test name (`test_no_contract_models_a_human_decision`, `test_no_run_state_waits_for_a_person`, etc.) confirmed to exist. But the same document now self-contradicts: S3 line 131 lists `reviewer_summary` as a current field though it was removed (contradicting the same document's own line 9), and S2 lines 116-118 imply a human review gate currently exists, contradicting S5 lines 192-197 of the same document (correctly rewritten by the same commit) which states ADR-022 removed that gate. |
| 5 | `CLAUDE.md` § Current state and `README.md` § Status accurately reflect ADR-020/022/023's scope (SC5) | ✓ VERIFIED — fully fixed | `CLAUDE.md` line 64: "12 Pydantic v2 contracts... Contract set 2.0.0". Line 66-68: `lambda_fit/` cited, "160 passing, 8 skipped" (matches live run). Lines 86-89: correctly states "ARCH-03... is closed, not outstanding: ADR-020 cut it, ADR-023 measured it... and closed it." `README.md` line 29: "Twelve data contracts". Line 44-47: ADR-023 Lambda-fit closure cited with the measured figures. Line 58: "160 passed, 8 skipped" (matches live run). All independently verified against `uv run pytest -q` (160 passed, 8 skipped) and `ireports_domain.ROOT_CONTRACTS` (12 keys). |
| 6 | `SpecialistResult`'s immutability claim holds (D-06) | ✓ VERIFIED — no regression | Unaffected by this commit. `findings: tuple[ProposedFinding, ...]` unchanged; mutability-guard tests still pass within the 114-test contract suite. |

**Score:** 4/6 cleanly verified (truths 1, 3, 5, 6); 2 failed (2, 4), both narrower in scope than
the prior report's failures on the same truths; 1 of those 2 also carries the unresolved human
sign-off clause (truth 1b).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `schemas/*.schema.json` (12 files) | Generated, current with the models | ✓ VERIFIED — regression from prior report fixed | `generate_schemas.py --check` exits 0 live. |
| `docs/handoff/contracts.md` | CONT-01 deliverable, accurate for ADR-022 | ⚠️ PARTIAL — headline fixed, residual self-contradiction | 12 contracts, v2.0.0, correct rule/mechanism/test table. Line 131 and lines 116-118 contradict the rest of the same document (see gaps). |
| `docs/handoff/component-architecture.md` | ARCH-01 deliverable, accurate against current code | ⚠️ PARTIAL — ARCH-03 fixed, evidence-base figures and Sources not | S4/S5/S6 ARCH-03 classification correct. Lines 356/358 stale (14/91 vs 12/114). S7 Sources omits ADR-023. |
| `CLAUDE.md` § Current state | ARCH-04 deliverable, true now | ✓ VERIFIED — fully fixed | 12 contracts, ARCH-03 correctly closed, test count (160) matches live run. |
| `README.md` § Status | ARCH-04 deliverable, true now | ✓ VERIFIED — fully fixed | Twelve contracts, ADR-023 cited, test count (160) matches live run. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `docs/DECISIONS.md` ADR-023 | `docs/handoff/component-architecture.md` §4/§5/§6 | Row/narrative should reflect closure | ✓ WIRED — regression fixed | ARCH-03 correctly moved to S4 `BUILT`, S5/S6 narrative correct. |
| `docs/DECISIONS.md` ADR-023 | `docs/handoff/component-architecture.md` §4 evidence-base table, §7 Sources | Contract/test figures and citation should reflect the current state | ✗ **NOT WIRED** | Lines 356/358 unchanged since before ADR-022 (still 14/91); ADR-023 absent from S7 Sources despite five in-body citations. |
| `docs/DECISIONS.md` ADR-022 | `docs/handoff/contracts.md` §1/§2 (contract set, rule table) | Should update contract set, version, rule table | ✓ WIRED — regression fixed | Contract set, version, and rule/mechanism/test table all correctly rewritten. |
| `docs/DECISIONS.md` ADR-022 | `docs/handoff/contracts.md` §2 language-guard note, §3 divergence table | Should remove/update claims that assume a human review gate still exists | ✗ **NOT WIRED** | Line 131 still presents `reviewer_summary` as current; lines 116-118 still imply the gate exists, contradicting the document's own §5. |
| `packages/domain/src/ireports_domain/finding.py` docstring | `schemas/finding.schema.json` / `schemas/specialist-result.schema.json` | `scripts/generate_schemas.py` regeneration | ✓ WIRED — regression fixed | `--check` exits 0; regeneration confirmed committed. |
| `CLAUDE.md` / `README.md` | current codebase (contract count, test count, ARCH-03 status) | Direct prose claims | ✓ WIRED — fully fixed | All figures independently confirmed to match live command output. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest -q` | `160 passed, 8 skipped` in ~42s | ✓ PASS |
| Contract test suite passes | `uv run pytest tests/contract -q` | `114 passed` | ✓ PASS |
| Build-state guard passes | `uv run pytest tests/architecture -q` | `16 passed` | ✓ PASS |
| Schema currency gate | `uv run python scripts/generate_schemas.py --check` | exit 0: `schemas/ is current (12 contracts)` | ✓ PASS — regression fixed |
| Lint | `uv run ruff check` | `All checks passed!` | ✓ PASS |
| Format | `uv run ruff format --check packages tests scripts` | `22 files already formatted` | ✓ PASS |
| Types | `uv run mypy --strict packages tests scripts` | `Success: no issues found in 22 source files` | ✓ PASS |
| Security scan | `uv run bandit -r packages -q` | `0 High, 0 Medium, 3 Low` (known `B105` false positives) | ✓ PASS |
| Root contract count | `ireports_domain.ROOT_CONTRACTS` / `ls schemas/*.schema.json` | 12 and 12 | ✓ Matches `contracts.md`, `CLAUDE.md`, `README.md`; contradicts `component-architecture.md` line 356 |
| Contract test count | `uv run pytest tests/contract -q` | 114 | ✓ Matches `contracts.md`, `CLAUDE.md` (via 160 total); contradicts `component-architecture.md` line 358 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ARCH-01 | 01-02-PLAN.md | Component-architecture write-up, boundaries + build-state markers, program-leadership-signable | ✗ **FAILED** (narrower) | ARCH-03 classification fixed; evidence-base figures (356, 358) and Sources citation (§7) still wrong. Not yet signable without misleading the signer on two numbers and a missing citation. |
| ARCH-04 | 01-03-PLAN.md | Entry documents describe actual current state | ✓ **SATISFIED** | Both `CLAUDE.md` and `README.md` independently confirmed fully accurate against live command output. |
| CONT-01 | 01-01-PLAN.md | `SpecialistResult` contract published, documented, immutable, no aggregate score | ✗ **FAILED** (narrower) | Schema-currency regression fixed; contract structure/immutability hold. `contracts.md`'s headline defect fixed, but two residual self-contradictions remain in the same document. |

No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `docs/handoff/contracts.md` | 131 | `reviewer_summary` presented as a current field; field does not exist (removed by ADR-022, per the same document's line 9) | 🛑 Blocker | Self-contradiction within CONT-01's own required deliverable. |
| `docs/handoff/contracts.md` | 116-118 | Implies a human review gate currently exists ("not a substitute for the human review gate"), contradicting §5 (lines 192-197) of the same document | 🛑 Blocker | Same document gives two different answers to "does a human review gate exist" 80 lines apart. |
| `docs/handoff/component-architecture.md` | 356, 358 | Stale contract/test counts ("fourteen", "91 tests") unchanged since before ADR-022, while the same document's ARCH-03 rows were correctly updated in this commit | 🛑 Blocker | This is the ARCH-01 sign-off artifact; a signer reading S4 top-to-bottom sees a self-inconsistent evidence base. |
| `docs/handoff/component-architecture.md` | §7 | ADR-023 cited five times in the body but absent from the Sources list | ⚠️ Warning | Traceability gap on the document's own stated Sources contract, not a factual error. |

No `TBD`/`FIXME`/`XXX` markers found in any of the flagged files.

### Status of the four gaps from the prior report

| # | Gap | Status now |
|---|-----|-------------|
| 1 | `contracts.md` never updated for ADR-022 | ⚠️ Headline fixed; 2 residual self-contradictions found (lines 116-118, 131) |
| 2 | Schema-currency gate failing live | ✓ Fully closed, reproduced |
| 3 | `component-architecture.md` misrepresents ARCH-03 | ⚠️ Headline fixed; stale evidence-base figures (356, 358) and missing ADR-023 citation (§7) remain |
| 4 | `CLAUDE.md`/`README.md` false claims | ✓ Fully closed, all figures independently verified |

### Human Verification Required

### 1. Program-leadership sign-off on component boundaries

**Test:** Program leadership reads `docs/handoff/component-architecture.md` §1-§3 (both Mermaid
diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS
ingestion, ASAP, and the human reviewer begin.
**Expected:** Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause).
**Why human:** Leadership decision, not a code fact — unchanged since the prior report. No sign-off
artifact exists anywhere in the repo. Two small residual defects remain in the same document's
S4/S7 (stale contract/test counts, missing ADR-023 citation) — this is much smaller than the prior
report's findings, but the document should not go to a signer with visibly wrong numbers on the
table the ARCH-03 fix itself sits two rows below.

### Gaps Summary

Two gaps remain, both mechanically reproducible and both narrower instances of the exact category
of defect the four original gaps were about (stale figures, and — new to this pass — internal
self-contradiction within a single document):

1. **`docs/handoff/contracts.md` still contradicts itself** on whether `reviewer_summary` is a
   current field (line 131 says yes; line 9 of the same document says it was removed) and on
   whether a human review gate currently exists (lines 116-118 say "not a substitute for" it,
   implying it exists; lines 192-197 of the same document, correctly rewritten by the fix commit,
   say ADR-022 removed it).
2. **`docs/handoff/component-architecture.md` still carries two stale figures** ("fourteen
   Pydantic v2 models", "91 tests as of CONT-01" — actual 12 and 114) two rows above the correctly
   fixed ARCH-03 row, and its Sources list (§7) was never updated to cite ADR-023 despite the
   document's own body citing it five times.

Both of the prior report's other two gaps — the live schema-currency failure, and the false
ARCH-03/contract-count claims in `CLAUDE.md`/`README.md` — are confirmed fully closed, independent
of the commit message: `generate_schemas.py --check` exits 0 on a fresh run, and every figure in
`CLAUDE.md` and `README.md` was independently cross-checked against `uv run pytest -q`,
`ireports_domain.ROOT_CONTRACTS`, and `ls schemas/*.schema.json` rather than read as prose.

The phase's own goal text — "stop asserting things that are no longer true" — is not yet fully
met: two documents each still assert one thing that is no longer true, in each case immediately
adjacent to a passage the same commit correctly fixed. Given CONT-01 and ARCH-01 explicitly name
`docs/handoff/contracts.md` and `docs/handoff/component-architecture.md` as their deliverables,
these residual defects are scored as gaps blocking the phase, not deferred.

Per the decision tree (gaps found takes priority over human-needed), **status is `gaps_found`**.

---

_Verified: 2026-08-12T02:00:44Z_
_Verifier: Claude (gsd-verifier)_
_Confirmation pass on commit `77569ff`, which claimed to close all four gaps from the prior report
(verified 2026-08-12T01:47:35Z). Two of four independently confirmed fully closed; two confirmed
only partially closed, with narrower, newly-identified residual defects documented above._
