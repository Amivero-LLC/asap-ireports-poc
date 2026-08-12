# Orchestration Landscape Scan

**Milestone 1b** · **Date of scan: 2026-08-10** · **Status: complete — feeds ADR-012**

The candidate set in ADR-012 was drawn from `blueprint.md` §9, written before this project started.
This scan exists to check that set against the field as it stands today, *before* spike effort is
spent. It ends in a recommended amendment to ADR-012.

> **Read this before relying on any claim below.** Every claim is tagged with how it was
> established. `[measured]` means we ran it on this machine and the number is reproducible.
> `[first-party]` means it comes from the project's own source code, package metadata, or official
> documentation, and the URL is in §11. `[secondary]` means a third party said it and we did not
> independently confirm it. `[unverified]` means we could not confirm it and it should be treated as
> an open question, not a fact.

---

## 1. Method, and what this scan is not

**What we did.**

- Pulled exact release metadata, licences, and dependency lists from the PyPI JSON API for every
  candidate `[first-party]`.
- Pulled repository activity — commits in the trailing 90 days, contributor counts, archive status —
  from the GitHub API `[measured]`.
- Read the actual source of the persistence, session, and interrupt modules at the exact released
  tag, rather than trusting documentation or blog summaries `[first-party]`. This changed two
  conclusions.
- Built a clean virtual environment per candidate and measured the installed footprint `[measured]`.
- Queried OSV for known vulnerabilities and pulled the fixed-version ranges, so that advisory counts
  are not reported without saying whether current versions are affected `[first-party]`.

**What this scan cannot tell us.** Nothing here measures resume *correctness*, serialized state
size under a realistic run, test determinism, or developer comprehension. Those are behavioural
properties and only the Milestone 1c spike can settle them. This scan narrows the set; it does not
pick the winner. §10 lists exactly what remains unanswerable by reading.

**Measurement environment.** macOS 15 (Darwin 25.5.0), arm64; Python 3.12.13; `uv` 0.7.21;
2026-08-10. Footprint figures are a *proxy* for a Lambda deployment package, not equal to one —
Lambda targets Linux and a different architecture, and wheels differ. Treat them as comparative,
not absolute.

---

## 2. What has changed since the blueprint was written

Four changes are material enough that the blueprint's §9 comparison table should not be relied on
as written.

**AutoGen and Semantic Kernel no longer exist as independent choices.** Microsoft merged both into
the **Microsoft Agent Framework**, which reached 1.0 GA for Python and .NET in April 2026; AutoGen
and Semantic Kernel moved to maintenance mode — security patches and critical fixes, no new
features `[secondary]`. Blueprint §9.2 evaluates both as live options. They are not.

**Pydantic Graph removed its persistence layer.** This is the single most consequential finding in
this scan and it inverts a blueprint recommendation. Detail in §5.3.

**The Strands repository was restructured.** `strands-agents/sdk-python` now redirects to
`strands-agents/harness-sdk`, a monorepo carrying the Python SDK, the TypeScript SDK, and an MCP
server, released under tags like `python/v1.51.0` `[first-party]`. Along the way
`strands-agents/sdk-typescript`, `strands-agents/docs`, `strands-agents/mcp-server`, and
`strands-agents/agent-builder` were **archived** `[first-party]`. The framing also shifted from
"agent SDK" to "agent harness." This is consolidation rather than abandonment — the monorepo is the
most active repository in the set — but any blueprint URL pointing at `sdk-python` or the old docs
repo is stale.

**Amazon Bedrock AgentCore is now available in AWS GovCloud (US-West)**, as of 2026-05-05, with a
documented list of feature gaps `[first-party]`. The blueprint predates this. It does not add a
bake-off candidate — AgentCore is a managed runtime, not a Python orchestration library — but it
changes the deployment picture and bears directly on ADR-004 and Q-01. See §8.4.

---

## 3. The constraints we are actually evaluating against

Not a generic framework comparison. These come from `docs/DECISIONS.md` and are non-negotiable
unless an ADR supersedes them.

| # | Constraint | Source | Why it eliminates things |
|---|---|---|---|
| C1 | **Bounded loops, not open-ended agency** | ADR-012, blueprint §3.5, §8.5 | Frameworks whose core abstraction is a conversational team or a role-playing crew push toward open-ended iteration. We need a fixed graph with enforced call, tool, token, and wall-clock ceilings. |
| C2 | **Durable checkpoint + resume in a separate process** | ADR-012 spike leg 1, ADR-013 | The run model must not assume one in-process execution. A framework whose persistence is in-memory or single-process cannot satisfy this without us writing the persistence layer. |
| C3 | **Human-in-the-loop interrupt as a state transition** | ADR-011 | Pause mid-run, record a disposition out of band, resume. Not a UI convention and not bypassable. The framework needs a first-class interrupt primitive whose pending state survives the checkpoint. |
| C4 | **PostgreSQL is the system of record for workflow state** | `CLAUDE.md`, ADR-006 | A Postgres-backed checkpoint store is strongly preferred first-party. File and S3 session stores are a mismatch we would have to bridge. |
| C5 | **AWS Lambda packaging, GovCloud target** | ADR-004, blueprint §14 | Deployment footprint and cold start matter. A framework requiring a long-running supervisory process is a poor fit for the Lambda adapter. |
| C6 | **Bedrock via LiteLLM, model referenced only by alias** | ADR-008 | The framework must not hard-bind a provider SDK. It must accept an OpenAI-compatible base URL or a pluggable provider. |
| C7 | **OpenTelemetry, framework-neutral** | `CLAUDE.md`, blueprint §4.1.10 | Traces carry identifiers and outcomes only. Raw case text must never reach a trace or a log. |
| C8 | **Deterministic testability** | ADR-009 | With no offline profile, unit and contract tests mock at the gateway boundary. Control flow must be inspectable and assertable without invoking a model. |
| C9 | **No raw case text to third-party telemetry** | `CLAUDE.md`, blueprint §13 | Case files may contain PII, SPII, personnel-security information, and CUI. Any vendor telemetry path is a control to be verified and disabled, not a default to be accepted. |

---

## 4. Measured footprint and repository health

### 4.1 Installed footprint `[measured]`

Clean `uv` virtual environment per row, Python 3.12, macOS arm64, 2026-08-10. "Baseline" is the
hand-rolled stack: contracts, a Postgres driver, an HTTP client, and OTel — the floor any candidate
is measured against.

| Configuration | Distributions | site-packages | Δ over baseline |
|---|---:|---:|---:|
| **Baseline** — `pydantic`, `psycopg[binary,pool]`, `httpx`, `opentelemetry-sdk` | 17 | 28 MB | — |
| **LangGraph** — `langgraph`, `langgraph-checkpoint-postgres`, `psycopg`, `httpx`, `opentelemetry-sdk` | 42 | 46 MB | +25 dists, +18 MB |
| **LangGraph + `langchain-openai`** | 47 | 46 MB | +30 dists, +18 MB |
| **PydanticAI** — `pydantic-ai-slim[openai]`, `psycopg`, `opentelemetry-sdk` | 35 | 54 MB | +18 dists, +26 MB |
| **Strands** — `strands-agents`, `opentelemetry-sdk` | 47 | 62 MB | +30 dists, +34 MB |
| **MS Agent Framework — `agent-framework-core`** | 9 | 11 MB | −8 dists, −17 MB |
| **MS Agent Framework — `agent-framework` (meta)** | 203 | **677 MB** | +186 dists, +649 MB |

Three things worth pulling out.

- **The hand-rolled baseline is genuinely small.** 17 distributions and 28 MB is the honest cost of
  the alternative, and no candidate is within 18 MB of it. This strengthens the hand-rolled entry in
  ADR-012 rather than weakening it.
- **`agent-framework` the meta-package is a trap, not a verdict.** Its 677 MB is dominated by
  `claude_agent_sdk` (274 MB) and `copilot` (148 MB) — optional integrations pulled in by the
  convenience package. The fair number is `agent-framework-core` at 11 MB and 9 distributions, which
  is the *smallest* of any framework measured. Reporting the 677 MB figure without this correction
  would misrepresent the framework.
- **Strands carries server dependencies in its core.** `boto3`, `botocore`, `mcp`, `starlette`,
  `uvicorn`, `cryptography`, and `watchdog` are non-optional `[first-party]`. `boto3` is partly free
  in a Lambda context since the runtime ships it, but `starlette`/`uvicorn` in a library core is
  weight we would carry without using.

### 4.2 Repository health `[measured]`

GitHub API, 2026-08-10. "Commits/90d" is the trailing 90 days.

| Project | Repository | Stars | Commits/90d | Contributors | Licence | Latest release |
|---|---|---:|---:|---:|---|---|
| LangGraph | `langchain-ai/langgraph` | 39,390 | 189 | 277 | MIT | `langgraph` 1.2.10 (2026-07-28) |
| Strands | `strands-agents/harness-sdk` | 6,870 | 692 | 251 | Apache-2.0 | `python/v1.51.0` (2026-08-07) |
| PydanticAI | `pydantic/pydantic-ai` | 19,199 | 657 | 475 | MIT | 2.27.0 (2026-08-08) |
| MS Agent Framework | `microsoft/agent-framework` | 12,718 | 682 | 196 | MIT | 1.0 GA April 2026 `[secondary]` |
| OpenAI Agents SDK | `openai/openai-agents-python` | 28,544 | 492 | 334 | MIT | — |
| Google ADK | `google/adk-python` | 21,067 | 1,033 | 404 | Apache-2.0 | — |
| Burr | `apache/burr` | 2,506 | 50 | 50 | — | — |
| DBOS | `dbos-inc/dbos-transact-py` | 1,519 | — | — | MIT | — |

All candidate licences are permissive (MIT or Apache-2.0). No candidate has a licence that
constrains federal use, and none is archived.

Read LangGraph's 189 commits/90d against its 39k stars carefully: **low commit volume post-1.0 is
the expected shape of a project honouring a no-breaking-changes commitment**, not evidence of
neglect. Strands, PydanticAI, MS Agent Framework, and ADK are all in the 650–1,000 range, which is
the signature of pre-consolidation churn. For a program that must pin versions and defend them
through an ATO, low churn on a stable API is an asset.

---

## 5. Candidate assessment

### 5.1 LangGraph — **confirmed, remains the incumbent to beat**

`langgraph` 1.2.10, MIT, Python ≥3.10. Resolved for this scan: `langgraph` 1.2.10,
`langgraph-checkpoint` 4.2.0, `langgraph-checkpoint-postgres` 3.1.2, `langchain-core` 1.5.3,
`langsmith` 0.10.17 `[measured]`.

**Against our constraints.**

- **C2/C4 — the strongest fit in the set.** `langgraph-checkpoint-postgres` is a first-party,
  MIT-licensed package providing `PostgresSaver` and `AsyncPostgresSaver` `[first-party]`. Resume in
  a new process is by design: pass the same `thread_id` in the config and the graph rehydrates from
  the checkpoint `[first-party]`. This is exactly ADR-012 spike leg 1, and it is the only candidate
  where Postgres checkpointing is a supported first-party package rather than something we build.
  Documented caveat: `PostgresSaver` stores `thread_id` in a length-limited column — keep thread IDs
  under 255 characters `[first-party]`.
- **C3** — interrupt-and-resume against a persistent thread ID is the framework's own model for
  human-in-the-loop `[first-party]`.
- **C5** — 42 distributions / 46 MB; AWS publishes prescriptive guidance for LangChain and LangGraph
  `[first-party]`. Fits a Lambda zip with room, subject to Linux-wheel verification.
- **API stability — materially better than the blueprint could have known.** LangGraph 1.0 GA'd in
  October 2025 `[secondary]`. The published release policy commits to semver with breaking changes
  only in major releases, major releases spaced at least 6–12 months, and 1.0 remaining ACTIVE until
  2.0 with at least a year of MAINTENANCE afterwards `[first-party]`. For a program that must pin
  and defend versions, this is the most valuable single property in this scan. It also directly
  answers blueprint §9.2's "API evolution must be pinned" caveat.

**Real costs, stated plainly.**

- **`langchain-core` and `langsmith` are mandatory transitive dependencies**, not optional.
  `langchain-core` 1.5.3 declares `langsmith<1.0.0,>=0.3.45` as a hard requirement `[first-party]`.
  Blueprint §9.2 says LangGraph "can be used without broader LangChain" and warns that managed
  LangSmith features "should not become a hidden dependency." The first is true of `langchain`, not
  of `langchain-core`; the second is a live concern — LangSmith is in the dependency tree whether we
  use it or not. On the C9 question that actually matters, tracing is **opt-in**: LangSmith's
  `tracing_is_enabled` returns false absent an explicit context override, an active run tree, a
  configured global, or the environment variable `[first-party]`. So the default is not egress. But
  a mandatory client library capable of exporting run content into a system that may carry CUI is a
  control to be *verified and pinned closed* — an egress-deny test plus an explicit disabling
  environment variable — not a default to be trusted. **This is a required spike deliverable, not a
  footnote.**
- **A recurring class of deserialization vulnerabilities on the checkpoint path.** Four advisories
  since November 2025 land on exactly the component we would depend on most:
  `GHSA-wwqv-p2pp-99h5` (RCE in JsonPlusSerializer "json" mode, fixed 3.0.0), `GHSA-mhr3-j7m5-c7c9`
  (BaseCache untrusted deserialization → RCE, fixed 4.0.0), `GHSA-g48c-2wqr-h844` (unsafe msgpack
  deserialization in checkpoint loading, fixed `langgraph` 1.0.10), and `GHSA-fjqc-hq36-qh5p`
  (unsafe JSON deserialization in checkpoint loading, fixed 4.1.1) `[first-party]`.
  **The versions we would use are patched** — we resolve `langgraph` 1.2.10 and
  `langgraph-checkpoint` 4.2.0, both above every fixed version. The finding is not "LangGraph is
  insecure." It is that **the checkpoint blob is a deserialization trust boundary**, it has been
  exercised repeatedly, and our architecture must treat the checkpoint store as a security-relevant
  asset — integrity-controlled, access-controlled, never fed from anything outside our own Postgres.
  That obligation is framework-independent and applies equally to a hand-rolled checkpointer.
  `langchain-core` and `langsmith` also carry their own advisory histories, including SSRF and file
  read `[first-party]`; a pinned dependency set with `pip-audit` in CI is a hard requirement, which
  `CLAUDE.md` already mandates.

**Verdict: confirmed.** The only candidate that satisfies C2, C3, and C4 out of the box, and the
only one with a written stability commitment. Its costs are real, bounded, and testable.

### 5.2 Strands Agents SDK — **confirmed, with amended rationale**

`strands-agents` 1.51.0 (2026-08-07), Apache-2.0, Python ≥3.10 `[first-party]`.

**What we confirmed by reading the source at tag `python/v1.51.0`, not the docs.**

- **A real human-in-the-loop primitive exists.** `strands-py/src/strands/interrupt.py` defines
  `Interrupt` (id, name, reason, response), `InterruptException`, and an `_InterruptState` tracking
  raised interrupts with an `activated` flag and a version counter. `Interrupt.to_dict()` exists
  explicitly "to serialize to dict for session management" `[first-party]`. This is a genuine C3
  primitive, and better than the blueprint could have asserted.
- **Session backends are file, S3, and snapshot — there is no PostgreSQL backend.**
  `strands-py/src/strands/session/` contains `file_session_manager.py`, `s3_session_manager.py`,
  `repository_session_manager.py`, `snapshot_session_manager.py`, and the `session_repository.py`
  interface; `strands-py/src/strands/storage/` contains in-memory, local-file, and S3 backends
  `[first-party]`. Meeting **C4** means implementing `SessionRepository` against Postgres ourselves.
  That is a bounded, well-defined piece of work against a published interface — but it is work, and
  it is the load-bearing work.
- **Multi-agent persistence exists.** `multiagent/graph.py` and `multiagent/swarm.py` are present,
  and the feature request for a multi-agent session manager covering graph and swarm patterns closed
  in November 2025 `[first-party]`.
- **Lambda packaging is genuinely first-class** — official deployment documentation plus a published
  Lambda layer ARN `[first-party]`. This is the AWS-alignment argument in ADR-012, and it holds.

**The open question that matters most, stated fairly.** A Diagrid engineering blog (2026-03-02)
argues that Strands persists *conversation state* rather than *execution state*: "conversation
restore is not execution resume" — a crashed agent reloading the same session recovers message
history but restarts inference, and graph failures reset rather than resume from the failure point.
It also notes `FileSessionManager` lacks locking for concurrent access `[secondary]`. **Diagrid
sells a competing durable-execution product, so this is an interested source and we have not
independently confirmed the resume behaviour** `[unverified]`. But the concurrency caveat is
corroborated by Strands' own documentation `[secondary]`, and the distinction it draws is precisely
what ADR-012 spike leg 1 exists to measure. **This is the single highest-value thing the Strands
spike must settle**, and it should be tested directly: kill the process mid-node and assert on
whether completed work is re-executed.

**On C6.** Strands pins its optional LiteLLM extra to `litellm<=1.95.0,>=1.75.9` `[first-party]` —
an upper bound on a component we depend on. This mostly does not bind us: ADR-008 uses LiteLLM as a
**proxy server**, so application code talks to an OpenAI-compatible endpoint and never imports the
`litellm` package. Worth recording so nobody adopts the in-process extra by reflex and inherits the
pin.

**Verdict: confirmed, with the rationale amended.** ADR-012 lists it for AWS alignment and Lambda
packaging; both hold. Add that it has a real interrupt primitive, that Postgres session storage is
ours to build, and that whether it resumes *execution* or merely restores *conversation* is the
question its spike must answer.

### 5.3 PydanticAI / Pydantic Graph — **recommend dropping as an orchestrator candidate**

This is the amendment that changes the shape of Milestone 1c, so the evidence is given in full.

**Pydantic Graph 2.x has no state-persistence API at all.** Verified three ways at the exact
released tag `[first-party]`:

1. The module listing for `pydantic_graph/pydantic_graph` at `v2.27.0` contains no `persistence`
   directory. Requesting that path returns `Not Found`.
2. The same listing at `v1.107.2` — the 1.x line, still being published alongside 2.x — **does**
   contain `persistence/`, holding exactly `file.py` and `in_mem.py`.
3. `pydantic_graph/__init__.py` at `v2.27.0` exports no persistence, snapshot, checkpoint, or resume
   symbol, and grepping `graph_builder.py`, `step.py`, `paths.py`, and `node.py` for
   `persist|snapshot|checkpoint|resume` returns nothing.

Two conclusions follow. First, **even in 1.x the only persistence backends were a local file and
in-memory** — never Postgres, so **C4** was never met. Second, **2.x removed the layer entirely**
as part of a rewrite around `GraphBuilder`, `Decision`, `Join`, and `Step`.

Durability moved instead to `pydantic_ai/durable_exec/`, which at `v2.27.0` contains exactly three
subpackages: `dbos`, `prefect`, and `temporal` `[first-party]`. Pydantic's own documentation
confirms Temporal, DBOS, Prefect, and Restate as the supported durable-execution backends
`[first-party]`. **This is a deliberate architectural position: PydanticAI does not implement
durable execution, it delegates it.** Adopting PydanticAI as our orchestrator therefore means
adopting Temporal, DBOS, or Prefect as an *additional* runtime component — a substantially larger
decision than "pick an orchestration library," and one nothing in `docs/DECISIONS.md` contemplates.

**The consequence for our spike is decisive.** Spike leg 1 is "durable checkpoint and resume in a
separate process." With no persistence layer, PydanticAI cannot attempt leg 1 unless we either write
the entire persistence layer ourselves — at which point the candidate *is* the hand-rolled baseline
plus a dependency, and the spike measures nothing new — or introduce a workflow engine we have not
decided to adopt. Neither produces a comparable scorecard row.

**Release cadence and API stability compound this.** Versions 2.21.0 through 2.27.0 shipped between
2026-07-30 and 2026-08-08 — seven minor releases in nine days — while a parallel 1.x line
(`1.107.2`) was published on 2026-08-08, the same day as 2.27.0 `[measured]`. A near-daily minor
cadence with a concurrent breaking major rewrite is the opposite of what a version-pinning,
ATO-bound program wants underneath its hardest-to-reverse component. Pydantic's own documentation
describes graphs as "designed for advanced users" and cautions "don't use a nail gun unless you need
a nail gun" `[first-party]`.

**None of this argues against Pydantic v2.** `CLAUDE.md` already commits to Pydantic v2 for
contracts, and that is unaffected and correct. PydanticAI also remains available as a *typed
agent-and-tool layer inside* whichever orchestrator wins — its typed tool schemas and structured
outputs compose with LangGraph nodes or hand-rolled nodes without being the orchestrator. Blueprint
§9.2's advice to "use Pydantic models throughout" survives intact; only "evaluate as alternate
orchestrator" does not.

**Verdict: drop from the bake-off set.** Retained as a contracts library (already decided) and as an
optional typed node-level layer. Recorded as evaluated-and-rejected with the reason above — a
rejected candidate with a recorded reason is a handoff artifact (ADR-001).

### 5.4 Hand-rolled Python on PostgreSQL — **confirmed, and its case is stronger than assumed**

ADR-012 calls this "the honest baseline." The evidence supports promoting it from a control to a
serious contender.

- **The footprint gap is large.** 17 distributions and 28 MB, against 42–47 and 46–62 MB `[measured]`.
  That is fewer moving parts to pin, audit, `pip-audit`, and defend.
- **Every constraint it must satisfy, it satisfies by construction.** C1 (bounded loops), C7
  (framework-neutral OTel), C8 (deterministic testability), and C9 (no third-party telemetry in the
  tree at all) are free. C4 is native — Postgres is already our system of record, so the checkpoint
  table lives beside the run state rather than in a parallel store with its own consistency story.
- **The scan surfaced a reason the gap may be narrower than it looks.** The deserialization
  advisories in §5.1 show that a checkpoint store is a security-relevant trust boundary requiring
  deliberate design regardless of who writes it. A framework does not remove that obligation; it
  relocates it into code we do not control and must track advisories for.
- **The real risk is unchanged and should not be soft-pedalled.** What looks like "a few hundred
  lines" tends to grow once bounded parallel fan-out with join and de-duplication, cancellation,
  no-progress detection, budget enforcement, and partial-failure resume are all real. That is the
  measurement, and it is exactly what spike leg 4 exists to produce.

**Verdict: confirmed, and weighted up.** If it lands within a few hundred lines with clean resume
semantics, that is the finding — and it carries no framework lifecycle risk, no mandatory vendor
telemetry client, and no external advisory surface.

---

## 6. Frameworks considered and not taken forward

| Framework | Status | Reason |
|---|---|---|
| **Microsoft Agent Framework** | **Considered; not spiked** | Closest HITL semantics in the field to blueprint §8 — `ctx.request_info()` with a `@response_handler`, pending requests saved *into* the checkpoint, re-emitted as `RequestInfoEvent` on restore, and `workflow.run(checkpoint_id=..., responses=...)` to resume and answer in one call `[first-party]`. `agent-framework-core` is also the lightest framework measured at 9 distributions / 11 MB `[measured]`, MIT, 1.0 GA April 2026 `[secondary]`. **Excluded on ecosystem alignment, not capability:** it is Azure-oriented with no Bedrock-first path, against a GovCloud/Bedrock program (ADR-004, ADR-008). The same Diagrid critique applied to Strands also targets it — resume requires an explicit `checkpoint_id`, there is no supervisory restart, and concurrent resumption of one checkpoint is unguarded by distributed locking `[secondary]`, `[unverified]`. **Recorded because its request/response checkpoint model is the design to steal from** when we specify our own human-review interrupt, whichever framework wins. |
| **AutoGen** | **Removed from consideration** | Maintenance mode since April 2026; merged into Microsoft Agent Framework `[secondary]`. Blueprint §9.2 evaluates it as live. It is not. |
| **Semantic Kernel** | **Removed from consideration** | Same merger, same status `[secondary]`. |
| **DBOS** | **Considered; not spiked** | Genuinely attractive on C4 — durable execution checkpointed to Postgres, in-library with no extra infrastructure, MIT `[first-party]`. Two disqualifiers for M1. It **requires a long-running process and is not designed for stateless serverless environments** `[first-party]`, which conflicts with C5 and the ADR-004 Lambda adapter; and at 1,519 stars it is a materially smaller project than anything else here `[measured]`. Worth revisiting if the Lambda adapter is ever dropped, or if PostgreSQL-native durable execution becomes the deciding factor. |
| **Temporal / Restate** | **Considered; not spiked** | Same category as DBOS: durable-execution substrates, not agent orchestrators. Both require a server or engine we have not decided to adopt. Blueprint §9 omits this category entirely; recording it so the handoff shows it was considered. |
| **OpenAI Agents SDK** | **Not a candidate** | Provider-shaped, and its durable story is again Temporal `[secondary]`. Session persistence is conversation-item persistence, the same C2 mismatch as §5.2. |
| **Google ADK** | **Not a candidate** | Highest commit volume measured (1,033/90d) but GCP-aligned, against an AWS GovCloud target. |
| **Claude Agent SDK** | **Not a candidate** | Unchanged from ADR-012. Optimised for open-ended coding agency, not a bounded adjudicative graph (C1). |
| **Haystack, LlamaIndex Workflows, CrewAI** | **Not candidates** | Unchanged from ADR-012 and blueprint §9.2. Haystack and LlamaIndex add a second retrieval abstraction over the OpenSearch adapter ADR-007 already defines; CrewAI's role/crew model conflicts with C1. |
| **Burr** | **Noted** | Moved to the Apache Software Foundation (`apache/burr`). 50 commits/90d — an order of magnitude below every other project measured `[measured]`. Not enough momentum to bet a program on. |

---

## 7. Bedrock AgentCore — a deployment option, not a bake-off candidate

**Amazon Bedrock AgentCore became available in AWS GovCloud (US-West) on 2026-05-05**
`[first-party]`. AWS's GovCloud user guide documents the differences: AgentCore Gateway has no
semantic search; AWS Agent Registry (Preview), Bedrock Guardrails Policy, and Temporal Policy are
unavailable; and six CloudFormation resource types — including `Policy`, `PolicyEngine`,
`Evaluator`, `OnlineEvaluationConfig`, and both credential-provider types — are not available
`[first-party]`. The same page carries export-control language stating that AgentCore metadata **is
not permitted to contain export-controlled data**, and enumerates the customer-initiated
configurations under which data-plane traffic leaves the GovCloud partition `[first-party]`. For a
system handling CUI and personnel-security information, that paragraph is a design constraint, not
boilerplate.

AWS Step Functions also added an AgentCore-powered agentic reasoning step in June 2026 `[secondary]`.

**This does not change the M1 candidate set** — AgentCore is a managed runtime, not a Python
orchestration library, and ADR-004 commits to local-first development with a Lambda/SAM adapter.
It matters for three reasons, and belongs in the handoff regardless of what M1 decides:

1. It is a live alternative to the Lambda adapter for the eventual production deployment, in the
   target partition, and it did not exist when the blueprint was written.
2. Its GovCloud feature gaps are the first concrete, citable evidence for **Q-01** — which
   `docs/OPEN-QUESTIONS.md` correctly refuses to assume. This is adjacent evidence about the Bedrock
   service family, **not** an answer to Q-01. Q-01 asks about Claude model availability, concrete
   model and inference-profile IDs, and cross-region inference rules, and remains open.
3. Its export-control and data-routing language bears directly on ADR-004's data-routing risk and
   should be read by whoever resolves Q-01.

Recorded as **Q-14** in `docs/OPEN-QUESTIONS.md`: whether AgentCore Runtime is an approved or
preferred deployment target for this program, since the answer changes what the Lambda adapter is
for. Recorded as an open question with a stated assumption (ADR-004 stands), not as a decision.

---

## 8. Recommended amendment to ADR-012

**Confirmed, unchanged:** LangGraph · Strands Agents SDK · hand-rolled Python.

**Dropped:** PydanticAI / Pydantic Graph as an orchestration candidate — Pydantic Graph 2.x has no
state-persistence API, 1.x had only file and in-memory backends, and durability is delegated to
Temporal/DBOS/Prefect. It cannot attempt spike leg 1 without either becoming the hand-rolled
baseline or importing a workflow engine we have not adopted. Retained for contracts (already
decided) and available as a typed node-level layer inside the winner.

**Added:** nothing. The scan deliberately **reduces the spike from four candidates to three.**

That reduction is the recommendation, not an accident of it. Three candidates is a better spike than
four: the freed effort goes into the legs where the answer is actually unknown — resume correctness
under a mid-node process kill, and whether Strands resumes execution or merely restores
conversation. A fourth candidate that cannot attempt leg 1 would produce a scorecard row that reads
as a comparison but is not one.

**Also recorded for the handoff:** AutoGen and Semantic Kernel removed from the "also considered"
list (both in maintenance mode, merged into Microsoft Agent Framework); Microsoft Agent Framework,
DBOS, Temporal, and Restate added to it with reasons; Bedrock AgentCore recorded as a deployment
option with a proposed Q-14.

---

## 9. What the spike must settle that reading cannot

Carried into Milestone 1c. Each is a behavioural property no amount of documentation resolves.

1. **Does Strands resume *execution* or restore *conversation*?** (§5.2) Kill the process mid-node
   and assert on whether completed work re-executes. The highest-value single measurement in the
   bake-off, and it applies to LangGraph too — assert it, do not assume it.
2. **What does a Postgres `SessionRepository` for Strands actually cost?** Lines of code and
   correctness under concurrent access, given the documented absence of locking in the file backend.
3. **Can LangSmith be pinned closed?** An egress-deny test proving no LangSmith network call occurs
   in a default-configured run, plus the explicit environment configuration that guarantees it.
   Required deliverable, per C9.
4. **Serialized checkpoint size under a realistic run**, for all three, against blueprint §8.2's
   identifiers-not-transcripts state model.
5. **Does the hand-rolled checkpointer stay small** once bounded fan-out with join and
   de-duplication, cancellation, no-progress detection, and budget enforcement are all real?
6. **Cold start and Linux-wheel footprint under SAM local**, since §4.1 measured macOS arm64.
7. **Checkpoint-store threat model**, framework-independent, informed by §5.1's advisory pattern:
   who can write a checkpoint, what deserializes it, and what happens if the row is tampered with.

---

## 10. Sources

Retrieved 2026-08-10 unless noted.

**Package and repository metadata** (PyPI JSON API and GitHub REST API, queried directly)
- `https://pypi.org/pypi/langgraph/json`, `.../langgraph-checkpoint-postgres/json`,
  `.../langchain-core/json`, `.../strands-agents/json`, `.../pydantic-ai/json`,
  `.../pydantic-ai-slim/json`, `.../pydantic-graph/json`
- `https://api.github.com/repos/{langchain-ai/langgraph, strands-agents/harness-sdk,
  pydantic/pydantic-ai, microsoft/agent-framework, openai/openai-agents-python, google/adk-python,
  apache/burr, dbos-inc/dbos-transact-py}`

**Source read at released tags**
- Pydantic Graph module listings at `v2.27.0` and `v1.107.2`; `pydantic_graph/__init__.py` at
  `v2.27.0`; `pydantic_ai/durable_exec/` at `v2.27.0` —
  `https://github.com/pydantic/pydantic-ai`
- Strands `interrupt.py`, `session/`, `storage/`, `multiagent/` at `python/v1.51.0` —
  `https://github.com/strands-agents/harness-sdk`
- `langsmith/utils.py::tracing_is_enabled` as installed from `langsmith` 0.10.17

**Official documentation**
- LangGraph persistence — `https://docs.langchain.com/oss/python/langgraph/persistence`
- LangChain/LangGraph release policy — `https://docs.langchain.com/oss/python/release-policy`
- Pydantic AI durable execution — `https://pydantic.dev/docs/ai/integrations/durable_execution/overview/`
- Pydantic Graph — `https://pydantic.dev/docs/ai/graph/graph/`
- Strands Lambda deployment — `https://strandsagents.com/docs/user-guide/deploy/deploy_to_aws_lambda/`
- Microsoft Agent Framework HITL — `https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop`
- DBOS Python programming guide — `https://docs.dbos.dev/python/programming-guide`
- Bedrock AgentCore in GovCloud — `https://docs.aws.amazon.com/govcloud-us/latest/UserGuide/govcloud-bedrock-agentcore.html`
- AgentCore GovCloud launch (2026-05-05) — `https://aws.amazon.com/about-aws/whats-new/2026/05/bedrock-agentcore-launch-aws-govcloud-us/`
- AWS prescriptive guidance, agentic AI frameworks —
  `https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/`

**Vulnerability data** — OSV API (`https://api.osv.dev/v1/`), advisory IDs quoted inline with their
fixed-version ranges.

**Secondary, interested, or unconfirmed**
- Diagrid, "Still Not Durable: How Microsoft Agent Framework and Strands Agents Repeat the Same
  Mistake," 2026-03-02 — **vendor of a competing durable-execution product**. Its central claim
  about Strands resume behaviour is `[unverified]` and is carried into §9 as a spike measurement,
  not accepted as fact.
- Microsoft Agent Framework 1.0 GA date, AutoGen/Semantic Kernel maintenance status, LangGraph 1.0
  GA date, Step Functions AgentCore integration — established from secondary coverage. The
  underlying stability *policy* is `[first-party]`; the GA *dates* are `[secondary]` and should be
  confirmed against vendor release notes before the handoff is treated as authoritative.
