# Orchestration Decision: Custom Python vs LangGraph

**Scored: 2026-08-19** · **Status: complete — resolves ADR-024** · **Supersedes the
recommendation in [`orchestration-scorecard.md`](orchestration-scorecard.md) (ADR-012)**

**Decision: custom Python is the reference implementation.**

> **Amended 2026-08-19 by ADR-029.** This report originally also retained the LangGraph adapter as a
> "conformance arm." That clause was withdrawn: the retention argument was circular — the second
> implementation only ever surfaced defects *in itself*, never in shared code — and it carried
> `langsmith`, a run-content exporter, into everything that shipped. **The adapter is removed.**
> §2's measurements stand; they were taken while both existed, and the evidence is this report plus
> git history. `spikes/langgraph/` retains a LangGraph implementation from the first bake-off.

This is the **second** bake-off and it answers a different question from the first. ADR-012 scored
three candidates on a stubbed four-leg harness in one day, before any analysis code existed, and
chose LangGraph on the cost of a PostgreSQL checkpointer — two lines against fifty-six. ADR-024
then declined to treat that as settled and set a trigger: *the call gets made when idempotent
crash/resume works.* It works. This is that call.

The evidence here is not a scorecard run. It is **eight features built twice**, behind one port,
over one shared specialist, and the record of where one path fought us.

> **Claim tagging.** `[measured]` — reproduced on this machine, 2026-08-18/19, by
> `uv run pytest tests spikes` or a named live run. `[judged]` — one engineer's assessment after
> building both, recorded with its reasoning. **Read §5 before quoting §2.**

---

## 1. The criteria, and why these

Not a weighted matrix. The criteria are simply **every orchestration feature the roadmap required**,
because ADR-024's premise was that a comparison at a fixed three-node fan-out measures nothing, and
the way to learn something is to build the real thing twice and notice.

Each row below is a capability that had to exist for the system to work. None was invented to
create a difference, and the four that produced **no** difference are reported as results, not
omitted.

The two things ADR-012 actually selected LangGraph for — durable checkpointing and crash/resume —
are rows 6 and 7, and they are the reason the answer changed.

---

## 2. The table

| # | Capability | Hand-rolled | LangGraph |
|---|---|---|---|
| 1 | Runtime fan-out width `[measured]` | No change — `pool.map` never cared about list length | **Structural.** Rebuilt around `Send`; one-node-per-criterion needs criteria known at construction |
| 2 | Fan-in barrier for stage two `[measured]` | Free — exiting the pool context | Free — supersteps. **Null result** |
| 3 | Conditional routing after fan-out `[measured]` | `if should_synthesize(outcomes):` | A do-nothing `join` node. The naive version fires once per dispatch on partial state and **fails silently** |
| 4 | `mypy --strict` `[measured]` | 0 suppressions | 6 suppressions; the documented `Send` pattern matches no `add_node` overload |
| 5 | Early termination on a budget `[measured]` | 3 lines | 3 lines, marginally cheaper. **Null result** |
| 6 | Node-level checkpointing `[measured]` | Store, upsert and read written by hand | `setup()` writes the schema. **And** a shared JSON codec is forced, the budget stop must `raise` rather than `return`, and **8 of 24 crash trials lost the write for a call already paid for**, against 0 |
| 7 | Resume across a Lambda invocation boundary `[measured]` | 3 + 3 = 6 paid calls, against ~6 for one uninterrupted run | Identical. **Null result** |
| 8 | A bounded loop inside a node `[measured]` | No change | No change. **Null result** |
| — | Adapter size `[measured]` | **47 statements** | 118 statements (both excluding docstrings) |
| — | Fan-out bound by default `[measured]` | `max_workers` — bound by construction | **Unbounded.** `Send` ran 8 of 8 dispatches at once until `max_concurrency` was set on the config |
| — | Developer comprehension `[judged]` | **good** — a thread pool and a loop | adequate — three traps are invisible in a correct-looking graph |

Everything not in this table is **shared, framework-free code both paths call**: ~3,400 lines of
criteria selection, specialists, evidence gathering, synthesis, budgets, idempotency, checkpoint
codec, and tracing. That ratio is itself a finding — the orchestrator is the small part.

Pinned versions: `langgraph` 1.2.10, `langgraph-checkpoint-postgres` 3.1.2, `langgraph-checkpoint`
4.2.0, `langchain-core` 1.5.3. Hand-rolled has none.

---

## 3. Why the answer changed from ADR-012

ADR-012's reasoning was sound on the evidence it had, and one specific thing did not survive
contact with a typed contract and a real crash.

**The two-lines-versus-fifty-six figure was real and incomplete.** `PostgresSaver.setup()` genuinely
creates and migrates its own tables, and nothing in our adapter writes SQL. But ORCH-01 also
requires **strict checkpoint deserialization**, and under that setting LangGraph does not refuse an
unknown type — it silently returns a `dict`, on the resume path only. So the state channels *and*
the `Send` payloads must carry plain JSON that our own code re-validates. **The first-party
checkpointer saves you the store; it does not save you the codec, and the codec is most of the
code.** Both paths now share ours.

**And on the one capability it was chosen for, it is behind.** A task that finished before a sibling
raised can lose its checkpoint write, because LangGraph persists from the runner *after* a task
returns and the executor is torn down in between. `durability="sync"` narrows that window and cannot
close it, because the write still happens outside the node. The hand-rolled path commits inside the
worker before `analyze` returns and lost nothing in the same trials. **Read §5 item 3 before
weighting this.**

---

## 4. What the decision obliges us to carry

1. **The port stays, and the no-import rule stays.** A source scan over every module in
   `packages/orchestration/` fails if anything but the adapter and the registry names LangGraph.
   It stops being lock-in insurance and becomes the thing that keeps the control arm honest.
2. **Every orchestration feature is still owed by both paths.** That is what made this comparison
   possible and it is what would make a future reversal cheap.
3. ~~**The LangGraph adapter is maintained, not frozen.**~~ **Withdrawn by ADR-029.** The four
   "earned its keep" instances — the per-dispatch router, the concurrent-write reducer, the
   strict-serde type downgrade, the unbounded fan-out — are all defects *in the LangGraph path*,
   which would not exist without it. It found zero defects in shared code. What two implementations
   genuinely bought was forcing routing policy and the checkpoint codec into shared code, and that
   value is banked rather than recurring.

---

## 5. What this decision does **not** say

**It does not say LangGraph is the wrong choice for the production system.** Five reasons, and the
fourth is the one to weight highest.

1. **The graph is trivial.** `START → N specialists → join → synthesis → END`. One fan-out level,
   one second stage. Frameworks earn their keep on nested subgraphs, many node types, streaming,
   and human-in-the-loop interrupts — and **ADR-022 removed the in-run review pause**, which is
   among LangGraph's strongest features. This measured it on a shape that uses little of what it
   offers.
2. **The loop was deliberately built where a framework cannot help.** Roadmap item 6 puts the
   multi-step loop *inside* a node, so neither orchestrator can see it; the null result was
   predicted in `gather.py`'s docstring before it was measured. Where a framework would plausibly
   win is a loop the **orchestrator** sees, with separately checkpointable steps. We did not build
   that, so row 8 is a result about our design choice, not about the general question.
3. **Row 6's crash is an exception, not a kill.** The 8-of-24 lost writes come from a *sibling task
   raising*, which tears down the executor. The original bake-off's 11/24 and 12/24 came from hard
   kills (`os._exit`). Those are different experiments, and the mechanism documented here is
   specific to in-process exceptions — which is what a bug or a budget stop looks like, **not what
   a Lambda timeout looks like.** A timeout is a kill. Untested; see §6.
4. **The evaluation was written by the author of both adapters.** If that engineer is more fluent in
   plain Python than in LangGraph — and they are — the asymmetries are biased toward the
   hand-rolled path and would not necessarily be noticed. The six `mypy` suppressions and the
   `join`-node discovery may be a competent LangGraph user's ordinary afternoon. **No scorecard can
   correct for this; only an outside reader can.**
5. **Nothing has ever run on AWS.** SAM local and a LiteLLM proxy throughout. The `bedrock` adapter
   has never executed in any partition (Q-01), and Bedrock AgentCore — which reached GovCloud
   US-West on 2026-05-05 — was never evaluated. A different runtime could move several rows.

**The stakes are lower than a framework decision usually is**, and that is part of why it is
defensible now. Being wrong in each direction costs differently: choosing hand-rolled and regretting
it means adopting a framework behind a port that already exists and is test-enforced; choosing
LangGraph and regretting it means carrying its constraints through a codebase that did not need
them.

---

## 6. Named open items

Cheapest first. None blocks implementation; all three would raise confidence in §2.

| Item | Cost | What it would settle |
|---|---|---|
| An outside review of `langgraph_adapter.py` by someone fluent in LangGraph | hours | §5 item 4 — the bias this document cannot correct for itself |
| A hard-kill (`os._exit`) variant of the row-6 measurement | an afternoon | §5 item 3 — whether the lost-write finding survives the failure mode that motivated the whole question |
| Confirmation that review stays in ASAP (ADR-022) | a conversation | §5 item 1 — if review ever moves in-run, the comparison reopens on LangGraph's home turf |
