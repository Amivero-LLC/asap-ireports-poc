# Model Compatibility Matrix

**Partial evidence for Q-01.** Blueprint §15.3 asks for a compatibility matrix rather than prose;
this is that file. It records what has actually been observed against a real endpoint, and — more
importantly — what has not.

> ## This says nothing about AWS GovCloud
>
> Every measurement below was taken against a **commercial-partition** AWS Bedrock deployment,
> reached through an organisation-shared LiteLLM proxy. Model availability, concrete model and
> inference-profile IDs, cross-region inference rules, and data-routing behaviour in
> **AWS GovCloud (US)** remain **unvalidated**.
>
> A model that answers here may be absent there. An endpoint that resolves here may not exist
> there. A request shape accepted here may be rejected there.
>
> **Q-01 is not closed and is not narrowed by this document.** It is closed by someone running
> these same checks in the target account, in the target partition, and pasting the result into
> the table below. See `docs/OPEN-QUESTIONS.md`.

---

## 1. Run of record

| | |
|---|---|
| Date | 2026-08-10 |
| Partition | AWS commercial (**not** GovCloud) |
| Route | Organisation-shared LiteLLM proxy → Amazon Bedrock |
| Adapter | `litellm` (ADR-015), official `anthropic` SDK 0.121.0 |
| Reproduce | `IREPORTS_LIVE_SMOKE=1 uv run pytest tests/live -v -s` |
| Source | `tests/live/test_live_smoke.py` |

This was the first real model call this project has ever made. Every prior gateway test was
offline, so before this the gateway was verified as *correctly constructed*, not as *working*.

---

## 2. Tier mapping used for this run

**Local development only. Not a recommendation, and not an answer to Q-01.** The three tiers were
mapped onto model groups the shared proxy happens to expose, chosen to exercise three *different*
code paths rather than to propose a production configuration.

| Alias | Model group | Effort | Why this one |
|---|---|---|---|
| `ireports-orchestrator` | `anthropic.claude-sonnet-5` | `medium` | Current-generation Sonnet; native Bedrock request path |
| `ireports-thinking` | `anthropic.claude-opus-4-8` | `high` | Highest-capability group available; native Bedrock request path |
| `ireports-fast` | `bedrock/anthropic.claude-haiku-4-5-20251001` | `low` | Natural fast tier, **and** it routes through LiteLLM's translation layer rather than natively — see §5 |

---

## 3. Results

| Alias | Outcome | Resolved model | `stop_reason` | in/out tokens | Schema enforced |
|---|---|---|---|---|---|
| `ireports-orchestrator` | answered | `anthropic.claude-sonnet-5` | `end_turn` | 19 / 5 | **no** |
| `ireports-thinking` | answered | `anthropic.claude-opus-4-8` | `end_turn` | 19 / 5 | yes |
| `ireports-fast` | answered | `bedrock/anthropic.claude-haiku-4-5-20251001` | `end_turn` | 44 / 42 | **no** |

No refusals occurred on this run. A refusal would have been recorded as a **pass** for
connectivity purposes and reported in its own column — refusals are expected traffic for an
adjudicative domain, not a failure (`docs/handoff/model-gateway.md` §3).

---

## 4. Request-surface support

ADR-015 rests on the claim that the Anthropic request surface survives the LiteLLM hop. That is
now measured rather than assumed.

| Field | Result | How it was established |
|---|---|---|
| `output_config.effort` | **forwarded and honoured** | An invalid value returns `400` naming the real enum (`low, medium, high, xhigh, max`). `effort: low` vs `high` on the same prompt changed whether a `thinking` block was returned, the output-token count (3 vs 344), *and* the answer's correctness. A dropped parameter cannot do that. |
| `thinking: {type: adaptive}` | **forwarded and honoured** | `display: "summarized"` returned a populated `thinking` content block. |
| `output_config.format` | **accepted; enforcement varies by model group** | See §5 — this is the important row. |
| `temperature` | accepted (**not** rejected) | Expected to `400` on current models; it returned `200` instead. Our gateway never sends sampling parameters, so this is informational — but note the endpoint would **not** have caught the mistake. The guard rail is ours, not the platform's. |
| `thinking.budget_tokens` | accepted (**not** rejected) | Expected to `400` on Opus 4.7+; returned `200` with a thinking block. Same caveat as above — our gateway never sends it. |

The last two rows are worth carrying into the handoff on their own: **this path is more permissive
than the first-party Claude API.** Two request shapes that Anthropic's documentation says are
rejected were silently accepted. Anything in the deployed system that relies on the endpoint
rejecting a malformed request is relying on something that did not happen here.

---

## 5. Structured outputs are not a guarantee on this path

This is the finding with the largest blast radius, and it was not visible from any documentation.

`output_config.format` is accepted with **HTTP 200** by every model group tested. It is **not
enforced** by several of them. When it is not enforced, the schema is neither applied nor
rejected — the model simply answers in prose, wrapping the JSON in a Markdown fence.

| Model group | `output_config.format` | Returned |
|---|---|---|
| `anthropic.claude-opus-4-8` | **enforced** | `{"acknowledged": true}` |
| `anthropic.claude-opus-4-6` | **enforced** | `{"acknowledged": true}` |
| `anthropic.claude-sonnet-5` | not enforced | ` ```json\n{"acknowledged": true}\n``` ` |
| `anthropic.claude-sonnet-4-6` | not enforced | ` ```json\n{\n  "acknowledged": true\n}\n``` ` |
| `bedrock/anthropic.claude-haiku-4-5-20251001` | not enforced | ` ```json\n{\n  "acknowledged": true\n}\n``` ` |

**The split does not follow documented model support.** Anthropic documents structured outputs as
supported on Claude Sonnet 5 and Haiku 4.5, both of which did not enforce here, and the two groups
that did enforce include Opus 4.6. So the determining factor is something about how each entry is
registered and routed on this particular proxy — **not** the model's advertised capability.
We could not establish the root cause from outside the proxy, and we are not guessing at it.
**Unverified: whether this is a LiteLLM routing property, a Bedrock endpoint property, or a
per-entry configuration choice on this specific proxy.**

Two observations support "routing, not model": an invalid `effort` value on the
`anthropic.claude-*` groups is rejected by *Bedrock* (`unknown variant ... expected one of low,
medium, high, xhigh, max`), while the same value on the `bedrock/`-prefixed group is rejected by
*LiteLLM* (`litellm.BadRequestError: Unmapped reasoning effort`). Those are two different code
paths inside the proxy for the same field.

**What this changes.** Every deterministic validator downstream assumes a finding arrives as
parseable JSON. On this path that assumption is false for three of five groups, and false
*silently*. ADR-018 makes the gateway verify it: when a response schema was requested and the text
does not parse, the gateway raises `StructuredOutputError` rather than returning prose.

Deliberately **not** done: stripping the fence. A lenient parser would hide from the program team
that schema enforcement is a per-model-group property rather than a platform guarantee, and it
would eventually accept something that is not a finding at all.

---

## 6. Endpoint routing

Also measured, and also not obvious from documentation.

| Route | Result |
|---|---|
| `{base}/v1/messages` | **works.** LiteLLM's native Anthropic-format endpoint; routes a Messages API request to any `model_list` entry, Bedrock included. |
| `{base}/anthropic/v1/messages` | **`401 invalid x-api-key`.** The passthrough to `api.anthropic.com`. It requires the proxy to hold a first-party Anthropic credential; a Bedrock-backed proxy has none, so it forwards the caller's virtual key upstream and Anthropic rejects it. |

The failure presents as an authentication error and is in fact a wrong-route error. ADR-015
originally had the gateway append `/anthropic` to the configured base URL, which made this
substantially harder to read — the operator could not see the URL that was actually being called.
ADR-017 removes the rewrite: `IREPORTS_LITELLM_BASE_URL` is now used verbatim.

---

## 7. What is still unknown

Listed so this document is not read as more than it is.

- **Everything about AWS GovCloud.** Model availability, model and inference-profile IDs,
  cross-region inference rules, data routing. This is Q-01 and it is untouched.
- **Whether `bedrock-mantle.{region}.api.aws` resolves in GovCloud.** The `bedrock` adapter has
  never been run at all, in any partition. Its endpoint pattern is unverified (ADR-015).
- **Whether LiteLLM is permitted in the approved environment.** Unknown. Half the reason two
  adapters exist.
- **The root cause of the structured-output split** (§5).
- **Cost and latency at realistic prompt sizes.** Every probe here was a handful of tokens.
- **Refusal behaviour on adjudicative content.** No refusal was observed, because nothing
  resembling a case file was sent. Refusal *handling* is covered offline; refusal *rates* on real
  criterion analysis are unmeasured.
- **Prompt caching.** Not enabled pending Q-13.

---

## 8. How to extend this file

Add a run-of-record block per partition and endpoint. Do not overwrite §1–§6 with a GovCloud run —
the value of this document is the comparison between partitions, and a commercial-partition
baseline that gets deleted takes the comparison with it.
