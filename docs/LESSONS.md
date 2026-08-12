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

**What to do.** Parse defensively and never index into a model response. Coerce the two recoverable
shapes (string-encoded JSON, single object where a list was expected), reject everything else with
a reason recorded. Then allow one bounded retry — bounded, because a node that retries until it
likes the answer is selecting for agreeable output rather than correct output.

See `spikes/lambda_demo/src/lambda_demo/specialist.py`. The four malformed shapes we have actually
seen are pinned as test cases in `test_demo.py`.

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

## Orchestration

### LangGraph fan-out state must be defined at module level `[measured]`

A `TypedDict` defined inside a method raises `NameError: Annotated` at graph construction when the
module uses `from __future__ import annotations`. Annotations become strings, LangGraph resolves
them with `get_type_hints`, and a type nested in a function has no resolvable scope.

It looks exactly like a LangGraph bug. It is not. Define fan-out state at module level.

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
