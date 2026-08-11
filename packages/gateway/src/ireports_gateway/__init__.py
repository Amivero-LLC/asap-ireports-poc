"""The model gateway — the only component in this system permitted to call a model.

Application code imports `ModelGateway`, `ModelRequest`, and `build_gateway`, and nothing else.
It never imports an SDK client, never names a model, and never learns which adapter is running.

    from ireports_gateway import Message, ModelRequest, build_gateway
    from ireports_domain import ModelAlias

    gateway = build_gateway()                      # adapter chosen by configuration
    response = gateway.complete(ModelRequest(
        alias=ModelAlias.THINKING,                 # a tier, never a model
        messages=(Message(role="user", content=prompt),),
        node_id="foreign_influence_specialist",
    ))

See `docs/handoff/model-gateway.md` for the adapter comparison and the configuration surface,
and ADR-015 for why there are two adapters rather than one.
"""

from __future__ import annotations

from .adapters import (
    BedrockGateway,
    LiteLLMGateway,
    StubGateway,
    build_gateway,
)
from .config import DEFAULT_EFFORT, AdapterKind, GatewayConfig
from .port import (
    Effort,
    GatewayConfigurationError,
    GatewayError,
    Message,
    ModelGateway,
    ModelRefusalError,
    ModelRequest,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
    ModelUsage,
    StructuredOutputError,
)

__all__ = [
    "DEFAULT_EFFORT",
    "AdapterKind",
    "BedrockGateway",
    "Effort",
    "GatewayConfig",
    "GatewayConfigurationError",
    "GatewayError",
    "LiteLLMGateway",
    "Message",
    "ModelGateway",
    "ModelRefusalError",
    "ModelRequest",
    "ModelResponse",
    "ModelTimeoutError",
    "ModelUnavailableError",
    "ModelUsage",
    "StructuredOutputError",
    "StubGateway",
    "build_gateway",
]
