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

**Amended 2026-08-10 by ADR-015** — recorded 2026-08-11, on a gap the doc ingest surfaced. This
entry says "Bedrock **via LiteLLM** as the only network egress"; ADR-015 adds a `bedrock` adapter
using the standard AWS credential chain with no proxy, which is a Bedrock call that does not go via
LiteLLM. ADR-015 declared itself an amendment to ADR-008 and quoted the equivalent `CLAUDE.md`
sentence, but did not name ADR-004, so the two entries read as though they disagree.

**They do not, and the distinction is worth stating.** What ADR-004 governs is *what egress is
permitted* — nothing but Bedrock — and that is unchanged. "Via LiteLLM" was mechanism wording, and
the mechanism is what ADR-015 revisits. The surviving constraint is the stronger one: **the model
gateway port is the only component permitted to call a model.** Read ADR-004's egress rule that way.

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

**Date:** 2026-08-10 · **Status:** Superseded by ADR-022 (2026-08-11)

> **Superseded.** This entry modelled human review as an in-run pause. iReports has no human
> interaction — it runs unattended and emits output, and review happens afterwards in ASAP. The
> decision below is retained unedited as the record of what was believed and why; **ADR-022 is
> what holds.** The decision-support boundary itself did not change: no determination, no
> aggregate score, everything emitted is a proposal.

**Decision.** A run pauses in an explicit review state. One authorized reviewer role may accept,
modify, or reject each proposed finding. **Nothing reaches ASAP without a recorded disposition** —
there is no bypass, in any profile, including local development. Both the machine proposal and the
approved version are retained.

**Rationale.** Human review is a state transition, not a UI convention (blueprint §3.6). A
dev-mode auto-approve flag is exactly the kind of affordance that survives into production.

**Consequences.** End-to-end tests must drive the review transition explicitly rather than running
unattended. That friction is the point.

---

## ADR-012 — Orchestration framework: LangGraph

**Date:** 2026-08-10 · **Resolved:** 2026-08-11 · **Status:** Accepted

**Decision: LangGraph**, on the evidence in `docs/handoff/orchestration-scorecard.md` and the
retained spikes under `spikes/`. The entry below is the original text, which set the method and
the candidate set; §"Resolution" at the end records the outcome. Nothing above it was edited —
the reasoning that led to a bake-off is as much a handoff artifact as its result.

**Context.** This is the project's central risk. The blueprint recommends LangGraph (§9.3) but
supports the recommendation with a criteria comparison rather than a demonstration. Choosing wrong
is expensive: orchestration touches checkpointing, human-in-the-loop, error handling, packaging,
testing, and observability, and the choice is difficult to reverse once analysis nodes are written
against it.

**Decision.** No framework is adopted until a spike produces a scorecard. Candidates, **as amended
by the Milestone 1b landscape scan on 2026-08-10** (`docs/handoff/orchestration-landscape.md`):

| Candidate | Why it is in the set |
|---|---|
| **LangGraph** | The blueprint's recommendation and the incumbent to beat. Explicit state graph, durable checkpoints, interrupt-based human-in-the-loop. Scan confirmed: the only candidate where a PostgreSQL checkpointer is a first-party package, and the only one with a written semver stability commitment |
| **Strands Agents SDK** | AWS-aligned, documented Lambda packaging — relevant to a GovCloud target and an AWS-standardizing program. Scan confirmed a real first-class interrupt primitive; also found session storage is file/S3 only, so a PostgreSQL `SessionRepository` is ours to build |
| **Hand-rolled Python** | The honest baseline. If a bounded, checkpointed state machine over PostgreSQL is a few hundred lines, that is the finding — and it carries no framework lifecycle risk. Scan weighted this up: 17 distributions / 28 MB against 42–47 / 46–62 MB for every framework measured |

**Dropped by the scan — PydanticAI / Pydantic Graph.** Originally in the set for typed agents and
graphs on Pydantic v2. Removed because Pydantic Graph 2.x **has no state-persistence API at all**
(verified in source at tag `v2.27.0`), 1.x had only file and in-memory backends — never PostgreSQL —
and durability is delegated to Temporal, DBOS, or Prefect via `pydantic_ai/durable_exec/`. It
therefore cannot attempt spike leg 1 without either becoming the hand-rolled baseline plus a
dependency, or importing a workflow engine this project has not decided to adopt. A near-daily minor
release cadence alongside a concurrent 1.x line compounds the API-stability risk. **This does not
affect Pydantic v2 for contracts**, which stands; PydanticAI also remains available as a typed
agent-and-tool layer *inside* whichever orchestrator wins.

The scan reduced the set from four candidates to three deliberately. The freed effort goes into the
spike legs where the answer is genuinely unknown, rather than into a fourth scorecard row that would
read as a comparison without being one.

Also considered, not in the M1 set: Microsoft Agent Framework (closest human-in-the-loop semantics
in the field and the lightest core measured, but Azure-oriented against a GovCloud/Bedrock program),
DBOS and Temporal and Restate (durable-execution substrates, not agent orchestrators; DBOS requires
a long-running process, conflicting with the ADR-004 Lambda adapter), Claude Agent SDK, Haystack,
CrewAI, LlamaIndex Workflows, Burr. **AutoGen and Semantic Kernel are removed from consideration
entirely** — both moved to maintenance mode in April 2026 and merged into Microsoft Agent Framework,
so blueprint §9.2 evaluates them as live options when they are not.

Amazon Bedrock AgentCore reached AWS GovCloud (US-West) on 2026-05-05, after the blueprint was
written. It is a managed runtime rather than a Python orchestration library, so it is not a bake-off
candidate, but it is a live alternative to the Lambda adapter for production deployment and its
documented GovCloud feature gaps and export-control language bear on ADR-004 and Q-01. The scan
proposes a new open question (Q-14) covering whether it is an approved deployment target.

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

**Added to the spike by the 1b scan.** Three measurements the scan could not make by reading, which
the bake-off must produce:

1. **Resume semantics under a mid-node process kill** — for every candidate, assert on whether
   completed work re-executes. A third party alleges Strands restores *conversation* rather than
   resuming *execution*; the source sells a competing product and the claim is unconfirmed, so it is
   a measurement, not a finding. Assert it for LangGraph too rather than assuming it.
2. **LangSmith egress-deny test.** `langsmith` is a mandatory transitive dependency of
   `langchain-core`, so it is in the tree whether or not we use it. Tracing is opt-in and the
   default is not egress, but a client library capable of exporting run content out of a system that
   may carry CUI must be *pinned closed and proven closed*, not trusted. Required deliverable if
   LangGraph is selected.
3. **Checkpoint-store threat model**, framework-independent. Four deserialization advisories landed
   on LangGraph's checkpoint path between November 2025 and June 2026 — all fixed in versions at or
   below what we would use. The finding is not that a framework is insecure; it is that the
   checkpoint blob is a deserialization trust boundary in any design, including a hand-rolled one,
   and must be integrity-controlled, access-controlled, and never fed from outside our own
   PostgreSQL.

**Consequences.** No analysis-node code is written against any framework until this resolves. The
orchestration package is defined by a port so nodes depend on our interface, not the framework's.
The losing spikes are retained — a rejected candidate with a recorded reason is a handoff artifact.
PydanticAI was rejected before the spike rather than during it; the reasoning above is its recorded
entry, and the evidence sits in `docs/handoff/orchestration-landscape.md` §5.3.

### Resolution — 2026-08-11

**All three candidates pass all four legs.** The decision is therefore not about correctness but
about which costs the program carries for the life of the system. Full scorecard, with the fair
reading of every number: `docs/handoff/orchestration-scorecard.md` and
`orchestration-scorecard.json` (a validated `Scorecard` contract, not a hand-typed table).

| | hand-rolled | **LangGraph** | Strands |
|---|---|---|---|
| Candidate-specific lines | 195 | 266 (~192 net of spike-only instrumentation) | 373 |
| State at the review interrupt | 16,346 B | 16,115 B (37,033 B retained per run) | 23,739 B |
| Distributions / size beyond baseline | 0 / 0.0 MB | 31 / 18.0 MB | 42 / 47.3 MB |
| `pip-audit` advisories, pinned set | 0 | 0 | 0 |
| Cold start under SAM local | not run | not run | not run |

**Why LangGraph.** The capability this ADR named as load-bearing — durable checkpointing over
PostgreSQL — cost **two lines**, against 56 for the hand-rolled store and 166 for the
`SessionRepository` Strands does not ship, and its durability is per-task inside a super-step
rather than per-super-step. Net of instrumentation its wiring is ~192 lines, *below* the
hand-rolled floor of 195, while additionally providing scheduling, a native interrupt, and
declarative retry. It is the only candidate with a written semver commitment, which is the
property a version-pinning, ATO-bound program most needs. And the conditions this ADR attached to
selecting it are met rather than deferred.

**Why not hand-rolled.** Not rejected on its measurements, which are excellent. Rejected on the
ledger behind them: no-progress and duplicate-query detection, cancellation, tool allowlists,
budget accounting, OTel spans, replay, and a scheduler are all absent, all needed, and all work
this program would own forever rather than inherit. 195 is a floor that grows. Retained as the
fallback if the dependency surface is refused.

**Why not Strands.** Dominated on every measured dimension — 373 lines to 266, a 47% larger
checkpoint for identical content, 42 distributions / 47.3 MB to 31 / 18.0 MB. Its real asset is
AWS alignment and first-class Lambda packaging, which does not offset that spread, and AWS
publishes prescriptive Lambda guidance for LangGraph as well. The structural objection is that its
state container is a transcript, so typed contract records pay a serialize/parse tax at every node
boundary — a poor fit for an architecture whose discipline is typed, citable, validated records.

**Three findings that outlive the choice.**

1. **The duplicate-model-call window is universal.** A crash mid-fan-out re-runs a sibling
   specialist whose model call was in flight but uncommitted: hand-rolled 12/24, LangGraph 11/24,
   Strands 0/24 — and Strands' zero is an artifact of our synchronous node bodies, confirmed by
   LangGraph, which genuinely interleaves and shows the window. **Model-call-level idempotency
   (blueprint §8.5 duplicate-query detection) is owed by all three and built by none.** It is a
   Milestone 2 requirement regardless of this decision.
2. **Two LangGraph defaults are wrong for this architecture and invisible in the code.**
   `durability` defaults to `async` rather than `sync`; checkpoint deserialization defaults to
   permissive, where the library's own source states that *"any Python callable stored in
   checkpoint data will be imported and executed on load"*. Both are now set in code, with tests.
   A graph reads identically either way, so a reviewer cannot catch these by reading it.
3. **The scan's highest-value unknown is settled.** The third-party claim that Strands restores
   conversation rather than resuming execution **does not hold** for `Graph` in 1.51.0. Asserted,
   not assumed, for LangGraph too.

**Conditions carried forward, not closed.**

- **Cold start and packaging under SAM local were not measured for any candidate.** This is the
  one outstanding number most likely to reopen the choice, and ADR-004 commits to exercising that
  adapter. `spikes/test_scorecard.py` fails the moment a cold-start figure is recorded, which
  forces the recommendation to be re-read against it rather than left standing by default.
- **LangSmith stays pinned closed and proven closed.** `langsmith` is a mandatory transitive
  dependency of `langchain-core`. The control is `langsmith.configure(enabled=False)` at the entry
  point, verified and fail-closed, with a negative control showing that an *unpinned* run `POST`s
  roughly 90 KB of graph state — including finding text — to `api.smith.langchain.com` **and still
  succeeds**, because the failure is swallowed. Any future entry point inherits this obligation.
- **The checkpoint blob remains a deserialization trust boundary**, in this and any design.
  `docs/handoff/checkpoint-threat-model.md`, including §6's list of controls not built — row-level
  integrity being the largest.
- **Nodes depend on our port, never on LangGraph directly.** The original consequence stands
  unchanged and is Milestone 2's first obligation. This decision selects an implementation behind
  the port; it does not license `from langgraph import ...` in analysis code.

**The losing spikes are retained** under `spikes/handrolled/` and `spikes/strands/`, passing the
same suite, and `spikes/harness/negative_control.py` stays permanently so leg 1 keeps being a test
that can fail.

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

---

## ADR-015 — Two model-gateway adapters behind one port; both use the Anthropic SDK

**Date:** 2026-08-10 · **Status:** Accepted · **Amends ADR-008**

**Context.** ADR-008 and `CLAUDE.md` name LiteLLM as "the only component permitted to call
Bedrock." That is a good default and a bad single point of failure. LiteLLM's own availability
and approval in the target partition is not established, its advisory history is substantial
(the M1b scan found repeated RCE, auth-bypass, and privilege-escalation advisories), and a proxy
the program has not approved is a deployment blocker we would discover late. Separately, nothing
in this project had ever actually called a model — the orchestration spike runs against a
deterministic stub, correctly, since all four bake-off legs are about control flow.

**Decision.** A `ModelGateway` port with two production adapters, selected by configuration:

| Adapter | Transport | Where the alias→model mapping lives |
|---|---|---|
| `litellm` (default) | Official Anthropic SDK pointed at LiteLLM's **Anthropic-native passthrough** (`{base}/anthropic`) | LiteLLM's config — outside our process entirely |
| `bedrock` | `anthropic.AnthropicBedrockMantle`, standard AWS credential chain, no proxy | Our environment (`IREPORTS_BEDROCK_MODEL_*`) |

A third adapter, `stub`, is offline and exists for contract tests only (ADR-009's "mock at the
gateway boundary"). It must never be selectable in a profile that produces reviewer-visible
findings.

**Both production adapters use the official `anthropic` SDK, and that is the load-bearing part.**
The obvious LiteLLM integration is its OpenAI-compatible surface, which would silently cost the
Anthropic request surface this architecture depends on: adaptive thinking, `output_config.effort`,
structured outputs, thinking blocks, and the `refusal` stop reason. LiteLLM also exposes an
Anthropic passthrough, so we keep the gateway *and* the real API. The Bedrock adapter uses the
SDK's Messages-API Bedrock client rather than a raw `bedrock-runtime` `converse` call for the same
reason — one request shape, one refusal path, no second place for decision-support behaviour to
drift.

**Consequences.**

1. **ADR-008 still holds, more strongly.** Application code names a tier; no model id reaches a
   contract. With the LiteLLM adapter no model id reaches our repository at all.
2. **A refusal can never become an empty finding.** Current models decline with HTTP 200 and a
   possibly-empty content list; the gateway raises rather than returning. For this system that is
   the highest-stakes error path — silent under-analysis that validates cleanly and reaches a
   reviewer looking like a clean result.
3. **No sampling parameters, anywhere.** `temperature`, `top_p`, and `top_k` are rejected by
   current models and are not configurable in this system. Reasoning depth is `effort` per tier.
4. **`ireports-fast` is low effort with thinking on, not thinking disabled.** Disabling thinking
   has two documented failure modes — a tool call written into visible text (the call silently
   never runs) and internal tags leaking into output. Neither is survivable for a system whose
   validators depend on structured output.
5. **No default model id exists.** A missing one is a startup error naming the variable. Q-01 is
   refused, not guessed; `.env.example` carries placeholders that fail loudly.
6. **New unverified risk.** The Mantle endpoint is `bedrock-mantle.{region}.api.aws`; whether it
   resolves in GovCloud is **unverified**, and GovCloud endpoints do not generally follow the
   commercial pattern. `IREPORTS_BEDROCK_BASE_URL` is the escape hatch; if the endpoint is absent
   there, the fallback is a `bedrock-runtime` adapter — real work to scope, not a flag. Folded
   into Q-01.

**Amended 2026-08-10 by ADR-017 and ADR-018**, both on evidence from the first live model call.
The decision stands; two of its implementation details were wrong.

---

## ADR-016 — `.env` reaches a process at entry points, never through a library

**Date:** 2026-08-10 · **Status:** Accepted

**Context.** `.env` was populated with working LiteLLM settings and the gateway still failed with
`adapter 'litellm' requires IREPORTS_LITELLM_BASE_URL`. Nothing in the repository loaded the file:
`GatewayConfig.from_env()` reads `os.environ`, `python-dotenv` was not a dependency, and `uv run`
does not read `.env` unless told to. The variable was set in a file nobody read.

**Decision.** Library code stays a pure consumer of `os.environ`. The file is loaded **explicitly,
at process entry points**. Two exist today:

| Entry point | Mechanism |
|---|---|
| The pytest session | `conftest.py` at the repository root calls `load_dotenv(..., override=False)` |
| Any other command | `uv run --env-file .env <command>` — first-class in the toolchain already in use |

When `apps/api` lands it becomes the third, loading in its own `main` rather than in a package
anything else imports. Docker Compose uses `env_file` for containers.

**Rejected: calling `load_dotenv()` inside `GatewayConfig.from_env()`.** It is the shortest fix and
the worst one. A library that reads a file relative to the current working directory acquires a
hidden dependency on where the process was started, and in Lambda there is no `.env` at all — so
local and deployed behaviour would diverge for reasons having nothing to do with configuration.
The gateway would also start behaving differently depending on which directory a test runner
happened to be invoked from.

**Rejected as the *only* mechanism: `set -a; source .env`.** Zero dependencies and perfectly
explicit, but it does not reach an IDE test runner, a pre-commit hook, or a CI step — which
reproduces exactly the failure above, silently. It remains fine as an ad hoc shell convenience.

**Consequences.**

1. `python-dotenv` is a **dev dependency, permanently.** Deployed environments (Lambda, ECS,
   Compose) get variables injected by the platform. Nothing in a shipped artifact reads a `.env`
   file, so the dependency never reaches a deployment.
2. **`override=False`.** A variable already present in the real environment beats the file. CI, a
   container, and a deployed function cannot be silently overridden by a `.env` on disk.
3. **Contract tests are isolated from it.** `tests/contract/conftest.py` strips every `IREPORTS_*`
   variable. A contract test whose result depends on an untracked local file is not evidence of
   anything, which is the one thing ADR-001 cannot tolerate.
4. `mypy` is configured to skip the root `conftest.py` — two files legitimately named `conftest.py`
   are a duplicate module to mypy, and the alternative fix (adding `__init__.py` across the test
   tree) changes module resolution for every existing test file.

---

## ADR-017 — LiteLLM's native Messages endpoint, and a per-tier override for shared proxies

**Date:** 2026-08-10 · **Status:** Accepted · **Amends ADR-015**

**Context.** The first live call against a real Bedrock-backed LiteLLM proxy failed two ways that
offline tests could not have caught. Evidence: `docs/handoff/compatibility-matrix.md` §6.

**Decision 1 — `IREPORTS_LITELLM_BASE_URL` is used verbatim; the gateway appends nothing.**

ADR-015 had the gateway append `/anthropic`, reaching for LiteLLM's *passthrough* route. LiteLLM
serves two routes that look interchangeable and are not:

| Route | What it is |
|---|---|
| `{base}/v1/messages` | LiteLLM's **native Anthropic-format endpoint** — accepts a Messages API request and routes it to any `model_list` entry, Bedrock included. What this architecture needs. |
| `{base}/anthropic/v1/messages` | **Passthrough to `api.anthropic.com`**, requiring the proxy to hold a first-party Anthropic credential. A Bedrock-backed proxy has none, so it forwards the caller's virtual key upstream and Anthropic returns `401 invalid x-api-key`. |

The failure presents as a bad key and is in fact a wrong route — and a gateway that rewrites the
operator's URL underneath them makes that near-undiagnosable. Passthrough remains reachable by
configuring `…/anthropic` deliberately.

**Decision 2 — an optional per-tier alias→model override for the LiteLLM adapter**
(`IREPORTS_LITELLM_MODEL_ORCHESTRATOR|THINKING|FAST`), defaulting to the identity mapping.

ADR-008 assumed LiteLLM's config is ours to write. The realistic case is a LiteLLM instance owned
by the organisation, fronting dozens of models for many teams, that does not carry
`ireports-thinking` and will not without a change-control ticket. Blocking the architecture on
another team's config file is not a design.

**ADR-008's invariant is untouched.** *Application code* names a tier; a node still writes
`ModelAlias.THINKING`. Only the place the tier is resolved moves — into our environment, exactly
where the `bedrock` adapter already keeps it. The identity mapping remains **preferred** and
remains the default: when the proxy carries our three names, no model identifier exists on our
side at all, and that is still the better arrangement.

**Consequences.** The ADR-015 claim "with the LiteLLM adapter no model id reaches our repository at
all" is now conditional on the proxy carrying our aliases. `docs/handoff/model-gateway.md` says so.

---

## ADR-018 — A requested schema is verified, not trusted

**Date:** 2026-08-10 · **Status:** Accepted · **Amends ADR-015**

**Context.** Measured against a live endpoint: `output_config.format` is accepted with **HTTP 200**
by every model group tested and **silently not enforced** by three of five. Where it is not
enforced the schema is neither applied nor rejected — the model answers in prose, wrapping the JSON
in a Markdown fence. The split does not follow Anthropic's documented model support, so it cannot
be predicted from a model name. Detail and the per-group table: `compatibility-matrix.md` §5.

**Decision.** When a `ModelRequest` carries a `response_schema`, the gateway parses the returned
text and raises `StructuredOutputError` if it is not JSON. The diagnostic reports shape — length,
and whether the text is fenced — and never the text itself, because a model asked to structure a
finding was by construction looking at case evidence and the error travels into logs and traces.

**Rejected: stripping the fence.** It is two lines and it would make the system appear to work. It
would also hide from the program team that schema enforcement is a per-model-group property rather
than a platform guarantee, and it would install a lenient parser that eventually accepts something
that is not a finding at all. `CLAUDE.md`: the model reasons; it does not decide whether its own
output is valid.

**Consequences.**

1. A tier mapped to a non-enforcing model group **fails loudly** on any structured request. That
   is the correct signal: choose an enforcing group, or make a recorded decision to repair.
2. This is the same failure class as ADR-015's refusal path, one layer out. A refusal must not
   become an empty finding; an unenforced schema must not become a prose finding. Both are silent
   under-analysis that validates cleanly and reaches a reviewer looking like a clean result.
3. Milestone 2 should surface a `StructuredOutputError` to the reviewer as an information gap,
   exactly as a refusal is meant to. The contracts already support it (`InformationGap`,
   `blocking=True`); wiring both is one job.
4. **Two request shapes documented as rejected were accepted** on this path (`temperature`,
   `thinking.budget_tokens`). Nothing in this system may rely on the endpoint rejecting a
   malformed request — the guard rails are ours.

**Partly superseded by ADR-019.** ADR-018's *mechanism* diagnosis was wrong — enforcement is not a
per-model-group property. Its *guard* stands and is now load-bearing for a different reason.

---

## ADR-019 — Structured output is a single tool call, and no tier needs Opus

**Date:** 2026-08-10 · **Status:** Accepted · **Supersedes the mechanism in ADR-015 and the
diagnosis in ADR-018**

**Context.** ADR-018 concluded that `output_config.format` was enforced by some model groups and
not others, and that the tier mapping therefore had to prefer Opus for anything structured. That
conclusion came from one trial per model. Repeated eight times per group, it does not survive:
`output_config.format` is unreliable **everywhere**, including Opus 4.8 (6 of 8). Sonnet 5,
Sonnet 4.6, and Haiku 4.5 were 0 of 8. Full tables: `docs/handoff/compatibility-matrix.md` §5.

The schema does reach the model — adding it raises `input_tokens` — so this is not the proxy
dropping a field. The mechanism simply is not binding on this path.

**Decision.** A `ModelRequest` carrying a `response_schema` is sent as **one tool**, and the
gateway returns that tool call's validated input as `ModelResponse.text`. `output_config.format`
is removed rather than kept alongside — two mechanisms competing to shape one response is worse
than the one that works.

Three fields are deliberately **not** sent, each because sending it breaks a tier we want:

| Not sent | Why |
|---|---|
| `strict: true` | Bedrock rejects it: `tools.0.custom.strict: Extra inputs are not permitted` |
| `tool_choice` (forced) | 400s with adaptive thinking on Sonnet 4.6 and Haiku 4.5: *"Thinking may not be enabled when tool_choice forces a specific tool"*. ADR-015 keeps thinking on for every tier, so forcing is unavailable |
| `output_config.format` | Measured unreliable on every group |

What remains is the least-specified configuration — one tool, model's choice, thinking on — and it
returned the exact expected input **20 of 20** across Opus 4.8, Sonnet 5, Sonnet 4.6, and Haiku 4.5.

**Consequences.**

1. **No tier requires an Opus-class model.** This was the practical blocker and it is gone. The
   development mapping is Sonnet 4.6 (orchestrator), Sonnet 5 (thinking), Haiku 4.5 (fast) — all
   three verified end to end. Opus 4.8 remains an escalation for the thinking tier if Milestone 3
   evaluation demands it, on evidence rather than by default.
2. **ADR-018's guard survives and matters more.** With `tool_choice` left to the model, a turn
   *could* answer in prose. It did not in 20 of 20 trials, but the gateway raises
   `StructuredOutputError` if no tool call comes back. "Did not occur" is not "cannot occur".
3. **We do not get the documented hard guarantee.** `strict: true` would make tool input
   schema-valid by construction; Bedrock refuses it. So tool input is best-effort and must still be
   validated through the Pydantic contracts downstream — which the architecture already does. Worth
   stating plainly rather than implying the tool path is airtight.
4. **The prompt now carries part of the contract.** The tool's description tells the model to call
   it exactly once and not to answer in prose. That is a prompt-shaped dependency in a system that
   otherwise keeps its guarantees in code, and it is the price of not being allowed to force the
   call.
5. **This is a per-endpoint finding.** A first-party Anthropic endpoint may well enforce
   `output_config.format` correctly. The decision is scoped to what was measured; re-run the live
   smoke check before assuming it transfers.

---

## ADR-020 — The buildable scope is an orchestrator spine; breadth moves to the handoff

**Date:** 2026-08-11 · **Status:** Accepted · **Amends the scope of ADR-003, ADR-007, ADR-010, and
ADR-012's carried conditions. Does not touch ADR-011 or ADR-014.**

**Context.** The roadmap that preceded this entry carried thirty-three requirements across nine
phases: a dual-adapter orchestration bake-off re-run at outcome level, checkpoint MAC hardening
with least-privilege database roles, local OpenSearch ingestion with embedding provenance,
authority routing across two approved policy packs, deterministic citation validators, a
transactional outbox against an ASAP mock, a dependency inventory, and a GovCloud gate.

Every one of those is defensible on its own terms. Together they answer a question the project was
not asked. ADR-001 fixes the deliverable as *a proven architecture and a handoff package*, and
`CLAUDE.md` names the risk that deliverable exists to retire: **the agentic orchestrator is harder
than it looks.** Breadth across authorities, retrieval infrastructure, and delivery plumbing does
not retire that risk — it spends the budget that would have.

The dual-adapter bake-off is the clearest case. It was added to re-test ADR-012 at outcome level
because Milestone 1c was a partial spike against a deterministic stub. But it multiplies every
downstream phase by two, and it re-opens a decision that was already made on measured evidence and
already protected structurally: nodes depend on our port, never on LangGraph, so the escape hatch
is the port, not a second implementation maintained in parallel.

**Decision.** The buildable scope is the orchestrator spine and nothing else:

> One command loads a synthetic case, fans out to bounded specialist sub-calls through the
> `ModelGateway` port on tier aliases, enforces budgets and loop limits in the deterministic shell,
> survives a crash mid-fan-out and resumes in a separate process without double-paying for an
> in-flight model call, pauses for a recorded human disposition, and emits a validated typed
> envelope.

Nine phases become three. What is cut is **not abandoned** — it is designed in the handoff package
and explicitly marked unbuilt, with the reason, per ADR-001's standing requirement that every claim
be cited or marked unverified.

| Cut | Requirements | Where it lives now |
|---|---|---|
| Second orchestration adapter and the outcome-level bake-off | ORCH-05, BAKE-01, ARCH-03, ARCH-05 | ADR-012 stands as decided; the port is the escape hatch |
| Checkpoint row integrity, least privilege, resume provenance | CKPT-01..03 | `docs/handoff/checkpoint-threat-model.md` §6, already written |
| OpenSearch retrieval, local ingest, embedding provenance | RETR-01..03, CONT-02 | Handoff; evidence is handed to the specialist from a synthetic fixture |
| Authority routing, two approved policy packs | ROUT-01..02 | Handoff; ADR-003's coverage decision is unchanged, its *implementation* is deferred |
| Evidence-citation validators | VAL-01 | Handoff; the finding contract still requires citations structurally |
| Transactional outbox, ASAP mock | DEL-01 | Handoff; ADR-010's envelope contract stands, its transport does not ship |
| Dependency inventory, GovCloud gate, `bedrock` live run | ARCH-02, HAND-02..03 | Handoff; Q-01 stays open and its cost is stated |

**What is explicitly retained, and why.**

1. **The human disposition gate (ADR-011) and the no-aggregate-score rule (ADR-014) are untouched.**
   Both were considered for the cut and both were kept. They are already structural in the thirteen
   shipped contracts with passing tests, so retaining them costs nothing — and cutting them would
   mean deleting working guardrails, which is not a simplification. Both remain NON-NEGOTIABLE.
2. **Crash and resume across a genuine process boundary.** Named non-negotiable. "Bounded-agentic"
   is a word rather than a claim if the run cannot survive a process death.
3. **Model-call idempotency (ORCH-02).** The most expensive retained item, and retained
   deliberately. A crash mid-fan-out currently re-runs an in-flight model call — measured 11 of 24
   trials under LangGraph, 12 of 24 hand-rolled, and owed by all three bake-off candidates while
   built by none. Durable orchestration of paid sub-calls is not proven if resuming double-pays.
4. **A refusal never becomes an empty result (VAL-02).** Nearly free — the gateway already raises
   `ModelRefusalError` — and it defends against the failure mode the project names as its worst:
   silent under-analysis that looks like a completed analysis.

**Consequences.**

1. **ADR-012 stands as decided and is no longer under re-test.** The outcome-level bake-off that
   would have judged it does not happen. The conditions ADR-012 carried forward are re-homed: nodes
   still depend on our port; LangSmith is still pinned closed and proven closed; the checkpoint blob
   is still a deserialization trust boundary. **Cold start under SAM local remains unmeasured, and
   now has no scheduled phase** — `spikes/test_scorecard.py` continues to fail the moment a figure
   is recorded, which keeps the gap visible rather than closing it by omission.
2. **The Strands amendment is moot.** Removing Strands from a mission bake-off that no longer exists
   needs no amendment. `spikes/` is retained in full per ADR-001 — all three candidates, all four
   legs, still running.
3. **Q-02 and Q-03 stop being build gates and become documented unknowns.** No local retrieval means
   no mapping module to mark PROVISIONAL and no embedding parity to check. Their blast radius is
   unchanged for whoever builds retrieval; what changes is that this project no longer proceeds
   under a working assumption about them. That is a smaller claim, honestly made.
4. **The handoff package carries more weight and less evidence.** More of it is design rather than
   demonstrated architecture. ADR-001's rule — a decision that cannot be demonstrated is a decision
   that has not been made — now applies to a larger share of the package, so the unbuilt sections
   must say plainly that they are unbuilt. This is the real cost of this decision and it is not
   hedged.
5. **Milestone 3 is unaffected.** It was already a placeholder gated on measurements, and the
   measurements it was gated on have narrowed.

---

## ADR-021 — Retrieval is part of the spine; the refusal path is a log line

**Date:** 2026-08-11 · **Status:** Accepted · **Amends ADR-020 (same day)**

**Context.** ADR-020 cut retrieval on the reasoning that evidence could be handed to the specialist
from a synthetic fixture, since bounded fan-out, budget exhaustion, and crash-mid-flight do not
depend on where the spans came from. That reasoning was wrong about what the architecture is. The
thing being demonstrated is *an orchestrator kicking off a sub-agent call that searches the case
record and returns policy findings with citations* — the search is not incidental to the sub-agent,
it is what the sub-agent does. A fixture-fed specialist demonstrates a fan-out, not this system.

Separately, ADR-020 retained VAL-02's full refusal path — a model refusal surfacing to the reviewer
as a blocking `InformationGap`. That is reviewer-workflow machinery, and this project is proving an
architecture rather than building the analysis product or evaluating model behaviour.

**Decision.**

1. **Retrieval returns to the spine, reduced.** Local OpenSearch in Docker, one synthetic case
   indexed, queried through the retrieval port. Every field name, filter, and facet mapping lives in
   one module marked PROVISIONAL against Q-02, per ADR-007's one-file containment rule.
   **RETR-01 and RETR-02 return to v1; RETR-03 stays cut** — embedding provenance and the parity
   check are model-evaluation work, and Q-03 remains a documented unknown rather than a build gate.
   **ADR-006 is untouched: vector and lexical search only, no graph database, in any milestone.**
2. **`SpecialistResult` carries no completion status.** It is the criterion analyzed, the provenance
   of the run, and the proposed findings with their citations. Nothing else.
3. **VAL-02 reduces from wired to logged.** The gateway already raises `ModelRefusalError` on
   `stop_reason` before touching content, so a refusal cannot become an empty string. The node
   catches it, logs it with `run_id`, `case_id`, and the criterion, and the orchestrator does no
   special routing. No `InformationGap` plumbing, no `blocking` flag, no review branch.

**Consequences.**

1. **Q-02 is a live containment concern again, and is still not cleared.** The mapping module must
   carry a header naming Q-02 and stating that the AWS collection's real schema is unconfirmed.
   Adapting to the real schema stays a one-file change. No document may imply the gate was cleared.
2. **The false-negative failure mode is now caught by logs rather than by contract.** A refused
   sub-agent produces a `SpecialistResult` with an empty findings list, which is indistinguishable
   at the artifact level from a criterion that came back clean. The distinction lives in the log.
   **This is a deliberate trade and it is the weakest point in the spine** — stated here so the
   handoff can carry it forward as a known gap rather than discovering it in production.
3. **`ChunkRecord` and `PolicyRecord` (CONT-02) stay cut.** The indexed record shape lives inside
   the retrieval package rather than being published as a domain contract. Publishing it would mean
   committing a schema against an unconfirmed collection (Q-02) for no consumer outside retrieval.

---

## ADR-022 — Human review happens in ASAP, not inside a run

**Date:** 2026-08-11 · **Status:** Accepted · **Supersedes ADR-011**

**Context.** ADR-011 modelled human review as an in-run pause: a run stops in
`AWAITING_HUMAN_REVIEW`, an authorized officer records a disposition, and the run resumes. Every
downstream artifact was built on that shape — two run states, a no-bypass transition table, the
`HumanDisposition` / `DispositionedFinding` / `ReviewSummary` contracts, and an `ASAPEnvelope`
whose `human_reviewed` field was pinned to `Literal[True]`.

**That is not the system.** iReports has no reviewer-facing surface and no human interaction of any
kind. It runs unattended, analyzes a case, and emits its output. Review happens afterwards, in
ASAP, by an officer using ASAP's own tooling. The pause this project built was a gate in front of a
door that does not exist here.

The confusion is understandable and worth recording, because the two things it conflated are both
real. There **is** human judgment involved in this project — but it is *validation*, not
*adjudication*: synthetic cases carry issues a human analyst already identified, and the measure of
the system is whether what iReports finds matches what the human found. That is an evaluation
activity performed against test data, not a step in a production run.

**Decision.**

1. **A run never waits for a human.** `AWAITING_HUMAN_REVIEW` and `REVIEW_RECORDED` are removed
   from `RunStatus`, along with the `human_review_recorded` flag and the `_delivery_requires_review`
   validator. A run proceeds from validation to packaging to delivered without stopping.
2. **iReports does not model disposition.** `HumanDisposition`, `DispositionedFinding`,
   `ReviewSummary`, `ApprovedFindingText`, `ReviewerRole`, `DispositionKind`, and `ReasonCode` are
   removed, with their generated schemas. What an officer decides, and how ASAP records it, is
   ASAP's contract to define — publishing our guess at it would invite a downstream system to
   implement against a shape we do not own.
3. **The envelope carries proposals, not approved findings.** `human_reviewed`,
   `human_disposition`, `reviewer_modified`, and `reviewer_summary` are removed from the
   `ASAPEnvelope`. An envelope is what iReports proposes for review — it is un-reviewed by
   construction, which is the opposite of what the pinned `Literal[True]` asserted.
4. **The decision-support boundary is unchanged, and its enforcement moves.** ADR-014 stands
   untouched: no aggregate score, no determination, in any contract, under any name. What changes
   is the mechanism. The boundary used to rest on two legs — a state-machine gate *and* the fact
   that everything emitted is a proposal. The gate is gone; the second leg now carries it alone,
   so it is strengthened rather than merely retained (see consequence 2).

**Rationale.** A gate that models a workflow the system does not have is worse than no gate. It
costs real complexity, it tells a reader the architecture does something it does not, and — most
seriously — it invites the handoff team to build a reviewer workflow into iReports that belongs in
ASAP. Removing it makes the boundary between the two systems sharper, not softer.

**Consequences.**

1. **Phase 3 changes content.** "Human gate, typed output, and the handoff" becomes validation and
   handoff: synthetic cases with analyst-identified issues, scorers that measure agreement between
   those and what iReports found, and the handoff package. REV-01 and REV-02 are withdrawn rather
   than cut — they describe a system that was never being built, so they are not owed a
   designed-not-built entry the way ADR-020's cuts are. This is recorded in `REQUIREMENTS.md`.
2. **The no-determination rule loses a redundant enforcement and must be tightened.** Under
   ADR-011, an envelope reaching ASAP had passed a structural gate. Now nothing structural stands
   between an analysis and ASAP except the shape of what is emitted. Two mechanisms therefore
   become load-bearing rather than supporting: `ProposedFinding` is the only finding type that
   exists, and `reject_determinative_language` guards every text field on the way out. Both were
   already built and tested; the point is that their failure is now unmitigated.
3. **We give up the ability to prove non-delivery of rejected findings.** ADR-011 let us assert, by
   walking a transition table, that a rejected finding could not reach ASAP. That assertion now
   belongs to ASAP and this project cannot make it. **This is a real reduction in what the handoff
   can claim**, and the package must say so rather than quietly dropping the claim.
4. **Contract count drops from 14 to 12** and `CONTRACT_VERSION` is bumped, because removing a
   published contract is a breaking change for any consumer that had started against it.

---

## ADR-023 — Lambda fit: one invocation per run, and the cold-start number that closes ARCH-03

**Date:** 2026-08-11 · **Status:** Accepted · **Closes ARCH-03 (cut by ADR-020)** · **Amends ADR-004**

**Context.** ADR-004 commits to AWS GovCloud with a Lambda/SAM adapter "built and exercised," but
nothing was ever built or exercised, and ADR-020 cut ARCH-03 — the cold-start measurement — leaving
the scorecard's largest hole open with no scheduled phase. Two questions had gone unanswered long
enough to be load-bearing:

1. **Does an orchestrator that fans out to sub-agents fit Lambda at all?** A 15-minute ceiling and
   a fan-out of paid model calls look like a bad match.
2. **Does LangGraph's dependency weight disqualify it on cold start?** The scorecard names this as
   the one outstanding measurement that could reopen ADR-012.

**Decision.**

1. **The target shape is one Lambda invocation per run, with in-process fan-out.** The orchestrator
   and its specialist sub-calls run inside a single invocation; LangGraph is a library executing in
   that process, and fan-out is async concurrency bounded by `max_parallel_specialists`. Step
   Functions with a Lambda per node is **rejected as the primary shape** — it moves control flow out
   of the framework ADR-012 selected and splits the deterministic shell across Python and ASL, which
   is a large cost to buy a ceiling this workload can already survive.
2. **The 15-minute ceiling is survived by the mechanism already owed, not by a new one.** ORCH-02
   requires that a crash mid-fan-out resume in a separate process without re-running an in-flight
   model call. **A Lambda timeout is that crash.** `max_wall_clock_seconds` is already a first-class
   budget on `Budgets`; the shell stops before the ceiling, checkpoints, and returns, and the next
   invocation resumes from the checkpoint. No new architecture is required — but note the
   dependency in consequence 3.
3. **LocalStack is permitted in an opt-in profile.** `CLAUDE.md` excludes it "in the default
   profile," which governs the everyday `pytest` loop and is unchanged. Proving the trigger chain
   (upload → extract → chunk → index → start analysis) needs service emulation that SAM local does
   not provide, and that is a legitimate opt-in.
4. **ARCH-03 is closed with a measurement, and ADR-012 stands.**

**The measurement** `[measured]` — `spikes/lambda_fit/`, SAM local, python3.12 arm64, 1024 MB,
reproducible via `measure_coldstart.py`:

| Candidate | Import (typical) | vs control | Unzipped | Zipped |
|---|---|---|---|---|
| hand-rolled | ~0.5 s | 1× | 30.1 MB | 9.1 MB |
| **langgraph** | **~1.6–2.3 s** | **~3×** | 68.9 MB | 19 MB |
| strands | ~1.5–1.8 s | ~3× | 79.7 MB | 34 MB |

**The precision here is lower than a stopwatch implies, and that is stated rather than smoothed.**
Three runs on the same machine gave LangGraph medians of 1.565 s, 1.974 s and 2.303 s, with samples
from 1.49 s to 5.78 s, as host load varied. The candidate ratio moved between 2.84× and 4.03×. An
early version of this entry quoted 1.565 s and 3.27× as though they were stable; they are a
low-load snapshot. **Package size is the load-independent number and is what Lambda limits are
checked against.**

The conclusion is robust across that whole spread, which is why the imprecision does not undermine
it: at the *worst* observed ratio and median, LangGraph costs roughly 1.5–1.8 s more per cold
start than a framework-free control.

**ADR-012 does not reopen.** LangGraph costs ~1.1 s more per cold start than a framework-free
control, on a workload where one specialist model call runs tens of seconds and cold starts occur
on scale-up rather than per request. Package size is comfortably inside both Lambda limits
(250 MB unzipped, 50 MB zipped). The dependency-weight objection was the strongest argument against
LangGraph and it does not survive contact with the number.

**What the number is not.** `sam local invoke` reports an `Init Duration` of ~0.05 ms for every
candidate; it does not emulate Lambda's init/invoke split and that field is meaningless. The figure
above is `import_seconds`, timed inside the handler module around the orchestrator import, on
macOS arm64 Docker. It is an **indicative comparison between candidates on identical footing**, not
a production cold-start figure `[unverified]` — a real one needs a deploy to Lambda, gated on Q-01
for GovCloud. Treat the *ratio* as the finding, not the absolute.

**Consequences.**

1. **Strands is the heaviest package at 79.7 MB unzipped / 34 MB zipped**, approaching the 50 MB
   zipped limit before any application code. Recorded because it constrains a candidate this
   project no longer plans to use, and a future reader may be considering it fresh.
2. **`spikes/lambda_fit/` is retained and runs in the suite**, like the other spikes. Its two
   guard tests assert the figures stay under a 3 s ceiling and that LangGraph stays within 5× the
   control — tripwires on the reasoning, not performance budgets.
3. **The timeout-resume proof is owed and not yet built.** Consequence 2 of the decision above is
   an argument, not a demonstration: it depends on ORCH-02, which is unbuilt and measured at 11/24
   duplicate paid calls for LangGraph today. **Under Lambda this is worse than on a laptop**,
   because Lambda retries automatically — a timeout without idempotency means paying for the same
   model calls again on every retry. Phase 2 (LAMB-01) proves it under Lambda semantics.
4. **The trigger chain is not ours and is not proven here.** Upload, extraction, chunking, and
   indexing belong to the AWS ingestion pipeline (ADR-007). What ADR-023 covers starts at "case is
   ready, start the analysis." How that invocation is triggered is an integration question for the
   handoff team, and Q-02 still gates what the index looks like when they get there.

---

## ADR-024 — Both orchestration paths stay live; the framework decision is deferred

**Date:** 2026-08-12 · **Status:** Accepted · **Amends ADR-012**

**Context.** ADR-012 selected LangGraph on 2026-08-11 — correctly, on the evidence it had: all
three candidates passed all four bake-off legs, and LangGraph cost two lines for durable
PostgreSQL checkpointing against 56 and 166 for the others. That was a decision about *cost at the
checkpointing seam*, made before any real analysis code existed.

Since then the runnable demo (`spikes/lambda_demo/`) has run real cases through **both** a
hand-rolled orchestrator and a LangGraph one, behind one port, sharing one specialist
implementation. Two things became visible that the bake-off could not show:

1. **The hand-rolled path is a thread pool and a loop.** For one invocation per run with
   in-process fan-out (ADR-023), the framework is not carrying much. LangGraph's advantage was
   concentrated in checkpointing, and checkpointing is not yet built.
2. **Keeping both costs almost nothing.** The port was built as insurance against lock-in. It
   turns out to be cheap enough to run as the actual arrangement — one shared specialist, two
   orchestrators, identical output shape.

> **Trigger fired 2026-08-18.** Crash/resume works on both paths and across a Lambda invocation
> boundary. The complete evidence and a recommendation are in **ADR-027**, recorded as *proposed*.
> This ADR stands until that one is accepted.

**Decision.** **Both paths stay live.** Custom Python and LangGraph are developed in parallel
behind this project's own orchestration port until there is a reason to choose — most likely when
crash/resume and model-call idempotency (ORCH-02) are built, since that is the seam where the
frameworks actually differ.

ADR-012 is **not reversed.** Its evidence stands and LangGraph remains the leading candidate. What
changes is that it is no longer treated as settled, and no code may assume it.

**Consequences.**

1. **The no-import rule is now the working arrangement, not lock-in insurance.** No module that
   analyzes a case may import LangGraph. This was previously a hedge; it is now load-bearing,
   because a second implementation genuinely runs. Enforced by
   `spikes/lambda_demo/test_demo.py::test_nodes_do_not_import_langgraph`.
2. **Every orchestration feature is owed by both paths.** Budgets, loop limits, fan-out bounds,
   and eventually checkpointing get built twice — or, better, built once in shared code that both
   orchestrators call. Where a feature is easy in one and hard in the other, *that is the finding*
   and it belongs in `docs/LESSONS.md`.
3. **The decision point is named, not open-ended.** Deferring forever is worse than choosing
   wrong. The call gets made when idempotent crash/resume works, because that is the capability
   the framework was selected for in the first place.
4. **Packaging stays separate per path.** Each is built with only its own dependencies, so neither
   inflates the other — `spikes/lambda_demo/build.py` already does this.

---

## ADR-025 — The specialist classifies its own findings; an empty findings array stays valid

**Date:** 2026-08-18 · **Status:** Accepted

**Context.** `specialist.py` set `classification=FindingClassification.POTENTIAL_ISSUE` as a
constant and the response schema never asked the model to classify. Two of the contract's five
values — `MITIGATING_INFORMATION` and `NO_ISSUE_IDENTIFIED` — were therefore unreachable from the
specialist path from the day it was written.

Nothing caught it, because every case run against the system had been built alongside it and
contained real concerns; on those records the constant is right most of the time. The first
deliberately clean case (`AMI-SYN-CLR-001`, 2026-08-17) produced seven findings whose analysis was
correct and whose labels were not — including one titled *"Criminal history and financial record
checks returned no indicators of criminal or dishonest conduct"*, delivered to a reviewer as a
`potential_issue`.

Fixing it surfaced a rule conflict that had been latent since the envelope contract was written.
The specialist prompt says an empty findings array is a good answer. `EnvelopeAnalysis.findings`
has `min_length=1`. On a genuinely clean record those cannot both hold, and a model with no way to
say "clean" will reach for the only classification it has.

**Decision.**

1. **The model classifies, from a constrained enum.** The schema offers a specialist three of the
   five values: `potential_issue`, `mitigating_information`, `no_issue_identified`. `contradiction`
   and `information_gap` remain synthesis's, which is competent to see across criteria and collects
   the fields those two require.
2. **An empty findings array stays valid.** A criterion with nothing relevant emits no finding. A
   wholly clean case therefore produces **no envelope**, and the run reports why.
3. **`no_issue_identified` is not the same as silence.** It asserts an absence the record
   *establishes* — a negative record check, a consistency review that found no discrepancy. Having
   nothing to say is `[]`.

**Why not always emit a `no_issue_identified` finding per criterion**, which would guarantee an
envelope: it changes what an envelope *is*, from a record of findings to a record of coverage.
That is a defensible design and it is a bigger decision than this one — it alters what every
downstream consumer receives, including ASAP. The run payload already reports per-criterion
coverage for anyone who needs it.

**Why not classify in code from the finding's shape.** A finding citing a span that supports a
*resolution* is structurally identical to one citing a span that supports a *concern*. The
difference is meaning, and meaning is what the model is for — deriving it from field occupancy
would be a heuristic dressed as determinism.

**Consequences.**

- **An empty envelope is still refused, and that is the point.** "Nothing found" is not a claim
  this system makes; the run says so and produces no artifact asserting it.
- **A missing or unrecognised classification defaults to `potential_issue` and is recorded as a
  rejection.** Dropping a good finding over a label would discard real analysis; defaulting
  silently is how the original bug survived. The finding ships, and the run says the label was not
  the model's answer.
- **`no_issue_identified` may cite nothing.** `ProposedFinding._material_claims_are_cited` already
  exempts assertions of absence, on the reasoning that requiring citations there pushes nodes
  toward citing irrelevant spans to satisfy a validator. The specialist's own "no resolvable
  supporting evidence — dropped" rule now carries the same exemption.
- **`prompt_version` moves to `specialist-v2`.** Two materially different prompts that share a
  provenance string are indistinguishable in the record.
- **`evals`' `classification_is_not_a_constant` stops failing** — but only once a corpus contains a
  record varied enough to warrant more than one value. It was the check that caught this, and it
  is worth keeping pointed at any enum a node chooses from.

## ADR-026 — Checkpointing is per path; the port shares a connection string and nothing richer

**Date:** 2026-08-18 · **Status:** Accepted

**Context.** Node-level checkpointing is what ORCH-01's remaining clauses and LAMB-01 both need,
and it is the feature ADR-012 chose LangGraph for. Building it meant deciding what, if anything,
the two orchestration paths share — every other capability so far has been shared framework-free
code both call, and idempotency (ORCH-02) turned out to belong at the gateway, where the paths
cannot differ at all.

That pattern does not extend here. The hand-rolled path needs a map of node id to result.
LangGraph needs a `BaseCheckpointSaver`, which also owns the graph's superstep bookkeeping — which
tasks are pending, which channel versions a checkpoint refers to, what a resume must re-dispatch.
Those are not two implementations of one interface. And `packages/orchestration/` may not name a
LangGraph type outside the adapter, which is enforced by a source scan.

**Decision.**

1. **`Checkpointing` carries one slot per path plus a shared `dsn`.** `store` is the hand-rolled
   `CheckpointStore`; `saver` is LangGraph's checkpointer, typed `Any` so the no-import rule holds;
   `dsn` is the only field both understand, and each adapter builds its own thing from it.
2. **The codec is shared and framework-free.** `checkpoint.py` encodes a `SpecialistOutcome` and a
   `SynthesisOutcome` to JSON and re-validates them through the ordinary contracts. Both paths use
   it — the LangGraph one is *obliged* to, see the consequences.
3. **Only work that happened is checkpointed.** `COMPLETED` and `REFUSED` are recorded; a refusal
   was paid for and ADR-015 forbids re-asking it. `SKIPPED_BUDGET` and `FAILED` are not.
4. **`durability="sync"` and strict deserialization are set in code**, as named module-level
   values with tests, not as environment variables. Both LangGraph defaults are wrong here and
   invisible when reading a graph.

**Why not a single `CheckpointStore` both paths implement**, with a LangGraph adapter behind it:
LangGraph's checkpointer is called by the framework's runner, not by our code, and it is handed
superstep state we have no meaning for. An adapter would have had to either discard that state — 
breaking resume — or invent a representation of it, which is writing a checkpointer to avoid using
one. The asymmetry is real and the port should show it rather than hide it.

**Why not skip the hand-rolled store and require LangGraph for durability:** that decides ADR-024
by omission. The comparison is the deliverable, and it needs both.

**Consequences.**

- **The framework-free codec is not optional on the LangGraph path either.** Under strict
  deserialization LangGraph does not refuse an unknown type — it returns a `dict`, on the resume
  path only. State channels and `Send` payloads therefore carry JSON. `PostgresSaver` saves us the
  *store*; it does not save us the codec, which is most of the interesting code.
- **A budget stop needs two different spellings.** The hand-rolled path returns a skipped outcome;
  the LangGraph node must *raise*, because there a returned value is what marks a task complete and
  a completed task is never re-dispatched. `run()` reconstructs the skipped outcomes afterwards so
  both paths report the same run.
- **The `Criterion` is not stored.** It is re-derived from the case and the stored `criterion_id`
  is checked against it, so a row cannot deliver one criterion's findings under another's authority.
- **Row integrity is still unaddressed**, and is now the largest known gap on two tables rather than
  one (`docs/handoff/checkpoint-threat-model.md`). Re-validating through the contracts catches a row
  that no longer satisfies them; it catches nothing about a tampered row that still parses.

## ADR-027 — The orchestration evidence is complete; a framework recommendation

**Date:** 2026-08-18 · **Status:** *Proposed* — the evidence is gathered, the call is the project
owner's · **Would supersede ADR-024, amending ADR-012**

**Context.** ADR-024 deferred the framework choice and named its own trigger: *"The call gets made
when idempotent crash/resume works, because that is the capability the framework was selected for
in the first place."* That works now. Model-call idempotency landed 2026-08-18 at the gateway;
node-level checkpointing landed the same day on both paths (ADR-026); and LAMB-01 proved both
across a real SAM invocation boundary.

This entry records what building items 1–7 twice actually measured. It is written as *proposed*
because the evidence being one-sided does not make the decision automatic, and a choice this size
should not be a side effect of the commit that gathered the evidence.

**The complete scorecard.** Seven comparison points, all measured, none argued.

| | Hand-rolled | LangGraph |
|---|---|---|
| Runtime fan-out width | No change — `pool.map` never cared | **Structural.** Rebuilt around `Send` |
| Fan-in barrier | Free — exiting the pool context | Free — supersteps. **Null result** |
| Conditional routing after fan-out | `if should_synthesize(...)` | A do-nothing `join` node; the naive version fires per dispatch on partial state and **fails silently** |
| `mypy --strict` | No change | Four suppressions; the documented `Send` pattern matches no `add_node` overload |
| Early termination on a budget | 3 lines | 3 lines, marginally cheaper. **Null result** |
| Node-level checkpointing | Ask, then tell — 4 lines, plus a store, an upsert and a read | `setup()` writes the schema **and**: a shared JSON codec is forced, the budget stop must raise rather than return, and **8 of 24 crash trials lost the write for a call already paid for**, against 0 |
| Resume across a Lambda boundary | 3 + 3 = 6 paid calls | 3 + 3 = 6 paid calls. **Null result** |

Plus one defect found only by looking: the `Send` fan-out was **unbounded** — 8 of 8 dispatches at
once — because `MAX_PARALLEL` only ever reached the `ThreadPoolExecutor`. Unbounded fan-out over
paid model calls is the failure budgets exist to prevent, and under Lambda a timed-out invocation
re-pays for the whole width.

**What ADR-012 expected, and what happened.** ADR-012 chose LangGraph because a PostgreSQL
checkpointer was two lines against 56 hand-rolled. That number was real and it did not survive
contact with a typed contract: `PostgresSaver.setup()` genuinely writes the schema, but strict
deserialization — which ORCH-01 *requires* — silently downgrades our types to `dict`, so both paths
need the same framework-free codec, and the codec is most of the code. **The first-party
checkpointer saves the store, not the codec.**

**Proposed decision.** Make **custom Python** the reference implementation, and keep the LangGraph
adapter as a conformance arm rather than removing it.

**Why not simply adopt LangGraph**, as ADR-012 leaned: on the one capability it was chosen for, it
is behind — it loses checkpoint writes a crash should not lose, and the mitigation
(`durability="sync"`) narrows the window without closing it, because the write happens outside the
node.

**Why not delete the LangGraph adapter.** It is what makes the no-import rule mean anything, it
costs one file, and it has earned its keep four times by making a silent failure loud. It should
stop being a candidate and start being a control.

**What would have reopened this — now closed.** ADR-024 named multi-step specialists alongside
crash/resume as the strongest signal available, and when this entry was first written they were not
built. **They were built on 2026-08-19 (roadmap item 6) and discriminated between the paths not at
all.** The loop lives inside `analyze`, which both orchestrators call, so neither can see it; the
one place it could have crossed the boundary was cancellation, and that needed the same
`raise`-instead-of-`return` treatment already recorded for budget stops. One asymmetry deepened,
none added — and `gather.py` recorded that prediction in its docstring *before* the measurement, so
the result cannot be read backwards.

So the evidence set ADR-024 asked for is complete. **An eighth row for the scorecard:**

| | Hand-rolled | LangGraph |
|---|---|---|
| A bounded loop inside a node | No change | No change. **Null result** |

What a framework would plausibly still win is a loop the *orchestrator* has to see — one whose
steps are separately checkpointable, so a crash mid-loop resumes mid-loop. That is a different
design, it costs the one-shared-specialist arrangement that makes these two paths comparable at
all, and nothing in this project needs it today.

**Consequences if accepted.**

1. `ORCHESTRATORS["hand-rolled"]` becomes the default everywhere the demo and the handoff describe
   a single path.
2. The no-import rule stays, and stops being provisional.
3. Every orchestration feature is still owed by both paths, because that is what keeps the control
   arm honest.
4. ADR-012 is amended, not erased: its reasoning was sound on the evidence it had, and the specific
   thing that changed is that the checkpointing seam turned out to be wider than two lines.

## ADR-028 — A specialist may search again; it may not do anything else

**Date:** 2026-08-19 · **Status:** Accepted

**Context.** A specialist got one query — the criterion's own text — and whatever it returned. That
is the right first version and it has a specific blind spot: evidence that answers the criterion in
different words is invisible. The criterion asks about "contacts with foreign nationals"; the record
says "my wife's parents live in Ankara". One hop, and one hop is exactly what a single query does
not make.

Roadmap item 6 closes that, and it is the first node in this system that can loop. That makes it
also the first place ORCH-03's no-progress detector and cancellation clauses mean anything, and the
first place `max_model_calls_per_node` can actually be reached.

**Decision.**

1. **The loop is retrieval only.** Retrieve → a cheap fast-tier call asking whether the record is
   sufficient and what is missing → retrieve again → analyse. The specialist gains no capability
   beyond re-querying the same `Retriever`.
2. **Seven named stop reasons**, not a boolean: sufficient, step limit, no progress, call budget,
   run budget, cancelled, assessor unavailable. Each is a different fact about how complete the
   criterion's evidence is.
3. **An unusable assessment stops the loop.** A refusal, a transport failure, unparseable output,
   off-schema output, or "insufficient" with no query to run — all stop gathering and analyse what
   round one found.
4. **`CANCELLED` becomes a fifth `SpecialistStatus`**, and cancellation is driven in Lambda by
   `context.get_remaining_time_in_millis()`.
5. **Gathering reserves the analysis's budget.** `calls_reserved` is subtracted from
   `max_model_calls_per_node` before the loop decides it can afford another round.

**Why retrieval only, and not a tool surface.** A tool-dispatching specialist would make SPEC-01's
allowlist clause *real* rather than vacuous, which is genuinely attractive — that clause is
currently unmet-by-absence and this repo says so rather than claiming it. It was declined because it
changes the threat model (a node choosing between capabilities is a different thing to secure than
a node that can only search), it is a larger piece of work than the loop it would ride in on, and
nothing in the analysis needs a second capability yet. When a specialist gains a tool, that wants
its own ADR and its own threat model.

**Why stopping is the fail-safe direction when the assessor breaks.** The alternative is to keep
querying when the thing that decides whether to keep querying is broken — paid calls on the strength
of an answer nobody got. Stopping costs the criterion nothing it would have had before the loop
existed: it is analysed on what round one retrieved, which is exactly what a single-step specialist
had.

**Why the triage call is on the fast tier.** Paying thinking-tier rates to decide whether to pay
thinking-tier rates is how a loop stops being worth having. It also bounds what the call sees —
600-character excerpts rather than whole chapters, because the question is "is this the right *kind*
of evidence" and the synthesis stage has already shown once what happens when a stage is handed more
than it needs (`max_tokens` exhausted while thinking, no text returned).

**Consequences.**

- **The value is unproven and the cost is not.** Two live runs: the assessor asked for more once in
  ten criteria, that refinement surfaced nothing new, and the loop cost roughly +50% tokens and 2.4×
  wall clock on the small case. `docs/ROADMAP.md` item 6 has the numbers. **Before this is defended
  it should be tuned and re-measured, or defaulted to `max_steps=1` and kept for cases that need
  it.** Recording that here rather than in a commit message, because the next person to look at this
  will otherwise assume it earns its keep.
- **`max_model_calls_per_node` changed meaning.** It used to be satisfied by a bounded retry — two
  calls against a limit of five. It is now a real ceiling on a real loop.
- **Every offline test that counts model calls had to learn the difference** between an analysis
  call and a triage sub-call. `node_id` carries it: an analysis call is the bare node id, a sub-call
  is suffixed.
- **SPEC-01 stays unchecked**, and its allowlist clause stays vacuous rather than satisfied.
