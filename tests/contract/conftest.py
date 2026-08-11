"""Contract tests are hermetic: no `IREPORTS_*` variable reaches them from anywhere.

The repo-root `conftest.py` loads `.env` into `os.environ` (ADR-016) so the live smoke check and
the orchestration spike can find their configuration. That is right for those and wrong here.

These tests assert what the gateway does with a *given* configuration. If a developer's `.env`
leaked in, `test_effort_defaults_are_per_tier_and_overridable` would start passing or failing
based on an untracked local file — and a test whose result depends on something not in the
repository is not evidence of anything, which is the one thing this project cannot afford
(ADR-001: claims are backed by something runnable, or marked unverified).

The fixture is autouse and unconditional rather than opt-in per test. A new contract test should
inherit isolation by existing, not by its author remembering to ask for it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [n for n in os.environ if n.startswith("IREPORTS_")]:
        monkeypatch.delenv(name, raising=False)
    yield
