# The runnable demo

One synthetic case goes in, a Lambda runs, and an `ASAPEnvelope` you can open comes out. Both
orchestration candidates — LangGraph and the hand-rolled control — run the same case through the
same specialists against a **real model**.

Everything else in this repository argues that the architecture works. This is the part you can
run. `spikes/lambda_fit/` measured whether the shape *packages*; this runs a case through it.

## What it demonstrates

1. **One invocation per run, with in-process fan-out** — ADR-023's chosen shape, executing. Three
   specialists fan out inside a single Lambda invocation, bounded by `IREPORTS_MAX_PARALLEL`.
   No Step Function, no Lambda per node, no queue between specialists.
2. **Both orchestration paths run behind one port (ADR-024)** — custom Python and LangGraph, the
   same case, the same shared specialist, the same *shape* of answer. The framework decision is
   deferred until crash/resume exists, so this is the working arrangement rather than a hedge.
   `specialist.py` does not know a graph exists, and `test_nodes_do_not_import_langgraph` fails if
   that ever stops being true.
3. **Evidence before inference, as executable code** — every citation is checked against the case
   before a finding is constructed. A finding citing evidence that is not in the record is dropped,
   not trimmed.
4. **The decision-support boundary is a type, not a prompt** — `DecisionSupportText` rejects
   determinative language whoever wrote it. ADR-022 removed the in-run review gate, so this guard
   and the `ProposedFinding` type carry the boundary alone.
5. **Malformed model output never takes the run down** — a requested schema is verified, not
   trusted (ADR-018).

## Run it

```bash
uv run python spikes/lambda_demo/build.py                       # stage one dir per candidate
cd spikes/lambda_demo && sam build --use-container --parallel   # real Linux wheels
cd - && uv run --env-file .env python spikes/lambda_demo/run_case.py
```

Needs the SAM CLI, a running Docker daemon, and a configured `.env`. No PostgreSQL — this demo has
no checkpointer.

`--use-container` is not optional. `pydantic-core` ships a native extension, and a macOS arm64
wheel will not load in a Lambda container; a host build would package something that cannot run.

`--candidate langgraph` runs one orchestrator instead of both. `--case-id` picks a different case
directory. `--verbose` prints the raw SAM and container streams — the Lambda runtime's
`START` / `END` / `REPORT` records and the handler's own structured log lines. The default output
is a reading of the response; `--verbose` is a record of the invocation.

**Two services have to be up, and they fail differently.** Docker, because SAM runs the function
inside a Lambda container image; and the compose stack, because OpenSearch holds the indexed cases
the specialists retrieve from. The first fails loudly. The second does not fail at all — retrieval
returns nothing, every criterion reports `nothing in the record matched`, and a missing service
reads like a clean record. `run_case.py` checks both before spending anything.

**This costs money.** A full run is roughly 22k–34k tokens across six thinking-tier calls. Nothing
in CI runs it and nothing should. The offline half — `test_demo.py` here plus
`tests/orchestration/test_orchestration.py`, all against `StubGateway` — is what CI checks.

Envelopes land in `out/<candidate>-<run_id>.json`, gitignored. **Open one.** That file is what the
architecture produces: a validated envelope of citation-backed proposals, pinned
`machine_generated: true`, carrying no field that records a human decision.

## What came out

`[measured]` 2026-08-12, SAM local, python3.12 arm64, 1024 MB, `ireports-thinking` resolved to
`anthropic.claude-sonnet-5` through a Bedrock-backed LiteLLM proxy. Five criteria selected from the
case, retrieval at k=6, plus the cross-criterion stage.

| Candidate | Wall | Tokens | Findings | of which synthesis | Envelope |
|---|---|---|---|---|---|
| hand-rolled | 102.6 s | 30,482 | 12 | 3 | valid |
| langgraph | 121.0 s | 37,298 | 9 | 2 | valid |

**Do not read a comparison into those numbers.** Two orchestrators running a probabilistic
analysis are two samples, not two evaluations of a function — across runs, one candidate differs
from itself by more than the two candidates differ from each other. Wall time is dominated by model
latency at `effort: high`, which varies by tens of seconds run to run. What is being demonstrated
is that **both produce a valid envelope of citation-checked proposals**, which is the claim; the
timing column is context, not evidence.

**The run before this one produced zero synthesis findings on both paths** — with a valid envelope,
no error, and 4,547 rejections reading `not an object`. The model had returned synthesis's arrays
as JSON strings and the loop enumerated them character by character. That is what a live run buys
that the offline suite cannot: the offline suite tests the shapes we already know about. See
`docs/LESSONS.md`, "A coercion in a private helper protects one call site".

The findings themselves read like decision support. From one run, on the candor criterion:

> **Inconsistency between SF-86 'No' answer and admitted/confirmed foreign business interest** —
> Subject answered 'No' to holding any financial interest in a foreign business on Section 20A of
> the SF-86 (ev_003). During the subject interview, Subject stated they hold a 4 percent
> non-controlling interest in a family-owned foreign import business, inherited in 2021 (ev_004)…
> Reviewer should assess the materiality of the omitted interest alongside the timing and
> voluntariness of the interview disclosure…

It states what the record shows, cites the spans, names what a reviewer would need to weigh, and
decides nothing.

## What the shell rejected, and why that is the interesting part

`run_case.py` prints every rejection. They are not an error path — they are the deterministic shell
doing its job, and a demo that hid them would put the safety story out of view. Observed across
these runs:

| Rejection | What happened |
|---|---|
| `['ev_005'] cited as both supporting and mitigating` | The model routinely cites one span in two roles — usually an investigator finding that establishes a fact *and* softens it. Resolved deterministically: supporting wins, and the demotion is recorded. |
| `missing/blank ['title', 'observation', …] — dropped` | A finding object arrived with none of its required fields. Intermittent — roughly one call in three, per ADR-018 — and it survived a bounded retry twice. |

That second one is unexplained, and is stated as unexplained. The rejection message now names the
keys that *were* present so the next occurrence distinguishes a truncated response from a
differently-shaped one, but that improvement has not yet caught one in the act. **It is a real,
reproducible property of structured output on this model group, not a bug in the shell** — the
shell's job is to reject it, and it does.

## What this does not prove

**It is not a Lambda deployment.** `sam local invoke` runs the function in a container on your
laptop. It does not emulate Lambda's init/invoke split, IAM, VPC egress to a proxy, or the
15-minute ceiling arriving as a real timeout. A production figure needs a deploy, which is gated on
Q-01 for GovCloud.

**It does not prove crash/resume.** There is no checkpointer here at all. LAMB-01 — that a Lambda
timeout resumes without re-paying for an in-flight model call — depends on ORCH-02 and lands in
Phase 2. This demo runs to completion or fails; it does not survive anything.

**It is not the VAL-03 corpus.** `AMI-SYN-FIN-001` has no analyst ground truth attached, so nothing
here measures whether the findings are *right* — only that they are well-formed, cited, and inside
the decision-support boundary. `cases/synthetic/` stays `PLANNED`.

**It is not retrieval.** Evidence spans are read from a file. RETR-01 and RETR-02 are Phase 2.

**No authority routing.** The three criteria are hard-coded in `specialist.py`. Routing (ROUT-01)
and policy packs are `DESIGNED-NOT-BUILT` under ADR-020.

**The package sizes here are not comparable to `lambda_fit`'s**, and the largest thing in them
should not be shipped at all. `[measured]` 2026-08-11, byte counts on the built artifacts:

| Function | Zipped | Unzipped |
|---|---|---|
| HandRolledFunction | 20.1 MB | 43.7 MB |
| LangGraphFunction | 28.9 MB | 82.4 MB |
| LangGraphFunction, less `boto3`/`botocore`/`s3transfer`/`jmespath` | **13.7 MB** | ~57 MB |

`botocore` alone is 24 MB unzipped, pulled in by `anthropic[bedrock]`, and the boto3 family is
**15.2 MB of the 28.9 MB zipped — more than half the package.**

**Vendoring it is waste, not a necessary cost.** The managed Lambda Python runtime already ships
it: `public.ecr.aws/lambda/python:3.12` carries boto3 and botocore 1.42.97 `[measured]`. A
deployment should exclude the boto3 family from the package and use the runtime's copy, which
recovers the 15 MB **without touching the `bedrock` adapter**. The one caveat is version drift —
the runtime's boto3 is whatever AWS ships and lags PyPI, so a dependency that needs a newer
botocore than the runtime carries has to vendor it or use a layer. `build.py` does not do this
exclusion today; it stages a self-contained package on purpose, because this spike is about
whether the shape runs, not about deployment tuning.

Dropping the `bedrock` adapter is **not** the way to get that space back. ADR-015 has two adapters
deliberately, and the direct one exists precisely for the case where no proxy is reachable — which
is unresolved for GovCloud under Q-01. Trading the only proxy-free path to a model for 15 MB that
the runtime would have given away is a bad trade.

`lambda_fit` remains the place package weight was measured for the ADR-012 comparison, on
directories that deliberately share nothing.

## Credentials

`GatewayConfig` reads `IREPORTS_*` from the environment (ADR-016) and a SAM container inherits
nothing from your shell, so `run_case.py` writes a `--env-vars` file first. It holds a live proxy
key, is chmod 600, is rewritten every run, and is gitignored. Never commit it.

**`sam local invoke --env-vars` only overrides variables the template already declares.** An
undeclared one is dropped in silence, and the function then fails inside the container reporting a
missing variable that is plainly set in your shell — which reads as a credentials problem and is
not one. That is why `template.yaml` declares every gateway variable with an empty default, and
why `run_case.py` reads that list back out of the built template and names anything it will not
forward.

## Layout

| File | What it is |
|---|---|
**The analysis is not here.** Criteria routing, specialists, synthesis and both orchestrators
graduated to `packages/orchestration/` on 2026-08-12, and their tests went with them to
`tests/orchestration/`. What is left in this directory is the runnable shell around that package.

| File | What it is |
|---|---|
| `cases/AMI-SYN-FIN-001/` | The synthetic case: a manifest and 8 citable evidence spans. Edit it and re-run. |
| `src/lambda_demo/case_loader.py` | Disk → the types `ireports_orchestration` analyses |
| `out/` | Where a live run writes its envelopes. Gitignored — **open one** |
| `src/lambda_demo/package.py` | Findings → validated `ASAPEnvelope` |
| `src/lambda_demo/handler.py` | The Lambda entry point. One invocation, one run, one envelope |
| `build.py` | Stages one directory per candidate with its own dependency set. **Staging is by path, so a new workspace package must be added here or the container lacks it** |
| `template.yaml` | Two functions. No event sources — the trigger chain belongs to the AWS ingestion pipeline (ADR-007) |
| `run_case.py` | Invokes both, writes `out/`, prints the comparison. The deliverable |
| `test_demo.py` | The offline half: the wrapper's own tests against `StubGateway`, safe in CI |

`.stage/`, `.aws-sam/`, `out/`, and `.env-vars.json` are build and run artifacts, and are
gitignored.
