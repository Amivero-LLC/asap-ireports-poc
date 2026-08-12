"""The two live orchestrators, by name (ADR-024).

Separated from `port.py` for one reason: this is the only module besides the adapter itself that
may name a framework, and keeping that surface to a single import line is what makes the no-import
test a sharp check rather than a list of exceptions.

Importing this does **not** import LangGraph. `LangGraphOrchestrator` defers the framework import
into `run()`, so a deployment built without the `langgraph` extra can still construct this mapping
and use the hand-rolled entry — it only fails if something actually asks for the LangGraph run.
"""

from __future__ import annotations

from .handrolled import HandRolledOrchestrator
from .langgraph_adapter import LangGraphOrchestrator
from .port import Orchestrator

ORCHESTRATORS: dict[str, Orchestrator] = {
    "hand-rolled": HandRolledOrchestrator(),
    "langgraph": LangGraphOrchestrator(),
}
