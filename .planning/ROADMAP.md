# Roadmap: asap-ireports

## Overview

The project is sequenced so the riskiest architectural claims are settled first and every phase
leaves behind an artifact the ASAP program team can act on (ADR-001). Milestones 1b and 1c are
already complete; the orchestration framework is decided (LangGraph, ADR-012) on measured evidence.

Phase 1 closes the last of Milestone 1a — the component-architecture write-up that program sign-off
is waiting on — and takes the cold-start measurement **before** any node is written against
LangGraph, because that is the one number most likely to reopen ADR-012. Phases 2 and 3 build the
orchestration spine behind our own port and harden the checkpoint store that spine depends on.
Phases 4 through 7 walk the case through the system once: evidence in, authority routed, one
specialist criterion analyzed, findings validated, a human disposition recorded, an envelope
delivered to the ASAP mock. Phase 7 is the Milestone 2 exit. Phase 8 makes the handoff package
current and confronts the GovCloud gate.

Milestone 3 is a named placeholder with no phases. See § Milestone 3 below.

---

## Gates

Three GATE questions from `docs/OPEN-QUESTIONS.md` are open. This roadmap does not clear any of
them. Two shape the plan directly.

### Q-02 — AWS vector collection schema · OPEN · **contained, NOT cleared**

Phase 4 **proceeds under Q-02's working assumption**: a single collection with a facet separating
case data from policy knowledge, plus case-file metadata facets applied post-ingestion via a
`document.xml` sidecar (ADR-007).

The containment argument is ADR-007's, and it is the only reason proceeding is defensible: **all
field names, filters, and facet mappings are isolated to one mapping module, so adapting to the real
AWS collection schema is a one-file change.** RETR-01 requires that module to be explicitly marked
PROVISIONAL, naming Q-02, so no reader can mistake it for confirmed.

**This is a decision to contain the risk, not evidence that the risk is gone.** The gate stays shut.
Q-02 becomes high blast radius rather than medium if the real shape is structurally different —
separate collections per corpus, or nested/parent-child documents. It resolves only when the
ingestion team supplies actual index mappings: field names, vector dimension, similarity metric, and
filterable metadata fields.

### Q-03 — Query-time embedding parity · OPEN · **high blast radius and silent**

**Nobody may read locally-measured retrieval quality as predictive of AWS behaviour.** A mismatch
between the query-time embedding model and the model that populated the AWS collection does not
error — it retrieves worse, and every downstream evaluation number becomes meaningless without
anyone noticing. RETR-03 requires per-vector embedding provenance and a parity check that fails
loudly on drift, and requires the handoff to record the coupling as unverified.

### Q-01 — Claude model availability in AWS GovCloud · OPEN · **refuses any working assumption**

The one item this project declines to assume. All model evidence to date is commercial-partition
only and says nothing about GovCloud. HAND-02 in Phase 8 closes it by re-running the live smoke
check in the target account and **appending** the result to `compatibility-matrix.md` as a second
run-of-record. It is externally blocked on GovCloud account access; if access does not arrive, Phase
8 records the cost of not knowing rather than guessing.

---

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Close the architecture package** - Component-architecture write-up, library
      inventory, cold-start measurement, and the last contract the framework decision was blocking
- [ ] **Phase 2: Orchestration spine behind our own port** - LangGraph adapter, model-call
      idempotency, budget enforcement, LangSmith pinned closed
- [ ] **Phase 3: Harden the checkpoint store** - Row integrity, least privilege, resume provenance
- [ ] **Phase 4: Case evidence in, retrieval through the port** - One synthetic case indexed locally,
      every field name in one PROVISIONAL mapping module
- [ ] **Phase 5: Authority routing selects the policy pack** - Explicit decision per authority,
      including the ones that do not apply
- [ ] **Phase 6: One specialist, validated** - Proposed findings against one criterion, rejected
      before a reviewer sees them if unsupported
- [ ] **Phase 7: Human review gate and ASAP delivery** - The Milestone 2 exit: one command, synthetic
      case to delivered human-approved iReport
- [ ] **Phase 8: Handoff package and the GovCloud gate** - What the program team receives, and what
      Q-01 turns out to cost

## Phase Details

### Phase 1: Close the architecture package
**Goal**: Program leadership can sign off on Milestone 1a, and the framework decision has been
re-read against the one number that could reopen it.
**Depends on**: Nothing (Milestones 1b and 1c are complete)
**Requirements**: ARCH-01, ARCH-02, ARCH-03, ARCH-04, CONT-01, QUAL-01
**Success Criteria** (what must be TRUE):
  1. A reader of the component-architecture write-up can point to where our system ends and the AWS
     ingestion pipeline, ASAP, and the human reviewer begin — and program leadership signs off on
     those boundaries.
  2. Every dependency in the project has a recorded version and a recorded reason it is there.
  3. A cold-start and packaging figure exists under SAM local for all three retained bake-off
     candidates, and ADR-012 has been re-read against it and either stands with the number recorded
     or is superseded.
  4. `SpecialistResult` is published to `schemas/` with contract tests, carrying no aggregate score
     field.
  5. `mypy --strict` is clean across the workspace, and no handoff document claims a quality gate
     that does not hold.
**Plans**: TBD

*Why cold start is here and not in Phase 2:* it can be measured today against the three retained
spikes, before a single analysis node is written against LangGraph. `spikes/test_scorecard.py` fails
the moment a figure is recorded, which forces the recommendation to be re-read rather than left
standing. Measuring it after Phase 2 would mean discovering a framework problem after paying for it.

### Phase 2: Orchestration spine behind our own port
**Goal**: A run can execute, checkpoint, crash, and resume in a different process — through this
project's own orchestration port, with no analysis code aware of LangGraph.
**Depends on**: Phase 1
**Requirements**: ORCH-01, ORCH-02, ORCH-03, ORCH-04, QUAL-02
**Success Criteria** (what must be TRUE):
  1. A run survives a mid-node process kill and resumes in a separate process without re-executing
     completed work.
  2. No file outside the orchestration adapter imports LangGraph, and a test proves it.
  3. A crash mid-fan-out does not re-run an in-flight model call — measured as 0 duplicate paid calls
     over the same 24-trial harness that measured LangGraph at 11/24.
  4. A node that hits a model-call, tool-call, token, or wall-clock ceiling emits
     `INCOMPLETE_DUE_TO_BUDGET` and routes to human review, not to failure.
  5. LangSmith egress is proven closed at every production entry point by a fail-closed test, not
     merely configured closed.
**Plans**: TBD

*Two LangGraph defaults are wrong here and invisible when reading a graph:* `durability` defaults to
`async` rather than `sync`, and checkpoint deserialization defaults to permissive. Both must be set
in code with tests — a reviewer cannot catch them by reading the graph.

### Phase 3: Harden the checkpoint store
**Goal**: A tampered or replayed checkpoint cannot alter a finding, skip the review gate, or execute
code — and if one is tried, it is detectable.
**Depends on**: Phase 2
**Requirements**: CKPT-01, CKPT-02, CKPT-03
**Success Criteria** (what must be TRUE):
  1. A checkpoint row modified outside the application fails to load, loudly.
  2. The role that writes checkpoints cannot read or alter findings, dispositions, or run state, and
     is distinct from the migration role.
  3. For any resumed run, an audit can reconstruct which checkpoint id it resumed from, out of the
     run manifest.
**Plans**: TBD

*Why this is its own phase and comes before analysis work:* the checkpoint is read back and acted
upon by machine, with no human between write and read, so a tampered row has no natural detection
point. Threats T1 (code execution on load) and T3 (the review gate skipped) turn a data problem into
an execution problem. The controls implemented in the bake-off — plain JSON, strict serializer
construction, never `pickle`, re-validation on load — are the floor, not the ceiling; strict mode
fails *soft*, returning a refused value as a plain `dict` rather than raising, which is why
re-validation is load-bearing rather than belt-and-braces.

### Phase 4: Case evidence in, retrieval through the port
**Goal**: One synthetic case is ingested and retrievable, with every OpenSearch detail contained in a
single module marked PROVISIONAL against Q-02.
**Depends on**: Phase 3
**Requirements**: RETR-01, RETR-02, RETR-03, CONT-02
**Success Criteria** (what must be TRUE):
  1. A synthetic case is ingested locally and its evidence is retrievable by hybrid lexical + kNN
     query with mandatory case, access, and version filters and a bounded K.
  2. No OpenSearch field name, filter, or facet appears anywhere outside one mapping module, and
     that module states in its header that the AWS collection's real schema is unconfirmed (Q-02).
  3. Every vector carries its embedding provenance — model identifier and revision, dimension,
     normalization, input prefix, library version, and source-text hash.
  4. `ChunkRecord` and `PolicyRecord` are published, each explicitly marked provisional against Q-02.
  5. No document, test, or report claims that retrieval quality measured locally predicts retrieval
     quality in AWS.
**Plans**: TBD

*This phase proceeds under an open gate.* See § Gates — Q-02 is contained by ADR-007's one-file rule,
not cleared. Local ingestion, chunking, and embedding are **development only**; in AWS a separate
pipeline owns the collection and iReports is a consumer, not a producer.

### Phase 5: Authority routing selects the policy pack
**Goal**: A case is routed to the correct legal authorities, with the routing visible and defensible
— including the authorities that were considered and declined.
**Depends on**: Phase 4
**Requirements**: ROUT-01, ROUT-02
**Success Criteria** (what must be TRUE):
  1. A synthetic case produces an `AuthorityRoutingResult` with an explicit decision for **every**
     authority — a reviewer can see that SEAD-4 was considered and declined, and on what basis.
  2. A case with missing routing metadata produces `BLOCKED_MISSING_METADATA` with a required
     `blocking_gap`, never an inferred route.
  3. Two approved policy packs — 5 CFR 731 factors and SEAD-4 guidelines — are selectable by routing.
  4. A policy pack that is unapproved or outside its effective dates stops the run rather than
     degrading it.
**Plans**: TBD

*Why routing is its own phase:* federal personnel-vetting terms are related but not interchangeable.
The same conduct can be relevant under multiple authorities while the legal basis, covered
population, decision standard, available action, timing, and procedural protections all differ.
Collapsing them produces analysis that is wrong in a way that is hard to detect. An absent route is
indistinguishable from an oversight, which is why every authority gets an explicit decision.

### Phase 6: One specialist, validated
**Goal**: A specialist produces proposed findings against one criterion, and nothing unsupported,
determinative, or empty reaches a reviewer.
**Depends on**: Phase 5
**Requirements**: SPEC-01, VAL-01, VAL-02
**Success Criteria** (what must be TRUE):
  1. A specialist sub-agent query against one criterion returns a typed `SpecialistResult`, obtained
     through the gateway port on a tier alias, with a criterion-specific tool allowlist and every
     prohibited tool unreachable.
  2. A proposed finding asserting something about the record without a resolvable evidence span is
     rejected before a reviewer sees it; so is a policy-relevance claim without a resolvable policy
     citation, an expired policy pack, and determinative phrasing.
  3. A model refusal reaches the reviewer as an `InformationGap` with `blocking=True`, never as an
     absent finding or an empty result.
  4. A `StructuredOutputError` reaches the reviewer the same way, never as a prose finding.
**Plans**: TBD

*The failure this phase exists to prevent:* silent under-analysis that looks like a completed
analysis is the worst outcome this system can produce — worse than a crash, because a crash is
visible. Models decline with HTTP 200 and a possibly-empty content list; read naively, a refused
specialist returns `""`, which validates, yields no finding, and reaches a reviewer as a clean
result. Refusals are expected in normal operation — adjudicative case files routinely discuss
criminal conduct, substance use, and foreign contacts.

### Phase 7: Human review gate and ASAP delivery
**Goal**: The Milestone 2 exit — one command takes a synthetic case to a delivered, human-approved
iReport, with every seam exercised once.
**Depends on**: Phase 6
**Requirements**: REV-01, REV-02, DEL-01, DEL-02
**Success Criteria** (what must be TRUE):
  1. A run pauses in an explicit review state; a disposition is recorded by a **different process**
     than the one that proposed the finding; the run resumes from the checkpoint.
  2. No path in the state machine reaches delivery without a recorded human disposition — proven by
     walking the transition table — and no bypass exists in any profile, including local development.
  3. Both the immutable machine proposal and the human-approved version are retained and separately
     readable.
  4. Delivery to the ASAP mock goes through the transactional outbox with an idempotency key; a
     replayed delivery does not double-deliver; a `DeliveryReceipt` is recorded.
  5. One command takes a synthetic case end to end — ingest, routing, specialist, validation, review
     gate, outbox, receipt — and produces a delivered, human-approved iReport.
**Plans**: TBD

*No dev-mode auto-approve flag may be added to make this convenient.* That affordance is exactly the
one that survives into production, which is why ADR-011 makes the gate a state transition rather than
a configuration option.

### Phase 8: Handoff package and the GovCloud gate
**Goal**: The ASAP program team receives something they can act on, and Q-01 is either closed or its
cost is recorded rather than guessed.
**Depends on**: Phase 7
**Requirements**: HAND-01, HAND-02, HAND-03
**Success Criteria** (what must be TRUE):
  1. Decisions, open questions, contracts and schemas, deployment and packaging notes, and **known
     failure modes and things that did not work** are current as of the Milestone 2 exit, with every
     claim cited or carrying an explicit evidence tag.
  2. The live smoke check has been run in the target GovCloud account and region, and the result is
     **appended** to `compatibility-matrix.md` as a second run-of-record beside the commercial one —
     or, if account access did not arrive, the gate's remaining cost is stated plainly and Q-01 stays
     open.
  3. The `bedrock` adapter has been exercised against a real endpoint at least once, so the green
     test suite is no longer being read as connectivity.
**Plans**: TBD

*Q-01 refuses a working assumption and this phase does not supply one.* A commercial-partition result
is not evidence about GovCloud: a model that answers here may be absent there, an endpoint that
resolves here may not exist there, and a request shape accepted here may be rejected there.

---

## Milestone 3 — Optimize (placeholder, **not decomposed**)

**Gated on Milestone 2 measurements. No phases. No exit criteria.**

`docs/ROADMAP.md` gives Milestone 3 a goal — "widen and deepen against measurements from M2, in the
order the evidence justifies" — an unordered candidate list, and one instruction: **"Sequence this
from M2 findings — not from this list."** It states no exit criteria, unlike Milestones 1 and 2 which
both carry them verbatim.

Decomposing that list into phases would invent scope and ordering the source deliberately withheld.
The candidates are recorded in `.planning/REQUIREMENTS.md` § v2 as M3-a through M3-f, unordered.

**To open Milestone 3:** complete Phase 7, read the M2 measurements, and run a fresh roadmapping pass
that sequences from those measurements. Do not linearize the candidate list.

---

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Close the architecture package | 0/TBD | Not started | - |
| 2. Orchestration spine behind our own port | 0/TBD | Not started | - |
| 3. Harden the checkpoint store | 0/TBD | Not started | - |
| 4. Case evidence in, retrieval through the port | 0/TBD | Not started | - |
| 5. Authority routing selects the policy pack | 0/TBD | Not started | - |
| 6. One specialist, validated | 0/TBD | Not started | - |
| 7. Human review gate and ASAP delivery | 0/TBD | Not started | - |
| 8. Handoff package and the GovCloud gate | 0/TBD | Not started | - |

**Milestone mapping:** Phase 1 closes Milestone 1a. Phases 2–7 deliver Milestone 2 (Phase 7 is its
verbatim exit). Phase 8 is the Continuous handoff obligation brought to a checkpoint. Milestone 3 is
a placeholder above.

---

## Prior work (complete, not re-planned as phases)

Recorded here so a cold session does not re-derive it.

| Milestone | Status | Artifact |
|---|---|---|
| 1a · Data contracts | Complete 2026-08-10 | 13 Pydantic v2 contracts in `packages/domain/`, `schemas/`, `docs/handoff/contracts.md` |
| 1a · Model gateway | Complete 2026-08-10 | `packages/gateway/`, `docs/handoff/model-gateway.md`, `docs/handoff/compatibility-matrix.md` |
| 1a · Remainder | **Outstanding** | → Phase 1 |
| 1b · Orchestration landscape scan | Complete 2026-08-10 | `docs/handoff/orchestration-landscape.md` |
| 1c · Orchestration bake-off | Complete 2026-08-11 | ADR-012 Accepted (LangGraph); `spikes/`, `docs/handoff/orchestration-scorecard.md`, `orchestration-scorecard.json`, `docs/handoff/checkpoint-threat-model.md` |

---
*Roadmap created: 2026-08-11 from `.planning/intel/SYNTHESIS.md` (12 source documents, 19 LOCKED
ADRs, 0 ingest blockers).*
