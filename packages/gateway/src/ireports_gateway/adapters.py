"""The two production adapters, plus a stub.

**Both production adapters use the official `anthropic` SDK.** That is the one design decision
worth stating up front, because the obvious alternative is wrong in a way that is easy to miss:
LiteLLM's best-known surface is OpenAI-compatible, so "point an OpenAI client at the proxy" looks
like the natural LiteLLM integration. It costs the Anthropic request surface — adaptive thinking,
`output_config.effort`, the `refusal` stop reason, structured outputs, thinking blocks — all of
which this architecture depends on. LiteLLM also exposes an **Anthropic-native passthrough**, so
we get the gateway *and* the real API by pointing `anthropic.Anthropic` at it via `base_url`.

The two adapters differ in exactly one thing: how a `ModelAlias` becomes something concrete.

- `litellm` — `anthropic.Anthropic(base_url=…)`. The alias **is** the model name; LiteLLM's
  own config maps it to something concrete.
- `bedrock` — `anthropic.AnthropicBedrockMantle(aws_region=…)`. Our config maps the alias to an
  `anthropic.`-prefixed Bedrock model id.

That difference is the point of ADR-015: with LiteLLM, the alias→model table lives in the
gateway's config and application code never learns a model id. With Bedrock, the table moves into
*our* environment. Both honour ADR-008; only one of them keeps the mapping outside our process.
"""

from __future__ import annotations

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


def _text_from(content: Any) -> str:
    return "".join(
        block.text for block in (content or []) if getattr(block, "type", None) == "text"
    )


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
            # Structured outputs replace the assistant-prefill trick, which now returns a 400
            # on current models. `output_config` already exists, so merge rather than overwrite.
            kwargs["output_config"]["format"] = {
                "type": "json_schema",
                "schema": request.response_schema,
            }
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

        return ModelResponse(
            text=text,
            alias=request.alias,
            resolved_model=getattr(message, "model", "") or self._resolve_model(request.alias),
            usage=_usage_from(getattr(message, "usage", None)),
            stop_reason=stop_reason,
        )


class LiteLLMGateway(_AnthropicAdapterBase):
    """Calls Claude through a LiteLLM proxy, in Anthropic's own request format.

    Points the official SDK at LiteLLM's **Anthropic passthrough** (`{base}/anthropic`), so the
    proxy forwards a native Messages API request rather than translating an OpenAI-shaped one.
    Everything the architecture needs — adaptive thinking, effort, structured outputs, the
    `refusal` stop reason — survives the hop.

    This is the ADR-008 default: application code names `ireports-thinking`, LiteLLM's config
    decides what that is, and a partition or model-generation change never reaches our code or
    even our environment.
    """

    name = "litellm"

    def __init__(self, config: GatewayConfig) -> None:
        if not config.litellm_base_url:
            raise GatewayConfigurationError("LiteLLMGateway requires litellm_base_url")
        base = config.litellm_base_url.rstrip("/")
        client = anthropic.Anthropic(
            base_url=f"{base}/anthropic",
            # LiteLLM authenticates with a virtual key. A placeholder keeps the SDK from
            # searching the ambient environment for a real Anthropic key, which must never be
            # what authenticates a request in this architecture.
            api_key=config.litellm_api_key or "litellm-virtual-key-not-set",
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        super().__init__(client, config)

    def _resolve_model(self, alias: ModelAlias) -> str:
        # The alias goes over the wire unchanged: LiteLLM's `model_list` maps
        # `ireports-thinking` to a concrete Bedrock model. No model id exists on our side.
        return alias.value


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


class StubGateway:
    """Deterministic, offline, no credentials. For contract tests only.

    ADR-009 declines an offline *run profile* for the system; it also says unit and contract
    tests mock at the gateway boundary. This is that boundary. It is not a fixture corpus and
    must never be selectable in a profile that produces findings a reviewer might see.
    """

    name = "stub"

    def __init__(self, responses: dict[str, str] | None = None, default: str = "") -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        key = request.node_id or request.alias.value
        return ModelResponse(
            text=self._responses.get(key, self._default),
            alias=request.alias,
            resolved_model=f"stub:{request.alias.value}",
            usage=ModelUsage(input_tokens=0, output_tokens=0),
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
