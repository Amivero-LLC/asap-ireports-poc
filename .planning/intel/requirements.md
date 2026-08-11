# Requirements Intel

Extracted from PRD-typed sources. One source contributed:

- `docs/ROADMAP.md` — precedence 2, not locked. Milestone plan with exit criteria and per-item status.

Because only one PRD is in the ingest set, there are **no competing acceptance variants** — no two
PRDs define the same requirement with divergent acceptance criteria. Every requirement below has a
single acceptance statement traceable to one source.

Status as of 2026-08-11: 1a data contracts DONE, component-architecture write-up OUTSTANDING and
the last item blocking program sign-off on 1a; 1b COMPLETE; 1c COMPLETE (ADR-012 Accepted,
orchestration framework is LangGraph); Milestones 2 and 3 not started.

Requirement IDs are derived (`REQ-{slug}`) and are stable handles for downstream planning; they do
not appear in the source.

---

## Milestone 1 — Architecture sign-off and the orchestration decision

**Goal (verbatim):** produce an architecture the program can sign off on, with the orchestration
framework chosen on evidence rather than assertion.

**Status:** orchestration decision made 2026-08-11 (LangGraph, ADR-012 Accepted). Only the 1a
component-architecture write-up remains open.

### 1a · Architecture package
source: docs/ROADMAP.md §1a
**Exit criteria (verbatim):** "Exit: program leadership can sign off on components, libraries, and
contracts."
**Status (verbatim):** "Status: contracts ready for sign-off; the component-architecture write-up
is outstanding."

**REQ-component-architecture** — status: **OUTSTANDING** — *last item blocking program sign-off on 1a*
source: docs/ROADMAP.md §1a
Component architecture with the boundaries that matter marked: what is ours, what the AWS ingestion
pipeline owns, what ASAP owns, and where the human review gate sits.
Acceptance: program leadership can sign off on the component boundaries.

**REQ-library-inventory** — status: **partly covered**
source: docs/ROADMAP.md §1a
Library and framework inventory with versions, and the reason each one is there.
Acceptance: every dependency has a recorded version and rationale.
Detail: covered for the orchestration layer by the 1b scan's measured footprint and version tables
(`docs/handoff/orchestration-landscape.md` §4.1, §4.2). The non-orchestration layers still need
writing up.

**REQ-data-contracts** — status: **DONE (2026-08-10)**
source: docs/ROADMAP.md §1a
Data contracts as Pydantic models with generated JSON Schema: case, document, evidence, finding,
run manifest, human disposition, ASAP envelope. Contracts come first because they are the interface
the orchestration decision has to satisfy.
Acceptance (met): thirteen contracts in `packages/domain/`, published to `schemas/`, documented in
`docs/handoff/contracts.md`; 56 contract tests passing; contract version 1.0.0, envelope version
1.0.0.
Deferred, carried forward: `ChunkRecord`, `EntityCandidate`, `TimelineEvent`, `PolicyRecord`
(blocked on Q-02 — the AWS collection's real schema) and `SpecialistResult` (deferred until ADR-012
resolved; **that block is now lifted** and `SpecialistResult` is unblocked forward work).

**REQ-authority-routing-model** — status: **contract done**, routing engine is Milestone 2
source: docs/ROADMAP.md §1a
The authority-routing model: how a case maps to 5 CFR 731 suitability/fitness, SEAD-4, or both.
Acceptance: `AuthorityRoutingResult` requires an explicit decision for **every** authority,
including those that do not apply — an absent route is indistinguishable from an oversight.

### 1b · Orchestration landscape scan
source: docs/ROADMAP.md §1b
**Status:** complete (2026-08-10).
**Exit criteria (verbatim):** "Exit met. `docs/handoff/orchestration-landscape.md`."

**REQ-orchestration-landscape-scan** — status: **DONE (2026-08-10)**
Survey current agentic-orchestration frameworks — maintenance activity, release cadence, API
stability, production adoption, licensing, dependency footprint — and confirm or amend ADR-012's
candidate set with a recorded reason per change.
Outcome: PydanticAI / Pydantic Graph dropped (no state-persistence API in Pydantic Graph 2.x);
AutoGen and Semantic Kernel removed (maintenance mode since April 2026); Microsoft Agent Framework,
DBOS, Temporal, Restate recorded as considered-and-not-spiked. Four candidates became three. Added
three spike deliverables to 1c and raised Q-14.

### 1c · Orchestration bake-off (partial spike)
source: docs/ROADMAP.md §1c
**Status:** complete (2026-08-11).
**Exit criteria (verbatim):** "Exit met (2026-08-11). ADR-012 is Accepted: the orchestration
framework is LangGraph."

**REQ-bakeoff-four-legs** — status: **DONE (2026-08-11)** — all three candidates built and passing
Each candidate (LangGraph, Strands Agents SDK, hand-rolled Python) implements the same narrow
scenario, covering only the legs where frameworks actually differ:
1. Durable checkpoint and resume **in a separate process** after the first exits
2. Human-in-the-loop interrupt — pause mid-run, record a disposition out of band, resume
3. Survive a simulated model timeout without losing or duplicating completed work
4. Bounded parallel fan-out of two specialist nodes, then join and de-duplicate
Scored on blueprint §9.4 dimensions.

**REQ-langsmith-egress-deny** — status: **DONE**
A LangSmith egress-deny test, required because `langsmith` is a mandatory transitive dependency of
`langchain-core`. Acceptance (met): `spikes/langgraph/test_langsmith_egress.py` proves the default
is closed, proves an explicit `langsmith.configure(enabled=False)` pin beats a hostile inherited
`LANGSMITH_TRACING`, and via a negative control proves the risk is real — unpinned, a run POSTs
~90 KB of graph state including finding text to `api.smith.langchain.com` **and still succeeds**.

**REQ-checkpoint-threat-model** — status: **DONE**
A framework-independent checkpoint-store threat model treating the checkpoint blob as a
deserialization trust boundary in every design, hand-rolled included.
Acceptance (met): `docs/handoff/checkpoint-threat-model.md`, including §6's list of controls **not**
built.

**REQ-resume-semantics-assertion** — status: **DONE**
Assert on resume semantics under a mid-node process kill for every candidate: does completed work
re-execute? Outcome: the unconfirmed third-party claim that Strands restores *conversation* rather
than resuming *execution* **does not hold** for `Graph` in 1.51.0. Asserted rather than assumed for
LangGraph too, same result.

**Carried forward from 1c into Milestone 2 (not blocking the 1c exit):**
- Cold start and packaging under SAM local — unmeasured for all three, and the one number most
  likely to reopen the framework choice. `spikes/test_scorecard.py` fails the moment it is
  recorded, forcing the recommendation to be re-read rather than left standing.
- Model-call-level idempotency (blueprint §8.5 duplicate-query detection) — owed by all three
  candidates, built by none.

---

## Milestone 2 — The orchestrator produces an iReport

source: docs/ROADMAP.md §Milestone 2 · **status: not started**

**Goal (verbatim):** the general orchestrator runs end to end and produces an iReport from a single
sub-agent query — the simplest path that touches every seam, before any optimization.

**Exit criteria (verbatim):** "Exit: one command takes a synthetic case to a delivered,
human-approved iReport. Every seam has been exercised once."

**REQ-orchestrator-on-langgraph** — Orchestrator on LangGraph (ADR-012), **behind our own port so
nodes never import it directly.** ADR-012 calls this Milestone 2's first obligation.

**REQ-model-call-idempotency** — Model-call-level idempotency (blueprint §8.5 duplicate-query
detection). Owed by every 1c candidate and built by none; a crash mid-fan-out currently re-runs an
in-flight model call. Measured: hand-rolled 12/24, LangGraph 11/24, Strands 0/24 (artifact of
synchronous node bodies). This is a property of at-least-once execution with uncommitted in-flight
calls, not a framework discriminator.

**REQ-synthetic-case-ingest** — One synthetic case, ingested locally and indexed into local
OpenSearch. *Note: the local index definition is gated by Q-02 — see conflicts report.*

**REQ-authority-routing-engine** — Authority routing selects the policy pack.

**REQ-specialist-query** — A single specialist sub-agent query produces proposed findings against
one criterion.

**REQ-deterministic-validators** — Deterministic validators: schema, citation resolution, policy
effectivity, prohibited content.

**REQ-human-review-gate** — Human review gate: run pauses, disposition recorded, run resumes.
Enforced as a state transition with no bypass in any profile (ADR-011).

**REQ-asap-delivery-outbox** — Delivery to the ASAP mock through the outbox with an idempotency key.

**REQ-refusal-to-information-gap** — Wire a refused specialist and a `StructuredOutputError` to the
reviewer as an `InformationGap` (`blocking=True`) rather than as an absent finding. The contracts
already support it; wiring both is one job.
source: docs/handoff/model-gateway.md §3, docs/DECISIONS.md ADR-018

---

## Milestone 3 — Optimize

source: docs/ROADMAP.md §Milestone 3 · **status: not started**

**Goal (verbatim):** Widen and deepen against measurements from M2, in the order the evidence
justifies.

**Exit criteria: NONE STATED.** The source is explicit: "Sequence this from M2 findings — not from
this list." Candidates listed, deliberately unordered and unscoped: the full specialist set across
both authority families; retrieval quality work (hybrid fusion, query planning, reranking); the
contradiction and challenge stages; multi-criterion fan-out; model-tier tuning across the three
aliases; the evaluation harness and red-team scenarios.

See `INGEST-CONFLICTS.md` WARNING — M3 cannot be decomposed into phases from this intel.

---

## Continuous — the handoff package

source: docs/ROADMAP.md §Continuous · **status: ongoing** · rationale: ADR-001, built as we go

- `docs/DECISIONS.md` — every decision with its reasoning, kept current
- `docs/OPEN-QUESTIONS.md` — what remains unresolved and what it would cost to be wrong
- The bake-off scorecard and the retained spikes
- Contracts and schemas
- Deployment and packaging notes, including whatever Q-01 turns up about GovCloud
- Known failure modes and things we tried that did not work — described in the source as "the most
  useful and most commonly omitted artifact in a handoff"

---

## Outstanding work items carried into planning

Each is recorded in a source document and is real, unbuilt work.

| ID | Item | Source | Blocked by |
|---|---|---|---|
| `REQ-model-call-idempotency` | Model-call-level idempotency / duplicate-query detection | ROADMAP M2, scorecard §4, blueprint §8.5 | — |
| `REQ-cold-start-measurement` | Cold start and packaging under SAM local, all candidates | ROADMAP 1c, scorecard §2 | — |
| `REQ-checkpoint-row-integrity` | Keyed MAC over serialized checkpoint state, key unreadable by the DB role, verified on load. **Single largest gap**; converts threats T2/T3 from difficult to detectable | checkpoint-threat-model.md §6 | — |
| `REQ-checkpoint-least-privilege` | Separate checkpoint-write DB role, distinct from everything else and from the migration role | checkpoint-threat-model.md §6 | — |
| `REQ-checkpoint-encryption-at-rest` | Encryption at rest and backup handling — assumed platform-provided, `[unverified]` | checkpoint-threat-model.md §6 | Q-01 |
| `REQ-checkpoint-retention` | Retention and pruning policy for checkpoints carrying case-derived text; 37,033 B retained per run and growing | checkpoint-threat-model.md §6, scorecard §3 | Q-09 |
| `REQ-checkpoint-provenance-on-load` | Record which checkpoint id a resumed run resumed from, into the run manifest, so an audit can reconstruct the resume chain. "Cheap to add; not added" | checkpoint-threat-model.md §6 | — |
| `REQ-deferred-contracts` | `ChunkRecord`, `EntityCandidate`, `TimelineEvent`, `PolicyRecord` | contracts.md §5, ROADMAP 1a | Q-02 |
| `REQ-specialist-result-contract` | `SpecialistResult` contract — **block lifted**, ADR-012 resolved | contracts.md §5 | — (was ADR-012) |
| `REQ-fix-mypy-tests-contract` | 13 pre-existing `mypy --strict` errors, all in `tests/contract/` — nine unused `# type: ignore`, four missing annotations in `test_decision_support_boundary.py`. No package under `packages/` affected | model-gateway.md §6 | — |
| `REQ-max-excerpt-chars` | `MAX_EXCERPT_CHARS = 2000` is an unresearched starting value; revisit against real ASAP payload limits | contracts.md §5 | Q-04 |
| `REQ-migrate-spike-to-gateway-port` | `spikes/harness/gateway.py` is a separate Postgres-backed instrument; migrating the spike onto the real `ModelGateway` port | model-gateway.md §5 | — |
| `REQ-retry-fallback-policy` | No retry or fallback policy yet. Server-side `fallbacks` unavailable on Bedrock; deferred until the orchestrator exists to own bounded retry semantics | model-gateway.md §5, blueprint §8.5 | — |
| `REQ-streaming-run-status` | No streaming. ADR-013 single-case interactive runs want streaming run status eventually; the port is synchronous today. Additive change | model-gateway.md §5 | — |
