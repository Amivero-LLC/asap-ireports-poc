"""Measure import cost and package size per candidate under SAM local (ARCH-03).

Run after `build.py` and `sam build --use-container`:

    uv run python spikes/lambda_fit/build.py
    cd spikes/lambda_fit && sam build --use-container --parallel && cd -
    uv run python spikes/lambda_fit/measure_coldstart.py --runs 5

**What this measures, and what it does not.** `sam local invoke` reports an `Init Duration` of
~0.05 ms for every candidate. That figure is not real: SAM local runs the whole module in one
container step and does not emulate Lambda's init/invoke split, so its `Init Duration` says
nothing. The number that carries signal is `import_seconds`, timed inside the handler module
around the orchestrator import — which is where a framework's dependency tree actually costs you
on a cold start.

So this is an **indicative comparison between candidates on identical footing**, not a production
cold-start figure. A real number needs a deploy to Lambda, which is gated on Q-01 for GovCloud.
The comparison is still the thing ARCH-03 was for: whether LangGraph's dependency weight is
disqualifying relative to the hand-rolled control.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_DIR.parent.parent
BUILD_DIR = SPIKE_DIR / ".aws-sam" / "build"

FUNCTIONS: dict[str, str] = {
    "hand-rolled": "HandRolledFunction",
    "langgraph": "LangGraphFunction",
    "strands": "StrandsFunction",
}

_IMPORT_RE = re.compile(r'"import_seconds":\s*([0-9.]+)')
_DURATION_RE = re.compile(r"Billed Duration:\s*([0-9]+) ms")


def _dir_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def invoke(function: str, event: Path) -> tuple[float, int]:
    """One `sam local invoke`. Returns (import_seconds, billed_ms)."""
    result = subprocess.run(
        ["sam", "local", "invoke", function, "--event", str(event)],
        cwd=SPIKE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    blob = result.stdout + result.stderr
    imp = _IMPORT_RE.search(blob)
    dur = _DURATION_RE.search(blob)
    if not imp or not dur:
        raise SystemExit(
            f"could not parse a measurement for {function}.\n"
            f"Did `sam build --use-container` run? Output follows:\n{blob[-2000:]}"
        )
    return float(imp.group(1)), int(dur.group(1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=SPIKE_DIR / "coldstart.json")
    args = parser.parse_args()

    if not BUILD_DIR.exists():
        raise SystemExit(
            f"{BUILD_DIR} does not exist. Run:\n"
            "  uv run python spikes/lambda_fit/build.py\n"
            "  cd spikes/lambda_fit && sam build --use-container --parallel"
        )

    event = SPIKE_DIR / "event.json"
    event.write_text("{}\n")

    # Interleave candidates round-robin rather than finishing one before starting the next.
    #
    # This is not a style preference. Grouped runs took ~10 minutes end to end, and host load
    # drifted across them: a re-run on a loaded machine moved LangGraph +26% while the hand-rolled
    # control barely changed, pushing the ratio from 3.27x to 4.03x. That spread was measuring the
    # laptop, not the dependency tree. Round-robin spreads any drift across all candidates, so the
    # ratio — which is the actual finding — stays comparable even when absolute numbers wander.
    samples: dict[str, list[tuple[float, int]]] = {label: [] for label in FUNCTIONS}
    for _ in range(args.runs):
        for label, function in FUNCTIONS.items():
            samples[label].append(invoke(function, event))

    results: dict[str, object] = {}
    for label, function in FUNCTIONS.items():
        imports = [s[0] for s in samples[label]]
        billed = [s[1] for s in samples[label]]
        pkg = BUILD_DIR / function
        results[label] = {
            "import_seconds_median": round(statistics.median(imports), 3),
            "import_seconds_min": round(min(imports), 3),
            "import_seconds_max": round(max(imports), 3),
            "billed_ms_median": int(statistics.median(billed)),
            "unzipped_mb": round(_dir_bytes(pkg) / 1_048_576, 1),
            "runs": args.runs,
        }
        r = results[label]
        print(
            f"{label:<12} import {r['import_seconds_median']}s "  # type: ignore[index]
            f"({r['import_seconds_min']}-{r['import_seconds_max']})  "  # type: ignore[index]
            f"billed {r['billed_ms_median']}ms  "  # type: ignore[index]
            f"unzipped {r['unzipped_mb']}MB"  # type: ignore[index]
        )

    baseline = results["hand-rolled"]["import_seconds_median"]  # type: ignore[index]
    for r in results.values():
        r["import_ratio_vs_handrolled"] = round(  # type: ignore[index]
            r["import_seconds_median"] / baseline,
            2,  # type: ignore[index,operator]
        )

    payload = {
        "measured_on": "SAM local, macOS arm64 Docker, python3.12 arm64, 1024 MB",
        "caveat": (
            "Indicative comparison only. SAM local does not emulate Lambda's init phase — its "
            "own Init Duration is ~0.05ms for every candidate and is meaningless. import_seconds "
            "is timed inside the handler module. A production cold-start figure requires a real "
            "Lambda deploy (Q-01)."
        ),
        "candidates": results,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {args.out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
