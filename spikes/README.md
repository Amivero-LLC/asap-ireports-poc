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

### LangGraph, Strands — not yet run

Add to `CANDIDATES` in `test_conformance.py` and they inherit the whole suite.

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
