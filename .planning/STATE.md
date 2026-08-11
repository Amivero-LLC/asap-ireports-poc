---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 8
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

Phase: 1 of 8 (Close the architecture package)
Plan: — of — (no plans yet)
Status: Ready to plan
Last activity: 2026-08-11 — `/gsd-new-project` ingested 12 source documents; PROJECT, REQUIREMENTS,
ROADMAP, and STATE created. 0 ingest blockers, 3 warnings resolved by user decision.

Progress: [░░░░░░░░░░] 0%

**Next action:** `/gsd-plan-phase 1`. The single highest-priority item inside it is **ARCH-01, the
component-architecture write-up — the last thing blocking program sign-off on Milestone 1a.**

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
via `IREPORTS_LIVE_SMOKE=1`). `ruff` clean. `mypy --strict` 15 errors — **all pre-existing and all
confined to `tests/contract/`**; none in `packages/`, none in `spikes/`. `pip-audit` clean over the
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
  All evidence to date is commercial-partition only. Blocks Phase 8 HAND-02 and any GovCloud
  deployment work. Externally blocked on account access.
- **Q-02 (GATE, open) — contained, NOT cleared.** Phase 4 proceeds under the working assumption with
  the retrieval mapping module marked PROVISIONAL, on ADR-007's one-file containment. **Do not let
  any later document imply the gate was cleared.**
- **Q-03 (GATE, open) — high blast radius and silent.** Embedding parity between query time and the
  AWS collection is unverified. A mismatch does not error; it retrieves worse. **No
  locally-measured retrieval quality may be presented as predictive of AWS behaviour.**
- **ADR-012 is conditional on an unmeasured number.** Cold start and packaging under SAM local were
  never measured for any candidate. `spikes/test_scorecard.py` fails the moment a figure is recorded.
  Scheduled in Phase 1, deliberately before nodes are written against LangGraph.
- **Model-call idempotency is owed and unbuilt.** A crash mid-fan-out re-runs an in-flight model call
  — LangGraph 11/24, hand-rolled 12/24 over 24 trials. Phase 2, ORCH-02.
- **Checkpoint row integrity is the single largest recorded security gap** (threat-model §6). Phase 3.
- **`CLAUDE.md` § Current state is stale** — it says application code does not exist. The stack table
  was corrected to LangGraph on 2026-08-11; the state narrative was not. Phase 1, ARCH-04.
- **`bedrock` adapter has never been run in any partition.** Verified as correctly constructed and
  nothing more — do not read the green test suite as connectivity. Phase 8, HAND-03.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Milestone | M3 Optimize — candidates recorded unordered, gated on M2 measurements | Placeholder, not decomposed | 2026-08-11 (ingest) |
| Contracts | `EntityCandidate`, `TimelineEvent` | Blocked on Q-02, no M2 consumer | 2026-08-11 |
| Security | Checkpoint encryption at rest / retention & pruning | Blocked on Q-01 / Q-09 | 2026-08-11 |
| Gateway | Retry & fallback policy, streaming run status, `MAX_EXCERPT_CHARS`, prompt caching | v2 (Q-04, Q-13) | 2026-08-11 |

## Session Continuity

Last session: 2026-08-11 — document ingest and roadmapping.
Stopped at: `.planning/` initialized from 12 source documents. No implementation work started under
GSD; the repo's own prior work is inventoried above.
Resume file: None.

**Cold-start reading order:** this file → `.planning/ROADMAP.md` § Gates → `docs/DECISIONS.md` →
`docs/OPEN-QUESTIONS.md`. `blueprint.md` is the project's **input**, lowest precedence; where it
conflicts with `docs/DECISIONS.md`, DECISIONS.md wins.
