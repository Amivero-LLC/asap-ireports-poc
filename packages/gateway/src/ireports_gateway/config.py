"""Gateway configuration — the one place a concrete model identifier is allowed to live.

ADR-008's whole point is that changing partition, region, or model generation is a **config
change, not a code change**. This module is where that promise is kept: aliases in, concrete
identifiers out, everything sourced from the environment.

Nothing here has a default model ID, and that is deliberate. Q-01 — Claude model availability in
AWS GovCloud, and the concrete model and inference-profile IDs — is the one open question this
project explicitly refuses to assume. Shipping a plausible-looking default would turn an
unanswered question into an invisible assumption, so a missing model ID is a startup error with
a message that names the variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from ireports_domain import ModelAlias

from .port import Effort, GatewayConfigurationError

ENV_PREFIX = "IREPORTS_"


class AdapterKind(StrEnum):
    """Which adapter services model calls. See ADR-015."""

    LITELLM = "litellm"
    BEDROCK = "bedrock"
    STUB = "stub"


DEFAULT_EFFORT: dict[ModelAlias, Effort] = {
    ModelAlias.ORCHESTRATOR: Effort.MEDIUM,
    ModelAlias.THINKING: Effort.HIGH,
    ModelAlias.FAST: Effort.LOW,
}
"""Default reasoning depth per tier (ADR-008's three roles).

`ireports-fast` is `low` effort **with thinking still on**, rather than thinking disabled. That
is a deliberate choice: on current Claude models, disabling thinking has two documented failure
modes — a tool call can be written into visible text instead of emitted as a structured tool-use
block (the call silently never runs, and the turn still succeeds), and internal `<thinking>` tags
can leak into the response. Low effort gets most of the cost and latency saving without either.
For a system whose validators depend on structured output, a silently-skipped tool call is
exactly the failure we cannot afford.

Source: `claude-api` skill, "Two failure modes when thinking is disabled" (2026-08).
"""

_ALIAS_ENV_SUFFIX: dict[ModelAlias, str] = {
    ModelAlias.ORCHESTRATOR: "ORCHESTRATOR",
    ModelAlias.THINKING: "THINKING",
    ModelAlias.FAST: "FAST",
}


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


@dataclass(frozen=True)
class GatewayConfig:
    """Everything the gateway needs, resolved from the environment at startup."""

    adapter: AdapterKind
    max_tokens: int = 16_000
    timeout_seconds: float = 300.0
    max_retries: int = 2

    # LiteLLM adapter
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None

    # Bedrock adapter
    aws_region: str | None = None
    aws_profile: str | None = None
    bedrock_base_url: str | None = None
    bedrock_models: dict[ModelAlias, str] | None = None

    effort: dict[ModelAlias, Effort] | None = None

    @classmethod
    def from_env(cls) -> GatewayConfig:
        raw_adapter = _env("MODEL_ADAPTER", AdapterKind.LITELLM.value) or ""
        try:
            adapter = AdapterKind(raw_adapter)
        except ValueError as exc:
            raise GatewayConfigurationError(
                f"{ENV_PREFIX}MODEL_ADAPTER={raw_adapter!r} is not one of "
                f"{sorted(a.value for a in AdapterKind)}"
            ) from exc

        effort = dict(DEFAULT_EFFORT)
        for alias, suffix in _ALIAS_ENV_SUFFIX.items():
            override = _env(f"EFFORT_{suffix}")
            if override:
                try:
                    effort[alias] = Effort(override)
                except ValueError as exc:
                    raise GatewayConfigurationError(
                        f"{ENV_PREFIX}EFFORT_{suffix}={override!r} is not a valid effort level"
                    ) from exc

        config = cls(
            adapter=adapter,
            max_tokens=int(_env("MODEL_MAX_TOKENS", "16000") or 16000),
            timeout_seconds=float(_env("MODEL_TIMEOUT_SECONDS", "300") or 300),
            max_retries=int(_env("MODEL_MAX_RETRIES", "2") or 2),
            litellm_base_url=_env("LITELLM_BASE_URL"),
            litellm_api_key=_env("LITELLM_API_KEY"),
            aws_region=_env("AWS_REGION") or os.environ.get("AWS_REGION"),
            aws_profile=_env("AWS_PROFILE") or os.environ.get("AWS_PROFILE"),
            bedrock_base_url=_env("BEDROCK_BASE_URL"),
            bedrock_models=cls._bedrock_models_from_env(),
            effort=effort,
        )
        config.validate()
        return config

    @staticmethod
    def _bedrock_models_from_env() -> dict[ModelAlias, str]:
        resolved: dict[ModelAlias, str] = {}
        for alias, suffix in _ALIAS_ENV_SUFFIX.items():
            value = _env(f"BEDROCK_MODEL_{suffix}")
            if value:
                resolved[alias] = value
        return resolved

    # -- validation --------------------------------------------------------

    def validate(self) -> None:
        """Fail at startup, with the variable name, never mid-run.

        A gateway that discovers a missing model ID on the first specialist call has already
        started a run, written a checkpoint, and consumed a reviewer's attention.
        """
        if self.adapter is AdapterKind.LITELLM and not self.litellm_base_url:
            raise GatewayConfigurationError(
                f"adapter 'litellm' requires {ENV_PREFIX}LITELLM_BASE_URL "
                "(the LiteLLM proxy root, e.g. http://localhost:4000)"
            )

        if self.adapter is AdapterKind.BEDROCK:
            if not self.aws_region:
                raise GatewayConfigurationError(
                    f"adapter 'bedrock' requires {ENV_PREFIX}AWS_REGION or AWS_REGION"
                )
            missing = [
                f"{ENV_PREFIX}BEDROCK_MODEL_{suffix}"
                for alias, suffix in _ALIAS_ENV_SUFFIX.items()
                if not (self.bedrock_models or {}).get(alias)
            ]
            if missing:
                raise GatewayConfigurationError(
                    "adapter 'bedrock' requires a model id per tier; missing: "
                    + ", ".join(sorted(missing))
                    + ". These are unvalidated for AWS GovCloud (Q-01) — confirm against the "
                    "target account and region rather than copying a commercial-partition value."
                )
            for alias, model_id in (self.bedrock_models or {}).items():
                if not model_id.startswith("anthropic."):
                    raise GatewayConfigurationError(
                        f"Bedrock model id {model_id!r} for {alias.value!r} is missing the "
                        "'anthropic.' prefix; the bare first-party id fails on Bedrock"
                    )

    # -- resolution --------------------------------------------------------

    def effort_for(self, alias: ModelAlias) -> Effort:
        return (self.effort or DEFAULT_EFFORT)[alias]

    def bedrock_model_for(self, alias: ModelAlias) -> str:
        model_id = (self.bedrock_models or {}).get(alias)
        if not model_id:
            raise GatewayConfigurationError(
                f"no Bedrock model configured for {alias.value!r}; set "
                f"{ENV_PREFIX}BEDROCK_MODEL_{_ALIAS_ENV_SUFFIX[alias]}"
            )
        return model_id
