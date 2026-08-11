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

Concretely, this constrains the code:

- No universal person-risk score. No aggregate "risk level" field on any contract.
- Every finding is a *proposed* finding until a human reviewer records a disposition.
- Nothing reaches ASAP without an explicit human disposition — the gate is a state transition,
  not a config flag.
- Both the original machine proposal and the human-approved version are retained.

If a change would let the system emit a determination, or would let a run reach delivery without
a recorded human disposition, stop and raise it.

## Current state

**Last updated 2026-08-11.** Milestone 1 is nearly closed. If this section disagrees with
`.planning/STATE.md`, STATE.md is newer — and fix this section, because a stale "what exists" note
is the single most expensive thing in this file.

What exists and works:

| Area | State |
|---|---|
| `packages/domain/` | 13 Pydantic v2 contracts + generated JSON Schema in `schemas/` (M1a, done) |
| `packages/gateway/` | `ModelGateway` port with `litellm`, `bedrock`, and `stub` adapters; proven against a real endpoint |
| `spikes/` | All three ADR-012 bake-off candidates, passing four legs each, plus a retained negative control and `measure.py` |
| `docs/handoff/` | Six handoff documents, including the scorecard that resolved ADR-012 |
| Tests | 111 passing, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |

What does **not** exist yet: `packages/orchestration`, `retrieval`, `ingestion`, `policy`,
`delivery`, `observability`; `apps/`; `workers/`; `policy-packs/`; `cases/synthetic/`; `evals/`.

Outstanding before M1 sign-off: the **component-architecture write-up** (the last 1a item), and
cold start under SAM local — unmeasured, and the one number that could reopen ADR-012.

**Do not scaffold empty directories.** Create a directory when the first real file lands in it.
The target layout below is the plan, not the current state.

## Target layout

Adapted from `blueprint.md` §5.2, trimmed to the decisions in `docs/DECISIONS.md`
(no `ui/`, no Neo4j, no offline fixture profile):

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
Never treat a search index as authoritative for findings, dispositions, or run state.

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
