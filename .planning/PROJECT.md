# asap-ireports

## What This Is

A local-first, bounded-agentic case-analysis platform for US federal suitability, fitness, and
national-security eligibility adjudication. It organizes case evidence, identifies evidence-backed
potential concerns and mitigating information, surfaces contradictions and information gaps, and
packages the result for the ASAP front-end workflow — **for review by an authorized officer, never
as a determination.**

**The deliverable is a proven architecture and a handoff package for the ASAP program team, not a
product** (ADR-001). Code exists to make architectural claims verifiable. A decision that cannot be
demonstrated is a decision that has not been made.

## Core Value

One command takes a synthetic case to a delivered, **human-approved** iReport, with every seam
exercised once and every claim in the handoff package either cited or explicitly marked unverified.

## Requirements

### Validated

<!-- Shipped, verified, and recorded in a handoff document. -->

- ✓ Thirteen data contracts as Pydantic v2 models with generated JSON Schema — `packages/domain/`,
  `schemas/`, `docs/handoff/contracts.md` (Milestone 1a, 2026-08-10)
- ✓ `ModelGateway` port with `litellm`, `bedrock`, and `stub` adapters —
  `packages/gateway/`, `docs/handoff/model-gateway.md` (2026-08-10)
- ✓ First live model call; tier mapping measured on the commercial partition —
  `docs/handoff/compatibility-matrix.md` (2026-08-10)
- ✓ Orchestration landscape scan — `docs/handoff/orchestration-landscape.md` (Milestone 1b, 2026-08-10)
- ✓ Four-leg orchestration bake-off across three retained candidates; ADR-012 Accepted —
  `spikes/`, `docs/handoff/orchestration-scorecard.md` (Milestone 1c, 2026-08-11)
- ✓ LangSmith egress-deny test with a negative control — `spikes/langgraph/test_langsmith_egress.py`
- ✓ Framework-independent checkpoint threat model — `docs/handoff/checkpoint-threat-model.md`

### Active

Full list with IDs and acceptance in `.planning/REQUIREMENTS.md`. Summary:

- [ ] Close Milestone 1a — component-architecture write-up, library inventory, cold-start
      measurement, `SpecialistResult`, `mypy --strict` clean (ARCH-01..04, CONT-01, QUAL-01)
- [ ] Orchestration spine on LangGraph behind our own port, with model-call idempotency, budget
      enforcement, and LangSmith pinned closed at every entry point (ORCH-01..04, QUAL-02)
- [ ] Checkpoint hardening — row integrity, least privilege, resume provenance (CKPT-01..03)
- [ ] Case evidence in and retrieval through the port, PROVISIONAL under Q-02 (RETR-01..03, CONT-02)
- [ ] Authority routing selects the policy pack, explicit decision per authority (ROUT-01..02)
- [ ] One specialist produces validated proposed findings against one criterion (SPEC-01, VAL-01..02)
- [ ] Human review gate and ASAP delivery through the outbox (REV-01..02, DEL-01..02)
- [ ] Handoff package current, and the Q-01 GovCloud gate closed or its cost recorded (HAND-01..03)

### Out of Scope

- **Any final adjudicative determination** — grant, deny, revoke, suspend, credential. The
  decision-support boundary is the mission constraint; the system identifies issues for an
  authorized officer.
- **Universal person-risk score, aggregate risk level, or overall recommendation field** — ADR-014.
  A single score collapses distinct legal authorities into a number that invites exactly the
  deference the boundary prohibits.
- **Cross-case personality profiling and generalized predictive scoring** — blueprint §1.3.
- **Real case data, anywhere** — no fixtures, no tests, no examples. Synthetic only, ever.
- **Neo4j or any graph database** — ADR-006. Supersede only with a measurement showing graph
  traversal improves findings.
- **Streamlit or any UI** — ADR-005. FastAPI + JSON + contract tests are the interface. The human
  review *state machine* is still built and enforced; only its presentation is deferred.
- **Offline run profile, recorded-fixture provider, local LLM server** — ADR-009. Bedrock access is
  required to run the system; unit and contract tests mock at the gateway boundary instead.
- **LocalStack in the default profile** — CLAUDE.md.
- **Shared code, infrastructure, or submodules with `amilens-localdev`** — ADR-002. AmiLens is prior
  art; lessons transfer by being written down, not by code reuse.
- **Batch queue** — ADR-013, single-case interactive in the first milestone. Checkpointing and resume
  are built regardless, so a volume surprise means adding a queue rather than reworking the run model.
- **PIV/HSPD-12 credentialing analysis** — ADR-003, out of the first release but must not be
  structurally excluded.
- **Bedrock AgentCore as a deployment target** — Q-14 working assumption is no; ADR-004 stands.
- **Milestone 3 decomposition** — `docs/ROADMAP.md` deliberately withholds ordering and exit
  criteria and says "Sequence this from M2 findings — not from this list." Carried as a named
  placeholder, gated on M2 measurements. See `.planning/ROADMAP.md`.

## Context

**Where the work stands (2026-08-11).** Milestone 1b and 1c are complete. Milestone 1a is partially
complete: the thirteen contracts are done and ready for sign-off; **the component-architecture
write-up is outstanding and is the last item blocking program sign-off on 1a.** Milestone 2 has not
started. Milestone 3 is an explicit placeholder.

**Repo health (2026-08-11):** 111 tests passing, 8 skipped (the 8 are opt-in live-model checks,
`IREPORTS_LIVE_SMOKE=1`). `ruff` clean. `mypy --strict` reports 15 errors, **all pre-existing and all
confined to `tests/contract/`** — none in `packages/`, none in `spikes/`. `pip-audit` reports no
known vulnerabilities over the pinned set.

**The orchestration decision is settled and the reasoning matters.** All three bake-off candidates
passed all four legs, so ADR-012 turned on cost, not correctness: durable checkpointing over
PostgreSQL cost two lines with LangGraph's first-party `PostgresSaver`, against 56 hand-rolled and
166 for a `SessionRepository` Strands does not ship. Hand-rolled is the recorded runner-up and the
fallback if the dependency surface is refused. Both losing spikes are retained and still run in the
suite. Cold start under SAM local was never measured for any candidate and is the one number most
likely to reopen the choice — `spikes/test_scorecard.py` fails the moment a figure is recorded.

**`blueprint.md` is the project's INPUT, not its output.** It is deliberately lowest precedence.
Wherever it conflicts with `docs/DECISIONS.md`, DECISIONS.md wins, and the divergence is recorded
rather than dropped.

**Three GATE questions are open.** Q-01 (Claude model availability in GovCloud) refuses any working
assumption and all model evidence to date is commercial-partition only. Q-02 (AWS vector collection
schema) proceeds under a working assumption with the mapping module marked PROVISIONAL — contained
by ADR-007, **not cleared**. Q-03 (query-time embedding parity) is high blast radius and silent: a
mismatch does not error, it just retrieves worse.

**Evidence-tag vocabulary travels with every quoted claim** in the handoff docs: `[measured]`,
`[first-party]`, `[secondary]`, `[judged]`, `[unverified]`.

## Constraints

### Hard constraints — NON-NEGOTIABLE

These are enforced structurally, in code and tests, not by policy statement. If a change would
violate one, stop and raise it.

- **Decision-support boundary**: the system must **never** grant, deny, revoke, suspend, or
  otherwise make a final suitability, fitness, credentialing, or national-security eligibility
  determination — it identifies evidence-backed issues for review by an authorized officer.
  Enforced by `DecisionSupportText`'s `AfterValidator` on every narrative field a model writes into.
  It is a guard, not a proof; the human review gate is the actual control.
- **No aggregate score**: no universal person-risk score, no aggregate risk level, no overall
  recommendation field, on **any** contract, whatever it is named (ADR-014). A test walks every
  published schema following `$defs` and rejects such a property. Known drift risk: `ReviewUrgency`
  is a per-finding sequencing hint and is never aggregated.
- **Human disposition gate**: nothing reaches ASAP without a recorded human disposition. No bypass,
  in any profile, **including local development**. It is a state transition, not a config flag
  (ADR-011). Both the machine proposal and the approved version are retained.
- **Models by alias only**: application code names one of three tiers — `ireports-orchestrator`,
  `ireports-thinking`, `ireports-fast` — never a model id, in any application code
  (ADR-008 / ADR-017). Concrete model ids, inference profiles, and regions live in configuration; a
  partition change must be a config change.
- **Evidence before inference**: every material factual statement in a finding carries a resolvable
  citation to a case evidence span; every policy-relevance claim carries a resolvable policy
  citation. Deterministic validators reject unsupported citations **before a human ever sees them**.
- **Deterministic shell around probabilistic reasoning**: schema validation, citation validation,
  authority routing, policy-pack effectivity, and loop/termination limits are ordinary code. The
  model reasons; **it does not decide control flow, and it does not decide whether its own output is
  valid.** A node at a budget ceiling emits `INCOMPLETE_DUE_TO_BUDGET`, which routes to human review
  rather than to failure.
- **Synthetic data only, ever**: no real case data in this repo — not in fixtures, not in tests, not
  in examples. `DataClassification` has exactly one member.
- **Raw case text never in logs, traces, or error messages**: traces carry identifiers (`case_id`,
  `run_id`, `node_id`), versions, and outcomes. Evidence text lives in access-controlled stores only.
  The `StructuredOutputError` diagnostic reports shape only — length, and whether the text is fenced.

### Architecture constraints

- **PostgreSQL is the system of record** for workflow state. OpenSearch is a retrieval index and is
  never authoritative for findings, dispositions, or run state.
- **Retrieval goes through the port, never a raw client.** Every OpenSearch field name, filter, and
  facet mapping lives in **one mapping module**, so adapting to the real AWS collection schema is a
  one-file change (ADR-007, Q-02).
- **Orchestration goes through our own port.** Analysis nodes depend on this project's orchestration
  port, never on LangGraph directly. ADR-012 selects an implementation behind the port; it does not
  license `from langgraph import ...` in analysis code.
- **The model gateway port is the only component permitted to call a model.** Two production
  adapters (`litellm` default, `bedrock` direct), both on the official `anthropic` SDK. The `stub`
  adapter must never be selectable in a profile that produces reviewer-visible findings.
- **The checkpoint is a deserialization trust boundary.** Everything crossing it is untrusted input,
  even though the store is our own PostgreSQL. Plain JSON built from Pydantic contracts,
  re-validated on load; `JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)`
  constructed strictly in code; never `pickle`. LangGraph's `durability` must be set `sync` and
  deserialization set strict — both defaults are wrong here and **invisible in the code**.
- **Run ids are server-generated, never client-supplied.** `PostgresSaver` truncates `thread_id` at
  a length-limited column, so a truncating id scheme could *create* cross-run collisions.
- **Routing is never inferred.** `RoutingBasis` has no `INFERRED` member; missing metadata produces
  `BLOCKED_MISSING_METADATA` with a required `blocking_gap`. `AuthorityRoutingResult` requires an
  explicit decision for **every** authority, including those that do not apply.
- **Policy fails closed.** `PolicyPackRef` refuses to construct unless `status == APPROVED`;
  effectivity is a date comparison in code.
- **No sampling parameters, anywhere.** `temperature`, `top_p`, `top_k` are not configurable.
  Reasoning depth is `effort` per tier (orchestrator `medium`, thinking `high`, fast `low`).
  `ireports-fast` is low effort with thinking **ON**, not thinking disabled. The live path was
  measured to *accept* `temperature` and `thinking.budget_tokens` — **nothing may rely on the
  endpoint rejecting a malformed request; the guard rails are ours.**
- **A refusal can never become an empty finding.** Models decline with HTTP 200 and a possibly-empty
  content list; the gateway checks `stop_reason` before touching content and raises
  `ModelRefusalError`. Refusals are expected in normal operation — adjudicative case files routinely
  discuss criminal conduct, substance use, and foreign contacts.
- **A requested schema is verified, not trusted.** A `response_schema` is sent as one tool; the
  gateway returns that tool call's validated input or raises `StructuredOutputError`. `strict: true`
  is unavailable, so tool input is best-effort and must still be validated through the Pydantic
  contracts downstream.
- **Contract hygiene**: `extra="forbid"` and `frozen=True` on every contract; prefixed identifier
  types (`^run_…`, `^fnd_…`); contracts round-trip through JSON without loss, because a checkpoint
  is a serialization.
- **`.env` reaches a process at entry points only** (ADR-016). Library code is a pure consumer of
  `os.environ`. `python-dotenv` is a dev dependency, permanently.
- **No empty directories.** Create a directory when the first real file lands in it.

### Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+, `uv` + `pyproject.toml` |
| API | FastAPI + Uvicorn — the stable boundary for local and cloud |
| Contracts | Pydantic v2 + JSON Schema |
| Orchestration | **LangGraph** (ADR-012), behind our own port |
| Retrieval | OpenSearch (local, Docker) mirroring the AWS vector collection |
| Transactional store | PostgreSQL — system of record for workflow state |
| Model gateway | `ModelGateway` port; `litellm` (default) and `bedrock` adapters, both on the `anthropic` SDK |
| Extraction | Docling, OCRmyPDF + Tesseract, Chonkie |
| Embeddings | Local model, **development only** — AWS owns production chunking and embedding |
| Observability | OpenTelemetry + Jaeger |
| Quality | Ruff, mypy/pyright, Bandit, pytest, pip-audit |
| Deployment target | AWS GovCloud, Lambda/SAM adapter built and exercised (ADR-004) |

### Conventions

Branches `feature/`, `bugfix/`, `hotfix/`, `chore/`, `docs/`. Commits: Conventional Commits.
Every claim about a framework, service, or model in a handoff document is either cited or explicitly
marked unverified.

## Key Decisions

Nineteen decisions from `docs/DECISIONS.md` (precedence 0). **All LOCKED.** Read `docs/DECISIONS.md`
before proposing an architectural change; either follow a recorded decision or explicitly supersede
it with a new numbered entry stating what changed and why. Do not silently diverge.

<decisions>
<decision id="ADR-001" status="LOCKED" scope="project deliverable">The deliverable is a proven architecture and a handoff package, not a product. Runnable code is a means of proof. Handoff artifacts are built continuously, not written up at the end. Work producing a demo but no transferable finding is deprioritized against work that settles a real question.</decision>
<decision id="ADR-002" status="LOCKED" scope="repository boundaries">Standalone platform. No shared code, infrastructure, or submodules with `amilens-localdev`. AmiLens is prior art whose documented gaps this architecture is designed to close.</decision>
<decision id="ADR-003" status="LOCKED" scope="authority coverage">First release covers both 5 CFR part 731 suitability/fitness and SEAD-4 national-security eligibility, with the authority-routing engine implemented — not stubbed. Two approved policy packs at launch. PIV/HSPD-12 out of the first release but not structurally excluded.</decision>
<decision id="ADR-004" status="LOCKED" scope="deployment partition">Local-first development on Docker Compose; AWS GovCloud is the deployment target, with the Lambda/SAM adapter built and exercised. GovCloud feature gaps are checked per feature, never assumed from commercial AWS. Q-01 is a hard gate, not an assumption.</decision>
<decision id="ADR-005" status="LOCKED" scope="interface layer">FastAPI is the boundary; no UI in Milestone 1. Blueprint §4.1.2's Streamlit console is declined. The human-review state machine is still built and enforced; only its presentation is deferred.</decision>
<decision id="ADR-006" status="LOCKED" scope="graph database">No Neo4j, in any milestone, until evidence demands one. Cross-document relationships and timelines are served by structured entities and dated events in PostgreSQL plus OpenSearch retrieval.</decision>
<decision id="ADR-007" status="LOCKED" scope="retrieval architecture">iReports issues hybrid lexical + kNN queries directly against an AWS OpenSearch-compatible vector collection owned and populated by a separate ingestion pipeline. iReports is a consumer, not a producer. Local ingestion, chunking, and embedding are development only. Embedding-model parity is a hard coupling. All field names, filters, and facet mappings are isolated to a single mapping module so adapting is a one-file change.</decision>
<decision id="ADR-008" status="LOCKED" scope="model routing" amended-by="ADR-015,ADR-017">Three model tiers, referenced only by alias: `ireports-orchestrator`, `ireports-thinking`, `ireports-fast`. Application code never names a model. On Bedrock, model ids carry an `anthropic.` prefix. Pin the tested combination in a compatibility matrix.</decision>
<decision id="ADR-009" status="LOCKED" scope="run profiles">No offline run profile. No recorded-fixture provider, no local LLM server. Bedrock access is required to run the system. Unit and contract tests mock at the gateway boundary. Reproducibility comes from recorded run manifests, not replay.</decision>
<decision id="ADR-010" status="LOCKED" scope="ASAP delivery">A versioned JSON envelope carrying bounded evidence excerpts plus stable references, delivered through a transactional outbox with idempotency keys and recorded receipts, against a local ASAP mock that validates the schema and simulates status codes, timeouts, and retries. The envelope is our proposal, not an agreed interface (Q-04).</decision>
<decision id="ADR-011" status="LOCKED" scope="human review">Hard human-review gate, single reviewer role. A run pauses in an explicit review state; one authorized reviewer may accept, modify, or reject each proposed finding. Nothing reaches ASAP without a recorded disposition — no bypass, in any profile, including local development. A dev-mode auto-approve flag is exactly the affordance that survives into production.</decision>
<decision id="ADR-012" status="LOCKED" scope="orchestration framework">The orchestration framework is LangGraph, resolved 2026-08-11 on a measured four-leg bake-off. All three candidates passed all four legs, so the decision is about cost, not correctness. Hand-rolled is the recorded runner-up and the fallback if the dependency surface is refused. Conditions carried forward and NOT closed: cold start under SAM local unmeasured; LangSmith stays pinned closed and proven closed at every entry point; the checkpoint blob remains a deserialization trust boundary; nodes depend on our port, never on LangGraph directly.</decision>
<decision id="ADR-013" status="LOCKED" scope="run model">Interactive analysis, one case at a time, results in minutes. No batch queue in the first milestone. The run model must not assume a single in-process execution — checkpointing and resume are required regardless.</decision>
<decision id="ADR-014" status="LOCKED" scope="prohibited fields">No universal person-risk score. No contract carries an aggregate risk score, risk level, or overall recommendation field. Findings are per-criterion, per-authority, evidence-backed, and individually dispositioned. Schema review must reject any field that functions as an aggregate score, whatever it is named.</decision>
<decision id="ADR-015" status="LOCKED" scope="model gateway" amends="ADR-008">A `ModelGateway` port with two production adapters selected by configuration — `litellm` (default) and `bedrock` — plus an offline `stub` for contract tests only. Both production adapters use the official `anthropic` SDK; the OpenAI-compatible surface would silently cost adaptive thinking, effort, structured outputs, thinking blocks, and the `refusal` stop reason. A refusal can never become an empty finding. No sampling parameters, anywhere. No default model id exists — a missing one is a startup error naming the variable.</decision>
<decision id="ADR-016" status="LOCKED" scope="configuration loading">`.env` reaches a process at entry points, never through a library. Library code stays a pure consumer of `os.environ`. `python-dotenv` is a dev dependency, permanently. `override=False`. Contract tests strip every `IREPORTS_*` variable.</decision>
<decision id="ADR-017" status="LOCKED" scope="gateway routing" amends="ADR-015">`IREPORTS_LITELLM_BASE_URL` is used verbatim; `{base}/v1/messages` is LiteLLM's native Anthropic-format endpoint. `{base}/anthropic/v1/messages` is passthrough to `api.anthropic.com` and returns `401 invalid x-api-key` — a wrong-route error that presents as an authentication error. An optional per-tier alias→model override exists for shared proxies, defaulting to the identity mapping. ADR-008's invariant is untouched.</decision>
<decision id="ADR-018" status="LOCKED" scope="structured output" amends="ADR-015" partly-superseded-by="ADR-019">A requested schema is verified, not trusted. The gateway raises `StructuredOutputError` if the response is not the requested structure; the diagnostic reports shape only — length, and whether the text is fenced — never the text itself. Stripping the Markdown fence was rejected. Milestone 2 surfaces `StructuredOutputError` to the reviewer as an `InformationGap` (`blocking=True`).</decision>
<decision id="ADR-019" status="LOCKED" scope="structured output mechanism" supersedes="ADR-015 mechanism, ADR-018 diagnosis">Structured output is a single tool call, and no tier needs Opus. `output_config.format` is measured unreliable everywhere including Opus 4.8. A `response_schema` is sent as one tool and the gateway returns that tool call's validated input. Not sent: `strict: true`, forced `tool_choice`, `output_config.format`. Development mapping is Sonnet 4.6 / Sonnet 5 / Haiku 4.5, verified end to end. This is a per-endpoint finding — re-run the live smoke check before assuming it transfers.</decision>
</decisions>

**Open questions live in `docs/OPEN-QUESTIONS.md` (Q-01..Q-14) and nothing there is decided.** Check
it before building on an assumption. Q-01, Q-02, and Q-03 are GATE items — see
`.planning/ROADMAP.md` § Gates for how each is being handled.

---
*Last updated: 2026-08-11 after `/gsd-new-project` ingest of 12 source documents
(`.planning/intel/SYNTHESIS.md`, `.planning/INGEST-CONFLICTS.md`).*
