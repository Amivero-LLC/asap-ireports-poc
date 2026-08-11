"""The model gateway port — the single boundary between this system and any model.

`CLAUDE.md` names LiteLLM as "the only component permitted to call Bedrock." This module
generalizes that into an interface so the *architecture* holds regardless of which adapter is
configured: application code depends on `ModelGateway`, never on an SDK client, a proxy URL, or
a provider.

Four things this port exists to guarantee:

1. **A model is named by alias, never by ID** (ADR-008). `ModelRequest.alias` is a
   `ModelAlias`; resolving it to something concrete is the adapter's job, driven by config.
2. **A refusal is never mistaken for an answer.** Current Claude models can decline a request
   and still return HTTP 200 with `stop_reason: "refusal"` and possibly empty content. Code that
   reads the first content block unconditionally turns that into an empty finding. Every adapter
   raises `ModelRefusalError` instead.
3. **Raw case text never leaves the access-controlled path.** `ModelResponse` carries usage and
   identifiers that are safe to trace; the prompt and completion are not logged by this package,
   and `ModelUsage` is what the run manifest records.
4. **Budgets are accountable.** Every call returns token counts so `BudgetConsumption` on the
   run manifest reflects what was actually spent (blueprint §8.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from ireports_domain import ModelAlias


class Effort(StrEnum):
    """Reasoning depth, passed through as `output_config.effort`.

    Note what is absent: `temperature`, `top_p`, `top_k`. Current-generation Claude models
    **reject** sampling parameters with a 400, and effort replaces the older fixed
    thinking-token budget. Neither belongs in a request this system builds.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ModelRequest:
    """What a node asks for. Deliberately small.

    There is no `temperature`, no `model`, no `thinking` budget, and no provider hint. A node
    states its tier and its content; everything else is configuration.
    """

    alias: ModelAlias
    messages: tuple[Message, ...]
    system: str | None = None
    max_tokens: int = 16_000
    effort: Effort | None = None
    """None means "use the configured default for this tier" — see `config.GatewayConfig`."""

    response_schema: dict[str, Any] | None = None
    node_id: str | None = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("a model request needs at least one message")
        if self.messages[0].role != "user":
            raise ValueError("the first message must be from the user")


@dataclass(frozen=True)
class ModelUsage:
    """Token accounting. Safe to trace — carries no case content."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )


@dataclass(frozen=True)
class ModelResponse:
    """A completed model call.

    `resolved_model` is recorded for the run manifest's reproducibility story (ADR-009) — it is
    the one place a concrete model identifier is allowed to appear, because a past run cannot be
    explained without knowing what actually served it. It never travels into a contract.
    """

    text: str
    alias: ModelAlias
    resolved_model: str
    usage: ModelUsage = field(default_factory=ModelUsage)
    stop_reason: str | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GatewayError(RuntimeError):
    """Base for every failure this package raises.

    Messages must never contain prompt or completion text — they propagate to logs and traces,
    which `CLAUDE.md` forbids case text from reaching.
    """


class ModelRefusalError(GatewayError):
    """The model declined the request.

    A distinct type because it is not a transport failure and must not be retried blindly. For
    this system it is also a *finding-quality* event: a specialist whose call was refused has
    produced no analysis, and that must reach the reviewer as an information gap rather than as
    silence.
    """

    def __init__(self, category: str | None, explanation: str | None = None) -> None:
        self.category = category
        self.explanation = explanation
        super().__init__(f"model declined the request (category={category or 'unspecified'})")


class StructuredOutputError(GatewayError):
    """A response schema was requested and the returned text is not JSON.

    Distinct from a transport failure and **not** retriable in the naive sense: on some endpoints
    it is a permanent property of the model group, not a transient fault.

    This exists because of a measured behaviour, not a hypothetical one. Against a live
    Bedrock-backed LiteLLM proxy on 2026-08-10, `output_config.format` was accepted with HTTP 200
    and **silently not enforced** on several model groups — the schema is neither applied nor
    rejected, and the model answers with a Markdown-fenced code block instead of bare JSON
    (`docs/handoff/compatibility-matrix.md`).

    The tempting fix is to strip the fence. That would be wrong twice over: it hides from the
    program team that schema enforcement is a per-model-group property rather than a guarantee,
    and it converts a detectable fault into a lenient parser that will one day accept something
    that is not a finding at all. `CLAUDE.md`: the model reasons; it does not decide whether its
    own output is valid.
    """


class ModelTimeoutError(GatewayError):
    """The call did not complete in time. Retriable."""


class ModelUnavailableError(GatewayError):
    """Rate limited, overloaded, or transport failure. Retriable."""


class GatewayConfigurationError(GatewayError):
    """The gateway is misconfigured — raised at construction, never mid-run."""


# ---------------------------------------------------------------------------
# The port
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelGateway(Protocol):
    """What every adapter provides, and all application code may depend on."""

    name: str

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Run one bounded model call.

        Raises `ModelRefusalError` on a refusal, `ModelTimeoutError` or
        `ModelUnavailableError` on retriable failures, and `GatewayError` otherwise. It never
        returns an empty response to represent a failure.
        """
        ...
