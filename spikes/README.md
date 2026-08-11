# Orchestration bake-off (Milestone 1c)

Settles ADR-012 with evidence. Three candidates — **hand-rolled**, **LangGraph**, **Strands
Agents SDK** — implement the same four legs against the same substrate and are scored on the same
dimensions. Set confirmed by the 2026-08-10 landscape scan
(`docs/handoff/orchestration-landscape.md`); PydanticAI was dropped there, with reasons.

**Status: complete as of 2026-08-11.** All three candidates pass all four legs. Two of the three
questions the landscape scan could not answer by reading are now measurements rather than
citations — Strands resumes execution rather than restoring conversation, and the
duplicate-model-call window is universal rather than an artifact of one candidate. The remaining
scan deliverables are done: the LangSmith egress-deny test (with a negative control) and the
framework-independent `docs/handoff/checkpoint-threat-model.md`. Cold start under SAM local is
still not run.

```bash
docker compose -f infrastructure/docker/compose.yaml up -d
uv sync
uv run pytest spikes -v -s

uv run python spikes/measure.py lines        # candidate-specific code lines
uv run python spikes/measure.py bytes r1     # serialized state at the review interrupt
uv run python spikes/measure.py duplicates   # the duplicate-model-call probe
uv run python spikes/measure.py footprint    # clean venv per candidate; slow
```

Tests skip rather than fail when PostgreSQL is unreachable.

Every number below comes from `spikes/measure.py`, which is in the repository precisely so that
none of them depends on someone's shell history. Measured on macOS 15 (Darwin 25.5.0), arm64,
Python 3.13.13 / 3.12 for the footprint venvs, `uv` 0.7.21, 2026-08-11.

---

## The design, and why it is shaped this way

**Candidates share everything except the wiring.** `harness/scenario.py` holds the node bodies —
routing, the two specialists, join-and-dedupe, validate, package. Every candidate calls those
functions; none reimplements them.

This is the load-bearing decision. ADR-012 scores "framework-specific lines of code", and that
number means nothing if each spike also carries its own node implementations: the count would
measure how verbosely three authors wrote a specialist, not how much scaffolding each framework
demands. With bodies shared, a candidate's line count is exactly its orchestration wiring, and
its output is exactly comparable.

**The gateway records what executed, outside the framework.** `harness/gateway.py` writes every
model call to PostgreSQL *before* returning, in its own transaction. The log survives a process
being killed, and no framework can influence it. That is what makes leg 1 answerable.

**Leg 1 runs across a real process boundary.** The conformance suite drives candidates through a
subprocess CLI, and `--crash-after` exits via `os._exit` — no unwinding, no `finally`, no atexit.
An in-process `resume()` would let object graphs, pools, and caches survive in memory, and a
candidate could pass while depending on state a restarted Lambda worker would not have.

**There is a permanent negative control.** `harness/negative_control.py` restores state and then
re-runs everything anyway. `test_negative_control_is_caught_by_leg_one` asserts leg 1 *fails* it
while legs 2 and 4 still pass. A leg that has never failed is not evidence, and this is how we
know leg 1 detects re-execution specifically rather than general brokenness.

---

## The four legs

| Leg | What it actually asks |
|---|---|
| **1 · durable resume** | Crash hard after one specialist commits, restart in a new process. Did completed work stay completed, or was it re-executed? |
| **2 · human interrupt** | Stop with proposals, take a disposition recorded out of band, deliver on resume. No envelope may exist before a disposition (ADR-011). |
| **3 · timeout survival** | A one-shot gateway timeout must not lose or duplicate completed work. |
| **4 · bounded fan-out** | Both specialists run exactly once; the join de-duplicates without collapsing two authorities into one. |

Leg 1 is the one the landscape scan singled out. §5.2 there records an unconfirmed third-party
claim that Strands restores *conversation* rather than resuming *execution*. This is how that
gets settled with a measurement instead of a citation — including for LangGraph, where it is
asserted rather than assumed.

Leg 4's de-duplication is deliberately non-trivial. One specialist emits the same finding twice;
separately, both specialists analyse the *same conduct* under different authorities. A dedupe
keyed on conduct would collapse those two and silently drop an authority's view — the failure
blueprint §2.1 warns about. Dedupe is keyed on `(run_id, domain, criterion)`, so the correct
result is **3 findings**: two removed as a true duplicate, two preserved as distinct authorities.

---

## Results

**All three candidates pass all four legs.** The bake-off does not separate them on correctness;
it separates them on cost, on what each still owes, and on what each makes the architecture
depend on.

| Measurement | hand-rolled | LangGraph | Strands |
|---|---|---|---|
| Candidate-specific code lines | **195** | **266** | **373** |
| Serialized state at the review interrupt | **16,346 B** | **16,115 B** | **23,739 B** |
| …everything the store retains for the run | 16,346 B | **37,033 B** | 23,739 B |
| Distributions beyond the harness baseline | **0** | 31 | 42 |
| Added installed size | **0.0 MB** | 18.0 MB | 47.3 MB |
| Open advisories against the pinned set (`pip-audit`, 2026-08-11) | 0 | 0 | 0 |
| Duplicate paid model call on a mid-fan-out crash (24 trials) | 12/24 | 11/24 | 0/24 † |
| Framework version | — | `langgraph` 1.2.10, `langgraph-checkpoint-postgres` 3.1.2 | `strands-agents` 1.51.0 |

† Not a durability property. See "the duplicate-model-call window" below.

**A recorded correction to earlier figures.** The 2026-08-10 line counts (hand-rolled 202, Strands
367) came from a count whose method was not recorded and could not be reproduced. Re-counted by
`spikes/measure.py lines` — physical lines carrying a non-comment token, minus docstrings — they
are 195 and 373: within 4%, in opposite directions, ordering unchanged. The reproducible numbers
supersede them. The checkpoint-byte figures moved similarly and for a duller reason: `run_id` is
embedded in every finding and serialized about ten times, so a longer run id is a bigger
checkpoint. `measure.py` now uses equal-length ids for all three.

### hand-rolled — all four legs pass

ADR-012 asks whether a bounded, checkpointed state machine over PostgreSQL is "a few hundred
lines." **It is 195** (orchestrator 130, checkpoint 56, entry point 9) — and that is a real floor,
not a strawman: it passes the same four legs the frameworks are held to.

Read it as a floor and not a total, though. Absent and genuinely needed for Milestone 2:
blueprint §8.5's no-progress and duplicate-query detectors, cancellation, tool allowlists,
budget accounting beyond a retry cap, OpenTelemetry spans, and any scheduler or supervisor. Those
will add lines. The comparison to make is not "195 vs. a framework's wiring" but "195 plus what
we still owe vs. a framework's wiring plus what it still owes."

**Caveat on the 16,346 bytes.** The hand-rolled checkpoint stores full finding JSON at three
stages — specialist output, join output, validate output — so each finding is serialized about
three times. Blueprint §8.2 says state should carry identifiers and typed records, not
accumulated copies, so this is a known inefficiency rather than an intrinsic cost. Cross-candidate
comparison on this dimension must normalize on *what* is stored, or a framework that happens to
store less will look better than it is.

### Strands Agents SDK — all four legs pass

`strands-agents` 1.51.0, the same tag the 1b scan read. Wired as a real
`strands.multiagent.Graph`: Strands owns node scheduling, the parallel batch, the interrupt, and
when state is written. What we supply is the PostgreSQL `SessionRepository` it does not ship, and
the encode/decode of typed contracts into the only container it persists.

| Measurement | Strands | hand-rolled |
|---|---|---|
| Candidate-specific code lines | **373** (session repo 166, orchestrator 148, nodes 53, entry 6) | 195 |
| Serialized state at the review interrupt | **23,739 bytes** | 16,346 bytes |
| Distributions beyond the harness baseline | **42 (47.3 MB)** — `botocore` dominates | 0 |
| Open advisories against the pinned set | 0 (`pip-audit`, 2026-08-11) | none |

#### Leg 1 settles the question the scan could not

**The claim does not hold for `Graph` in 1.51.0.** §5.2 of the landscape scan records a
third-party allegation that Strands restores *conversation* rather than resuming *execution* — an
interested source, unconfirmed, and the highest-value unknown in the milestone. Measured:

- `Graph.serialize_state()` persists `completed_nodes`, `node_results`, and
  `next_nodes_to_execute`; `deserialize_state()` sets a resume flag and restarts from the computed
  ready set rather than from the entry point.
- State is synced after **every node**, via an `AfterNodeCallEvent` hook — not once at the end.
- After a hard `os._exit(9)`, **no completed node re-executed.**

This is execution resume, not conversation restore. The scan was right to mark the claim
unverified rather than adopt it.

Strands also scores 0 on the duplicate-model-call probe. That is **not** a durability property —
see "the duplicate-model-call window" below, where LangGraph settles what the Strands result could
only leave open.

#### What Strands costs

- **The `SessionRepository` is ours to build, and it is the single largest file in the candidate**
  (166 of 373 lines). The scan predicted this. What the scan could not see is the ratio: a `Graph`
  of deterministic nodes calls only `read/create/update_multi_agent`, yet the abstract base
  requires session, agent, and message CRUD as well. Most of what we implement is never called.
- **State is conversation-shaped.** A node's durable result must be an `AgentResult`, and
  `AgentResult.to_dict` persists exactly `message` and `stop_reason` — `metrics` and `state` are
  dropped. So typed Pydantic contracts have to be flattened into an assistant message body and
  re-validated on the way out. This is the *defensible* core of the third-party claim: execution
  genuinely resumes, but the container for state is a transcript, and a workflow carrying typed
  records pays a serialize/parse tax at every node boundary. It also explains the larger
  checkpoint: 23,739 bytes against 16,346 for the same three findings — and against LangGraph's
  16,115, which stores the same three copies without the transcript wrapper.
- **`botocore` dominates the footprint.** 42 distributions and 47.3 MB added, of which the 1b scan
  measured `botocore` at 20.1 MB, pulled in whether or not a run ever touches AWS. Relevant to a
  Lambda zip and to `pip-audit` surface, not to correctness.
- **`Graph` owns run status**, so the domain state machine (`is_legal_transition`) is not enforced
  in this candidate the way the hand-rolled one enforces it. Part of why 373 is not directly
  comparable to 195 — see below.

#### Reading the line counts fairly

373 against 195 is not "Strands costs 178 lines". The two carry different things:

- Strands **adds** a `SessionRepository` implementation (166 lines) that the hand-rolled candidate
  does not need, because it writes its own two-table checkpoint (56 lines) instead.
- Strands **omits** the domain run-status machine that the hand-rolled candidate enforces.
- Strands **provides**, at no line cost to us, the per-node durability that the hand-rolled
  candidate demonstrably lacks (table above), plus node scheduling and the interrupt primitive.

The comparison ADR-012 actually needs is "each candidate's wiring **plus what it still owes**",
and both still owe blueprint §8.5's no-progress and duplicate-query detectors, cancellation, tool
allowlists, and OTel spans.

### LangGraph — all four legs pass

`langgraph` 1.2.10 with `langgraph-checkpoint-postgres` 3.1.2 — the exact versions the 1b scan
resolved, so its advisory analysis and these measurements describe the same code. Wired as a real
`StateGraph` compiled with `PostgresSaver`: LangGraph owns node scheduling, the parallel
super-step, the `operator.add` reducer that joins the fan-out, checkpoint writing, what
re-executes after a crash, per-node retry, and the interrupt. What we supply is a state schema,
eight one-line node wrappers around the shared scenario functions, and the edges.

| Measurement | LangGraph | hand-rolled | Strands |
|---|---|---|---|
| Candidate-specific code lines | **266** | 195 | 373 |
| Serialized state at the review interrupt | **16,115 B** | 16,346 B | 23,739 B |
| …everything the store retains for the run | **37,033 B** | 16,346 B | 23,739 B |
| Distributions beyond the harness baseline | **31 (18.0 MB)** | 0 | 42 (47.3 MB) |
| Open advisories against the pinned set | 0 | none | 0 |

#### What the first-party checkpointer is actually worth

ADR-012 called LangGraph "the only candidate where a PostgreSQL checkpointer is a first-party
package rather than something we build", and that is the dimension where the difference is
largest and least arguable. **Persistence cost us two lines** — `PostgresSaver.setup()` and
passing the saver to `compile()`. Strands needed 166 lines of `SessionRepository`; the hand-rolled
candidate needed 56 lines of checkpoint store.

Leg 1's mechanism is LangGraph's own, and it is more granular than either alternative: when a task
completes, its output is written as *pending writes* against the current checkpoint
(`put_writes`), and on resume LangGraph applies those writes rather than re-running the task. So
durability is per-task inside a super-step, not per-super-step. After a hard `os._exit(9)`
immediately following that write, **no completed node re-executed** — measured, not assumed, as
ADR-012 required for LangGraph as well as for Strands.

#### Two defaults that are wrong for this architecture, and are not visible in the code

This is the most transferable finding in the LangGraph candidate. A graph reads identically
whether or not either of these is set.

**1. `durability` defaults to `"async"`.** LangGraph 1.x offers `sync` (persist before the next
super-step), `async` (persist in the background while the next super-step runs), and `exit`
(persist only on exit). The candidate sets `sync`.

Stated at the confidence it earned: all four legs pass under **both** `sync` and `async`. Under
`exit`, leg 1 cannot be measured at all — the crash hook lives in `put_writes`, which `exit` mode
never calls — and that absence *is* the finding, since nothing is durable mid-run in that mode.
Crashing right after a sequential node's durable write redid no model calls in 24/24 trials under
`sync`; under `async` it redid work in 2 of 6 trials in one early round and 0 of 30 afterwards.
That is consistent with a real race we cannot reliably provoke, **not** with a clean result. So
`sync` is not chosen because `async` was measured to fail. It is chosen because the source does
not await the checkpoint future, so the window exists whether or not our harness can hit it, and
closing it costs one keyword on a run whose latency budget is minutes (ADR-013).

**2. Checkpoint deserialization defaults to permissive.** From the library's own source: *"Without
this, any Python callable stored in checkpoint data will be imported and executed on load."* The
candidate constructs `JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)` —
the same strict mode as `LANGGRAPH_STRICT_MSGPACK=true`, but in code, where an environment cannot
forget it. Demonstrated both ways in `test_checkpoint_trust_boundary.py`, and written up
framework-independently in `docs/handoff/checkpoint-threat-model.md`.

#### LangSmith is pinned closed, and proven closed

The 1b scan made this a required deliverable rather than a footnote:
`spikes/langgraph/test_langsmith_egress.py`, four scenarios, each in its own subprocess.

| Scenario | tracing | egress attempts during a full run |
|---|---|---|
| clean environment | off | **0** |
| `LANGSMITH_TRACING=true`, unpinned — *negative control* | on | `api.smith.langchain.com:443` |
| `LANGSMITH_TRACING=true`, `pin_tracing_closed()` | off | **0** |

The negative control is the important row, and what it found is worse than "tracing is opt-in"
suggests. The unpinned run issues `POST /runs/multipart` with **Content-Length ≈ 90 KB** — the
whole graph state, including every proposed finding's observation text — and **the run still
returns three findings**. LangSmith logs the failure and continues. So a misconfigured deployment
leaks silently, and a network-blocked one gives the operator no signal either.

The control is therefore an explicit, verified, fail-closed call at the entry point:
`langsmith.configure(enabled=False)`, which sets a process-global that `tracing_is_enabled`
consults **before** the environment — so an inherited `LANGSMITH_TRACING=true` from a base image
or a shared task definition cannot turn it back on. `pin_tracing_closed` then re-reads
`tracing_is_enabled()` and raises if it is still on, because a telemetry control that silently
fails to apply is worse than none: it gets reported as present.

#### What LangGraph costs

- **The framework is in the tree whether we use it or not.** 31 distributions and 18.0 MB,
  including `langchain-core`, `langsmith`, `httpx`, `requests`, `orjson`, and `ormsgpack`. Lighter
  than Strands by 11 distributions and 29 MB, and not close to the hand-rolled candidate's zero.
- **Checkpoint history is retained by default.** 37,033 bytes of thread storage against a
  16,115-byte latest checkpoint, for the same three findings — every super-step is kept, plus a
  blob per channel per version. That history is a real feature (`get_state_history`, time travel,
  replay) and it is also case-derived text at rest with no retention policy attached. Pruning is a
  design decision, not a default.
- **The state schema is ours to get right.** `Annotated[list[...], operator.add]` is what makes the
  fan-out join; declare the wrong reducer and two specialists silently overwrite each other rather
  than merging. Nothing type-checks that intent.
- **`add_node` typing is strict in an unobvious way.** A node function whose parameter is named `_`
  fails mypy's overload resolution against LangGraph's node protocol, while the same function with
  the parameter named `state` passes. Cosmetic, and exactly the kind of thing that costs an
  afternoon.
- **Pregel is the largest conceptual surface of the three.** Super-steps, channels, reducers,
  pending writes, task ids, and three durability modes are all load-bearing concepts a reader must
  hold to reason about a crash. The hand-rolled candidate has one: "skip what is committed."

#### Reading the 266 fairly

**57 of the 266 lines are the byte-measuring query**, which exists only to fill in a scorecard row
and does nothing at run time. It is that large because LangGraph spreads a checkpoint across three
tables — `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` — so measuring "one checkpoint"
means resolving `channel_versions` against the blob table. The other two candidates need 3–4 lines
for the same job because each stores one row. A further 17 lines are the `--crash-after` hook,
which is spike scaffolding rather than architecture.

Net orchestration wiring is therefore closer to **192 lines** — below the hand-rolled candidate's
195, while also providing per-task durability, the interrupt, retry policy, and scheduling. The
266 stays in the headline table because that is what the same ruler measured on all three, and
selectively subtracting from one candidate is how comparisons get massaged.

### The duplicate-model-call window — universal, not an artifact

Leg 1 deliberately does not assert on this. Twenty-four trials per candidate, crashing after
`specialist_suitability`:

| Candidate | Sibling's call already issued at crash time | Sibling re-ran on resume | **Duplicate paid call** |
|---|---|---|---|
| hand-rolled | 24 / 24 | 12 / 24 | **12 / 24** |
| **LangGraph** | **24 / 24** | 11 / 24 | **11 / 24** |
| Strands | 14 / 24 | 10 / 24 | **0 / 24** |

A crash lands while the sibling specialist's model call is **in flight** — issued and logged, not
yet committed. On resume it runs again. Correctness survives (all three candidates still produce
three findings in 24/24) but a paid model call is spent twice.

**LangGraph settles what the Strands result could not.** The 2026-08-10 write-up recorded Strands'
zero as an artifact of our synchronous node bodies, which stop its `asyncio` tasks from ever
interleaving, and predicted that a candidate with genuine concurrent fan-out would show the same
window as the hand-rolled one. LangGraph is that candidate — its super-step runs both specialists
on a thread pool — and it does: the window was open in **24 of 24** trials and cost a duplicate
call in **11**, statistically indistinguishable from hand-rolled's 12.

Strands' numbers now partition cleanly and confirm the artifact reading: in the 14 trials where
the sibling had been called it never re-ran, and in the 10 where it re-ran it had never been
called. There is no in-flight window in that candidate because there is no overlap.

So this is a property of at-least-once execution with uncommitted in-flight calls, **not** a
discriminator between frameworks. It belongs on the "what each candidate still owes" ledger, not
against any one candidate's line count.

**The real mitigation is owed by all three**: model-call-level idempotency — blueprint §8.5's
duplicate-query detection. **None of them has it.**

**Tried and reverted (2026-08-10, still the right call).** Leg 1 was tightened to assert every
specialist ran exactly once, then reverted. Re-running a sibling whose call the orchestrator never
observed completing is at-least-once behaviour, which is correct: nothing durable said that work
was done. The stricter assertion is flaky by construction — it fails on thread timing, not on a
defect, as the 11/24 and 12/24 above make plain. Leg 1 asserts on the node named by
`--crash-after`, which every candidate is contractually required to have committed, and duplicate
sibling calls are recorded as a measurement (`duplicated_specialist_calls`) instead.

---

### One harness amendment, recorded rather than quiet

Leg 1's process-liveness guard used to require a new process id in the model-call log after every
resume. Strands failed it for the wrong reason: it re-executed nothing, so it made no model calls,
so no new pid could appear — the guard punished a candidate for having less work to redo.

The guard now applies only when the resumed process actually called the gateway. It is
corroboration, not the mechanism: `port.invoke` shells out through `subprocess.run` on every
invocation, so the process boundary is structural and a candidate cannot fake an in-process
resume. **Leg 1's actual assertion — that a completed specialist ran exactly once across the
crash — is unchanged, and `negative_control` still fails it** with
`specialist_suitability ran 2 times across the crash`.

## Adding a candidate

1. New workspace member under `spikes/<name>/`, added to `[tool.uv.workspace]`.
2. Implement `ireports_spike_harness.port.Orchestrator`: `start(run_id, crash_after)` and
   `resume(run_id, dispositions)`.
3. `__main__.py` calls `ireports_spike_harness.main(YourOrchestrator())` and nothing else —
   argument handling lives in the harness so no candidate can advantage itself with a different
   invocation shape.
4. Add one line to `CANDIDATES` in `spikes/test_conformance.py`.
5. Add the package path to `CANDIDATES` in `spikes/measure.py` so the rulers cover it too.

Honour `crash_after` at your own node boundaries. Where that boundary sits relative to your
checkpoint write is not an implementation detail — it is what leg 1 measures. All three existing
candidates kill immediately **after** their durable write commits — the hand-rolled one after
`commit_node`, Strands inside `update_multi_agent`, LangGraph inside `put_writes` — because any
other placement measures the spike author's hook rather than the framework's durability.

---

## What this does not measure

Stated so the scorecard is not read as more than it is.

- **Cold start and packaging under SAM local.** Not yet run; `MeasuredFootprint.cold_start_seconds`
  is null until it is. This is the largest remaining gap, and it is the dimension where the
  footprint numbers above would turn into a decision rather than a data point.
- **OpenTelemetry export.** Blueprint §9.4 lists it; not yet exercised. Note that Strands already
  drags the OTel SDK into its dependency set and the other two do not — that is a footprint
  observation, not evidence about how easy tracing is to wire in any of them.
- **Developer comprehension.** A judged dimension, recorded with reasoning in the scorecard, not
  produced here.
- **Checkpoint integrity.** No candidate detects a tampered checkpoint row that still parses.
  `docs/handoff/checkpoint-threat-model.md` §6 lists this and the other controls that were *not*
  built, so the threat model is not read as a completion certificate.
- **Real model behaviour.** The gateway is a deterministic stub, deliberately — all four legs are
  about control flow, and leg 3 is a *simulated* timeout by definition. This also decouples the
  bake-off from Q-01, which cannot be answered without account access.
