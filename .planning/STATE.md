---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-08-11T21:08:16.212Z"
last_activity: 2026-08-11
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 3
  completed_plans: 2
  percent: 0
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-08-11)

**Core value:** One command takes a synthetic case to a **human-approved**, validated typed envelope,
with the orchestrator's hard parts exercised and every handoff claim cited or explicitly marked
unverified.
**Current focus:** Phase 01 — close-the-architecture-package
**The deliverable is a proven architecture and a handoff package, not a product** (ADR-001).
**Scope is the orchestrator spine — 3 phases, not 9 (ADR-020).**

## Current Position

Phase: 01 (close-the-architecture-package) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-08-11
requirements → 15.** Cut: the second orchestration adapter and the outcome-level bake-off
(ORCH-05, BAKE-01, ARCH-03, ARCH-05), checkpoint hardening (CKPT-01..03), retrieval and local ingest
(RETR-01..03, CONT-02), authority routing and policy packs (ROUT-01..02), citation validators
(VAL-01), the outbox and ASAP mock (DEL-01), the dependency inventory and GovCloud gate (ARCH-02,
HAND-02..03). **Nothing deleted** — all 18 moved to `REQUIREMENTS.md` § v2 § Cut by ADR-020 with
acceptance intact, each owed a designed-not-built entry under HAND-01. ADR-011 (disposition gate) and
ADR-014 (no aggregate score) were considered for the cut and **explicitly kept** — already structural
in the shipped contracts, so retaining them costs nothing.

Progress: [███████░░░] 67%

**Next action:** resume `/gsd-discuss-phase 1` against the new, smaller Phase 1 (ARCH-01, ARCH-04,
CONT-01), then `/gsd-plan-phase 1`. The highest-priority item remains **ARCH-01, the
component-architecture write-up — the last thing blocking program sign-off on Milestone 1a.**

**Carried into the Phase 1 discussion:**

- The write-up's diagrams are Mermaid fences inside the doc (canonical there, not exported).
- Every component is marked BUILT / PLANNED-with-phase / NOT OURS, **plus a new DESIGNED-NOT-BUILT
  category** for ADR-020's cuts with the reason — a reader must not have to infer the difference
  between "coming in Phase 3" and "deliberately not coming."

- A test fails if a BUILT row does not resolve to a real path or a PLANNED row already exists.
- **Partly obsolete:** the interrupted discussion's first area (the orchestration port's prose spec)
  was settled and then cut with ARCH-05 — the port is built in Phase 2 under ORCH-01, unspecified in
  prose. The `SpecialistResult` decisions from that session survive; see `01-DISCUSS-CHECKPOINT.json`
  in the phase directory.

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

| Phase 01 P01 | 14m | 3 tasks | 6 files |
| Phase 01 P02 | 20min | 3 tasks | 2 files |

### Decisions

21 LOCKED ADRs in `docs/DECISIONS.md`, mirrored into `.planning/PROJECT.md` § Key Decisions.
Read `docs/DECISIONS.md` before proposing an architectural change; supersede with a numbered entry
rather than diverging silently. Most load-bearing for current work:

- **ADR-020** — **the buildable scope is the orchestrator spine.** 9 phases → 3; 18 requirements
  moved to v2 with acceptance intact, each owed a designed-not-built entry in the handoff. Retained
  deliberately: the disposition gate, no-aggregate-score, crash-and-resume, model-call idempotency.

- **ADR-021** — **retrieval is back in the spine; the refusal path is a log line.** RETR-01/02
  restored reduced (RETR-03 stays cut); `SpecialistResult` carries no completion status; VAL-02
  reduces to logging. **ADR-006 untouched — vector and lexical only, no graph database, ever.**

- **ADR-012** — LangGraph, decided on cost not correctness (all three candidates passed all four
  legs). **Stands as decided; no longer under re-test (ADR-020).** The second adapter that would have
  proven the port is cut, so **the no-import test is now the sole lock-in protection** — nodes depend
  on our own port, never `from langgraph import ...`.

- **ADR-011 / ADR-014** — the human disposition gate and the no-aggregate-score rule. Both enforced
  structurally and both NON-NEGOTIABLE.

- **ADR-015 / ADR-018 / ADR-019** — gateway on the official `anthropic` SDK; a refusal raises rather
  than returning; structured output is one tool call and is verified, not trusted; no tier needs Opus.

- **ADR-007** — iReports consumes an AWS-owned vector collection; local ingest/embedding is
  development only; all field mappings in one module.

- [Phase 01]: CONT-01: SpecialistResult/SpecialistCriterion published; SpecialistCriterion kept as the criterion-descriptor name, CONTRACT_VERSION not bumped since a new root contract changes no existing contract's shape
- [Phase 01]: P02: six build-state tables (one per subsystem grouping) rather than one large table, all sharing the identical header row the D-11 test parses on
- [Phase 01]: P02: packages/retrieval/ used as the shared PLANNED path for both RETR-01 and RETR-02, deferring the workers/ vs packages/ ingestion split to Phase 2 planning
- [Phase 01]: P02: Row in test_build_state_table.py is a plain tuple type alias, not a dataclass/NamedTuple, to keep the module's imports confined to stdlib + pytest

### Pending Todos

None captured yet.

### Blockers/Concerns

**Under ADR-020, none of the three GATE questions blocks the build** — the work that would have run
into them is not being built. That narrows what the project claims; it does not resolve anything.

- **Q-01 (GATE, open, refuses any working assumption)** — Claude availability, model and
  inference-profile ids, cross-region inference, and data-routing rules in GovCloud are unvalidated.
  All evidence to date is commercial-partition only. **Now left open with its cost stated rather than
  closed** (HAND-02 cut). Externally blocked on account access regardless.

- **Q-02 (GATE, open) — no longer a build gate, and NOT cleared.** No local OpenSearch and no mapping
  module, so nothing proceeds under a working assumption about the collection schema. Blast radius is
  unchanged for whoever builds retrieval. **Do not let any later document imply the gate was cleared.**

- **Q-03 (GATE, open) — no longer a build gate; still high blast radius and silent.** No local
  embedding means no parity to verify. A mismatch does not error; it retrieves worse. **No
  locally-measured retrieval quality may ever be presented as predictive of AWS behaviour.**

- **Cold start under SAM local is unmeasured and has NO scheduled phase** (ARCH-03 cut with the
  bake-off). `spikes/test_scorecard.py` still fails the moment a figure is recorded, which keeps the
  gap visible rather than closing it by omission. This is a deliberate, recorded cost of ADR-020.

- **Model-call idempotency is owed and unbuilt.** A crash mid-fan-out re-runs an in-flight model call
  — LangGraph 11/24, hand-rolled 12/24 over 24 trials. **Retained by ADR-020 as its most expensive
  keep.** Phase 2, ORCH-02.

- **Checkpoint row integrity is the single largest recorded security gap** (threat-model §6).
  **CKPT-01 is cut** — the spine exercises the store unhardened, and the gap is owed a
  designed-not-built entry under HAND-01.

- **`CLAUDE.md` § Current state is stale** — it says application code does not exist. The stack table
  was corrected to LangGraph on 2026-08-11; the state narrative was not, and it now also predates
  ADR-020. Phase 1, ARCH-04.

- **`bedrock` adapter has never been run in any partition.** Verified as correctly constructed and
  nothing more — do not read the green test suite as connectivity. **HAND-03 cut**; recorded as a
  known gap.

- **The handoff package now carries more design and less evidence.** ADR-020 consequence 4: a larger
  share of the package is asserted rather than demonstrated, so the unbuilt sections must say plainly
  that they are unbuilt. This is the real cost of the pare-down.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| **Scope (ADR-020)** | **18 requirements cut to the spine — 2nd adapter & bake-off (ORCH-05, BAKE-01, ARCH-03, ARCH-05), checkpoint hardening (CKPT-01..03), retrieval (RETR-01..03, CONT-02), routing (ROUT-01..02), citation validators (VAL-01), outbox (DEL-01), inventory & GovCloud (ARCH-02, HAND-02..03)** | In `REQUIREMENTS.md` § v2 § Cut by ADR-020, acceptance intact; each owed a designed-not-built entry under HAND-01 | 2026-08-11 |
| Milestone | M3 Optimize — candidate pool is now the ADR-020 cuts plus the originals, unordered | Placeholder, not decomposed | 2026-08-11 (ingest) |
| Contracts | `EntityCandidate`, `TimelineEvent` | Blocked on Q-02, no consumer | 2026-08-11 |
| Security | Checkpoint encryption at rest / retention & pruning | Blocked on Q-01 / Q-09 | 2026-08-11 |
| Gateway | Retry & fallback policy, streaming run status, `MAX_EXCERPT_CHARS`, prompt caching | v2 (Q-04, Q-13) | 2026-08-11 |

## Session Continuity

Last session: 2026-08-11T21:08:16.206Z
Stopped at: Completed 01-02-PLAN.md (component-architecture write-up, ARCH-01); proceeding to 01-03
`.planning/ROADMAP.md` and `REQUIREMENTS.md` are updated. **Two follow-on writes are owed and not
yet done:** a numbered ADR entry recording the outcome-level re-test and the Strands amendment, and
`docs/ROADMAP.md` (which still describes the old milestone shape). No implementation work has
started under GSD; the repo's own prior work is inventoried above.
Resume file: None

**Cold-start reading order:** this file → `.planning/ROADMAP.md` § Gates → `docs/DECISIONS.md` →
`docs/OPEN-QUESTIONS.md`. `blueprint.md` is the project's **input**, lowest precedence; where it
conflicts with `docs/DECISIONS.md`, DECISIONS.md wins.
