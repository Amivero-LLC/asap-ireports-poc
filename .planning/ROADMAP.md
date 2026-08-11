# Roadmap: asap-ireports

## Overview

**The buildable scope is the orchestrator spine (ADR-020).** Three phases, not nine. The project is
sequenced so that the one risk `CLAUDE.md` names — *the agentic orchestrator is harder than it looks*
— is retired with running code, and everything else is designed in the handoff package and marked
unbuilt.

The spine, stated once:

> One command loads a synthetic case, fans out to bounded specialist sub-calls through the
> `ModelGateway` port on tier aliases, enforces budgets and loop limits in the deterministic shell,
> survives a crash mid-fan-out and resumes in a separate process without double-paying for an
> in-flight model call, pauses for a recorded human disposition, and emits a validated typed
> envelope.

Phase 1 publishes the contract and the boundary the build needs, and makes the entry documents true.
Phase 2 is the thesis: the orchestrator, the sub-calls, the budgets, the crash, the resume. Phase 3
closes the loop with the human gate and typed output, and brings the handoff package to a state the
ASAP program team can act on — including an explicit account of what was designed and not built.

`docs/ROADMAP.md` describes the older, wider milestone shape and is **superseded by this file and by
ADR-020**. Reconciling it is a Phase 3 obligation.

Milestone 3 is a named placeholder with no phases. See § Milestone 3 below.

---

## Gates

Three GATE questions in `docs/OPEN-QUESTIONS.md` are open. **None is cleared.** ADR-021 restored
retrieval to the spine, so Q-02 is a live containment concern again.

### Q-02 — AWS vector collection schema · OPEN · **contained, NOT cleared**

Phase 2 proceeds under Q-02's working assumption because RETR-01/02 are back in scope (ADR-021). The
containment argument is ADR-007's and it is the only reason proceeding is defensible: **every field
name, filter, and facet mapping is isolated to one module, so adapting to the real AWS collection
schema is a one-file change.** RETR-01 requires that module's header to name Q-02 explicitly, so no
reader can mistake it for confirmed. Q-02 becomes high blast radius rather than medium if the real
shape is structurally different — separate collections per corpus, or nested documents. It resolves
only when the ingestion team supplies actual index mappings. **No document may imply the gate was
cleared.**

### Q-03 — Query-time embedding parity · OPEN · **not a build gate; high blast radius and silent**

RETR-03 stays cut, so there is no parity check and no embedding-provenance record. **Nobody may read
locally-measured retrieval quality as predictive of AWS behaviour.** A mismatch between the
query-time embedding model and the model that populated the AWS collection does not error — it
retrieves worse, silently, and every downstream number becomes meaningless without anyone noticing.
Local embedding is development only (ADR-007). The handoff records the coupling as unverified.

### Q-01 — Claude model availability in AWS GovCloud · OPEN · **refuses any working assumption**

The one item this project declines to assume, and now the one it declines to close. All model
evidence is commercial-partition only and says nothing about GovCloud. HAND-02 is cut with the rest
of the GovCloud work; Phase 3 records the cost of not knowing rather than guessing. Externally
blocked on account access regardless.

---

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Close the architecture package** - The component-architecture write-up, the
      `SpecialistResult` contract, and entry documents that describe the actual current state

- [ ] **Phase 2: Bounded sub-calls that survive a crash** - The orchestrator fans out through the
      gateway port, enforces its own limits, dies mid-fan-out, and resumes without double-paying

- [ ] **Phase 3: Human gate, typed output, and the handoff** - The run pauses for a disposition,
      resumes, emits a validated envelope, and the package states plainly what was not built

## Phase Details

### Phase 1: Close the architecture package

**Goal**: Program leadership can sign off on Milestone 1a's component boundaries, the build has the
contract it needs, and the repository's entry documents stop asserting things that are no longer
true.
**Depends on**: Nothing (Milestones 1b and 1c are complete)
**Requirements**: ARCH-01, ARCH-04, CONT-01
**Success Criteria** (what must be TRUE):

  1. A reader of the component-architecture write-up can point to where our system ends and the AWS
     ingestion pipeline, ASAP, and the human reviewer begin — and program leadership signs off on
     those boundaries.

  2. The write-up marks every component BUILT, PLANNED (naming the phase that delivers it), or
     NOT OURS, **and separately marks what ADR-020 cut as DESIGNED-NOT-BUILT with the reason** — a
     reader must not have to infer the difference between "coming in Phase 3" and "deliberately not
     coming."

  3. A test fails if a BUILT row does not resolve to a real path, or a PLANNED row already exists.
  4. `SpecialistResult` is published to `schemas/` with contract tests, carrying no aggregate score
     field.

  5. `CLAUDE.md` § Current state and `README.md` § Status no longer assert that application code does
     not exist or that the orchestration framework is undecided, and both reflect ADR-020's scope.
**Plans**: 3 plans, in 3 waves
Plans:

- [x] 01-01-PLAN.md — `SpecialistResult` contract (CONT-01): the Pydantic v2 model, generated JSON
      Schema, contract tests, and the lifted deferral in `docs/handoff/contracts.md`

- [ ] 01-02-PLAN.md — The component-architecture write-up (ARCH-01): two Mermaid levels, the
      four-marker build-state tables, the designed-not-built account, and the test that enforces them

- [ ] 01-03-PLAN.md — Entry documents made true (ARCH-04): `CLAUDE.md` § Current state and
      `README.md` § Status carry the measured inventory and ADR-020's three-phase scope

*Diagrams are Mermaid fences inside the write-up*, canonical there rather than exported — the
diagram and the prose stay one reviewable artifact, and it diffs. The build-state table is enforced
by a test for the same reason ARCH-04 exists at all: `CLAUDE.md`'s state narrative went stale and
nothing caught it.

*The DESIGNED-NOT-BUILT category is new and is the load-bearing part of this phase under ADR-020.*
A handoff package that quietly omits what it did not build is the failure ADR-001 is written
against.

*Cut from this phase by ADR-020:* the orchestration port's prose specification and ADR-012's
pre-registered supersession criteria (ARCH-05). Both existed to serve a dual-adapter bake-off that
is no longer happening. The port itself is still built in Phase 2 — ORCH-01 is untouched.

### Phase 2: Bounded sub-calls that survive a crash

**Goal**: The orchestrator fans out to bounded specialist sub-calls through the gateway port,
enforces its own ceilings, dies mid-fan-out, and resumes in a different process without re-running an
in-flight model call — with no analysis node aware of LangGraph.
**Depends on**: Phase 1
**Requirements**: ORCH-01, ORCH-02, ORCH-03, ORCH-04, SPEC-01, VAL-02, RETR-01, RETR-02, QUAL-02
**Success Criteria** (what must be TRUE):

  1. `packages/orchestration/` exposes this project's own port with a LangGraph adapter behind it,
     and a test proves no file outside the adapter imports LangGraph.

  2. `durability="sync"` and strict checkpoint deserialization are set in code with tests — both
     defaults are wrong here and invisible when reading a graph.

  3. One synthetic case is indexed into local OpenSearch, and the sub-agent retrieves against it by
     vector + lexical query with a mandatory case filter and bounded K — **no graph database, ever
     (ADR-006)**. Every field name, filter, and facet mapping lives in one module whose header names
     Q-02 and states that the AWS collection's real schema is unconfirmed.

  4. A specialist sub-call against one criterion returns a typed `SpecialistResult` — criterion,
     provenance, and proposed findings with citations, **and no completion-status field** — obtained
     through the `ModelGateway` port on a tier **alias**, with a criterion-specific tool allowlist and
     every prohibited tool unreachable.

  5. A run survives a mid-node process kill and resumes in a separate process without re-executing
     completed work.

  6. A crash mid-fan-out does not re-run an in-flight model call — measured as 0 duplicate paid calls
     over the same 24-trial harness that measured LangGraph at 11/24 and hand-rolled at 12/24.

  7. A node that hits a model-call, tool-call, token, or wall-clock ceiling emits
     `INCOMPLETE_DUE_TO_BUDGET` and routes to human review, not to failure.

  8. A model refusal and a `StructuredOutputError` are **logged** with `run_id`, `case_id`, and the
     criterion, and never become an empty string. No `InformationGap` plumbing, no review routing
     (ADR-021).

  9. LangSmith egress is proven closed at every production entry point by a fail-closed test, not
     merely configured closed.
**Plans**: TBD

*This is the phase the project exists for.* Everything before it is contracts and everything after
it is closing the loop. If the orchestrator is harder than it looks, this is where that shows up.

*Model-call idempotency (criterion 5) is the most expensive item ADR-020 retained,* and the only one
retained on cost rather than on being nearly free. It is owed by all three bake-off candidates and
was built by none of them. Durable orchestration of paid sub-calls is not a proven claim if resuming
double-pays.

*The sub-agent's RAG search is what the sub-agent is (ADR-021).* ADR-020 cut retrieval on the
reasoning that evidence could be handed in from a fixture; that was wrong about the architecture — a
fixture-fed specialist demonstrates a fan-out, not this system. RETR-01 and RETR-02 are restored
reduced. **RETR-03 stays cut**: embedding provenance and the parity check are model-evaluation work,
and Q-03 stays a documented unknown rather than a build gate.

*Criterion 8 is a deliberate weakening, recorded rather than hidden.* Models decline with HTTP 200
and a possibly-empty content list; read naively, a refused specialist returns `""`. The gateway
already raises `ModelRefusalError` on `stop_reason` before touching content, so that cannot happen.
What is **not** built is the reviewer-facing path: a refused sub-agent produces an empty findings
list that is indistinguishable at the artifact level from a criterion that came back clean, and the
distinction lives only in the log. **This is the weakest point in the spine** and is owed a
designed-not-built entry under HAND-01. Refusals are expected in normal operation — adjudicative case
files routinely discuss criminal conduct, substance use, and foreign contacts.

### Phase 3: Human gate, typed output, and the handoff

**Goal**: One command takes a synthetic case to a human-approved, validated typed envelope — and the
ASAP program team receives a package that states plainly what was built, what was designed and not
built, and what it would cost to be wrong.
**Depends on**: Phase 2
**Requirements**: REV-01, REV-02, DEL-02, HAND-01
**Success Criteria** (what must be TRUE):

  1. A run pauses in an explicit review state; a disposition is recorded by a **different process**
     than the one that proposed the finding; the run resumes from the checkpoint.

  2. No path in the state machine reaches output without a recorded human disposition — proven by
     walking the transition table — and no bypass exists in any profile, including local development.

  3. Both the immutable machine proposal and the human-approved version are retained and separately
     readable.

  4. One command takes a synthetic case end to end — load, fan-out, budgets, validation, review gate,
     typed envelope — and produces a human-approved result under a single invocation.

  5. The handoff package is current: decisions, open questions, contracts and schemas, **and a
     section on what was designed and deliberately not built, with the reason for each** — every
     claim cited or carrying an explicit evidence tag.

  6. Known failure modes and things that did not work are recorded — described in the source as the
     most useful and most commonly omitted artifact.

  7. `docs/ROADMAP.md`, which still describes the pre-ADR-020 milestone shape, is reconciled or
     explicitly retired.
**Plans**: TBD

*No dev-mode auto-approve flag may be added to make criterion 1 convenient.* That affordance is
exactly the one that survives into production, which is why ADR-011 makes the gate a state transition
rather than a configuration option. ADR-011 and ADR-014 were both considered for ADR-020's cut and
both were explicitly kept.

*Criterion 5 is where ADR-020 is paid for.* A narrower build is only defensible if the package is
honest about the narrowing. Cold start under SAM local is unmeasured and now has no scheduled phase;
`spikes/test_scorecard.py` still fails the moment a figure is recorded, and that visible gap stays.

*The envelope is written to disk, not delivered.* ADR-010's envelope contract stands and is validated;
the transactional outbox and the ASAP mock (DEL-01) are cut and documented.

---

## Milestone 3 — Optimize (placeholder, **not decomposed**)

**Gated on measurements from the spine. No phases. No exit criteria.**

`docs/ROADMAP.md` gives Milestone 3 a goal — "widen and deepen against measurements, in the order the
evidence justifies" — an unordered candidate list, and one instruction: **"Sequence this from
findings — not from this list."**

Under ADR-020 the candidate list grows: everything cut in that entry is a Milestone 3 candidate
alongside the originals. Decomposing any of it now would invent scope and ordering the source
deliberately withheld. Candidates are recorded in `.planning/REQUIREMENTS.md` § v2, unordered.

**To open Milestone 3:** complete Phase 3, read what the spine actually measured, and run a fresh
roadmapping pass that sequences from those measurements. Do not linearize the candidate list.

---

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Close the architecture package | 1/3 | In Progress|  |
| 2. Bounded sub-calls that survive a crash | 0/TBD | Not started | - |
| 3. Human gate, typed output, and the handoff | 0/TBD | Not started | - |

**Milestone mapping:** Phase 1 closes Milestone 1a. Phases 2–3 are the orchestrator spine as defined
by ADR-020, and Phase 3 carries the Continuous handoff obligation to a checkpoint. Milestone 3 is a
placeholder above.

---

## Prior work (complete, not re-planned as phases)

Recorded here so a cold session does not re-derive it.

| Milestone | Status | Artifact |
|---|---|---|
| 1a · Data contracts | Complete 2026-08-10 | 13 Pydantic v2 contracts in `packages/domain/`, `schemas/`, `docs/handoff/contracts.md` |
| 1a · Model gateway | Complete 2026-08-10 | `packages/gateway/`, `docs/handoff/model-gateway.md`, `docs/handoff/compatibility-matrix.md` |
| 1a · Remainder | **Outstanding** | → Phase 1 (write-up, contract, entry docs) |
| 1b · Orchestration landscape scan | Complete 2026-08-10 | `docs/handoff/orchestration-landscape.md` |
| 1c · Orchestration bake-off (**partial spike**) | Complete 2026-08-11 | ADR-012 Accepted (LangGraph); `spikes/`, `docs/handoff/orchestration-scorecard.md`, `orchestration-scorecard.json`, `docs/handoff/checkpoint-threat-model.md` |

**1c's result stands and is no longer under re-test (ADR-020).** The outcome-level bake-off that would
have judged ADR-012 against the real workload is cut along with the second adapter. The protection
against lock-in is the port (ORCH-01), which Phase 2 builds. `spikes/` is retained in full per
ADR-001 — all three candidates, all four legs, still running.

---
*Roadmap created: 2026-08-11 from `.planning/intel/SYNTHESIS.md` (12 source documents, 19 LOCKED
ADRs, 0 ingest blockers).*
*Restructured: 2026-08-11 — port-first dual-adapter bake-off over the full seam-walk. 8 phases → 9.*
*Restructured: 2026-08-11 — **ADR-020: pared to the orchestrator spine. 9 phases → 3.** Cut the
second adapter and the outcome-level bake-off, checkpoint hardening, retrieval, authority routing,
the outbox, and the GovCloud gate; all moved to the handoff as designed-not-built. ADR-011 and
ADR-014 explicitly retained.*
