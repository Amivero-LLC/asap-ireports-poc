---
phase: 01-close-the-architecture-package
verified: 2026-08-12T03:15:00Z
status: gaps_found
score: 5/6 must-haves cleanly verified; 1 failed (narrower than any prior report, and newly discovered rather than a re-check of a known item)
overrides_applied: 0
supersedes:
  report: (this file's own prior contents, verified 2026-08-12T02:00:44Z, status gaps_found)
  reason: >
    This is a final confirmation pass, requested independently of commit messages, on commits
    e173ee6, 9dbb08e, and f241b0d (CI addition and closure of the two gaps the 02:00:44Z report
    found), plus two threat-model claims that report did not check. All four of those are
    independently confirmed closed below — every hand-recorded figure was re-derived by running
    the actual command, not read as prose, and the CI workflow was read line-by-line against every
    document that now describes it. But the adversarial sweep this pass required (checking
    CLAUDE.md and README.md's Milestone-1 status claims, not just their contract/test counts) found
    one previously undetected defect: CLAUDE.md's "Current state" section asserts Milestone 1 is
    closed in one sentence and that program-leadership sign-off is still outstanding three sentences
    later, and README.md's "Status" section asserts Milestone 1 is complete with no mention
    anywhere in the file that a sign-off is still pending. This defect predates all four prior
    verification passes on this phase (introduced in commit b7af8a8, 2026-08-11 17:11:43) and was
    missed by every one of them, including this pass's own predecessor.
re_verification:
  previous_status: gaps_found
  previous_score: "4/6 cleanly verified; 2 failed"
  gaps_closed:
    - "contracts.md line 131 (S3 divergence table): reviewer_summary is now correctly described as historical — \"ADR-011 kept it as a reviewer-authored `reviewer_summary`; ADR-022 removed even that, since no reviewer exists at this point in the pipeline\" — consistent with line 9's breaking-change note. Independently re-read; no residual contradiction found."
    - "contracts.md lines 116-118 (language-guard note): now reads \"Under ADR-011 that was tolerable because an in-run review gate stood behind it; that gate is gone, so this validator and the fact that ProposedFinding is the only finding type are what the decision-support boundary now rests on\" — past tense, consistent with S5 (lines 196-197) of the same document. Independently re-read; no residual contradiction found."
    - "component-architecture.md line 356: now reads \"Domain contracts (twelve Pydantic v2 models)\" — matches the independently re-derived count of 12 (`ireports_domain.ROOT_CONTRACTS` has 12 keys; `ls schemas/*.schema.json` lists 12 files)."
    - "component-architecture.md line 358: now reads \"114 tests\" for tests/contract/ — matches `uv run pytest tests/contract -q` → 114 passed, reproduced live."
    - "component-architecture.md §7 Sources item 1: ADR list now includes ADR-023 alongside ADR-001 through ADR-022. Confirmed by direct read of line 568."
    - "checkpoint-threat-model.md T2: no longer relies on \"retain both machine proposal and approved version (ADR-011)\" as a current mitigation; now states \"there is no approved version here any more — ASAP holds it\" and reframes the threat as pre-delivery alteration. Confirmed by direct read of line 99."
    - "checkpoint-threat-model.md T3: no longer cites the ADR-011 HumanDisposition gate as an existing control; now states \"ADR-022 removed that gate\" and names the actual compensating control (envelope pinned machine_generated, no approval field). Confirmed by direct read of line 100."
    - "CI infrastructure: `.github/workflows/quality.yml` exists, is well-formed, and was read line by line. The `gates` job runs `ruff check`, `ruff format --check`, `mypy --strict`, `generate_schemas.py --check`, `pytest tests -q`, and `bandit -r packages -q --severity-level medium`, in that order, on every push and PR. The `spikes` job runs the three-candidate bake-off against a live PostgreSQL 17 service container and fails the build if the JUnit XML shows any skipped test. Every document that now describes this workflow (contracts.md lines 223-228, component-architecture.md lines 357 and 440) was checked against the actual YAML and is accurate. WR-07 and WR-14 in 01-REVIEW.md, which recorded the prior absence of CI, are correctly superseded."
  gaps_remaining:
    - "CLAUDE.md line 56 (\"Milestone 1 is closed — 1a, 1b, and 1c are all done\") self-contradicts line 83 (\"Outstanding before M1 sign-off: program-leadership sign-off on the component boundaries\") three sentences later. Newly found, not a residual of a previously reported gap."
    - "README.md line 27 (\"Milestone 1 is complete.\") is the entire content of the § Status header — no sentence anywhere in the 115-line file mentions that program-leadership sign-off is still pending, even though 01-HUMAN-UAT.md and CLAUDE.md both currently track it as unresolved. Newly found."
  regressions: []
gaps:
  - truth: "CLAUDE.md § Current state and README.md § Status no longer assert that application code does not exist or that the orchestration framework is undecided, and both reflect ADR-020's scope (SC5 / ARCH-04), without asserting a milestone-completion state that is not yet true."
    status: failed
    reason: >
      Both of SC5's two named false claims (app code doesn't exist; orchestration undecided) are
      gone, and every contract/test-count figure independently re-derived matches. But this phase's
      own goal text is broader than SC5's letter — "the repository's entry documents stop asserting
      things that are no longer true" — and CLAUDE.md and README.md, ARCH-04's own named
      deliverables, both currently assert an unqualified "Milestone 1 is closed / complete" while
      the same milestone's own exit criterion (ROADMAP SC1: program leadership signs off on the
      component boundaries) has not happened. CLAUDE.md's own next paragraph and 01-HUMAN-UAT.md
      both currently track that sign-off as outstanding. This is not a re-detection of the two
      gaps a prior pass found and this commit closed — it is a new instance of the identical defect
      category (an entry document over-claiming completion), located in the same two files, that
      none of the four prior verification passes on this phase caught.
    artifacts:
      - path: "CLAUDE.md"
        issue: "Line 56: \"Milestone 1 is closed — 1a, 1b, and 1c are all done\" directly contradicts line 83's \"Outstanding before M1 sign-off: program-leadership sign-off on the component boundaries... tracked in 01-HUMAN-UAT.md\" three sentences later in the same section."
      - path: "README.md"
        issue: "Line 27: \"Milestone 1 is complete.\" is the entire § Status lede and is never qualified anywhere in the file — a reader of README.md alone has no way to learn that program-leadership sign-off has not happened."
    missing:
      - "Rewrite CLAUDE.md line 56 to distinguish '1a/1b/1c artifacts are complete and ready for sign-off' from 'Milestone 1 is closed', e.g. 'Milestone 1's artifacts are complete; 1a, 1b, and 1c have all produced their deliverables' — leaving the closure claim to wait until the paragraph at line 83 no longer lists an outstanding sign-off."
      - "Add one sentence to README.md § Status, immediately under 'Milestone 1 is complete.' (or in place of it), stating that program-leadership sign-off on the component boundaries is the one remaining item and pointing to component-architecture.md / 01-HUMAN-UAT.md, matching the caveat CLAUDE.md already carries (once CLAUDE.md's own wording is fixed to not contradict itself)."
deferred:
  - truth: "docs/handoff/orchestration-scorecard.md and orchestration-scorecard.json's recommendation_rationale still state 'Cold start under SAM local — not run' / 'have NOT been measured for any candidate' (last touched by commit 284b26e, 2026-08-11 06:41:39, before ADR-023 measured and closed ARCH-03 at 21:00:15 the same day)."
    addressed_in: "Out of this phase's requirement scope (ARCH-01/ARCH-04/CONT-01 name component-architecture.md, CLAUDE.md, README.md, and contracts.md — not orchestration-scorecard.md, a 1c deliverable). Flagged here as an observation, not scored as a phase gap. .planning/ROADMAP.md's Phase 1 plan list and PROJECT.md do not name this file; commit 1a160b9 rescoped what remained of pre-Phase-1 validation work rather than reopening 1c. Whoever next touches ADR-023-adjacent documents should sweep this file too — it is the same defect category as the two gaps this phase closed, just in a document this phase's requirements do not own."
    evidence: "docs/handoff/orchestration-scorecard.md line 33: 'Cold start under SAM local | not run | not run | not run'; line 80: 'Cold start under SAM local has not been measured for any candidate.' docs/handoff/orchestration-scorecard.json line 167's recommendation_rationale repeats the same claim. component-architecture.md and CLAUDE.md, by contrast, both correctly state ARCH-03 is closed by ADR-023."
human_verification:
  - test: "Program leadership reads docs/handoff/component-architecture.md §1-§3 (both Mermaid diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS ingestion, ASAP, and the human reviewer begin, then formally signs off on the boundaries as drawn."
    expected: "Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause)."
    why_human: "Leadership decision, not a code fact — unchanged since the first report on this phase. No sign-off artifact exists anywhere in the repo; 01-HUMAN-UAT.md itself records this as 'pending' with 0 of 1 tests passed. component-architecture.md itself is now accurate (all four prior figure/citation defects independently confirmed closed this pass) — the document is ready to be signed, but the signature has not happened, and CLAUDE.md/README.md incorrectly imply it has (see gaps above)."
---

# Phase 1: Close the architecture package — Final Confirmation Pass

**Phase Goal:** Program leadership can sign off on Milestone 1a's component boundaries, the build
has the contract it needs, and the repository's entry documents stop asserting things that are no
longer true.
**Verified:** 2026-08-12T03:15:00Z
**Status:** gaps_found
**Re-verification:** Yes — final confirmation pass on commits e173ee6 (residual-defect fix),
9dbb08e and f241b0d (CI addition), following the 02:00:44Z report (status gaps_found, 4/6).

## What this pass checked, and how

Nothing here was taken from a commit message. Every claim below was independently reproduced:

- The two gaps the 02:00:44Z report left open (`contracts.md` self-contradictions;
  `component-architecture.md` stale figures and missing citation) were re-read directly from the
  current file content at the cited line numbers.
- The two threat-model claims the task flagged (T2, T3 in `checkpoint-threat-model.md`) were
  re-read directly, and cross-checked against the ADR-022 text they now describe.
- `.github/workflows/quality.yml` was read in full and compared, gate by gate, against every
  sentence in `contracts.md` and `component-architecture.md` that now describes CI.
- Every hand-recorded figure in `CLAUDE.md`, `README.md`, `contracts.md`, and
  `component-architecture.md` was re-derived by running the actual command (see Behavioral
  Spot-Checks) rather than trusted as prose — this has been the recurring defect class in this
  phase (five prior incidents, now a sixth, below).
- The full test suite, schema-currency gate, mypy, ruff, ruff format, bandit, and the
  architecture guard were all re-run from a clean working tree (`git status` confirmed no
  uncommitted changes) to confirm no regression.
- Beyond the specific items the task named, both entry documents were read start to finish (not
  just grepped for known phrases) looking for new self-contradictions of the same kind the prior
  gaps were — this is what surfaced the one new finding below.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A reader can point to where our system ends and AWS ingestion, ASAP, and the human reviewer begin (SC1, mechanical half) | ✓ VERIFIED | `component-architecture.md` §1-§3 diagrams and boundary prose re-confirmed unchanged and correct; unaffected by the commits under review. |
| 1b | Program leadership signs off on those boundaries (SC1, human half) | ? HUMAN NEEDED | No sign-off artifact exists anywhere in the repo. `01-HUMAN-UAT.md` records it as pending (0/1). Unchanged since the first report on this phase. |
| 2 | Every component marked `BUILT`/`PLANNED`/`NOT OURS`/`DESIGNED-NOT-BUILT` correctly, and the document is accurate throughout, satisfying SC2 and ARCH-01 | ✓ VERIFIED — fully closed this pass | ARCH-03 classification correct (S4 `BUILT`, citing ADR-023 and `spikes/lambda_fit/`). Line 356 now reads "twelve Pydantic v2 models" (12, confirmed). Line 358 now reads "114 tests" (confirmed live). §7 Sources now cites ADR-023 (confirmed, line 568). |
| 3 | A test fails if a `BUILT` row does not resolve, or a `PLANNED` row already exists (SC3) | ✓ VERIFIED — no regression | `uv run pytest tests/architecture -q` → 16 passed. |
| 4 | `SpecialistResult` published to `schemas/` with contract tests, no aggregate score field (SC4), and CONT-01's contracts.md-updated acceptance | ✓ VERIFIED — fully closed this pass | `generate_schemas.py --check` exits 0 live: "schemas/ is current (12 contracts)". `contracts.md` line 131 now correctly presents `reviewer_summary` as historical (ADR-011, removed by ADR-022). Lines 116-118 now correctly state the review gate "is gone" (past tense), consistent with §5. No residual self-contradiction found on a full re-read. |
| 5 | `CLAUDE.md` § Current state and `README.md` § Status accurately reflect ADR-020/022/023's scope, without over-claiming milestone completion (SC5 / ARCH-04) | ✗ **FAILED — new finding, not a re-check** | SC5's two literal claims (app code doesn't exist; orchestration undecided) are gone, and every figure matches live output. But CLAUDE.md line 56 ("Milestone 1 is closed — 1a, 1b, and 1c are all done") contradicts line 83 ("Outstanding before M1 sign-off: program-leadership sign-off...") in the same section. README.md line 27 ("Milestone 1 is complete.") is unqualified anywhere in the 115-line file. Neither statement was touched by any of the fix commits (`b7af8a8`, the commit that introduced the CLAUDE.md line, predates all four verification passes on this phase). |
| 6 | `SpecialistResult`'s immutability claim holds (D-06) | ✓ VERIFIED — no regression | `findings: tuple[ProposedFinding, ...]` unchanged; mutability-guard tests still pass within the 114-test contract suite. |

**Score:** 5/6 cleanly verified (truths 1, 2, 3, 4, 6); 1 failed (truth 5), newly discovered by
this pass rather than a residual instance of a previously reported gap; 1 unresolved human clause
(truth 1b), unchanged since the first report on this phase.

### Threat-Model Claims (task-specified re-check)

| Claim | Prior wording (superseded) | Current wording | Status |
|-------|------------------------------|------------------|--------|
| T3 mitigation | "The gate is a state transition over `HumanDisposition` records... `package` refuses unless every proposal has one." | "ADR-011's mitigation was a gate over `HumanDisposition` records that `package` refused to pass without; ADR-022 removed that gate... What remains is the transition table and re-validation on load." | ✓ VERIFIED — no longer cites a control that does not exist |
| T2 mitigation | "...retain both machine proposal and approved version (ADR-011)." | "**Note ADR-022 narrows this:** the 'retain both machine proposal and approved version' leg was ADR-011's, and there is no approved version here — ASAP holds it. An alteration before delivery reaches ASAP as though it were ours." | ✓ VERIFIED — no longer asserts a current approved-version leg |

### CI Verification (task-specified re-check)

`.github/workflows/quality.yml` read in full. Two jobs:

| Job | Steps | Matches document claims? |
|-----|-------|---------------------------|
| `gates` | checkout → install uv → `uv sync --locked --all-extras --dev` → `ruff check packages tests scripts spikes` → `ruff format --check packages tests scripts spikes` → `mypy --strict packages tests scripts` → `generate_schemas.py --check` → `pytest tests -q` → `bandit -r packages -q --severity-level medium` | ✓ Yes. `contracts.md` lines 223-228 and `component-architecture.md` line 357/440 describe exactly this. |
| `spikes` | checkout → install uv → sync → `pytest spikes -q --junitxml=spikes-results.xml` against a live PostgreSQL 17 service → parse the JUnit XML and `sys.exit` with a failure message if any test was skipped | ✓ Yes. Matches `component-architecture.md`'s description of the bake-off retained in full and run on every push, and the explicit "fail if any leg was skipped" guard the task described. |

Both jobs trigger `on: push` (`branches: ["**"]`) and `pull_request`. `spikes` correctly excludes
`spikes/lambda_fit/` (ARCH-03) with an explanatory comment (lines 128-132) — a SAM-local, host-load
sensitive measurement that a shared runner would report unreliably; this matches ADR-023's own
"load sensitivity, not false precision" framing. No discrepancy found between the workflow and any
document that describes it.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `schemas/*.schema.json` (12 files) | Generated, current with the models | ✓ VERIFIED | `generate_schemas.py --check` exits 0 live: "schemas/ is current (12 contracts)". |
| `docs/handoff/contracts.md` | CONT-01 deliverable, accurate for ADR-022 | ✓ VERIFIED — fully closed this pass | 12 contracts, v2.0.0, correct rule/mechanism/test table, no residual self-contradiction found. |
| `docs/handoff/component-architecture.md` | ARCH-01 deliverable, accurate against current code | ✓ VERIFIED — fully closed this pass | ARCH-03 classification, evidence-base figures (12/114), and §7 Sources (ADR-023) all correct. |
| `docs/handoff/checkpoint-threat-model.md` | Accurate about the current threat surface post-ADR-022 | ✓ VERIFIED | T2/T3 no longer cite the removed ADR-011 gate as a current control. |
| `.github/workflows/quality.yml` | CI infrastructure that actually runs what the docs claim | ✓ VERIFIED | Read in full; matches every document claim checked. |
| `CLAUDE.md` § Current state | ARCH-04 deliverable, true now | ✗ **FAILED** | Self-contradicts on Milestone-1 closure status (line 56 vs. 83). |
| `README.md` § Status | ARCH-04 deliverable, true now | ✗ **FAILED** | Asserts "Milestone 1 is complete" with the outstanding sign-off unmentioned anywhere in the file. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `docs/DECISIONS.md` ADR-023 | `docs/handoff/component-architecture.md` §4 evidence-base table, §7 Sources | Figures and citation should reflect the current state | ✓ WIRED — regression fixed | Confirmed 12/114 and ADR-023 present in Sources. |
| `docs/DECISIONS.md` ADR-022 | `docs/handoff/contracts.md` §2/§3 | Should remove/update claims assuming a current human review gate | ✓ WIRED — regression fixed | Both residual instances confirmed rewritten and consistent with §5. |
| `docs/DECISIONS.md` ADR-022 | `docs/handoff/checkpoint-threat-model.md` T2/T3 | Mitigations should not cite a removed control | ✓ WIRED | Confirmed on direct read. |
| `.github/workflows/quality.yml` | `docs/handoff/contracts.md`, `component-architecture.md` | Document claims about CI should match the workflow | ✓ WIRED | Every gate name, order, and severity level cross-checked against the YAML. |
| `01-HUMAN-UAT.md` (sign-off pending) | `CLAUDE.md` § Current state, `README.md` § Status | Entry documents should not assert the sign-off has happened or omit that it is pending | ✗ **NOT WIRED** | CLAUDE.md contradicts itself; README.md omits the fact entirely. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest -q` | `160 passed, 8 skipped` in ~44s | ✓ PASS |
| Contract test suite passes | `uv run pytest tests/contract -q` | `114 passed` | ✓ PASS |
| Build-state guard passes | `uv run pytest tests/architecture -q` | `16 passed` | ✓ PASS |
| Spikes (bake-off) pass, unaffected by CI addition | `uv run pytest spikes -q` | `30 passed` | ✓ PASS — no regression |
| Schema currency gate | `uv run python scripts/generate_schemas.py --check` | exit 0: `schemas/ is current (12 contracts)` | ✓ PASS |
| Lint (as CI runs it) | `uv run ruff check packages tests scripts spikes` | `All checks passed!` | ✓ PASS |
| Lint (as contracts.md's gate table scopes it) | `uv run ruff check packages tests scripts` | `All checks passed!` | ✓ PASS |
| Format (as CI runs it) | `uv run ruff format --check packages tests scripts spikes` | `56 files already formatted` | ✓ PASS |
| Format (as contracts.md's gate table scopes it) | `uv run ruff format --check packages tests scripts` | `22 files already formatted` | ✓ PASS — matches contracts.md's stated figure exactly |
| Types | `uv run mypy --strict packages tests scripts` | `Success: no issues found in 22 source files` | ✓ PASS — matches contracts.md's stated figure exactly |
| Security scan (severity-scoped, as CI runs it) | `uv run bandit -r packages -q --severity-level medium` | exit 0, no output | ✓ PASS |
| Security scan (unscoped, as contracts.md's gate table describes) | `uv run bandit -r packages -q` | `0 High, 0 Medium, 3 Low` (documented `B105` false positives on `ClearanceRequirement` enum members) | ✓ PASS — matches contracts.md exactly |
| Root contract count | `ireports_domain.ROOT_CONTRACTS` / `ls schemas/*.schema.json` | 12 and 12 | ✓ Matches `contracts.md`, `CLAUDE.md`, `README.md`, `component-architecture.md` (all now say 12/twelve) |
| No uncommitted changes ahead of this pass | `git status --short` | (empty) | ✓ Confirmed working tree matches the commits reviewed |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ARCH-01 | 01-02-PLAN.md | Component-architecture write-up, boundaries + build-state markers, program-leadership-signable | ✓ **SATISFIED** (document); ? sign-off itself is human-only | `component-architecture.md` fully accurate — all four previously-open figure/citation defects confirmed closed. The document is ready to be signed; the signature has not happened (truth 1b). |
| ARCH-04 | 01-03-PLAN.md | Entry documents describe actual current state | ✗ **FAILED** (new finding) | Contract/test/tooling figures all correct in both files, but both files over-claim Milestone-1 completion relative to the outstanding sign-off — CLAUDE.md self-contradicts within its own section; README.md never mentions the pending item at all. |
| CONT-01 | 01-01-PLAN.md | `SpecialistResult` contract published, documented, immutable, no aggregate score | ✓ **SATISFIED** | Schema-currency gate clean; contract structure/immutability hold; `contracts.md` fully accurate, no residual self-contradiction found on this pass. |

No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `CLAUDE.md` | 56 vs 83 | "Milestone 1 is closed" contradicts "Outstanding before M1 sign-off" three sentences later | 🛑 Blocker | ARCH-04's own deliverable asserting an unearned completion state — the exact defect class this phase exists to eliminate. |
| `README.md` | 27 | "Milestone 1 is complete." — unqualified anywhere in the file | 🛑 Blocker | The first document most readers open states the milestone is done with zero acknowledgment that program-leadership sign-off, the milestone's own exit criterion, is still pending. |
| `docs/handoff/orchestration-scorecard.md` / `.json` | 33, 80, 167 | "Cold start under SAM local — not run" / "have NOT been measured for any candidate" — stale since ADR-023 (2026-08-11 21:00) measured and closed it; this file was last touched at 06:41 the same day | ℹ️ Info (deferred, out of this phase's requirement scope) | Same defect category as the two gaps this phase closed, in a document ARCH-01/ARCH-04/CONT-01 do not name. Flagged for whoever next touches ADR-023-adjacent documents. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any file checked this pass
(`CLAUDE.md`, `README.md`, `docs/handoff/component-architecture.md`, `docs/handoff/contracts.md`,
`docs/handoff/checkpoint-threat-model.md`, `.github/workflows/quality.yml`, `docs/DECISIONS.md`).

### Status of every item this pass was asked to check

| # | Item | Status now |
|---|------|-------------|
| 1 | `contracts.md` self-contradiction (`reviewer_summary`, review-gate tense) | ✓ Fully closed, independently confirmed |
| 2 | `component-architecture.md` stale figures (14/91) and missing ADR-023 citation | ✓ Fully closed, independently confirmed |
| 3 | `checkpoint-threat-model.md` T2/T3 citing a removed control | ✓ Fully closed, independently confirmed |
| 4 | CI exists and runs what the updated documents claim | ✓ Confirmed accurate, read line-by-line against `.github/workflows/quality.yml` |
| 5 | Every hand-recorded figure in the four named documents | ✓ All re-derived and matched, **except** the Milestone-1-status claims below, which are not numeric figures and were not previously checked for internal consistency |
| 6 | Full regression (suite, schema check, mypy, ruff, architecture guard) | ✓ No regressions: 160/8skip, 12 contracts current, mypy clean, ruff clean, 16/16 architecture, 30/30 spikes |
| — | New finding, not asked for by name but within "verify numbers, not prose" and the adversarial mandate | ✗ CLAUDE.md and README.md both over-claim Milestone-1 completion relative to the still-pending sign-off — see gaps above |

### Human Verification Required

### 1. Program-leadership sign-off on component boundaries

**Test:** Program leadership reads `docs/handoff/component-architecture.md` §1-§3 (both Mermaid
diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS
ingestion, ASAP, and the human reviewer begin.
**Expected:** Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause).
**Why human:** Leadership decision, not a code fact. `component-architecture.md` itself is now
fully accurate (every previously-flagged figure and citation defect confirmed closed this pass) —
the document is ready to be signed. `01-HUMAN-UAT.md` records the sign-off as pending, 0 of 1
tests passed. This has been true since the first verification report on this phase and remains the
last mechanically-unresolvable item — but CLAUDE.md and README.md currently misstate whether it
has happened, which is a separate, code-level defect scored as a gap above.

### Gaps Summary

Three of the four items this pass was specifically asked to re-check are fully closed, independent
of the fix commits' own messages:

1. **`contracts.md`'s two self-contradictions are gone.** `reviewer_summary` is now correctly
   described as historical (removed by ADR-022), and the language-guard note now correctly states
   the human review gate "is gone" — consistent with the rest of the same document.
2. **`component-architecture.md`'s stale figures and missing citation are gone.** Twelve contracts,
   114 tests, and ADR-023 now appears in §7 Sources.
3. **`checkpoint-threat-model.md`'s T2 and T3 no longer cite a removed control** as though it still
   existed.
4. **CI genuinely exists and runs what the documents now say it runs** — `.github/workflows/quality.yml`
   was read start to finish and matches `contracts.md` and `component-architecture.md`'s
   descriptions gate for gate, including the severity-scoped bandit step and the postgres-backed
   bake-off with its skip-guard.

One new defect was found, in the same two files ARCH-04 names, that none of the four prior
verification passes on this phase caught: **CLAUDE.md and README.md both currently over-claim that
Milestone 1 is finished.** CLAUDE.md's "Current state" section asserts "Milestone 1 is closed" in
one sentence and "program-leadership sign-off... [is] outstanding" three sentences later — a direct
self-contradiction within the same paragraph block. README.md's "Status" section states "Milestone
1 is complete." as its entire lede and never once mentions, anywhere in the file, that the
milestone's own exit criterion (sign-off) has not happened. This defect was introduced on
2026-08-11 at 17:11:43 (commit `b7af8a8`, the original ARCH-04 plan execution) and has survived
every subsequent commit and every prior verification pass on this phase, including the one
immediately before this one.

This is the same defect category — an entry document asserting something that is not (yet) true —
that the prior five incidents in this phase were about, just not one of the specific instances any
prior pass had already flagged. Given ARCH-04 explicitly names `CLAUDE.md` § Current state and
`README.md` § Status as its deliverables, and the phase's own goal text is "the repository's entry
documents stop asserting things that are no longer true," this is scored as a gap blocking the
phase rather than deferred.

Separately, and out of this phase's requirement scope, `docs/handoff/orchestration-scorecard.md`
and `.json` still say cold start "has not been measured for any candidate" — stale since ADR-023.
This is not named by ARCH-01, ARCH-04, or CONT-01, so it is recorded as a deferred observation, not
a phase gap.

Per the decision tree (gaps found takes priority over human-needed), **status is `gaps_found`**.

---

_Verified: 2026-08-12T03:15:00Z_
_Verifier: Claude (gsd-verifier)_
_Final confirmation pass, independent of commit messages, on commits e173ee6, 9dbb08e, and
f241b0d following the 02:00:44Z report. All four specifically-requested re-checks (contracts.md,
component-architecture.md, checkpoint-threat-model.md, CI) confirmed fully closed. One new,
previously undetected defect found in CLAUDE.md and README.md during the required adversarial
sweep of every hand-recorded claim in those files, not just their numeric figures._
