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

**To resolve:** confirm against current AWS GovCloud Bedrock documentation and an actual API call
in the target account and region — not from a general availability page. Record the answer as a
compatibility matrix entry (blueprint §15.3), not prose.

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
