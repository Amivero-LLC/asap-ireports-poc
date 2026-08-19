"""Stage one SAM build directory per candidate for the runnable demo.

Same staging pattern as `spikes/lambda_fit/build.py`, and for the same reason: `sam build
--use-container` runs pip inside the Lambda base image, which is the only way to get **Linux**
wheels for compiled dependencies. `pydantic-core` ships a native extension, and a macOS arm64
wheel will not load in a Lambda container — a host build would package something that cannot run.
Everything the build needs therefore has to sit inside the function's `CodeUri`, so our own
pure-Python packages are copied in as source and third-party resolution is left to pip.

Two differences from `lambda_fit`, both because this spike does a different job:

* **The case files are staged too.** `lambda_fit` measured an import and never ran anything. This
  runs a real case, so `cases/` is copied in beside the package and the handler reads it from
  there.
* **`anthropic[bedrock]` is in every candidate's requirements.** The demo makes real model calls
  through `ModelGateway`, so the SDK is not optional. The `bedrock` extra is included even though
  the demo runs the `litellm` adapter, because `packages/gateway` declares it and a package that
  can only construct one of the two adapters is not the gateway this project ships.

**These packages are not size-comparable, and no conclusion should be drawn from their size.**
`lambda_fit` is where package weight was measured, on directories that deliberately share nothing.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_DIR.parent.parent
STAGE_ROOT = SPIKE_DIR / ".stage"
CASES = SPIKE_DIR / "cases"

# Pure Python, so copying source is faithful and avoids a local-path pip install that would not
# resolve inside the build container.
SHARED_SOURCE: tuple[tuple[Path, str], ...] = (
    (REPO_ROOT / "packages" / "domain" / "src" / "ireports_domain", "ireports_domain"),
    (REPO_ROOT / "packages" / "gateway" / "src" / "ireports_gateway", "ireports_gateway"),
    (REPO_ROOT / "packages" / "retrieval" / "src" / "ireports_retrieval", "ireports_retrieval"),
    (
        REPO_ROOT / "packages" / "orchestration" / "src" / "ireports_orchestration",
        "ireports_orchestration",
    ),
    (SPIKE_DIR / "src" / "lambda_demo", "lambda_demo"),
)

BASE_REQUIREMENTS = (
    "pydantic>=2.12",
    "anthropic[bedrock]>=0.121.0",
    "httpx>=0.27",
    "opensearch-py>=3.0,<4",
    # LAMB-01. Both the call store and the hand-rolled checkpoint store are PostgreSQL-backed, and
    # both import `psycopg` lazily so the package still builds without it — which is exactly why it
    # has to be listed here rather than relied upon: a missing driver would not fail the build, it
    # would fail the first invocation that tried to be durable.
    "psycopg[binary]>=3.2",
)

CANDIDATES: dict[str, tuple[str, ...]] = {
    # The control adds nothing to the dependency tree — a thread pool and a loop.
    "handrolled": (),
    # `langgraph-checkpoint-postgres` is the checkpointer, and it is this candidate's alone: the
    # hand-rolled package checkpoints through `checkpoint.py` and `psycopg` above. That the two
    # paths need different packages to do the same job is ADR-026 showing up in a requirements
    # file.
    "langgraph": ("langgraph>=1.2.10,<1.3", "langgraph-checkpoint-postgres>=3.1,<4"),
}

CANDIDATE_ENV: dict[str, str] = {
    # The stage directory name is a filesystem-safe token; `CANDIDATE` is the orchestrator's own
    # name as `ORCHESTRATORS` keys it. Keeping the mapping here means the handler never has to
    # guess which spelling it was given.
    "handrolled": "hand-rolled",
    "langgraph": "langgraph",
}


def stage(candidate: str) -> Path:
    target = STAGE_ROOT / candidate
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for src, name in SHARED_SOURCE:
        if not src.exists():
            raise SystemExit(f"expected package source at {src}, which does not exist")
        shutil.copytree(src, target / name, ignore=ignore)

    if not CASES.is_dir():
        raise SystemExit(f"expected case fixtures at {CASES}, which does not exist")
    # Beside the package, where `handler.CASES_DIR` looks for them by default.
    shutil.copytree(CASES, target / "lambda_demo" / "cases", ignore=ignore)

    reqs = "\n".join((*BASE_REQUIREMENTS, *CANDIDATES[candidate])) + "\n"
    (target / "requirements.txt").write_text(reqs)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", nargs="*", default=sorted(CANDIDATES))
    args = parser.parse_args()

    for candidate in args.candidates or sorted(CANDIDATES):
        if candidate not in CANDIDATES:
            raise SystemExit(f"unknown candidate {candidate!r}; pick from {sorted(CANDIDATES)}")
        target = stage(candidate)
        print(f"staged {candidate} -> {target.relative_to(REPO_ROOT)}")

    print("\nnext:  cd spikes/lambda_demo && sam build --use-container --parallel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
