"""Pin LangSmith closed, and prove it — the 1b scan's required LangGraph deliverable.

`docs/handoff/orchestration-landscape.md` §5.1 and ADR-012: `langsmith` is a **mandatory**
transitive dependency of `langchain-core` (1.5.3 declares `langsmith<1.0.0,>=0.3.45`), so it is in
the tree whether or not we ever use it. Tracing is opt-in and the default is not egress — but a
client library capable of exporting run content out of a system that may carry CUI is a control to
be *verified and pinned closed*, not a default to be trusted.

**What actually decides whether tracing runs.** Read at `langsmith` 0.10.17,
`langsmith/utils.py::tracing_is_enabled`, which resolves in this order `[first-party]`:

1. the `enabled` key of the current tracing context (a `ContextVar`);
2. whether a `RunTree` is already active;
3. the process-global `_context._GLOBAL_TRACING_ENABLED`;
4. finally the environment — `LANGSMITH_TRACING_V2` / `LANGCHAIN_TRACING_V2`, falling back to
   `LANGSMITH_TRACING` / `LANGCHAIN_TRACING`.

The environment is checked **last**. That is the useful part: `langsmith.configure(enabled=False)`
sets both the context var and the process-global, so it wins over an inherited environment
variable. A deployment that picks up `LANGSMITH_TRACING=true` from a shared task definition, a base
image, or a developer's shell is therefore not able to turn tracing on underneath us.

**Why an environment variable alone is not the control.** Setting `LANGSMITH_TRACING=false`
ourselves would work, but only until something in the process sets it back, and `get_env_var` is
`lru_cache`d so the observed value depends on when it was first read. The API-level global has
neither problem, and it is first-party and documented (`langsmith.configure(enabled=False)` is the
"Disabling tracing" example in `run_trees.py`).

**Fail closed.** `pin_tracing_closed` verifies the result and raises if tracing is still enabled.
A telemetry control that silently fails to apply is worse than none, because it is reported as
present. This mirrors ADR-018's rule one layer out: a requested guarantee is verified, not trusted.

The proof that this holds — including a negative control showing that *without* the pin a run does
attempt egress — is `spikes/langgraph/test_langsmith_egress.py`.
"""

from __future__ import annotations


class TracingPinError(RuntimeError):
    """Raised when LangSmith tracing could not be pinned off. Never swallowed."""


def pin_tracing_closed() -> None:
    """Disable LangSmith tracing process-wide, then verify it.

    Called from this candidate's entry point rather than at import time. Import-time side effects
    on a shared library are exactly the hidden-dependency problem ADR-016 rejects for `.env`;
    the same reasoning applies to a global that changes telemetry behaviour.
    """
    import langsmith
    from langsmith.utils import tracing_is_enabled

    langsmith.configure(enabled=False)

    if tracing_is_enabled():
        raise TracingPinError(
            "LangSmith tracing is still enabled after langsmith.configure(enabled=False); "
            "refusing to run a workload that may carry CUI with an unpinned telemetry client"
        )
