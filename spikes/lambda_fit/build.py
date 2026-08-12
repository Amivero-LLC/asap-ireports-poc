"""Stage one SAM build directory per candidate (ARCH-03, cold-start leg).

Why staging rather than pointing SAM at the repo: `sam build --use-container` runs pip inside the
Lambda base image, which is the only way to get *Linux* wheels for compiled dependencies —
`pydantic-core` and `psycopg[binary]` both ship native extensions, and a macOS arm64 wheel will
not load in a Lambda container. Anything the build needs must therefore sit inside the function's
`CodeUri`, so this copies our own pure-Python packages in as source and leaves third-party
resolution to pip.

Each candidate gets its own directory containing only its own dependency set. Sharing one
directory would let the heaviest candidate's tree inflate everyone's package size, which is
precisely the number being compared.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STAGE_ROOT = REPO_ROOT / "spikes" / "lambda_fit" / ".stage"
HANDLER = REPO_ROOT / "spikes" / "lambda_fit" / "functions" / "app.py"

# Our own packages are pure Python, so copying source is faithful and avoids a local-path pip
# install that would not resolve inside the build container.
SHARED_SOURCE: tuple[tuple[Path, str], ...] = (
    (REPO_ROOT / "packages" / "domain" / "src" / "ireports_domain", "ireports_domain"),
    (
        REPO_ROOT / "spikes" / "harness" / "src" / "ireports_spike_harness",
        "ireports_spike_harness",
    ),
)

CANDIDATES: dict[str, dict[str, object]] = {
    "handrolled": {
        "source": (
            REPO_ROOT / "spikes" / "handrolled" / "src" / "spike_handrolled",
            "spike_handrolled",
        ),
        # The control. Its whole argument is that it adds nothing to the dependency tree.
        "requirements": ["pydantic>=2.12", "psycopg[binary,pool]>=3.2"],
    },
    "langgraph": {
        "source": (
            REPO_ROOT / "spikes" / "langgraph" / "src" / "spike_langgraph",
            "spike_langgraph",
        ),
        "requirements": [
            "pydantic>=2.12",
            "psycopg[binary,pool]>=3.2",
            "langgraph>=1.2.10,<1.3",
            "langgraph-checkpoint-postgres>=3.1.2,<3.2",
        ],
    },
    "strands": {
        "source": (
            REPO_ROOT / "spikes" / "strands" / "src" / "spike_strands",
            "spike_strands",
        ),
        "requirements": [
            "pydantic>=2.12",
            "psycopg[binary,pool]>=3.2",
            "strands-agents>=1.51,<1.52",
        ],
    },
}


def stage(candidate: str) -> Path:
    spec = CANDIDATES[candidate]
    target = STAGE_ROOT / candidate
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    shutil.copy2(HANDLER, target / "app.py")

    sources = [*SHARED_SOURCE, spec["source"]]  # type: ignore[list-item]
    for src, name in sources:  # type: ignore[misc]
        if not src.exists():
            raise SystemExit(f"expected package source at {src}, which does not exist")
        shutil.copytree(src, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    reqs = "\n".join(spec["requirements"]) + "\n"  # type: ignore[arg-type]
    (target / "requirements.txt").write_text(reqs)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="*", default=sorted(CANDIDATES))
    args = parser.parse_args()

    chosen = args.candidates or sorted(CANDIDATES)
    for candidate in chosen:
        if candidate not in CANDIDATES:
            raise SystemExit(f"unknown candidate {candidate!r}; pick from {sorted(CANDIDATES)}")
        target = stage(candidate)
        print(f"staged {candidate} -> {target.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
