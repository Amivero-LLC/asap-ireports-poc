# Synthesis Summary

Entry point for `gsd-roadmapper`. Produced by `gsd-doc-synthesizer` from 12 per-doc classifications.

**Project:** asap-ireports — a reference implementation of a local-first, bounded-agentic
case-analysis platform for US federal suitability, fitness, and national-security eligibility
adjudication.

**Mode:** new · **Date:** 2026-08-11 · **Existing `.planning/` context:** none

---

## Doc counts by type

| Type | Count | Sources (precedence) |
|---|---|---|
| ADR | 2 | `docs/DECISIONS.md` (0, **LOCKED**), `docs/OPEN-QUESTIONS.md` (1) |
| PRD | 1 | `docs/ROADMAP.md` (2) |
| SPEC | 1 | `CLAUDE.md` (3) |
| DOC | 8 | `orchestration-scorecard.md` (4), `orchestration-landscape.md` (5), `contracts.md` (6), `model-gateway.md` (7), `compatibility-matrix.md` (8), `checkpoint-threat-model.md` (9), `README.md` (10), `blueprint.md` (11) |
| **Total** | **12** | all `high` confidence, all `manifest_override: true` |

No document was classified UNKNOWN, and none was low confidence.

**Precedence is per-document and integer-valued, not type-derived.** All twelve values are distinct
(0..11), forming a strict total order. The type ordering `ADR > SPEC > PRD > DOC` was **not** used —
it does not encode this project's actual rule, in which `docs/ROADMAP.md` (PRD) outranks `CLAUDE.md`
(SPEC), and `blueprint.md` is deliberately last.

**The single most important precedence rule:** `blueprint.md` is the INPUT to this project, not its
output. Wherever it conflicts with `docs/DECISIONS.md`, DECISIONS.md wins. Six such divergences were
found and every one resolved in favour of the ADR — recorded rather than dropped, because the
program team reading this handoff needs to see the divergence was deliberate.

---

## Decisions

**19 LOCKED decisions**, all from `docs/DECISIONS.md` (precedence 0), all status `Accepted`:
ADR-001 through ADR-019. Each was extracted as its own decision; the file was **not** collapsed into
one entry.

Amendment chain preserved rather than flattened:
- ADR-015 amends ADR-008
- ADR-017 amends ADR-015 (route: LiteLLM native `/v1/messages`, base URL verbatim)
- ADR-018 amends ADR-015 (a requested schema is verified, not trusted)
- ADR-019 supersedes the structured-output *mechanism* in ADR-015 and the per-model-group
  *diagnosis* in ADR-018; ADR-018's `StructuredOutputError` guard survives
- ADR-012 moved Open → Accepted on 2026-08-11 and retains its original bake-off reasoning above its
  Resolution section

The headline decision: **ADR-012 — the orchestration framework is LangGraph**, resolved 2026-08-11
on a measured four-leg bake-off, not on the blueprint's paper comparison.

**14 open questions**, from `docs/OPEN-QUESTIONS.md` (precedence 1, **not locked** — nothing there
is decided). Q-01, Q-02, Q-03 are **GATE items** and must be answered before the work they block
starts. Q-01 uniquely refuses any working assumption, and all model evidence to date is
commercial-partition only — it says nothing about AWS GovCloud.

→ `intel/decisions.md`

---

## Requirements

**24 requirements** extracted from the single PRD, `docs/ROADMAP.md`. Because only one PRD is in the
set, there are **no competing acceptance variants** — no requirement carries divergent acceptance
criteria from two sources.

Milestone status as of 2026-08-11:

| Milestone | Status |
|---|---|
| 1a Architecture package | Contracts DONE (2026-08-10). **Component-architecture write-up OUTSTANDING — the last item blocking program sign-off on 1a.** |
| 1b Orchestration landscape scan | COMPLETE (2026-08-10) |
| 1c Orchestration bake-off | COMPLETE (2026-08-11) — ADR-012 Accepted, framework is LangGraph |
| 2 Orchestrator produces an iReport | Not started |
| 3 Optimize | Not started, **no exit criteria stated** |
| Continuous handoff package | Ongoing |

Milestone-scoped IDs: `REQ-component-architecture` (outstanding) · `REQ-library-inventory` (partly
covered) · `REQ-data-contracts` (done) · `REQ-authority-routing-model` (contract done) ·
`REQ-orchestration-landscape-scan` · `REQ-bakeoff-four-legs` · `REQ-langsmith-egress-deny` ·
`REQ-checkpoint-threat-model` · `REQ-resume-semantics-assertion` · `REQ-orchestrator-on-langgraph` ·
`REQ-model-call-idempotency` · `REQ-synthetic-case-ingest` · `REQ-authority-routing-engine` ·
`REQ-specialist-query` · `REQ-deterministic-validators` · `REQ-human-review-gate` ·
`REQ-asap-delivery-outbox` · `REQ-refusal-to-information-gap`

Outstanding work items carried forward, each recorded in a source doc and each real and unbuilt:
`REQ-cold-start-measurement` · `REQ-checkpoint-row-integrity` (the single largest security gap) ·
`REQ-checkpoint-least-privilege` · `REQ-checkpoint-encryption-at-rest` · `REQ-checkpoint-retention` ·
`REQ-checkpoint-provenance-on-load` · `REQ-deferred-contracts` (4, blocked on Q-02) ·
`REQ-specialist-result-contract` (block lifted by ADR-012) · `REQ-fix-mypy-tests-contract` (13
pre-existing errors in `tests/contract/`) · `REQ-max-excerpt-chars` ·
`REQ-migrate-spike-to-gateway-port` · `REQ-retry-fallback-policy` · `REQ-streaming-run-status`

→ `intel/requirements.md`

---

## Constraints

**24 constraints**, primarily from `CLAUDE.md` (precedence 3, SPEC), reinforced by LOCKED ADRs.

By type: **protocol** 11 · **schema** 4 · **api-contract** 6 · **nfr** 4 (approximate; several
constraints span types).

**Eight are marked NON-NEGOTIABLE and must survive into every downstream artifact:**

1. **Decision-support boundary** — the system must never grant, deny, revoke, suspend, or otherwise
   make a final suitability, fitness, credentialing, or national-security eligibility determination.
2. **No universal person-risk score** — no aggregate risk score, risk level, or overall
   recommendation field in ANY contract (ADR-014), whatever it is named.
3. **Human disposition gate** — nothing reaches ASAP without a recorded human disposition. No
   bypass, in any profile, including local development. A state transition, not a config flag
   (ADR-011).
4. **Never hard-code a model ID** — the three LiteLLM aliases only, in application code.
5. **Evidence before inference** — every material factual statement carries a resolvable citation;
   deterministic validators reject unsupported citations before a human sees them.
6. **Deterministic shell around probabilistic reasoning** — the model reasons; it does not decide
   control flow, and it does not decide whether its own output is valid.
7. **Synthetic data only, ever** — no real case data in fixtures, tests, or examples.
8. **Raw case text never in logs, traces, or error messages.**

Three `CLAUDE.md` entries are marked **SUPERSEDED** by higher-precedence ADRs and retained so the
divergence is visible: the orchestration framework (stale "Undecided"), the LiteLLM-only model
gateway (ADR-015 adds a direct `bedrock` adapter behind the same port), and the
`packages/` layout list (omits `packages/gateway/`).

→ `intel/constraints.md`

---

## Context

**16 topics** from the 8 DOC sources, each with source attribution.

Unique blueprint contributions preserved as context because nothing higher-precedence supersedes
them: why authority routing is essential (§2.1); the `RunState` identifiers-not-transcripts model
(§8.2); the tool allowlist and prohibited-tool list (§8.4); loop limits, budgets, and termination
including the no-progress and duplicate-query detectors (§8.5); the specialist set (§8.3); contract
versioning (§10.1); non-functional success criteria (§1.5); the five synthetic case designs
including the `NEG-005` negative control (§11).

Evidence-tag vocabulary preserved and required to travel with any quoted claim: `[measured]`,
`[first-party]`, `[secondary]`, `[judged]`, `[unverified]`.

→ `intel/context.md`

---

## Conflicts

**0 blockers · 3 competing/ambiguous (WARNING) · 24 auto-resolved (INFO)**

No LOCKED-vs-LOCKED contradiction. No UNKNOWN/low-confidence document. No cycle blocked synthesis.

The three WARNINGs need a human decision before routing:

1. **Three source documents still say the orchestration framework is undecided** — `CLAUDE.md` and
   `README.md` contradict ADR-012 (Accepted, LangGraph). Precedence resolves the intel; it does not
   fix the files, and `CLAUDE.md` is the live instruction file every agent in this repo reads.
2. **Milestone 3 has no exit criteria** and explicitly refuses to be sequenced from its own
   candidate list. It cannot be decomposed into phases without inventing scope.
3. **Q-02 is an OPEN GATE that blocks work Milestone 2 lists as in-scope** — local OpenSearch index
   definition. Precedence alone would mark M2 blocked, which is likely not the intent.

Cycle detection: 21 cycles found across 12 nodes / 60 edges, max traversal depth 4 (cap 50). All are
ordinary bidirectional documentation hyperlinks, and all are broken by the strict integer precedence
total order. **Recorded as INFO rather than as blockers — a judgment call documented in
INGEST-CONFLICTS.md INFO-01.**

→ `../INGEST-CONFLICTS.md`

---

## Files

| File | Contents |
|---|---|
| `.planning/intel/decisions.md` | 19 LOCKED ADRs + 14 open questions |
| `.planning/intel/requirements.md` | 24 requirements + 13 outstanding work items, by milestone |
| `.planning/intel/constraints.md` | 24 constraints, 8 non-negotiable |
| `.planning/intel/context.md` | 16 topics from 8 DOC sources |
| `.planning/INGEST-CONFLICTS.md` | 0 blockers, 3 warnings, 24 info |
| `.planning/intel/classifications/*.json` | 12 per-doc classifications (inputs) |
