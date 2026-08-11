"""Reproduce the bake-off's measured numbers. Not a test — a ruler.

ADR-001: a claim in the handoff package is either cited or reproducible. "Framework-specific lines
of code" is the scorecard's headline number and the one most open to being quietly favourable, so
the counter that produces it lives here rather than in someone's shell history.

    uv run python spikes/measure.py lines
    uv run python spikes/measure.py bytes RUN_ID_PREFIX
    uv run python spikes/measure.py footprint     # builds clean venvs; slow

**What counts as a line.** Physical lines carrying at least one token that is not a comment,
minus docstrings — including the bare-string "attribute docstrings" this repository uses under
module constants. Multi-line strings that are *values* (the SQL `SCHEMA` constants) count in full,
because they are code the candidate had to write. Blank lines never count.

**A recorded correction.** The 2026-08-10 figures for hand-rolled (202) and Strands (367) came
from a count whose method was not recorded. Re-counted here they are 195 and 373 — within 4%, in
opposite directions, and the ordering is unchanged. The numbers this script prints supersede them,
because they are reproducible and the earlier ones were not.
"""

from __future__ import annotations

import ast
import io
import json
import subprocess
import sys
import tokenize
from pathlib import Path

SPIKES = Path(__file__).resolve().parent
REPO = SPIKES.parent

CANDIDATES = {
    "hand-rolled": SPIKES / "handrolled" / "src" / "spike_handrolled",
    "langgraph": SPIKES / "langgraph" / "src" / "spike_langgraph",
    "strands": SPIKES / "strands" / "src" / "spike_strands",
}


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Constant):
            continue
        if isinstance(node.value.value, str) and node.end_lineno is not None:
            lines.update(range(node.lineno, node.end_lineno + 1))
    return lines


def code_lines(path: Path) -> int:
    source = path.read_text()
    occupied: set[int] = set()
    skip = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in skip:
            continue
        occupied.update(range(token.start[0], token.end[0] + 1))
    return len(occupied - _docstring_lines(ast.parse(source)))


def report_lines() -> None:
    for name, package in CANDIDATES.items():
        files = sorted(package.rglob("*.py"))
        total = 0
        print(f"\n{name}")
        for path in files:
            count = code_lines(path)
            total += count
            print(f"  {path.name:24s} {count:5d}")
        print(f"  {'TOTAL':24s} {total:5d}")


# ---------------------------------------------------------------------------
# Serialized state
# ---------------------------------------------------------------------------


MODULES = {
    "hand-rolled": "spike_handrolled",
    "langgraph": "spike_langgraph",
    "strands": "spike_strands",
}


def report_bytes(tag: str) -> None:
    """Drive each candidate to the human-review interrupt, then ask it how big its state is.

    Each candidate measures itself, because "the checkpoint" is not the same object in three
    designs: one row of JSON, one session payload, or a checkpoint row plus its channel blobs
    plus its pending writes. A single SQL query over three schemas would be a fourth opinion
    rather than a measurement.

    The run reaches the *interrupt* and stops there, which is what makes the three numbers
    comparable — every candidate is holding the same three findings, the same manifest, and the
    same routing result at that moment.
    """
    from ireports_spike_harness import port
    from ireports_spike_harness.gateway import init_schema
    from spike_handrolled.orchestrator import HandRolledOrchestrator
    from spike_langgraph.checkpointer import state_bytes
    from spike_strands.orchestrator import StrandsOrchestrator

    init_schema()
    for index, (name, module) in enumerate(MODULES.items()):
        # Equal-length run ids, deliberately. `run_id` is embedded in every finding, and the
        # findings are serialized about ten times across a checkpoint — so a candidate whose name
        # is three characters shorter would "win" this dimension by thirty bytes.
        run_id = f"run_measure_{tag}_{index}"
        outcome = port.invoke(module, "start", "--run-id", run_id).outcome()
        assert len(outcome.proposed_findings) == 3, outcome.status
        if name == "hand-rolled":
            print(f"{name}: {HandRolledOrchestrator().checkpoint_bytes(run_id)}")
        elif name == "strands":
            print(f"{name}: {StrandsOrchestrator().checkpoint_bytes(run_id)}")
        else:
            measured = state_bytes(run_id)
            print(
                f"{name}: {measured['latest_checkpoint']} "
                f"(thread total across all supersteps: {measured['thread_total']})"
            )


# ---------------------------------------------------------------------------
# The duplicate-model-call probe
# ---------------------------------------------------------------------------

CRASH_NODE = "specialist_suitability"
SIBLING_NODE = "specialist_national_security"


def report_duplicates(trials: int = 12, tag: str = "a") -> None:
    """How often does a crash mid-fan-out cause a sibling's model call to be paid for twice?

    Leg 1 deliberately does **not** assert on this. Re-running a sibling whose call the
    orchestrator never observed completing is at-least-once behaviour and is correct: nothing
    durable said that work was done. It is still money, so it is measured.

    Two columns, because they answer different questions. *Issued at crash time* is whether the
    window was even open on that trial — if the sibling had not been called yet, there is nothing
    to duplicate and the trial says nothing. *Re-ran on resume* is the cost. A candidate whose
    node bodies never overlap will score 0 on both and must not be read as having solved anything.
    """
    from ireports_spike_harness import port
    from ireports_spike_harness.gateway import StubModelGateway, init_schema

    init_schema()
    for name, module in MODULES.items():
        issued = reran = duplicated = correct = crashed = 0
        for trial in range(trials):
            run_id = f"run_dup_{tag}_{name.replace('-', '')}_{trial:02d}"
            observer = StubModelGateway(run_id)

            first = port.invoke(module, "start", "--run-id", run_id, "--crash-after", CRASH_NODE)
            if not first.crashed:
                continue
            crashed += 1
            before = observer.call_counts().get(SIBLING_NODE, 0)

            outcome = port.invoke(module, "start", "--run-id", run_id).outcome()
            after = observer.call_counts().get(SIBLING_NODE, 0)

            issued += before >= 1
            reran += after > before
            duplicated += before >= 1 and after > before
            correct += len(outcome.proposed_findings) == 3

        print(
            f"{name}: crashed {crashed}/{trials} · sibling issued at crash {issued}/{trials} · "
            f"sibling re-ran on resume {reran}/{trials} · duplicate paid call "
            f"{duplicated}/{trials} · still 3 findings {correct}/{trials}"
        )


# ---------------------------------------------------------------------------
# Dependency footprint
# ---------------------------------------------------------------------------

BASELINE = SPIKES / "harness"
"""What the domain package already needs. A candidate's cost is measured against this, not
against an empty interpreter — `psycopg` and Pydantic are already required by the architecture."""


def _install_and_measure(target: Path, venv: Path) -> tuple[set[str], int]:
    subprocess.run(["uv", "venv", "--python", "3.12", str(venv)], check=True, capture_output=True)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(venv / "bin" / "python"), str(target)],
        check=True,
        capture_output=True,
        cwd=REPO,
    )
    listing = subprocess.run(
        ["uv", "pip", "list", "--python", str(venv / "bin" / "python"), "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    names = {d["name"] for d in json.loads(listing.stdout)}
    size = sum(f.stat().st_size for f in venv.rglob("*") if f.is_file())
    return names, size


def report_footprint() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base_names, base_size = _install_and_measure(BASELINE, root / "baseline")
        print(f"baseline (harness only): {len(base_names)} distributions, {base_size / 1e6:.1f} MB")
        for name, package in CANDIDATES.items():
            project = package.parents[1]
            names, size = _install_and_measure(project, root / name)
            # The candidate's own `spike-*` distribution is not a dependency it imposes. Match it
            # by package name, not by candidate name: `langgraph` is also a real distribution.
            added = names - base_names - {package.name.replace("_", "-")}
            print(
                f"{name}: +{len(added)} distributions, +{(size - base_size) / 1e6:.1f} MB\n"
                f"    {sorted(added)}"
            )


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "lines"
    if command == "lines":
        report_lines()
    elif command == "bytes":
        report_bytes(sys.argv[2] if len(sys.argv) > 2 else "run_")
    elif command == "duplicates":
        report_duplicates(
            int(sys.argv[2]) if len(sys.argv) > 2 else 12,
            sys.argv[3] if len(sys.argv) > 3 else "a",
        )
    elif command == "footprint":
        report_footprint()
    else:
        raise SystemExit(f"unknown command {command!r}; expected lines, bytes, or footprint")
