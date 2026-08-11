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

Early. This repo currently holds the source blueprint and the decision record. Application code
does not exist yet — Milestone 1 is architecture sign-off plus an orchestration-framework bake-off.

## Start here

| Document | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every architectural decision, with reasoning. **Read before proposing changes.** |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Milestones and what each one has to prove |
| [`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md) | What is unresolved, and what it costs to be wrong |
| [`CLAUDE.md`](CLAUDE.md) | Working conventions and the rules that constrain code |
| [`blueprint.md`](blueprint.md) | The source architecture paper — the project's **input**, not its output |

Where this repo's decisions diverge from `blueprint.md`, the divergence is recorded in
`docs/DECISIONS.md` and this repo's decisions win.

## The central question

The blueprint recommends an orchestration framework but supports the recommendation with a
criteria comparison rather than a demonstration. Orchestration touches checkpointing,
human-in-the-loop, error handling, packaging, testing, and observability, and the choice is hard to
reverse once analysis nodes are written against it.

Milestone 1 settles it with a runnable bake-off across LangGraph, Strands Agents SDK,
PydanticAI/Pydantic Graph, and hand-rolled Python — each implementing the same scenario, scored on
the same dimensions. The losing spikes are kept: a rejected candidate with a recorded reason is
part of the handoff.

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
