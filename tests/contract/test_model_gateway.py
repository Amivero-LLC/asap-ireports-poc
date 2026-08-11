"""The gateway's guarantees, asserted without credentials or a network.

Every test here runs offline. That is the point of ADR-009's "mock at the gateway boundary":
the rules this package enforces — alias-only model references, no sampling parameters, adaptive
thinking, refusal handling — are properties of the request we build and the response we
interpret, and none of them needs a real model to check.

What these tests deliberately do *not* cover is whether Bedrock accepts the request in the target
partition. That is Q-01, it cannot be answered offline, and pretending otherwise would be the
exact assumption `docs/OPEN-QUESTIONS.md` refuses to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from ireports_domain import ModelAlias
from ireports_gateway import (
    AdapterKind,
    Effort,
    GatewayConfig,
    GatewayConfigurationError,
    GatewayError,
    LiteLLMGateway,
    Message,
    ModelRefusalError,
    ModelRequest,
    ModelTimeoutError,
    StubGateway,
    build_gateway,
)
from ireports_gateway.adapters import _AnthropicAdapterBase

REQUEST = ModelRequest(
    alias=ModelAlias.THINKING,
    messages=(Message(role="user", content="Analyse the cited evidence."),),
    system="You identify evidence-backed issues for review by an authorized officer.",
    node_id="foreign_influence_specialist",
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _StopDetails:
    category: str | None = None
    explanation: str | None = None


@dataclass
class _Usage:
    input_tokens: int = 120
    output_tokens: int = 40
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _Message:
    content: list[_Block]
    stop_reason: str = "end_turn"
    model: str = "anthropic.claude-test"
    usage: _Usage | None = None
    stop_details: _StopDetails | None = None


class _FakeMessages:
    def __init__(self, result: Any) -> None:
        self._result = result
        self.captured: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.captured = kwargs
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeClient:
    def __init__(self, result: Any) -> None:
        self.messages = _FakeMessages(result)


class _Adapter(_AnthropicAdapterBase):
    """Exercises the shared request/response logic without constructing a real client."""

    name = "test"

    def _resolve_model(self, alias: ModelAlias) -> str:
        return f"anthropic.test-{alias.value}"


def _adapter(result: Any, config: GatewayConfig | None = None) -> _Adapter:
    return _Adapter(_FakeClient(result), config or GatewayConfig(adapter=AdapterKind.STUB))


# ---------------------------------------------------------------------------
# The request we build
# ---------------------------------------------------------------------------


def test_no_sampling_parameters_are_ever_sent() -> None:
    """Current Claude models reject temperature/top_p/top_k with a 400.

    Asserted rather than assumed: a well-meaning change adding `temperature=0` "for
    determinism" would break every call, and determinism was never what it bought.
    """
    adapter = _adapter(_Message(content=[_Block("ok")], usage=_Usage()))
    adapter.complete(REQUEST)
    sent = adapter._client.messages.captured  # type: ignore[attr-defined]
    assert "temperature" not in sent
    assert "top_p" not in sent
    assert "top_k" not in sent


def test_thinking_is_adaptive_not_a_token_budget() -> None:
    adapter = _adapter(_Message(content=[_Block("ok")], usage=_Usage()))
    adapter.complete(REQUEST)
    sent = adapter._client.messages.captured  # type: ignore[attr-defined]
    assert sent["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in sent["thinking"]


def test_effort_comes_from_the_tier() -> None:
    adapter = _adapter(_Message(content=[_Block("ok")], usage=_Usage()))
    adapter.complete(REQUEST)
    assert adapter._client.messages.captured["output_config"]["effort"] == "high"  # type: ignore[attr-defined]

    adapter2 = _adapter(_Message(content=[_Block("ok")], usage=_Usage()))
    adapter2.complete(
        ModelRequest(alias=ModelAlias.FAST, messages=(Message(role="user", content="Classify."),))
    )
    assert adapter2._client.messages.captured["output_config"]["effort"] == "low"  # type: ignore[attr-defined]


def test_a_response_schema_does_not_clobber_effort() -> None:
    """Structured outputs and effort share `output_config` — a naive assignment loses one."""
    adapter = _adapter(_Message(content=[_Block("{}")], usage=_Usage()))
    schema = {"type": "object", "properties": {"finding": {"type": "string"}}}
    adapter.complete(
        ModelRequest(
            alias=ModelAlias.THINKING,
            messages=(Message(role="user", content="Extract."),),
            response_schema=schema,
        )
    )
    output_config = adapter._client.messages.captured["output_config"]  # type: ignore[attr-defined]
    assert output_config["effort"] == "high"
    assert output_config["format"] == {"type": "json_schema", "schema": schema}


def test_a_request_must_start_with_a_user_message() -> None:
    with pytest.raises(ValueError, match="first message must be from the user"):
        ModelRequest(
            alias=ModelAlias.FAST, messages=(Message(role="assistant", content="prefill"),)
        )


# ---------------------------------------------------------------------------
# The response we interpret — the load-bearing one
# ---------------------------------------------------------------------------


def test_a_refusal_raises_rather_than_returning_empty() -> None:
    """The failure mode this package exists to prevent.

    A declined request is HTTP 200 with an empty content list. Read naively, a specialist that
    was refused returns "" — which validates, produces no finding, and reaches a reviewer as a
    clean result. Silent under-analysis is the worst outcome this system can have, so the
    refusal must be an exception, not a value.
    """
    refusal = _Message(
        content=[], stop_reason="refusal", stop_details=_StopDetails(category="cyber")
    )
    with pytest.raises(ModelRefusalError) as exc:
        _adapter(refusal).complete(REQUEST)
    assert exc.value.category == "cyber"


def test_a_refusal_is_caught_even_with_partial_content() -> None:
    """A mid-stream refusal carries partial text. Returning it would deliver a truncated
    analysis as though it were complete."""
    refusal = _Message(
        content=[_Block("The record indicates")],
        stop_reason="refusal",
        stop_details=_StopDetails(category=None),
    )
    with pytest.raises(ModelRefusalError):
        _adapter(refusal).complete(REQUEST)


def test_max_tokens_with_no_text_is_an_error_not_an_empty_answer() -> None:
    truncated = _Message(content=[], stop_reason="max_tokens", usage=_Usage())
    with pytest.raises(GatewayError, match="max_tokens"):
        _adapter(truncated).complete(REQUEST)


def test_usage_is_returned_for_budget_accounting() -> None:
    response = _adapter(_Message(content=[_Block("ok")], usage=_Usage())).complete(REQUEST)
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 40
    assert response.usage.total_tokens == 160


def test_the_alias_survives_and_the_resolved_model_is_recorded() -> None:
    """Both halves of ADR-008: the contract keeps the alias, the manifest keeps the reality."""
    response = _adapter(_Message(content=[_Block("ok")], usage=_Usage())).complete(REQUEST)
    assert response.alias is ModelAlias.THINKING
    assert response.resolved_model == "anthropic.claude-test"


def test_transport_failures_map_to_typed_retriable_errors() -> None:
    import anthropic
    import httpx

    timeout = anthropic.APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
    with pytest.raises(ModelTimeoutError):
        _adapter(timeout).complete(REQUEST)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_bedrock_requires_a_model_id_per_tier_and_says_which() -> None:
    """No default model id exists — Q-01 is refused, not guessed."""
    with pytest.raises(GatewayConfigurationError) as exc:
        GatewayConfig(adapter=AdapterKind.BEDROCK, aws_region="us-gov-west-1").validate()
    message = str(exc.value)
    assert "IREPORTS_BEDROCK_MODEL_THINKING" in message
    assert "Q-01" in message


def test_bedrock_model_ids_must_carry_the_anthropic_prefix() -> None:
    """`CLAUDE.md`: the bare first-party id fails on Bedrock."""
    with pytest.raises(GatewayConfigurationError, match=r"anthropic\."):
        GatewayConfig(
            adapter=AdapterKind.BEDROCK,
            aws_region="us-gov-west-1",
            bedrock_models=dict.fromkeys(ModelAlias, "claude-opus-5"),
        ).validate()


def test_litellm_requires_a_base_url() -> None:
    with pytest.raises(GatewayConfigurationError, match="LITELLM_BASE_URL"):
        GatewayConfig(adapter=AdapterKind.LITELLM).validate()


def test_litellm_passes_the_alias_through_as_the_model() -> None:
    """With LiteLLM, no model id exists on our side at all — the proxy owns the mapping."""
    gateway = LiteLLMGateway(
        GatewayConfig(adapter=AdapterKind.LITELLM, litellm_base_url="http://localhost:4000")
    )
    assert gateway._resolve_model(ModelAlias.THINKING) == "ireports-thinking"


def test_litellm_targets_the_anthropic_passthrough_not_an_openai_shim() -> None:
    """The design decision, asserted.

    Pointing an OpenAI-compatible client at LiteLLM would silently cost adaptive thinking,
    effort, structured outputs, and the refusal stop reason — the whole basis of this package.
    """
    gateway = LiteLLMGateway(
        GatewayConfig(adapter=AdapterKind.LITELLM, litellm_base_url="http://localhost:4000/")
    )
    assert str(gateway._client.base_url).rstrip("/").endswith("/anthropic")


def test_effort_defaults_are_per_tier_and_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IREPORTS_MODEL_ADAPTER", "stub")
    monkeypatch.setenv("IREPORTS_EFFORT_FAST", "medium")
    config = GatewayConfig.from_env()
    assert config.effort_for(ModelAlias.FAST) is Effort.MEDIUM
    assert config.effort_for(ModelAlias.THINKING) is Effort.HIGH


def test_an_unknown_adapter_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IREPORTS_MODEL_ADAPTER", "openai")
    with pytest.raises(GatewayConfigurationError, match="MODEL_ADAPTER"):
        GatewayConfig.from_env()


def test_build_gateway_returns_the_configured_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IREPORTS_MODEL_ADAPTER", "stub")
    assert isinstance(build_gateway(), StubGateway)


def test_the_stub_records_calls_for_assertions() -> None:
    stub = StubGateway(responses={"foreign_influence_specialist": "a finding"})
    response = stub.complete(REQUEST)
    assert response.text == "a finding"
    assert stub.calls[0].node_id == "foreign_influence_specialist"
