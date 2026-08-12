---
phase: 01-close-the-architecture-package
verified: 2026-08-12T01:47:35Z
status: gaps_found
score: 2/6 must-haves cleanly verified; 4 failed; re-verification against a materially changed codebase
overrides_applied: 0
supersedes:
  report: ea9cd08 (2026-08-11T22:16:31Z, status human_needed)
  reason: >
    Twelve commits landed after that report: ADR-022 (supersedes ADR-011, removes
    HumanDisposition/ReviewSummary and the in-run review gate, contract set 1.0.0 -> 2.0.0,
    14 contracts -> 12) and ADR-023 (closes ARCH-03 with a measured cold-start figure under SAM
    local, adds LAMB-01 to Phase 2). Both changed exactly what the prior report verified as
    VERIFIED or deferred to human sign-off. This report re-derives every truth from the current
    codebase rather than trusting the prior report's findings to still hold.
re_verification:
  previous_status: human_needed
  previous_score: "4/5 must-haves verified (1 human-only)"
  gaps_closed:
    - "CR-01/CR-02 (D-11 build-state guard completeness, noted-not-litigated in the prior report) are now fully closed: test_the_document_has_no_build_state_problems asserts the whole problem list, test_designed_not_built_is_never_quietly_dropped replaces the unsatisfiable set-equality assertion, and test_every_problem_code_has_a_failing_example proves every one of the nine problem categories can fire."
    - "WR-11 through WR-16 from 01-REVIEW.md (diagram/prose defects in component-architecture.md as it stood 2026-08-11) are all independently confirmed fixed in the current document: the fan-out and loop-back edges are drawn (WR-16), the budget-stop path routes through the checkpoint step before returning (WR-13), the CI claim is corrected to state no CI pipeline exists (WR-14), the AWS-query sentence uses future/PLANNED tense (WR-15), and the gateway edge is qualified per ADR-017 with both adapter paths drawn (WR-12). WR-11's reviewer-bypass edge is moot: ADR-022 removed the reviewer from the diagram entirely, which resolves the underlying concern by removing the workflow it modelled."
  gaps_remaining: []
  regressions:
    - "docs/handoff/contracts.md was not touched by the ADR-022 commit (74d9a3e) or by either ADR-023 commit. It now describes a superseded 14-contract, version-1.0.0 set that includes two contracts (HumanDisposition, ReviewSummary) that no longer exist in packages/domain/, and documents enforcement mechanisms (human_review_recorded, _delivery_requires_review, test_no_path_reaches_delivery_without_human_review, the AWAITING_HUMAN_REVIEW pause) that were deleted by ADR-022. CONT-01's own acceptance text in REQUIREMENTS.md requires 'docs/handoff/contracts.md updated' -- it is not."
    - "schemas/ is currently out of date with the Pydantic models (uv run python scripts/generate_schemas.py --check fails: finding.schema.json, specialist-result.schema.json). Commit 89f1f5f (ADR-023) edited ProposedFinding's docstring without regenerating schemas/. This is a live, reproducible failure of the exact gate both contracts.md and component-architecture.md assert is green."
    - "docs/handoff/component-architecture.md -- last touched by the ADR-022 commit (74d9a3e), before ADR-023 landed -- now misstates ARCH-03's status in two places (S4 row, S5 narrative): it claims cold start under SAM local is unmeasured and has no scheduled phase and names it as the one number most likely to reopen ADR-012. ADR-023 measured it in spikes/lambda_fit/ and closed ARCH-03; ADR-012 was confirmed not to reopen. The document's own S7 Sources list does not cite ADR-023. It also carries two pre-existing stale figures (fourteen Pydantic v2 models, 91 tests as of CONT-01; actual: twelve, 114) and a now-false claim that contracts.md is 'Updated for CONT-01'."
    - "README.md S Status still reads 'Fourteen data contracts... the fourteenth is SpecialistResult' and 'uv run pytest -q # 126 passed, 8 skipped' -- both wrong against the current code (12 contracts; 160 passed, 8 skipped). README.md was not touched by either ADR-022 or ADR-023 commit."
    - "CLAUDE.md S Current state still reads 'Outstanding before M1 sign-off: cold start and packaging under SAM local, which is unmeasured, has no scheduled phase because ARCH-03 was cut by ADR-020' -- the same false ARCH-03 claim as component-architecture.md, and for the same reason: CLAUDE.md's last edit (a55d4d2) predates the ADR-023 commit (89f1f5f). Test count is also stale by one (159 vs 160)."
gaps:
  - truth: "SpecialistResult is published to schemas/ with contract tests, carrying no aggregate score field (ROADMAP Phase 1 SC4), and CONT-01's acceptance that docs/handoff/contracts.md is updated."
    status: failed
    reason: >
      Two independent mechanical failures. (1) generate_schemas.py --check currently fails --
      schemas/ is out of date for finding.schema.json and specialist-result.schema.json, both of
      which embed ProposedFinding's docstring, edited in commit 89f1f5f without a schema
      regeneration. (2) docs/handoff/contracts.md, CONT-01's own explicitly-required deliverable
      ("Acceptance: ... docs/handoff/contracts.md updated"), still describes the pre-ADR-022
      contract set: 14 contracts including two (HumanDisposition, ReviewSummary) that no longer
      exist, contract version 1.0.0 (actual 2.0.0), and mechanisms/tests that were deleted
      (human_review_recorded, _delivery_requires_review, test_no_path_reaches_delivery_without_
      human_review, the AWAITING_HUMAN_REVIEW state). Every numeric gate figure in its S6 table
      (107 contract tests, 142 total, 14 contracts) is also stale (actual: 114, 160, 12).
    artifacts:
      - path: "schemas/finding.schema.json"
        issue: "Stale: does not match ProposedFinding's current docstring. generate_schemas.py --check fails."
      - path: "schemas/specialist-result.schema.json"
        issue: "Stale for the same reason (embeds ProposedFinding as a nested $def)."
      - path: "docs/handoff/contracts.md"
        issue: "Describes a superseded 14-contract, v1.0.0 set; documents removed contracts and removed mechanisms; every S6 gate figure is stale."
    missing:
      - "Run `uv run python scripts/generate_schemas.py` and commit the regenerated schemas/."
      - "Rewrite docs/handoff/contracts.md S1/S2/S3/S4/S5/S6 against the current 12-contract, 2.0.0 set: remove HumanDisposition/ReviewSummary rows, remove the ADR-011 human-review rule/mechanism/test rows (or replace with the ADR-022 boundary mechanisms), and refresh every gate figure (contract test count, whole-suite count, contract count)."
  - truth: "The write-up marks every component BUILT, PLANNED (naming the phase), NOT OURS, or DESIGNED-NOT-BUILT correctly (ROADMAP Phase 1 SC2), and a reader can sign off on it (SC1)."
    status: failed
    reason: >
      docs/handoff/component-architecture.md's S4/S5 misclassify ARCH-03. The S4 evidence-base
      table (line 356/358) carries stale figures ("fourteen Pydantic v2 models", "91 tests as of
      CONT-01"; actual 12 and 114), and falsely marks docs/handoff/contracts.md "Updated for
      CONT-01" (line 414), which the contracts.md gap above shows is not true. Separately, S5's
      DESIGNED-NOT-BUILT table (line 465) and S6 narrative (lines 487-490) state cold start under
      SAM local is "unmeasured" with "no scheduled phase" and call it "the one number most likely
      to reopen ADR-012." ADR-023 (commit 89f1f5f, after this document's last edit) measured it in
      spikes/lambda_fit/ and formally closed ARCH-03 with ADR-012 confirmed not to reopen; this is
      independently corroborated by REQUIREMENTS.md ("CLOSED 2026-08-11 by ADR-023"). The
      document's own S7 Sources list does not cite ADR-023 at all. This is the flagship document
      program leadership is asked to sign off on, and it currently misrepresents the status of the
      single risk the project itself calls "the one number most likely to reopen ADR-012."
    artifacts:
      - path: "docs/handoff/component-architecture.md"
        issue: "S4 line 356/358 stale contract/test counts; line 414 falsely claims contracts.md is updated; S5 line 465 and S6 lines 487-490 wrongly present ARCH-03 as open and unscheduled; S7 Sources omits ADR-023."
    missing:
      - "Move the ARCH-03 row from S5 DESIGNED-NOT-BUILT to a closed/resolved note (or S4), citing ADR-023 and spikes/lambda_fit/, and update the S6 narrative to state ADR-012 does not reopen."
      - "Refresh the contract count (12) and contract-test count (114, or the current whole-suite figure) in S4."
      - "Cite ADR-023 in S7 Sources."
      - "Do not mark docs/handoff/contracts.md BUILT/'Updated for CONT-01' until the contracts.md gap above is closed."
  - truth: "CLAUDE.md S Current state and README.md S Status no longer assert that application code does not exist or that the orchestration framework is undecided, and both reflect ADR-020's scope (ROADMAP Phase 1 SC5)."
    status: failed
    reason: >
      Both files were correctly refreshed for ADR-022's contract-set change but not for ADR-023,
      which landed after each file's last edit. CLAUDE.md line 83-86 still reads "Outstanding
      before M1 sign-off: cold start and packaging under SAM local, which is unmeasured, has no
      scheduled phase because ARCH-03 was cut by ADR-020" -- false for the same reason as the
      component-architecture.md gap above. CLAUDE.md's test count (159) is also stale by one
      (actual 160). README.md line 29-30 still reads "Fourteen data contracts as Pydantic v2
      models... the fourteenth is SpecialistResult" -- directly contradicted by the current code
      (12 root contracts in ireports_domain.ROOT_CONTRACTS, 12 files in schemas/). README.md's
      quickstart block (line 53) still reads "uv run pytest -q # 126 passed, 8 skipped" against an
      actual 160 passed, 8 skipped. README.md was not touched by the ADR-022 or ADR-023 commits at
      all.
    artifacts:
      - path: "CLAUDE.md"
        issue: "Lines 83-86 falsely claim ARCH-03/cold start is unmeasured and unscheduled; line 68 test count stale by one (159 vs 160)."
      - path: "README.md"
        issue: "Lines 29-30 claim fourteen contracts (actual 12); line 53 claims 126 passed, 8 skipped (actual 160 passed, 8 skipped); no mention of ADR-023/ARCH-03's closure at all."
    missing:
      - "Update CLAUDE.md's Outstanding-before-M1-sign-off note to state ARCH-03 was closed by ADR-023 (spikes/lambda_fit/), and refresh the test count to 160."
      - "Update README.md S Status to state twelve contracts (matching CLAUDE.md's already-correct figure), refresh the pytest quickstart count to the current total, and add a line for ADR-023/ARCH-03's closure alongside the existing 1a/1b/1c bullets."
deferred: []
human_verification:
  - test: "Program leadership reads docs/handoff/component-architecture.md S1-S3 (both Mermaid diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS ingestion, ASAP, and the human reviewer begin, then formally signs off on the boundaries as drawn."
    expected: "Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause)."
    why_human: "This is a leadership decision, not a code fact. No sign-off artifact exists anywhere in the repo. Note for the reviewer: fix the gaps above first -- S2/S3 (the boundary diagrams themselves) are accurate, but S4/S5 of the same document currently misstate ARCH-03's status, which undermines the document's reliability as a sign-off artifact even though the boundary content proper is sound."
---

# Phase 1: Close the architecture package — Re-Verification Report

**Phase Goal:** Program leadership can sign off on Milestone 1a's component boundaries, the build
has the contract it needs, and the repository's entry documents stop asserting things that are no
longer true.
**Verified:** 2026-08-12T01:47:35Z
**Status:** gaps_found
**Re-verification:** Yes — supersedes the `ea9cd08` report (2026-08-11T22:16:31Z, `human_needed`)

## Why this report supersedes `ea9cd08`

The prior report attests to a codebase 12 commits old. Since then:

- **ADR-022** (commit `74d9a3e`) supersedes ADR-011: removed `HumanDisposition`, `ReviewSummary`,
  `AWAITING_HUMAN_REVIEW`, `REVIEW_RECORDED`, and four `ASAPEnvelope`/`DeliveredFinding` fields.
  Contract set bumped 1.0.0 → 2.0.0, 14 contracts → 12.
- **ADR-023** (commits `89f1f5f`, `0e45876`) closes ARCH-03 with a measured cold-start figure
  under SAM local (`spikes/lambda_fit/`) and adds LAMB-01 to Phase 2.

Both changes directly touch what the prior report verified. `packages/domain/`,
`docs/handoff/component-architecture.md`, `CLAUDE.md`, and `docs/DECISIONS.md` all changed. This
report re-derives every truth from the current codebase — nothing is carried forward from the
prior report's findings without independent re-verification.

**Headline finding:** the prior report's one open item was a human sign-off with no mechanical
gap remaining. That is no longer the state of the repository. Independent re-verification finds
**four mechanically-demonstrable failures**, three of them regressions introduced by work that
landed *after* this phase's artifacts were last edited (ADR-023 in particular), not by anything
wrong with the original Phase 1 work itself. The original Phase 1 work — the `SpecialistResult`
contract's structure and immutability, the build-state guard's completeness (CR-01/CR-02), and
the six diagram/prose defects from `01-REVIEW.md` (WR-11 through WR-16) — all independently
re-verified as still fixed. What broke is document currency against two ADRs that landed after
Phase 1 closed.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A reader can point to where our system ends and AWS ingestion, ASAP, and the human reviewer begin (SC1, mechanical half) | ✓ VERIFIED | §2/§3 diagrams and boundary prose read cleanly, independently re-checked against ADR-022 and ADR-023: no reviewer edge exists anywhere in the diagram (ADR-022), the `bedrock`/`litellm` split is correctly drawn (ADR-017), the fan-out and loop-back edges are present (WR-16 fixed), the budget-stop path routes through the checkpoint before returning (WR-13 fixed). |
| 1b | Program leadership signs off on those boundaries (SC1, human half) | ? HUMAN NEEDED | No sign-off artifact exists anywhere in the repo. Unaffected by any commit since the prior report. See caveat below: the document to be signed contains accuracy defects elsewhere (S4/S5), noted so the reviewer fixes those first. |
| 2 | Every component marked `BUILT`/`PLANNED`/`NOT OURS`, and every ADR-020/021 cut marked `DESIGNED-NOT-BUILT` individually, correctly (SC2) | ✗ FAILED | The classification *mechanism* (four-marker vocabulary, one row per component) is sound and test-enforced. But the **content** of one row is wrong: ARCH-03 is still listed `DESIGNED-NOT-BUILT` with "no scheduled phase" (component-architecture.md:465,487-490) when ADR-023 closed it with a measurement (`spikes/lambda_fit/`), independently confirmed CLOSED in `.planning/REQUIREMENTS.md:222`. Stale figures (14 contracts, 91 tests) and a false "contracts.md updated" claim (line 414) compound this. |
| 3 | A test fails if a `BUILT` row does not resolve, or a `PLANNED` row already exists; the test proves on in-memory input that it can fail (SC3) | ✓ VERIFIED — **CR-01/CR-02 now fully closed** | `tests/architecture -q` → 16 passed. `test_the_document_has_no_build_state_problems` asserts the whole `check_rows` output (closes CR-01's five-orphaned-category gap). `test_designed_not_built_is_never_quietly_dropped` replaces the unsatisfiable set-equality assertion with a subset check (closes CR-02's equality trap). `test_every_problem_code_has_a_failing_example` parametrizes over all nine problem codes and proves each can fire on a crafted bad document. `test_planned_rows_name_distinct_paths` confirms file-granularity `PLANNED` rows (closes CR-02's directory-collision defect). |
| 4 | `SpecialistResult` published to `schemas/` with contract tests, no aggregate score field (SC4), and CONT-01's documented-contracts.md-updated acceptance | ✗ FAILED | Contract structure, immutability, and the no-aggregate-score guard all independently re-verified passing (see below). But `generate_schemas.py --check` **currently fails** (`schemas/ is out of date... finding.schema.json, specialist-result.schema.json`) — a live, reproducible failure, not a claim taken on trust. `docs/handoff/contracts.md`, CONT-01's own explicitly required deliverable, was not touched since before ADR-022 and describes a superseded contract set. |
| 5 | `CLAUDE.md` § Current state and `README.md` § Status no longer assert application code does not exist or the framework is undecided, and reflect ADR-020's scope (SC5) | ✗ FAILED | Both correctly reflect ADR-020's three-phase scope and ADR-022's contract-set change (CLAUDE.md line 64 is accurate: 12 contracts, v2.0.0). Both are false on ADR-023: CLAUDE.md still calls cold start "unmeasured... no scheduled phase" (lines 83-86); README.md still says "Fourteen data contracts" (lines 29-30, contradicts the code) and quotes a stale test count (line 53: 126 vs actual 160). |
| 6 | `SpecialistResult`'s immutability claim holds (D-06, carried forward from the prior report's closed gap) | ✓ VERIFIED — no regression | `findings: tuple[ProposedFinding, ...]` unchanged in `packages/domain/src/ireports_domain/specialist.py:71`. `test_no_contract_field_is_a_mutable_container`, `test_the_mutability_guard_actually_catches_something`, and `test_a_validated_result_cannot_be_given_another_cases_finding` all pass in the current `tests/contract/test_decision_support_boundary.py` run (70 passed). |

**Score:** 2/6 cleanly verified (truths 1, 3, 6); 4 failed (truths 1b-adjacent document quality,
2, 4, 5); 1 of those 4 also carries the unresolved human sign-off clause.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/domain/src/ireports_domain/specialist.py` | `SpecialistResult`/`SpecialistCriterion`, immutable, no aggregate score | ✓ VERIFIED | `findings: tuple[ProposedFinding, ...]`. Docstring accurately describes D-01/D-02/D-04/D-05. |
| `packages/domain/src/ireports_domain/__init__.py` | `ROOT_CONTRACTS` reflects ADR-022 (12 entries) | ✓ VERIFIED | Confirmed 12 keys by direct read; `HumanDisposition`/`ReviewSummary` absent from `__all__` and from `ROOT_CONTRACTS`. |
| `packages/domain/src/ireports_domain/run.py` | `RunStatus` has no `AWAITING_HUMAN_REVIEW`/`REVIEW_RECORDED` | ✓ VERIFIED | `grep` confirms both removed; the file's own comment documents the removal in place. |
| `packages/domain/src/ireports_domain/asap.py` | `ASAPEnvelope` carries no `human_reviewed`/`human_disposition`/`reviewer_modified`/`reviewer_summary` | ✓ VERIFIED | `grep` finds only docstring references *describing* the removal, no live fields. |
| `schemas/*.schema.json` (12 files) | Generated, current with the models | ✗ **FAILED — live drift** | `uv run python scripts/generate_schemas.py --check` exits 1: `finding.schema.json, specialist-result.schema.json` are stale (`ProposedFinding`'s docstring changed in commit `89f1f5f` without a regeneration). Reproduced: regenerating the two files changes only the `description` field to match the current docstring; `git diff --stat` shows exactly 2 files, 2 lines. Reverted after confirming (`git checkout -- schemas/`). |
| `tests/contract/test_decision_support_boundary.py` | ADR-014/ADR-022 boundary guards, CONT-01 immutability guard | ✓ VERIFIED | 70 tests, all passing. Covers `test_no_contract_models_a_human_decision`, `test_no_run_state_waits_for_a_person`, `test_every_state_can_reach_a_terminal_state_unattended`, `test_the_envelope_never_claims_to_have_been_reviewed`, plus the three mutability-guard tests. |
| `tests/architecture/test_build_state_table.py` | D-11 guard, complete (CR-01/CR-02 closed) | ✓ VERIFIED | 16 tests, all passing. See truth 3 above for the specific tests that close CR-01/CR-02. |
| `docs/handoff/component-architecture.md` | ARCH-01 deliverable, accurate against current code | ✗ **FAILED — regression** | Boundary diagrams/prose (§2/§3) accurate. §4/§5/§7 stale: ARCH-03 misrepresented as open (line 465, 487-490), contract/test counts stale (356, 358), false claim that `contracts.md` is updated (414), ADR-023 not cited in Sources (§7). |
| `docs/handoff/contracts.md` | CONT-01 deliverable, updated | ✗ **FAILED — regression, never updated for ADR-022** | Last touched by `dd9f349`, before `74d9a3e` (ADR-022). Describes 14 contracts including two removed ones, version 1.0.0, and removed mechanisms. Every §6 gate figure stale. |
| `CLAUDE.md` § Current state | ARCH-04 deliverable, true now | ✗ **FAILED — regression** | Correct on ADR-022 (12 contracts, v2.0.0). False on ADR-023 (lines 83-86 claim ARCH-03 unmeasured/unscheduled). Test count stale by 1. |
| `README.md` § Status | ARCH-04 deliverable, true now | ✗ **FAILED — never updated for ADR-022 or ADR-023** | "Fourteen data contracts" (line 29-30) directly contradicts the code. Test count stale (line 53: 126 vs 160). No mention of ADR-023/ARCH-03's closure. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `docs/DECISIONS.md` ADR-022/ADR-023 | `packages/domain/` | Contract removal / no contract change respectively | ✓ WIRED | Domain code correctly implements both ADRs' contract-level consequences. |
| `docs/DECISIONS.md` ADR-023 | `docs/handoff/component-architecture.md` §5 ARCH-03 row | Should update the row to closed | ✗ **NOT WIRED** | The row still reads `DESIGNED-NOT-BUILT`/"no scheduled phase"; ADR-023 landed after this document's last edit and was never propagated into it. |
| `docs/DECISIONS.md` ADR-022 | `docs/handoff/contracts.md` | Should update contract set, version, rule table | ✗ **NOT WIRED** | Never touched by the ADR-022 commit or any commit since. |
| `packages/domain/src/ireports_domain/finding.py` docstring edit (commit `89f1f5f`) | `schemas/finding.schema.json` / `schemas/specialist-result.schema.json` | `scripts/generate_schemas.py` regeneration | ✗ **NOT WIRED** | Commit changed the docstring, did not regenerate. `--check` fails today, reproducibly. |
| `SpecialistResult.findings` | Pydantic frozen-instance enforcement | `tuple[ProposedFinding, ...]` + `ContractModel(frozen=True)` | ✓ WIRED — no regression | Same as prior report; field type and guard tests unchanged and passing. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite passes | `uv run pytest -q` | `160 passed, 8 skipped` in 44-46s | ✓ PASS |
| Contract test suite passes | `uv run pytest tests/contract -q` | `114 passed` | ✓ PASS |
| Build-state guard passes | `uv run pytest tests/architecture -q` | `16 passed` | ✓ PASS |
| Spikes still run | `uv run pytest spikes -q` | `30 passed` | ✓ PASS |
| Schema currency gate | `uv run python scripts/generate_schemas.py --check` | exit 1: `schemas/ is out of date... finding.schema.json, specialist-result.schema.json` | ✗ **FAIL — live, reproduced** |
| Lint | `uv run ruff check` | `All checks passed!` | ✓ PASS |
| Format | `uv run ruff format --check packages tests scripts` | `22 files already formatted` | ✓ PASS |
| Types | `uv run mypy --strict packages tests scripts` | `Success: no issues found in 22 source files` | ✓ PASS |
| Security scan | `uv run bandit -r packages` | `0 High, 0 Medium, 3 Low` (known `B105` false positives on `ClearanceRequirement`) | ✓ PASS |
| Root contract count | direct read of `ireports_domain.__init__.ROOT_CONTRACTS` and `ls schemas/*.schema.json` | 12 and 12 | ✓ Matches code, contradicts `contracts.md` and `README.md` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| ARCH-01 | 01-02-PLAN.md | Component-architecture write-up, boundaries + build-state markers, program-leadership-signable | ✗ **FAILED** | Boundary diagrams/prose sound; §4/§5 content (ARCH-03 status, stale figures, false contracts.md claim) is currently wrong. Not signable as-is without misleading the signer about the project's own stated highest-risk open question. |
| ARCH-04 | 01-03-PLAN.md | Entry documents describe actual current state | ✗ **FAILED** | Both `CLAUDE.md` and `README.md` contain claims directly falsified by the current codebase or by `docs/DECISIONS.md`/`.planning/REQUIREMENTS.md` itself. |
| CONT-01 | 01-01-PLAN.md | `SpecialistResult` contract published, documented, immutable, no aggregate score | ✗ **FAILED** | Contract structure and immutability hold (no regression). But the schema-currency gate fails live, and `docs/handoff/contracts.md` — CONT-01's own required deliverable — was never updated for ADR-022 and now describes a contract set that does not exist. |

No orphaned requirements. Same three requirements map to Phase 1 in `.planning/REQUIREMENTS.md`
(lines 297-299, all marked "Complete" there — that status itself needs revisiting given the
findings above, since it predates none of the regressions but records completion against a moving
target).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `docs/handoff/contracts.md` | 3, 7, 18, 24, 39, 40, 42-46, 60-71, 80-82, 128-131, 140-155, 181, 191-208 | Describes a superseded 14-contract, v1.0.0 set, removed contracts, removed mechanisms, stale gate figures throughout | 🛑 Blocker | CONT-01's explicit acceptance ("docs/handoff/contracts.md updated") is unmet; a reader would learn a materially wrong picture of the contract set. |
| `docs/handoff/component-architecture.md` | 356, 358, 414, 465, 487-490, §7 | Stale contract/test counts, false "contracts.md updated" claim, ARCH-03 misrepresented as open, ADR-023 not cited | 🛑 Blocker | This is the ARCH-01 sign-off artifact; it misrepresents the status of the project's own named highest-risk open question. |
| `CLAUDE.md` | 68, 83-86 | Test count stale by 1; ARCH-03 falsely described as unmeasured/unscheduled | 🛑 Blocker | Same false claim as above, in the file `CLAUDE.md`-reading sessions treat as ground truth for "what exists now." |
| `README.md` | 29-30, 53 | "Fourteen data contracts" contradicts the code (12); stale test count (126 vs 160) | 🛑 Blocker | README.md is the first document an external reader opens; the contract count is wrong in the most basic, checkable way. |
| `docs/handoff/orchestration-scorecard.md` | 33, 80 | "Cold start under SAM local: not run" — also stale against ADR-023 | ℹ️ Info | Not a Phase 1 deliverable (predates this phase, from the 1c bake-off). Noted for completeness; not scored against Phase 1's requirements. |

No `TBD`/`FIXME`/`XXX` markers found in any of the flagged files (`grep -n "TBD\|FIXME\|XXX"` returns
nothing in `contracts.md`, `component-architecture.md`, `CLAUDE.md`, `README.md`).

### Status of prior review findings (`01-REVIEW.md`)

Independently re-checked, not taken on trust:

| Finding | Status now | Evidence |
|---|---|---|
| CR-01 (5 of 9 build-state problem categories orphaned) | ✓ Closed | `test_the_document_has_no_build_state_problems` asserts the full list; `test_every_problem_code_has_a_failing_example` proves every code fires. |
| CR-02 (directory-granularity + set-equality trap) | ✓ Closed | `PLANNED` rows now file-granular (`test_planned_rows_name_distinct_paths`); equality assertion replaced with subset assertion (`test_designed_not_built_is_never_quietly_dropped`). |
| CR-03 (`SpecialistResult.findings` mutable list) | ✓ Closed, no regression | `tuple[ProposedFinding, ...]`, confirmed live. |
| WR-11 (reviewer-bypass edge) | ✓ Moot | ADR-022 removed the reviewer from the diagram entirely. |
| WR-12 (gateway edge overstates; missing bedrock edge) | ✓ Closed | Edge qualified per ADR-017; both `PROXY` and direct `BEDROCK` edges drawn. |
| WR-13 (budget-stop skips checkpoint) | ✓ Closed | `BUDGETSTOP --> AGG --> STEP5` — routes through the checkpoint before returning. |
| WR-14 (false CI claim) | ✓ Closed | Now states "no CI pipeline exists in this repository." |
| WR-15 (present-tense AWS query claim) | ✓ Closed | Now future tense, `PLANNED`. |
| WR-16 (no fan-out/loop drawn) | ✓ Closed | `STEP2 -- "per criterion" --> SPECIALIST` and `SHELL -- "criteria remain" --> STEP2` both present. |

`01-HUMAN-UAT.md`'s pending test (program-leadership sign-off) remains a valid, unresolved item —
but the document it asks leadership to review has changed since it was written and now carries the
accuracy defects listed above. A reviewer should not sign off on the current document without the
`gaps_found` items being closed first, or the sign-off would be against a document making a false
claim about the project's own named highest risk (ARCH-03/ADR-012 reopening).

### Human Verification Required

### 1. Program-leadership sign-off on component boundaries

**Test:** Program leadership reads `docs/handoff/component-architecture.md` §1-§3 (both Mermaid
diagrams and the boundary prose) and confirms they can point to where iReports ends and AWS
ingestion, ASAP, and the human reviewer begin.
**Expected:** Explicit sign-off recorded (ROADMAP Phase 1 success criterion 1's second clause).
**Why human:** Leadership decision, not a code fact — unchanged from the prior report. No sign-off
artifact exists anywhere in the repo. **Recommendation:** close the four gaps above first. The
boundary content itself (§2/§3) is sound, but §4/§5 of the same document currently make a false
claim about ARCH-03's status, which is exactly the kind of defect that should not be in front of a
signer.

### Gaps Summary

Four gaps, all mechanically reproducible, none requiring human judgment to detect:

1. **`docs/handoff/contracts.md` was never updated for ADR-022.** It documents a 14-contract,
   v1.0.0 set including two contracts that no longer exist and mechanisms that were deleted.
   CONT-01's own acceptance text names this file explicitly.
2. **The schema-currency gate fails right now.** `generate_schemas.py --check` reports drift on
   `finding.schema.json` and `specialist-result.schema.json`, caused by an unregenerated docstring
   edit in the ADR-023 commit. Reproduced and reverted; not a hypothetical.
3. **`docs/handoff/component-architecture.md` (the ARCH-01 sign-off artifact) misrepresents ARCH-03
   as open and unscheduled** when ADR-023 closed it with a measurement. This is independently
   corroborated as false by `docs/DECISIONS.md` and `.planning/REQUIREMENTS.md` themselves. The
   document also carries stale contract/test counts and a false claim that `contracts.md` is
   current.
4. **`CLAUDE.md` and `README.md` (the ARCH-04 deliverables) both make claims contradicted by the
   current codebase** — `CLAUDE.md` repeats the same false ARCH-03 claim as component-architecture.md;
   `README.md` was never updated for ADR-022 at all and still claims fourteen contracts.

None of these are failures of the original Phase 1 work — every defect the prior review report
(`01-REVIEW.md`) raised against that work (CR-01 through CR-03, WR-11 through WR-16) is
independently confirmed fixed. All four gaps here are regressions: two documents (`contracts.md`,
`README.md`) that a subsequent commit should have touched and did not, and two documents
(`component-architecture.md`, `CLAUDE.md`) that were correctly updated for ADR-022 but never
revisited after ADR-023 landed. Given the decision-support boundary re-checked clean (`packages
domain` code and its 70-test guard suite are unaffected by any of this), and given the phase's own
goal text is explicitly present-tense ("stop asserting things that are no longer true"), these are
scored as gaps blocking this phase rather than deferred to Phase 3's handoff-currency criterion —
Phase 1's own deliverables should not sit stale for two more phases before anyone notices.

Per the decision tree (gaps found takes priority over human-needed), **status is `gaps_found`**,
not `human_needed`, even though the human sign-off item from the prior report also remains open.

---

_Verified: 2026-08-12T01:47:35Z_
_Verifier: Claude (gsd-verifier)_
_Supersedes: `ea9cd08` (2026-08-11T22:16:31Z, `human_needed`) — see "Why this report supersedes" above_
