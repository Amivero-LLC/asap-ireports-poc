"""The build guide reproduces three system prompts. This asserts it reproduces them *exactly*.

`docs/handoff/build-guide.md` is written for a team building the production system from this proof
of concept, and its prompt section is the part most likely to be copied straight into code. A prompt
that has drifted from the implementation is worse than one that is merely absent: the guide states
it is verbatim, so a reader has no reason to check.

This is the same argument as `test_build_state_table.py` — a claim in a handoff document should not
be able to go stale without something failing — applied to the one claim in that document that is
mechanically checkable.

**Character-exact, deliberately.** Em dashes, quote style, and line breaks are all input to a model.
An earlier draft of the guide silently replaced em dashes with hyphens while claiming to be
verbatim, which is exactly the drift this catches.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUIDE = REPO_ROOT / "docs" / "handoff" / "build-guide.md"
ORCHESTRATION = REPO_ROOT / "packages" / "orchestration" / "src" / "ireports_orchestration"

# (module, module-level constant) in the order the guide presents them.
PROMPTS: tuple[tuple[str, str], ...] = (
    ("specialist.py", "SYSTEM"),
    ("synthesis.py", "SYSTEM"),
    ("gather.py", "SUFFICIENCY_SYSTEM"),
)


def _constant(module: str, name: str) -> str:
    """Read a module-level string constant without importing the package.

    Parsed rather than imported so this test cannot be affected by import side effects, and so it
    keeps working if the module grows a dependency that is not installed in every environment.
    """
    tree = ast.parse((ORCHESTRATION / module).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    pytest.fail(f"{module} has no module-level {name}")


def _guide_blocks() -> list[str]:
    return re.findall(r"```text\n(.*?)```", GUIDE.read_text(), re.S)


def test_the_guide_reproduces_every_prompt() -> None:
    """Count first: a guide that dropped a prompt would pass every comparison below."""
    assert len(_guide_blocks()) == len(PROMPTS)


@pytest.mark.parametrize(("module", "name"), PROMPTS)
def test_a_reproduced_prompt_matches_its_source_exactly(module: str, name: str) -> None:
    blocks = _guide_blocks()
    index = PROMPTS.index((module, name))
    reproduced = blocks[index].strip()
    source = _constant(module, name).strip()

    assert reproduced == source, (
        f"{module}:{name} has drifted from docs/handoff/build-guide.md.\n"
        "The guide says these are verbatim, so a reader will not check. Re-copy the constant, "
        "including em dashes and quote style — they are input to a model."
    )


def test_the_prompts_still_forbid_a_determination() -> None:
    """The property the whole architecture rests on, asserted where a team will copy it from.

    Not a substitute for `reject_determinative_language` — the prompt asks and the type enforces,
    and this repository is explicit that the type is the control. But a build guide that reproduced
    a prompt which had quietly lost this instruction would be teaching the wrong thing.
    """
    for module, name in PROMPTS[:2]:  # the two that emit findings; triage emits none
        assert "NEVER state or imply a determination" in _constant(module, name), module
