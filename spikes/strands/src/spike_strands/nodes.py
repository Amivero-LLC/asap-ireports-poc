"""Wrapping the shared scenario functions as Strands graph nodes.

`GraphBuilder.add_node` accepts an `AgentBase` or a `MultiAgentBase`, and the scenario functions
are neither — they are deterministic Python that never calls a model (`harness/scenario.py`). So
each becomes a `MultiAgentBase` whose `invoke_async` runs the shared function.

**The framework cost this file exposes.** A node's durable result must be an `AgentResult`, and
`AgentResult.to_dict` persists exactly two fields: `message` and `stop_reason`. `metrics` and
`state` are dropped. So the only channel through which a node's output survives a process death is
**the assistant message body** — our typed Pydantic contracts have to be flattened into message
text and re-validated on the way back out.

That is the sharpened version of the concern §5.2 of the landscape scan raised. The Diagrid claim
was that Strands restores *conversation* rather than resuming *execution*; for a `Graph` in 1.51.0
that is not quite right — `serialize_state` carries `completed_nodes` and `next_nodes_to_execute`,
so execution genuinely resumes. What is true is that the *container* for state is
conversation-shaped, and a workflow carrying typed records pays a serialize/parse tax at every
node boundary that a purpose-built state graph does not.

`_decode` is where that tax is paid, and it is also where the trust boundary sits: every payload
coming back out of the store is re-validated through the domain contracts, never trusted.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from strands.agent import AgentResult
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, NodeResult, Status
from strands.telemetry.metrics import EventLoopMetrics
from strands.types.content import Message

PAYLOAD_SLOT = "payload"
"""Nested-result key holding the node's JSON body. One slot: nodes return one payload."""


def encode(payload: Any) -> MultiAgentResult:
    """Wrap a JSON-serializable payload as the only shape Strands will persist."""
    message: Message = {"role": "assistant", "content": [{"text": json.dumps(payload)}]}
    agent_result = AgentResult(
        stop_reason="end_turn",
        message=message,
        metrics=EventLoopMetrics(),
        state={},
    )
    return MultiAgentResult(
        status=Status.COMPLETED,
        results={
            PAYLOAD_SLOT: NodeResult(result=agent_result, status=Status.COMPLETED),
        },
    )


def decode(node_result: NodeResult) -> Any:
    """Pull a node's payload back out of a (possibly session-restored) result.

    Handles both the live object and the rehydrated one — after a resume these are structurally
    identical but were rebuilt by `MultiAgentResult.from_dict`, which is precisely the path
    leg 1 exercises.
    """
    inner = node_result.result
    if not isinstance(inner, MultiAgentResult):
        raise TypeError(f"expected a MultiAgentResult payload, got {type(inner)!r}")
    payload_node = inner.results[PAYLOAD_SLOT]
    agent_result = payload_node.result
    if not isinstance(agent_result, AgentResult):
        raise TypeError(f"expected an AgentResult payload, got {type(agent_result)!r}")
    text = "".join(block.get("text", "") for block in agent_result.message.get("content", []))
    return json.loads(text)


class ScenarioNode(MultiAgentBase):
    """One shared scenario function, presented to Strands as a multi-agent node.

    `run` receives the orchestrator, so a node can read prior nodes' payloads out of the graph's
    own restored state rather than out of `Graph._build_node_input`. That is deliberate: the
    framework's node input is a *prose summary* of upstream results, formatted for a model to
    read ("From data_processor:\\n  - Agent: ..."). Parsing typed findings back out of English
    would measure our regex, not the framework's durability.
    """

    def __init__(self, node_id: str, run: Callable[[dict[str, Any]], MultiAgentResult]) -> None:
        super().__init__()
        self.id = node_id
        self._run = run

    async def invoke_async(
        self,
        task: Any,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> MultiAgentResult:
        return self._run(invocation_state or {})

    async def stream_async(
        self,
        task: Any,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        result = await self.invoke_async(task, invocation_state, **kwargs)
        yield {"result": result}
