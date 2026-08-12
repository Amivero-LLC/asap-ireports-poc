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

**The orchestration today is a stub** — one level, fixed width of three, no conditional edges, no
second stage — so the two paths are currently indistinguishable and no comparison between them means
anything yet. The decision waits until the orchestration is real enough to strain one of them; see
`docs/ROADMAP.md`, which is ordered around that.

**No module that analyzes a case may import LangGraph.** A test enforces it
(`spikes/lambda_demo/test_demo.py`). With two implementations genuinely running, this is the working
arrangement rather than lock-in insurance.

Build shared orchestration logic in framework-free code both paths call. Where a feature is easy in
one and hard in the other, that is a finding — write it into `docs/LESSONS.md`.

## Current state

**Last updated 2026-08-12.** If this disagrees with the code, the code is right — and fix this
section, because a stale "what exists" note is the most expensive thing in this file.

| Area | State |
|---|---|
| `packages/domain/` | 12 Pydantic v2 contracts + generated JSON Schema in `schemas/` |
| `packages/gateway/` | `ModelGateway` port; `litellm` (proven live), `bedrock` (never run), `stub` (tests only) |
| `spikes/lambda_demo/` | The runnable demo — both orchestrators, real model calls, validated envelopes, Lambda handler |
| `spikes/lambda_fit/` | Packaging and cold-start measurement under SAM local |
| Tests | 177 passing, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |

**Not built:** retrieval, crash/resume, model-call idempotency, budgets and loop limits, authority
routing, policy packs, ingestion, `apps/`, `evals/`.

**Don't scaffold empty directories.** Create one when the first real file lands in it.

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
