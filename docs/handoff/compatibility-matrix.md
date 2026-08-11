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

## 2. Tier mapping

**A development mapping against a commercial-partition proxy, not an answer to Q-01.** The models
a GovCloud deployment may use are unknown; what follows is the reasoning, so that whoever answers
Q-01 can re-apply it to whatever is actually available there.

**No Opus tier.** Once §5 established that structured output does not depend on an Opus-class
model, nothing else required one either.

| Alias | Official model | First-party ID | Bedrock ID | Group on this proxy | Effort | List price (in/out per MTok) |
|---|---|---|---|---|---|---|
| `ireports-orchestrator` | **Claude Sonnet 4.6** | `claude-sonnet-4-6` | `anthropic.claude-sonnet-4-6` | `anthropic.claude-sonnet-4-6` | `medium` | $3 / $15 |
| `ireports-thinking` | **Claude Sonnet 5** | `claude-sonnet-5` | `anthropic.claude-sonnet-5` | `anthropic.claude-sonnet-5` | `high` | $3 / $15 (intro $2 / $10 to 2026-08-31) |
| `ireports-fast` | **Claude Haiku 4.5** | `claude-haiku-4-5` (dated: `claude-haiku-4-5-20251001`) | `anthropic.claude-haiku-4-5` | `bedrock/anthropic.claude-haiku-4-5-20251001` | `low` | $1 / $5 |

**Why each one.**

- **`ireports-fast` → Haiku 4.5.** Classification, extraction, and mechanical tasks (ADR-008), at a
  fifth the input cost of the Sonnet tiers. It produces validated structured input through the
  §5.2 mechanism, which was the only thing that had been in doubt. Low effort with thinking still
  on, per ADR-015.
- **`ireports-thinking` → Sonnet 5.** This is the tier that produces findings a reviewer reads, so
  it gets the strongest non-Opus model available. Note the cost reasoning: **Sonnet 5 and Sonnet
  4.6 carry the same list price**, and Sonnet 5 is currently cheaper under introductory pricing. So
  there is no cost argument for putting the quality-critical tier on the older model — preferring
  Sonnet 4.6 here would trade capability for nothing.
- **`ireports-orchestrator` → Sonnet 4.6.** The lightest of the three jobs: `CLAUDE.md` is explicit
  that the model does not decide control flow, so this tier does sequencing and planning support,
  not adjudication. Keeping it on a different model generation from the thinking tier also means a
  route-level or generation-level regression shows up on one tier rather than silently on both.

**Escalation, if evaluation demands it.** `anthropic.claude-opus-4-8` is available on this proxy
and is the obvious escalation for the thinking tier. That should be a decision made on measured
finding quality in Milestone 3, not a default taken now — which is exactly what this mapping
avoids.

---

## 3. Results

| Alias | Outcome | Resolved model | `stop_reason` | in/out tokens | Structured output |
|---|---|---|---|---|---|
| `ireports-orchestrator` | answered | `anthropic.claude-sonnet-4-6` | `end_turn` | 15 / 5 | enforced |
| `ireports-thinking` | answered | `anthropic.claude-sonnet-5` | `end_turn` | 19 / 5 | enforced |
| `ireports-fast` | answered | `bedrock/anthropic.claude-haiku-4-5-20251001` | `end_turn` | 44 / 44 | enforced |

All three tiers, no Opus. "Enforced" here means the §5.2 mechanism returned validated structured
input; the gateway raises rather than returning prose if it does not.

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

## 5. Structured output: `output_config.format` is unusable; a single tool works everywhere

This is the finding with the largest blast radius, and it took three rounds of probing to get
right. **An earlier revision of this page concluded that enforcement was a per-model-group
property, with the Opus groups enforcing and Sonnet/Haiku not. That was wrong** — a sample-size-1
artifact. Recorded rather than deleted, because the corrected result is the opposite of the
intuitive one and the wrong version is the version a reader would otherwise reach on their own.

### 5.1 `output_config.format` is unreliable on every group, including Opus

Eight trials per group, identical request each time:

| Model group | bare JSON | fenced prose |
|---|---|---|
| `anthropic.claude-opus-4-8` | 6 | **2** |
| `anthropic.claude-sonnet-5` | 0 | **8** |
| `anthropic.claude-sonnet-4-6` | 0 | **8** |
| `bedrock/anthropic.claude-haiku-4-5-20251001` | 0 | **8** |

It is accepted with HTTP 200 everywhere and enforced nowhere reliably. **The schema does reach the
model** — adding it raises `input_tokens` from 12→44 (Sonnet 4.6, Haiku) and 16→69 (Opus 4.8, Sonnet
5) — so this is not the proxy silently dropping the field. The model receives the schema and does
not treat it as binding.

The two input-token clusters (12/44 and 16/69) line up exactly with the two error-message sources
seen in §4, confirming the proxy runs two distinct routes; but **both routes fail this mechanism**,
so the route is not the explanation for the failure.

### 5.2 A single tool call works on every group, every time

| Mechanism | Opus 4.8 | Sonnet 5 | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|---|---|
| `output_config.format` | 6/8 | 0/8 | 0/8 | 0/8 |
| One tool, `tool_choice` omitted, adaptive thinking | **5/5** | **5/5** | **5/5** | **5/5** |
| One tool, `tool_choice` forced, adaptive thinking | 5/5 | 5/5 | **400** | **400** |
| Tool with `strict: true` | **400** | **400** | ok | ok |

Every cell returned the exact expected input (`{"acknowledged": true}`) or an error; there were no
partial or malformed results.

Two constraints fall out, and they pull in opposite directions — which is why the working
configuration is the *least* specified one:

- **`strict: true` is rejected by Bedrock** on the native routes:
  `tools.0.custom.strict: Extra inputs are not permitted`. So the documented hard guarantee of
  schema-valid tool input is not available here.
- **Forcing `tool_choice` 400s with adaptive thinking** on exactly the two models this project most
  wants to use: `Thinking may not be enabled when tool_choice forces a specific tool`. Since
  ADR-015 keeps thinking on for every tier including `fast`, forcing the tool is not available
  either.

Omitting both leaves one tool and an instruction to call it, which every group did in every trial.

### 5.3 What this changes

ADR-019 moves the gateway onto the tool mechanism and deletes `output_config.format`. The
`StructuredOutputError` guard from ADR-018 stays and gains a sharper job: with `tool_choice` left
to the model, a turn *could* answer in prose instead of calling the tool. It did not in 20 of 20
trials — but "did not occur" is not "cannot occur", and prose reaching a validator as though it
were a finding is the failure this system cannot have.

**The practical consequence is the good one:** structured output does not require an Opus tier.
Sonnet 4.6 and Haiku 4.5 both produce validated structured input through this mechanism, so the
tier mapping in §2 is free to prefer them on cost and latency grounds.

Deliberately **not** done: stripping the Markdown fence off a prose answer. It is two lines and it
would make the system appear to work, while installing a lenient parser that eventually accepts
something that is not a finding at all.

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
