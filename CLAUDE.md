# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**asap-ireports** is a reference implementation of a local-first, bounded-agentic case-analysis
platform for federal suitability, fitness, and national-security eligibility adjudication.

**The deliverable is not the running system — it is a proven architecture and a handoff package
for the ASAP program team to implement.** Code exists to make architectural claims verifiable.
A decision we cannot demonstrate is a decision we have not made. Every significant choice ends
up in `docs/DECISIONS.md`, and every claim about a framework, a service, or a model ends up
backed by something runnable or explicitly marked unproven.

The primary risk this project addresses: **the agentic orchestrator is harder than it looks, and
the framework choice is load-bearing.** Milestone 1 exists to settle that with evidence rather
than assertion. See `docs/ROADMAP.md`.

`blueprint.md` is the source document — a developer-handoff architecture paper. It is the input
to this project, not its output. Where this repo's decisions diverge from the blueprint, the
divergence is recorded in `docs/DECISIONS.md` and **this repo's decisions win**.

## Decision-support boundary (non-negotiable)

The system identifies evidence-backed issues, mitigating information, contradictions, and
information gaps **for review by an authorized officer**. It must never grant, deny, revoke,
suspend, or otherwise make a final suitability, fitness, credentialing, or national-security
eligibility determination.

**Review happens in ASAP, not here (ADR-022).** iReports has no human interaction of any kind: it
runs unattended start to finish and emits proposals. An authorized officer reviews them in ASAP,
with ASAP's tooling, and their decision is recorded in ASAP. Do not add a review pause, a
disposition contract, a reviewer role, or any field recording what a human decided — that is
ASAP's contract to define, and ADR-022 superseded the ADR-011 gate that used to live here.

Concretely, this constrains the code:

- No universal person-risk score. No aggregate "risk level" field on any contract.
- Every finding is a *proposed* finding. `ProposedFinding` is the only finding type; nothing
  promotes it to anything else.
- No contract carries a field that models a human decision — no disposition, approval,
  sign-off, `human_reviewed`, or `release_to_asap`.
- Every envelope is pinned `machine_generated: true` and is un-reviewed by construction.
- Determinative language is rejected on every text field, whoever wrote it.

The boundary used to rest on two mechanisms: a state-machine gate *and* the fact that everything
emitted is a proposal. **The gate is gone, so the second one now carries it alone** — treat the
`ProposedFinding` type and `reject_determinative_language` as load-bearing, not as belt-and-braces.

If a change would let the system emit a determination, or would have iReports model, record, or
wait on a human decision, stop and raise it.

## Current state

**Last updated 2026-08-11.** Milestone 1's *build* is done — 1a, 1b, and 1c — but **the milestone
is not closed**: it needs program-leadership sign-off on the component boundaries, which is a human
review and is still outstanding (see below, and `01-HUMAN-UAT.md`). If this section
disagrees with `.planning/STATE.md`, STATE.md is newer — and fix this section, because a stale
"what exists" note is the single most expensive thing in this file.

What exists and works:

| Area | State |
|---|---|
| `packages/domain/` | 12 Pydantic v2 contracts + generated JSON Schema in `schemas/` (M1a, done) — includes `SpecialistResult` / `SpecialistCriterion` (CONT-01). Contract set **2.0.0**: ADR-022 removed `HumanDisposition` and `ReviewSummary` |
| `packages/gateway/` | `ModelGateway` port with `litellm`, `bedrock`, and `stub` adapters; proven against a real endpoint |
| `spikes/` | All three ADR-012 bake-off candidates, passing four legs each, plus a retained negative control, `measure.py`, and `lambda_fit/` (ARCH-03, closed by ADR-023) |
| `docs/handoff/` | Seven handoff documents, including the scorecard that resolved ADR-012 and `component-architecture.md`, the seventh, which closes Milestone 1a (ARCH-01) |
| Tests | 160 passing, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |

What does **not** exist yet: `packages/orchestration`, `retrieval`, `ingestion`, `policy`,
`delivery`, `observability`; `apps/`; `workers/`; `policy-packs/`; `cases/synthetic/`; `evals/`.

**Scope is the orchestrator spine (ADR-020).** Three phases, not nine. Nothing was deleted:
eighteen requirements moved to `.planning/REQUIREMENTS.md` § v2 with their acceptance intact, each
owed a designed-not-built entry in the handoff. ADR-021 restored retrieval to the spine — RETR-01
and RETR-02 are back, while RETR-03 and CONT-02 stay cut. ADR-014 (no aggregate score) was considered for the cut
and explicitly kept — it remains NON-NEGOTIABLE. ADR-011 (the in-run disposition gate) was also
kept by ADR-020 and has since been **superseded by ADR-022**, which removed it entirely: review
happens in ASAP, not inside a run. The per-component account of what is built, planned, and designed-not-built, with
the reason for each cut, lives in `docs/handoff/component-architecture.md`, enforced by
`tests/architecture/test_build_state_table.py`.

Outstanding before M1 sign-off: **program-leadership sign-off on the component boundaries**, which
is a human review and cannot be produced mechanically — tracked in `01-HUMAN-UAT.md`.

ARCH-03 (cold start and packaging under SAM local) is **closed**, not outstanding: ADR-020 cut it,
ADR-023 measured it in `spikes/lambda_fit/` and closed it, and ADR-012 stands. What is still owed
is LAMB-01 — proving a Lambda timeout resumes without re-paying for an in-flight model call, which
depends on ORCH-02 and lands in Phase 2.

**Do not scaffold empty directories.** Create a directory when the first real file lands in it.
The target layout below is the plan, not the current state.

## Target layout

This is the blueprint-derived target layout — wider than the buildable scope, since ADR-020 and
ADR-021 pared the build to the orchestrator spine. Several directories below, `policy/`,
`delivery/`, `workers/`, `policy-packs/`, and `evals/` among them, are designed and not built. The
authority on what is built, planned, and designed-not-built is the build-state table in
`docs/handoff/component-architecture.md`:

```
.planning/       GSD planning state — PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, intel/
docs/            DECISIONS.md, ROADMAP.md, OPEN-QUESTIONS.md, handoff/
spikes/          orchestration bake-off — one directory per candidate framework
schemas/         JSON Schema contracts (case, document, evidence, finding, run, asap-envelope)
packages/        domain, orchestration, retrieval, ingestion, policy, delivery, observability
apps/            api (FastAPI), lambda_adapter, asap_mock
workers/         ingestion, analysis
policy-packs/    versioned, approved authority content
cases/synthetic/ synthetic case fixtures with expected/ results
evals/           datasets, expected, scorers
tests/           unit, contract, integration, retrieval, orchestration, security, end_to_end
infrastructure/  sam, docker, opensearch, postgres, otel
```

## Stack

Decided (see `docs/DECISIONS.md` for the reasoning behind each):

| Layer | Choice |
|---|---|
| Language | Python 3.12+, `uv` + `pyproject.toml` |
| API | FastAPI + Uvicorn — the stable boundary for local and cloud |
| Contracts | Pydantic v2 + JSON Schema |
| Orchestration | **LangGraph** (ADR-012, accepted 2026-08-11) — chosen by a measured four-leg bake-off, not by comparison. Nodes depend on our own port, never on LangGraph directly. Set `durability="sync"` and strict checkpoint deserialization; both defaults are wrong for us and invisible in the code |
| Retrieval | OpenSearch (local, Docker) mirroring the AWS vector collection |
| Transactional store | PostgreSQL — system of record for workflow state |
| Model gateway | The `ModelGateway` **port** is the only component permitted to call a model (ADR-015). Two production adapters behind it: `litellm` (default) and `bedrock` (direct, no proxy), both on the official `anthropic` SDK. A third, `stub`, is contract-tests only and must never be selectable where findings reach a reviewer |
| Extraction | Docling, OCRmyPDF + Tesseract, Chonkie |
| Embeddings | Local model, **development only** — AWS owns production chunking and embedding |
| Observability | OpenTelemetry + Jaeger |
| Quality | Ruff, mypy/pyright, Bandit, pytest, pip-audit |

This table records which technology was chosen for each layer, not which layer has been built —
see the build-state table in `docs/handoff/component-architecture.md` for what exists today.

Explicitly **out**: Neo4j, Streamlit/any UI, LocalStack in the default profile, a local LLM server.

## Rules that constrain code

**Never hard-code a model ID.** Application code references LiteLLM aliases only. Three tiers:

| Alias | Role |
|---|---|
| `ireports-orchestrator` | Orchestration and control-flow reasoning |
| `ireports-thinking` | Deep criterion analysis, synthesis, challenge |
| `ireports-fast` | Classification, extraction, mechanical tasks |

Concrete model IDs, inference-profile IDs, and regions live in LiteLLM config. A partition change
must be a config change. On Bedrock, model IDs carry an `anthropic.` prefix
(e.g. `anthropic.claude-sonnet-4-6`) — the bare first-party ID will fail.

**Evidence before inference.** Every material factual statement in a finding carries a resolvable
citation to a case evidence span. Every policy-relevance claim carries a resolvable policy
citation. Deterministic validators reject unsupported citations before a human ever sees them.

**Deterministic shell around probabilistic reasoning.** Schema validation, citation validation,
authority routing, policy-pack effectivity, and loop/termination limits are ordinary code. The
model reasons; it does not decide control flow, and it does not decide whether its own output is
valid.

**PostgreSQL is the system of record for workflow state.** OpenSearch is a retrieval index.
Never treat a search index as authoritative for findings or run state.

**Retrieval goes through the port, never a raw client.** All OpenSearch field names, filters, and
mappings live in one mapping module — the AWS collection's real schema is not fully known yet, so
adapting to it must be a single-file change. See `docs/OPEN-QUESTIONS.md` Q-02.

**Synthetic data only.** No real case data in this repo, ever — not in fixtures, not in tests, not
in examples. Production case files may contain PII, SPII, personnel-security information, and CUI.

**Raw case text never goes to logs or traces.** Traces carry identifiers (`case_id`, `run_id`,
`node_id`), versions, and outcomes. Evidence text lives in access-controlled stores only.

## Working on this repo

- Read `docs/DECISIONS.md` before proposing an architectural change. If a decision is already
  recorded, either follow it or explicitly supersede it with a new numbered entry that states
  what changed and why. Do not silently diverge.
- Check `docs/OPEN-QUESTIONS.md` before building on an assumption. Unresolved items are marked
  with their blast radius — some are cosmetic, some would invalidate a whole subsystem.
- When you make a claim about a framework, service, or model in a handoff document, either cite
  a source or mark it unverified. This package will be read as authoritative by a team that
  cannot easily check our work.

## Conventions

Follows the Amivero standards in `amivero-dev-resources/docs/reference/coding-standards.md`:

- **Branches:** `feature/`, `bugfix/`, `hotfix/`, `chore/`, `docs/`
- **Commits:** Conventional Commits — `<type>(scope): <description>`
