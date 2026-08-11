"""The checkpoint blob is a deserialization trust boundary — proven, not asserted.

ADR-012's third added deliverable. The finding it exists to support is **framework-independent**:
the 1b scan catalogued four deserialization advisories on LangGraph's checkpoint path between
November 2025 and June 2026, all fixed at or below the versions we use, and concluded that the
lesson is not "LangGraph is insecure" but that a checkpoint blob is a trust boundary in *any*
design, hand-rolled included. The narrative version is
`docs/handoff/checkpoint-threat-model.md`; this file is the part a test runner can check.

What is demonstrated here, on `langgraph-checkpoint` 4.2.0:

1. The library's **default** msgpack deserialization is permissive. A checkpoint row naming an
   arbitrary importable class causes that class to be imported and constructed on load. The
   library says so itself in `serde/_msgpack.py`: *"Without this, any Python callable stored in
   checkpoint data will be imported and executed on load."*
2. `strict_serde()` — which is what this candidate actually installs — blocks it.
3. Strict mode **degrades rather than raises**: the blocked value comes back as a plain `dict`.
   That is the reason the architecture re-validates every payload through the domain contracts
   instead of trusting what the checkpointer returns. A soft failure that produced a `dict` where
   a `ProposedFinding` was expected would otherwise reach a reviewer as missing analysis.

Nothing here executes anything dangerous. The stand-in is a dataclass that records its own
construction, which is sufficient to distinguish "the blob named a type and it was built" from
"the blob named a type and it was refused".
"""

from __future__ import annotations

import dataclasses

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from spike_langgraph.checkpointer import strict_serde

CONSTRUCTED: list[str] = []


@dataclasses.dataclass
class ConstructedFromTheBlob:
    """Stands in for any class a tampered checkpoint row could name."""

    tag: str = "x"

    def __post_init__(self) -> None:
        CONSTRUCTED.append(self.tag)


def _payload() -> tuple[str, bytes]:
    """A checkpoint value that names a type outside the safe allowlist."""
    return JsonPlusSerializer().dumps_typed({"payload": ConstructedFromTheBlob("from-the-blob")})


def test_default_serializer_constructs_arbitrary_types_from_the_blob() -> None:
    """Negative control: the library default is permissive, and this is what that means.

    If a future version makes strict the default, this test fails — which is good news arriving
    as a red test rather than as an unread changelog entry.
    """
    blob = _payload()  # building it constructs one instance; that is not what we are counting
    CONSTRUCTED.clear()
    loaded = JsonPlusSerializer().loads_typed(blob)

    assert isinstance(loaded["payload"], ConstructedFromTheBlob)
    assert CONSTRUCTED == ["from-the-blob"], (
        "the permissive default did not construct the type named by the blob; the negative "
        "control is no longer demonstrating the risk it was written for"
    )


def test_strict_serializer_refuses() -> None:
    """The control this candidate installs: the named type is not imported or constructed."""
    blob = _payload()
    CONSTRUCTED.clear()
    loaded = strict_serde().loads_typed(blob)

    assert CONSTRUCTED == [], "strict mode constructed a type outside the allowlist"
    assert not isinstance(loaded["payload"], ConstructedFromTheBlob)


def test_strict_mode_fails_soft_which_is_why_contracts_re_validate() -> None:
    """A blocked value returns as a plain `dict`, not as an exception.

    Recorded as a test because it is the load-bearing consequence: the checkpointer will hand back
    something structurally wrong without complaining, so refusing to trust it is the application's
    job. `orchestrator.SpikeState` stores plain JSON and re-validates through the domain contracts
    for exactly this reason.
    """
    loaded = strict_serde().loads_typed(_payload())
    assert isinstance(loaded["payload"], dict)


def test_pickle_fallback_is_off() -> None:
    """`pickle` is never a checkpoint format here.

    Off by default in 4.2.0 and passed explicitly by `strict_serde()`, so a changed default shows
    up in a diff. `GHSA-mhr3-j7m5-c7c9` was untrusted deserialization on this class of path.
    """
    assert strict_serde().pickle_fallback is False
