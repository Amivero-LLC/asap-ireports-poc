# Lambda fit (ARCH-03)

Answers two questions ADR-004 assumed and never checked: **can an orchestrator that fans out to
sub-agents run on Lambda at all**, and **does LangGraph's dependency weight disqualify it on cold
start**. Settled in ADR-023.

**Status: cold-start leg complete as of 2026-08-11.** The timeout-resume leg is *not* built —
see "What this does not prove" below, because that gap is the important one.

## Run it

```bash
uv run python spikes/lambda_fit/build.py                       # stage one dir per candidate
cd spikes/lambda_fit && sam build --use-container --parallel   # real Linux wheels
cd - && uv run python spikes/lambda_fit/measure_coldstart.py --runs 5
```

Requires SAM CLI and a running Docker daemon. `--use-container` is not optional: `pydantic-core`
and `psycopg[binary]` ship native extensions, and a macOS arm64 wheel will not load in a Lambda
container. Building on the host would measure a package that cannot run.

## What was measured

`[measured]` SAM local, python3.12 arm64, 1024 MB.

| Candidate | Import (typical) | vs control | Unzipped | Zipped |
|---|---|---|---|---|
| hand-rolled | ~0.5 s | 1× | 30.1 MB | 9.1 MB |
| **langgraph** | **~1.6–2.3 s** | **~3×** | 68.9 MB | 19 MB |
| strands | ~1.5–1.8 s | ~3× | 79.7 MB | 34 MB |

**Do not quote these to three decimals.** Import time is sensitive to host load, and three runs on
the same machine produced medians of 1.565 s, 1.974 s and 2.303 s for LangGraph — with individual
samples from 1.49 s to 5.78 s. The candidate ratio, which is the finding, moved between 2.84× and
4.03×. `coldstart.json` records one low-load reference run; treat it as a reference point, not a
constant.

**The package sizes are the trustworthy numbers.** They do not vary with load at all, and they are
what a Lambda limit is actually checked against.

**ADR-012 stands.** LangGraph costs about a second more per cold start than a framework-free
control, on a workload where one specialist model call takes tens of seconds and cold starts happen
on scale-up rather than per request. Both Lambda size limits (250 MB unzipped, 50 MB zipped) have
room. Dependency weight was the strongest argument against LangGraph and the number does not
support it.

Strands is the heaviest package — 34 MB zipped before any application code, against a 50 MB limit.
Recorded for a future reader considering it fresh.

## What the numbers are not

`sam local invoke` reports `Init Duration: ~0.05 ms` for every candidate. **That field is
meaningless here** — SAM local runs the module in one container step and does not emulate Lambda's
init/invoke split. The figure in the table is `import_seconds`, timed inside the handler module
around the orchestrator import.

So this is an **indicative comparison between candidates on identical footing**, not a production
cold-start number `[unverified]`. A real one needs a deploy to Lambda, which is gated on Q-01 for
GovCloud. **Treat the ratio as the finding, not the absolute.**

## What this does not prove

The measurement above is the easy half. The hard half is unbuilt:

**A Lambda timeout is a crash mid-fan-out.** The 15-minute ceiling is survivable because the shell
stops at `max_wall_clock_seconds`, checkpoints, and returns, and the next invocation resumes — but
that argument depends on ORCH-02, model-call idempotency, which **does not exist**. Today the
bake-off measures 11 of 24 mid-fan-out crashes re-running an in-flight model call under LangGraph.

**Under Lambda that is worse than on a laptop**, because Lambda retries automatically: a timeout
without idempotency means paying for the same model calls again on every retry. Phase 2 (LAMB-01)
proves the resume path under Lambda semantics once ORCH-02 lands. Until then, "the ceiling is
survivable" is an argument, not a demonstration.

Also out of scope here: the trigger chain. Upload → extract → chunk → index belongs to the AWS
ingestion pipeline (ADR-007). This spike starts at "the case is ready, run the analysis."

## Layout

| File | What it is |
|---|---|
| `build.py` | Stages one directory per candidate with its own dependency set — sharing one would let the heaviest candidate inflate everyone's package size |
| `functions/app.py` | The handler. Imports the orchestrator at module scope, as a real handler would, and does nothing at request time |
| `template.yaml` | Three functions, one per candidate. No event sources — this exists to be measured, not deployed |
| `measure_coldstart.py` | Drives `sam local invoke`, parses the figures, writes `coldstart.json` |
| `coldstart.json` | The recorded result. Consumed by `spikes/bakeoff_scorecard.py` |

`.stage/` and `.aws-sam/` are build artifacts and are gitignored.
