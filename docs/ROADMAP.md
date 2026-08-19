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

## 2 · Cross-criterion synthesis ✅ done 2026-08-12

A second stage that reads every specialist's findings and reports only what is invisible from one
criterion. Split by who is competent to answer:

- **Computed** — which findings rest on the same evidence span. Set arithmetic, free, exact.
- **Model** — contradictions and information gaps across the record.

**What it produces.** On the demo case the computed half reports that `ev_003` and `ev_004` each
carry findings under **four** criteria — the "you are looking at one fact four times" signal, which
is what item 1 predicted would be needed. The model half reported zero contradictions (correctly,
since the candor specialist had already found the obvious one) and instead surfaced gaps genuinely
invisible from any single criterion: *the financial criterion evaluated the debt in isolation while
the foreign income was treated only as a disclosure issue, and nobody cross-referenced them.*

**What it told us — a null result, which counts.** The fan-in barrier was expected to favour
LangGraph and did not. One line each: exiting the `ThreadPoolExecutor` context, or LangGraph's
superstep model. Whatever separates these two paths, it is not joining.

**Constraint held:** no summary, no ranking, no aggregate. It emits `ProposedFinding`s of the two
classifications the contract already had for this, and the same validators reject its output —
a contradiction citing one span, or naming a criterion nobody analysed, is dropped like anything
else.

## 3 · Conditional routing ✅ done 2026-08-12

Refusals contained, statuses explicit, synthesis skipped when there is nothing to reason across.

**It found a real bug first.** `gateway.complete()` was called bare, so **one refused criterion
killed the entire run** on both paths, discarding every other specialist's completed and paid-for
work. Under Lambda that is worse — the invocation is retried automatically and every model call is
paid for again, into the same refusal. ADR-021 §3 had already decided the node should catch it;
the decision was recorded and never implemented, and nothing tested it, so nothing contradicted it.

Now: `SpecialistStatus` is `COMPLETED` / `REFUSED` / `FAILED`, refusals are not retried (ADR-015),
and the run surfaces `not_analysed` at the top of its payload. **`completed with no findings` and
`refused` are different facts** and no longer look alike to an operator.

**What it told us — the clearest LangGraph result so far.** A conditional edge leaving a
`Send`-dispatched node fires **once per dispatch, each seeing only its own contribution to state**.
Measured: five dispatches, five router calls, `[1, 1, 1, 1, 1]` outcomes visible, never five. Every
branch decided on one-fifth of the evidence and synthesis silently never ran — no error, no
warning. The fix is a do-nothing `join` node so the conditional edge leaves a joined point. The
hand-rolled equivalent of the entire problem is `if should_synthesize(outcomes):`.

Not that LangGraph is wrong — but the correct construction is non-obvious, the incorrect one runs
cleanly, and you only find out by counting.

**Still open, deliberately:** the envelope does not carry the refused/clean distinction. ADR-021 §2
weighed that and kept it out of the contract, so a reviewer in ASAP still cannot tell. The gap is
narrowed to the operator, not closed — closing it means superseding ADR-021 on purpose.

## 3b · The reference implementation, at its own address ✅ done 2026-08-12

Criteria, specialists, synthesis and both orchestrators moved from `spikes/lambda_demo/` into
`packages/orchestration/`, and specialists now return the published `SpecialistResult` contract
instead of a local dataclass. `spikes/lambda_demo/` is what it should have been all along: case
loading off disk, envelope packaging, a Lambda handler, and the synthetic corpus.

Not a feature — an address change — but three things fell out of it that a pure move would not
have produced:

1. **The contract validates now.** `SpecialistResult` re-checks that every finding's run id, case
   id, and authority agree with the criterion the sub-call was pointed at. The local dataclass
   checked nothing; the invariant was true by construction and unasserted.
2. **A fourth path asymmetry.** `packages/` is under `mypy --strict` and `spikes/` is not. The
   hand-rolled adapter needed no change. The LangGraph adapter needed four suppressions, because
   the `Send` pattern LangGraph's own documentation prescribes matches none of `add_node`'s
   overloads. See `LESSONS.md`.
3. **A real bug the tests could not see** — a variable in `synthesis.py` bound to a set and then
   re-bound to a list in the loop below, harmless by accident of ordering. `mypy` found it on the
   first run. `spikes/` sitting outside the quality gate is a gap, not a convenience.

**And the first live run after it found a fourth thing**, which is the argument for running live
at all. Synthesis returned both its arrays as JSON *strings*; the loop enumerated the string
character by character and produced **4,547 rejections and zero synthesis findings**, on both
paths, with a valid envelope and no error. The specialist path handled the identical shape
correctly in the same process, because the coercion for it lived in a private helper written
weeks earlier and never went anywhere else. Now `coercion.py`, imported by both, plus a cap on
rejection lists — four thousand copies of "not an object" is not a diagnostic, it is what hid the
two rejections that mattered. See `LESSONS.md`.

**What the graduation did not close.** ORCH-01 also wants `durability="sync"` and strict checkpoint
deserialization; those need a checkpointer, which is item 7. SPEC-01's tool-allowlist clause is
*vacuous* rather than met — a specialist has no tool surface. Both stay unchecked in
`REQUIREMENTS.md`.

## 4 · Budgets as control flow ✅ done 2026-08-18

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

**What it told us — a third null result.** Three lines in the mapped function, three lines in the
node. Neither path can withdraw work it has already dispatched — `pool.map` has queued every
criterion and `Send` has dispatched every criterion — so both can only make a criterion reached
after the ceiling cheap rather than un-scheduling it. The one asymmetry runs slightly toward
LangGraph: declining the second stage costs one boolean on a conditional edge that already existed.

**Built:** `budget.py`, a thread-safe run-level ledger over wall clock and tokens.
`SpecialistStatus.SKIPPED_BUDGET` is a fourth distinct fact — a criterion nobody got to is not one
that broke. A run that hits a ceiling still packages and delivers what it has, and says which
ceiling stopped it. The default wall clock is 780s against Lambda's 900s timeout, which is the only
number here with a hard reason: **the shell has to stop before the platform does, because that is
the only moment it will ever get to checkpoint.**

**Not built, and named rather than glossed:** `Budgets` has no per-run model-call ceiling, only a
per-node one. With runtime fan-out width that does not bound a run. Wall clock and tokens do, so
the gap is covered in practice rather than by design; closing it is a contract change and wants an
ADR.

**Next up: item 7** — crash, resume, and idempotency. The wall-clock budget is what makes the
Lambda half of it possible, and it is now what a run gets to checkpoint against: a criterion the
ceiling skipped is deliberately *not* recorded, so it is the next invocation's work.

---

# Part 2 · Make the specialists real

## 5 · Retrieval ✅ done 2026-08-12

Specialists retrieve their own evidence instead of being handed the whole case. OpenSearch in
compose, Titan embeddings through an `EmbeddingGateway` port, hybrid vector + lexical, mandatory
case filter, k=6.

**Measured on a real 35k-token case** (`CASE-TEST-001`, langgraph, one run):

| | |
|---|---|
| Input tokens | **69,139** — against ~209,664 if every call got the whole case |
| Ratio | **3.0× fewer input tokens** |
| Output tokens | 25,632 (thinking at `effort=high`, unaffected by retrieval) |
| Findings | 18 — 14 specialist, 4 cross-criterion |

I estimated 7× beforehand and was wrong: retrieval preferentially surfaces the *large* ROI chapters
(~2,000 tokens each), not the average span. 3× is the honest figure.

**Citations are now checked against what the specialist was shown**, not against the whole case.
With retrieval those differ, and validating against the case would let a model cite a span it never
saw — indistinguishable from a lucky hallucination.

**Two bugs the first real run found**, both invisible at 430 tokens:

1. **Synthesis was still pasting the entire case.** It exhausted `max_tokens` while thinking and
   returned no text. Now scoped to the spans the findings actually cite, as bounded excerpts.
2. **A synthesis failure killed the run** — the same containment gap fixed one layer down in item
   3, in a place I had not looked. Contained now.

And a reporting bug worth naming: the summary said `synthesis skipped — nothing to reason across`
when synthesis had **run and failed**. Both states inferred from one null. Same shape as
refused-versus-clean, one layer up.

## 6 · Multi-step specialists ✅ built 2026-08-19 — machinery proven, value not

Retrieve → assess whether the evidence is sufficient → retrieve again → then analyze. A loop inside
a node, bounded at every edge: `max_steps`, `max_model_calls_per_node`, `max_evidence_per_node`, the
run ledger, a no-progress detector, and a cancellation token. Seven distinct stop reasons, because a
loop that cannot say why it stopped is one that looks like it found everything.

**This closes ORCH-03.** Its last two clauses — a no-progress detector and cancellation — were
deferred four times with the same reasoning: they are meaningless in a node that cannot loop. And
`max_model_calls_per_node` finally means something; it was previously "enforced by the bounded retry
in `analyze`", which was true and thin at two calls against a limit of five.

**What it told us, and it is not the answer anyone wanted.** Two live runs, hand-rolled path:

| | `AMI-SYN-FIN-001` (8 spans) | `CASE-TEST-001` (34 spans) |
|---|---|---|
| Sufficiency calls | 5 | 5 |
| Criteria that asked for more | **1** | **0** |
| New evidence a refinement surfaced | **0** | — |
| Tokens | 46,824 (~32k before) | 159,505 (~95k before) |
| Wall clock | 143s (~60s before) | 357s |

**The assessor says "sufficient" almost always, and on two cases the loop added no evidence at
all.** The one refinement it did attempt surfaced nothing new, and the no-progress detector stopped
it — the machinery working exactly as designed, on a question that did not need asking.

Two readings, and they are not distinguishable yet:

1. **The prompt is too conservative.** It explicitly tells the assessor that asking reflexively
   costs a paid call and returns the same spans. That guard is there because a loop that always
   loops is worse than no loop, and it may be over-tuned.
2. **`k=6` against an 8-span case is already the whole record.** There is nothing a second query
   *could* find. On the 34-span case that argument is weaker, and the assessor still never asked.

**What is not in doubt is the cost:** roughly +50% tokens and 2.4× wall clock on the small case,
for five calls that changed nothing. Before this is defended it should be either tuned and
re-measured, or turned off by default with `max_steps=1` and kept for cases that need it.

**And what it told us about ADR-024 — nothing, which was predicted in writing beforehand.** The
loop lives *inside* a node, so neither orchestrator can see it. `gather.py` said before it was
measured that if anything discriminated here it would be cancellation crossing the node boundary,
and cancellation turned out to be the same `_StopWork`-versus-`return` asymmetry already recorded
for budgets — deepened, not new. **This was the last capability ADR-027 named as unmeasured.**

**A live run also found a real bug**, in the way live runs keep doing: `IREPORTS_DEADLINE_RESERVE_SECONDS`
was read with `os.environ.get(name, "60")` at *module scope*. Every variable in `template.yaml` is
declared with an empty default, so in the container the name is present and blank, the default never
applies, and `float("")` raised before a line of the handler ran — `ValueError`, no variable name,
no case id. See `LESSONS.md`.

**Deliberately not built: a tool surface.** The loop re-queries the same `Retriever` and can do
nothing else, so SPEC-01's allowlist clause stays *vacuous* rather than satisfied. That clause
becomes real the day a specialist can choose between capabilities.

---

# Part 3 · Make it survive

## 7 · Crash, resume, and idempotency

The hard one, the highest technical risk, and **the thing that decides the framework question.**

- ~~**A crash mid-fan-out must not re-run an in-flight model call.**~~ ✅ **done 2026-08-18.**
  0 duplicate paid calls, both paths, every crash point — against the bake-off's 11 of 24 and 12 of
  24. It landed at the *gateway*, not the orchestrator, so both paths got it in identical
  framework-free code and it discriminates between them not at all. **That reframed the rest of
  this item:** a resumed run re-executes everything and pays for nothing, so checkpointing buys
  back wall clock rather than money. See `LESSONS.md`
- ~~Checkpoint after each node; resume in a *separate process* without re-running completed work~~
  ✅ **done 2026-08-18.** `checkpoint.py` for the hand-rolled path, `PostgresSaver` for LangGraph,
  both proven across a real process boundary
- ~~On the LangGraph path set `durability="sync"` and strict checkpoint deserialization~~
  ✅ **done 2026-08-18**, in code with tests. **This closes ORCH-01**, whose last two clauses these
  were
- ~~Then prove it across a Lambda invocation boundary, where a timeout *is* the crash~~
  ✅ **done 2026-08-18, live under SAM local, both paths.** One `run_id`, two containers, a 10s
  ceiling on the first: 3 criteria completed and 2 skipped, then 3 nodes restored and only the 2
  outstanding run. **3 + 3 = 6 paid calls against ~6 for one uninterrupted run**, identically on
  both paths. `run_case.py --resume-demo`

**What it told us — the first result that runs against LangGraph, on the dimension it was chosen
for.** Three findings, all measured, all in `LESSONS.md`:

1. **A crash can lose the checkpoint write for a call already paid for.** The hand-rolled path
   commits inside the worker before the node returns; LangGraph persists from the runner *after* it
   returns, and a sibling's exception shuts the executor down in between. Over the bake-off's
   24-trial shape: **hand-rolled 0 lost writes, LangGraph 8.** It costs wall clock rather than
   money — idempotency covers the spend — which is precisely the resource this feature exists to
   buy back. `durability="sync"` narrows that window and cannot close it.
2. **Strict deserialization silently returns a `dict`.** Not an exception — a type downgrade, on
   the resume path only. It hit the `Send` payload before it hit the state, so the fan-out died on
   `criterion.question` after a crash and never before one. Both paths therefore share a
   framework-free JSON codec: **`PostgresSaver` saves you the store, not the codec**, and the codec
   is most of the code.
3. **A budget stop needs two spellings on the LangGraph path and one on the other.** A returned
   value is also what marks a task complete, so returning a skip would tell the checkpoint the
   criterion is done and strand the invocation whose job was to finish it. The node has to raise —
   but only when something will resume, because an un-checkpointed raise discards every other
   specialist's paid-for work.

**What is genuinely easier on LangGraph**, recorded rather than buried: `PostgresSaver.setup()`
creates and migrates its own tables, and nothing in the adapter writes SQL. `checkpoint.py` had to
write a schema, an upsert, and a read. That is real, and it is smaller than the three costs above.

**LAMB-01 was a null result for the framework question, and that is itself the answer.** Both paths
resumed across the invocation boundary and both paid exactly once for everything. The boundary that
motivated the whole framework decision does not discriminate between them.

**So ADR-024's trigger has fired.** It said the call gets made when idempotent crash/resume works.
The complete scorecard is in ADR-027, recorded as **proposed** rather than accepted: the evidence is
one-sided, and the decision is the project owner's to make rather than a side effect of the commit
that gathered it.

Two things that fell out of building it, both real bugs rather than findings about frameworks:

- **The LangGraph fan-out was unbounded.** `MAX_PARALLEL` only ever reached the thread pool;
  `Send` ran 8 of 8 dispatches at once until `max_concurrency` was set on the config. It also
  silently disabled the wall-clock stop, because a criterion that starts at t=0 never sees a
  crossed ceiling.
- **A breach was measured on every read**, so one payload reported `18.5 of 10` on its skipped
  criteria and `34.4 of 10` in its summary. The ledger now remembers the first breach. Same shape
  as `completed with no findings` versus `refused`, one layer down.

---

# Part 4 · Prove it

## 8 · A case the system has never seen ✅ built 2026-08-17, and it found something

Every run so far uses `AMI-SYN-FIN-001`, built alongside the system, and it contains real concerns.
So we have shown it finds issues when issues exist. We have **not** shown the opposite — whether it
manufactures concern on a clean record to look thorough.

A second synthetic case with a different shape: a clean record, or one where concern is strongly
mitigated. The interesting result is **fewer findings, or none.** An empty envelope is refused by
design, so a genuinely clean case should produce a run that says so rather than one that invents
something.

Cheap, fast, and the single strongest evidence improvement available. Do it earlier if you want a
confidence check before investing in Parts 1–3.

**Built as `AMI-SYN-CLR-001`** — same five criteria, clean record with every concerning-looking
item explained *in the record*: a late payment that was the creditor's addressing error with a
written correction, foreign in-laws who are retired dual citizens, a below-threshold foreign
account the subject volunteered unprompted.

**The substance was right and the labelling was wrong.** Seven findings instead of ten, text that
led with the mitigation and deferred the judgment — and every one stamped `potential_issue`,
because `specialist.py` hard-coded that classification and the schema never asked. Two of the
contract's five values had never been reachable. See `LESSONS.md`.

**Fixed 2026-08-18, ADR-025.** The schema asks, the model answers from a constrained enum, and an
empty findings array stays valid — so a wholly clean case produces no envelope and the run says
why, rather than manufacturing a finding to have something to deliver.

**Two things this run did *not* establish**, and neither should be rounded up:

- **The contradiction test never ran.** Synthesis failed on `max_tokens` — contained correctly and
  reported as `failed` rather than `skipped`, which is two earlier fixes working, but the stage
  did not execute. "Zero contradictions" is not a result here.
- **Only the hand-rolled path ran.** The LangGraph run was interrupted. The finding lives in the
  shared specialist so it is path-independent by construction, but that is reasoning, not
  measurement.

## 9 · Local AWS parity

- **OpenSearch in the compose file** configured to mirror the Serverless vector collection — same
  index shape and vector settings, so local behaviour predicts AWS behaviour (folds into item 5)
- **LocalStack as an opt-in profile** for the S3 and trigger path — never in the default `pytest`
  loop, which stays fast and service-free
- A short "what runs where" check against `docs/AWS.md`

**Region decided 2026-08-12: GovCloud US-West** `[believed]`, per the project owner, not yet
confirmed against the account. That is the region where `bedrock-mantle` exists, so **our `bedrock`
adapter works as written** and the `bedrock-runtime` sibling ADR-015 scoped is not needed. See
`docs/AWS.md` for what remains open — chiefly that documented availability is not account
entitlement, and that the adapter has never been run in any partition.

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
