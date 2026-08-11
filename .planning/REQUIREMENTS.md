# Requirements: asap-ireports

**Defined:** 2026-08-11 · **Pared to the spine:** 2026-08-11 (ADR-020)
**Core Value:** One command takes a synthetic case to a human-approved, validated typed envelope,
with the orchestrator's hard parts exercised and every handoff claim either cited or explicitly
marked unverified.

**Source:** derived from `.planning/intel/requirements.md` (extracted from `docs/ROADMAP.md`) plus
the outstanding work items recorded in `docs/handoff/*`, then narrowed by **ADR-020** to the
orchestrator spine. The `REQ-{slug}` handles from the intel are carried in each *Traces* line so the
mapping back to source is not lost.

**Scope of v1:** close Milestone 1a, then build and prove the orchestrator spine —
bounded specialist sub-calls through the gateway port, deterministic ceilings, crash and resume
without double-paying, a human disposition gate, and a validated typed envelope. Thirteen active
requirements, down from thirty-three.

**What "cut" means here.** Nothing was deleted. Every requirement ADR-020 removed from v1 appears
under § v2 § Cut by ADR-020 with its acceptance criteria intact, and Phase 3 is obliged to record it
in the handoff package as designed-not-built with the reason. A requirement that quietly disappears
is the failure ADR-001 is written against.

---

## v1 Requirements

### Architecture package (Milestone 1a close-out)

- [ ] **ARCH-01**: A component-architecture write-up marks the boundaries that matter — what is
      ours, what the AWS ingestion pipeline owns, what ASAP owns, and where the human review gate
      sits — **and separately marks what ADR-020 designed and did not build.**
      *Acceptance:* program leadership can sign off on the component boundaries. Every component is
      BUILT, PLANNED (naming its phase), NOT OURS, or DESIGNED-NOT-BUILT (naming the reason). A test
      fails if a BUILT row does not resolve to a real path or a PLANNED row already exists.
      *Traces:* `REQ-component-architecture` · docs/ROADMAP.md §1a · ADR-020. **This is the last item
      blocking program sign-off on Milestone 1a — highest priority in the project.**
- [ ] **ARCH-04**: The repository's entry documents describe the actual current state.
      *Acceptance:* `CLAUDE.md` § Current state and `README.md` § Status no longer assert that
      application code does not exist or that the orchestration framework is undecided, and both
      reflect ADR-020's narrowed scope.
      *Traces:* INGEST-CONFLICTS.md WARNING 1 residue (the stack-table line was fixed 2026-08-11;
      the state narrative was not) · ADR-020.

### Contracts

- [ ] **CONT-01**: The `SpecialistResult` contract is defined, published to `schemas/`, and
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
- [ ] **QUAL-02**: The orchestrator runs on the real `ModelGateway` port.
      *Acceptance:* `spikes/harness/gateway.py`'s separate Postgres-backed instrument is replaced by
      or reconciled with `packages/gateway/`; the bake-off's leg-1 model-call log survives the move.
      *Traces:* `REQ-migrate-spike-to-gateway-port` · model-gateway.md §5.

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

### Specialist sub-calls

- [ ] **SPEC-01**: A specialist sub-call produces proposed findings against one criterion, and the
      orchestrator fans out over criteria.
      *Acceptance:* the specialist runs through the `ModelGateway` port on a tier **alias**, with a
      criterion-specific tool allowlist; prohibited tools (shell, generic HTTP, unrestricted
      filesystem, generic SQL, arbitrary Python, cross-case vector search, email, direct ASAP
      delivery) are unreachable; the result is a typed `SpecialistResult`, not prose. **Evidence is
      handed in from a synthetic fixture, not retrieved** — RETR-01..03 are cut by ADR-020.
      *Traces:* `REQ-specialist-query` · blueprint §8.3, §8.4 · ADR-020.
- [ ] **VAL-02**: A model refusal and a `StructuredOutputError` reach the reviewer as an
      `InformationGap` with `blocking=True`, never as an absent or empty finding.
      *Acceptance:* both paths wired and tested. Silent under-analysis that looks like a completed
      analysis is the worst outcome this system can produce — worse than a crash, because a crash is
      visible. Refusals are expected in normal operation on adjudicative content.
      *Traces:* `REQ-refusal-to-information-gap` · ADR-018 · model-gateway.md §3. **Retained by
      ADR-020 as nearly free — the gateway already raises `ModelRefusalError`.**

### Human review and typed output

- [ ] **REV-01**: The run pauses in an explicit review state, an authorized reviewer records a
      disposition out of band, and the run resumes.
      *Acceptance:* the pause survives a process boundary — the disposition is recorded by a
      different process than the one that proposed the finding, and the run resumes from the
      checkpoint. End-to-end tests drive the review transition explicitly.
      *Traces:* `REQ-human-review-gate` · ADR-011. **Explicitly retained by ADR-020; NON-NEGOTIABLE.**
- [ ] **REV-02**: No path reaches output without a recorded human disposition, in **any** profile
      including local development, and both versions are retained.
      *Acceptance:* the transition table is walked to prove no path reaches output without passing
      the gate; a run in any output-side status with `human_review_recorded=False` fails validation;
      `HumanDisposition` references the immutable proposal by id and carries `approved_text` alongside
      it. No dev-mode auto-approve flag exists — that affordance is exactly what survives into
      production.
      *Traces:* ADR-011 · C-human-disposition-gate (**NON-NEGOTIABLE**) · ADR-020 § retained.
- [ ] **DEL-02**: One command takes a synthetic case to a human-approved, validated typed envelope.
      *Acceptance:* load → fan-out → budgets → validation → review gate → validated `ASAPEnvelope`
      written to disk, in one invocation. **The envelope contract is validated; the transactional
      outbox and ASAP mock (DEL-01) are cut by ADR-020.**
      *Traces:* docs/ROADMAP.md §Milestone 2 Exit (narrowed) · ADR-010 (contract stands, transport
      does not ship).

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
| **ARCH-03** | Cold start and packaging measured under SAM local | Was scoped to the bake-off verdict. **Remains unmeasured with no scheduled phase**; `spikes/test_scorecard.py` still fails the moment a figure is recorded, keeping the gap visible |
| **ARCH-05** | ADR-012's supersession criteria pre-registered before the build | Existed only to stop a bake-off from choosing its own rubric |
| **ARCH-02** | Library and framework inventory with versions and rationale | Dependency set is small and stable under the spine |
| **CKPT-01** | Keyed MAC over serialized checkpoint state, verified on load | **The single largest recorded security gap** (threat-model §6). Converts T2 and T3 from difficult to detectable |
| **CKPT-02** | Least-privilege checkpoint-write DB role, distinct from the migration role | Hardening of a store the spine exercises unhardened |
| **CKPT-03** | Resume provenance — the checkpoint id a resumed run resumed from, in the run manifest | Described in the source as "cheap to add; not added" — still true |
| **RETR-01** | Retrieval through the port, all OpenSearch mappings in one PROVISIONAL module | No local retrieval in the spine; ADR-007's one-file rule stands as design guidance |
| **RETR-02** | One synthetic case ingested into local OpenSearch | Evidence is handed to the specialist from a fixture instead |
| **RETR-03** | Per-vector embedding provenance and a parity check that fails loudly on drift | No local embedding. **Q-03's blast radius is unchanged for whoever builds this** |
| **CONT-02** | `ChunkRecord` and `PolicyRecord`, PROVISIONAL under Q-02 | No consumer in the spine |
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
| ARCH-01 | Phase 1 | Pending |
| ARCH-04 | Phase 1 | Pending |
| CONT-01 | Phase 1 | Pending |
| QUAL-01 | — | Done (2026-08-11) |
| ORCH-01 | Phase 2 | Pending |
| ORCH-02 | Phase 2 | Pending |
| ORCH-03 | Phase 2 | Pending |
| ORCH-04 | Phase 2 | Pending |
| SPEC-01 | Phase 2 | Pending |
| VAL-02 | Phase 2 | Pending |
| QUAL-02 | Phase 2 | Pending |
| REV-01 | Phase 3 | Pending |
| REV-02 | Phase 3 | Pending |
| DEL-02 | Phase 3 | Pending |
| HAND-01 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 15 total (14 active, 1 done)
- Mapped to phases: 14
- Unmapped: 0 ✓
- Cut to v2 by ADR-020: 18, each owed a designed-not-built entry under HAND-01

---
*Requirements defined: 2026-08-11*
*Updated 2026-08-11 — port-first dual-adapter bake-off. Added ARCH-05, ORCH-05, BAKE-01.*
*Updated 2026-08-11 — **ADR-020: pared to the orchestrator spine. 33 v1 requirements → 15.** Nothing
was deleted; 18 requirements moved to v2 § Cut by ADR-020 with their acceptance intact and are owed
a designed-not-built entry in the handoff. No acceptance criterion on a retained requirement was
weakened. ADR-011 (REV-01/02) and ADR-014 were considered for the cut and explicitly kept.*
