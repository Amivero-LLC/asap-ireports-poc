# Context Intel

Running notes from DOC-typed sources, keyed by topic. **Context only** — nothing here is a
requirement, constraint, or locked decision. Where a DOC's content is also covered by a
higher-precedence source, the higher-precedence source governs.

Sources, in precedence order:

| Prec | Source | What it is |
|---|---|---|
| 4 | `docs/handoff/orchestration-scorecard.md` | Measured bake-off evidence behind ADR-012 |
| 5 | `docs/handoff/orchestration-landscape.md` | Milestone 1b framework scan |
| 6 | `docs/handoff/contracts.md` | Delivered contract set record |
| 7 | `docs/handoff/model-gateway.md` | Gateway port, adapters, failure paths |
| 8 | `docs/handoff/compatibility-matrix.md` | Live model measurements, run of record |
| 9 | `docs/handoff/checkpoint-threat-model.md` | Checkpoint deserialization threat model |
| 10 | `README.md` | Repository front page — **summary only, expected to lag** |
| 11 | `blueprint.md` | **The project's INPUT, not its output.** Lowest precedence by design |

---

## Topic: the blueprint's standing

source: blueprint.md, CLAUDE.md, README.md, docs/DECISIONS.md

`blueprint.md` is a developer-handoff architecture paper and is the **input** to this project, not
its output. It is deliberately last in precedence. Wherever it conflicts with `docs/DECISIONS.md`,
DECISIONS.md wins — a project rule, not a preference.

Every proposal in `blueprint.md` is **context only**. Seven divergences are recorded in
`contracts.md` §3 and six more in `INGEST-CONFLICTS.md`; all resolve in favour of the ADRs.

`blueprint.md` contains no markdown cross-reference links. It cites internal AmiLens architecture
artifacts by tag (`[I-01]`) and technical sources by tag (`[T-nn]`), resolved in its Appendices B
and C, not by file path.

---

## Topic: mission and scope framing

source: blueprint.md §1.1–§1.3, README.md

**Mission (blueprint §1.1, verbatim):** "Provide authorized officers with a consistent, traceable,
policy-aware review of employee suitability, fitness, credentialing, and clearance case materials by
organizing evidence, identifying potential adjudicative concerns and mitigation, surfacing
contradictions and missing information, and packaging results for the ASAP front-end workflow."

**Explicitly out of scope for the initial release (blueprint §1.3):** final favorable or
unfavorable adjudicative decisions; automatic denial, debarment, revocation, suspension, or
credential issuance; investigative data collection from external commercial databases; unrestricted
web browsing by agents; autonomous contact with subjects, employers, references, or investigators;
automated legal conclusions or replacement of agency counsel; processing classified information in
an unapproved environment; training a foundation model on case data; **cross-case personality
profiling or generalized predictive scoring**; production use of real PII until the system boundary
and controls are approved.

**Non-functional success criteria (blueprint §1.5)**, unsuperseded and worth carrying: traceability
(every finding maps to source document, page, extracted span, chunk identifier, policy section,
prompt version, model alias, run identifier); isolation (no case retrieval without exact
authorization filters; cross-case leakage tests must produce zero unauthorized results);
reproducibility; recoverability (a run resumes from a checkpoint without repeating completed side
effects); observability (timing, status, model usage, retrieval identifiers, validation outcomes,
without sensitive text in ordinary logs); portability (the analysis core has no direct dependency
on Lambda globals, S3 paths, Bedrock SDK calls, or OpenSearch-specific response objects); security
(least privilege, documents treated as untrusted data, all outbound model calls through a
controlled gateway); human control.

---

## Topic: why authority routing is essential

source: blueprint.md §2.1 — **unique contribution, nothing higher-precedence supersedes it**

Federal personnel-vetting terms are related but **not interchangeable**. The same underlying conduct
can be relevant under multiple authorities, but the legal basis, covered population, decision
standard, available action, timing, and procedural protections differ. The software must produce
separate analyses and **never label a SEAD-4 concern as a suitability violation, or a suitability
factor as proof of national-security ineligibility.**

Domains the router must distinguish, with primary authority family:

- **Suitability** — competitive service and covered career SES applicants, appointees, employees per
  part 731. 5 CFR part 731 + OPM supplemental issuances.
- **Fitness** — excepted-service and contractor personnel. EO 13467, 5 CFR 731.202, agency policy;
  part 731 factors as a minimum plus job-related agency factors.
- **National-security eligibility** — persons needing access to classified information or a
  sensitive position. EO 12968, EO 13467, 5 CFR parts 732 and 1400, SEAD-4.
- **PIV credentialing** — HSPD-12, FIPS 201-3, OPM credentialing guidance. Identity and
  credentialing issues kept separate from employment or clearance analysis.
- **Fair Chance timing** — 5 CFR part 920. Produces a **process-control flag, not an adjudicative
  conclusion.**
- **Agency access / public trust** — position designation, agency directives, contracts.

Collapsing these produces analysis that is wrong in a way that is hard to detect (ADR-003).

---

## Topic: the RunState model — identifiers, not transcripts

source: blueprint.md §8.2 — **unique contribution**, reinforced by contracts.md §4.1

Graph state contains **identifiers and typed records, not an ever-growing transcript**:

```
RunState
  run_id, case_id, ingestion_id
  policy_pack_ids, authority_routes, run_profile
  model_aliases, configuration_hash, prompt_registry_version
  structured_fact_ids, timeline_version, retrieval_request_ids
  evidence_snapshot_ids, specialist_result_ids
  contradiction_ids, proposed_finding_ids
  validation_results, human_review_state, delivery_state
  budgets, errors
```

Large evidence text stays in the evidence store, referenced by identifier. This is **both** a
token-cost control and a sensitive-content-propagation control.

`contracts.md` §4 makes the consequence explicit: the less that is in the checkpoint blob, the less
a deserialization trust boundary can leak. This is also why Strands' transcript-shaped state
container was a structural objection in the bake-off — typed contract records pay a serialize/parse
tax at every node boundary.

---

## Topic: tool contracts and the prohibited-tool list

source: blueprint.md §8.4 — **unique contribution, unsuperseded**

The model may call only tools from a **criterion-specific allowlist**:

| Tool | Purpose | Key constraints |
|---|---|---|
| `get_case_metadata` | Read approved routing metadata | Exact case; selected fields only |
| `retrieve_case_evidence` | Hybrid evidence search | Mandatory case/access/version filters; bounded K |
| `retrieve_policy_authority` | Retrieve applicable policy text | Approved pack and effective date only |
| `get_timeline_events` | Read normalized events | Exact case and version |
| `get_document_context` | Expand around an evidence span | Same document; bounded pages/blocks |
| `get_contradictions` | Read unresolved conflicting assertions | Exact case and topic |
| `propose_information_gap` | Record a question for human review | No external investigation or contact |
| `submit_specialist_result` | End specialist loop with typed result | Schema validation and citation requirements |

**Prohibited tools:** shell, generic HTTP, unrestricted filesystem, generic SQL, arbitrary Python
execution, cross-case vector search, email, and **direct ASAP delivery**.

---

## Topic: loop limits, budgets, and termination

source: blueprint.md §8.5 — **unique contribution, unsuperseded, and the origin of an outstanding requirement**

Each specialist should have: maximum model calls (initially 3–5); maximum tool calls (initially
8–12); maximum retrieved evidence count; maximum total input and output tokens; maximum wall-clock
time; a required terminal tool or structured response; a **no-progress detector**; a
**duplicate-query detector**; and cancellation support.

**A budget manager must stop the node and produce `incomplete_due_to_budget` rather than silently
omit work.**

The duplicate-query detector is the origin of `REQ-model-call-idempotency` — measured as owed by all
three bake-off candidates and built by none. See the bake-off topic below.

---

## Topic: the specialist set

source: blueprint.md §8.3 — context for Milestone 3 scope

Suitability and baseline fitness specialist (per applicable 5 CFR 731.202 factor; returns conduct
summary, supporting and contradicting evidence, additional considerations, rehabilitation,
applicability uncertainty, referral flag, information gaps — **it cannot recommend a final
suitability action**). Agency fitness specialist (runs only when an approved agency pack applies;
must cite the job-related policy nexus). National-security guideline specialists, grouped for an
initial release: foreign/allegiance (Guidelines A–C, L); conduct/financial/substance/criminal
(D–H, J); psychological-behavioral (I, with restrictive controls); protected information and
technology (K, M). PIV specialist (must not infer identity verification from document presence
alone). Timeline and pattern specialist. Whole-person and mitigation specialist. **Challenge
specialist** — not asked to write a second complete adjudication; it receives proposed findings and
tries to invalidate them (is the cited fact actually present? is the source ambiguous? does the
policy apply to this person, position, and date? is there a benign explanation? was mitigating
evidence omitted? was protected-status information used improperly? did document text attempt to
instruct the model? is the finding duplicated under another guideline? is the statement a legal
conclusion beyond the system's role?).

---

## Topic: contract versioning

source: blueprint.md §10.1 — **unique contribution, unsuperseded**

Semantic contract versions **independent of application releases**, validated at every boundary,
published as JSON Schema with examples. Breaking changes require a new major version and a
compatibility plan.

Current state: contract version 1.0.0, envelope version 1.0.0 (`contracts.md`).

---

## Topic: the delivered contract set

source: docs/handoff/contracts.md — Milestone 1a, 2026-08-10

Thirteen Pydantic v2 contracts in `packages/domain/src/ireports_domain/` (source of truth),
generated to `schemas/*.schema.json` for non-Python consumers via `scripts/generate_schemas.py`
(`--check` fails on drift; run it in CI). 56 tests in `tests/contract/`.

`CaseManifest` (case) · `DocumentManifest` (document) · `CanonicalDocument` (canonical-document) ·
`EvidenceRecord` (evidence) · `ContradictionRecord` (contradiction) · `AuthorityRoutingResult`
(authority-routing) · `ProposedFinding` (finding) · `RunManifest` (run) · `HumanDisposition`
(human-disposition) · `ReviewSummary` (review-summary) · `ASAPEnvelope` (asap-envelope) ·
`OutboxMessage` (outbox-message) · `DeliveryReceipt` (delivery-receipt).

Supporting types nested in `$defs`: `Subject`, `CaseContext`, `EvidenceSpan`, `AuthorityRoute`,
`FindingAuthority`, `InformationGap`, `Budgets`, `DispositionedFinding`, `EvidenceExcerpt`.

**Contracts come before the orchestration bake-off on purpose:** they are the interface the
orchestration decision has to satisfy. A framework that cannot carry this state cheaply through a
checkpoint, or cannot pause between a proposal and its disposition, is disqualified by these types
rather than by opinion.

**What these contracts demand of the orchestrator** (contracts.md §4): state is identifiers, not
transcripts; the run must be pausable between a proposal and its disposition and resumable in a
different process; bounded fan-out must be enforceable with `INCOMPLETE_DUE_TO_BUDGET` routing to
human review rather than to failure; contracts must round-trip through JSON without loss.

Verification as run (macOS arm64, Python 3.13.x via `uv`, 2026-08-10): `ruff check` passed;
`ruff format --check` 20 files formatted; `mypy --strict` no issues in 11 source files; `pytest`
56 passed; `generate_schemas.py --check` current (13 contracts); `bandit` 0 high / 0 medium
(3 low-severity false positives — `B105` on `ClearanceRequirement` enum members `secret`,
`top_secret`, `top_secret_sci`).

---

## Topic: the orchestration bake-off result

source: docs/handoff/orchestration-scorecard.md — Milestone 1c, scored 2026-08-11

Evidence behind ADR-012, **not the decision itself** — the decision lives in `docs/DECISIONS.md`.
Machine-readable version is `orchestration-scorecard.json`, generated from
`spikes/bakeoff_scorecard.py` and validated as a `Scorecard` contract: a candidate row is either
complete or it fails to build.

| Dimension | hand-rolled | LangGraph | Strands |
|---|---|---|---|
| Four legs `[measured]` | pass | pass | pass |
| Candidate-specific lines `[measured]` | 195 | 266 | 373 |
| …net of spike-only instrumentation | 195 | ~192 | 373 |
| State at the review interrupt `[measured]` | 16,346 B | 16,115 B | 23,739 B |
| …total retained for the run | 16,346 B | 37,033 B | 23,739 B |
| Distributions beyond baseline `[measured]` | 0 | 31 | 42 |
| Added installed size `[measured]` | 0.0 MB | 18.0 MB | 47.3 MB |
| `pip-audit` advisories, pinned set | 0 | 0 | 0 |
| Cold start under SAM local | **not run** | **not run** | **not run** |
| Duplicate paid model call, 24 crashes | 12/24 | 11/24 | 0/24 † |
| Budget/allowlist enforcement `[judged]` | adequate | adequate | adequate |
| State inspectability `[judged]` | adequate | good | adequate |
| Test determinism `[judged]` | good | good | good |
| Developer comprehension `[judged]` | good | adequate | adequate |

† Not a durability property — an artifact of synchronous node bodies.

Pinned versions: `langgraph` 1.2.10, `langgraph-checkpoint-postgres` 3.1.2, `langgraph-checkpoint`
4.2.0, `langchain-core` 1.5.3, `langsmith` 0.10.17; `strands-agents` 1.51.0; hand-rolled has none.

**What the scorecard explicitly does not say:** it does not say the losers would fail (all three
passed identical assertions, both retained per ADR-001); it does not include cold start, packaging
size under Linux wheels, or OpenTelemetry export (blueprint §9.4 lists all three; none was run); it
does not measure real model behaviour (the gateway is a deterministic stub, deliberately — all four
legs are about control flow, which also keeps the bake-off decoupled from Q-01); the judged columns
are opinions on a three-point scale; it does not settle where analysis nodes live.

**What the harness guarantees:** node bodies are shared so "framework-specific lines of code"
measures wiring and nothing else; the stub gateway logs every model call to PostgreSQL *outside*
the framework so leg 1 is answerable; candidates are driven across a real process boundary; a
permanently retained broken candidate (`spikes/harness/negative_control.py`) proves leg 1 can
actually fail something.

Superseded figures, recorded rather than quiet: the 2026-08-10 line counts (hand-rolled 202,
Strands 367) came from an unrecorded method and could not be reproduced; re-counted by
`spikes/measure.py` they are 195 and 373 — within 4%, ordering unchanged.

Leg 1 was once tightened to assert on every specialist and then reverted — re-running work the
orchestrator never observed completing is correct at-least-once behaviour, so the stricter
assertion is flaky rather than strict.

---

## Topic: the framework landscape as of 2026-08-10

source: docs/handoff/orchestration-landscape.md — Milestone 1b

**Every claim in this document carries an evidence tag and the tag must travel with any quoted
claim.** In particular, the Diagrid claim about Strands resume behaviour is explicitly
`[unverified]` from an interested vendor and **must never be extracted as fact** — the bake-off
subsequently measured it and it did not hold.

Four changes make blueprint §9's comparison table unreliable as written:
1. **AutoGen and Semantic Kernel no longer exist as independent choices** — merged into Microsoft
   Agent Framework (1.0 GA, Python and .NET, April 2026); both in maintenance mode `[secondary]`.
2. **Pydantic Graph removed its persistence layer** — the single most consequential finding, and it
   inverts a blueprint recommendation.
3. **The Strands repository was restructured** — `strands-agents/sdk-python` now redirects to
   `strands-agents/harness-sdk`, a monorepo; `sdk-typescript`, `docs`, `mcp-server`, and
   `agent-builder` were archived `[first-party]`. Consolidation, not abandonment, but any blueprint
   URL pointing at the old repos is stale.
4. **Bedrock AgentCore reached GovCloud (US-West) 2026-05-05** with documented feature gaps.

**Measured installed footprint** `[measured]`, clean `uv` venv per row, Python 3.12, macOS arm64:
baseline (`pydantic`, `psycopg[binary,pool]`, `httpx`, `opentelemetry-sdk`) 17 dists / 28 MB;
LangGraph 42 / 46 MB (+25, +18); LangGraph + `langchain-openai` 47 / 46 MB; PydanticAI 35 / 54 MB;
Strands 47 / 62 MB (+30, +34); MS Agent Framework core 9 / 11 MB (−8, −17); MS Agent Framework meta
203 / **677 MB**.

Three corrections the scan insists on: the hand-rolled baseline is genuinely small (17 dists / 28 MB
— this strengthens the hand-rolled ADR-012 entry rather than weakening it); the `agent-framework`
meta-package's 677 MB is a trap, not a verdict (dominated by optional `claude_agent_sdk` 274 MB and
`copilot` 148 MB — the fair number is `agent-framework-core` at 11 MB, the *smallest* framework
measured); Strands carries server dependencies in its core (`boto3`, `botocore`, `mcp`, `starlette`,
`uvicorn`, `cryptography`, `watchdog`, all non-optional) `[first-party]`.

**Repository health** `[measured]`, GitHub API 2026-08-10: LangGraph 39,390 stars / 189 commits per
90d / 277 contributors / MIT / `langgraph` 1.2.10; Strands 6,870 / 692 / 251 / Apache-2.0 /
`python/v1.51.0`; PydanticAI 19,199 / 657 / 475 / MIT / 2.27.0; MS Agent Framework 12,718 / 682 /
196 / MIT; OpenAI Agents SDK 28,544 / 492 / 334 / MIT; Google ADK 21,067 / 1,033 / 404 /
Apache-2.0; Burr 2,506 / 50 / 50; DBOS 1,519 / MIT. **All candidate licences are permissive; none is
archived.** LangGraph's low commit volume post-1.0 should be read against its semver commitment
rather than as decay.

**The nine constraints the scan evaluated against**, drawn from `docs/DECISIONS.md`: C1 bounded
loops not open-ended agency; C2 durable checkpoint + resume in a separate process; C3
human-in-the-loop interrupt as a state transition; C4 PostgreSQL as system of record; C5 AWS Lambda
packaging with a GovCloud target; C6 Bedrock via LiteLLM, model by alias only; C7 OpenTelemetry,
framework-neutral, no raw case text in a trace; C8 deterministic testability with no offline
profile; C9 no raw case text to third-party telemetry — "any vendor telemetry path is a control to
be verified and disabled, not a default to be accepted."

**Frameworks considered and not taken forward:** Microsoft Agent Framework (closest human-in-the-loop
semantics in the field and the lightest core measured, but Azure-oriented against a GovCloud/Bedrock
program); DBOS, Temporal, Restate (durable-execution substrates, not agent orchestrators; DBOS
requires a long-running process, conflicting with the ADR-004 Lambda adapter); Claude Agent SDK,
Haystack, CrewAI, LlamaIndex Workflows, Burr, OpenAI Agents SDK, Google ADK.

---

## Topic: the model gateway

source: docs/handoff/model-gateway.md — 2026-08-10, `packages/gateway/`

The only component permitted to call a model. Application code depends on the `ModelGateway` port
and nothing else.

```python
from ireports_domain import ModelAlias
from ireports_gateway import Message, ModelRequest, build_gateway

gateway = build_gateway()  # adapter chosen by configuration
response = gateway.complete(
    ModelRequest(
        alias=ModelAlias.THINKING,  # a tier, never a model
        messages=(Message(role="user", content=prompt),),
        node_id="foreign_influence_specialist",
    )
)
```

**Configuration surface** (full set in `.env.example`): `IREPORTS_MODEL_ADAPTER`
(`litellm` | `bedrock` | `stub`), `IREPORTS_LITELLM_BASE_URL`, `IREPORTS_EFFORT_THINKING`
(`low|medium|high|xhigh|max`), `IREPORTS_LITELLM_MODEL_<TIER>`, `IREPORTS_BEDROCK_MODEL_*`,
`IREPORTS_BEDROCK_BASE_URL`, `IREPORTS_LIVE_SMOKE`. Effort defaults per tier: orchestrator
`medium`, thinking `high`, fast `low`.

**Preferred configuration:** name the models after the aliases in LiteLLM's `model_list`, so no
model id exists on our side at all.

```yaml
model_list:
  - model_name: ireports-thinking
    litellm_params: { model: bedrock/<CONFIRM VIA Q-01>, aws_region_name: <region> }
```

**Known gaps, carried honestly:** the `litellm` adapter has one live run, commercial partition only;
the `bedrock` adapter **has never been run at all, in any partition** — verified as correctly
constructed and nothing more, so do not read the green test suite as connectivity; the live path is
more permissive than the first-party API; the Mantle endpoint's GovCloud availability is unverified;
whether LiteLLM is permitted in the approved environment is unknown; prompt caching is not enabled
(Q-13); no retry or fallback policy; no streaming; the orchestration spike does not use this port.

**Verification as run** (macOS arm64, Python 3.13.x, `anthropic` 0.121.0, 2026-08-10): `ruff` clean;
`pytest` offline 87 passed, 8 skipped (the 8 are opt-in live checks); `pytest tests/live` 8 passed
against a commercial-partition Bedrock proxy; **`mypy --strict` 13 pre-existing errors in three test
modules, all in `tests/contract/`** — nine unused `# type: ignore`, four missing annotations in
`test_decision_support_boundary.py`. No package under `packages/` is affected. An earlier revision
of the page wrongly recorded this gate as clean; the correction is recorded rather than quietly
fixed, "because a handoff document that overstates a quality gate is exactly the failure ADR-001 is
written against."

---

## Topic: live model measurements — commercial partition only

source: docs/handoff/compatibility-matrix.md — run of record 2026-08-10

> **This says nothing about AWS GovCloud.** Every measurement was taken against a
> **commercial-partition** AWS Bedrock deployment reached through an organisation-shared LiteLLM
> proxy. A model that answers here may be absent there. An endpoint that resolves here may not exist
> there. A request shape accepted here may be rejected there. **Q-01 is not closed and is not
> narrowed by this document.**

This was the first real model call the project has ever made. Every prior gateway test was offline.

**Tier mapping — a development mapping, not an answer to Q-01:**

| Alias | Model | Bedrock ID | Effort | List price (in/out per MTok) |
|---|---|---|---|---|
| `ireports-orchestrator` | Claude Sonnet 4.6 | `anthropic.claude-sonnet-4-6` | `medium` | $3 / $15 |
| `ireports-thinking` | Claude Sonnet 5 | `anthropic.claude-sonnet-5` | `high` | $3 / $15 (intro $2 / $10 to 2026-08-31) |
| `ireports-fast` | Claude Haiku 4.5 | `anthropic.claude-haiku-4-5` | `low` | $1 / $5 |

Reasoning, recorded so whoever answers Q-01 can re-apply it to whatever is actually available:
`fast` → Haiku 4.5 at a fifth the input cost, low effort with thinking still on. `thinking` →
Sonnet 5 because this is the tier producing findings a reviewer reads, and **Sonnet 5 and Sonnet 4.6
carry the same list price** — preferring the older model would trade capability for nothing.
`orchestrator` → Sonnet 4.6, the lightest of the three jobs since the model does not decide control
flow; keeping it on a different model generation also means a route- or generation-level regression
shows up on one tier rather than silently on both. Opus 4.8 is available and is the obvious
escalation for the thinking tier — a Milestone 3 decision on measured finding quality, not a default.

**Request-surface support:** `output_config.effort` forwarded and honoured (an invalid value 400s
naming the real enum; `low` vs `high` on the same prompt changed whether a thinking block was
returned, the output-token count 3 vs 344, *and* the answer's correctness — a dropped parameter
cannot do that). `thinking: {type: adaptive}` forwarded and honoured. `temperature` **accepted**,
not rejected. `thinking.budget_tokens` **accepted**, not rejected.

**Structured output** — the finding with the largest blast radius, and it took three rounds of
probing. An earlier revision concluded enforcement was a per-model-group property with Opus
enforcing; **that was wrong, a sample-size-1 artifact**, recorded rather than deleted because the
corrected result is the opposite of the intuitive one.

`output_config.format`, eight trials per group (bare JSON / fenced prose): Opus 4.8 6/2; Sonnet 5
0/8; Sonnet 4.6 0/8; Haiku 4.5 0/8. The schema **does** reach the model — adding it raises
`input_tokens` 12→44 and 16→69 — so this is not the proxy dropping a field.

One tool, `tool_choice` omitted, adaptive thinking: **5/5 on every group.** Forced `tool_choice`:
400 on Sonnet 4.6 and Haiku 4.5. `strict: true`: 400 on Opus 4.8 and Sonnet 5.

**Endpoint routing:** `{base}/v1/messages` works (LiteLLM's native Anthropic-format endpoint);
`{base}/anthropic/v1/messages` returns `401 invalid x-api-key` (passthrough to `api.anthropic.com`,
which needs a first-party credential a Bedrock-backed proxy does not have). The failure presents as
an authentication error and is in fact a wrong-route error.

**Still unknown:** everything about GovCloud; whether `bedrock-mantle.{region}.api.aws` resolves
there; whether LiteLLM is permitted; the root cause of the structured-output split; cost and latency
at realistic prompt sizes (every probe was a handful of tokens); refusal behaviour on adjudicative
content (no refusal was observed because nothing resembling a case file was sent — refusal
*handling* is covered offline, refusal *rates* are unmeasured); prompt caching (Q-13).

**How to extend this file:** add a run-of-record block per partition and endpoint. **Do not
overwrite §1–§6 with a GovCloud run** — the value is the comparison between partitions.

---

## Topic: the checkpoint store as a security asset

source: docs/handoff/checkpoint-threat-model.md — Milestone 1c, 2026-08-11

Framework-independent; applies to whichever candidate ADR-012 selects, hand-rolled included. §7
states explicitly: **"It does not select a candidate."**

Three properties make the checkpoint worth its own threat model: it is **read back and acted upon**
(deserialized into live objects used to decide what executes next — integrity is an
execution-control property, not only a confidentiality one); it is **written by machine and read by
machine** (no human reviews a checkpoint between write and read, so a tampered row has no natural
detection point); it **carries case-derived text** (the checkpoint is where such text legitimately
lives, which makes it the thing the log-redaction rule is protecting).

**Advisory history** — four on LangGraph's checkpoint path between November 2025 and June 2026,
catalogued by the 1b scan `[first-party]`: `GHSA-wwqv-p2pp-99h5` (RCE in `JsonPlusSerializer` json
mode, fixed `langgraph-checkpoint` 3.0.0); `GHSA-mhr3-j7m5-c7c9` (`BaseCache` untrusted
deserialization → RCE, fixed 4.0.0); `GHSA-g48c-2wqr-h844` (unsafe msgpack deserialization, fixed
`langgraph` 1.0.10); `GHSA-fjqc-hq36-qh5p` (unsafe JSON deserialization, fixed 4.1.1). **Every one
is fixed at or below the versions this project resolves** (`langgraph` 1.2.10,
`langgraph-checkpoint` 4.2.0) `[measured]`; `pip-audit` over the full workspace reports no known
vulnerabilities `[measured, 2026-08-11]`.

What the history shows is not that a library is careless — it is that **this specific surface is
where the bugs land**, and a design treating the checkpoint as trusted has been wrong four times in
nine months in one codebase. "A hand-rolled checkpointer does not inherit those CVEs; it inherits
the surface."

**Threats T1–T6:** code execution on load; findings altered before review; the review gate skipped;
disclosure of case content; cross-run contamination; unbounded state growth. T1 and T3 are the two
that turn a data problem into an execution problem.

Controls **implemented** are recorded in `constraints.md` (C-checkpoint-is-a-trust-boundary).
Controls **not implemented** are recorded in `requirements.md` as outstanding work
(`REQ-checkpoint-row-integrity`, `REQ-checkpoint-least-privilege`,
`REQ-checkpoint-encryption-at-rest`, `REQ-checkpoint-retention`,
`REQ-checkpoint-provenance-on-load`).

The one asymmetry worth recording: **direction of default.** LangGraph's serializer defaults to
permissive deserialization and must be explicitly hardened; the hand-rolled store has no
deserialization surface beyond `json.loads` because it never grew one. A point for hand-rolled, and
a small one — the hardening is one constructor argument and a test. "Choosing a framework relocates
this boundary into code we do not control and must track advisories for. It does not remove it."

---

## Topic: README status (stale — do not use for current state)

source: README.md — precedence 10

The README describes the deliverable, the decision-support boundary, the quickstart, and a
start-here document index accurately. **Its Status section is stale** and is superseded by
`docs/ROADMAP.md` and `docs/DECISIONS.md`. Its own classifier notes it is "expected to lag."

Quickstart, still accurate:

```bash
uv sync
uv run pytest tests -q                             # 56 contract tests
uv run python scripts/generate_schemas.py --check  # schemas/ current with the models

# bake-off (needs Docker)
docker compose -f infrastructure/docker/compose.yaml up -d
uv run pytest spikes -v -s
```

Start-here index: `docs/DECISIONS.md` (read before proposing changes) · `docs/ROADMAP.md` ·
`docs/OPEN-QUESTIONS.md` · `docs/handoff/orchestration-landscape.md` · `docs/handoff/contracts.md` ·
`docs/handoff/model-gateway.md` · `CLAUDE.md` · `blueprint.md` (the project's **input**).

---

## Topic: synthetic case designs

source: blueprint.md §11 — context for Milestone 2 fixtures

Five synthetic case designs are specified: `AMI-SYN-SUIT-001` (tax filing, delinquent debt, and
candor), `FIT-002`, `MIX-003`, `SUIT-004`, and `NEG-005` — the last being a **negative control**
containing old, disclosed, mitigated conduct that the system must distinguish from an actual
concern (blueprint §1.4). Milestone 2 needs one synthetic case; these designs are the starting
point.
