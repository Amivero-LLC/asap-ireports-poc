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
conditional routing, a type-checked tree, and budgets. Five results so far, in `docs/LESSONS.md`:

| Change | Hand-rolled | LangGraph |
|---|---|---|
| Runtime fan-out width | No change | Structural — rebuilt around `Send` |
| Fan-in barrier | Free | Free (supersteps) — a null result |
| Conditional routing after fan-out | `if should_synthesize(...)` | Needs a `join` node; the naive version fires per dispatch on partial state **and fails silently** |
| `mypy --strict` | No change | Four suppressions — the documented `Send` pattern matches no `add_node` overload |
| Early termination on a budget | 3 lines | 3 lines — a null result, and marginally cheaper for the synthesis skip |
| Node-level checkpointing | Ask, then tell — 4 lines | `PostgresSaver` writes no SQL, **and** costs a shared JSON codec, a raise-not-return budget stop, and 8 lost writes in 24 crash trials against 0 |
| Resume across a Lambda boundary | 3 + 3 = 6 paid calls | 3 + 3 = 6 paid calls — a third null result |
| A bounded loop inside a node | No change | No change — a fourth null result, predicted in writing beforehand |

**ADR-024's trigger has fired.** It said the call gets made when idempotent crash/resume works;
it works, on both paths, across a real SAM invocation boundary. The complete scorecard and a
recommendation (custom Python as the reference implementation, LangGraph retained as a conformance
arm) are in **ADR-027, recorded as *proposed*** — the evidence is one-sided but the decision is the
project owner's. **Read ADR-027 before doing orchestration work.**

**The evidence set is now complete.** ADR-027 named multi-step specialists as the one unmeasured
capability; they were built 2026-08-19 and discriminated between the paths not at all.

**No module that analyzes a case may import LangGraph.** A test enforces it by scanning every
module in `packages/orchestration/`, exempting only `langgraph_adapter.py` and `registry.py`
(`tests/orchestration/test_orchestration.py`). With two implementations genuinely running, this is
the working arrangement rather than lock-in insurance.

Build shared orchestration logic in framework-free code both paths call. Where a feature is easy in
one and hard in the other, that is a finding — write it into `docs/LESSONS.md`.

## Current state

**Last updated 2026-08-18.** If this disagrees with the code, the code is right — and fix this
section, because a stale "what exists" note is the most expensive thing in this file.

| Area | State |
|---|---|
| `packages/domain/` | 12 Pydantic v2 contracts + generated JSON Schema in `schemas/` |
| `packages/gateway/` | `ModelGateway` port — `litellm` (proven live), `bedrock` (never run), `stub`. Plus an `EmbeddingGateway`, Titan via the proxy |
| `packages/retrieval/` | OpenSearch hybrid vector + lexical, mandatory case filter, bounded K. **All field names in `mapping.py`** (Q-02) |
| `packages/orchestration/` | Criteria routing, multi-step retrieval-backed specialists, synthesis, budgets, gateway-level idempotency, node-level checkpointing, and both orchestrators behind `port.py` |
| `spikes/lambda_demo/` | The runnable wrapper — case loading off disk, envelope packaging, Lambda handler, `run_case.py`, and the synthetic corpus |
| `spikes/lambda_fit/` | Packaging and cold-start measurement under SAM local |
| `cases/` in the demo | Three imported synthetic cases, ~35k tokens each, plus the original toy one |
| `evals/` | Scores **saved run files** offline — nine invariants, each descending from a real incident, plus a corpus check no single run can make about itself. `uv run python -m evals.score_run` |
| Tests | 371 passing, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |

**Not built:** authority routing from policy packs, ingestion, `apps/`, ground-truth agreement
scoring (VAL-03/04), a specialist tool surface.

**Classification is the model's answer, not a constant (ADR-025).** The specialist picks from three
of the contract's five values; `contradiction` and `information_gap` stay synthesis's. An
unrecognised answer defaults to `potential_issue` **and is recorded as a rejection** — defaulting
silently is how the previous hard-coded version survived for weeks. An empty findings array remains
valid, so a wholly clean case produces **no envelope** and the run reports why.

**Graduated 2026-08-12.** The orchestrator, specialist, synthesis and criteria modules now live in
`packages/orchestration/` and specialists return the published `SpecialistResult`. `SpecialistStatus`
stays on the local `SpecialistOutcome` wrapper — ADR-021 §2 keeps completion status off the contract
on purpose, and a test now asserts that rather than trusting prose.

**LAMB-01 closed 2026-08-18, live under SAM local, both paths.** One `run_id`, two containers,
a 10s wall-clock ceiling on the first: 3 criteria completed and 2 skipped, then 3 nodes restored and
only the 2 outstanding ones run — **6 paid calls total against ~6 for one uninterrupted run**.
`uv run --env-file .env python spikes/lambda_demo/run_case.py --resume-demo` (costs real money).

**Checkpointing landed 2026-08-18 (ADR-026).** A completed node is checkpointed inside the node,
and a resume restores it instead of re-executing it — hand-rolled store in `checkpoint.py`,
`PostgresSaver` on the LangGraph path, both proven across a real process boundary. **This closed
ORCH-01**, whose last two clauses were `durability="sync"` and strict deserialization; both are now
named module-level values in `langgraph_adapter.py` with tests. Only work that *happened* is
recorded — a budget-skipped criterion is deliberately not, because it is the next invocation's job.

**A run evidences its own fan-out (2026-08-19).** `trace.py` records per-node start/end offsets,
`RunResult.peak_concurrency` is 3 on a five-criterion run, and `run_case.py` draws the timeline.
This exists because every fan-out test in the suite passed on a serial implementation — they
asserted width and a ceiling, and a `for` loop satisfies both. **Assert the mechanism, not the
outcome.**

**Multi-step specialists landed 2026-08-19 (ADR-028).** `gather.py` retrieves, asks a cheap
fast-tier model whether that was enough, and retrieves again — bounded by a no-progress detector, a
cancellation token, and `max_model_calls_per_node`, which **closes ORCH-03**. Read ADR-028's
consequences before defending it: on two live runs the assessor asked for more once in ten criteria,
that refinement surfaced nothing new, and the loop cost roughly +50% tokens. The machinery is
proven; the value is not.

**SPEC-01's tool-allowlist clause is *vacuous* rather than satisfied** — a specialist has no tool
surface to allowlist — so it stays unchecked in `docs/REQUIREMENTS.md`, deliberately.

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
- **Quality:** run what CI runs, with **its scopes** — `mypy packages/` passes while
  `mypy --strict packages tests scripts evals` fails, and the tests are where it fails, because a
  test double that adds an attribute loses it when returned as its base type. That exact mistake
  broke the build on 2026-08-19.

  ```bash
  uv run ruff check packages tests scripts spikes evals
  uv run ruff format --check packages tests scripts spikes evals
  uv run mypy --strict packages tests scripts evals      # note: tests, and --strict
  uv run python scripts/generate_schemas.py --check
  uv run pytest tests -q && uv run pytest spikes -q      # spikes must skip nothing
  uv run bandit -r packages evals -q --severity-level medium
  ```

  `.github/workflows/quality.yml` is the authority; if this list drifts from it, it is wrong.
- **Docs live with the code they describe.** When behaviour changes, update the doc in the same
  commit. A stale doc is worse than a missing one.
