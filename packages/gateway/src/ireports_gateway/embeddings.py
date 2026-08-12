"""The embedding port — an embedding is a model call, so it goes through a port too.

ADR-015 says the gateway is the only component permitted to call a model, and nothing about that
argument is specific to text generation: an embedding call has the same properties that made the
port worth having. It names a model, it costs money, it differs by partition, and getting it
subtly wrong is silent.

**Silent is the operative word.** A text model that is misconfigured returns an error. An embedding
model that is misconfigured returns *vectors* — the right shape, the right dimension count, and
semantically unrelated to the ones already in the index. Nothing raises. Retrieval simply gets
worse, and every number downstream becomes meaningless without anyone noticing. That is Q-03, and
it is the reason this is a port rather than a `httpx.post` in the retrieval module.

**Query-time parity, and how it is held here.** The indexed corpus was embedded with
`amazon.titan-embed-text-v2:0`, and the same model is used to embed queries — verified against the
proxy, 1024 dimensions on both sides. `EmbeddingResponse.model` records what actually served each
call so a stored vector can be traced to the model that produced it. An index whose vectors came
from two different models is not detectably broken; it is just quietly bad.

Deliberately small: one method, no batching policy, no caching. Both belong to whoever operates
this at volume, and inventing them here would be guessing at their constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .config import AdapterKind, GatewayConfig
from .port import (
    GatewayConfigurationError,
    GatewayError,
    ModelTimeoutError,
    ModelUnavailableError,
)

EMBEDDING_ALIAS = "ireports-embedding"
"""The tier alias, matching ADR-008's rule for text models: application code names a tier, and
configuration resolves it. `IREPORTS_LITELLM_MODEL_EMBEDDING` supplies the model group on a shared
proxy that does not carry our names (ADR-017)."""


@dataclass(frozen=True)
class EmbeddingResponse:
    """Vectors plus what produced them.

    `model` is recorded for the same reason `ModelResponse.resolved_model` is: a stored vector
    cannot be explained later without knowing what embedded it, and a corpus embedded by two
    models is broken in a way no assertion catches.
    """

    vectors: tuple[tuple[float, ...], ...]
    model: str
    total_tokens: int = 0
    dimensions: int = field(default=0)

    def __post_init__(self) -> None:
        if self.vectors and not self.dimensions:
            object.__setattr__(self, "dimensions", len(self.vectors[0]))


@runtime_checkable
class EmbeddingGateway(Protocol):
    """What every embedding adapter provides."""

    name: str
    dimensions: int

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        """Embed one or more texts. Order in equals order out."""
        ...


class LiteLLMEmbeddingGateway:
    """Embeddings through the LiteLLM proxy's OpenAI-compatible `/v1/embeddings` route.

    Note the asymmetry with `LiteLLMGateway`, which deliberately uses the *Anthropic* Messages
    route: there is no Anthropic embedding API, so the OpenAI-shaped route is the only one, and the
    reasoning that made the Messages route load-bearing (thinking, effort, refusals) has no
    embedding equivalent. Recorded because "why does one adapter use a different route" is
    otherwise a question a reader has to reconstruct.
    """

    name = "litellm-embedding"

    def __init__(self, config: GatewayConfig, dimensions: int = 1024) -> None:
        if not config.litellm_base_url:
            raise GatewayConfigurationError(
                "the embedding gateway requires IREPORTS_LITELLM_BASE_URL"
            )
        self._config = config
        self._base = config.litellm_base_url.rstrip("/")
        self._model = config.embedding_model()
        self.dimensions = dimensions

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        import httpx

        if not texts:
            return EmbeddingResponse(vectors=(), model=self._model, dimensions=self.dimensions)

        try:
            response = httpx.post(
                f"{self._base}/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self._config.litellm_api_key or ''}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": list(texts)},
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("embedding call timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailableError("embedding endpoint unreachable") from exc

        if response.status_code >= 500:
            raise ModelUnavailableError(f"embedding endpoint returned {response.status_code}")
        if response.status_code >= 400:
            # Status and the model we asked for, never the response payload — a 4xx body echoes
            # the input, and the input is case text (`CLAUDE.md`). The model name is configuration
            # rather than content, and naming it is the difference between a debuggable error and
            # "rejected the request": on a shared proxy the usual cause is that this model group
            # is not published under the name we sent (ADR-017).
            raise GatewayError(
                f"embedding endpoint rejected the request ({response.status_code}) for model "
                f"{self._model!r} — check IREPORTS_LITELLM_MODEL_EMBEDDING against the proxy's "
                "published model list"
            )

        payload: dict[str, Any] = response.json()
        rows = sorted(payload.get("data", []), key=lambda r: r.get("index", 0))
        vectors = tuple(tuple(float(x) for x in row["embedding"]) for row in rows)

        if len(vectors) != len(texts):
            raise GatewayError(
                f"asked for {len(texts)} embeddings and got {len(vectors)}; "
                "order-sensitive callers cannot align these"
            )
        widths = {len(v) for v in vectors}
        if len(widths) > 1:
            raise GatewayError(f"embedding endpoint returned mixed dimensions {sorted(widths)}")

        return EmbeddingResponse(
            vectors=vectors,
            model=payload.get("model") or self._model,
            total_tokens=(payload.get("usage") or {}).get("total_tokens", 0) or 0,
            dimensions=next(iter(widths), self.dimensions),
        )


class StubEmbeddingGateway:
    """Deterministic vectors from a hash. Offline, free, and **not** semantic.

    Good enough to test that indexing and querying wire together, and useless for testing whether
    retrieval finds the right thing — similarity here is an artefact of hashing, not meaning. Any
    test asserting retrieval *quality* against this stub is asserting nothing.
    """

    name = "stub-embedding"

    def __init__(self, dimensions: int = 8) -> None:
        self.dimensions = dimensions

    def embed(self, texts: tuple[str, ...]) -> EmbeddingResponse:
        import hashlib

        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            raw = [digest[i % len(digest)] / 255.0 for i in range(self.dimensions)]
            norm = sum(x * x for x in raw) ** 0.5 or 1.0
            vectors.append(tuple(x / norm for x in raw))
        return EmbeddingResponse(
            vectors=tuple(vectors), model="stub-embedding", dimensions=self.dimensions
        )


def build_embedding_gateway(config: GatewayConfig | None = None) -> EmbeddingGateway:
    """Construct the configured embedding adapter.

    There is no `bedrock` adapter here yet. Titan on Bedrock is reachable directly, but the
    Anthropic SDK this package is built on has no embedding surface, so it would mean a boto3
    `bedrock-runtime` client — a second HTTP path with its own auth and error mapping. Worth doing
    when something needs it; not worth guessing at now. Named so its absence is a decision rather
    than an oversight.
    """
    resolved = config or GatewayConfig.from_env()
    if resolved.adapter is AdapterKind.STUB:
        return StubEmbeddingGateway()
    if resolved.adapter is AdapterKind.LITELLM:
        return LiteLLMEmbeddingGateway(resolved)
    raise GatewayConfigurationError(
        f"no embedding adapter for {resolved.adapter.value!r}; use 'litellm' or 'stub'. "
        "A bedrock embedding adapter needs a bedrock-runtime client and does not exist yet."
    )
