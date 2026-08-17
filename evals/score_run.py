"""Score saved runs. Free, offline, and re-runnable as the checks improve.

    uv run python -m evals.score_run                       # every run in out/
    uv run python -m evals.score_run --case AMI-SYN-CLR-001
    uv run python -m evals.score_run --run spikes/lambda_demo/out/<file>.json

Reads `spikes/lambda_demo/out/*.json` — a run's own accounting plus its envelope — and reports
what held and what did not. **Nothing here invokes a model or a service.** A run costs real money
and is nondeterministic; scoring it costs nothing and is exact, so the two are separated on
purpose. Pay for the analysis once, score it as many times as the harness improves.

Exit code is 1 when any check fails, so this is usable as a gate. It is deliberately *not* wired
into CI yet: the saved runs are development artifacts, gitignored, and a gate over files that may
not exist would be a gate that passes vacuously.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evals.scorers.properties import classification_is_not_a_constant, score_run

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "out"
CASES_DIR = REPO_ROOT / "spikes" / "lambda_demo" / "cases"


def case_spans(case_id: str) -> dict[str, str] | None:
    """The case's own span text, for hashing excerpts against.

    Returns `None` rather than an empty dict when the case is not on disk, so `excerpt_integrity`
    can report SKIPPED instead of failing every excerpt against nothing.
    """
    evidence = CASES_DIR / case_id / "evidence.json"
    if not evidence.exists():
        return None
    raw = json.loads(evidence.read_text())
    return {s["evidence_id"]: s["text"] for s in raw["spans"]}


def load_runs(args: argparse.Namespace) -> list[tuple[Path, dict[str, Any]]]:
    paths = [Path(args.run)] if args.run else sorted(OUT_DIR.glob("*.json"))
    runs: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skipping {path.name}: {exc}")
            continue
        if args.case and payload.get("case_id") != args.case:
            continue
        runs.append((path, payload))
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="only score runs of this case id")
    parser.add_argument("--run", help="score one run file")
    args = parser.parse_args()

    runs = load_runs(args)
    if not runs:
        raise SystemExit(
            f"no run files matched. {OUT_DIR.relative_to(REPO_ROOT)}/ is written by "
            "run_case.py, and is gitignored — a fresh clone has none until you do a live run."
        )

    failures = 0
    for path, run in runs:
        spans = case_spans(str(run.get("case_id")))
        checks = score_run(run, spans)
        bad = [c for c in checks if not c.passed and not c.skipped]
        failures += len(bad)

        skips = sum(1 for c in checks if c.skipped)
        suffix = f"   [{skips} check(s) not applicable to this run's schema]" if skips else ""
        head = (
            f"{run.get('case_id')}  {run.get('candidate')}  "
            f"{run.get('findings', 0)} findings{suffix}"
        )
        print(f"\n{head}\n{'-' * len(head)}")
        print(f"  {path.name}")
        for check in checks:
            print(f"  {check.mark}  {check.name:<34} {check.detail}")

    corpus = classification_is_not_a_constant([run for _p, run in runs])
    print(f"\ncorpus ({len(runs)} run(s))\n{'-' * 22}")
    print(f"  {corpus.mark}  {corpus.name:<34} {corpus.detail}")
    if not corpus.passed:
        failures += 1
        print(f"        descends from: {corpus.incident}")

    print(f"\n{failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
