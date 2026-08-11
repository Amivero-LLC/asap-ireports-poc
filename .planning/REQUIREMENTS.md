# Requirements: asap-ireports

**Defined:** 2026-08-11
**Core Value:** One command takes a synthetic case to a delivered, human-approved iReport, with
every seam exercised once and every handoff claim either cited or explicitly marked unverified.

**Source:** derived from `.planning/intel/requirements.md` (extracted from `docs/ROADMAP.md`) plus
the outstanding work items recorded in `docs/handoff/*`. Every requirement below traces to a source
document. The `REQ-{slug}` handles in the intel are carried in the *Traces* line of each requirement
so the mapping back to the source is not lost.

**Scope of v1:** close Milestone 1a, then deliver Milestone 2. Milestone 3 is deliberately not
decomposed — see v2.

---

## v1 Requirements

### Architecture package (Milestone 1a close-out)

- [ ] **ARCH-01**: A component-architecture write-up marks the boundaries that matter — what is
      ours, what the AWS ingestion pipeline owns, what ASAP owns, and where the human review gate
      sits.
      *Acceptance:* program leadership can sign off on the component boundaries.
      *Traces:* `REQ-component-architecture` · docs/ROADMAP.md §1a. **This is the last item blocking
      program sign-off on Milestone 1a — highest priority in the project.**
- [ ] **ARCH-02**: The library and framework inventory covers the non-orchestration layers, with
      versions and the reason each dependency is there.
      *Acceptance:* every dependency has a recorded version and rationale. The orchestration layer is
      already covered by the 1b scan's footprint and version tables.
      *Traces:* `REQ-library-inventory` · docs/ROADMAP.md §1a (partly covered).
- [ ] **ARCH-03**: Cold start and packaging under SAM local are measured for all three retained
      bake-off candidates, the figure is recorded, and ADR-012 is re-read against it.
      *Acceptance:* a number exists per candidate; `spikes/test_scorecard.py` (which fails the moment
      a figure is recorded) is updated; ADR-012 either stands with the number recorded or is
      superseded.
      *Traces:* `REQ-cold-start-measurement` · docs/ROADMAP.md §1c, scorecard §2. **The one number
      most likely to reopen the framework choice — measured before nodes are written against it.**
- [ ] **ARCH-04**: The repository's entry documents describe the actual current state.
      *Acceptance:* `CLAUDE.md` § Current state and `README.md` § Status no longer assert that
      application code does not exist or that the orchestration framework is undecided.
      *Traces:* INGEST-CONFLICTS.md WARNING 1 residue (the stack-table line was fixed 2026-08-11;
      the state narrative was not).

### Contracts

- [ ] **CONT-01**: The `SpecialistResult` contract is defined, published to `schemas/`, and
      documented.
      *Acceptance:* Pydantic v2 model in `packages/domain/`, generated JSON Schema, contract tests,
      `docs/handoff/contracts.md` updated. `extra="forbid"`, `frozen=True`, no aggregate score field.
      *Traces:* `REQ-specialist-result-contract` · contracts.md §5. **Block lifted — it was deferred
      only until ADR-012 resolved.**
- [ ] **CONT-02**: `ChunkRecord` and `PolicyRecord` are defined **PROVISIONALLY** under Q-02's
      working assumption.
      *Acceptance:* both contracts published, each carrying an explicit provisional marker naming
      Q-02, so a reader cannot mistake them for confirmed against the real AWS collection.
      *Traces:* `REQ-deferred-contracts` (partial) · contracts.md §5. **Derived split:**
      `EntityCandidate` and `TimelineEvent` have no Milestone 2 consumer and stay deferred to v2.

### Quality gates

- [ ] **QUAL-01**: `mypy --strict` is clean across the workspace.
      *Acceptance:* the 15 pre-existing errors in `tests/contract/` are cleared; no package under
      `packages/` or `spikes/` is affected. A handoff document that overstates a quality gate is
      exactly the failure ADR-001 is written against.
      *Traces:* `REQ-fix-mypy-tests-contract` · model-gateway.md §6 (recorded as 13 at the time of
      writing; 15 as measured 2026-08-11).
- [ ] **QUAL-02**: The orchestration spike runs on the real `ModelGateway` port.
      *Acceptance:* `spikes/harness/gateway.py`'s separate Postgres-backed instrument is replaced by
      or reconciled with `packages/gateway/`; the bake-off's leg-1 model-call log survives the move.
      *Traces:* `REQ-migrate-spike-to-gateway-port` · model-gateway.md §5.

### Orchestration

- [ ] **ORCH-01**: The orchestrator runs on LangGraph **behind this project's own orchestration
      port**, and no analysis node imports LangGraph.
      *Acceptance:* `packages/orchestration/` exposes the port; a test asserts no
      `from langgraph import ...` outside the adapter; `durability="sync"` and strict checkpoint
      deserialization are set in code with tests, because both defaults are wrong here and invisible
      when reading a graph.
      *Traces:* `REQ-orchestrator-on-langgraph` · ADR-012, docs/ROADMAP.md §M2. ADR-012 calls this
      Milestone 2's first obligation.
- [ ] **ORCH-02**: Model-call-level idempotency — a crash mid-fan-out does not re-run an in-flight
      model call.
      *Acceptance:* the duplicate-query detector of blueprint §8.5 exists and the bake-off's crash
      harness measures 0 duplicate paid calls over the same 24 trials that measured LangGraph 11/24
      and hand-rolled 12/24.
      *Traces:* `REQ-model-call-idempotency` · docs/ROADMAP.md §M2, scorecard §4, blueprint §8.5.
      **Owed by all three bake-off candidates and built by none.**
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
      *Traces:* `REQ-langsmith-egress-deny` (carried obligation) · ADR-012: "any future entry point
      inherits this obligation."

### Checkpoint hardening

- [ ] **CKPT-01**: A keyed MAC over serialized checkpoint state, with the key unreadable by the DB
      role, verified on load.
      *Acceptance:* a tampered checkpoint row fails to load and the failure is loud. Converts threats
      T2 (findings altered before review) and T3 (review gate skipped) from difficult to detectable.
      *Traces:* `REQ-checkpoint-row-integrity` · checkpoint-threat-model.md §6. **The single largest
      security gap recorded in the threat model.**
- [ ] **CKPT-02**: A separate least-privilege checkpoint-write DB role, distinct from everything else
      and from the migration role.
      *Acceptance:* the application's checkpoint role cannot read or alter findings, dispositions, or
      run state; a test asserts the grant set.
      *Traces:* `REQ-checkpoint-least-privilege` · checkpoint-threat-model.md §6.
- [ ] **CKPT-03**: Resume provenance — the checkpoint id a resumed run resumed from is recorded in
      the run manifest.
      *Acceptance:* an audit can reconstruct the resume chain for any run. Described in the source as
      "cheap to add; not added."
      *Traces:* `REQ-checkpoint-provenance-on-load` · checkpoint-threat-model.md §6.

### Retrieval and case evidence — PROVISIONAL under Q-02

- [ ] **RETR-01**: Retrieval goes through the port, and every OpenSearch field name, filter, and
      facet mapping lives in **one module**, explicitly marked PROVISIONAL.
      *Acceptance:* no raw OpenSearch client outside the adapter; a test asserts every field name
      resolves through the mapping module; the module carries a header naming Q-02 and stating that
      the AWS collection's real schema is unconfirmed.
      *Traces:* C-retrieval-through-the-port · ADR-007 · Q-02. **See ROADMAP § Gates — Q-02 is
      contained, not cleared.**
- [ ] **RETR-02**: One synthetic case is ingested locally and indexed into local OpenSearch, mirroring
      the assumed collection shape.
      *Acceptance:* a case from the blueprint §11 designs (starting with `AMI-SYN-SUIT-001`) is
      ingested and retrievable with mandatory case/access/version filters and bounded K. Local
      ingestion, chunking, and embedding are development only (ADR-007).
      *Traces:* `REQ-synthetic-case-ingest` · docs/ROADMAP.md §M2.
- [ ] **RETR-03**: Every vector records its embedding provenance, and no locally-measured retrieval
      quality is presented as predictive of AWS behaviour.
      *Acceptance:* model identifier and revision, dimension, normalization, input prefix, library
      version, and source-text hash recorded per vector; the embedding provider sits behind an
      interface; a parity check fails loudly on drift; the handoff records Q-03 as open and the
      coupling as unverified.
      *Traces:* ADR-007 consequences 1 and 3 · Q-03 (**high blast radius and silent — a mismatch does
      not error, it retrieves worse**).

### Authority routing and policy

- [ ] **ROUT-01**: Authority routing selects the policy pack, with an explicit recorded decision for
      **every** authority, including those that do not apply.
      *Acceptance:* `AuthorityRoutingResult` produced for a synthetic case showing that, e.g., SEAD-4
      was considered and declined and on what basis. `RoutingBasis` has no `INFERRED` member; missing
      metadata produces `BLOCKED_MISSING_METADATA` with a required `blocking_gap`, never a guess.
      *Traces:* `REQ-authority-routing-engine`, `REQ-authority-routing-model` · ADR-003 ·
      C-routing-is-never-inferred · blueprint §2.1.
- [ ] **ROUT-02**: Two approved policy packs exist — 5 CFR 731 factors and SEAD-4 guidelines — and
      policy fails closed.
      *Acceptance:* `PolicyPackRef` refuses to construct unless `status == APPROVED`; effectivity is
      a date comparison in code; an expired or unapproved pack stops the run rather than degrading it.
      *Traces:* ADR-003 (two approved packs at launch) · C-fail-closed-on-policy.

### Specialist analysis and validation

- [ ] **SPEC-01**: A single specialist sub-agent query produces proposed findings against one
      criterion.
      *Acceptance:* the specialist runs through the `ModelGateway` port on a tier **alias**, with a
      criterion-specific tool allowlist; prohibited tools (shell, generic HTTP, unrestricted
      filesystem, generic SQL, arbitrary Python, cross-case vector search, email, direct ASAP
      delivery) are unreachable; the result is a typed `SpecialistResult`, not prose.
      *Traces:* `REQ-specialist-query` · docs/ROADMAP.md §M2 · blueprint §8.3, §8.4.
- [ ] **VAL-01**: Deterministic validators reject a proposed finding on schema, unresolvable
      citation, policy effectivity, or prohibited content **before a reviewer sees it**.
      *Acceptance:* a finding asserting something about the record without a resolvable evidence span
      is rejected; a policy-relevance claim without a resolvable policy citation is rejected; a
      finding carrying determinative phrasing is rejected; an expired policy pack is rejected. Tool
      input is best-effort (`strict: true` is unavailable), so it is re-validated through the
      Pydantic contracts here.
      *Traces:* `REQ-deterministic-validators` · C-evidence-before-inference · C-deterministic-shell.
- [ ] **VAL-02**: A model refusal and a `StructuredOutputError` reach the reviewer as an
      `InformationGap` with `blocking=True`, never as an absent or empty finding.
      *Acceptance:* both paths wired and tested. Silent under-analysis that looks like a completed
      analysis is the worst outcome this system can produce — worse than a crash, because a crash is
      visible. Refusals are expected in normal operation on adjudicative content.
      *Traces:* `REQ-refusal-to-information-gap` · ADR-018 · model-gateway.md §3.

### Human review and delivery

- [ ] **REV-01**: The run pauses in an explicit review state, an authorized reviewer records a
      disposition out of band, and the run resumes.
      *Acceptance:* the pause survives a process boundary — the disposition is recorded by a
      different process than the one that proposed the finding, and the run resumes from the
      checkpoint. End-to-end tests drive the review transition explicitly.
      *Traces:* `REQ-human-review-gate` · ADR-011.
- [ ] **REV-02**: No path reaches delivery without a recorded human disposition, in **any** profile
      including local development, and both versions are retained.
      *Acceptance:* the transition table is walked to prove no path reaches delivery without passing
      the gate; a run in any delivery-side status with `human_review_recorded=False` fails validation;
      `HumanDisposition` references the immutable proposal by id and carries `approved_text` alongside
      it. No dev-mode auto-approve flag exists — that affordance is exactly what survives into
      production.
      *Traces:* ADR-011 · C-human-disposition-gate (NON-NEGOTIABLE).
- [ ] **DEL-01**: Delivery to the ASAP mock goes through the transactional outbox with an idempotency
      key and a recorded receipt.
      *Acceptance:* the mock validates the envelope schema and simulates status codes, timeouts, and
      retries; a replayed delivery does not double-deliver; a `DeliveryReceipt` is recorded. The
      envelope is our proposal, not an agreed interface (Q-04) — contract tests pin our side so the
      delta is measurable.
      *Traces:* `REQ-asap-delivery-outbox` · ADR-010.
- [ ] **DEL-02**: One command takes a synthetic case to a delivered, human-approved iReport, with
      every seam exercised once.
      *Acceptance:* **this is the verbatim Milestone 2 exit criterion.** Ingest → routing →
      specialist → validation → review gate → outbox → mock receipt, in one invocation.
      *Traces:* docs/ROADMAP.md §Milestone 2 Exit.

### Handoff package and the GovCloud gate

- [ ] **HAND-01**: The handoff package is current at the Milestone 2 exit.
      *Acceptance:* `docs/DECISIONS.md`, `docs/OPEN-QUESTIONS.md`, the scorecard, contracts and
      schemas, deployment and packaging notes, and — described in the source as the most useful and
      most commonly omitted artifact — **known failure modes and things we tried that did not work**.
      Every claim cited or explicitly marked with an evidence tag.
      *Traces:* docs/ROADMAP.md §Continuous · ADR-001.
- [ ] **HAND-02**: Q-01 is closed — the live smoke check is re-run in the target GovCloud account and
      region.
      *Acceptance:* the result is **appended to `docs/handoff/compatibility-matrix.md` as a SECOND
      run-of-record, alongside the commercial one rather than replacing it** — the value is the
      comparison between partitions. Covers model availability, concrete model and inference-profile
      ids, cross-region inference restrictions, data-routing rules, whether
      `bedrock-mantle.{region}.api.aws` resolves, and whether a LiteLLM proxy is permitted.
      *Traces:* Q-01 (GATE, refuses any working assumption) · ADR-004 · ADR-015 · ADR-019
      ("a per-endpoint finding — re-run the live smoke check before assuming it transfers").
      **Status: Blocked — requires access to the target GovCloud account.**
- [ ] **HAND-03**: The `bedrock` adapter is exercised against a real endpoint for the first time in
      any partition.
      *Acceptance:* a recorded live run. Today the adapter is verified as correctly constructed and
      nothing more — the green test suite must not be read as connectivity.
      *Traces:* model-gateway.md § Known gaps.

---

## v2 Requirements

Tracked, not in the current roadmap.

### Milestone 3 — Optimize (**placeholder, deliberately not sequenced**)

`docs/ROADMAP.md` states no exit criteria for Milestone 3 and instructs: *"Sequence this from M2
findings — not from this list."* The candidates below are recorded **unordered and unscoped**.
Turning them into phases would manufacture a plan the source refuses to make.

- **M3-a**: The full specialist set across both authority families (blueprint §8.3)
- **M3-b**: Retrieval quality work — hybrid fusion, query planning, reranking
- **M3-c**: The contradiction and challenge stages
- **M3-d**: Multi-criterion fan-out
- **M3-e**: Model-tier tuning across the three aliases (including whether the thinking tier escalates
  to an Opus-class model — on measured finding quality, not by default)
- **M3-f**: The evaluation harness and red-team scenarios

### Deferred, blocked on an open question

- **CKPT-04**: Checkpoint encryption at rest and backup handling — assumed platform-provided,
  `[unverified]`. *Blocked on:* Q-01. *Traces:* `REQ-checkpoint-encryption-at-rest`.
- **CKPT-05**: Checkpoint retention and pruning policy for state carrying case-derived text — 37,033 B
  retained per run and growing. *Blocked on:* Q-09 (records retention).
  *Traces:* `REQ-checkpoint-retention`.
- **CONT-03**: `EntityCandidate` and `TimelineEvent` contracts. *Blocked on:* Q-02, and no Milestone 2
  consumer exists. *Traces:* `REQ-deferred-contracts` (remainder).
- **GW-01**: Revisit `MAX_EXCERPT_CHARS = 2000`, an unresearched starting value, against real ASAP
  payload limits. *Blocked on:* Q-04. *Traces:* `REQ-max-excerpt-chars`.
- **GW-02**: Prompt caching. *Blocked on:* Q-13 — material to cost, immaterial to correctness; not
  enabled pending approval for this data class.

### Deferred, unblocked but not yet needed

- **GW-03**: Retry and fallback policy. Server-side `fallbacks` is unavailable on Bedrock; deferred
  until the orchestrator exists to own bounded retry semantics. *Traces:* `REQ-retry-fallback-policy`.
- **GW-04**: Streaming run status. ADR-013's single-case interactive model wants it eventually; the
  port is synchronous today and the change is additive. *Traces:* `REQ-streaming-run-status`.
- **PIV-01**: PIV/HSPD-12 credentialing analysis — ADR-003 places it outside the first release while
  requiring that it not be structurally excluded.

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Any final adjudicative determination | The decision-support boundary. NON-NEGOTIABLE. |
| Universal person-risk score / aggregate risk level / overall recommendation field | ADR-014. Collapses distinct legal authorities into a number that invites the deference the boundary prohibits. |
| Cross-case personality profiling, generalized predictive scoring | blueprint §1.3 |
| Real case data in fixtures, tests, or examples | Synthetic only, ever. `DataClassification` has one member. |
| Neo4j or any graph database | ADR-006 — until a measurement shows graph traversal improves findings |
| Streamlit or any UI | ADR-005 — FastAPI, JSON, contract tests, and the eval harness are the interface |
| Offline run profile, recorded-fixture provider, local LLM server | ADR-009 — Bedrock access is required; tests mock at the gateway boundary |
| LocalStack in the default profile | CLAUDE.md |
| Shared code or infrastructure with `amilens-localdev` | ADR-002 — prior art, not a dependency |
| Batch queue | ADR-013 — single-case interactive in the first milestone |
| Bedrock AgentCore as a deployment target | Q-14 working assumption is no; ADR-004 stands |
| Investigative data collection, web browsing, autonomous contact with subjects | blueprint §1.3 |
| Sampling parameters (`temperature`, `top_p`, `top_k`) | ADR-015 — reasoning depth is `effort` per tier |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01 | Phase 1 | Pending |
| ARCH-02 | Phase 1 | Pending |
| ARCH-03 | Phase 1 | Pending |
| ARCH-04 | Phase 1 | Pending |
| CONT-01 | Phase 1 | Pending |
| QUAL-01 | Phase 1 | Pending |
| ORCH-01 | Phase 2 | Pending |
| ORCH-02 | Phase 2 | Pending |
| ORCH-03 | Phase 2 | Pending |
| ORCH-04 | Phase 2 | Pending |
| QUAL-02 | Phase 2 | Pending |
| CKPT-01 | Phase 3 | Pending |
| CKPT-02 | Phase 3 | Pending |
| CKPT-03 | Phase 3 | Pending |
| RETR-01 | Phase 4 | Pending |
| RETR-02 | Phase 4 | Pending |
| RETR-03 | Phase 4 | Pending |
| CONT-02 | Phase 4 | Pending |
| ROUT-01 | Phase 5 | Pending |
| ROUT-02 | Phase 5 | Pending |
| SPEC-01 | Phase 6 | Pending |
| VAL-01 | Phase 6 | Pending |
| VAL-02 | Phase 6 | Pending |
| REV-01 | Phase 7 | Pending |
| REV-02 | Phase 7 | Pending |
| DEL-01 | Phase 7 | Pending |
| DEL-02 | Phase 7 | Pending |
| HAND-01 | Phase 8 | Pending |
| HAND-02 | Phase 8 | Blocked (GovCloud account access) |
| HAND-03 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-11*
*Last updated: 2026-08-11 after the `/gsd-new-project` document ingest*
