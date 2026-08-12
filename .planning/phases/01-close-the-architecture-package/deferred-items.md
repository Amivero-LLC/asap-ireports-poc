# Deferred items — Phase 1

Out-of-scope discoveries surfaced while executing this phase's plans. Not fixed here per the
scope-boundary rule: only issues directly caused by the current task's changes get auto-fixed.

## Plan 01-01

- **`uv run ruff format --check` (whole repo) fails on a pre-existing file:**
  `.planning/phases/01-close-the-architecture-package/01-PATTERNS.md:274` — ruff's Markdown
  formatter would reformat an embedded ` ```python ` code fence (a multi-line docstring collapsed
  to one line). This file predates plan 01-01 (committed in `16e94b7`, part of the phase-planning
  step, not touched by any 01-01 task) and is not in 01-01's `files_modified`. Every file 01-01
  actually modified is individually clean under `ruff format --check`. Left unfixed; whoever next
  touches `01-PATTERNS.md` should run `uv run ruff format` on it.
- **`uv run mypy --strict tests/contract` reports 3 pre-existing errors in
  `tests/contract/test_model_gateway.py`** (two `import-untyped` on `ireports_gateway`, one `misc`
  subclassing-`Any` on `_AnthropicAdapterBase`). Confirmed present before any 01-01 change (commit
  `fbb4594`, "chore: clear the mypy backlog"). Unrelated to `SpecialistResult`; left unfixed.
