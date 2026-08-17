# Architecture

How iReports is shaped and why. Written for a developer who has to build this on the government
side — enough to make the design decisions legible, not an exhaustive specification.

**This is a proof of concept.** Parts of it run against real models today; parts are designed and
not built. § What exists says which is which, and it is the section most worth keeping current.

---

## What the system does

A case is ready. iReports analyzes it against named adjudicative criteria and emits a validated
envelope of **proposed findings**, each one traceable to evidence in the record. An authorized
officer reviews those proposals in ASAP.

That is the whole job. It is deliberately narrow at both ends: iReports does not ingest documents,
and it does not decide anything.

```mermaid
flowchart LR
    subgraph NOT_OURS1["AWS ingestion pipeline"]
        UP[upload] --> EX[extract] --> CH[chunk] --> IX[(vector collection)]
    end

    subgraph OURS["iReports"]
        CR[criteria from the case] --> SP[specialists, one per criterion]
        SP --> SY[cross-criterion synthesis]
        SP --> VA[validators]
        SY --> VA
        VA --> EN[envelope]
    end

    subgraph NOT_OURS2["ASAP"]
        RV[officer review] --> DEC[determination]
    end

    IX -.retrieve.-> SP
    CR -->|one invocation, no pause| EN
    EN ==>|proposals| RV

    style OURS fill:#e8f0fe,stroke:#1a73e8
    style NOT_OURS1 fill:#f5f5f5,stroke:#9aa0a6
    style NOT_OURS2 fill:#f5f5f5,stroke:#9aa0a6
```

**Three boundaries worth being precise about:**

| Boundary | Who owns it |
|---|---|
| Upload → extract → chunk → index | The AWS ingestion pipeline. We consume the collection, we do not populate it |
| Analysis → proposals | **Ours.** Starts at "the case is ready," ends at a validated envelope |
| Review → determination | ASAP. iReports has no reviewer surface, no pause, and records no human decision |

---

## The one idea that shapes everything

**A deterministic shell around probabilistic reasoning.**

The model reasons. It does not decide control flow, and it does not decide whether its own output is
valid. Everything load-bearing is ordinary code:

```mermaid
flowchart TD
    A[criterion + retrieved spans] --> B[model call via port]
    B -->|refused or transport error| N[criterion NOT analysed<br/>run continues]
    B --> C{known shape?}
    C -->|coercible| C2[normalize: string, bare object,<br/>envelope nested in itself]
    C -->|no| R1[reject, record what it was]
    C2 --> D
    C -->|yes| D{citations resolve<br/>to spans it was shown?}
    D -->|no| R2[drop finding, record why]
    D -->|yes| E{passes contract?}
    E -->|no| R3[reject, record why]
    E -->|yes| F[ProposedFinding]
    R1 --> G[rejection record<br/>capped, with a count]
    R2 --> G
    R3 --> G
    N --> G
    F --> H[envelope]
    G --> H

    style B fill:#fef7e0,stroke:#f9ab00
    style F fill:#e6f4ea,stroke:#137333
    style G fill:#fce8e6,stroke:#c5221f
    style N fill:#fce8e6,stroke:#c5221f
```

Only the yellow box is probabilistic. Shape coercion, citation validation, containment of a
refusal, and the decision-support language guard are all deterministic code. **Budget and loop
limits belong on this diagram and are not on it, because they are not built** — see
[`ROADMAP.md`](ROADMAP.md) item 4.

Two paths here exist because they were once missing. A refusal used to propagate and kill the whole
run, discarding every other specialist's paid-for work; and a response whose `findings` array
arrived as a JSON string was rejected as unparseable rather than coerced. Both are in
[`LESSONS.md`](LESSONS.md).

**The rejection record is output, not error logging.** It ships with the run. A pipeline that hides
its rejections looks cleaner and tells you nothing about where its safety lives.

---

## Two rules that are not negotiable

### 1. Evidence before inference

Every material factual statement in a finding carries a citation to a case evidence span, and the
citation is **checked against the case** before the finding is constructed. A finding citing
evidence that is not in the record is **dropped**, not repaired — trimming the bad citation would
leave an observation standing on evidence nobody can open.

This is the product. A finding an adjudicator cannot trace to a document is worse than no finding.

### 2. The decision-support boundary

The system never grants, denies, revokes, or suspends anything. Structurally:

- **No aggregate risk score.** No "risk level" field exists on any contract.
- **`ProposedFinding` is the only finding type.** Nothing promotes it.
- **No contract models a human decision** — no disposition, approval, or sign-off field.
- **Every envelope is pinned `machine_generated: true`.**
- **Determinative language is rejected** on every narrative field, whoever wrote it.

The prompt asks for decision-support phrasing. The *type* enforces it. When a model wrote "the
subject violated SEAD-4," the prompt had already failed and the type is what stopped it.

---

## Components

```mermaid
flowchart TB
    subgraph WRAP["spikes/lambda_demo — the runnable wrapper, no analysis in it"]
        HAND["handler.py<br/>one invocation, one run"]
        LOAD["case_loader.py<br/>disk to typed case"]
        PACK["package.py<br/>findings to ASAPEnvelope"]
    end

    subgraph ORCHP["packages/orchestration — the reference implementation"]
        PORT["port.py<br/>Orchestrator protocol, RunResult<br/>routing policy both paths share"]
        HR["handrolled.py<br/>thread pool and a loop"]
        LG["langgraph_adapter.py<br/>the only module that imports the framework"]
        CRIT["criteria.py<br/>fan-out width comes from the case"]
        SPEC["specialist.py<br/>one criterion, citation-checked"]
        SYN["synthesis.py<br/>overlap computed, conflicts by model"]
        COER["coercion.py<br/>response shapes, rejection caps"]
    end

    subgraph PORTS["packages/ — the boundary to everything outside"]
        GW["gateway/<br/>ModelGateway, the only caller of a model"]
        RETR["retrieval/<br/>Retriever, every field name in mapping.py"]
    end

    DOM["packages/domain/ — 12 contracts + generated JSON Schema<br/>the vocabulary every box above speaks"]

    subgraph OUTSIDE["Not ours"]
        PROXY["LiteLLM proxy, resolves alias to model id"]
        OS[("OpenSearch")]
    end

    ENV[("ASAPEnvelope<br/>spikes/lambda_demo/out/")]

    EVAL["evals/scorers/properties.py<br/>scores saved runs offline, after the fact"]

    HAND --> LOAD
    HAND --> PORT
    PORT --> HR
    PORT --> LG
    HR --> CRIT
    LG --> CRIT
    HR --> SPEC
    LG --> SPEC
    HR --> SYN
    LG --> SYN
    SPEC --> COER
    SYN --> COER
    SPEC --> GW
    SYN --> GW
    SPEC --> RETR
    GW --> PROXY
    RETR --> OS
    HAND --> PACK
    PACK --> ENV
    ENV -.->|no model calls, no services| EVAL

    style ORCHP fill:#e8f0fe,stroke:#1a73e8
    style PORTS fill:#e6f4ea,stroke:#137333
    style OUTSIDE fill:#f5f5f5,stroke:#9aa0a6
    style LG fill:#fef7e0,stroke:#f9ab00
```

**What the picture is meant to show.** The wrapper at the top holds no analysis — it loads a case,
calls a port, and packages the result. Everything that reasons about a case lives in
`packages/orchestration/`, and everything that touches the outside world goes through a port. Only
the yellow box knows a framework exists, and a test enforces that against every other module in
its package.

`evals/` hangs off the envelope rather than off the run, and that is the design: it scores **saved
output**, so it costs nothing and can be re-run as the checks improve.

| Component | What it is |
|---|---|
| `packages/domain/` | 12 Pydantic v2 contracts + generated JSON Schema. The vocabulary everything else speaks |
| `packages/gateway/` | The **only** component permitted to call a model. One port, three adapters |
| `packages/retrieval/` | Hybrid vector + lexical search, mandatory case filter, every field name in one module |
| `packages/orchestration/` | Criteria routing, specialists, synthesis, and both orchestrators behind one port. **The reference implementation** |
| `spikes/lambda_demo/` | The runnable wrapper: case loading off disk, envelope packaging, Lambda handler, and the synthetic corpus |
| `spikes/lambda_fit/` | Packaging and cold-start measurement under SAM local |

---

## Two orchestration paths, on purpose

**Custom Python and LangGraph are both live** (ADR-024). Both sit behind one port; both share one
specialist implementation; both produce the same shape of output.

```python
class Orchestrator(Protocol):
    name: str
    def run(
        self, case: LoadedCase, gateway: ModelGateway, retriever: Retriever, run_id: str
    ) -> RunResult: ...
```

### How far the comparison has actually got

The orchestration started as a fixed three-node fan-out, at which shape the two paths were
indistinguishable — a fixed-width fan-out is one line in either. It is now two stages with runtime
width:

```
START ──▶ select criteria (from the case) ──▶ N specialists ──▶ synthesis ──▶ END
```

Four comparison points so far, one of them a null result:

| Change | Hand-rolled | LangGraph |
|---|---|---|
| **Runtime fan-out width** | No change — `pool.map` never cared about list length | **Structural.** Rebuilt around `Send`, because one-node-per-criterion needs the criteria known at construction |
| **Fan-in barrier for stage two** | Free — exiting the `ThreadPoolExecutor` context | Free — supersteps; a node after a `Send` waits for every dispatch |
| **Conditional routing after fan-out** | `if should_synthesize(outcomes):` | Needs a do-nothing `join` node. The naive version fires once per dispatch on partial state and **fails silently** |
| **Passing `mypy --strict`** | No change | Four suppressions, because the documented `Send` pattern matches no `add_node` overload |

The second is a null result and counts as evidence: joining was expected to favour LangGraph and
did not. The others are real asymmetries, all favouring the hand-rolled path on simplicity — though
the first is not obviously a point *against* LangGraph, since its version keeps the graph shape
constant while the work varies, which is what a checkpoint needs.

**None of the four touches durable checkpointing, which is what LangGraph was chosen for.** The
decision is not close to made.

**Still to come before it:** multi-step specialists, and crash/resume. [`ROADMAP.md`](ROADMAP.md) is ordered around exactly that, so the comparison falls
out of the work rather than needing a separate exercise, and each result lands in
[`LESSONS.md`](LESSONS.md) as it happens.

**The rule that makes this work: no module that analyzes a case may import LangGraph.** A test
enforces it. This began as insurance against lock-in; with two implementations actually running, it
is now the working arrangement.

### What it costs

Every orchestration feature is owed by both paths — budgets, loop limits, fan-out bounds, eventually
checkpointing. The mitigation is to build shared logic once, in framework-free code both
orchestrators call. Where a feature is easy in one and hard in the other, **that is the finding**,
and it belongs in `docs/LESSONS.md`.

---

## The model gateway

One port. Application code names a **tier**, never a model:

| Alias | Role |
|---|---|
| `ireports-orchestrator` | Control-flow reasoning |
| `ireports-thinking` | Deep criterion analysis |
| `ireports-fast` | Classification, extraction |

Concrete model IDs live in configuration. A partition, region, or model-generation change is a
config edit. On Bedrock the IDs carry an `anthropic.` prefix — the bare first-party ID fails.

The gateway guarantees four things, each because getting it wrong is silent:

1. **A model is named by alias, never by ID.**
2. **A refusal is never mistaken for an answer.** Refusals return HTTP 200; the adapter checks
   `stop_reason` before touching content and raises.
3. **Raw case text never reaches logs or traces.** Traces carry identifiers, versions, outcomes.
4. **Budgets are accountable.** Every call returns token counts.

See `docs/AWS.md` for the two adapters and the region constraint.

---

## Data flow, concretely

```
case.json + evidence.json
   │
   ├─▶ load and validate ──────────────── typed contracts
   │
   ├─▶ select criteria ───────────────── from requested_analyses × policy_pack_ids,
   │                                      so the fan-out width is runtime data
   │
   ├─▶ fan out, bounded by max_parallel
   │     ├── criterion A ──┐
   │     ├── criterion B ──┼── each: model call → parse → check citations → build finding
   │     └── criterion C ──┘
   │
   ├─▶ synthesis ─────────────────────── reason ACROSS criteria:
   │     ├── computed: which findings rest on the same span (set arithmetic, free)
   │     └── model:    contradictions and information gaps
   │
   ├─▶ join, sort by finding_id ───────── deterministic order, so runs are comparable
   │
   └─▶ package ───────────────────────── ASAPEnvelope + rejection record
```

Findings are sorted by ID at the join so two runs produce comparable output. An unordered join makes
every diff noise.

**Synthesis is the second stage, and it is deliberately narrow.** Until it existed the run fanned
out and *concatenated* — when one underlying fact bore on four criteria, four specialists reported
it independently and the reviewer had to work out they were seeing one fact four times. Synthesis
computes that overlap exactly, and spends a model call only on the part that needs judgement.

It may not summarise, rank, or assess. It emits `ProposedFinding`s classified `contradiction` or
`information_gap` — both of which the contract already had — and its output is validated by the
same shell as everything else. A synthesis that concluded something about the person would be the
determination this system must never make, wearing a helpful-sounding name.

**Storage roles are not interchangeable:** PostgreSQL is the system of record for workflow state.
OpenSearch is a retrieval index. Never treat a search index as authoritative for findings or run
state.

---

## What exists

**Runs today, against real models:**

| | |
|---|---|
| Data contracts | 12 Pydantic v2 models + JSON Schema |
| Model gateway | Port + `litellm` / `bedrock` / `stub` adapters. LiteLLM proven live; **bedrock never run** |
| Both orchestrators | Custom Python and LangGraph, one shared specialist and one shared synthesis stage |
| Criteria selection | Derived from the case manifest, so fan-out width is runtime data |
| Cross-criterion synthesis | Computed overlap + a model pass for contradictions and gaps |
| Citation + contract validation | Enforced, with rejections recorded |
| Envelope packaging | Validated `ASAPEnvelope` |
| Lambda packaging | `sam build --use-container`, invoked locally, envelopes on disk |

**Designed, not built:**

| | Approach |
|---|---|
| Retrieval | OpenSearch vector + lexical, mandatory case filter, bounded K, **all field mappings in one module** |
| Crash / resume | Checkpoint per node; resume in a new process without re-running an in-flight model call |
| Model-call idempotency | The expensive one. Measured today at 11–12 duplicate paid calls per 24 crash trials |
| Budgets and loop limits | Ceilings on model calls, tokens, wall clock, per node and per run |
| Authority routing | Criteria are currently hard-coded; routing from versioned policy packs is designed |
| Ingestion | Not ours (ADR-007) |

**The weakest point, named:** a refused specialist currently produces an empty findings list that is
indistinguishable at the artifact level from a criterion that came back clean. The distinction lives
only in the log. Refusals are expected in normal operation here, so this matters.

---

## Running it

```bash
uv sync
uv run pytest -q                      # offline; no model calls

# the demo — real model calls, ~20s, costs money
uv run python spikes/lambda_demo/build.py
cd spikes/lambda_demo && sam build --use-container --parallel && cd -
uv run --env-file .env python spikes/lambda_demo/run_case.py
```

Envelopes land in `spikes/lambda_demo/out/`. Open one — that file is what the architecture produces.

Everything runs locally except model calls, which go to a real endpoint. There is no offline model
fixture, deliberately: a fixture would let us claim things about model behaviour we have not
observed.

---

## Where to go next

| Document | What it is |
|---|---|
| [`LESSONS.md`](LESSONS.md) | What cost us time. **Read this before building** |
| [`AWS.md`](AWS.md) | GovCloud availability, the region constraint, local↔AWS parity |
| [`DECISIONS.md`](DECISIONS.md) | Why things are the way they are, with reasoning |
| [`../spikes/lambda_demo/README.md`](../spikes/lambda_demo/README.md) | The demo: how to run it, what it proves, what it does not |
