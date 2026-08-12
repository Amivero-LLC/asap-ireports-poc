"""The first real model calls this project makes. Opt-in, never in the default run.

Every other test of the gateway is offline (`tests/contract/test_model_gateway.py`), and that is
correct — the rules the gateway enforces are properties of the request it builds and the response
it interprets. But an offline suite verifies the gateway as *correctly constructed*, not as
*working*, and `docs/handoff/model-gateway.md` §5 says so in as many words. This module closes
that gap for one specific endpoint, and produces the evidence as a compatibility-matrix row
rather than as a green tick (blueprint §15.3, Q-01).

    IREPORTS_LIVE_SMOKE=1 uv run pytest tests/live -v -s

Skipped by default. It costs money, it needs network egress, and it is non-deterministic — ADR-009
accepted all three knowingly for anything touching a real model path, and the consequence it drew
was that such tests cannot gate CI.

**A refusal is a pass, and is reported as its own outcome.** Adjudicative case files routinely
discuss criminal conduct, substance use, and foreign contacts; refusals are expected traffic for
this domain, not an exotic failure. What this check is asking is "did a request reach a model and
come back interpretable" — a decline answers that as well as an answer does. Conflating the two
would be the same category error the gateway exists to prevent, run backwards.

**What this does not prove.** It exercises whatever endpoint `IREPORTS_LITELLM_BASE_URL` points
at. A result from a commercial-partition proxy says *nothing* about AWS GovCloud: not model
availability, not inference-profile IDs, not cross-region inference rules, not data routing.
Q-01 stays open. See `docs/handoff/compatibility-matrix.md`.

**Synthetic prompts only.** The probes below are trivial and content-free by construction. No
case text, real or synthetic, goes over this wire.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import pytest
from ireports_domain import ModelAlias
from ireports_gateway import (
    AdapterKind,
    GatewayConfig,
    GatewayError,
    Message,
    ModelRefusalError,
    ModelRequest,
    StructuredOutputError,
    build_gateway,
)

ENABLED = os.environ.get("IREPORTS_LIVE_SMOKE") == "1"

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not ENABLED,
        reason="live model check is opt-in: IREPORTS_LIVE_SMOKE=1 (costs money, needs egress)",
    ),
]

PROBE = "Reply with exactly one word: ACK"

Outcome = Literal["answered", "refused", "failed"]


@dataclass
class Probe:
    """One alias, one call, one row of the compatibility matrix."""

    alias: ModelAlias
    outcome: Outcome
    resolved_model: str = "—"
    stop_reason: str = "—"
    input_tokens: int = 0
    output_tokens: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        # Connectivity is the question. A decline reached a model and came back interpretable.
        return self.outcome in ("answered", "refused")


_PROBES: list[Probe] = []
_SCHEMA: dict[ModelAlias, str] = {}


def _render(probes: list[Probe]) -> str:
    header = (
        f"{'alias':<24} {'outcome':<9} {'resolved model':<44}"
        f"{'stop':<10} {'in':>6} {'out':>6}  {'schema':<21}"
    )
    lines = ["", header, "-" * len(header)]
    for p in probes:
        lines.append(
            f"{p.alias.value:<24} {p.outcome:<9} {p.resolved_model:<44}"
            f"{p.stop_reason:<10} {p.input_tokens:>6} {p.output_tokens:>6}  "
            f"{_SCHEMA.get(p.alias, '—'):<21}"
        )
        if p.detail:
            lines.append(f"{'':<24} └─ {p.detail}")
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module", autouse=True)
def _matrix() -> Iterator[None]:
    """Print the matrix once, after every alias has been probed.

    A per-test print would interleave with pytest's own output and would not survive one alias
    failing. The point of this module is the table, not the assertions.
    """
    yield
    print(_render(_PROBES))


@pytest.fixture(scope="module")
def config() -> GatewayConfig:
    resolved = GatewayConfig.from_env()
    if resolved.adapter is AdapterKind.STUB:
        pytest.skip("IREPORTS_MODEL_ADAPTER=stub — nothing to smoke-test")
    return resolved


def test_the_configured_adapter_is_a_production_one(config: GatewayConfig) -> None:
    """Guards against a green run that proved nothing.

    `StubGateway` answers every request instantly and offline. A live check that silently ran
    against it would report three healthy aliases and zero real calls.
    """
    assert config.adapter in (AdapterKind.LITELLM, AdapterKind.BEDROCK)


@pytest.mark.parametrize("alias", list(ModelAlias), ids=lambda a: a.value)
def test_each_alias_reaches_a_model(alias: ModelAlias, config: GatewayConfig) -> None:
    """One call per ADR-008 tier — the aliases are the unit of configuration, so each is a row.

    Probing only one alias would prove the transport and leave the alias→model mapping for the
    other two untested, which is precisely the part that lives outside our repository.
    """
    gateway = build_gateway(config)
    request = ModelRequest(
        alias=alias,
        messages=(Message(role="user", content=PROBE),),
        node_id="live_smoke",
    )

    try:
        response = gateway.complete(request)
    except ModelRefusalError as exc:
        probe = Probe(
            alias=alias,
            outcome="refused",
            stop_reason="refusal",
            detail=f"declined (category={exc.category or 'unspecified'}) — connectivity confirmed",
        )
    except GatewayError as exc:
        probe = Probe(alias=alias, outcome="failed", detail=f"{type(exc).__name__}: {exc}")
    else:
        probe = Probe(
            alias=alias,
            outcome="answered",
            resolved_model=response.resolved_model or "(not reported)",
            stop_reason=response.stop_reason or "—",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            detail="" if response.text.strip() else "empty text with a non-refusal stop reason",
        )

    _PROBES.append(probe)
    assert probe.ok, f"{alias.value}: {probe.detail}"


def test_effort_and_adaptive_thinking_survive_the_hop(config: GatewayConfig) -> None:
    """ADR-015's load-bearing claim, checked against a real endpoint.

    The whole reason both production adapters use the official Anthropic SDK — rather than
    LiteLLM's better-known OpenAI-compatible surface — is that the Anthropic request surface
    survives: adaptive thinking, `output_config.effort`, structured outputs, the `refusal` stop
    reason. Offline tests prove we *send* those fields. Only a real call proves the endpoint
    accepts them: an OpenAI-shaped translation in the middle would 400 on `output_config`, and
    a model generation that predates adaptive thinking would 400 on `thinking`.

    `ireports-thinking` is the tier that carries the highest effort, so it is the one most
    likely to expose a rejection.
    """
    gateway = build_gateway(config)
    try:
        gateway.complete(
            ModelRequest(
                alias=ModelAlias.THINKING,
                messages=(Message(role="user", content=PROBE),),
                node_id="live_smoke_effort",
            )
        )
    except ModelRefusalError:
        pytest.skip("declined — the request surface was accepted, but nothing else is provable")


@pytest.mark.parametrize("alias", list(ModelAlias), ids=lambda a: a.value)
def test_a_requested_schema_is_never_silently_unenforced(
    alias: ModelAlias, config: GatewayConfig
) -> None:
    """Whether the endpoint honours a schema is measured; whether we notice is asserted.

    Structured outputs replaced assistant-prefill on current models, and every deterministic
    validator downstream assumes a finding arrives as parseable JSON. Measured 2026-08-10, that
    assumption does not hold uniformly: `output_config.format` is accepted with HTTP 200 and
    silently not enforced on several model groups.

    So this test does *not* assert that any particular model enforces a schema — that is a
    property of whatever the program approves under Q-01, and asserting it here would bake a
    local accident into the suite. It asserts the invariant we control: a schema request either
    comes back as JSON, or the gateway raises. Never prose returned as though it were a finding.

    The enforcement result per alias goes into the matrix, which is the actual deliverable.
    """
    gateway = build_gateway(config)
    schema = {
        "type": "object",
        "properties": {"acknowledged": {"type": "boolean"}},
        "required": ["acknowledged"],
        "additionalProperties": False,
    }
    request = ModelRequest(
        alias=alias,
        messages=(Message(role="user", content="Set acknowledged to true."),),
        response_schema=schema,
        node_id="live_smoke_schema",
    )

    try:
        response = gateway.complete(request)
    except StructuredOutputError:
        _SCHEMA[alias] = "NOT enforced (caught)"
        return
    except ModelRefusalError:
        _SCHEMA[alias] = "declined"
        pytest.skip("declined — schema enforcement is not provable from this call")
    except GatewayError as exc:
        _SCHEMA[alias] = "failed"
        pytest.fail(f"{alias.value}: {type(exc).__name__}: {exc}")

    _SCHEMA[alias] = "enforced"
    assert json.loads(response.text)["acknowledged"] is True
