# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## What this is

**asap-ireports** is an exploratory proof of concept for AI-assisted case analysis in federal
suitability, fitness, and national-security eligibility adjudication. A case goes in; evidence-backed
**proposed findings** come out; an authorized officer reviews them in ASAP.

The goal is working code plus documentation good enough for developers to build the real system on
the government side. It is not a product, and it is not a formal research deliverable — **prefer
building and learning over process ceremony.** If you can answer a question by looking it up or
running something, do that instead of recording an assumption about it.

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) first. Read
[`docs/LESSONS.md`](docs/LESSONS.md) before building anything — it is where the traps live.

## The decision-support boundary (non-negotiable)

The system identifies issues, mitigating information, contradictions, and information gaps **for
review by an authorized officer**. It must never grant, deny, revoke, suspend, or otherwise make any
determination.

This is a real legal and ethical limit on federal adjudication, not ceremony. It constrains code:

- No aggregate person-risk score. No "risk level" field on any contract.
- `ProposedFinding` is the only finding type. Nothing promotes it.
- No contract models a human decision — no disposition, approval, sign-off, or `human_reviewed`.
- Every envelope is pinned `machine_generated: true`.
- Determinative language is rejected on every narrative text field, whoever wrote it.

**Review happens in ASAP, not here (ADR-022).** iReports runs unattended start to finish. Do not add
a review pause, a disposition contract, or a reviewer role.

The boundary rests on two mechanisms: the `ProposedFinding` type and
`reject_determinative_language`. Treat both as load-bearing. If a change would let the system emit a
determination, stop and raise it.

## Rules that constrain code

**Never hard-code a model ID.** Application code names a tier — `ireports-orchestrator`,
`ireports-thinking`, `ireports-fast` — and configuration resolves it. On Bedrock, IDs carry an
`anthropic.` prefix; the bare first-party ID fails.

**Evidence before inference.** Every material factual claim carries a resolvable citation to a case
evidence span. Citations are checked deterministically, and a finding citing evidence that is not in
the case is **dropped**, not repaired.

**Deterministic shell around probabilistic reasoning.** Schema validation, citation validation,
budgets, and loop limits are ordinary code. The model reasons; it does not decide control flow, and
it does not decide whether its own output is valid.

**Rejections are output, not error logging.** Return them with the run. A silently empty result is
indistinguishable from a clean record, which is the worst failure this system can produce.

**PostgreSQL is the system of record for workflow state.** OpenSearch is a retrieval index — never
authoritative for findings or run state.

**Retrieval goes through one mapping module.** The AWS collection's real schema is unconfirmed, so
adapting to it must be a single-file change.

**Synthetic data only.** No real case data anywhere in this repo, ever.

**Raw case text never goes to logs or traces.** Traces carry identifiers (`case_id`, `run_id`,
`node_id`), versions, and outcomes.

## Two orchestration paths (ADR-024)

**Custom Python and LangGraph are both live**, behind this project's own port, sharing one
specialist implementation.

The orchestration is now real enough to tell them apart: runtime fan-out width, a synthesis stage,
conditional routing, and a type-checked tree. Four results so far, in `docs/LESSONS.md`:

| Change | Hand-rolled | LangGraph |
|---|---|---|
| Runtime fan-out width | No change | Structural — rebuilt around `Send` |
| Fan-in barrier | Free | Free (supersteps) — a null result |
| Conditional routing after fan-out | `if should_synthesize(...)` | Needs a `join` node; the naive version fires per dispatch on partial state **and fails silently** |
| `mypy --strict` | No change | Four suppressions — the documented `Send` pattern matches no `add_node` overload |

None is decisive, and none yet touches what LangGraph was chosen for — durable checkpointing.
**ORCH-02 is what closes this.**

**No module that analyzes a case may import LangGraph.** A test enforces it by scanning every
module in `packages/orchestration/`, exempting only `langgraph_adapter.py` and `registry.py`
(`tests/orchestration/test_orchestration.py`). With two implementations genuinely running, this is
the working arrangement rather than lock-in insurance.

Build shared orchestration logic in framework-free code both paths call. Where a feature is easy in
one and hard in the other, that is a finding — write it into `docs/LESSONS.md`.

## Current state

**Last updated 2026-08-12.** If this disagrees with the code, the code is right — and fix this
section, because a stale "what exists" note is the most expensive thing in this file.

| Area | State |
|---|---|
| `packages/domain/` | 12 Pydantic v2 contracts + generated JSON Schema in `schemas/` |
| `packages/gateway/` | `ModelGateway` port — `litellm` (proven live), `bedrock` (never run), `stub`. Plus an `EmbeddingGateway`, Titan via the proxy |
| `packages/retrieval/` | OpenSearch hybrid vector + lexical, mandatory case filter, bounded K. **All field names in `mapping.py`** (Q-02) |
| `packages/orchestration/` | Criteria routing, retrieval-backed specialists, synthesis, and both orchestrators behind `port.py`. Specialists return the published `SpecialistResult` |
| `spikes/lambda_demo/` | The runnable wrapper — case loading off disk, envelope packaging, Lambda handler, `run_case.py`, and the synthetic corpus |
| `spikes/lambda_fit/` | Packaging and cold-start measurement under SAM local |
| `cases/` in the demo | Three imported synthetic cases, ~35k tokens each, plus the original toy one |
| `evals/` | Scores **saved run files** offline — nine invariants, each descending from a real incident, plus a corpus check no single run can make about itself. `uv run python -m evals.score_run` |
| Tests | 246 passing, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |

**Not built:** crash/resume, model-call idempotency, wall-clock and token budgets, authority routing
from policy packs, ingestion, `apps/`, ground-truth agreement scoring (VAL-03/04).

**Known open defect.** `specialist.py` hard-codes `classification=POTENTIAL_ISSUE` and the response
schema never asks for one, so `MITIGATING_INFORMATION` and `NO_ISSUE_IDENTIFIED` are unreachable. On
a clean record every finding ships mislabelled. `evals` fails on it by design until it is fixed —
see `docs/ROADMAP.md` item 8, and note the rule conflict it sits on (an empty findings array is a
good answer, but an envelope with no findings is refused).

**Graduated 2026-08-12.** The orchestrator, specialist, synthesis and criteria modules now live in
`packages/orchestration/` and specialists return the published `SpecialistResult`. `SpecialistStatus`
stays on the local `SpecialistOutcome` wrapper — ADR-021 §2 keeps completion status off the contract
on purpose, and a test now asserts that rather than trusting prose.

**What that did *not* close.** ORCH-01's acceptance also requires `durability="sync"` and strict
checkpoint deserialization, which belong to ORCH-02 and do not exist. SPEC-01's tool-allowlist
clause is *vacuous* rather than satisfied — a specialist has no tool surface to allowlist. Both are
still unchecked in `docs/REQUIREMENTS.md`, deliberately.

**To run the demo you need Docker up** — OpenSearch holds the indexed cases:

```bash
docker compose -f infrastructure/docker/compose.yaml up -d
uv run --env-file .env python spikes/lambda_demo/index_cases.py   # a few embedding calls
```

**Don't scaffold empty directories.** Create one when the first real file lands in it.

## Where things live

Four documents, no fifth. The GSD planning machinery (`.planning/`) was retired 2026-08-12 —
it described the same work in a second vocabulary that nobody updated, and a stale tracker is
worse than none because it reads as current.

| File | Answers |
|---|---|
| `docs/ROADMAP.md` | What to build next, in order, with what each item taught us |
| `docs/REQUIREMENTS.md` | How you know a thing is finished |
| `docs/LESSONS.md` | What already cost someone a day |
| `docs/ARCHITECTURE.md` | How it is shaped and why |

**Update them in the commit that does the work.** That convention is the only thing keeping them
honest, and it is exactly the one that failed for the files they replaced.

## Working here

- Read `docs/DECISIONS.md` before an architectural change. Follow a recorded decision or supersede
  it with a new numbered entry — don't diverge silently. Keep new entries short.
- Write the trap next to the code that avoids it, then index it in `docs/LESSONS.md`. The comment at
  the fix is the version people actually read.
- When you claim something about a framework, service, or model in documentation, cite it or mark it
  unverified. This gets read by people who cannot easily check our work.
- Prefer measuring to asserting. `stat -f%z`, not `du`.

## Conventions

- **Work on `main`.** No feature branches. This is a small exploratory project with one person on
  it, and per-change branches fragmented the documentation across states — you could not tell which
  version of a doc was current. Commit to `main` and push. Branch only for something genuinely
  risky or long-running, and merge it quickly.
- **Commits:** Conventional Commits — `<type>(scope): <description>`. Write a real body explaining
  *why*; that record is the project's memory.
- **Quality:** Ruff, mypy --strict, Bandit, pytest. CI runs them on every push — keep it green.
- **Docs live with the code they describe.** When behaviour changes, update the doc in the same
  commit. A stale doc is worse than a missing one.
