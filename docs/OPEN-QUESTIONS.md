# Open Questions

Consolidated from `blueprint.md` §"Questions that should be resolved during Phase 0" and §19,
minus the items already settled in `DECISIONS.md`.

Each item carries a **blast radius** — what breaks or has to be rebuilt if the answer differs from
our working assumption. Items marked **GATE** must be answered before the work they block starts;
the rest have a stated assumption we proceed under.

| Field | Meaning |
|---|---|
| Blocks | What cannot safely start until this is answered |
| Assumption | What we are proceeding on in the meantime |
| Blast radius | Cost of being wrong |

---

## GATE — must be answered before the work they block

### Q-01 · Claude model availability in AWS GovCloud

**Blocks:** any GovCloud deployment work; the LiteLLM production configuration.
**Assumption:** none — this is the one item we refuse to assume.
**Blast radius:** high. Model availability, concrete model and inference-profile IDs, cross-region
inference restrictions, and data-routing rules in GovCloud are unvalidated (blueprint
§"Working assumptions", §4.1.9). If the intended model is unavailable in the approved partition,
the model tier strategy (ADR-008) needs different targets and the evaluation baseline moves.

**Added 2026-08-10 (ADR-015).** Two endpoint questions now ride on Q-01, not just model ids:
whether the Anthropic SDK's Bedrock Messages endpoint (`bedrock-mantle.{region}.api.aws`) resolves
in GovCloud at all — GovCloud endpoints do not generally follow the commercial pattern — and
whether a LiteLLM proxy is permitted in the approved environment. If the first is absent, the
fallback is a `bedrock-runtime` adapter (scoped work); if the second is refused, the `bedrock`
adapter becomes the only path and the alias→model mapping moves into our environment.

**Partial evidence added 2026-08-10 — Q-01 remains OPEN.** The project made its first real model
calls, against a **commercial-partition** Bedrock deployment via an organisation-shared LiteLLM
proxy. Recorded as a compatibility matrix entry in `docs/handoff/compatibility-matrix.md`, and
reproducible with `IREPORTS_LIVE_SMOKE=1 uv run pytest tests/live -v -s`.

What it establishes — **for the commercial partition only**:

- All three ADR-008 tiers reach a model and return usage, a resolved model id, and a stop reason.
- `output_config.effort` and adaptive thinking are forwarded and genuinely honoured, not dropped.
  This was ADR-015's central bet and it holds on this path.
- `output_config.format` is accepted by every group tested and **enforced by only some of them**,
  with the split not following documented model support (ADR-018).
- LiteLLM's native `/v1/messages` route works; the `/anthropic` passthrough route 401s against a
  Bedrock-backed proxy (ADR-017).
- `temperature` and `thinking.budget_tokens` — both documented as rejected on current models —
  were **accepted**. This path is more permissive than the first-party API.

**What it does not establish, and why the gate stays shut.** A commercial-partition result is not
evidence about GovCloud: not model availability, not concrete model or inference-profile IDs, not
cross-region inference restrictions, not data-routing behaviour. A model that answers here may be
absent there; an endpoint that resolves here may not exist there. The `bedrock` adapter has still
never been run in any partition, so `bedrock-mantle.{region}.api.aws` remains unverified. Whether
LiteLLM is permitted in the approved environment remains unknown.

**Largely answered 2026-08-12 — see [`AWS.md`](AWS.md), which supersedes this entry.** Most of
Q-01 turned out to be answerable from AWS documentation, and treating it as unknowable was a
mistake that cost three cut requirements. What is now documented:

- **Claude Sonnet 5 is available on Bedrock in AWS GovCloud (US-West and US-East)** since
  2026-07-23; Opus 4.8 since 2026-05.
- **`bedrock-mantle` endpoints exist in GovCloud US-West only** — our `bedrock` adapter uses
  `AnthropicBedrockMantle`, so **region choice constrains adapter choice.** US-East needs a
  `bedrock-runtime` adapter, which is real work.
- **Claude in Bedrock is FedRAMP High and DoD IL4/IL5 approved** in GovCloud (US).

**What remains open is much smaller:** documented availability is not account entitlement (Bedrock
model access is granted per account), the concrete inference-profile IDs must come from the target
account, and whether a LiteLLM proxy is *permitted* in the approved environment is an
organizational question rather than an AWS one.

**To close the rest:** point the live smoke check at the target endpoint in the target account and
paste the resulting matrix into `docs/handoff/compatibility-matrix.md` as a second run-of-record,
alongside the commercial one rather than replacing it.

**Related:** Bedrock's feature surface differs from the first-party Claude API in ways that affect
design — check per feature rather than assuming parity.

### Q-02 · AWS vector collection schema and field mapping

**Blocks:** finalizing the retrieval mapping module and the local OpenSearch index definition.
**Assumption:** a single collection with a facet separating case data from policy knowledge, plus
case-file metadata facets (case number, subject name, file name, …) applied post-ingestion via a
`document.xml` sidecar (ADR-007).
**Blast radius:** medium, and deliberately contained. All field names, filters, and facet mappings
are isolated to one module so adapting is a one-file change. It becomes high only if the real
shape is structurally different — separate collections per corpus, or nested/parent-child docs.

**To resolve:** obtain the collection's actual index mappings from the ingestion team — field
names, vector dimension, similarity metric, and the filterable metadata fields.

### Q-03 · Query-time embedding parity

**Blocks:** any claim that retrieval quality measured locally predicts retrieval quality in AWS.
**Assumption:** we will pin a local model and treat parity as unverified until confirmed.
**Blast radius:** high and silent. Because iReports queries the collection directly (ADR-007), our
query vectors must come from the same embedding model and revision their pipeline used to index.
A mismatch does not error — it just retrieves worse, and every downstream evaluation number
becomes meaningless without anyone noticing.

**To resolve:** get the exact model identifier, revision, dimension, normalization setting, and any
input prefix or instruction from the ingestion team. Then build a parity test that fails loudly on
drift. Ask whether they can expose an embedding endpoint — that removes the coupling entirely.

---

## Contract and integration

### Q-04 · Authoritative ASAP ingestion contract

**Assumption:** our versioned envelope with embedded excerpts plus references (ADR-010).
**Blast radius:** medium. Contained to the delivery adapter and envelope schema. Unknowns:
endpoint and auth, idempotency semantics, error and retry contract, attachment handling, and
whether ASAP stores evidence excerpts or only references and findings.

### Q-05 · Case scale and volume

**Assumption:** ~5–25 documents, a few hundred pages per case; single-case interactive (ADR-013).
**Blast radius:** low for architecture, high for capacity planning. Checkpointing and resume are
built regardless, so a volume surprise means adding a batch queue rather than reworking the run
model. Needed: average and 95th-percentile case sizes, page counts, document counts, daily volumes.

### Q-14 · Is Amazon Bedrock AgentCore an approved deployment target?

**Raised by:** the Milestone 1b orchestration landscape scan, 2026-08-10.
**Assumption:** no — ADR-004 stands, and we build and exercise the Lambda/SAM adapter.
**Blast radius:** low for Milestone 1, medium for deployment. AgentCore is a managed agent runtime,
not a Python orchestration library, so it does not change the M1 bake-off. It changes what the
Lambda adapter is *for*.

Amazon Bedrock AgentCore reached AWS GovCloud (US-West) on 2026-05-05 — after `blueprint.md` was
written, which is why neither the blueprint nor ADR-004 considers it. AWS documents specific
GovCloud gaps: no semantic search in AgentCore Gateway; AWS Agent Registry (Preview), Bedrock
Guardrails Policy, and Temporal Policy unavailable; and six CloudFormation resource types absent,
including `Policy`, `PolicyEngine`, and `Evaluator`.

**Read alongside Q-01, not as an answer to it.** This is adjacent evidence about the Bedrock service
family in the target partition. Q-01 asks about Claude model availability, concrete model and
inference-profile IDs, and cross-region inference rules, and remains fully open.

**To resolve:** ask the program whether AgentCore Runtime is approved, preferred, or excluded for
this workload. Whoever resolves Q-01 should also read AgentCore's GovCloud export-control section —
it states that AgentCore metadata may not contain export-controlled data and enumerates the
customer-initiated configurations under which data-plane traffic leaves the GovCloud partition. For
a system carrying CUI and personnel-security information that is a design constraint, not
boilerplate.

**Source:** `https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-bedrock-agentcore.html`
and `https://aws.amazon.com/about-aws/whats-new/2026/05/bedrock-agentcore-launch-aws-govcloud-us/`.
Detail in `docs/handoff/orchestration-landscape.md` §7.

### Q-06 · Agency supplemental fitness factors and precedent material

**Assumption:** federal-core policy pack only (5 CFR 731 factors, SEAD-4 guidelines).
**Blast radius:** low structurally — the policy-pack mechanism is designed for exactly this — but
it changes the content scope and the evaluation set. Needed: which agency supplemental factors,
policy directives, desk guides, and precedent materials are in scope.

---

## Governance and policy ownership

These do not block engineering but must be answered before a pilot with real data. Recorded here
so the handoff package shows them as open rather than silently assumed.

### Q-07 · Policy ownership

Which office approves machine-readable policy interpretations, summaries, decision tables, and
supersession? The design fails closed when a policy pack is expired or unapproved — that is only
meaningful if an approver exists.

### Q-08 · Data environment rules

What synthetic, de-identified, and production data may each environment contain? Which data impact
level, CUI category, privacy controls, and records schedules apply?
**Assumption for this repo:** synthetic only, always (ADR-002 constraints in `CLAUDE.md`).

### Q-09 · Records retention

What retention schedule applies to evidence snapshots, model responses, reviewer edits, and run
manifests? Affects storage design and the audit trail, not the analysis path.

### Q-10 · Performance thresholds and error tolerances

What precision/recall and false-positive/false-negative rates are acceptable, per criterion? The
evaluation harness can be built without these — they are the thresholds, not the measurements —
but release gates cannot be set until an adjudication business owner sets them.

### Q-11 · Appeal and contestability

What subject-facing or reviewer-facing correction process must be supported?

### Q-12 · Production support ownership

Who owns policy incidents, model incidents, data incidents, and ASAP delivery failures?

### Q-13 · Prompt caching approval

Is prompt caching approved for this data class and provider configuration? Material to cost;
immaterial to correctness.

---

## Resolved

Answered in `DECISIONS.md` — listed so the blueprint's question set maps cleanly onto this file.

| Blueprint question | Resolved by |
|---|---|
| Scope order / authority scope for release 1 | ADR-003 |
| Deployment partition | ADR-004 (with Q-01 as the outstanding gate) |
| Latency target | ADR-013 |
| ASAP evidence model | ADR-010 |
| Human review roles | ADR-011 |
| Local model / disconnected operation | ADR-009 |
| Graph database | ADR-006 |
| Embedding strategy | ADR-007 |
| Model routing | ADR-008 |
| Workflow engine | ADR-012 (bake-off) |
| Universal risk score | ADR-014 |
| Docker Desktop permitted | Assumed yes — local Docker Compose (ADR-004) |
