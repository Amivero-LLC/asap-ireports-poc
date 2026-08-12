# Orchestration Bake-off Scorecard

**Milestone 1c** · **Scored: 2026-08-11** · **Status: complete — resolves ADR-012**

**Recommendation: LangGraph.** All three candidates pass all four legs, so this is not a
correctness decision. It is a decision about which costs the program carries for the life of the
system.

The machine-readable version is `orchestration-scorecard.json`, generated from
`spikes/bakeoff_scorecard.py` and validated as a `Scorecard` contract — a candidate row is either
complete or it fails to build. The evidence behind every number is `spikes/README.md`; the
candidates themselves are retained under `spikes/`, losers included (ADR-001).

> **Claim tagging.** `[measured]` — reproduced on this machine by `spikes/measure.py` or
> `uv run pytest spikes`, 2026-08-11. `[first-party]` — from a project's own source, package
> metadata, or official documentation. `[judged]` — one engineer's assessment after building all
> three, recorded with its reasoning.

---

## 1. The table

| Dimension | hand-rolled | **LangGraph** | Strands |
|---|---|---|---|
| Four legs `[measured]` | pass | **pass** | pass |
| Candidate-specific lines `[measured]` | **195** | 266 | 373 |
| …net of spike-only instrumentation | 195 | **~192** | 373 |
| Serialized state at the review interrupt `[measured]` | 16,346 B | **16,115 B** | 23,739 B |
| …total retained for the run | **16,346 B** | 37,033 B | 23,739 B |
| Distributions beyond the harness baseline `[measured]` | **0** | 31 | 42 |
| Added installed size `[measured]` | **0.0 MB** | 18.0 MB | 47.3 MB |
| Open advisories, pinned set (`pip-audit`) `[measured]` | 0 | 0 | 0 |
| Import cost under SAM local `[measured]` | **~0.5 s** | ~1.6–2.3 s | ~1.5–1.8 s |
| Package under Linux wheels, zipped `[measured]` | **9.1 MB** | 19 MB | 34 MB |
| Duplicate paid model call, 24 mid-fan-out crashes `[measured]` | 12/24 | 11/24 | 0/24 † |
| Budget and allowlist enforcement `[judged]` | adequate | adequate | adequate |
| State inspectability `[judged]` | adequate | **good** | adequate |
| Test determinism `[judged]` | good | good | good |
| Developer comprehension `[judged]` | **good** | adequate | adequate |

† Not a durability property — an artifact of our synchronous node bodies. §4.

Framework versions, pinned: `langgraph` 1.2.10 with `langgraph-checkpoint-postgres` 3.1.2,
`langgraph-checkpoint` 4.2.0, `langchain-core` 1.5.3, `langsmith` 0.10.17; `strands-agents`
1.51.0; hand-rolled has none.

---

## 2. Why LangGraph

**The thing this milestone existed to de-risk cost two lines.** ADR-012 named durable
checkpointing over PostgreSQL as the load-bearing capability and predicted that a first-party
checkpointer would be the dimension that separated the candidates. It was. Persistence in the
LangGraph candidate is `PostgresSaver.setup()` and passing the saver to `compile()`. Strands
needed a 166-line `SessionRepository`; the hand-rolled candidate needed a 56-line checkpoint
store. And the durability LangGraph provides is finer-grained than either: when a task completes,
its output is written as *pending writes* against the current checkpoint, and on resume those
writes are applied rather than the task re-run — so durability is per-task inside a super-step,
not per-super-step `[measured]`.

**Its orchestration wiring is smaller than the hand-rolled floor.** 57 of the 266 lines are the
byte-measuring query that exists only to fill in the table above, and 17 are the `--crash-after`
hook, which is spike scaffolding. Net wiring is ~192 lines against the hand-rolled candidate's 195
— while additionally providing node scheduling, a native interrupt, and declarative per-node
retry `[measured]`.

**It is the only candidate with a written stability commitment.** LangGraph publishes a release
policy: semver, breaking changes only in majors, majors at least 6–12 months apart, 1.0 ACTIVE
until 2.0 with at least a year of maintenance afterwards `[first-party]`. For a program that must
pin versions and defend them through an ATO, this is the most valuable single property in the
1b scan, and neither alternative offers it — Strands has no equivalent commitment, and the
hand-rolled candidate's stability is entirely a function of who maintains it.

**Its costs are now controlled rather than argued about.** Both of its wrong-for-us defaults are
pinned in code with tests (§3), and the mandatory LangSmith client is pinned closed and *proven*
closed with a negative control. That was the condition ADR-012 attached to selecting it, and it is
met.

### The two qualifications that ride with this recommendation

**Cold start under SAM local — measured 2026-08-11, and it does not reopen the decision.** This
was the one outstanding measurement most likely to: 31 distributions and 18 MB is either
irrelevant or decisive depending on what it does to a Lambda cold start. ADR-023 took it in
`spikes/lambda_fit/`, packaging each candidate into a real Lambda container with Linux wheels.
LangGraph imports in roughly 1.6–2.3 s against ~0.5 s for the framework-free control — about 3× —
at 19 MB zipped against a 50 MB limit. On a workload where a single specialist model call runs
tens of seconds, and where cold starts occur on scale-up rather than per request, that is
affordable. **The dependency-weight objection was the strongest argument against LangGraph and the
number does not support it.**

Two honest notes on the figure. It is load-sensitive — three runs on one machine moved LangGraph's
median between 1.565 s and 2.303 s — so it is a comparison between candidates on identical
footing, not a production cold-start number `[unverified]`; a real one needs a deploy to Lambda,
gated on Q-01. And `test_cold_start_is_null_and_stays_visible`, which used to fail the moment a
number was filled in, has done its job and been replaced: `spikes/test_scorecard.py` now guards
the *conclusion* — figures under a 3 s ceiling, LangGraph within 5× the control.

**The hand-rolled candidate is a genuine runner-up, not a strawman.** If the program refuses the
dependency surface, 195 lines that pass the same four legs is a defensible answer with a known
ledger attached. Nothing in this recommendation should be read as saying it would not work.

---

## 3. What selecting LangGraph obliges us to carry

Recorded here rather than in a footnote, because these are the terms of the recommendation.

| Obligation | Status |
|---|---|
| `durability="sync"`, not the library default `async` | Set in code (`orchestrator.DURABILITY`) |
| Strict checkpoint deserialization, not the permissive default | Set in code (`checkpointer.strict_serde`), tested both ways |
| LangSmith pinned closed at the entry point and verified | `telemetry.pin_tracing_closed`, four-scenario test with a negative control |
| Checkpoint history retention policy | **Owed.** 37,033 B retained per run and growing; ties to Q-09 |
| Checkpoint row integrity (keyed MAC) | **Owed by every candidate.** `checkpoint-threat-model.md` §6 |
| `pip-audit` in CI against the pinned set | Already mandated by `CLAUDE.md`; 0 advisories today |
| Nodes depend on our port, never on LangGraph directly | ADR-012 already requires this; enforced when `packages/orchestration` lands |

**Two of these are defaults that are invisible in the code**, which is the most transferable
finding in the whole bake-off. A LangGraph graph reads identically whether persistence is
synchronous and whether deserialization is allowlisted. The library's own source is explicit about
the second: *"any Python callable stored in checkpoint data will be imported and executed on
load"* without the strict setting `[first-party]`. A reviewer cannot catch either by reading the
graph; they can only catch them by knowing to look.

---

## 4. What the bake-off settled that reading could not

Three measurements the 1b landscape scan flagged as unanswerable without running code.

**Resume semantics under a mid-node process kill.** The scan recorded an unconfirmed third-party
claim that Strands restores *conversation* rather than resuming *execution*. **It does not hold**
for `Graph` in 1.51.0: `serialize_state` carries `completed_nodes` and `next_nodes_to_execute`,
state syncs after every node, and after a hard `os._exit(9)` no completed node re-executed. The
same was asserted rather than assumed for LangGraph, with the same result `[measured]`. What *is*
true of Strands is narrower and still material: its state *container* is a transcript, so typed
contracts are flattened into an assistant message body and re-validated on the way out.

**The duplicate-model-call window is universal.** The 2026-08-10 write-up recorded Strands'
0-of-12 as an artifact of our synchronous node bodies — which stop its asyncio tasks from ever
interleaving — and predicted that a candidate with genuine concurrent fan-out would show the same
window as the hand-rolled one. LangGraph is that candidate and it does: over 24 trials the
sibling's model call was in flight at crash time in **24/24** and cost a duplicate paid call in
**11/24**, against hand-rolled's 12/24 `[measured]`. Strands' numbers partition cleanly and
confirm the artifact reading: in the 14 trials where the sibling had been called it never re-ran,
and in the 10 where it re-ran it had never been called.

So this is a property of at-least-once execution with uncommitted in-flight calls, **not** a
discriminator between frameworks. **Model-call-level idempotency — blueprint §8.5's
duplicate-query detection — is owed by all three, and none of them has it.** It belongs on the
Milestone 2 plan regardless of which candidate was selected.

**The checkpoint blob is a deserialization trust boundary in every design.**
`docs/handoff/checkpoint-threat-model.md`, framework-independent, including §6's honest list of
controls this project has *not* built. The one asymmetry worth recording is direction of default:
LangGraph's serializer must be explicitly hardened, while the hand-rolled store has no
deserialization surface beyond `json.loads` because it never grew one. That is a point against
LangGraph on this dimension, and a small one — the hardening is one constructor argument and a
test.

---

## 5. What this scorecard does not say

- **It does not say the losers would fail.** All three passed identical assertions. Both are
  retained in the repository with their reasoning, per ADR-001.
- **It does not include OpenTelemetry export.** Blueprint §9.4 lists it alongside cold start and
  packaging size; those two were run under ADR-023, this one was not.
- **It does not measure real model behaviour.** The gateway is a deterministic stub, deliberately:
  all four legs are about control flow, and leg 3 is a simulated timeout by definition. This also
  keeps the bake-off decoupled from Q-01, which cannot be answered without GovCloud account
  access.
- **The judged columns are opinions**, held to a three-point scale so a close call is settled by
  argument rather than by rounding. Each carries its reasoning in the JSON.
- **It does not settle where analysis nodes live.** ADR-012 requires that the orchestration
  package be defined by our own port so nodes depend on our interface rather than LangGraph's.
  That constraint survives this decision unchanged and is Milestone 2's first obligation.
