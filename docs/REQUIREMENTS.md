# Requirements — the acceptance bar

**What this file is for:** "done" means something specific, and this is where that lives.
[`ROADMAP.md`](ROADMAP.md) says what to build and in what order; this says how you know a thing is
finished. Two files, no third.

**What it is not:** a plan. The GSD planning machinery that used to wrap this — phases, plan files,
state, progress percentages — was retired on 2026-08-12. It described work in a second vocabulary
that nobody updated, and a stale tracker is worse than none because it reads as current. The
requirement IDs survived the cull because acceptance criteria are genuinely useful; the ceremony
around them was not.

Read the IDs as a checklist, not a contract. If one turns out to be wrong, change it.

**Status is maintained by hand, in the commit that does the work.** That convention is the only
thing keeping this file honest, and it is the same one that failed for the file this replaced —
so if you find a checkbox disagreeing with the code, believe the code and fix the checkbox.

**Where things stand (2026-08-12).** The architecture-package requirements are closed. Of the
orchestrator-spine set, retrieval (RETR-01, RETR-02), the refusal path (VAL-02) and the gateway
port (QUAL-02) are done. ORCH-01 and SPEC-01 moved into `packages/orchestration/` and still are
not checked off — each has one clause left, and both are named in the status lines below rather
than rounded away. Idempotent crash/resume (ORCH-02) and the Lambda timeout proof (LAMB-01) are
the untouched hard ones — and ORCH-02 is what closes the framework question in ADR-024.

---

## v1 Requirements

### Architecture package (Milestone 1a close-out)

- [x] **ARCH-01**: A component-architecture write-up marks the boundaries that matter — what is
      ours, what the AWS ingestion pipeline owns, what ASAP owns, and where the human review gate
      sits — **and separately marks what ADR-020 designed and did not build.**
      *Acceptance:* program leadership can sign off on the component boundaries. Every component is
      BUILT, PLANNED (naming its phase), NOT OURS, or DESIGNED-NOT-BUILT (naming the reason). A test
      fails if a BUILT row does not resolve to a real path or a PLANNED row already exists.
      *Traces:* `REQ-component-architecture` · docs/ROADMAP.md §1a · ADR-020. **This is the last item
      blocking program sign-off on Milestone 1a — highest priority in the project.**
- [x] **ARCH-04**: The repository's entry documents describe the actual current state.
      *Acceptance:* `CLAUDE.md` § Current state and `README.md` § Status no longer assert that
      application code does not exist or that the orchestration framework is undecided, and both
      reflect ADR-020's narrowed scope.
      *Traces:* INGEST-CONFLICTS.md WARNING 1 residue (the stack-table line was fixed 2026-08-11;
      the state narrative was not) · ADR-020.

### Contracts

- [x] **CONT-01**: The `SpecialistResult` contract is defined, published to `schemas/`, and
      documented.
      *Acceptance:* Pydantic v2 model in `packages/domain/`, generated JSON Schema, contract tests,
      `docs/handoff/contracts.md` updated. `extra="forbid"`, `frozen=True`, no aggregate score field.
      *Traces:* `REQ-specialist-result-contract` · contracts.md §5. **Block lifted — it was deferred
      only until ADR-012 resolved.**

### Quality gates

- [x] **QUAL-01** *(done 2026-08-11)*: `mypy --strict` is clean across the workspace.
      *Acceptance:* the 15 pre-existing errors in `tests/contract/` are cleared. A handoff document
      that overstates a quality gate is exactly the failure ADR-001 is written against.
      *Traces:* `REQ-fix-mypy-tests-contract` · model-gateway.md §6.
- [x] **QUAL-02**: The orchestrator runs on the real `ModelGateway` port.
      *Acceptance:* `spikes/harness/gateway.py`'s separate Postgres-backed instrument is replaced by
      or reconciled with `packages/gateway/`; the bake-off's leg-1 model-call log survives the move.
      *Traces:* `REQ-migrate-spike-to-gateway-port` · model-gateway.md §5.
  - *Status:* Done — both orchestrators call the real `ModelGateway` port; only the `stub` adapter is offline

### The orchestrator spine

- [ ] **ORCH-01**: The orchestrator runs on LangGraph **behind this project's own orchestration
      port**, and no analysis node imports LangGraph.
      *Acceptance:* `packages/orchestration/` exposes the port; a test asserts no
      `from langgraph import ...` outside the adapter; `durability="sync"` and strict checkpoint
      deserialization are set in code with tests, because both defaults are wrong here and invisible
      when reading a graph.
      *Traces:* `REQ-orchestrator-on-langgraph` · ADR-012. **Under ADR-020 the port is the sole
      protection against framework lock-in — the second adapter that would have proven it is cut,
      so the no-import test carries that weight alone.**
- [ ] **ORCH-02**: Model-call-level idempotency — a crash mid-fan-out does not re-run an in-flight
      model call.
      *Acceptance:* the duplicate-query detector of blueprint §8.5 exists and the bake-off's crash
      harness measures 0 duplicate paid calls over the same 24 trials that measured LangGraph 11/24
      and hand-rolled 12/24.
      *Traces:* `REQ-model-call-idempotency` · scorecard §4 · blueprint §8.5. **Owed by all three
      bake-off candidates and built by none. The most expensive item ADR-020 retained, retained
      because durable orchestration of paid sub-calls is not proven if resuming double-pays.**
- [ ] **LAMB-01**: A run that exhausts its wall-clock budget inside Lambda checkpoints, returns,
      and resumes in a *new invocation* without re-paying for an in-flight model call.
      *Acceptance:* under SAM local with a wall-clock budget set below the work required, the first
      invocation returns having checkpointed; a second invocation resumes from that checkpoint and
      completes; the duplicate-model-call probe reports **0 duplicate paid calls** across the
      boundary. **This is ORCH-02 under Lambda semantics and cannot be built before it.**
      *Traces:* ADR-023 § consequence 3 · ADR-004 · scorecard §4.
      **Why it matters more here than on a laptop:** Lambda retries automatically, so a timeout
      without idempotency re-pays for every model call on every retry. `spikes/lambda_fit/` proves
      the packaging half; this proves the half that costs money.
- [ ] **ORCH-03**: Budgets and loop limits are enforced by the deterministic shell, not requested of
      the model.
      *Acceptance:* per-specialist ceilings on model calls, tool calls, retrieved evidence, tokens,
      and wall-clock; a no-progress detector; cancellation support. A node that hits a ceiling emits
      `INCOMPLETE_DUE_TO_BUDGET`, which **routes to human review rather than to failure** — a
      truncated analysis must be visible to a reviewer.
      *Traces:* C-deterministic-shell · blueprint §8.5 · contracts.md `Budgets`.
- [ ] **ORCH-04**: LangSmith egress is pinned closed and **proven** closed at every production entry
      point.
      *Acceptance:* `langsmith.configure(enabled=False)` at each entry point, with a fail-closed test
      per entry point of the same shape as `spikes/langgraph/test_langsmith_egress.py`. The negative
      control already showed an unpinned run POSTs ~90 KB of graph state including finding text to
      `api.smith.langchain.com` **and still succeeds**, because the failure is swallowed.
      *Traces:* `REQ-langsmith-egress-deny` · ADR-012: "any future entry point inherits this
      obligation."
  - *Status:* **Address closed 2026-08-12, one clause open.** `packages/orchestration/port.py` exposes the port; both adapters sit behind it; the no-import test scans every module in the package rather than a hand-written list. **What is left is the checkpoint half** — `durability="sync"` and strict deserialization cannot be set until there is a checkpointer, which is ORCH-02. Unchecked on purpose: the acceptance is a conjunction, and rounding it up is how a requirements file starts lying
  - *Status:* **Substantially done 2026-08-18.** `budget.py` enforces run-level wall-clock and token ceilings that **stop the run** — a crossed ceiling skips remaining criteria without a model call, the run reports which ceiling, and `SpecialistStatus.SKIPPED_BUDGET` keeps that distinct from a failure. `BudgetConsumption` is recorded. Fan-out width, bounded retry and bounded K were already enforced. **Two clauses remain:** no no-progress detector, and no cancellation — both belong with the multi-step specialist (item 6), which is the first node that can loop. `INCOMPLETE_DUE_TO_BUDGET` routes to packaging, not review: ADR-022 removed the in-run review gate, and the requirement's original wording predates it
  - *Status:* **Proven for the bake-off** (`spikes/langgraph/test_langsmith_egress.py`), never re-proven at the demo's entry points

### Specialist sub-calls

- [ ] **SPEC-01**: A specialist sub-call produces proposed findings against one criterion, and the
      orchestrator fans out over criteria.
      *Acceptance:* the specialist runs through the `ModelGateway` port on a tier **alias**, with a
      criterion-specific tool allowlist; prohibited tools (shell, generic HTTP, unrestricted
      filesystem, generic SQL, arbitrary Python, cross-case vector search, email, direct ASAP
      delivery) are unreachable; the result is a typed `SpecialistResult`, not prose. ~~**Evidence is
      handed in from a synthetic fixture, not retrieved** — RETR-01..03 are cut by ADR-020.~~
      **Stale: ADR-021 restored retrieval, and specialists now retrieve their own evidence.**
      *Traces:* `REQ-specialist-query` · blueprint §8.3, §8.4 · ADR-020, ADR-021.
  - *Status:* **Address closed 2026-08-12, one clause vacuous.** `packages/orchestration/specialist.py` runs through the `ModelGateway` port on a tier alias and returns the published `SpecialistResult`. **The tool-allowlist clause is not satisfied — it is empty.** A specialist has no tool surface at all: it is handed a `Retriever` and calls a gateway, so there is nothing to allowlist and nothing to prohibit. Every prohibited capability on that list is unreachable by construction rather than by policy, which is a stronger guarantee and a different one. When a specialist gains a tool, this clause becomes real and this requirement is not done until it is enforced
- [x] **VAL-02** *(reduced by ADR-021)*: A model refusal and a `StructuredOutputError` are **logged**,
      never swallowed into an empty result.
      *Acceptance:* the node catches `ModelRefusalError` / `StructuredOutputError` from the gateway
      and logs it with `run_id`, `case_id`, and the criterion. **No `InformationGap` plumbing, no
      `blocking` flag, no review routing** — the orchestrator does nothing special. The gateway
      already checks `stop_reason` before touching content, so a refusal cannot become `""`.
      *Traces:* `REQ-refusal-to-information-gap` (reduced) · ADR-018 · ADR-021 · model-gateway.md §3.
      **Known gap, deliberately accepted:** an empty findings list from a refusal is indistinguishable
      at the artifact level from a criterion that came back clean. The distinction lives in the log.
      Owed a designed-not-built entry under HAND-01.
  - *Status:* Done 2026-08-12 — the node catches, logs `run_id`/`case_id`/criterion, and the run continues. Until then a single refusal killed the entire run
  - *Status:* **Substance done, wrong type.** Typed per-criterion findings, but via a local `SpecialistOutcome` rather than the published `SpecialistResult` contract

### Retrieval — PROVISIONAL under Q-02, restored by ADR-021

- [x] **RETR-01**: Retrieval goes through the port, and every OpenSearch field name, filter, and
      facet mapping lives in **one module**, explicitly marked PROVISIONAL.
      *Acceptance:* no raw OpenSearch client outside the adapter; a test asserts every field name
      resolves through the mapping module; the module carries a header naming Q-02 and stating that
      the AWS collection's real schema is unconfirmed.
      *Traces:* C-retrieval-through-the-port · ADR-007 · ADR-021 · Q-02. **Q-02 is contained by the
      one-file rule, NOT cleared.**
- [x] **RETR-02**: One synthetic case is ingested locally and indexed into local OpenSearch, and the
      sub-agent retrieves against it.
      *Acceptance:* a synthetic case is indexed and retrievable by vector + lexical query with a
      mandatory case filter and bounded K. **Vector and lexical only — ADR-006, no graph database, in
      any milestone.** Local ingestion, chunking, and embedding are development only (ADR-007).
      *Traces:* `REQ-synthetic-case-ingest` · ADR-006 · ADR-007 · ADR-021.
  - *Status:* Done 2026-08-12 — `packages/retrieval/`, hybrid vector + lexical, mandatory case filter, bounded K; a test asserts no field name is written outside `mapping.py`
  - *Status:* Done 2026-08-12 — `index.py` + `spikes/lambda_demo/index_cases.py`; records the embedding model per document, which is what makes a two-model corpus detectable (Q-03)

### Validation and typed output

*Renamed from "Human review and typed output". REV-01 and REV-02 are **withdrawn** by ADR-022 —
see § Withdrawn below. They are not cut and not deferred: they specified an in-run review gate for
a system that has no human interaction at all, so there is nothing to defer.*

- [ ] **DEL-02**: One command takes a synthetic case to a validated typed envelope of proposals.
      *Acceptance:* load → fan-out → budgets → validation → packaging → validated `ASAPEnvelope`
      written to disk, in one invocation, **with no human step anywhere in it**. The envelope is
      pinned `machine_generated` and carries no field claiming review. **The envelope contract is
      validated; the transactional outbox and ASAP mock (DEL-01) are cut by ADR-020.**
      *Traces:* docs/ROADMAP.md §Milestone 2 Exit (narrowed) · ADR-010 (contract stands, transport
      does not ship) · ADR-022.
- [ ] **VAL-05**: A run's output can be scored without ground truth, offline, and repeatably.
      *Acceptance:* a scorer reads a saved run file and reports invariants that must hold for any
      correct run — citations resolving to what the specialist was shown, no determinative
      language in the shipped envelope, no aggregate under any field name, every criterion
      accounted for, rejection volume bounded, and **at least one corpus-level check that a single
      run cannot make about itself**. Each check names the incident it descends from, and each has
      a negative control proving it can fire.
      *Traces:* added 2026-08-17 after a hard-coded classification survived every existing test.
  - *Status:* **Done.** `evals/scorers/properties.py`, nine checks, scored over saved runs by
    `uv run python -m evals.score_run`. Necessary and not sufficient: a green board says the run
    is well-formed and internally honest, not that the analysis is right. That needs VAL-03/04

- [ ] **VAL-03**: Synthetic cases carry the issues a human analyst identified, as ground truth.
      *Acceptance:* at least one synthetic case in `cases/synthetic/` has an `expected/` record
      naming the issues a human found, each tied to the criterion and the evidence span that
      supports it, in a form a scorer can read. **Synthetic only — no real case data, ever.**
      *Traces:* ADR-022 § consequence 1 · blueprint §12.9 (human-factors evaluation).
- [ ] **VAL-04**: Agreement between machine-found and analyst-found issues is measured, not asserted.
      *Acceptance:* a scorer compares the `ProposedFinding`s a run emits against the VAL-03 ground
      truth and reports, per criterion, what both found, what only the machine found, and **what
      only the human found** — the last being the number that matters most, since a missed issue is
      the failure mode a demo hides. The figure is recorded with the run's `model_alias` and prompt
      version, because it is meaningless without them.
      *Traces:* ADR-022 § consequence 1.
      **This is what "human validation" means in this project** — an evaluation against test data,
      not a step in a production run.

### Withdrawn by ADR-022

*Distinct from § v2 § Cut by ADR-020. Those requirements were correctly specified and deliberately
deferred, and each is owed a designed-not-built entry in the handoff. These two were **wrong**:
they described a review gate inside a run, and iReports has no human interaction. Nothing is owed
for them beyond this record of why they are gone.*

- ~~**REV-01**~~: The run pauses in an explicit review state, an authorized reviewer records a
  disposition out of band, and the run resumes. **Withdrawn 2026-08-11.** Review happens in ASAP,
  after the run has finished; there is no pause to survive a process boundary.
- ~~**REV-02**~~: No path reaches output without a recorded human disposition. **Withdrawn
  2026-08-11.** The property is real but it is now ASAP's to enforce, not ours. What replaced it
  on our side is narrower and honest: no contract models a human decision, no run state waits for
  a person, and every envelope is pinned `machine_generated` — all asserted in
  `tests/contract/test_decision_support_boundary.py`.
  **Note what this costs.** ADR-011 let us prove, by walking a transition table, that a rejected
  finding could not reach ASAP. We can no longer make that claim, and the handoff must say so
  rather than let a reader assume it still holds.

### Handoff package

- [ ] **HAND-01**: The handoff package is current, and states plainly what was not built.
      *Acceptance:* `docs/DECISIONS.md`, `docs/OPEN-QUESTIONS.md`, the scorecard, contracts and
      schemas, **a designed-not-built section covering every ADR-020 cut with its reason**, and —
      described in the source as the most useful and most commonly omitted artifact — **known failure
      modes and things we tried that did not work**. Every claim cited or explicitly marked with an
      evidence tag. `docs/ROADMAP.md` is reconciled with ADR-020 or explicitly retired.
      *Traces:* docs/ROADMAP.md §Continuous · ADR-001 · ADR-020 consequence 4. **This is where
      ADR-020 is paid for: a narrower build is only defensible if the package is honest about the
      narrowing.**

---

## v2 Requirements

Tracked, not in the current roadmap.

### Cut by ADR-020 — designed, not built

Acceptance criteria are preserved verbatim in intent so that a future milestone can pick any of these
up without re-deriving it. **Each one is owed a designed-not-built entry in the handoff under
HAND-01.**

| ID | What it was | Why cut |
|---|---|---|
| **ORCH-05** | A second, hand-rolled adapter behind the same port, with one conformance suite over both | The port plus ORCH-01's no-import test is the lock-in protection; a parallel implementation doubles every downstream phase |
| **BAKE-01** | Outcome-level scorecard comparing both adapters over the full seam-walk | Needs two adapters; ADR-012 stands as decided |
| ~~**ARCH-03**~~ | ~~Cold start and packaging measured under SAM local~~ | **CLOSED 2026-08-11 by ADR-023, not by the cut.** Measured in `spikes/lambda_fit/`: hand-rolled 0.478s, LangGraph 1.565s (3.27x), Strands 1.459s; packages 9.1/19/34 MB zipped. ADR-012 stands. The tripwire test now guards the conclusion instead of the absence |
| **ARCH-05** | ADR-012's supersession criteria pre-registered before the build | Existed only to stop a bake-off from choosing its own rubric |
| **ARCH-02** | Library and framework inventory with versions and rationale | Dependency set is small and stable under the spine |
| **CKPT-01** | Keyed MAC over serialized checkpoint state, verified on load | **The single largest recorded security gap** (threat-model §6). Converts T2 and T3 from difficult to detectable |
| **CKPT-02** | Least-privilege checkpoint-write DB role, distinct from the migration role | Hardening of a store the spine exercises unhardened |
| **CKPT-03** | Resume provenance — the checkpoint id a resumed run resumed from, in the run manifest | Described in the source as "cheap to add; not added" — still true |
| ~~**RETR-01**~~ | ~~Retrieval through the port~~ | **RESTORED to v1 by ADR-021** — the sub-agent's RAG search is what the sub-agent *is*; a fixture-fed specialist demonstrates a fan-out, not this system |
| ~~**RETR-02**~~ | ~~One synthetic case in local OpenSearch~~ | **RESTORED to v1 by ADR-021** |
| **RETR-03** | Per-vector embedding provenance and a parity check that fails loudly on drift | Model-evaluation work; stays cut under ADR-021. **Q-03's blast radius is unchanged for whoever builds this** |
| **CONT-02** | `ChunkRecord` and `PolicyRecord`, PROVISIONAL under Q-02 | The indexed record shape lives inside the retrieval package rather than as a published contract — publishing it would commit a schema against an unconfirmed collection for no consumer outside retrieval (ADR-021) |
| **ROUT-01** | Authority routing with an explicit decision for **every** authority, never inferred | Breadth across authorities, not orchestrator risk. ADR-003's coverage decision is unchanged; its implementation is deferred |
| **ROUT-02** | Two approved policy packs (5 CFR 731, SEAD-4), policy fails closed | As above |
| **VAL-01** | Deterministic validators rejecting a finding on schema, unresolvable citation, effectivity, or prohibited content | Resolving citations needs a real evidence snapshot to mean anything. **The finding contract still requires citations structurally** |
| **DEL-01** | Transactional outbox with idempotency key, ASAP mock, `DeliveryReceipt` | Envelope contract stands and is validated; transport does not ship |
| **HAND-02** | Q-01 closed by re-running the live smoke check in GovCloud | Externally blocked on account access regardless. **Q-01 stays open and its cost is stated** |
| **HAND-03** | The `bedrock` adapter exercised against a real endpoint | Today it is verified as correctly constructed and nothing more — **do not read the green test suite as connectivity** |

### Milestone 3 — Optimize (**placeholder, deliberately not sequenced**)

`docs/ROADMAP.md` states no exit criteria for Milestone 3 and instructs: *"Sequence this from
findings — not from this list."* Under ADR-020 the candidate pool is the list above **plus** the
originals below. Recorded **unordered and unscoped**.

- **M3-a**: The full specialist set across both authority families (blueprint §8.3)
- **M3-b**: Retrieval quality work — hybrid fusion, query planning, reranking
- **M3-c**: The contradiction and challenge stages
- **M3-d**: Multi-criterion fan-out beyond the spine's demonstration
- **M3-e**: Model-tier tuning across the three aliases (including whether the thinking tier escalates
  to an Opus-class model — on measured finding quality, not by default)
- **M3-f**: The evaluation harness and red-team scenarios

### Deferred, blocked on an open question

- **CKPT-04**: Checkpoint encryption at rest and backup handling — assumed platform-provided,
  `[unverified]`. *Blocked on:* Q-01.
- **CKPT-05**: Checkpoint retention and pruning policy for state carrying case-derived text — 37,033 B
  retained per run and growing. *Blocked on:* Q-09 (records retention).
- **CONT-03**: `EntityCandidate` and `TimelineEvent` contracts. *Blocked on:* Q-02, and no consumer.
- **GW-01**: Revisit `MAX_EXCERPT_CHARS = 2000`, an unresearched starting value, against real ASAP
  payload limits. *Blocked on:* Q-04.
- **GW-02**: Prompt caching. *Blocked on:* Q-13 — material to cost, immaterial to correctness.

### Deferred, unblocked but not yet needed

- **GW-03**: Retry and fallback policy. Server-side `fallbacks` is unavailable on Bedrock.
- **GW-04**: Streaming run status. The port is synchronous today and the change is additive.
- **PIV-01**: PIV/HSPD-12 credentialing analysis — ADR-003 places it outside the first release while
  requiring that it not be structurally excluded.

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Any final adjudicative determination | The decision-support boundary. NON-NEGOTIABLE. |
| Universal person-risk score / aggregate risk level / overall recommendation field | ADR-014. **Considered for ADR-020's cut and explicitly retained** — already structural in the shipped contracts with a passing test, so keeping it costs nothing. |
| Cross-case personality profiling, generalized predictive scoring | blueprint §1.3 |
| Real case data in fixtures, tests, or examples | Synthetic only, ever. `DataClassification` has one member. |
| Neo4j or any graph database | ADR-006 |
| Streamlit or any UI | ADR-005 — FastAPI, JSON, and contract tests are the interface |
| Offline run profile, recorded-fixture provider, local LLM server | ADR-009 — Bedrock access is required; tests mock at the gateway boundary |
| LocalStack in the default profile | CLAUDE.md |
| Shared code or infrastructure with `amilens-localdev` | ADR-002 — prior art, not a dependency |
| Batch queue | ADR-013 — single-case interactive |
| Bedrock AgentCore as a deployment target | Q-14 working assumption is no; ADR-004 stands |
| Investigative data collection, web browsing, autonomous contact with subjects | blueprint §1.3 |
| Sampling parameters (`temperature`, `top_p`, `top_k`) | ADR-015 — reasoning depth is `effort` per tier |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 1 | Complete |
| ARCH-04 | Phase 1 | Complete |
| CONT-01 | Phase 1 | Complete |
| QUAL-01 | — | Done (2026-08-11) |
| ORCH-01 | Phase 2 | Pending |
| ORCH-02 | Phase 2 | Pending |
| LAMB-01 | Phase 2 | Pending |
| ORCH-03 | Phase 2 | Substantially done (2026-08-18) |
| ORCH-04 | Phase 2 | Pending |
| SPEC-01 | Phase 2 | Pending |
| VAL-02 | Phase 2 | Pending (reduced to logging, ADR-021) |
| RETR-01 | Phase 2 | Pending (restored, ADR-021) |
| RETR-02 | Phase 2 | Pending (restored, ADR-021) |
| QUAL-02 | Phase 2 | Pending |
| REV-01 | — | **Withdrawn (ADR-022)** |
| REV-02 | — | **Withdrawn (ADR-022)** |
| DEL-02 | Phase 3 | Pending |
| VAL-05 | — | Done (2026-08-17) |
| VAL-03 | Phase 3 | Pending |
| VAL-04 | Phase 3 | Pending |
| HAND-01 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 17 total (16 active, 1 done)
- Mapped to phases: 16
- Unmapped: 0 ✓
- Cut to v2 by ADR-020, net of ADR-021's restorations: 16, each owed a designed-not-built entry
  under HAND-01

---
*Requirements defined: 2026-08-11*
*Updated 2026-08-11 — port-first dual-adapter bake-off. Added ARCH-05, ORCH-05, BAKE-01.*
*Updated 2026-08-11 — **ADR-020: pared to the orchestrator spine. 33 v1 requirements → 15.** Nothing
was deleted; 18 requirements moved to v2 § Cut by ADR-020 with their acceptance intact and are owed
a designed-not-built entry in the handoff. No acceptance criterion on a retained requirement was
weakened. ADR-011 (REV-01/02) and ADR-014 were considered for the cut and explicitly kept.*
