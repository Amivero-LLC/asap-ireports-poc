# What to build next

A working list, in priority order. Not a formal plan — no requirement IDs, no acceptance criteria to
sign off. If something here turns out to be wrong or unnecessary, change it.

## Where we actually are

A case runs end to end through a Lambda, against real models, through both orchestration paths, and
produces a validated envelope. **The boundaries are right and the orchestration is a stub.**

Worth being blunt about, because it decides what to build next:

```
hand-rolled:   pool.map(one, CRITERIA)          # one line
langgraph:     START ──▶ 3 fixed nodes ──▶ END  # one level, fixed width
```

One level deep, hard-coded width of three, no conditions, no second stage, no state accumulated
across steps. What that proves is real but narrow: the port holds, one shared specialist serves both
paths, and the gateway is the only thing that touches a model.

**What it cannot prove is which orchestration path is better** — a fixed single-level fan-out is
trivial in both, so any comparison at this shape measures nothing. That is why ADR-024 defers the
framework decision, and it is why the work below is ordered the way it is: **make the orchestration
real, and the comparison falls out of the work** rather than needing a separate exercise.

Each item below notes what it tells us about custom Python vs LangGraph.

---

# Part 1 · Make the orchestration real

## 1 · Fan out from the case, not from a constant ✅ done 2026-08-12

Criteria now derive from `requested_analyses` × `policy_pack_ids` via `criteria.py`, so the fan-out
width is runtime data. Catalog widened to five so selection is real rather than a formality.

**What it told us — the first genuine divergence between the two paths.** The hand-rolled version
needed *no change at all*; `pool.map` never cared how long the list was. LangGraph had to be rebuilt
around `Send`, because one-node-per-criterion only works if the criteria are known before the graph
is built. Not worse — the graph shape is now constant while the work is variable, which is what a
checkpoint needs — but structural where the other was free. See `LESSONS.md`.

**It also found a real bug.** Widening the catalog surfaced a response shape
(`{"findings": {"findings": [...]}}`) that the coercion wrapped instead of unwrapping, so a criterion
reported zero findings when the model had answered fine. Silent under-analysis, the exact failure
this system exists to prevent. Fixed; 7 findings instead of 5, and 19.7k tokens instead of 28.8k.

## 2 · Cross-criterion synthesis

Today we fan out and **concatenate**. In our own synthetic case the foreign business interest
surfaces in three criteria independently, and each specialist reports it as its own discovery.

A second stage that reads all findings and reasons across them — these three concern the same
underlying fact, the SF-86 answer contradicts the interview, this concern is mitigated by that
evidence — is real analytical value and the first genuine fan-in → reason → emit stage.

Constraint: synthesis produces more `ProposedFinding`s or annotates existing ones. It never produces
a summary judgment, and never an aggregate score.

**Tells us:** how each path handles a second level with a real join. This is where LangGraph's state
reducers stop being ceremony.

## 3 · Conditional routing

Right now every path through the graph is the same path.

- **Refusal → an explicit "not analyzed" outcome.** This closes the worst gap in the current design:
  a refused specialist produces an empty findings list that is indistinguishable in the artifact from
  a criterion that came back clean. Refusals are expected here — adjudicative files routinely discuss
  criminal conduct, substance use, and foreign contacts
- **Zero findings → skip downstream work** rather than running synthesis over nothing
- **Failure → route somewhere,** instead of a try/except inside one function

**Tells us:** conditional edges are LangGraph's home ground. If the hand-rolled version stays
readable through this, that is a real result.

## 4 · Budgets as control flow

Ceilings on model calls, tokens, and wall clock — per node and per run — that **change what the
graph does** rather than just recording a number.

- Hit a ceiling → stop early, return partial results, say so
- Record `BudgetConsumption` on the run so spend is accountable afterward

Two reasons this matters beyond cost. First, an agentic system that influences its own control flow
can loop forever, and "the model reasons; it does not decide control flow" only holds if the stopping
condition is code. Second, and specifically here: **Lambda's 15-minute ceiling kills the process
mid-flight and retries automatically**, re-paying for every model call already made. The shell has to
stop at its *own* wall-clock budget first — that is the only moment it gets to checkpoint. Without it,
item 7 is impossible.

**Tells us:** whether early termination mid-fan-out is clean in both, or whether one of them fights
you.

---

# Part 2 · Make the specialists real

## 5 · Retrieval

Specialists are currently handed evidence from a file. A specialist that retrieves its own evidence
is the actual architecture — the fixture version demonstrates a fan-out, not this system.

- Vector + lexical query against local OpenSearch, **mandatory case filter**, bounded K
- One synthetic case indexed and retrieved against
- Every field name, filter, and facet in **one module**, so swapping to the real AWS collection
  schema is a single-file edit. Its header should say the schema is unconfirmed
- No graph database, ever (ADR-006)

**Write down, don't solve:** if the query-time embedding model differs from the one that populated
the AWS collection, nothing errors — retrieval just gets quietly worse. Local retrieval quality never
predicts AWS retrieval quality.

## 6 · Multi-step specialists

Retrieve → assess whether the evidence is sufficient → retrieve again → then analyze. A loop inside a
node, bounded by item 4.

**Tells us:** this is where graph frameworks earn their keep, and where a hand-rolled version starts
needing real state management rather than a thread pool. Along with item 7, this is the strongest
signal we will get.

---

# Part 3 · Make it survive

## 7 · Crash, resume, and idempotency

The hard one, the highest technical risk, and **the thing that decides the framework question.**
By this point there is a real graph to checkpoint rather than three parallel calls.

- Checkpoint after each node; resume in a *separate process* without re-running completed work
- **A crash mid-fan-out must not re-run an in-flight model call.** Today it does — the bake-off
  measured 11 of 24 duplicate paid calls for LangGraph, 12 of 24 hand-rolled
- On the LangGraph path set `durability="sync"` and strict checkpoint deserialization. Both defaults
  are wrong here and invisible when reading the graph
- Then prove it across a Lambda invocation boundary, where a timeout *is* the crash

**When this works, make the framework call and close ADR-024.** Durable orchestration of paid
sub-calls is not a real claim if resuming double-pays.

---

# Part 4 · Prove it

## 8 · A case the system has never seen

Every run so far uses `AMI-SYN-FIN-001`, built alongside the system, and it contains real concerns.
So we have shown it finds issues when issues exist. We have **not** shown the opposite — whether it
manufactures concern on a clean record to look thorough.

A second synthetic case with a different shape: a clean record, or one where concern is strongly
mitigated. The interesting result is **fewer findings, or none.** An empty envelope is refused by
design, so a genuinely clean case should produce a run that says so rather than one that invents
something.

Cheap, fast, and the single strongest evidence improvement available. Do it earlier if you want a
confidence check before investing in Parts 1–3.

## 9 · Local AWS parity

- **OpenSearch in the compose file** configured to mirror the Serverless vector collection — same
  index shape and vector settings, so local behaviour predicts AWS behaviour (folds into item 5)
- **LocalStack as an opt-in profile** for the S3 and trigger path — never in the default `pytest`
  loop, which stays fast and service-free
- A short "what runs where" check against `docs/AWS.md`

**Decide early, independently of this list:** GovCloud US-West or US-East. `bedrock-mantle` is
US-West only, and that decides whether our `bedrock` adapter works as written or needs a
`bedrock-runtime` sibling — which is real work with its own translation layer for thinking, effort,
and refusals.

## 10 · One command, end to end

```
ireports run --case AMI-SYN-FIN-001
```

Load, retrieve, fan out, enforce budgets, synthesize, validate, package, write the envelope.
Unattended, with no point at which it waits for a person.

---

## Not scheduled, deliberately

| | Why not |
|---|---|
| Document ingestion | Not ours — the AWS pipeline owns upload, extraction, chunking, indexing (ADR-007) |
| Authority routing from policy packs | Item 1 derives criteria from the case manifest, which is most of the value. Real routing needs approved policy content that does not exist yet |
| Checkpoint row integrity | The largest known security gap — a tampered checkpoint that still parses would not be detected. Do it before anything real runs on this, not before the PoC is proven |
| Agreement scoring against analyst findings | Needs synthetic cases with analyst-identified ground truth. Worth doing once there is something to measure |
| Bedrock AgentCore | Reached GovCloud US-West 2026-05-05 and is a live alternative to the Lambda adapter. Never evaluated — worth a look before committing to Lambda |

## How we will know the framework answer

Not from a scorecard. From having built items 1–7 twice and noticing where one path fought us. The
things to write down as they happen, in `LESSONS.md`:

- Which path needed more code for the same behaviour, and whether that code was incidental or real
- Where a bug was silent in one and loud in the other
- What each made *impossible* to get wrong

At three fixed parallel calls, neither of those questions has an answer. That is the whole point of
building this before deciding.
