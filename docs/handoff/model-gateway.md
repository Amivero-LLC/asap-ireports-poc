# Model Gateway

**Date: 2026-08-10** · **ADR-015** (amends ADR-008) · `packages/gateway/`

The only component in this system permitted to call a model. Application code depends on the
`ModelGateway` port and nothing else — never an SDK client, never a model id, never a provider.

```python
from ireports_domain import ModelAlias
from ireports_gateway import Message, ModelRequest, build_gateway

gateway = build_gateway()                       # adapter chosen by configuration
response = gateway.complete(ModelRequest(
    alias=ModelAlias.THINKING,                  # a tier, never a model
    messages=(Message(role="user", content=prompt),),
    node_id="foreign_influence_specialist",
))
```

---

## 1. Two adapters, one port

| Adapter | Transport | Alias → model mapping lives | Use when |
|---|---|---|---|
| **`litellm`** (default) | Official Anthropic SDK → LiteLLM's Anthropic passthrough (`{base}/anthropic`) | **LiteLLM's config — outside our repo entirely** | Default. A partition or model-generation change never touches our code *or* our environment. |
| **`bedrock`** | `anthropic.AnthropicBedrockMantle`, standard AWS credential chain, no proxy | Our environment (`IREPORTS_BEDROCK_MODEL_*`) | A proxy is not permitted, or you need to isolate whether a problem is LiteLLM's. |
| **`stub`** | none — offline | n/a | Contract tests only. Never in a profile producing reviewer-visible findings. |

### Both production adapters use the official Anthropic SDK

This is the decision most likely to be reversed by someone who hasn't read this page, so it gets
the space.

LiteLLM's best-known surface is **OpenAI-compatible**, so "point an OpenAI client at the proxy"
looks like the natural integration. It silently costs the Anthropic request surface this
architecture is built on:

- **adaptive thinking** — the only supported thinking mode on current models
- **`output_config.effort`** — what replaced the removed thinking-token budget, and how we express
  the three tiers
- **the `refusal` stop reason** — see §3; this one is the difference between a caught error and a
  silent empty finding
- **structured outputs** — which replaced assistant-prefill, now a 400
- **thinking blocks**

LiteLLM also exposes an **Anthropic-native passthrough**, so we get the gateway *and* the real API
by pointing `anthropic.Anthropic` at `{base}/anthropic` via `base_url`. There is no trade to make.

The Bedrock adapter uses the SDK's Messages-API Bedrock client rather than a raw `bedrock-runtime`
`converse` call for the same reason: one request shape, one refusal path, one place where the
decision-support behaviour lives. Both adapters authenticate the same way they always would —
LiteLLM by virtual key, Bedrock by the standard AWS credential chain — so "boto3 access" is
preserved; what changes is the wire format, not the auth.

---

## 2. What the gateway guarantees

Each row is enforced in `_AnthropicAdapterBase` and asserted in
`tests/contract/test_model_gateway.py` (20 tests, all offline).

| Guarantee | Why | Test |
|---|---|---|
| **A model is named by alias, never by id** (ADR-008) | A partition change must be config, not code | `test_litellm_passes_the_alias_through_as_the_model` |
| **A refusal raises, never returns** | §3 — the highest-stakes error path in this system | `test_a_refusal_raises_rather_than_returning_empty` |
| **No sampling parameters, ever** | `temperature`/`top_p`/`top_k` are rejected with a 400 on current models | `test_no_sampling_parameters_are_ever_sent` |
| **Adaptive thinking, not a token budget** | `budget_tokens` was removed and 400s | `test_thinking_is_adaptive_not_a_token_budget` |
| **Effort comes from the tier** | The three ADR-008 roles map to reasoning depth | `test_effort_comes_from_the_tier` |
| **Structured outputs don't clobber effort** | Both live in `output_config`; a naive assignment loses one | `test_a_response_schema_does_not_clobber_effort` |
| **Usage returned for budget accounting** | `BudgetConsumption` on the run manifest must reflect reality (blueprint §8.5) | `test_usage_is_returned_for_budget_accounting` |
| **No default model id** | Q-01 is refused, not guessed — startup error names the variable | `test_bedrock_requires_a_model_id_per_tier_and_says_which` |
| **Bedrock ids carry `anthropic.`** | The bare first-party id fails on Bedrock (`CLAUDE.md`) | `test_bedrock_model_ids_must_carry_the_anthropic_prefix` |
| **No case text in error messages** | `CLAUDE.md`: raw case text never reaches logs or traces | by construction — errors carry status codes and node ids only |

---

## 3. The refusal path — the reason this package exists

Current Claude models can decline a request and return **HTTP 200** with
`stop_reason: "refusal"` and a possibly-empty content list.

Read naively, a specialist whose call was refused returns `""`. That empty string validates, yields
no finding, and reaches a reviewer as a clean result. **Silent under-analysis that looks like a
completed analysis is the worst outcome this system can produce** — worse than a crash, because a
crash is visible.

So the gateway checks `stop_reason` *before* touching content and raises `ModelRefusalError` with
the policy category. Two tests cover it: the pre-output case (empty content) and the mid-stream
case (partial content, which is arguably more dangerous — it looks like a real answer).

This matters more than usual here: benign security and life-sciences adjacent work can trip the
classifiers, and adjudicative case files routinely discuss criminal conduct, substance use, and
foreign contacts. **Refusals should be expected in normal operation**, not treated as exotic.

**Not yet built:** a refused specialist should surface to the reviewer as an information gap
("analysis under this criterion could not be completed"), not as an absent finding. The contracts
support it (`InformationGap`, `blocking=True`); wiring it is Milestone 2.

---

## 4. Configuration

Full surface in `.env.example`. The three that matter:

```bash
IREPORTS_MODEL_ADAPTER=litellm          # litellm | bedrock | stub
IREPORTS_LITELLM_BASE_URL=http://localhost:4000
IREPORTS_EFFORT_THINKING=high           # low | medium | high | xhigh | max
```

Effort defaults per tier: orchestrator `medium`, thinking `high`, fast `low`.

**`ireports-fast` is low effort with thinking still ON, not thinking disabled.** Disabling thinking
has two documented failure modes: a tool call can be written into visible text instead of emitted
as a structured tool-use block — the call silently never runs and the turn still succeeds — and
internal `<thinking>` tags can leak into the response. For a system whose deterministic validators
depend on structured output, a silently-skipped tool call is not survivable. Low effort captures
most of the cost and latency saving without either risk.

For LiteLLM, name the models after the aliases in `model_list` so no model id exists on our side:

```yaml
model_list:
  - model_name: ireports-thinking
    litellm_params: { model: bedrock/<CONFIRM VIA Q-01>, aws_region_name: <region> }
```

---

## 5. Known gaps and unverified claims

- **Neither adapter has been run against a real endpoint.** Every test is offline. The gateway is
  verified as *correctly constructed*, not as *working against Bedrock* — that is Q-01 and cannot
  be answered without account access. Do not read the green test suite as connectivity.
- **The Mantle endpoint's GovCloud availability is unverified.** It is
  `bedrock-mantle.{region}.api.aws`; GovCloud endpoints do not generally follow the commercial
  pattern. `IREPORTS_BEDROCK_BASE_URL` is the escape hatch; if the endpoint is absent, the fallback
  is a `bedrock-runtime` adapter — real work to scope, not a flag. Folded into Q-01.
- **Whether LiteLLM is permitted in the approved environment is unknown.** Also folded into Q-01.
  This is half the reason two adapters exist.
- **Prompt caching is not enabled.** Q-13 asks whether caching is approved for this data class;
  enabling it before that answer would be exactly the kind of silent assumption this project
  avoids. Material to cost, immaterial to correctness.
- **No retry or fallback policy yet.** Server-side `fallbacks` is unavailable on Bedrock, so a
  refusal-fallback would need the SDK's client-side middleware. Deferred until the orchestrator
  exists to own retry semantics — that is where bounded retry belongs (blueprint §8.5), not here.
- **No streaming.** Single-case interactive runs (ADR-013) want streaming run status eventually;
  the port is synchronous today. Adding it is an additive change to the port.
- **The orchestration spike does not use this port.** `spikes/harness/gateway.py` is a separate,
  Postgres-backed observability instrument built before this package, and its job is measuring
  re-execution across a crash rather than calling a model. Migrating the spike onto this port is
  Milestone 2 work, recorded rather than silently left.

---

## 6. Verification, as run

macOS arm64, Python 3.13.x, `anthropic` 0.121.0, 2026-08-10.

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | clean |
| `mypy --strict` | no issues, 26 source files |
| `pytest tests` | 76 passed (20 new gateway tests) |
