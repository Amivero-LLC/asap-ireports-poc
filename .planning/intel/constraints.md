# Constraints Intel

Extracted from SPEC-typed sources. One source contributed:

- `CLAUDE.md` — precedence 3, not locked. Repository guidance whose content is dominated by binding
  implementation contracts.

`CLAUDE.md` is precedence 3 and therefore **loses to `docs/DECISIONS.md` (precedence 0) wherever the
two differ.** Three entries below are marked SUPERSEDED for exactly that reason and are retained so
the divergence is visible rather than silently dropped. `CLAUDE.md` states this precedence rule
itself.

Constraints marked **NON-NEGOTIABLE** are reinforced by a LOCKED ADR and must survive synthesis
into every downstream artifact.

---

## Legal / mission boundary

### C-decision-support-boundary — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol · reinforced by: ADR-014, ADR-011, README.md, blueprint §1.3

The system identifies evidence-backed issues, mitigating information, contradictions, and
information gaps **for review by an authorized officer**. It must **never grant, deny, revoke,
suspend, or otherwise make a final suitability, fitness, credentialing, or national-security
eligibility determination.** Final determinations remain with trained and authorized Government
personnel.

This is enforced structurally, not by policy statement.

> If a change would let the system emit a determination, or would let a run reach delivery without
> a recorded human disposition, stop and raise it.

Enforcement in code: `DecisionSupportText` runs an `AfterValidator` on every narrative field a
model can write into, rejecting determinative phrasing. Tests:
`test_determinative_language_is_rejected`, `test_a_finding_cannot_state_a_determination`. The guard
catches the formulations blueprint §10.4 prohibits — "is unsuitable", "eligibility should be
denied", "recommend denial", "violated SEAD-4", "the subject is deceptive", and predictions of
future misconduct — tested in both directions: eight prohibited phrasings rejected, fourteen
permitted ones (including deliberate near-misses such as *"the record indicates a security
clearance was granted in 2019"*) must pass.
**It is a guard, not a proof.** It is regex-based and cannot catch every phrasing. The human review
gate, not this validator, is the actual control.

### C-no-aggregate-risk-score — NON-NEGOTIABLE
source: CLAUDE.md · type: schema · reinforced by: ADR-014 (LOCKED)

**No universal person-risk score. No aggregate "risk level" field on any contract.** No overall
recommendation field either. Findings are per-criterion, per-authority, evidence-backed, and
individually dispositioned.

Enforcement: a test walks every published schema, following `$defs`, and rejects any property whose
name functions as an aggregate score or determination —
`test_no_contract_carries_an_aggregate_score`. Schema review must reject any field that functions
as an aggregate score, **whatever it is named**.

Known drift risk, called out in the source: `ReviewUrgency` is a sequencing hint for the reviewer's
queue — how soon a human should look — and **not** a severity score. It is per-finding and never
aggregated across findings or across a person. It is the field most likely to drift into an ADR-014
violation.

### C-human-disposition-gate — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol · reinforced by: ADR-011 (LOCKED)

Every finding is a *proposed* finding until a human reviewer records a disposition. **Nothing
reaches ASAP without an explicit human disposition — the gate is a state transition, not a config
flag.** No bypass, in any profile, **including local development.** Both the original machine
proposal and the human-approved version are retained.

Enforcement: a run in any delivery-side status with `human_review_recorded=False` fails validation;
the transition table is walked to prove no path reaches delivery without passing the gate
(`test_no_path_reaches_delivery_without_human_review`). `ContractModel` is `frozen=True`;
`HumanDisposition` references the proposal by id and carries `approved_text` alongside it
(`test_the_machine_proposal_is_immutable`, `test_modification_retains_both_versions`).

---

## Data handling

### C-synthetic-data-only — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol · reinforced by: README.md, Q-08 assumption

**Synthetic data only, ever.** No real case data in this repo — not in fixtures, not in tests, not
in examples. Production case files may contain PII, SPII, personnel-security information, and CUI.
Enforcement: `DataClassification` has exactly one member.

### C-no-case-text-in-telemetry — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol

**Raw case text never goes to logs, traces, or error messages.** Traces carry identifiers
(`case_id`, `run_id`, `node_id`), versions, and outcomes. Evidence text lives in access-controlled
stores only.

Downstream consequences recorded elsewhere in the ingest: the `StructuredOutputError` diagnostic
reports shape only — length, and whether the text is fenced — never the text itself, because a
model asked to structure a finding was by construction looking at case evidence (ADR-018). Gateway
errors carry status codes and node ids only, by construction. The checkpoint is where case-derived
text legitimately lives, which is what the log rule is protecting
(`checkpoint-threat-model.md` §1).

---

## Model access

### C-never-hardcode-a-model-id — NON-NEGOTIABLE
source: CLAUDE.md · type: api-contract · reinforced by: ADR-008 (LOCKED), ADR-017

**Application code references LiteLLM aliases only.** Three tiers:

| Alias | Role |
|---|---|
| `ireports-orchestrator` | Orchestration and control-flow reasoning |
| `ireports-thinking` | Deep criterion analysis, synthesis, challenge |
| `ireports-fast` | Classification, extraction, mechanical tasks |

Concrete model IDs, inference-profile IDs, and regions live in configuration. A partition change
must be a config change. On Bedrock, model IDs carry an `anthropic.` prefix (e.g.
`anthropic.claude-sonnet-4-6`) — the bare first-party ID will fail.

Enforcement: `ModelAlias` is a three-member enum; no contract has a free-text model field
(`test_model_reference_must_be_an_alias`). Gateway tests:
`test_litellm_passes_the_alias_through_as_the_model`,
`test_bedrock_model_ids_must_carry_the_anthropic_prefix`,
`test_bedrock_requires_a_model_id_per_tier_and_says_which`.

Refinement from ADR-017 (higher precedence, applies): the invariant is untouched — application code
names a tier. Only the *place the tier is resolved* may move into our environment when the LiteLLM
proxy is not ours to configure.

### C-model-gateway-sole-egress — SUPERSEDED IN PART
source: CLAUDE.md · type: api-contract · **superseded by ADR-015 (precedence 0)**

`CLAUDE.md` states: "Model gateway | LiteLLM — the only component permitted to call Bedrock."

ADR-015 amends this: a `ModelGateway` **port** with two production adapters — `litellm` (default)
and `bedrock` (direct, `AnthropicBedrockMantle`, standard AWS credential chain, no proxy) — plus an
offline `stub` for contract tests only. The surviving constraint is the stronger one: **the gateway
port is the only component permitted to call a model.** Application code depends on the port and
nothing else — never an SDK client, never a model id, never a provider.

The `stub` adapter must never be selectable in a profile that produces reviewer-visible findings.

### C-no-sampling-parameters
source: docs/DECISIONS.md ADR-015 (LOCKED), docs/handoff/model-gateway.md §2 · type: api-contract

`temperature`, `top_p`, and `top_k` are rejected by current models and are **not configurable in
this system**. Reasoning depth is `effort` per tier. Adaptive thinking, not a token budget —
`budget_tokens` was removed and 400s. `ireports-fast` is **low effort with thinking still ON**, not
thinking disabled: disabling thinking has two documented failure modes (a tool call written into
visible text so the call silently never runs; internal `<thinking>` tags leaking into output),
neither survivable for a system whose validators depend on structured output.

Per-tier effort defaults: orchestrator `medium`, thinking `high`, fast `low`.

Measured caveat: the live path **accepted** both `temperature` and `thinking.budget_tokens` with
HTTP 200 despite documentation saying they are rejected. **Nothing in this system may rely on the
endpoint rejecting a malformed request — the guard rails are ours.**

### C-refusal-must-raise
source: docs/DECISIONS.md ADR-015 (LOCKED), docs/handoff/model-gateway.md §3 · type: api-contract

Current models can decline with **HTTP 200**, `stop_reason: "refusal"`, and a possibly-empty
content list. Read naively, a refused specialist returns `""` — which validates, yields no finding,
and reaches a reviewer as a clean result. **Silent under-analysis that looks like a completed
analysis is the worst outcome this system can produce** — worse than a crash, because a crash is
visible. The gateway checks `stop_reason` *before* touching content and raises `ModelRefusalError`.

Refusals should be **expected in normal operation**, not treated as exotic: adjudicative case files
routinely discuss criminal conduct, substance use, and foreign contacts.

### C-structured-output-verified-not-trusted
source: docs/DECISIONS.md ADR-018, ADR-019 (LOCKED) · type: api-contract

A `ModelRequest` carrying a `response_schema` is sent as **one tool**; the gateway returns that tool
call's validated input. If no tool call comes back, the gateway raises `StructuredOutputError`
rather than returning prose. Not sent: `strict: true` (Bedrock rejects), forced `tool_choice`
(400s with adaptive thinking), `output_config.format` (measured unreliable on every model group).
Tool input is best-effort — `strict: true` is unavailable — so it **must still be validated through
the Pydantic contracts downstream.**

Deliberately not done: stripping the Markdown fence off a prose answer.

---

## Architecture invariants

### C-evidence-before-inference — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol · reinforced by: blueprint §3.3

Every material factual statement in a finding carries a **resolvable citation to a case evidence
span.** Every policy-relevance claim carries a **resolvable policy citation.** Deterministic
validators reject unsupported citations **before a human ever sees them.**

Enforcement: a finding that asserts something about the record must cite it; a span cannot serve
two roles; `policy_citations` has `min_length=1`
(`test_a_potential_issue_must_cite_evidence`, `test_a_span_cannot_serve_two_roles`).

### C-deterministic-shell — NON-NEGOTIABLE
source: CLAUDE.md · type: protocol · reinforced by: blueprint §3.4

Schema validation, citation validation, authority routing, policy-pack effectivity, and
loop/termination limits are **ordinary code.** The model reasons; **it does not decide control
flow, and it does not decide whether its own output is valid.**

`Budgets` is enforced by the deterministic shell, not requested of the model. A node that hits a
ceiling must produce `INCOMPLETE_DUE_TO_BUDGET`, which routes to **human review rather than to
failure** — a truncated analysis must be visible to a reviewer.

### C-postgres-is-system-of-record
source: CLAUDE.md · type: protocol

**PostgreSQL is the system of record for workflow state.** OpenSearch is a retrieval index. Never
treat a search index as authoritative for findings, dispositions, or run state.

### C-retrieval-through-the-port
source: CLAUDE.md · type: api-contract · reinforced by: ADR-007, Q-02

**Retrieval goes through the port, never a raw client.** All OpenSearch field names, filters, and
mappings live in **one mapping module** — the AWS collection's real schema is not fully known yet,
so adapting to it must be a single-file change.

### C-orchestration-through-the-port
source: docs/DECISIONS.md ADR-012 (LOCKED), scorecard §3, §5 · type: api-contract

Analysis nodes depend on **this project's own orchestration port**, never on LangGraph directly.
ADR-012 already requires this; enforced when `packages/orchestration` lands. Selecting LangGraph
"does not license `from langgraph import ...` in analysis code." Named as Milestone 2's first
obligation.

### C-routing-is-never-inferred
source: docs/handoff/contracts.md §2, blueprint §10.2 · type: schema

`RoutingBasis` has no `INFERRED` member. Missing metadata produces `BLOCKED_MISSING_METADATA` with
a required `blocking_gap` — never a guess.
`AuthorityRoutingResult` requires an explicit decision for **every** authority, including those that
do not apply: an absent route is indistinguishable from an oversight, and a reviewer needs to see
that SEAD-4 was considered and declined, and on what basis.

### C-fail-closed-on-policy
source: docs/handoff/contracts.md §2, blueprint §2.7 · type: schema

`PolicyPackRef` refuses to construct unless `status == APPROVED`. Effectivity is a date comparison
in code.

### C-contract-hygiene
source: docs/handoff/contracts.md §2 · type: schema

- **`extra="forbid"` on every contract.** A silently-dropped unknown field at a boundary is how a
  contract mismatch becomes a data-loss bug.
- **`frozen=True` on every contract.** ADR-011's "both versions are retained" only holds if the
  machine proposal cannot be edited in place.
- **Prefixed identifier types.** `^run_…` and `^fnd_…` patterns, because `run_id` and `finding_id`
  travel adjacently through orchestration, delivery, and audit; if both are bare strings,
  transposing them is invisible.
- Contracts must round-trip through JSON without loss, because a checkpoint is a serialization.

### C-checkpoint-is-a-trust-boundary
source: docs/handoff/checkpoint-threat-model.md §2, §5 · type: protocol

The boundary is between the checkpoint store and the process that deserializes from it. Everything
crossing it is **untrusted input**, even though the store is our own PostgreSQL.

Implemented controls: store plain JSON built from Pydantic contracts and **re-validate on load**;
construct the serializer strictly in code —
`JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)` — rather than relying on a
`LANGGRAPH_STRICT_MSGPACK` env var an environment might forget; **never `pickle`**, asserted by
test; exact pins plus `pip-audit` in CI.

**Strict mode fails *soft*** — a refused value returns as a plain `dict`, not an exception. This is
why contract re-validation on load is load-bearing rather than belt-and-braces.

Run ids must be **server-generated, never client-supplied**. Note `PostgresSaver` truncates
`thread_id` at a length-limited column, so a truncating id scheme could *create* cross-run
collisions.

Two LangGraph defaults are wrong for this architecture and **invisible in the code**:
`durability` defaults to `async` (must be `sync`) and checkpoint deserialization defaults to
permissive. A graph reads identically either way, so a reviewer cannot catch these by reading it.

### C-env-at-entry-points-only
source: docs/DECISIONS.md ADR-016 (LOCKED) · type: protocol

Library code is a pure consumer of `os.environ`. `.env` is loaded explicitly at process entry
points only. `python-dotenv` is a **dev dependency, permanently** — nothing in a shipped artifact
reads a `.env`. `override=False`. Contract tests strip every `IREPORTS_*` variable.

---

## Stack

source: CLAUDE.md · type: nfr

| Layer | Choice |
|---|---|
| Language | Python 3.12+, `uv` + `pyproject.toml` |
| API | FastAPI + Uvicorn — the stable boundary for local and cloud |
| Contracts | Pydantic v2 + JSON Schema |
| Orchestration | **SUPERSEDED — see below** |
| Retrieval | OpenSearch (local, Docker) mirroring the AWS vector collection |
| Transactional store | PostgreSQL — system of record for workflow state |
| Model gateway | LiteLLM — **superseded in part, see C-model-gateway-sole-egress** |
| Extraction | Docling, OCRmyPDF + Tesseract, Chonkie |
| Embeddings | Local model, **development only** — AWS owns production chunking and embedding |
| Observability | OpenTelemetry + Jaeger |
| Quality | Ruff, mypy/pyright, Bandit, pytest, pip-audit |

### C-orchestration-framework — SUPERSEDED
source: CLAUDE.md · **superseded by ADR-012 (precedence 0, LOCKED)**

`CLAUDE.md` states: "Orchestration | **Undecided — this is what Milestone 1 settles.** Candidates:
LangGraph, Strands Agents SDK, PydanticAI/Pydantic Graph, hand-rolled Python."

**This is stale on two counts.** ADR-012 is `Accepted` as of 2026-08-11: **the orchestration
framework is LangGraph.** And the candidate set was cut from four to three by the 1b landscape scan
on 2026-08-10 — PydanticAI / Pydantic Graph was dropped. See `INGEST-CONFLICTS.md` WARNING.

### C-explicitly-out-of-scope
source: CLAUDE.md · type: nfr · reinforced by: ADR-006, ADR-005, ADR-009

Explicitly **out**: Neo4j (ADR-006), Streamlit / any UI in Milestone 1 (ADR-005), LocalStack in the
default profile, a local LLM server (ADR-009), and any offline model-fixture profile (ADR-009).

### C-no-empty-directories
source: CLAUDE.md · type: nfr

**Do not scaffold empty directories.** Create a directory when the first real file lands in it. The
target layout in `CLAUDE.md` is the plan, not the current state.

Target layout: `docs/` · `spikes/` · `schemas/` · `packages/` (domain, orchestration, retrieval,
ingestion, policy, delivery, observability) · `apps/` (api, lambda_adapter, asap_mock) · `workers/`
· `policy-packs/` · `cases/synthetic/` · `evals/` · `tests/` · `infrastructure/`.
Note: `packages/gateway/` exists and is not in that list — the layout has drifted.

### C-conventions
source: CLAUDE.md · type: nfr

Branches: `feature/`, `bugfix/`, `hotfix/`, `chore/`, `docs/`.
Commits: Conventional Commits — `<type>(scope): <description>`.

### C-claims-are-cited-or-marked-unverified
source: CLAUDE.md · type: protocol · reinforced by: ADR-001

When making a claim about a framework, service, or model in a handoff document, **either cite a
source or mark it unverified.** This package will be read as authoritative by a team that cannot
easily check our work.

The handoff docs implement this with an explicit tag vocabulary that **must travel with any quoted
claim**: `[measured]` (reproduced on this machine), `[first-party]` (from the project's own source,
package metadata, or official documentation), `[secondary]` (a third party said it and we did not
confirm it), `[judged]` (one engineer's assessment, recorded with its reasoning), `[unverified]`
(could not be confirmed; treat as an open question).
