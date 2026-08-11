---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
last_updated: "2026-08-11T13:09:42.220Z"
last_activity: 2026-08-11 — `/gsd-new-project` ingested 12 source documents; PROJECT, REQUIREMENTS,
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-08-11)

**Core value:** One command takes a synthetic case to a delivered, **human-approved** iReport, with
every seam exercised once and every handoff claim cited or explicitly marked unverified.
**Current focus:** Phase 1 — Close the architecture package.
**The deliverable is a proven architecture and a handoff package, not a product** (ADR-001).

## Current Position

Phase: 1 of 9 (Close the architecture package)
Plan: — of — (no plans yet)
Status: Ready to plan
Last activity: 2026-08-11 — roadmap restructured to a **port-first dual-adapter bake-off over the
full seam-walk**. 8 phases → 9. Milestone 1c's *partial* spike is reopened at outcome level: analysis
logic is written once behind this project's orchestration port and run by two adapters (LangGraph
and hand-rolled), both landing in Phase 2 and both staying in the conformance suite thereafter.
Phase 8 is new — the verdict. ARCH-03 (cold start) moved Phase 1 → 8; ARCH-02 (dependency inventory)
moved Phase 1 → 9; ARCH-05, ORCH-05, BAKE-01 added.

Progress: [░░░░░░░░░░] 0%

**Next action:** `/gsd-discuss-phase 1` (the earlier run was abandoned mid-discussion when the
roadmap was reshaped; no CONTEXT.md was written), then `/gsd-plan-phase 1`. Phase 1 now carries
ARCH-01, ARCH-04, ARCH-05, CONT-01. The highest-priority item remains **ARCH-01, the
component-architecture write-up — the last thing blocking program sign-off on Milestone 1a** — which
now doubles as the port and boundary design the Phase 2 build consumes.

**Decided during the reshape, feeding Phase 1 discussion:** the write-up's diagrams are Mermaid
fences inside the doc (canonical there, not exported); it describes the target system with every
component marked BUILT / PLANNED-with-phase / NOT OURS; and a test fails if a BUILT row does not
resolve to a real path or a PLANNED row already exists.

## What Already Exists

Read this before assuming anything is unbuilt. `CLAUDE.md` § Current state is **stale** and still
says application code does not exist.

| Area | State | Where |
|---|---|---|
| Data contracts | 13 Pydantic v2 contracts + JSON Schema, 56 contract tests. v1.0.0 | `packages/domain/`, `schemas/`, `docs/handoff/contracts.md` |
| Model gateway | `ModelGateway` port; `litellm` / `bedrock` / `stub` adapters. One live commercial-partition run | `packages/gateway/`, `docs/handoff/model-gateway.md`, `docs/handoff/compatibility-matrix.md` |
| Orchestration bake-off | All three candidates built, all four legs passing, retained | `spikes/{langgraph,strands,handrolled,harness}/`, `spikes/measure.py`, `spikes/bakeoff_scorecard.py` |
| Scorecard | Measured, machine-readable, validated as a `Scorecard` contract | `docs/handoff/orchestration-scorecard.{md,json}` |
| Landscape scan | Framework survey, footprints, repo health | `docs/handoff/orchestration-landscape.md` |
| Checkpoint threat model | T1–T6, controls built and **not** built (§6) | `docs/handoff/checkpoint-threat-model.md` |
| LangSmith egress-deny | Proven fail-closed, with a negative control | `spikes/langgraph/test_langsmith_egress.py` |
| Not built yet | `packages/orchestration/`, `packages/retrieval/`, `packages/policy/`, `packages/delivery/`, `apps/`, `workers/`, `policy-packs/`, `cases/synthetic/`, `evals/` | — |

**Milestones:** 1a partially complete (contracts done; component-architecture write-up
**OUTSTANDING**). 1b complete 2026-08-10. 1c complete 2026-08-11 — **ADR-012 Accepted, the
orchestration framework is LangGraph.** M2 not started. M3 is a placeholder, gated on M2, not
decomposed.

**Repo health (2026-08-11):** 111 tests passing, 8 skipped (the skips are live-model tests, opt-in
via `IREPORTS_LIVE_SMOKE=1`). `ruff` clean. `mypy --strict` **clean across 48 source files** — the 15 pre-existing `tests/contract/` errors were cleared 2026-08-11 (QUAL-01 done). `pip-audit` clean over the
pinned set.

## Performance Metrics

**Velocity:** no plans executed yet under GSD.

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

## Accumulated Context

### Decisions

19 LOCKED ADRs in `docs/DECISIONS.md`, mirrored into `.planning/PROJECT.md` § Key Decisions.
Read `docs/DECISIONS.md` before proposing an architectural change; supersede with a numbered entry
rather than diverging silently. Most load-bearing for current work:

- **ADR-012** — LangGraph, decided on cost not correctness (all three candidates passed all four
  legs). Hand-rolled is the recorded runner-up and the fallback if the dependency surface is refused.
  **Nodes depend on our own port, never `from langgraph import ...`.**

- **ADR-011 / ADR-014** — the human disposition gate and the no-aggregate-score rule. Both enforced
  structurally and both NON-NEGOTIABLE.

- **ADR-015 / ADR-018 / ADR-019** — gateway on the official `anthropic` SDK; a refusal raises rather
  than returning; structured output is one tool call and is verified, not trusted; no tier needs Opus.

- **ADR-007** — iReports consumes an AWS-owned vector collection; local ingest/embedding is
  development only; all field mappings in one module.

### Pending Todos

None captured yet.

### Blockers/Concerns

- **Q-01 (GATE, open, refuses any working assumption)** — Claude availability, model and
  inference-profile ids, cross-region inference, and data-routing rules in GovCloud are unvalidated.
  All evidence to date is commercial-partition only. Blocks Phase 9 HAND-02 and any GovCloud
  deployment work. Externally blocked on account access.

- **Q-02 (GATE, open) — contained, NOT cleared.** Phase 4 proceeds under the working assumption with
  the retrieval mapping module marked PROVISIONAL, on ADR-007's one-file containment. **Do not let
  any later document imply the gate was cleared.**

- **Q-03 (GATE, open) — high blast radius and silent.** Embedding parity between query time and the
  AWS collection is unverified. A mismatch does not error; it retrieves worse. **No
  locally-measured retrieval quality may be presented as predictive of AWS behaviour.**

- **ADR-012 is provisional and is being re-tested at outcome level.** Milestone 1c was a *partial*
  spike — its own scorecard §5 records that it measured no real model behaviour, no retrieval, no
  findings, and no delivery. Phases 2–8 run what it deferred: two adapters behind one port over the
  full seam-walk. **Nothing in 1c is being redone.** Cold start under SAM local remains unmeasured
  and `spikes/test_scorecard.py` still fails the moment a figure is recorded — now scheduled in
  Phase 8, on both adapters carrying real work rather than on a toy spike. The trade this accepts is
  stated in ROADMAP.md § Phase 8.
- **Strands no longer carries mission logic.** Last on every measured axis (373 lines against
  195/266, 42 distributions, +47.3 MB), and its 0/24 duplicate-call result is already footnoted as
  an artifact of synchronous node bodies, not durability. This amends ADR-012's candidate set and
  needs a numbered entry; `spikes/strands/` stays in the repo and in the suite per ADR-001.

- **Model-call idempotency is owed and unbuilt.** A crash mid-fan-out re-runs an in-flight model call
  — LangGraph 11/24, hand-rolled 12/24 over 24 trials. Phase 2, ORCH-02.

- **Checkpoint row integrity is the single largest recorded security gap** (threat-model §6). Phase 3.
- **`CLAUDE.md` § Current state is stale** — it says application code does not exist. The stack table
  was corrected to LangGraph on 2026-08-11; the state narrative was not. Phase 1, ARCH-04.

- **`bedrock` adapter has never been run in any partition.** Verified as correctly constructed and
  nothing more — do not read the green test suite as connectivity. Phase 9, HAND-03.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Milestone | M3 Optimize — candidates recorded unordered, gated on M2 measurements | Placeholder, not decomposed | 2026-08-11 (ingest) |
| Contracts | `EntityCandidate`, `TimelineEvent` | Blocked on Q-02, no M2 consumer | 2026-08-11 |
| Security | Checkpoint encryption at rest / retention & pruning | Blocked on Q-01 / Q-09 | 2026-08-11 |
| Gateway | Retry & fallback policy, streaming run status, `MAX_EXCERPT_CHARS`, prompt caching | v2 (Q-04, Q-13) | 2026-08-11 |

## Session Continuity

Last session: 2026-08-11T13:09:42.209Z
Stopped at: Roadmap restructured: port-first dual-adapter bake-off over the full seam-walk (8 phases -> 9).
`.planning/ROADMAP.md` and `REQUIREMENTS.md` are updated. **Two follow-on writes are owed and not
yet done:** a numbered ADR entry recording the outcome-level re-test and the Strands amendment, and
`docs/ROADMAP.md` (which still describes the old milestone shape). No implementation work has
started under GSD; the repo's own prior work is inventoried above.
Resume file: .planning/ROADMAP.md

**Cold-start reading order:** this file → `.planning/ROADMAP.md` § Gates → `docs/DECISIONS.md` →
`docs/OPEN-QUESTIONS.md`. `blueprint.md` is the project's **input**, lowest precedence; where it
conflicts with `docs/DECISIONS.md`, DECISIONS.md wins.
