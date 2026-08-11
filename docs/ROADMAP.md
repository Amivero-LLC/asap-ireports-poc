# Roadmap

Sequenced so that the riskiest architectural claims are settled first and every milestone leaves
behind an artifact the ASAP program team can act on (ADR-001).

---

## Milestone 1 — Architecture sign-off and the orchestration decision

**Goal:** produce an architecture the program can sign off on, with the orchestration framework
chosen on evidence rather than assertion.

This milestone exists because the agentic orchestrator is the part of this system most likely to
be underestimated, and the framework choice is the hardest thing to reverse once analysis nodes
are written against it.

### 1a · Architecture package

- Component architecture with the boundaries that matter marked: what is ours, what the AWS
  ingestion pipeline owns, what ASAP owns, and where the human review gate sits. — **outstanding**
- Library and framework inventory with versions, and the reason each one is there. —
  **partly covered** by the 1b scan's measured footprint and version tables; the non-orchestration
  layers still need writing up.
- Data contracts as Pydantic models with generated JSON Schema: case, document, evidence, finding,
  run manifest, human disposition, ASAP envelope. Contracts first — they are the interface the
  orchestration decision has to satisfy. — **done (2026-08-10)**
- The authority-routing model: how a case maps to 5 CFR 731 suitability/fitness, SEAD-4, or both.
  — **contract done**, routing engine itself is Milestone 2.

**Contracts delivered.** Thirteen contracts in `packages/domain/`, published to `schemas/`,
documented in `docs/handoff/contracts.md`. ADR-014, ADR-011, ADR-008, and the decision-support
boundary are enforced structurally and asserted by 56 tests rather than left to review. Deferred:
`ChunkRecord`, `EntityCandidate`, `TimelineEvent`, and `PolicyRecord` (blocked on Q-02), and
`SpecialistResult` (deliberately deferred until ADR-012 resolves, since its shape is the one most
likely to be influenced by the framework).

**Exit:** program leadership can sign off on components, libraries, and contracts.
**Status:** contracts ready for sign-off; the component-architecture write-up is outstanding.

### 1b · Orchestration landscape scan — **complete (2026-08-10)**

Survey current agentic-orchestration frameworks — maintenance activity, release cadence, API
stability, production adoption, licensing, and dependency footprint. The candidate set in ADR-012
was drawn from a document written earlier; confirm it is still the right set before spending spike
effort, and add or drop candidates with a recorded reason.

**Exit met.** `docs/handoff/orchestration-landscape.md`. ADR-012's candidate set amended: PydanticAI
/ Pydantic Graph dropped (Pydantic Graph 2.x has no state-persistence API, so it cannot attempt
spike leg 1); AutoGen and Semantic Kernel removed from consideration (maintenance mode since April
2026); Microsoft Agent Framework, DBOS, Temporal, and Restate recorded as considered-and-not-spiked.
Four candidates became three. The scan also added three spike deliverables to 1c and raised Q-14.

### 1c · Orchestration bake-off (partial spike)

Each candidate — **LangGraph, Strands Agents SDK, hand-rolled Python** (three, per the 1b scan) —
implements the same narrow scenario, covering only the legs where frameworks actually differ:

1. Durable checkpoint and **resume in a separate process** after the first exits
2. **Human-in-the-loop interrupt** — pause mid-run, record a disposition out of band, resume
3. **Survive a simulated model timeout** without losing or duplicating completed work
4. Bounded parallel fan-out of two specialist nodes, then join and de-duplicate

Scored on blueprint §9.4: framework-specific lines of code, serialized state size, resume
correctness, budget and tool-allowlist enforcement, ease of inspecting and replaying state, test
determinism, dependency and vulnerability footprint, cold-start and image size, and developer
comprehension after a short onboarding exercise.

Plus three deliverables the 1b scan added, each a question reading could not settle: assert on
**resume semantics under a mid-node process kill** (does completed work re-execute?); a **LangSmith
egress-deny test** if LangGraph is selected, since `langsmith` is a mandatory transitive dependency
of `langchain-core`; and a **checkpoint-store threat model** treating the checkpoint blob as a
deserialization trust boundary in every design, hand-rolled included.

**All three candidates built and passing (2026-08-11).** Full results, measurement method, and
the fair reading of every number: `spikes/README.md`. Headline, one ruler across all three
(`spikes/measure.py`):

| | hand-rolled | LangGraph | Strands |
|---|---|---|---|
| Four legs | pass | pass | pass |
| Candidate-specific lines | **195** | 266 (192 net of spike-only instrumentation) | 373 |
| State at the review interrupt | 16,346 B | **16,115 B** (37,033 B retained for the run) | 23,739 B |
| Distributions / size beyond baseline | **0 / 0.0 MB** | 31 / 18.0 MB | 42 / 47.3 MB |
| `pip-audit` advisories, pinned set | 0 | 0 | 0 |

**Both LangGraph-specific deliverables the 1b scan required are done.** The LangSmith egress-deny
test (`spikes/langgraph/test_langsmith_egress.py`) proves the default is closed, proves an
explicit `langsmith.configure(enabled=False)` pin beats a hostile inherited `LANGSMITH_TRACING`,
and — via a negative control — proves the risk is real rather than theoretical: unpinned, a run
`POST`s roughly 90 KB of graph state including finding text to `api.smith.langchain.com`, **and
still succeeds**, because LangSmith swallows the failure. The framework-independent
`docs/handoff/checkpoint-threat-model.md` records the checkpoint blob as a deserialization trust
boundary in every design, together with the controls this project did *not* build.

Two LangGraph defaults are wrong for this architecture and invisible in the code: `durability`
defaults to `async` rather than `sync`, and checkpoint deserialization defaults to permissive —
the library's own source says *"any Python callable stored in checkpoint data will be imported and
executed on load"* without `LANGGRAPH_STRICT_MSGPACK`. The candidate sets both in code.

**The duplicate-model-call window is universal, not an artifact.** The 2026-08-10 write-up
predicted that Strands' 0/12 was an artifact of our synchronous node bodies and that a candidate
with genuine concurrent fan-out would show the window. LangGraph is that candidate and it does:
over 24 trials the sibling's call was in flight at crash time in **24/24** and cost a duplicate
paid call in **11/24**, against hand-rolled's 12/24 and Strands' 0/24. Model-call-level
idempotency (blueprint §8.5 duplicate-query detection) is owed by **all three**.

**Superseded figures, recorded rather than quiet.** The 2026-08-10 line counts (hand-rolled 202,
Strands 367) came from an unrecorded method and could not be reproduced; re-counted by
`spikes/measure.py` they are 195 and 373 — within 4%, ordering unchanged.

**What the harness guarantees**, unchanged since 2026-08-10: node bodies are shared so that
"framework-specific lines of code" measures wiring and nothing else; the stub gateway logs every
model call to PostgreSQL outside the framework so leg 1 is answerable; candidates are driven
across a real process boundary; and a permanently retained broken candidate proves leg 1 can
actually fail something. Leg 1 was once tightened to assert on every specialist and then reverted
— re-running work the orchestrator never observed completing is correct at-least-once behaviour,
so the stricter assertion is flaky rather than strict.

**The scan's highest-value unknown, settled (2026-08-10, unchanged).** The third-party claim that
Strands restores *conversation* rather than resuming *execution* **does not hold for `Graph` in
`strands-agents` 1.51.0**: `serialize_state` carries `completed_nodes` and `next_nodes_to_execute`,
state is synced after every node, and after a hard `os._exit(9)` no completed node re-executed.
The same was asserted rather than assumed for LangGraph, with the same result. What *is* true of
Strands is that its state container is conversation-shaped — a node's durable result must be an
`AgentResult`, which persists only `message` and `stop_reason` — so typed contracts are flattened
into a message body and re-validated on the way out, which is also why its checkpoint is the
largest of the three.

**Remaining:** cold start and packaging under SAM local, for all three candidates.

**Exit:** a scorecard, a recommendation, and ADR-012 moved from `Open` to `Accepted`. Losing
spikes are kept — a rejected candidate with a recorded reason is part of the handoff.

---

## Milestone 2 — The orchestrator produces an iReport

**Goal:** the general orchestrator runs end to end and produces an iReport from a single
sub-agent query — the simplest path that touches every seam, before any optimization.

- Orchestrator on the chosen framework, behind our own port so nodes never import it directly
- One synthetic case, ingested locally and indexed into local OpenSearch
- Authority routing selects the policy pack
- A single specialist sub-agent query produces proposed findings against one criterion
- Deterministic validators: schema, citation resolution, policy effectivity, prohibited content
- Human review gate — run pauses, disposition recorded, run resumes
- Delivery to the ASAP mock through the outbox with an idempotency key

**Exit:** one command takes a synthetic case to a delivered, human-approved iReport. Every seam
has been exercised once.

---

## Milestone 3 — Optimize

Widen and deepen against measurements from M2, in the order the evidence justifies. Candidates:
the full specialist set across both authority families; retrieval quality work (hybrid fusion,
query planning, reranking); the contradiction and challenge stages; multi-criterion fan-out;
model-tier tuning across the three aliases; the evaluation harness and red-team scenarios.

Sequence this from M2 findings — not from this list.

---

## Continuous — the handoff package

Built as we go, not written up at the end (ADR-001):

- `docs/DECISIONS.md` — every decision with its reasoning, kept current
- `docs/OPEN-QUESTIONS.md` — what remains unresolved and what it would cost to be wrong
- The bake-off scorecard and the retained spikes
- Contracts and schemas
- Deployment and packaging notes, including whatever Q-01 turns up about GovCloud
- Known failure modes and things we tried that did not work — the most useful and most commonly
  omitted artifact in a handoff
