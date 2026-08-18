"""The two production adapters, plus a stub.

**Both production adapters use the official `anthropic` SDK.** That is the one design decision
worth stating up front, because the obvious alternative is wrong in a way that is easy to miss:
LiteLLM's best-known surface is OpenAI-compatible, so "point an OpenAI client at the proxy" looks
like the natural LiteLLM integration. It costs the Anthropic request surface — adaptive thinking,
`output_config.effort`, the `refusal` stop reason, structured outputs, thinking blocks — all of
which this architecture depends on. LiteLLM also serves a **native Anthropic-format endpoint** at
`{base}/v1/messages`, so we get the gateway *and* the real API by pointing `anthropic.Anthropic`
at it via `base_url`. Verified against a live Bedrock-backed proxy: an invalid `effort` value is
rejected by Bedrock itself with the real enum, and `effort` demonstrably changes whether a
thinking block comes back — the parameters are forwarded and honoured, not quietly dropped
(`docs/handoff/compatibility-matrix.md`).

The two adapters differ in exactly one thing: how a `ModelAlias` becomes something concrete.

- `litellm` — `anthropic.Anthropic(base_url=…)`. The alias **is** the model name by default;
  LiteLLM's own config maps it to something concrete. On a shared proxy that cannot carry our
  three names, `IREPORTS_LITELLM_MODEL_*` supplies the model group instead (ADR-017).
- `bedrock` — `anthropic.AnthropicBedrockMantle(aws_region=…)`. Our config maps the alias to an
  `anthropic.`-prefixed Bedrock model id.

That difference is the point of ADR-015: with LiteLLM, the alias→model table lives in the
gateway's config and application code never learns a model id. With Bedrock, the table moves into
*our* environment. Both honour ADR-008; only one of them keeps the mapping outside our process.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
from ireports_domain import ModelAlias

from .config import AdapterKind, GatewayConfig
from .port import (
    GatewayConfigurationError,
    GatewayError,
    Message,
    ModelRefusalError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
    ModelUsage,
    StructuredOutputError,
)


def _messages_payload(messages: tuple[Message, ...]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _usage_from(raw: Any) -> ModelUsage:
    if raw is None:
        return ModelUsage()
    return ModelUsage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
    )


STRUCTURED_OUTPUT_TOOL = "emit_structured_output"
"""The single tool a structured request offers. One tool, so there is nothing to choose between."""


def _text_from(content: Any) -> str:
    return "".join(
        block.text for block in (content or []) if getattr(block, "type", None) == "text"
    )


def _structured_input_from(content: Any) -> dict[str, Any] | None:
    """The validated input of the structured-output tool call, or None if it was never called."""
    for block in content or []:
        if getattr(block, "type", None) == "tool_use" and block.name == STRUCTURED_OUTPUT_TOOL:
            return dict(block.input)
    return None


class _AnthropicAdapterBase:
    """Shared request construction and response handling.

    Everything that makes a request *correct for this project* lives here so the two adapters
    cannot drift: no sampling parameters, adaptive thinking, effort per tier, and a refusal
    check before any content is read.
    """

    name = "anthropic-base"

    def __init__(self, client: Any, config: GatewayConfig) -> None:
        self._client = client
        self._config = config

    def _resolve_model(self, alias: ModelAlias) -> str:
        raise NotImplementedError

    def _build_kwargs(self, request: ModelRequest) -> dict[str, Any]:
        effort = request.effort or self._config.effort_for(request.alias)
        kwargs: dict[str, Any] = {
            "model": self._resolve_model(request.alias),
            "max_tokens": request.max_tokens or self._config.max_tokens,
            "messages": _messages_payload(request.messages),
            # Adaptive thinking, always. `budget_tokens` was removed on current models and
            # returns a 400; depth is controlled by effort instead.
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort.value},
        }
        if request.system is not None:
            kwargs["system"] = request.system
        if request.response_schema is not None:
            # Structured output as a **single-tool call**, not `output_config.format` (ADR-019).
            # Measured against a live Bedrock-backed proxy: `output_config.format` is unreliable
            # on every model group tested — best case 6 of 8 on Opus 4.8, 0 of 8 on Sonnet and
            # Haiku — while a lone tool returns validated input 20 of 20 across all four.
            #
            # Three things are deliberately absent, each because sending it breaks a tier:
            #   * `strict: true`  — Bedrock rejects it outright ("Extra inputs are not permitted")
            #   * `tool_choice`   — forcing the tool 400s with adaptive thinking on Sonnet 4.6 and
            #                       Haiku 4.5 ("Thinking may not be enabled..."). Leaving it to the
            #                       model costs nothing: with one tool and an instruction to use
            #                       it, every group called it every time, and a turn that answers
            #                       in prose anyway is caught in `_to_response`.
            #   * `output_config.format` — removed, not merged. Sending both is two mechanisms
            #                       competing to shape one response.
            kwargs["tools"] = [
                {
                    "name": STRUCTURED_OUTPUT_TOOL,
                    "description": (
                        "Return your result as structured data matching the schema. "
                        "Call this tool exactly once. Do not answer in prose."
                    ),
                    "input_schema": request.response_schema,
                }
            ]
        # Deliberately absent: temperature, top_p, top_k. Current Claude models reject them
        # with a 400, and this system steers behaviour through prompts and validators anyway.
        return kwargs

    def complete(self, request: ModelRequest) -> ModelResponse:
        kwargs = self._build_kwargs(request)
        try:
            message = self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError as exc:
            raise ModelTimeoutError(f"model call timed out in node {request.node_id!r}") from exc
        except anthropic.RateLimitError as exc:
            raise ModelUnavailableError("model gateway rate limited") from exc
        except anthropic.APIConnectionError as exc:
            raise ModelUnavailableError("model gateway unreachable") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ModelUnavailableError(f"model gateway returned {exc.status_code}") from exc
            # 4xx is ours to fix — surface the status, never the payload.
            raise GatewayError(
                f"model gateway rejected the request with {exc.status_code} "
                f"(type={getattr(exc, 'type', None)})"
            ) from exc

        return self._to_response(request, message)

    def _to_response(self, request: ModelRequest, message: Any) -> ModelResponse:
        stop_reason = getattr(message, "stop_reason", None)

        # Check the refusal *before* touching content. A declined request returns HTTP 200 with
        # an empty or partial content list; reading content[0] unconditionally would turn a
        # refusal into an empty finding, which is the worst possible outcome for this system —
        # silent under-analysis that looks like a clean result.
        if stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise ModelRefusalError(
                category=getattr(details, "category", None),
                explanation=getattr(details, "explanation", None),
            )

        text = _text_from(getattr(message, "content", None))
        if stop_reason == "max_tokens" and not text:
            raise GatewayError(
                f"model produced no text before hitting max_tokens in node {request.node_id!r}; "
                "raise max_tokens or lower effort"
            )

        # A requested schema is checked, never trusted. `tool_choice` is left to the model
        # (see `_build_kwargs`), so a turn that answers in prose instead of calling the tool is
        # possible in principle — it did not occur in 20 of 20 trials, but "did not occur" is not
        # "cannot occur", and prose reaching a validator as though it were a finding is the whole
        # failure class ADR-018 exists to close.
        if request.response_schema is not None:
            emitted = _structured_input_from(getattr(message, "content", None))
            if emitted is None:
                raise StructuredOutputError(
                    f"node {request.node_id!r} requested structured output and the model "
                    f"answered without calling {STRUCTURED_OUTPUT_TOOL!r} "
                    f"(stop_reason={stop_reason!r}, text_length={len(text)}). "
                    "See docs/handoff/compatibility-matrix.md."
                )
            text = json.dumps(emitted)

        return ModelResponse(
            text=text,
            alias=request.alias,
            resolved_model=getattr(message, "model", "") or self._resolve_model(request.alias),
            usage=_usage_from(getattr(message, "usage", None)),
            stop_reason=stop_reason,
        )


class LiteLLMGateway(_AnthropicAdapterBase):
    """Calls Claude through a LiteLLM proxy, in Anthropic's own request format.

    **`base_url` is used exactly as configured.** An earlier version appended `/anthropic` on the
    operator's behalf, reaching for LiteLLM's *passthrough* route. That was wrong often enough to
    be worth spelling out, because the two LiteLLM routes look interchangeable and are not:

    - `{base}/v1/messages` — LiteLLM's **native Anthropic-format endpoint**. It accepts a Messages
      API request and routes it to any entry in `model_list`, including Bedrock ones. This is the
      route a Bedrock-backed proxy needs, and therefore the route this architecture needs.
    - `{base}/anthropic/v1/messages` — the **passthrough** to `api.anthropic.com`. It requires the
      proxy to hold a first-party Anthropic credential. A proxy that fronts Bedrock has no such
      credential, so it forwards the caller's virtual key upstream and Anthropic returns
      `401 invalid x-api-key` — an error that reads like a bad key rather than a wrong route.

    Measured against a live Bedrock-backed proxy on 2026-08-10; see
    `docs/handoff/compatibility-matrix.md`. Silently rewriting a URL the operator supplied made
    that failure much harder to read than it needed to be, so the gateway no longer does it. Set
    `IREPORTS_LITELLM_BASE_URL` to `…/anthropic` yourself if passthrough is genuinely what you
    want.

    Either way the Anthropic request surface is what travels: adaptive thinking, `effort`,
    structured outputs, and the `refusal` stop reason all survive the native route (verified, same
    source). That is the whole reason this adapter drives the official Anthropic SDK rather than
    LiteLLM's better-known OpenAI-compatible surface.
    """

    name = "litellm"

    def __init__(self, config: GatewayConfig) -> None:
        if not config.litellm_base_url:
            raise GatewayConfigurationError("LiteLLMGateway requires litellm_base_url")
        client = anthropic.Anthropic(
            base_url=config.litellm_base_url.rstrip("/"),
            # LiteLLM authenticates with a virtual key. A placeholder keeps the SDK from
            # searching the ambient environment for a real Anthropic key, which must never be
            # what authenticates a request in this architecture.
            api_key=config.litellm_api_key or "litellm-virtual-key-not-set",
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        super().__init__(client, config)

    def _resolve_model(self, alias: ModelAlias) -> str:
        # By default the alias goes over the wire unchanged and LiteLLM's `model_list` maps
        # `ireports-thinking` to something concrete — no model id exists on our side at all.
        # On a shared proxy that does not carry our three names, an override supplies the model
        # group instead (ADR-017). Application code names a tier in both cases.
        return self._config.litellm_model_for(alias)


class BedrockGateway(_AnthropicAdapterBase):
    """Calls Bedrock directly, using the Anthropic SDK's Bedrock client.

    Uses `AnthropicBedrockMantle` — the Messages-API Bedrock endpoint — rather than a raw
    `bedrock-runtime` `invoke_model` / `converse` call through boto3. Both authenticate with the
    same AWS credential chain, so this is still "direct AWS access with no proxy"; the difference
    is that the Mantle client speaks the Messages API, which keeps this adapter's request and
    response handling identical to the LiteLLM one. A raw `converse` adapter would need its own
    translation layer for thinking, effort, and refusals — a second place for the decision-support
    behaviour to drift.

    **Unverified, and it matters (Q-01, Q-14).** The Mantle endpoint is
    `bedrock-mantle.{region}.api.aws`. Whether that resolves in AWS GovCloud is *not* confirmed,
    and GovCloud endpoints do not generally follow the commercial pattern. `bedrock_base_url`
    exists as the escape hatch; if the endpoint turns out to be absent in the target partition,
    the fallback is a `bedrock-runtime` adapter, which is real work and should be scoped, not
    assumed. Do not treat this adapter as GovCloud-ready until someone has run it there.
    """

    name = "bedrock"

    def __init__(self, config: GatewayConfig) -> None:
        if not config.aws_region:
            raise GatewayConfigurationError("BedrockGateway requires aws_region")
        kwargs: dict[str, Any] = {
            "aws_region": config.aws_region,
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if config.aws_profile:
            kwargs["aws_profile"] = config.aws_profile
        if config.bedrock_base_url:
            kwargs["base_url"] = config.bedrock_base_url
        super().__init__(anthropic.AnthropicBedrockMantle(**kwargs), config)

    def _resolve_model(self, alias: ModelAlias) -> str:
        return self._config.bedrock_model_for(alias)


CHARS_PER_TOKEN = 4
"""The crude estimate this stub reports usage with. Not accurate, and it does not need to be."""


def _estimated_usage(request: ModelRequest, text: str) -> ModelUsage:
    """Non-zero, deterministic, roughly proportional to the work.

    **This used to report zero, and zero is not a neutral choice.** Anything that makes a decision
    on token spend — budgets, ceilings, accounting — is untestable against a double that always
    reports nothing spent, and untestable *silently*: the test passes, having exercised the branch
    where no budget is ever reached. A stub that reports zero for a quantity the system reasons
    about cannot stand in for a model that never does.

    A character estimate rather than a tokenizer: this is a test double, the number needs to be
    deterministic and to scale with the prompt, and importing a tokenizer to be wrong more
    precisely would be worse.
    """
    prompt_chars = len(request.system or "") + sum(len(m.content) for m in request.messages)
    return ModelUsage(
        input_tokens=prompt_chars // CHARS_PER_TOKEN,
        output_tokens=len(text) // CHARS_PER_TOKEN,
    )


class StubGateway:
    """Deterministic, offline, no credentials. For contract tests only.

    ADR-009 declines an offline *run profile* for the system; it also says unit and contract
    tests mock at the gateway boundary. This is that boundary. It is not a fixture corpus and
    must never be selectable in a profile that produces findings a reviewer might see.

    Reports **estimated** usage rather than zero — see `_estimated_usage`.
    """

    name = "stub"

    def __init__(self, responses: dict[str, str] | None = None, default: str = "") -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        key = request.node_id or request.alias.value
        text = self._responses.get(key, self._default)
        return ModelResponse(
            text=text,
            alias=request.alias,
            resolved_model=f"stub:{request.alias.value}",
            usage=_estimated_usage(request, text),
            stop_reason="end_turn",
        )


def build_gateway(config: GatewayConfig | None = None) -> Any:
    """Construct the configured adapter. The only function application code should call."""
    resolved = config or GatewayConfig.from_env()
    match resolved.adapter:
        case AdapterKind.LITELLM:
            return LiteLLMGateway(resolved)
        case AdapterKind.BEDROCK:
            return BedrockGateway(resolved)
        case AdapterKind.STUB:
            return StubGateway()
    raise GatewayConfigurationError(f"unhandled adapter {resolved.adapter!r}")
