# Architecture Decisions

The authoritative decision record for asap-ireports. Where an entry conflicts with
`blueprint.md`, **this file wins** — the blueprint is the input, this is the project.

Each entry is numbered, dated, and carries a status. To change a decision, add a new entry that
supersedes the old one; never edit a decided entry in place. Split into individual `ADR-NNN.md`
files if this record outgrows a single document.

**Status values:** `Accepted` · `Superseded by ADR-NNN` · `Open` (deferred to
`OPEN-QUESTIONS.md`)

---

## ADR-001 — The deliverable is a proven architecture, not a product

**Date:** 2026-08-10 · **Status:** Accepted

**Context.** The ASAP program team will implement the production system. The risk is that they
inherit an architecture whose hardest parts — particularly the agentic orchestrator — were never
actually exercised, and discover the gaps during implementation.

**Decision.** The primary output of this project is a **handoff package**: a defended
architecture, a set of decisions with recorded reasoning, contracts, and evidence that the hard
parts work. Runnable code is a means of proof, not the deliverable. Handoff artifacts are built
continuously, not written up at the end.

**Consequences.** Every milestone produces artifacts a third party can act on. Claims are cited
or explicitly marked unverified. Work that produces a working demo but no transferable finding is
deprioritized against work that settles a real question.

---

## ADR-002 — Standalone platform; AmiLens is prior art, not a dependency

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** Clean-slate build of the blueprint's local-first architecture. No shared code,
infrastructure, or submodules with `amilens-localdev`.

**Rationale.** AmiLens is a working SEAD-4 prototype with a Postgres/PGVector retrieval stack and
a Next.js front end. This project targets OpenSearch-compatible vector retrieval and an
AWS-deployable bounded orchestrator — coupling them would force one architecture onto both.
AmiLens remains valuable as prior art: its own `CLAUDE.md` documents concrete gaps in its analysis
pipeline (SEAD-4 conditions present in the graph but never queried during analysis; no RAG over
policy at analysis time; no cross-referencing of subject statements against investigator findings)
that this architecture is specifically designed to close.

**Consequences.** No code reuse. Lessons and failure modes transfer by being written down.

---

## ADR-003 — Suitability and SEAD-4, with authority routing from day one

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** First release covers both 5 CFR part 731 suitability/fitness and SEAD-4
national-security eligibility, with the authority-routing engine implemented — not stubbed.

**Rationale.** Blueprint §2.1 argues routing is essential rather than optional: suitability,
fitness, PIV credentialing, and national-security eligibility are distinct authorities with
distinct criteria, and collapsing them produces analysis that is wrong in a way that is hard to
detect. Building routing after the fact is a refactor of every analysis path.

**Consequences.** Two approved policy packs at launch and roughly double the policy-ingestion and
evaluation work. Position designation and Fair Chance Act process controls are in scope.
PIV/HSPD-12 credentialing is out of scope for the first release but must not be structurally
excluded.

---

## ADR-004 — Local-first development, AWS GovCloud deployment target

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** Develop against Docker Compose locally with Bedrock via LiteLLM as the only network
egress. The deployment target is AWS GovCloud, with the Lambda/SAM adapter built and exercised.

**Rationale.** The program's data sensitivity points at GovCloud.

**Open risk — treat as a hard gate, not an assumption.** Claude model availability, concrete model
and inference-profile IDs, cross-region inference restrictions, and data-routing rules in GovCloud
are **unvalidated**. Blueprint §"Working assumptions" flags this and it remains true. Tracked as
Q-01 in `OPEN-QUESTIONS.md`; must be validated before any GovCloud deployment work is committed.

**Consequences.** All model references sit behind LiteLLM aliases (ADR-008) so a partition change
is a config change. GovCloud feature gaps must be checked per feature, not assumed from commercial
AWS behavior — several Bedrock capabilities differ from the first-party Claude API.

---

## ADR-005 — FastAPI is the boundary; no UI in Milestone 1

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** No Streamlit console (blueprint §4.1.2 is declined). FastAPI endpoints are the
stable interface for local use, for the eventual production front end, and for the Lambda adapter.
Review happens through JSON, contract tests, and the evaluation harness.

**Consequences.** No side-by-side evidence review for humans in M1, which is where human-in-the-loop
value is most visible. The human-review *state machine* (ADR-011) is still built and enforced —
only its presentation is deferred. Revisit once the orchestrator is proven.

---

## ADR-006 — No Neo4j

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** No graph database, in any milestone, until evidence demands one.

**Rationale.** Blueprint §15.2 makes Neo4j conditional on demonstrated benefit. AmiLens's own
`CLAUDE.md` describes its Neo4j layer as scaffolding — nodes exist, content and relationships are
minimal, and the analysis pipeline never queries it. That is direct evidence against carrying the
service.

**Consequences.** Cross-document relationships and timelines are served by structured entities and
dated events in PostgreSQL plus OpenSearch retrieval. Supersede this ADR with a measurement if
graph traversal is later shown to improve findings.

---

## ADR-007 — iReports queries an OpenSearch-compatible vector collection directly

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** In AWS, iReports issues hybrid lexical + kNN queries directly against an AWS
OpenSearch-compatible vector collection **owned and populated by a separate ingestion and
embedding pipeline**. iReports is a consumer of that collection, not its producer.

Local ingestion, chunking, and embedding exist for **development only** — to produce a realistic
local index to develop retrieval against. They are not a production component.

**Known collection shape (to be confirmed):** a facet distinguishing case data from policy
knowledge, plus case-file metadata facets (case number, subject name, file name, and similar)
supplied by a `document.xml` sidecar applied after ingestion.

**Consequences and risks.**

1. **Embedding-model parity is a hard coupling.** Querying a collection directly means our
   query-time embedding model must match the model their pipeline used to index. A mismatch
   produces silently degraded retrieval — no error, just worse results. This must be pinned,
   documented, and covered by a parity test. Tracked as Q-03.
2. All field names, filters, and facet mappings are isolated in a single mapping module so that
   adapting to the real schema is a one-file change (Q-02).
3. The embedding provider sits behind an interface. Every vector records model identifier and
   revision, dimension, normalization, input prefix, library version, and source text hash.
4. Local OpenSearch mirrors the assumed collection shape so local and AWS behavior match.

---

## ADR-008 — Three model tiers, referenced only by LiteLLM alias

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** Application code never names a model. It names one of three aliases:

| Alias | Role |
|---|---|
| `ireports-orchestrator` | Orchestration and control-flow reasoning |
| `ireports-thinking` | Deep criterion analysis, synthesis, challenge |
| `ireports-fast` | Classification, extraction, mechanical tasks |

LiteLLM config maps aliases to concrete Bedrock model IDs, inference profiles, and regions.

**Rationale.** Cost and latency control without hard-coding, and — given ADR-004's unvalidated
GovCloud availability — the ability to change partition, region, or model generation without
touching application code.

**Notes for implementation.** On Bedrock, model IDs take an `anthropic.` prefix. The blueprint
names Claude Sonnet 4.6; **Claude Sonnet 5 and Claude Opus 5 have since been released** and should
be evaluated for the thinking and orchestrator tiers rather than defaulting to the blueprint's
model. Current-generation models also changed the request surface — adaptive thinking with an
effort level replaces fixed thinking-token budgets, and sampling parameters are rejected on
several models. Pin the tested combination in a compatibility matrix (blueprint §15.3).

---

## ADR-009 — No offline run profile

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** The blueprint's "offline deterministic" profile (§3.1) is declined. There is no
recorded-fixture provider and no local LLM server. Bedrock access is required to run the system.

**Rationale.** Program decision — avoids maintaining a fixture corpus and a second model path.

**Consequences — accepted knowingly.** Any test that exercises a real model path is
network-dependent, non-deterministic, and costs money, so end-to-end runs cannot gate CI on every
commit. Unit and contract tests must therefore mock at the gateway boundary rather than relying on
a run profile. Reproducibility of a given run is preserved through recorded run manifests (model
alias, prompt version, retrieval query IDs, configuration versions), not through replay.

---

## ADR-010 — ASAP delivery: versioned envelope with embedded evidence excerpts, against a local mock

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** The authoritative ASAP ingestion contract is not available to this project. We
define a versioned JSON envelope carrying **bounded evidence excerpts plus stable references**,
and build a local ASAP mock that validates the schema and simulates status codes, timeouts, and
retries. Delivery uses a transactional outbox with idempotency keys and recorded receipts.

**Rationale.** Embedded excerpts make a delivered finding reviewable without a second lookup and
without depending on ASAP's ability to resolve references into our stores.

**Consequences.** The envelope is our proposal, not an agreed interface — a real contract will
require changes. Contract tests pin our side so the delta is measurable when the real spec lands.
Tracked as Q-04.

---

## ADR-011 — Hard human-review gate, single reviewer role

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** A run pauses in an explicit review state. One authorized reviewer role may accept,
modify, or reject each proposed finding. **Nothing reaches ASAP without a recorded disposition** —
there is no bypass, in any profile, including local development. Both the machine proposal and the
approved version are retained.

**Rationale.** Human review is a state transition, not a UI convention (blueprint §3.6). A
dev-mode auto-approve flag is exactly the kind of affordance that survives into production.

**Consequences.** End-to-end tests must drive the review transition explicitly rather than running
unattended. That friction is the point.

---

## ADR-012 — Orchestration framework is undecided pending a bake-off

**Date:** 2026-08-10 · **Status:** Open — resolved by Milestone 1

**Context.** This is the project's central risk. The blueprint recommends LangGraph (§9.3) but
supports the recommendation with a criteria comparison rather than a demonstration. Choosing wrong
is expensive: orchestration touches checkpointing, human-in-the-loop, error handling, packaging,
testing, and observability, and the choice is difficult to reverse once analysis nodes are written
against it.

**Decision.** No framework is adopted until a spike produces a scorecard. Candidates:

| Candidate | Why it is in the set |
|---|---|
| **LangGraph** | The blueprint's recommendation and the incumbent to beat. Explicit state graph, durable checkpoints, interrupt-based human-in-the-loop |
| **Strands Agents SDK** | AWS-aligned, documented Lambda packaging — relevant to a GovCloud target and an AWS-standardizing program |
| **PydanticAI / Pydantic Graph** | Typed agents and graphs on Pydantic v2, which we use for contracts regardless. Direct Bedrock support |
| **Hand-rolled Python** | The honest baseline. If a bounded, checkpointed state machine over PostgreSQL is a few hundred lines, that is the finding — and it carries no framework lifecycle risk |

Also considered, not in the M1 set: Claude Agent SDK, Haystack, AutoGen, CrewAI, LlamaIndex
Workflows, Semantic Kernel. A landscape scan (M1 task) may add candidates before the spike starts.

**Method — partial spike, not the full §9.4 scenario.** Each candidate implements only the legs
where frameworks actually differ:

1. Durable checkpoint and **resume in a separate process** after the first process exits
2. **Human-in-the-loop interrupt** — pause mid-run, record a disposition out of band, resume
3. **Survive a simulated model timeout** without losing or duplicating completed work
4. Bounded parallel fan-out of two specialist nodes, then join and de-duplicate

Scored on blueprint §9.4's dimensions: framework-specific lines of code, serialized state size,
resume correctness, ability to enforce budgets and tool allowlists, ease of inspecting and
replaying state, test determinism, dependency and vulnerability footprint, cold-start and image
size, and developer comprehension after a short onboarding exercise.

**Consequences.** No analysis-node code is written against any framework until this resolves. The
orchestration package is defined by a port so nodes depend on our interface, not the framework's.
The losing spikes are retained — a rejected candidate with a recorded reason is a handoff artifact.

---

## ADR-013 — Interactive analysis, one case at a time

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** A single selected case analyzed on demand, results in minutes. No batch queue in the
first milestone.

**Consequences.** Design for responsiveness and streaming run status. Job and lease management for
batch is deferred, but the run model must not assume a single in-process execution — checkpointing
and resume are required regardless (ADR-012).

**Unknown.** Real case sizes and daily volumes are not established. Working assumption: roughly
5–25 documents and a few hundred pages per case. Tracked as Q-05.

---

## ADR-014 — No universal person-risk score

**Date:** 2026-08-10 · **Status:** Accepted

**Decision.** Carried forward from blueprint §3.7 and treated as binding. No contract carries an
aggregate risk score, risk level, or overall recommendation field. Findings are per-criterion,
per-authority, evidence-backed, and individually dispositioned.

**Rationale.** A single score collapses distinct legal authorities with different criteria and
different consequences into a number that invites exactly the deference the decision-support
boundary prohibits. It is also the field most likely to be extracted downstream and used as a
determination.

**Consequences.** Schema review must reject any field that functions as an aggregate score,
whatever it is named.
