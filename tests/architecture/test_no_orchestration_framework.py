"""Nothing that ships imports an orchestration framework, or a telemetry client. **ORCH-04.**

**This started as a lock-in guard and is now a security guarantee**, and the difference matters.

ADR-012 chose LangGraph, and a no-import rule kept nodes depending on this project's own port so
that choice could be reversed. ADR-027 reversed it; ADR-029 removed the adapter. What is left is
stronger than the rule it replaced: `langsmith` is a **mandatory** transitive dependency of
`langchain-core`, it is a client capable of exporting run content, and a bake-off negative control
measured an unpinned run POSTing roughly 90 KB — the whole graph state, including every proposed
finding's observation text — to a third-party endpoint, **and succeeding anyway**, because the
client swallows the failure. A misconfigured deployment leaks silently and a blocked one gives the
operator no signal either.

ORCH-04 asked for that to be pinned closed and proven closed at every entry point. Removing the
dependency is a better answer than pinning it: **absence cannot be misconfigured.** This test is
what keeps the absence true, because it is one `pip install` away from not being.

The same argument as SPEC-01's tool allowlist, in the other direction: there, a capability is
unreachable by construction and the requirement is honestly marked vacuous. Here, construction is
the enforcement and this test is the proof.

`spikes/` is deliberately out of scope — it retains the bake-off candidates as ADR-001 evidence, and
those genuinely do import the framework. Nothing in `spikes/` is shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SHIPPED = REPO_ROOT / "packages"

FORBIDDEN = ("langgraph", "langchain", "langchain_core", "langsmith")
"""Packages that must not appear in anything shipped.

`langsmith` is the one that matters and it is never imported directly — it arrives underneath
`langchain-core`, which arrives underneath `langgraph`. Naming all four means the test fails at
whichever level someone reintroduces."""

IMPORTS_FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(FORBIDDEN) + r")\b",
    re.MULTILINE,
)
"""Matches a lazy import inside a function as well as a module-level one. The lazy form is the one
that matters: it is how an adapter would reintroduce a framework, and it is invisible to any check
that inspects a loaded module's imports."""


def _shipped_modules() -> list[Path]:
    return sorted(p for p in SHIPPED.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_shipped_module_imports_an_orchestration_framework() -> None:
    modules = _shipped_modules()
    assert len(modules) >= 20, "the scan found almost nothing; the package layout moved"

    offenders = [
        (m.relative_to(REPO_ROOT), match.group(1))
        for m in modules
        if (match := IMPORTS_FORBIDDEN.search(m.read_text()))
    ]
    assert not offenders, (
        f"{offenders} — nothing shipped may import these. `langsmith` rides in underneath "
        "`langchain-core` and can export run content including finding text (ORCH-04). Absence "
        "is the guarantee; a configuration pin is not."
    )


def test_no_shipped_package_declares_them_as_a_dependency() -> None:
    """The import scan alone would miss a dependency added but not yet used.

    That is the state a package is in for exactly as long as it takes someone to write the import,
    and it is the moment the guarantee is already gone from the built artifact.
    """
    offenders = []
    for pyproject in sorted(SHIPPED.rglob("pyproject.toml")):
        text = pyproject.read_text()
        # Only the dependency declarations, not the prose explaining why they are absent.
        declared = re.findall(r'^\s*"([A-Za-z0-9_.\-\[\]]+)[^"]*",\s*$', text, re.MULTILINE)
        offenders += [
            (pyproject.relative_to(REPO_ROOT), d)
            for d in declared
            if any(d.lower().startswith(f) for f in FORBIDDEN)
        ]
    assert not offenders, offenders


@pytest.mark.parametrize(
    "source",
    [
        "def run(self):\n    from langgraph.graph import START\n",
        "import langgraph\n",
        "from langchain_core.runnables import RunnableConfig\n",
        "import langsmith\n",
    ],
)
def test_the_scan_catches_every_form(source: str) -> None:
    """The negative control. A pattern that matches nothing passes every file.

    The lazy import is first because it is the form a reintroduced adapter would use.
    """
    assert IMPORTS_FORBIDDEN.search(source)


def test_the_scan_does_not_fire_on_prose() -> None:
    """These names appear throughout the docstrings that explain why they are absent.

    A guard that cannot tell an import from an explanation would force the explanation out, and the
    explanation is the reason the guard exists.
    """
    prose = (
        "# see docs/handoff/orchestration-decision.md re langgraph\n",
        '"""LangGraph was removed by ADR-029; langsmith went with it."""\n',
        "    `spikes/langgraph/checkpointer.py` records the same trap from the other side.\n",
    )
    for line in prose:
        assert not IMPORTS_FORBIDDEN.search(line), line
