# Phase 1: Close the architecture package - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-11
**Phase:** 1-close-the-architecture-package
**Areas discussed:** Orchestration port boundary (later cut), `SpecialistResult` shape, project scope
(unplanned — produced ADR-020 and ADR-021), build-state table enforcement, write-up home and depth,
entry-document refresh scope

> **This discussion changed the project.** It began against a 9-phase roadmap and ended against a
> 3-phase one. The user interrupted mid-flight to pare the scope; that produced ADR-020, and a
> follow-on clarification produced ADR-021. Areas discussed before the interruption are recorded
> below with their outcome, including the one whose subject no longer exists.

---

## Orchestration port boundary — SETTLED, THEN CUT

Four questions were asked and answered before ADR-020 removed the requirement they served. Recorded
because the reasoning is still good and Phase 2 may want it.

### Q1 — How much of the port lands in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Prose spec only | A precise section in the write-up; no `packages/orchestration/` until Phase 2 | ✓ |
| Prose + Protocol code, no adapters | The spec plus an importable `port.py` | |
| Prose + Protocol + conformance skeleton | The above plus a parameterized suite with no adapters registered | |
| You decide | | |

**User's choice:** Prose spec only.
**Notes:** Kept Phase 1 a documentation-and-contract phase and avoided a port designed with zero
implementations pulling on it.

### Q2 — What level of precision does the spec commit to?

| Option | Description | Selected |
|--------|-------------|----------|
| Typed signatures + obligations | Signatures in a fence referencing real domain contracts, plus a numbered obligations list | ✓ |
| Obligations only, no signatures | Operations in English, no signatures | |
| Signatures + obligations + neutrality clauses | The first, plus an explicit "what an adapter may not assume" section | |

**User's choice:** Typed signatures + obligations.
**Notes:** The third option bundled the durability invariants; declining it prompted Q4 to ask about
those separately rather than assume they were unwanted.

### Q3 — Relationship to the existing `spikes/harness/port.py`?

| Option | Description | Selected |
|--------|-------------|----------|
| Derived from contracts, spike as prior art | Write from the domain contracts; cite the spike as evidence a two-face port survived three implementations | ✓ |
| Generalize the spike port | Treat the spike as the draft and clean it up | |
| Derived from contracts, with an explicit delta section | The first, plus a section on where the spike falls short | |

**User's choice:** Derived from contracts, spike as prior art.
**Notes:** The spike port was written for four control-flow legs and carries no budgets, no node
registration, no retrieval — generalizing it would have baked in the spike's scope.

### Q4 — Where do the durability invariants live?

| Option | Description | Selected |
|--------|-------------|----------|
| Port obligations — both adapters bound | State them adapter-neutrally: state durable before a node returns, nothing carried in memory across the process boundary, deserialized state re-validated | ✓ |
| LangGraph settings — stay in ORCH-01 | Leave them as `durability="sync"` and strict deserialization in ORCH-01's acceptance | |
| Obligations list, cross-referenced | Both, pointing at each other | |

**User's choice:** Port obligations — both adapters bound.
**Notes:** Asked explicitly rather than inferred, since Q2's answer had declined the option that
bundled them. **Still relevant after the cut:** these invariants now live only in ORCH-01's
acceptance. Phase 2 should not lose them.

**Outcome:** This entire area was cut by ADR-020. Its purpose was letting two adapters be written
without either shaping the port; ADR-020 cut the second adapter. The port is built directly in
Phase 2 under ORCH-01.

---

## `SpecialistResult` shape

### Q1 — Does it carry an explicit completion status?

| Option | Description | Selected |
|--------|-------------|----------|
| Required status, full enum | `COMPLETE` / `INCOMPLETE_DUE_TO_BUDGET` / `REFUSED` / `STRUCTURED_OUTPUT_ERROR` / `BLOCKED`, no default | ✓ (later reversed) |
| Required status, two members | `COMPLETE` / `INCOMPLETE`; the reason lives in an `InformationGap` | |
| No status field | Status lives on the run manifest and the node | ✓ (final) |

**User's choice:** Initially the full enum; **reversed later in the discussion** once the contract's
purpose was clarified in plain terms.
**Notes:** The reversal came with the reasoning: *"I don't think we need this. We should LOG things
and check the logs, but not require the orchestrator to do anything special. Again, we are just
proving out the architecture, not building the full solution or doing Model Evaluation."* Recorded
as ADR-021 § 2. The trade is accepted knowingly: an empty findings list from a refusal is
indistinguishable at the artifact level from a criterion that came back clean.

### Q2 — Per-query budget accounting?

| Option | Description | Selected |
|--------|-------------|----------|
| Consumption + which ceiling was hit | `BudgetConsumption` plus the specific ceiling, cross-validated against status | |
| Consumption only | A required `BudgetConsumption` per query | |
| Neither — run-level is enough | `RunManifest.consumption` already accumulates | ✓ |

**User's choice:** Neither — run-level is enough.
**Notes:** Keeps the contract to analysis output. Stated trade: a truncated analysis arrives with no
per-query account of what it spent.

### Q3 — What identifies a query that produced zero findings?

| Option | Description | Selected |
|--------|-------------|----------|
| Criterion + provenance | A criterion descriptor plus the existing `GeneratedBy` | ✓ |
| Criterion + provenance + tool allowlist id | The above plus which allowlist was in force | |
| Criterion + provenance + evidence considered | The above plus the evidence span ids handed in | |

**User's choice:** Criterion + provenance.
**Notes:** The question flagged that `FindingAuthority` cannot be reused verbatim — it requires ≥1
policy citation, and a query does not cite. The descriptor is a new sibling type without that
requirement.

### Q4 — Where does a refusal's blocking `InformationGap` live?

**Asked twice; not answered either time.** The first attempt was interrupted by the scope pare-down.
The second was interrupted by the user asking what "refusal" meant — which surfaced that the
question was built on machinery the user did not want. Superseded by Q1's reversal and by ADR-021 § 3
(VAL-02 reduced to logging), so the question no longer applies.

---

## Project scope — UNPLANNED, produced ADR-020

Raised by the user mid-discussion: *"Before we move on, I really think we need to pair-down the
requirements and have the POC be more simple...just orchestrating sub calls."*

### Q1 — How far down?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop the dual-adapter bake-off | One adapter as ADR-012 decided; 9 phases → ~6 | |
| That, plus stub the seams AWS owns | No OpenSearch, one policy pack, envelope to disk; ~4 phases | |
| Orchestrator spine only | Load a case, fan out to bounded sub-calls, budgets, crash/resume, human gate, typed JSON; ~3 phases | ✓ |
| Just thin Phase 1 | Leave the roadmap alone | |

**User's choice:** Orchestrator spine only.

### Q2 — What stays non-negotiable? (multi-select)

| Option | Description | Selected |
|--------|-------------|----------|
| Human disposition gate | ADR-011 | |
| No aggregate score | ADR-014 | |
| Evidence before inference | VAL-01 | |
| Crash and resume across a process boundary | The durable-checkpoint leg | ✓ |

**User's choice:** Crash and resume only.
**Notes:** This triggered a **stop-and-raise**, which `CLAUDE.md` requires when a change would let a
run reach delivery without a recorded human disposition. The two omitted guardrails are already built
and passing tests, so cutting them would have meant deleting working code rather than simplifying.
Evidence-before-inference was accepted as a genuine cut — resolving citations needs a real evidence
snapshot to mean anything.

### Q3 — Confirming the two already-built guardrails

| Option | Description | Selected |
|--------|-------------|----------|
| Keep both — they're already free | Both stay; VAL-01 is cut as selected | ✓ |
| Keep the gate, relax the score rule | Would contradict ADR-014 and need a superseding entry | |
| Cut both — spine only, truly | Would contradict ADR-011 and ADR-014 and need two superseding entries plus a `CLAUDE.md` edit | |

**User's choice:** Keep both.

### Q4 — Does the three-phase shape look right?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — restructure to this | Contract-and-boundary / spine / gate-and-handoff | ✓ |
| Merge into two phases | Fold the gate into the spine phase | |
| Split the sub-call fan-out out | Four phases, each independently verifiable | |

**User's choice:** Yes.

### Q5 — Model-call idempotency (ORCH-02), in or out?

| Option | Description | Selected |
|--------|-------------|----------|
| In — it is the thesis | A crash mid-fan-out currently re-runs an in-flight model call: 11/24 under LangGraph | ✓ |
| Out — measure it, do not fix it | Record the duplicate-call rate as an unfixed finding | |
| Out entirely | Carry it as a known gap | |

**User's choice:** In.
**Notes:** The most expensive item retained. Durable orchestration of paid sub-calls is not a proven
claim if resuming double-pays.

---

## Retrieval — reversed a cut made 40 minutes earlier

Surfaced when the user described the architecture: *"we have the orchestration model that is kicking
off a sub-agent call/skill (with opensearch RAG search) to review the adjudication case."*

| Option | Description | Selected |
|--------|-------------|----------|
| RAG is in — reverse that cut | Local OpenSearch, one synthetic case indexed, query behind the port, field names in one PROVISIONAL module | ✓ |
| Handed-in evidence — keep the cut | Spans from a synthetic fixture through the port's interface | |
| Port + a stub now, OpenSearch later | In-memory adapter; swap is a one-file change | |

**User's choice:** RAG is in.
**Notes:** ADR-020 had cut retrieval reasoning that fan-out, budget exhaustion, and crash-mid-flight
do not depend on where evidence came from. That was wrong about the architecture — the search is what
the sub-agent *does*. Recorded as ADR-021 § 1. **RETR-03 (embedding provenance, parity check) stays
cut** as model-evaluation work; Q-03 remains a documented unknown.

---

## Build-state table enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — a test, it is ~20 lines | Parse the table; fail if a `BUILT` path is missing or a `PLANNED` path already exists | ✓ |
| No — just keep the table accurate | Humans keep it current | |

**User's choice:** Yes — a test.
**Notes:** The staleness this guards against already happened in this repository, which is why
ARCH-04 exists.

---

## Write-up home and depth

**First attempt** offered `docs/handoff/` at package depth, `docs/handoff/` at "node-level" depth, or
a split boundaries/design pair. The user responded: *"No Graph Database! only vector in this
architecture."* — reading "node-level" as graph-database nodes. Already ADR-006 and locked; the
question was re-asked without the ambiguous word.

| Option | Description | Selected |
|--------|-------------|----------|
| Boxes: packages and external systems | Our packages plus AWS ingestion, OpenSearch, ASAP, the reviewer | |
| Boxes plus the workflow steps inside them | The same boxes, then one level down inside the orchestrator | ✓ |
| Boxes plus a walked example | The boxes, then one synthetic case traced through | |

**User's choice:** Boxes plus the workflow steps inside them.
**Notes:** All three options were `docs/handoff/` with Mermaid inline — that part was not contested.

---

## Entry-document refresh scope

| Option | Description | Selected |
|--------|-------------|----------|
| The stale claims plus ADR-020 scope | Fix what is provably wrong in `CLAUDE.md` § Current state and `README.md` § Status | ✓ |
| That, plus a full pass on `CLAUDE.md` | Also reconcile target layout, stack table, and rules sections | |

**User's choice:** The stale claims plus ADR-020 scope.
**Notes:** A flag is carried into CONTEXT.md D-12 — `CLAUDE.md`'s target layout and stack table still
describe cut subsystems as if being built. The narrow scoping is respected; an outright contradiction
should be surfaced rather than left in place.

---

## Claude's Discretion

- Section ordering and headings within the write-up.
- Exact field names on `SpecialistResult` and the name of the criterion-descriptor type.
- Whether the build-state table is one table or one per subsystem, provided the test can parse it.
- Whether the contract-version constant bumps.
- Where the build-state test lives (`tests/` currently has only `contract/` and `live/`).

## Deferred Ideas

- The orchestration port's prose spec — settled in full, then cut with the second adapter. Its
  durability invariants now live only in ORCH-01's acceptance; Phase 2 should not lose them.
- ADR-012's pre-registered supersession criteria (ARCH-05) — cut with the bake-off. The instinct
  (criteria invented after the effort get judged against the effort) is worth keeping.
- Result-level `information_gaps` with a cross-field validator — superseded by ADR-021 § 3.
- Per-query budget accounting naming the ceiling that fired.
- Tool-allowlist id and evidence-considered list on `SpecialistResult`.
- A full coherence pass over `CLAUDE.md`.
- `docs/ROADMAP.md` reconciliation — Phase 3, HAND-01.
