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

The full demo makes **real model calls** — roughly 100–145s and 44–47k tokens on the small
synthetic case — and needs Docker, the SAM CLI, and a configured `.env`:

```bash
uv run python spikes/lambda_demo/build.py
cd spikes/lambda_demo && sam build --use-container --parallel && cd -
uv run --env-file .env python spikes/lambda_demo/run_case.py
```

A synthetic case runs through a Lambda and writes a validated envelope to
`spikes/lambda_demo/out/`. **Open one.** That file is what the architecture produces.

`run_case.py --resume-demo` does something harder: it invokes the *same run id* twice, the first
with a wall-clock ceiling below the work required, and shows the second invocation finishing what
the first started without re-buying it.

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

**Building this yourself?** [`docs/handoff/build-guide.md`](docs/handoff/build-guide.md) is written
for a team constructing the production system rather than for someone working in this repository:
terms and definitions, process diagrams, how to set up the fan-out and the branch, the three system
prompts verbatim, the conventions, and a build order. It is the one document here that assumes you
are starting from nothing.

Reference material, kept but no longer growing: `docs/handoff/` (contract details, the orchestration
scan and both bake-off reports, the checkpoint threat model, the model-gateway write-up) and
`blueprint.md`, the source architecture paper this project takes as **input**. Where this repo's
decisions diverge from the blueprint, the repo wins.

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

**Working today, end to end, against real models.** A case is loaded, routed to criteria derived
from its manifest, fanned out to concurrent specialists that retrieve their own evidence, validated,
synthesised across criteria, and packaged into an envelope — inside one Lambda invocation, invoked
locally under SAM.

| | |
|---|---|
| Contracts | 12 Pydantic v2 models with generated JSON Schema, checked in CI |
| Synthetic cases | 5, from 8 to 34 evidence spans, including one **deliberately clean** record |
| Criteria catalog | 5, across two decision domains; fan-out width comes from the case |
| Tests | **349 passing, 8 skipped** — skips are live-model, opt-in and never in CI |
| Quality gates | Ruff, `mypy --strict` over packages *and* tests, Bandit, schema currency |

**Results worth naming**, each measured rather than asserted:

- **Retrieval cut input tokens ~3×** against handing every specialist the whole case. Estimated 7×
  beforehand and was wrong — retrieval preferentially surfaces the *large* chapters.
- **A resumed run pays for nothing it already bought.** 0 duplicate paid calls across both former
  orchestration paths and every crash point in the fan-out, against the original bake-off's 11-of-24
  and 12-of-24.
- **A run stopped by its own ceiling finishes in the next invocation.** Live under SAM local: the
  first invocation completed 3 of 5 criteria, the second restored those 3 and ran only the
  outstanding 2 — **6 paid calls in total, against ~6 for one uninterrupted run.**
- **The fan-out is provably concurrent**, not a loop: a run records per-node timings and reports
  peak concurrency, because width and a ceiling are both satisfied by a `for` loop.
- **A deliberately clean case produced fewer findings, not manufactured ones** — and exposed a
  hard-coded classification that had been wrong since the day it was written.

**Built and honest about its value:** multi-step specialists retrieve, ask a cheap model whether
that was enough, and retrieve again. The machinery is proven — every stop reason fires, every
ceiling holds. On two cases the loop added **no evidence at all** for ~50% more tokens. Recorded in
ADR-028 as something to tune or default off, rather than defended.

**Not built:** authority routing from policy packs, ground-truth agreement scoring, ingestion,
and checkpoint row integrity — the largest known security gap, named rather than hidden. Document
ingestion is not ours at all.

**Never run on AWS.** Every live run went through a LiteLLM proxy and SAM local. The `bedrock`
adapter has never executed in any partition. That is the single largest open question (Q-01), and
it needs account access rather than code.

**The orchestrator is custom Python** — a thread pool and a loop, behind this project's own port.
A LangGraph adapter was built alongside it and **eight capabilities were implemented twice** to
decide between them. Four comparisons were null results; of the rest, the decisive one was the
capability LangGraph was originally chosen for: a first-party checkpointer saves you the *store* but
not the *codec*, and 8 of 24 crash trials lost the write for a call already paid for, against 0.
ADR-027 chose custom Python; ADR-029 removed the adapter.
[`docs/handoff/orchestration-decision.md`](docs/handoff/orchestration-decision.md) is the report,
**including a section on what it does not claim** — the graph is trivial, and the evaluation was
written by the author of both adapters.

**Nothing shipped imports `langgraph`, `langchain`, or `langsmith`**, and a test scans every module
and every `pyproject.toml` in `packages/` to keep it that way. `langsmith` is a mandatory transitive
dependency of `langchain-core` and can export run content; absence is a stronger guarantee than a
configuration pin.

`docs/ARCHITECTURE.md` § What exists has the detail, including the weakest point in the current
design.

## Stack

Python 3.12+ · Pydantic v2 · PostgreSQL (system of record) · OpenSearch (retrieval) ·
Claude on Amazon Bedrock, via LiteLLM or direct · AWS Lambda + SAM

**No orchestration framework, and no tracing library.** Both were evaluated; the orchestrator is a
thread pool and a loop, and the run trace is ~100 lines carrying node ids and timings only.
OpenTelemetry's GenAI semantic conventions are still marked *Development* with nothing stable, so
the trace is deliberately ours and maps onto them if a deployment wants to export.

Everything runs locally except model calls, which go to a real endpoint. There is no offline model
fixture — a fixture would let us claim things about model behaviour we have not observed.

## Data

**Synthetic only, always.** No real case data in this repo — not in fixtures, not in tests, not in
examples. Production case files may contain PII, SPII, personnel-security information, and CUI.
