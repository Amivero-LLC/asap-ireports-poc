# Orchestration bake-off (Milestone 1c)

Settles ADR-012 with evidence. Three candidates — **hand-rolled**, **LangGraph**, **Strands
Agents SDK** — implement the same four legs against the same substrate and are scored on the same
dimensions. Set confirmed by the 2026-08-10 landscape scan
(`docs/handoff/orchestration-landscape.md`); PydanticAI was dropped there, with reasons.

```bash
docker compose -f infrastructure/docker/compose.yaml up -d
uv sync
uv run pytest spikes -v -s
```

Tests skip rather than fail when PostgreSQL is unreachable.

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

## Results so far

### hand-rolled — all four legs pass

| Measurement | Value |
|---|---|
| Candidate-specific code lines | **202** (orchestrator 137, checkpoint 56, entry point 9) |
| Serialized checkpoint at the review interrupt | **16,313 bytes** |
| Distributions beyond the domain package | **0** (psycopg only, already required) |
| Framework advisory surface | none |

ADR-012 asks whether a bounded, checkpointed state machine over PostgreSQL is "a few hundred
lines." **It is 202** — and that is a real floor, not a strawman: it passes the same four legs the
frameworks will be held to.

Read it as a floor and not a total, though. Absent and genuinely needed for Milestone 2:
blueprint §8.5's no-progress and duplicate-query detectors, cancellation, tool allowlists,
budget accounting beyond a retry cap, OpenTelemetry spans, and any scheduler or supervisor. Those
will add lines. The comparison to make is not "202 vs. a framework's wiring" but "202 plus what
we still owe vs. a framework's wiring plus what it still owes."

**Caveat on the 16,313 bytes.** The hand-rolled checkpoint stores full finding JSON at three
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
| Candidate-specific code lines | **367** (session repo 159, orchestrator 148, nodes 54, entry 6) | 200 |
| Serialized state at the review interrupt | **23,772 bytes** | 16,379 bytes |
| Distributions beyond what the domain package already needs | **39 (34.1 MB)** — 20.1 MB of it `botocore` | 0 |
| Framework advisory surface | to be tracked | none |

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

#### And it is stronger than the baseline, in the one place that matters

The crash could not be landed *mid*-fan-out: Strands makes each node durable as it finishes, so by
the time the named specialist is durable its sibling already is too. Probing both crash targets
against both candidates:

| Crash after | Candidate | Model calls after resume | Verdict |
|---|---|---|---|
| `specialist_suitability` | hand-rolled | suitability=1, **national_security=2** | **re-ran a completed model call** |
| `specialist_suitability` | strands | suitability=1, national_security=1 | no re-execution |
| `specialist_national_security` | hand-rolled | suitability=1, national_security=1 | no re-execution |
| `specialist_national_security` | strands | suitability=1, national_security=1 | no re-execution |

The hand-rolled candidate commits fan-out results in completion order and dies immediately after
the named node's commit — so a sibling that had already *called the model* but not yet committed
is re-executed on resume. Correctness survives (still three findings), but a paid model call is
spent twice. Strands' per-node sync does not have that window.

**Leg 1 as written does not catch this**, because it asserts only on `specialist_suitability`.
That is a gap in the leg, not a pass the hand-rolled candidate earned. Tightening it to assert
every specialist ran exactly once would fail the hand-rolled candidate as it currently stands;
whether to tighten it belongs with the ADR-012 resolution, not with a quiet edit here. Either way,
the honest reading of the 200-line floor is that **it does not yet include durable handling of
in-flight parallel work**, and adding that is real work.

#### What Strands costs

- **The `SessionRepository` is ours to build, and it is the single largest file in the candidate**
  (159 of 367 lines). The scan predicted this. What the scan could not see is the ratio: a `Graph`
  of deterministic nodes calls only `read/create/update_multi_agent`, yet the abstract base
  requires session, agent, and message CRUD as well. Most of what we implement is never called.
- **State is conversation-shaped.** A node's durable result must be an `AgentResult`, and
  `AgentResult.to_dict` persists exactly `message` and `stop_reason` — `metrics` and `state` are
  dropped. So typed Pydantic contracts have to be flattened into an assistant message body and
  re-validated on the way out. This is the *defensible* core of the third-party claim: execution
  genuinely resumes, but the container for state is a transcript, and a workflow carrying typed
  records pays a serialize/parse tax at every node boundary. It also explains the larger
  checkpoint: 23,772 bytes against 16,379 for the same three findings.
- **`botocore` dominates the footprint** — 20.1 MB of the 34.1 MB added, pulled in whether or not
  a run ever touches AWS. Relevant to a Lambda zip and to `pip-audit` surface, not to correctness.
- **`Graph` owns run status**, so the domain state machine (`is_legal_transition`) is not enforced
  in this candidate the way the hand-rolled one enforces it. Part of why 367 is not directly
  comparable to 200 — see below.

#### Reading the line counts fairly

367 against 200 is not "Strands costs 167 lines". The two carry different things:

- Strands **adds** a `SessionRepository` implementation (159 lines) that the hand-rolled candidate
  does not need, because it writes its own two-table checkpoint (56 lines) instead.
- Strands **omits** the domain run-status machine that the hand-rolled candidate enforces.
- Strands **provides**, at no line cost to us, the per-node durability that the hand-rolled
  candidate demonstrably lacks (table above), plus node scheduling and the interrupt primitive.

The comparison ADR-012 actually needs is "each candidate's wiring **plus what it still owes**",
and both still owe blueprint §8.5's no-progress and duplicate-query detectors, cancellation, tool
allowlists, and OTel spans.

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

### LangGraph — not yet run

Add to `CANDIDATES` in `test_conformance.py` and it inherits the whole suite.

---

## Adding a candidate

1. New workspace member under `spikes/<name>/`, added to `[tool.uv.workspace]`.
2. Implement `ireports_spike_harness.port.Orchestrator`: `start(run_id, crash_after)` and
   `resume(run_id, dispositions)`.
3. `__main__.py` calls `ireports_spike_harness.main(YourOrchestrator())` and nothing else —
   argument handling lives in the harness so no candidate can advantage itself with a different
   invocation shape.
4. Add one line to `CANDIDATES` in `spikes/test_conformance.py`.

Honour `crash_after` at your own node boundaries. Where that boundary sits relative to your
checkpoint write is not an implementation detail — it is what leg 1 measures.

---

## What this does not measure

Stated so the scorecard is not read as more than it is.

- **Cold start and packaging under SAM local.** Not yet run; `MeasuredFootprint.cold_start_seconds`
  is null until it is.
- **OpenTelemetry export.** Blueprint §9.4 lists it; not yet exercised.
- **LangSmith egress-deny**, required if LangGraph is selected (landscape scan §5.1, ADR-012).
- **Developer comprehension.** A judged dimension, recorded with reasoning in the scorecard, not
  produced here.
- **Real model behaviour.** The gateway is a deterministic stub, deliberately — all four legs are
  about control flow, and leg 3 is a *simulated* timeout by definition. This also decouples the
  bake-off from Q-01, which cannot be answered without account access.
