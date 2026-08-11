# Decisions Intel

Extracted from ADR-typed sources in the doc ingest. Two sources contributed:

- `docs/DECISIONS.md` — precedence 0, **LOCKED**. Nineteen numbered decisions, ADR-001..ADR-019, all `Accepted`.
- `docs/OPEN-QUESTIONS.md` — precedence 1, **not locked**. Fourteen questions, Q-01..Q-14, deliberately undecided.

`docs/DECISIONS.md` is self-declared authoritative for the whole project and beats `blueprint.md`
wherever the two diverge. That is a project rule stated in `CLAUDE.md`, not a preference.

Amendment chain, preserved rather than collapsed: ADR-015 amends ADR-008; ADR-017 and ADR-018 each
amend ADR-015; ADR-019 supersedes the structured-output *mechanism* in ADR-015 and the
per-model-group *diagnosis* in ADR-018, while ADR-018's `StructuredOutputError` guard survives.
ADR-012 moved Open → Accepted on 2026-08-11 and retains its original bake-off reasoning above its
Resolution section.

---

## LOCKED decisions — `docs/DECISIONS.md` (precedence 0)

### ADR-001 — The deliverable is a proven architecture, not a product
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: project deliverable, handoff package

The primary output is a handoff package: a defended architecture, decisions with recorded
reasoning, contracts, and evidence that the hard parts work. Runnable code is a means of proof, not
the deliverable. Handoff artifacts are built continuously, not written up at the end. Claims are
cited or explicitly marked unverified. Work producing a demo but no transferable finding is
deprioritized against work that settles a real question.

### ADR-002 — Standalone platform; AmiLens is prior art, not a dependency
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: repository boundaries, code reuse

Clean-slate build. No shared code, infrastructure, or submodules with `amilens-localdev`. AmiLens
remains valuable as prior art — its documented gaps (SEAD-4 conditions in the graph but never
queried; no RAG over policy at analysis time; no cross-referencing of subject statements against
investigator findings) are gaps this architecture is designed to close. Lessons transfer by being
written down, not by code reuse.

### ADR-003 — Suitability and SEAD-4, with authority routing from day one
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: authority coverage, routing engine

First release covers both 5 CFR part 731 suitability/fitness and SEAD-4 national-security
eligibility, with the authority-routing engine implemented — not stubbed. Two approved policy packs
at launch. Position designation and Fair Chance Act process controls are in scope. PIV/HSPD-12
credentialing is out of scope for the first release but must not be structurally excluded.

### ADR-004 — Local-first development, AWS GovCloud deployment target
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: deployment partition, local development topology

Develop against Docker Compose locally with Bedrock via LiteLLM as the only network egress. The
deployment target is AWS GovCloud, with the Lambda/SAM adapter built and exercised.

Open risk, treated as a hard gate rather than an assumption: Claude model availability, concrete
model and inference-profile IDs, cross-region inference restrictions, and data-routing rules in
GovCloud are unvalidated. Tracked as Q-01; must be validated before any GovCloud deployment work is
committed. GovCloud feature gaps must be checked per feature, never assumed from commercial AWS.

Note: the "via LiteLLM" wording predates ADR-015, which adds a direct `bedrock` adapter. See
`INGEST-CONFLICTS.md` INFO.

### ADR-005 — FastAPI is the boundary; no UI in Milestone 1
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: interface layer, UI

No Streamlit console — blueprint §4.1.2 is declined. FastAPI endpoints are the stable interface for
local use, the eventual production front end, and the Lambda adapter. Review happens through JSON,
contract tests, and the evaluation harness. The human-review *state machine* (ADR-011) is still
built and enforced; only its presentation is deferred.

### ADR-006 — No Neo4j
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: graph database

No graph database, in any milestone, until evidence demands one. Cross-document relationships and
timelines are served by structured entities and dated events in PostgreSQL plus OpenSearch
retrieval. Supersede only with a measurement showing graph traversal improves findings.

### ADR-007 — iReports queries an OpenSearch-compatible vector collection directly
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: retrieval architecture, embeddings

In AWS, iReports issues hybrid lexical + kNN queries directly against an AWS OpenSearch-compatible
vector collection **owned and populated by a separate ingestion and embedding pipeline**. iReports
is a consumer, not a producer. Local ingestion, chunking, and embedding are **development only**.

Assumed collection shape (unconfirmed, Q-02): a facet distinguishing case data from policy
knowledge, plus case-file metadata facets supplied by a `document.xml` sidecar applied after
ingestion.

Consequences: (1) embedding-model parity is a hard coupling — query-time model must match the
indexing model; a mismatch degrades retrieval silently, no error (Q-03); (2) all field names,
filters, and facet mappings isolated in a single mapping module so adapting is a one-file change
(Q-02); (3) the embedding provider sits behind an interface, and every vector records model
identifier and revision, dimension, normalization, input prefix, library version, and source text
hash; (4) local OpenSearch mirrors the assumed collection shape.

### ADR-008 — Three model tiers, referenced only by LiteLLM alias
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED · amended by ADR-015
scope: model routing, model references in application code

Application code never names a model. It names one of three aliases:
`ireports-orchestrator` (orchestration and control-flow reasoning), `ireports-thinking` (deep
criterion analysis, synthesis, challenge), `ireports-fast` (classification, extraction, mechanical
tasks). LiteLLM config maps aliases to concrete Bedrock model IDs, inference profiles, and regions.

On Bedrock, model IDs take an `anthropic.` prefix. The blueprint's named model (Claude Sonnet 4.6)
is not binding — newer models should be evaluated per tier. Pin the tested combination in a
compatibility matrix.

### ADR-009 — No offline run profile
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: run profiles, test strategy

The blueprint's "offline deterministic" profile (§3.1) is declined. No recorded-fixture provider,
no local LLM server. Bedrock access is required to run the system.

Accepted consequences: any test exercising a real model path is network-dependent,
non-deterministic, and costs money, so end-to-end runs cannot gate CI on every commit. Unit and
contract tests **mock at the gateway boundary** rather than relying on a run profile.
Reproducibility of a run is preserved through recorded run manifests (model alias, prompt version,
retrieval query IDs, configuration versions), not through replay.

### ADR-010 — ASAP delivery: versioned envelope with embedded evidence excerpts, against a local mock
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: ASAP delivery contract

The authoritative ASAP ingestion contract is unavailable. We define a versioned JSON envelope
carrying **bounded evidence excerpts plus stable references**, and build a local ASAP mock that
validates the schema and simulates status codes, timeouts, and retries. Delivery uses a
transactional outbox with idempotency keys and recorded receipts. The envelope is our proposal, not
an agreed interface (Q-04); contract tests pin our side so the delta is measurable.

### ADR-011 — Hard human-review gate, single reviewer role
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: human review, delivery gate

A run pauses in an explicit review state. One authorized reviewer role may accept, modify, or
reject each proposed finding. **Nothing reaches ASAP without a recorded disposition — there is no
bypass, in any profile, including local development.** Both the machine proposal and the approved
version are retained. Human review is a state transition, not a UI convention; a dev-mode
auto-approve flag is exactly the affordance that survives into production. End-to-end tests must
drive the review transition explicitly.

### ADR-012 — Orchestration framework: LangGraph
source: docs/DECISIONS.md · status: Accepted (2026-08-10, resolved 2026-08-11) · LOCKED
scope: orchestration framework

**Decision: LangGraph**, on the evidence in `docs/handoff/orchestration-scorecard.md` and the
retained spikes under `spikes/`.

Candidate set as amended by the Milestone 1b landscape scan: LangGraph, Strands Agents SDK,
hand-rolled Python. PydanticAI / Pydantic Graph dropped — Pydantic Graph 2.x has no
state-persistence API at all (verified at tag `v2.27.0`). This does not affect Pydantic v2 for
contracts. AutoGen and Semantic Kernel removed from consideration entirely (maintenance mode since
April 2026, merged into Microsoft Agent Framework), so blueprint §9.2 evaluates them as live
options when they are not.

All three candidates pass all four legs, so the decision is about cost, not correctness. LangGraph
selected because: durable checkpointing over PostgreSQL cost **two lines** with the first-party
`PostgresSaver`, against 56 for the hand-rolled store and 166 for the `SessionRepository` Strands
does not ship; net wiring is ~192 lines, below the hand-rolled floor of 195, while additionally
providing scheduling, a native interrupt, and declarative retry; it is the only candidate with a
written semver commitment, which is what a version-pinning, ATO-bound program most needs.

Hand-rolled is the recorded runner-up and the fallback if the dependency surface is refused.
Strands is dominated on every measured dimension except AWS alignment. Both spikes are retained.

Conditions carried forward, **not closed**:
- Cold start and packaging under SAM local were not measured for any candidate — the one number
  most likely to reopen the choice. `spikes/test_scorecard.py` fails the moment it is recorded.
- LangSmith stays pinned closed and proven closed. `langsmith` is a mandatory transitive dependency
  of `langchain-core`. Control is `langsmith.configure(enabled=False)` at the entry point, verified
  fail-closed, with a negative control showing an unpinned run POSTs ~90 KB of graph state including
  finding text to `api.smith.langchain.com` and **still succeeds** because the failure is swallowed.
  Any future entry point inherits this obligation.
- The checkpoint blob remains a deserialization trust boundary.
- **Nodes depend on our port, never on LangGraph directly.** This decision selects an
  implementation behind the port; it does not license `from langgraph import ...` in analysis code.

Two LangGraph defaults are wrong for this architecture and invisible in the code: `durability`
defaults to `async` rather than `sync`; checkpoint deserialization defaults to permissive. Both are
now set in code, with tests. A graph reads identically either way.

### ADR-013 — Interactive analysis, one case at a time
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: run model, latency

A single selected case analyzed on demand, results in minutes. No batch queue in the first
milestone. Design for responsiveness and streaming run status. The run model must not assume a
single in-process execution — checkpointing and resume are required regardless. Working assumption
~5–25 documents and a few hundred pages per case (Q-05).

### ADR-014 — No universal person-risk score
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: contracts, prohibited fields

**No contract carries an aggregate risk score, risk level, or overall recommendation field.**
Findings are per-criterion, per-authority, evidence-backed, and individually dispositioned. A
single score collapses distinct legal authorities into a number that invites exactly the deference
the decision-support boundary prohibits, and it is the field most likely to be extracted downstream
and used as a determination. Schema review must reject any field that functions as an aggregate
score, whatever it is named.

### ADR-015 — Two model-gateway adapters behind one port; both use the Anthropic SDK
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED · amends ADR-008
scope: model gateway

A `ModelGateway` port with two production adapters selected by configuration: `litellm` (default,
official Anthropic SDK pointed at LiteLLM; alias→model mapping lives in LiteLLM's config) and
`bedrock` (`anthropic.AnthropicBedrockMantle`, standard AWS credential chain, no proxy; mapping in
our environment). A third adapter, `stub`, is offline and exists for contract tests only — it must
never be selectable in a profile that produces reviewer-visible findings.

**Both production adapters use the official `anthropic` SDK, and that is the load-bearing part.**
The obvious LiteLLM integration is its OpenAI-compatible surface, which would silently cost
adaptive thinking, `output_config.effort`, structured outputs, thinking blocks, and the `refusal`
stop reason.

Consequences: (1) ADR-008 still holds, more strongly; (2) **a refusal can never become an empty
finding** — models decline with HTTP 200 and a possibly-empty content list, so the gateway raises
rather than returning; (3) **no sampling parameters, anywhere** — `temperature`, `top_p`, `top_k`
are not configurable; reasoning depth is `effort` per tier; (4) `ireports-fast` is low effort with
thinking ON, not thinking disabled; (5) **no default model id exists** — a missing one is a startup
error naming the variable; Q-01 is refused, not guessed; (6) the Mantle endpoint
`bedrock-mantle.{region}.api.aws` is unverified in GovCloud, folded into Q-01.

The `{base}/anthropic` passthrough detail in this ADR was corrected by ADR-017; the
`output_config.format` structured-output mechanism was superseded by ADR-019.

### ADR-016 — `.env` reaches a process at entry points, never through a library
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED
scope: configuration loading

Library code stays a pure consumer of `os.environ`. `.env` is loaded **explicitly, at process entry
points**: the pytest session (root `conftest.py`, `load_dotenv(override=False)`) and
`uv run --env-file .env <command>`. `apps/api` becomes the third when it lands, loading in its own
`main`. Docker Compose uses `env_file`.

Rejected: `load_dotenv()` inside `GatewayConfig.from_env()` — a library reading a file relative to
cwd acquires a hidden dependency on where the process started, and in Lambda there is no `.env` at
all. Rejected as the only mechanism: `set -a; source .env` — does not reach an IDE test runner, a
pre-commit hook, or a CI step.

Consequences: `python-dotenv` is a **dev dependency, permanently** — nothing in a shipped artifact
reads a `.env`. `override=False` so a real environment beats the file. `tests/contract/conftest.py`
strips every `IREPORTS_*` variable — a contract test depending on an untracked local file is not
evidence of anything.

### ADR-017 — LiteLLM's native Messages endpoint, and a per-tier override for shared proxies
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED · amends ADR-015
scope: model gateway routing, alias resolution

**Decision 1** — `IREPORTS_LITELLM_BASE_URL` is used verbatim; the gateway appends nothing.
`{base}/v1/messages` is LiteLLM's **native Anthropic-format endpoint** and is what this
architecture needs. `{base}/anthropic/v1/messages` is **passthrough to `api.anthropic.com`**,
requiring a first-party Anthropic credential the Bedrock-backed proxy does not have; it returns
`401 invalid x-api-key`. The failure presents as a bad key and is in fact a wrong route.

**Decision 2** — an optional per-tier alias→model override for the LiteLLM adapter
(`IREPORTS_LITELLM_MODEL_ORCHESTRATOR|THINKING|FAST`), defaulting to the identity mapping. The
realistic case is an organisation-owned LiteLLM that does not carry `ireports-thinking` and will
not without a change-control ticket.

**ADR-008's invariant is untouched.** Application code names a tier; only the place the tier is
resolved moves. Identity mapping remains preferred and default. Consequence: ADR-015's claim "no
model id reaches our repository at all" is now conditional on the proxy carrying our aliases.

### ADR-018 — A requested schema is verified, not trusted
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED · amends ADR-015 · partly superseded by ADR-019
scope: structured output validation

When a `ModelRequest` carries a `response_schema`, the gateway parses the returned text and raises
`StructuredOutputError` if it is not JSON. The diagnostic reports **shape only** — length, and
whether the text is fenced — and never the text itself, because a model asked to structure a
finding was by construction looking at case evidence and the error travels into logs and traces.

Rejected: stripping the Markdown fence. Two lines, and it would make the system appear to work
while installing a lenient parser that eventually accepts something that is not a finding at all.

Consequences: a tier mapped to a non-enforcing model group fails loudly. This is the same failure
class as ADR-015's refusal path, one layer out — a refusal must not become an empty finding; an
unenforced schema must not become a prose finding. Milestone 2 should surface
`StructuredOutputError` to the reviewer as an `InformationGap` (`blocking=True`). Two request
shapes documented as rejected were accepted on this path (`temperature`, `thinking.budget_tokens`)
— **nothing may rely on the endpoint rejecting a malformed request; the guard rails are ours.**

ADR-018's *mechanism diagnosis* was wrong (enforcement is not a per-model-group property). Its
*guard* stands and is now load-bearing for a different reason.

### ADR-019 — Structured output is a single tool call, and no tier needs Opus
source: docs/DECISIONS.md · status: Accepted (2026-08-10) · LOCKED · supersedes the mechanism in ADR-015 and the diagnosis in ADR-018
scope: structured output mechanism, tier mapping

Repeated eight times per group, `output_config.format` is unreliable **everywhere**, including
Opus 4.8 (6 of 8). Sonnet 5, Sonnet 4.6, and Haiku 4.5 were 0 of 8. The schema does reach the model
(adding it raises `input_tokens`), so this is not the proxy dropping a field.

**Decision.** A `ModelRequest` carrying a `response_schema` is sent as **one tool**, and the
gateway returns that tool call's validated input as `ModelResponse.text`. `output_config.format` is
removed rather than kept alongside.

Three fields deliberately **not** sent: `strict: true` (Bedrock rejects it), forced `tool_choice`
(400s with adaptive thinking on Sonnet 4.6 and Haiku 4.5, and ADR-015 keeps thinking on for every
tier), and `output_config.format` (measured unreliable everywhere). What remains is the
least-specified configuration — one tool, model's choice, thinking on — and it returned the exact
expected input **20 of 20** across Opus 4.8, Sonnet 5, Sonnet 4.6, and Haiku 4.5.

Consequences: (1) **no tier requires an Opus-class model** — development mapping is Sonnet 4.6
(orchestrator), Sonnet 5 (thinking), Haiku 4.5 (fast), all verified end to end; Opus 4.8 remains an
escalation for the thinking tier on evidence, not by default; (2) ADR-018's guard survives and
matters more; (3) `strict: true` is unavailable, so tool input is best-effort and must still be
validated through Pydantic contracts downstream; (4) the tool's description carries part of the
contract (call once, do not answer in prose) — a prompt-shaped dependency, and the price of not
being allowed to force the call; (5) this is a **per-endpoint finding** — re-run the live smoke
check before assuming it transfers.

---

## Open items — `docs/OPEN-QUESTIONS.md` (precedence 1, NOT locked)

Nothing in this file is decided. Every entry is explicitly open; several carry only a stated
working assumption. Consolidated from `blueprint.md` §"Questions that should be resolved during
Phase 0" and §19, minus items settled in `DECISIONS.md`.

### GATE items — must be answered before the work they block starts

**Q-01 · Claude model availability in AWS GovCloud** — source: docs/OPEN-QUESTIONS.md
- Blocks: any GovCloud deployment work; the LiteLLM production configuration.
- Assumption: **none — this is the one item the project refuses to assume.**
- Blast radius: high. Model availability, concrete model and inference-profile IDs, cross-region
  inference restrictions, and data-routing rules are unvalidated. If the intended model is
  unavailable in the approved partition, the ADR-008 tier strategy needs different targets and the
  evaluation baseline moves.
- Two endpoint questions ride on it (ADR-015): whether `bedrock-mantle.{region}.api.aws` resolves
  in GovCloud, and whether a LiteLLM proxy is permitted in the approved environment.
- **Partial evidence 2026-08-10 covers the COMMERCIAL partition only; the gate stays shut.** A
  commercial-partition result is not evidence about GovCloud. The `bedrock` adapter has still never
  been run in any partition.
- To resolve: run the live smoke check in the target GovCloud account and region and append the
  result to `docs/handoff/compatibility-matrix.md` as a **second** run-of-record, alongside the
  commercial one rather than replacing it.

**Q-02 · AWS vector collection schema and field mapping** — source: docs/OPEN-QUESTIONS.md
- Blocks: finalizing the retrieval mapping module and the local OpenSearch index definition.
- Assumption: single collection with a facet separating case data from policy knowledge, plus
  case-file metadata facets applied post-ingestion via a `document.xml` sidecar (ADR-007).
- Blast radius: medium and deliberately contained — one-file change. Becomes high only if the real
  shape is structurally different (separate collections per corpus, or nested/parent-child docs).
- To resolve: obtain actual index mappings from the ingestion team — field names, vector dimension,
  similarity metric, filterable metadata fields.

**Q-03 · Query-time embedding parity** — source: docs/OPEN-QUESTIONS.md
- Blocks: any claim that retrieval quality measured locally predicts retrieval quality in AWS.
- Assumption: pin a local model, treat parity as unverified until confirmed.
- Blast radius: **high and silent.** A mismatch does not error — it just retrieves worse, and every
  downstream evaluation number becomes meaningless without anyone noticing.
- To resolve: get exact model identifier, revision, dimension, normalization, and any input prefix
  from the ingestion team; build a parity test that fails loudly on drift. Ask whether they can
  expose an embedding endpoint — that removes the coupling entirely.

### Contract and integration

**Q-04 · Authoritative ASAP ingestion contract** — assumption: our versioned envelope with embedded
excerpts plus references (ADR-010). Blast radius medium, contained to the delivery adapter and
envelope schema. Unknown: endpoint and auth, idempotency semantics, error and retry contract,
attachment handling, whether ASAP stores excerpts or only references and findings.

**Q-05 · Case scale and volume** — assumption ~5–25 documents, a few hundred pages per case,
single-case interactive (ADR-013). Blast radius low for architecture, high for capacity planning;
checkpointing and resume are built regardless, so a volume surprise means adding a batch queue
rather than reworking the run model.

**Q-14 · Is Amazon Bedrock AgentCore an approved deployment target?** — raised by the Milestone 1b
scan, 2026-08-10. Assumption: no; ADR-004 stands and the Lambda/SAM adapter gets built and
exercised. Blast radius low for M1, medium for deployment — AgentCore is a managed agent runtime,
not a Python orchestration library, so it does not change the M1 bake-off; it changes what the
Lambda adapter is *for*. Reached GovCloud (US-West) 2026-05-05. Documented GovCloud gaps: no
semantic search in AgentCore Gateway; AWS Agent Registry (Preview), Bedrock Guardrails Policy, and
Temporal Policy unavailable; six CloudFormation resource types absent including `Policy`,
`PolicyEngine`, `Evaluator`. Its export-control section states AgentCore metadata may not contain
export-controlled data and enumerates configurations under which data-plane traffic leaves the
GovCloud partition — for a system carrying CUI that is a design constraint, not boilerplate.
**Read alongside Q-01, not as an answer to it.**

**Q-06 · Agency supplemental fitness factors and precedent material** — assumption: federal-core
policy pack only (5 CFR 731 factors, SEAD-4 guidelines). Blast radius low structurally; changes
content scope and the evaluation set.

### Governance and policy ownership

These do not block engineering but must be answered before a pilot with real data.

**Q-07 · Policy ownership** — which office approves machine-readable policy interpretations,
summaries, decision tables, and supersession. The design fails closed when a policy pack is expired
or unapproved, which is only meaningful if an approver exists.

**Q-08 · Data environment rules** — what synthetic, de-identified, and production data each
environment may contain; data impact level, CUI category, privacy controls, records schedules.
Assumption for this repo: **synthetic only, always.**

**Q-09 · Records retention** — retention schedule for evidence snapshots, model responses, reviewer
edits, run manifests. Affects storage design and audit trail, not the analysis path. Ties to the
unbuilt checkpoint retention/pruning control.

**Q-10 · Performance thresholds and error tolerances** — acceptable precision/recall and
false-positive/false-negative rates per criterion. The evaluation harness can be built without
these; release gates cannot be set until an adjudication business owner sets them.

**Q-11 · Appeal and contestability** — what subject-facing or reviewer-facing correction process
must be supported.

**Q-12 · Production support ownership** — who owns policy incidents, model incidents, data
incidents, ASAP delivery failures.

**Q-13 · Prompt caching approval** — is prompt caching approved for this data class and provider
configuration. Material to cost, immaterial to correctness. Caching is not enabled pending this.

### Resolved-question map (blueprint question → ADR)

Scope order → ADR-003 · Deployment partition → ADR-004 (with Q-01 outstanding) · Latency target →
ADR-013 · ASAP evidence model → ADR-010 · Human review roles → ADR-011 · Local model /
disconnected operation → ADR-009 · Graph database → ADR-006 · Embedding strategy → ADR-007 · Model
routing → ADR-008 · Workflow engine → ADR-012 · Universal risk score → ADR-014 · Docker Desktop
permitted → assumed yes under ADR-004.
