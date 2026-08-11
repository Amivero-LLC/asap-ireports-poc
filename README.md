# asap-ireports

A reference implementation of a local-first, bounded-agentic case-analysis platform for federal
employee suitability, contractor fitness, and national-security eligibility adjudication.

**The deliverable is a proven architecture and a handoff package for the ASAP program team — not a
product.** Code exists to make architectural claims verifiable. See
[`docs/DECISIONS.md`](docs/DECISIONS.md) ADR-001.

## Decision-support boundary

The system identifies evidence-backed issues, mitigating information, contradictions, and
information gaps **for review by an authorized officer**. It does not grant, deny, revoke, suspend,
or otherwise make a final suitability, fitness, credentialing, or national-security eligibility
determination. Final determinations remain with trained and authorized Government personnel.

This is enforced structurally, not by policy statement: no aggregate risk score exists in any
contract, findings are proposals until a human records a disposition, and nothing reaches ASAP
without that disposition.

## Status

Milestone 1 in progress.

- **1a — contracts: done.** Thirteen data contracts as Pydantic v2 models with generated JSON
  Schema, in `packages/domain/`. The component-architecture write-up is still outstanding.
- **1b — orchestration landscape scan: done.** ADR-012's candidate set amended on evidence.
- **1c — orchestration bake-off: in progress.** Shared harness and the hand-rolled baseline
  pass all four legs (202 lines, no framework). LangGraph and Strands still to run; ADR-012
  remains `Open`. See [`spikes/README.md`](spikes/README.md).

```bash
uv sync
uv run pytest tests -q                             # 56 contract tests
uv run python scripts/generate_schemas.py --check  # schemas/ current with the models

# bake-off (needs Docker)
docker compose -f infrastructure/docker/compose.yaml up -d
uv run pytest spikes -v -s
```

## Start here

| Document | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every architectural decision, with reasoning. **Read before proposing changes.** |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestones and what each one has to prove |
| [`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md) | What is unresolved, and what it costs to be wrong |
| [`docs/handoff/orchestration-landscape.md`](docs/handoff/orchestration-landscape.md) | The framework scan behind ADR-012's amended candidate set |
| [`docs/handoff/contracts.md`](docs/handoff/contracts.md) | The contract set, what each rule enforces, and where it diverges from the blueprint |
| [`docs/handoff/model-gateway.md`](docs/handoff/model-gateway.md) | The two model adapters, what the gateway guarantees, and the refusal path |
| [`CLAUDE.md`](CLAUDE.md) | Working conventions and the rules that constrain code |
| [`blueprint.md`](blueprint.md) | The source architecture paper — the project's **input**, not its output |

Where this repo's decisions diverge from `blueprint.md`, the divergence is recorded in
`docs/DECISIONS.md` and this repo's decisions win.

## The central question

The blueprint recommends an orchestration framework but supports the recommendation with a
criteria comparison rather than a demonstration. Orchestration touches checkpointing,
human-in-the-loop, error handling, packaging, testing, and observability, and the choice is hard to
reverse once analysis nodes are written against it.

Milestone 1 settles it with a runnable bake-off across **LangGraph, Strands Agents SDK, and
hand-rolled Python** — each implementing the same scenario, scored on the same dimensions. The
losing spikes are kept: a rejected candidate with a recorded reason is part of the handoff.

The 2026-08-10 landscape scan cut the set from four to three. PydanticAI / Pydantic Graph was
dropped: Pydantic Graph 2.x has no state-persistence API, so it cannot attempt the durable-resume
leg without either becoming the hand-rolled baseline or importing a workflow engine we have not
adopted. Reasoning in [`docs/handoff/orchestration-landscape.md`](docs/handoff/orchestration-landscape.md).

## Stack (decided)

Python 3.12+ · FastAPI · Pydantic v2 · PostgreSQL (system of record) · OpenSearch (retrieval) ·
LiteLLM → Amazon Bedrock · Docling / OCRmyPDF / Chonkie · OpenTelemetry + Jaeger

Orchestration framework: **undecided — Milestone 1 output.**

Explicitly out: Neo4j, any UI in Milestone 1, LocalStack in the default profile, a local LLM
server, and any offline model-fixture profile.

## Data

**Synthetic data only, always.** No real case data in this repo — not in fixtures, not in tests,
not in examples. Production case files may contain PII, SPII, personnel-security information, and
CUI.
