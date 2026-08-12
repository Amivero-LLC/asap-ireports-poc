# asap-ireports

A proof of concept for AI-assisted case analysis in federal suitability, fitness, and
national-security eligibility adjudication.

A case goes in. The system analyzes it against named adjudicative criteria and emits **proposed
findings**, each one traceable to evidence in the record. An authorized officer reviews those
proposals in ASAP and decides.

**This is exploratory work.** The goal is a working proof of concept plus enough documentation for
developers to build the real thing on the government side. It is not a product and not a formal
research deliverable.

## Try it

```bash
uv sync
uv run pytest -q          # offline — no model calls, no cost
```

The full demo makes **real model calls** (~20s, ~15k tokens) and needs Docker, the SAM CLI, and a
configured `.env`:

```bash
uv run python spikes/lambda_demo/build.py
cd spikes/lambda_demo && sam build --use-container --parallel && cd -
uv run --env-file .env python spikes/lambda_demo/run_case.py
```

A synthetic case runs through a Lambda — twice, once per orchestration path — and each run writes a
validated envelope to `spikes/lambda_demo/out/`. **Open one.** That file is what the architecture
produces.

Here is one finding from a real run, unedited:

> **Inconsistency between SF-86 'No' answer and admitted foreign business interest**
>
> Subject answered 'No' to holding any financial interest in a foreign business on Section 20A of
> the SF-86 (ev_003). During the subject interview, Subject stated they hold a 4 percent
> non-controlling interest in a family-owned foreign import business, inherited in 2021 (ev_004)…
>
> *Reviewer should assess the materiality of the omitted interest alongside the timing and
> voluntariness of the interview disclosure…*

It states what the record shows, cites the spans, names what a reviewer would need to weigh, and
decides nothing. That last part is structural, not stylistic — see below.

## Start here

| Document | What it is |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How it's shaped and why. **Start here** |
| [`docs/LESSONS.md`](docs/LESSONS.md) | What cost us time. The most useful thing in this repo |
| [`docs/AWS.md`](docs/AWS.md) | GovCloud availability, the region constraint, local↔AWS parity |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why each significant choice was made |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What to build next, in priority order |
| [`spikes/lambda_demo/`](spikes/lambda_demo/README.md) | The demo — what it proves and what it does not |

Reference material, kept but no longer growing: `docs/handoff/` (contract details, the orchestration
scan and scorecard, the checkpoint threat model, the model-gateway write-up) and `blueprint.md`, the
source architecture paper this project takes as **input**. Where this repo's decisions diverge from
the blueprint, the repo wins.

## The decision-support boundary

The system identifies evidence-backed issues, mitigating information, contradictions, and
information gaps **for review by an authorized officer**. It does not grant, deny, revoke, suspend,
or otherwise make any determination. Those stay with trained, authorized government personnel.

This is enforced structurally rather than by policy statement:

- No aggregate risk score exists on any contract.
- `ProposedFinding` is the only finding type the system can produce; nothing promotes it.
- No contract carries a field claiming a human decided anything.
- Every envelope is pinned `machine_generated`.
- Determinative language is rejected on every narrative field, whoever wrote it.

iReports runs unattended and has no reviewer-facing surface. Review happens in ASAP.

## Where it stands

**Working today, against real models:** the data contracts, the model gateway, both orchestration
paths, citation and contract validation, envelope packaging, and Lambda packaging invoked locally
under SAM.

**Designed, not built:** retrieval, crash/resume with model-call idempotency, budgets and loop
limits, and authority routing from policy packs. Document ingestion is not ours at all.

**Two orchestration paths are live on purpose** — custom Python and LangGraph, behind one port,
sharing one specialist implementation (ADR-024). The framework decision is deferred until
crash/resume exists, because that is the seam where the two actually differ. No module that
analyzes a case may import LangGraph, and a test enforces it.

`docs/ARCHITECTURE.md` § What exists has the detail, including the weakest point in the current
design.

## Stack

Python 3.12+ · Pydantic v2 · PostgreSQL (system of record) · OpenSearch (retrieval) ·
Claude on Amazon Bedrock, via LiteLLM or direct · AWS Lambda + SAM · OpenTelemetry

Everything runs locally except model calls, which go to a real endpoint. There is no offline model
fixture — a fixture would let us claim things about model behaviour we have not observed.

## Data

**Synthetic only, always.** No real case data in this repo — not in fixtures, not in tests, not in
examples. Production case files may contain PII, SPII, personnel-security information, and CUI.
