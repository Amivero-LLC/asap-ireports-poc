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
  ingestion pipeline owns, what ASAP owns, and where the human review gate sits.
- Library and framework inventory with versions, and the reason each one is there.
- Data contracts as Pydantic models with generated JSON Schema: case, document, evidence, finding,
  run manifest, human disposition, ASAP envelope. Contracts first — they are the interface the
  orchestration decision has to satisfy.
- The authority-routing model: how a case maps to 5 CFR 731 suitability/fitness, SEAD-4, or both.

**Exit:** program leadership can sign off on components, libraries, and contracts.

### 1b · Orchestration landscape scan

Survey current agentic-orchestration frameworks — maintenance activity, release cadence, API
stability, production adoption, licensing, and dependency footprint. The candidate set in ADR-012
was drawn from a document written earlier; confirm it is still the right set before spending spike
effort, and add or drop candidates with a recorded reason.

**Exit:** a short written scan; ADR-012's candidate list confirmed or amended.

### 1c · Orchestration bake-off (partial spike)

Each candidate — LangGraph, Strands Agents SDK, PydanticAI/Pydantic Graph, hand-rolled Python —
implements the same narrow scenario, covering only the legs where frameworks actually differ:

1. Durable checkpoint and **resume in a separate process** after the first exits
2. **Human-in-the-loop interrupt** — pause mid-run, record a disposition out of band, resume
3. **Survive a simulated model timeout** without losing or duplicating completed work
4. Bounded parallel fan-out of two specialist nodes, then join and de-duplicate

Scored on blueprint §9.4: framework-specific lines of code, serialized state size, resume
correctness, budget and tool-allowlist enforcement, ease of inspecting and replaying state, test
determinism, dependency and vulnerability footprint, cold-start and image size, and developer
comprehension after a short onboarding exercise.

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
