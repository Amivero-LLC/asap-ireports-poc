# Lessons learned

Things that cost us time, that you would otherwise pay for again. This is a **living document** —
append to it whenever something surprises you, while it is still fresh. A lesson written a week
later is half a lesson.

Each entry says what happened, what it looked like from the outside, and what to do. The "looked
like" part matters most: nearly everything here first presented as a *different* problem, and the
time went into the misdiagnosis, not the fix.

**Convention:** `[measured]` means we observed it in this repo and you can re-run it.
`[documented]` means it comes from a vendor source, cited. `[believed]` means we think so and
have not checked — treat as a lead, not a fact.

---

## Models and the gateway

### Structured output is a request, not a guarantee `[measured]`

**What happened.** We ask for a JSON schema and get valid JSON back — usually. Roughly **one call
in three** returns `findings` as a JSON *string* rather than an array, or as a bare object where an
array was asked for, or as an array containing a bare string. Same schema, same prompt, same model.

**What it looked like.** Intermittent empty results that read as model nondeterminism or a bad
prompt. We rewrote the prompt twice before realising the prompt was fine and the *shape* was wrong.

**What to do.** Parse defensively and never index into a model response. Normalize the recoverable
shapes, reject everything else with a reason recorded, then allow one bounded retry — bounded,
because a node that retries until it likes the answer is selecting for agreeable output rather than
correct output.

Every shape below came from the *same* schema and the same prompt:

| Returned | Handling |
|---|---|
| `[...]` | The requested shape |
| `"[...]"` — the array as a JSON string | Parse it |
| `{...}` — one finding where an array was asked for | Wrap it |
| `{"findings": [...]}` — **the envelope repeated inside itself** | **Unwrap it** |

See `packages/orchestration/src/ireports_orchestration/specialist.py`; all of them are pinned as
test cases in `tests/orchestration/test_orchestration.py`.

### The nested-envelope shape caused silent under-analysis for weeks `[measured]`

Worth its own entry, because of *how* it hid.

**What happened.** The coercion above handled a bare object by wrapping it. When the model returned
`{"findings": {"findings": [...]}}`, wrapping produced `[{"findings": [...]}]` — an object missing
every required field — which the validator correctly rejected. **So a response the model had
answered perfectly well, only nested one layer too deep, was recorded as unparseable and the
criterion reported zero findings.**

**What it looked like.** A criterion that came back clean. Which is precisely the failure this
system is built to prevent: silent under-analysis is indistinguishable from a clean record, and it
is the most dangerous thing this architecture can produce.

**How it was found.** The rejection message said `missing/blank ['title', 'observation', ...]` and
stopped there — true, and useless. Adding the keys that *were* present turned it into
`missing/blank [...] (keys present: ['findings'])`, and it was diagnosed on the next run.

**The measured effect of the fix**, same case, same criteria, one run each:

| | Before | After |
|---|---|---|
| Findings | 5 | 7 |
| Shape rejections | 5 | **0** |
| Tokens | 28,759 | 19,717 |

Fewer tokens *and* more findings, because the wasted retries were firing on responses that were
already fine.

**The lesson is about diagnosability, not parsing.** A rejection that does not say what it saw
cannot be acted on. Spend the extra line.

### A coercion in a private helper protects one call site `[measured]`

The first live run after the orchestration graduated found the nested-envelope bug's sibling, and
found it the expensive way.

**What happened.** `synthesis.py` asks the same provider, under the same structured-output setting,
for two arrays. The model returned both as JSON *strings*. `for index, raw in enumerate(payload
.get("contradictions") or [])` over a string enumerates **characters**, so the loop produced one
rejection per character:

```
synthesis/gap#2893: not an object — dropped
synthesis/gap#2894: not an object — dropped     ← 4,547 of these across the two arrays
```

Zero synthesis findings. No error, no warning, a valid envelope, and both orchestrators
independently — because they share the synthesis implementation, so this was never going to be a
one-path bug.

**The part worth remembering.** On the *same run*, in the *same process*, the specialist path
handled the identical shape correctly. It had `_normalize_findings`, written when the nested-envelope
bug was found, and the fix never left that module. Two call sites, one protected, and nothing
connected them. The fix is `coercion.py` — one `normalize_array` both stages import — not a second
copy in synthesis.

**And a second failure on top of the first.** The rejection record is supposed to be the diagnostic
(*Rejections are output, not error logging*, below). Four thousand copies of "not an object" is not
a diagnostic; it buried the two rejections that mattered and put 4,547 strings into the envelope's
accounting payload. A non-list is now named **once**, saying what type it actually was, and every
stage caps its rejection list at 50 with an honest suppressed count. A reader has to be able to
tell "three findings were dropped" from "four thousand were, and you are seeing fifty."

**Do not return `[]` when coercion fails.** `normalize_array` returns the uncoercible value so the
caller can name it. Returning an empty list would convert an unreadable response into a clean empty
one, which is this system's worst failure mode wearing a tidy shape.

### `output_config.format` is accepted and silently not enforced `[measured]`

**What happened.** Against a Bedrock-backed LiteLLM proxy, `output_config.format` returned HTTP 200
on every model group tested and was **enforced by only some of them** — best case 6 of 8 on one
model, 0 of 8 on others. The failure mode is a Markdown-fenced code block instead of bare JSON.

**What to do.** Use a **single-tool call** for structured output instead. One tool, described as
"call this exactly once, do not answer in prose," returned validated input 20 of 20 across all
groups tested. Three things must be absent or it breaks:

| Do not send | Why |
|---|---|
| `strict: true` | Bedrock rejects it — "Extra inputs are not permitted" |
| `tool_choice` | Forcing the tool 400s when adaptive thinking is on |
| `output_config.format` alongside the tool | Two mechanisms competing to shape one response |

The tempting fix — stripping the Markdown fence — is wrong twice: it hides that schema enforcement
is a per-model-group property, and it turns a detectable fault into a lenient parser that will
eventually accept something that is not a finding at all.

### One refusal killed the entire run `[measured]`

`gateway.complete()` was called bare inside the specialist. A model refusal raised through the
thread pool or the graph and **took the whole run down**, discarding every other specialist's
completed and already-paid-for work.

**Under Lambda it is worse than on a laptop:** the invocation fails, Lambda retries automatically,
every model call is paid for a second time, and the retry hits the same refusal.

Two things made this survive for weeks:

- It needs a refusal to trigger, and refusals do not happen on every run.
- ADR-021 had already decided the node should catch it. **A decision that is recorded but not
  implemented reads exactly like a decision that was implemented** — nothing in the code or the
  tests contradicted the ADR, because nothing tested it.

If a decision record says "the node catches it," write the test that proves the node catches it.

### `completed with no findings` and `refused` must not look alike `[measured]`

Both produce zero findings. If the run cannot tell them apart it reports **silent under-analysis as
a clean record**, which is the worst output this system can produce.

So the outcome carries a status — `COMPLETED` / `REFUSED` / `FAILED` — and the run surfaces
`not_analysed` at the top of its payload. It costs one enum and it is the difference between "this
criterion is clean" and "nobody looked at this criterion."

Note what this does *not* do: it does not put the distinction in the envelope. ADR-021 §2 weighed
that and chose to keep it out of the contract. So a reviewer in ASAP still cannot tell — the gap is
narrowed to the operator, not closed. **That remains the weakest point in the design**, and
closing it means superseding ADR-021, deliberately.

### A refusal returns HTTP 200 `[measured]`

Claude can decline a request and still return 200, with `stop_reason: "refusal"` and a possibly
empty content list. Code that reads `content[0]` turns that into an empty result — which for an
analysis system is the worst possible outcome, because **silent under-analysis looks exactly like a
clean record**.

Check `stop_reason` *before* touching content. Raise, don't return empty.

This matters more here than in most applications: adjudicative case files routinely discuss
criminal conduct, substance use, and foreign contacts, so refusals are expected in normal
operation, not an edge case.

### Sampling parameters are rejected on current models — except when they aren't `[measured]`

`temperature`, `top_p`, and `top_k` are documented as rejected by current Claude models, and
`thinking.budget_tokens` was removed in favour of `output_config.effort`. **Through a LiteLLM
proxy, both were accepted anyway.** The proxy path is more permissive than the first-party API.

Don't read "it worked through the proxy" as "it is supported." Steer with prompts, validators, and
`effort` per tier.

### Never hard-code a model ID

Application code names a *tier* — `ireports-orchestrator`, `ireports-thinking`, `ireports-fast` —
and configuration resolves it. This is not style. A partition change, a region change, or a model
generation change should be a config edit, and on Bedrock the IDs differ from the first-party ones
anyway (`anthropic.claude-sonnet-5`, not `claude-sonnet-5`).

---

## AWS and deployment

### `bedrock-mantle` is GovCloud **US-West only** `[documented]`

Claude Sonnet 5 is available on `bedrock-runtime` endpoints in **GovCloud US-West and US-East**,
but on `bedrock-mantle` endpoints in **US-West only**
([AWS, 2026-07-23](https://aws.amazon.com/about-aws/whats-new/2026/07/claude-sonnet-5-govcloud/)).

Our `bedrock` adapter uses `AnthropicBedrockMantle`, because the Mantle endpoint speaks the
Messages API and keeps request handling identical to the LiteLLM adapter. **So region choice
constrains adapter choice.** Deploy to GovCloud US-East and that adapter has no endpoint; you need
a `bedrock-runtime` adapter, which is real work — it needs its own translation layer for thinking,
effort, and refusals.

Decide the region before you decide the adapter. See `docs/AWS.md`.

### `sam local invoke --env-vars` silently drops undeclared variables `[measured]`

**What happened.** Environment variables were plainly set in the shell and written into the
`--env-vars` file, and the function still failed inside the container reporting a missing
`IREPORTS_LITELLM_BASE_URL`.

**Why.** SAM only *overrides* variables the template already declares. Anything not in the
template's `Environment.Variables` is dropped without a word.

**What to do.** Declare every variable in `template.yaml` with an empty default, and have your
runner read that list back out of the built template so the two cannot drift. See
`spikes/lambda_demo/template.yaml` and `run_case.py`.

### `sam build --use-container` is not optional

`pydantic-core` and `psycopg[binary]` ship native extensions. A macOS build produces macOS wheels
that will not load in a Lambda container, so a host build packages something that cannot run — and
you find out at invoke time, not build time.

### Half your Lambda package may be boto3 you don't need `[measured]`

Our LangGraph function is 28.9 MB zipped / 82.4 MB unzipped. The boto3 family is **15.2 MB of the
zipped total** — more than half — pulled in by `anthropic[bedrock]`.

The managed Lambda runtime **already ships boto3**: `public.ecr.aws/lambda/python:3.12` carries
boto3 and botocore 1.42.97 `[measured]`. Exclude it from the package and use the runtime's copy.
The caveat is version drift — the runtime's boto3 lags PyPI, so pin-sensitive code needs a layer.

Note what *not* to do: dropping the Bedrock adapter to save the space. That trades a proxy-free
path to a model for space the runtime gives away free.

### SAM local does not emulate the init/invoke split

`sam local invoke` reports `Init Duration: ~0.05 ms` for every function. **That number is
meaningless.** If you want import cost, time it yourself inside the handler module. Anything you
measure locally is an indicative comparison between candidates on identical footing, never a
production cold-start figure.

---

## Retrieval

### Scope citation checks to what the model was shown `[measured]`

Before retrieval, a specialist saw the whole case and citations were checked against it. With
retrieval those are different sets, and keeping the check at case scope would let a model cite a
span it was never given — which is indistinguishable from a lucky hallucination and passes silently.

Check against the retrieved set. And record it: `SpecialistOutcome.retrieved` is what makes "why did
the financial criterion miss this?" answerable, and the answer is usually that retrieval never
surfaced the span.

### Fixing one context-stuffing site does not fix the others `[measured]`

Specialists were switched to retrieval; synthesis was left pasting the whole case. At 430 tokens
that was invisible. On the first 35,000-token case the synthesis call exhausted `max_tokens` while
thinking and returned no text at all — and took the run down with it, because it had no failure
containment either.

Two lessons, one incident: **grep for every place that builds a prompt from the full corpus**, and
**a stage that calls a model needs the same containment as every other stage.** The refusal fix from
item 3 was applied one layer down and not carried up.

### Estimate token savings from the spans you actually retrieve `[measured]`

Predicted 7× fewer input tokens from retrieval; measured **3.0×** (69,139 against ~209,664 for
paste-everything, six calls on a 35k-token case).

The gap: I costed k=6 at the corpus *average* span size. Retrieval does not return average spans —
it returns the large, content-rich ones, because those are what match. Cost k from the biggest
plausible spans, not the mean.

Also worth separating: output tokens (25,632 here, thinking at `effort=high`) are unaffected by
retrieval. Only the input side moves.

## Orchestration

### Every type LangGraph inspects must resolve from module scope `[measured]`

We hit this twice, in two different disguises, before seeing the general rule.

1. A `TypedDict` defined inside a method → `NameError: Annotated` at graph construction.
2. A conditional-edge function annotated `-> list[Send]`, where `Send` is imported *inside* the
   method → `NameError: name 'Send' is not defined`.

**The rule:** `from __future__ import annotations` turns every annotation into a string, and
LangGraph resolves them with `get_type_hints` at module scope. So any type named in a signature
LangGraph inspects — node, conditional edge, state — must be importable from module level.

Both failures look exactly like a LangGraph bug. Neither is. The collision is between two
individually reasonable choices: postponed annotations, and a lazy framework import that keeps the
framework optional in the package.

If you must keep the import lazy, **leave the return type unannotated**. That is uglier than the
alternatives and it is the only one that works.

### A `Send` node receives the payload, not the graph state `[measured]`

Dynamic fan-out goes through `Send("node", payload)`, and the target node's argument is that
payload — not the accumulated state. So the node signature changes meaning entirely when you move
from static nodes to `Send`, and no type checker will catch it, because the signature is whatever
you wrote.

### A conditional edge after `Send` fires per dispatch, on partial state `[measured]`

**The most dangerous LangGraph behaviour found so far**, because it fails silently and produces a
plausible answer.

A `Send` fan-out dispatches one node N times. Put a **conditional edge** on that node and the
router runs **N times, each seeing only its own dispatch's contribution to state.** Measured
directly with five dispatches:

```
router invoked 5 times; outcomes visible each time: [1, 1, 1, 1, 1]
```

Never five. So a routing decision about the *aggregate* of a fan-out — "did we find enough to be
worth a second stage?" — is made five times on one-fifth of the evidence. In our case every branch
saw one finding, the threshold was two, and **synthesis silently never ran.** No error, no warning.

A **plain** edge behaves differently: it joins, and the target runs once. So the fix is a do-nothing
node whose only job is to be the join point, with the conditional edge leaving *it*:

```python
graph.add_edge("specialist", "join")                       # plain edge: joins, runs once
graph.add_conditional_edges("join", route, ["synthesis", END])
```

The hand-rolled equivalent of this whole problem is `if should_synthesize(outcomes):`.

**This is the clearest evidence yet in the ADR-024 comparison** — not because LangGraph is wrong,
but because the correct construction is non-obvious, the incorrect one runs cleanly, and you only
find out by counting.

### Route on shared code, not in each orchestrator `[measured]`

`should_synthesize()` lives in one place that both paths call. The pull is to inline it — an `if`
in one, a router in the other — and that is how two implementations of the same run drift into
producing different envelopes for reasons nobody can see.

We nearly shipped a version of this: the "should this stage run" rule existed *both* in the router
and as an early return inside `synthesize()`. Two copies, and the second one silently won on one
path. Policy in one function; the orchestrators only choose how to schedule it.

### The fan-in barrier is free in both paths `[measured]`

Adding a second stage that needs *every* specialist's output looked like the place a graph
framework would pull ahead. It was not:

| | How the barrier happens |
|---|---|
| Hand-rolled | Exiting the `ThreadPoolExecutor` context. `pool.map` has already collected everything |
| LangGraph | Supersteps. A node downstream of a `Send` fan-out does not start until every dispatch finishes |

One line each, neither of them written by hand. **Recorded because it is a null result and those
are worth as much as the other kind** — the prediction was that LangGraph would win here, and it
did not. What LangGraph adds shows up in the *next* stage (conditional routing) and in
checkpointing, not in joining.

### Decide what the model is competent to answer, and don't pay for the rest `[measured]`

The second stage does two things that look similar and are not:

- **Which findings rest on the same evidence span** — set arithmetic. Exact, instant, free.
- **Whether two statements in the record conflict** — a judgement about meaning. Worth a model
  call.

We nearly asked the model for both. The computed half turned out to be the more useful output: on
the demo case it reports that `ev_003` and `ev_004` each carry findings under **four** criteria,
which is precisely the "you are looking at one fact four times" signal a reviewer needs — and a
model asked the same question would be slower, cost money, and occasionally be wrong about
something with an exact answer.

Before writing a prompt, check whether the question has an exact answer.

### Telling a synthesis step *not* to restate is what makes it useful `[measured]`

The first instinct is to let a cross-criterion stage summarise. Two rules changed its output from
noise to signal:

- **"Do not restate a finding a single analyst already made."** Without this it rewrites the
  specialists' work back at you.
- **"One fact reported under several criteria is not a contradiction."** Without this it reports
  the overlap as a discrepancy — the thing we compute deterministically, guessed at badly.

With both, it reported zero contradictions on a case that has an obvious one — correctly, because
the candor specialist had already found it — and instead surfaced gaps that were genuinely
invisible from any single criterion: *the financial criterion evaluated the debt in isolation while
the foreign income was treated only as a disclosure issue, and nobody cross-referenced them.*

Also load-bearing: **no summary, no ranking, no overall assessment.** A "synthesis" that concluded
something about the person would be the determination this system must never make, wearing a
helpful-sounding name.

### Dynamic fan-out width is free in Python and structural in LangGraph `[measured]`

Moving fan-out width from a constant to runtime data (derived from the case) was the first change
where the two orchestration paths genuinely diverged:

| | Change required |
|---|---|
| Hand-rolled | **None.** `pool.map` never cared how long the list was |
| LangGraph | **Rebuilt around a different primitive.** One node per criterion added at construction only works if the criteria are known before the graph is built. They are not, so it became one node dispatched N times via `Send` |

The LangGraph version is not worse — arguably better, because the graph shape is now constant while
the work is variable, which is the property a checkpoint needs (a checkpoint refers to node names
that must still exist on resume). But it is a *structural* change where the other path had none,
and that asymmetry is the kind of evidence ADR-024's decision should rest on.

### LangGraph's documented `Send` pattern does not survive `mypy --strict` `[measured]`

Graduating the orchestration out of `spikes/` and into `packages/` moved it under the same
`mypy --strict` gate the rest of the repo runs. The hand-rolled adapter needed **no change**. The
LangGraph adapter produced four errors, and every one of them is the framework's typing
disagreeing with the framework's own documented pattern:

| Error | What it is |
|---|---|
| `add_node("specialist", specialist_node)` matches no overload | The overloads assume a node receives the graph **state**. A `Send`-dispatched node receives the *sent payload* — a `Criterion` — which is exactly what LangGraph's docs prescribe |
| `add_node("join", join)` matches no overload either | And **not** for that reason: `join` takes `FanOutState` like any ordinary node. `synthesis_node`, same parameter type, different return type, resolves fine. Whatever separates them is invisible at the call site |
| `StateGraph` needs type arguments | Generic in four parameters at runtime; written unparameterised in every example |
| Two router callables cannot be annotated at all | `Send` and `END` are not resolvable from module scope under postponed annotations (see the module-scope lesson above), and an unannotated function is a `--strict` error by definition |

So the four suppressions in `langgraph_adapter.py` are load-bearing rather than lazy, and each
carries its reason. **This is a cost, not a verdict** — the thing that decides ADR-024 is durable
checkpointing, which none of this touches. But it is the fourth asymmetry in a row, and all four
favour the hand-rolled path on simplicity.

### Moving code into a type-checked tree finds bugs the tests did not `[measured]`

The same move surfaced a variable in `synthesis.py` used as a set of the spans all findings rest
on, then re-bound in a loop below to a list of one contradiction's spans. Harmless by accident of
ordering — the set is finished with before the loop starts — and invisible to every test, because
the behaviour was correct. `mypy` reported it as an incompatible assignment on the first run.

The lesson is not about that variable. It is that `spikes/` being outside the quality gate is a
real gap, and the moment code stops being a spike it should stop being exempt.

### The concurrent-write reducer is the whole trick

When several branches write the same state key, you need `Annotated[list[X], operator.add]`.
Without it LangGraph raises on the concurrent update; with a plain dict the branches clobber each
other **silently**, which is worse. The silent version is the one that will reach production.

### Keep the framework import lazy at the adapter, eager at the entry point

`LangGraphOrchestrator` imports LangGraph inside `run()`, so a package built without LangGraph can
still import the module and run the other orchestrator. But the Lambda handler imports it at module
scope on purpose — otherwise the cost moves from Lambda's init phase to the first invocation, which
is a different billing and latency story.

Both are deliberate. Neither is obvious from reading one file.

---

### A hard-coded classification is invisible until the record is clean `[measured]`

`specialist.py` set `classification=FindingClassification.POTENTIAL_ISSUE` as a **constant**, and
the response schema never asked the model to classify at all. Two of the contract's five values —
`MITIGATING_INFORMATION` and `NO_ISSUE_IDENTIFIED` — were unreachable from the specialist path
from the day it was written.

Nothing caught it for weeks because every case run against the system contained real concerns, and
on those records the constant is right most of the time. The first deliberately clean case
(`AMI-SYN-CLR-001`, 2026-08-17) produced seven findings whose *text* was correct and whose *label*
was not:

| Finding title | Delivered as |
|---|---|
| "Criminal history and financial record checks returned **no indicators** of criminal or dishonest conduct" | `potential_issue` |
| "Investigator's consistency assessment identifies **no material omissions or inconsistencies**" | `potential_issue` |

The analysis was good — it found the creditor's written admission of error, led with the
resolution, and deferred the judgment to the officer. The envelope still told a reviewer it had
found seven potential issues on a clean file.

**The general lesson is about the test, not the field.** A constant that is usually correct is
indistinguishable from a decision until you run the case where it is wrong. Every fixture built
alongside a system inherits that system's assumptions; the case that disagrees with you is the one
worth building.

**And it surfaced a rule conflict nobody had noticed.** The specialist prompt says an empty
findings array is a good answer. `EnvelopeAnalysis.findings` has `min_length=1`, so a run with no
findings produces no envelope at all. On a genuinely clean record those two rules cannot both be
satisfied — and a model with no way to say "clean" will reach for the only classification it has.

## Contracts and validation

### Prefixed IDs catch transpositions — and fail far from the mistake

`run_id` and `finding_id` are passed adjacently through orchestration and delivery. As bare
strings, swapping them is invisible. Prefixes (`run_`, `fnd_`, `ev_`) make it a validation error.

**The trap:** we passed `run_id="demo_langgraph"` — no `run_` prefix. It did not fail at the top.
It failed on *every finding*, because `finding_id` embeds the run id. The run burned three model
calls and reported zero findings, which reads exactly like model nondeterminism. Cost several runs
before we saw it.

Validate identifiers at the entry point, where the error can still name itself.

### Validate citations by dropping the finding, not by trimming it

A finding citing evidence that is not in the case gets **dropped**, not repaired. Trimming the bad
citation would leave an observation standing on evidence nobody can open — which is the exact
failure the architecture exists to prevent.

### A span serves one role per finding, and models don't respect that

Models routinely cite the same evidence span as both supporting *and* mitigating — usually an
investigator finding that establishes a fact and softens it in the same sentence. Rather than drop
otherwise-good analysis, resolve it deterministically (supporting wins, since it is the basis of
the observation) and **record the demotion** so the adjustment is visible rather than silent.

### Rejections are output, not error logging

Every rejection — bad citation, malformed shape, determinative language — is part of the result and
should be returned with the run. They are the deterministic shell doing its job. A pipeline that
hides them looks cleaner and tells you nothing about where its safety actually lives.

Corollary: **a silently empty result is the worst outcome.** Zero findings with no reasons is
indistinguishable from a clean record. Always leave a reason behind.

### The prompt asks; the type enforces

The system prompt asks the model not to write determinative language. `DecisionSupportText`
*rejects* it at construction. When the model wrote "the subject violated SEAD-4," the prompt had
already failed and the type is what stopped it.

Put your real constraints in types and validators. Prompts are requests.

---

## Process

### An unanswerable question is often just an unasked one

We recorded GovCloud model availability as a gate that "refuses any working assumption," treated it
as externally blocked on account access, and **cut three requirements** because of it. A web search
answered most of it: Claude Sonnet 5 has been in GovCloud since July 2026, FedRAMP High and DoD
IL4/5 approved, and the Mantle endpoint exists in US-West.

Before declaring something unknowable, spend ten minutes trying to know it. Formal uncertainty
accounting is not a substitute for looking it up.

### Measure with `stat`, not `du`

We published a Lambda package as 37 MB zipped. It is 28.9 MB. `du` reports disk usage with block
rounding; `stat -f%z` reports bytes. For a number being compared against a hard limit, use bytes.

### Write the trap next to the code that avoids it

Every lesson here started as a comment in the module where it applies. That is the version people
actually read — this document is the index, not the source of truth. If you fix something subtle,
leave the explanation at the fix.
