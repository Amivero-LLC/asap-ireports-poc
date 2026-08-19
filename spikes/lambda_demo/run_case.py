"""Run one synthetic case through both Lambdas and write the envelopes where you can open them.

    docker compose -f infrastructure/docker/compose.yaml up -d    # OpenSearch: required
    uv run --env-file .env python spikes/lambda_demo/index_cases.py
    uv run python spikes/lambda_demo/build.py
    cd spikes/lambda_demo && sam build --use-container --parallel && cd -
    uv run --env-file .env python spikes/lambda_demo/run_case.py

The last command is the point of the whole spike. It invokes both functions under SAM local, and
each writes `out/<candidate>-<run_id>.json` — a validated `ASAPEnvelope` plus the run's accounting.
Open one. That file is what the architecture produces.

**The compose line used to say "not needed; no Postgres here" and was wrong from the day
specialists started retrieving their own evidence.** OpenSearch holds the indexed cases, and
without it a run completes reporting `nothing in the record matched` for every criterion — a
missing service that reads like a clean record. `preflight()` now refuses to start on that, and on
a stopped Docker daemon, rather than letting either surface a minute later as something else.

`--verbose` prints the raw SAM and container streams, including the Lambda runtime's
`START` / `END` / `REPORT` records and the handler's own structured log lines. The default output
is a reading of the response; `--verbose` is a record of the invocation.

`--resume-demo` is LAMB-01: it invokes the *same run id* twice, the first with a wall-clock
ceiling below the work required, and reports whether the second invocation finished what the first
started without re-buying it. It needs the compose PostgreSQL as well as OpenSearch — that is
where paid calls and completed nodes are recorded, and a SAM container is a genuine process
boundary, so nothing else connects the two invocations.

**Real model calls, real money.** A full run is roughly 22k tokens across six thinking-tier calls
(three specialists x two candidates, plus any bounded retry); `--resume-demo` costs about one
uninterrupted run per candidate, which is the point — the second invocation pays only for what the
first did not reach. Nothing in CI runs this, and nothing should: `--candidate` narrows it to one
orchestrator when you only need to see it work.

**Credentials.** `GatewayConfig` reads `IREPORTS_*` from the environment (ADR-016), and a SAM
container inherits nothing from this shell, so the variables are written to a `--env-vars` file
first. That file holds a live proxy key and is gitignored; it is rewritten on every run and never
printed. If you are adding to this script, keep it that way — `_env_vars_payload` is the only
place a secret is handled, and it hands SAM a path rather than an argument, because a command line
is visible in `ps` output to every user on the box.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SPIKE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_DIR.parent.parent
BUILD_DIR = SPIKE_DIR / ".aws-sam" / "build"
OUT_DIR = SPIKE_DIR / "out"
ENV_VARS_FILE = SPIKE_DIR / ".env-vars.json"

FUNCTIONS: dict[str, str] = {
    "hand-rolled": "HandRolledFunction",
    "langgraph": "LangGraphFunction",
}

# Everything the gateway reads, and nothing else. An allowlist rather than "forward the whole
# environment": a container that inherits the host's variables acquires whatever else happens to
# be exported — AWS session tokens, unrelated API keys — and none of that belongs in a demo.
ENV_PREFIXES = ("IREPORTS_",)

DEFAULT_CONTAINER_OPENSEARCH = "http://host.docker.internal:9201"
"""Where the compose stack's OpenSearch lives *from inside a SAM container*."""

HOST_OPENSEARCH = "http://localhost:9201"
"""The same cluster, from this shell. `preflight` checks it here rather than guessing whether the
container can see it — a host-side failure is the one a developer can actually act on."""
DEFAULT_CONTAINER_DSN = (
    "postgresql://ireports:ireports_local_only@host.docker.internal:5436/ireports_spike"
)
"""The compose stack's PostgreSQL *from inside a SAM container* — where a run's paid calls and
completed nodes are recorded so a second invocation can use them (LAMB-01)."""

HOST_DSN = "postgresql://ireports:ireports_local_only@localhost:5436/ireports_spike"
"""The same database from this shell, for the preflight check."""

ENV_EXCLUDE = frozenset(
    {
        # The host-side name for the same database `IREPORTS_STATE_DSN` names container-side.
        # Forwarded under its own name after a host rewrite (see `_env_vars_payload`) rather than
        # verbatim, because `localhost` inside a container is the container.
        "IREPORTS_SPIKE_DSN",
        # A host-side pytest switch. Forwarding it would suggest the function reads it.
        "IREPORTS_LIVE_SMOKE",
    }
)


def _declared_variables() -> set[str]:
    """The `IREPORTS_*` names the built template declares.

    Read back from the template rather than kept in a list here, because `sam local invoke
    --env-vars` **only overrides variables the template already declares**. An undeclared one is
    dropped without a word, and the function then fails inside the container reporting a missing
    variable that is plainly set in your shell — which reads as a credentials problem and is not
    one. Deriving the set from the template makes that impossible to get wrong twice.
    """
    template = BUILD_DIR / "template.yaml"
    if not template.exists():
        template = SPIKE_DIR / "template.yaml"
    # A regex rather than a YAML parse: this keeps the runner free of a parser dependency, and
    # the pattern is anchored to a key at the start of a line, which is the only shape these
    # names take in a template we own.
    return set(re.findall(r"^\s*(IREPORTS_[A-Z0-9_]+)\s*:", template.read_text(), re.MULTILINE))


def _env_vars_payload(overrides: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    """The `--env-vars` document: every declared gateway variable, per function.

    Empty values are dropped rather than forwarded as `""`. `GatewayConfig.validate()` treats an
    empty string as absent and names the missing variable, which is the error you want; an empty
    string forwarded into the container produces the same failure one layer further away.

    `overrides` is applied last and is how the two invocations of `--resume-demo` differ: the first
    carries a wall-clock ceiling below the work required, the second does not.
    """
    declared = _declared_variables()
    candidates = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(ENV_PREFIXES) and key not in ENV_EXCLUDE and value.strip()
    }
    candidates.update({k: v for k, v in (overrides or {}).items() if v.strip()})
    if not candidates:
        raise SystemExit(
            "no IREPORTS_* variables are set, so the gateway has nothing to authenticate with.\n"
            "Run this as:  uv run --env-file .env python spikes/lambda_demo/run_case.py"
        )

    # The container cannot reach the host's OpenSearch at localhost. Rewritten here rather than in
    # .env, so a developer's host-side tooling keeps working unchanged.
    if "IREPORTS_OPENSEARCH_URL" in declared:
        candidates.setdefault("IREPORTS_OPENSEARCH_URL", DEFAULT_CONTAINER_OPENSEARCH)
        candidates["IREPORTS_OPENSEARCH_URL"] = (
            candidates["IREPORTS_OPENSEARCH_URL"]
            .replace("localhost", "host.docker.internal")
            .replace("127.0.0.1", "host.docker.internal")
        )

    # Same rewrite, same reason, one variable later: a DSN naming `localhost` resolves to the
    # container itself, so the run would report a connection failure rather than a missing
    # checkpoint. Left as configuration because the deployed function points at RDS unchanged.
    if "IREPORTS_STATE_DSN" in candidates:
        candidates["IREPORTS_STATE_DSN"] = (
            candidates["IREPORTS_STATE_DSN"]
            .replace("localhost", "host.docker.internal")
            .replace("127.0.0.1", "host.docker.internal")
        )

    forwarded = {k: v for k, v in candidates.items() if k in declared}
    dropped = sorted(set(candidates) - declared)
    if dropped:
        # Named, never silent. This is the exact failure the declaration list exists to prevent,
        # so it is worth a line rather than a shrug.
        print(
            f"not forwarding {dropped} — the template does not declare them, and SAM drops "
            "undeclared overrides. Add them to template.yaml if the function needs them."
        )
    if not forwarded:
        raise SystemExit(
            f"none of the IREPORTS_* variables set in this shell are declared in the template "
            f"({sorted(declared)}), so the container would start with no configuration at all."
        )
    return dict.fromkeys(FUNCTIONS.values(), forwarded)


def write_env_vars(overrides: dict[str, str] | None = None) -> Path:
    ENV_VARS_FILE.write_text(json.dumps(_env_vars_payload(overrides), indent=2) + "\n")
    ENV_VARS_FILE.chmod(0o600)
    return ENV_VARS_FILE


def _payload_from(stdout: str) -> dict[str, Any]:
    """Pull the function's return value out of `sam local invoke` output.

    SAM sends its own chatter to stderr and the function's response to stdout, but the container's
    stdout is interleaved too — the handler's own log lines are JSON objects on that same stream.
    So this parses candidates and keeps the last one that looks like a handler response, rather
    than trusting the stream to hold exactly one document.
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    for match in re.finditer(r"^\s*\{", stdout, re.MULTILINE):
        try:
            value, _ = decoder.raw_decode(stdout[match.start() :].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "run_id" in value and "candidate" in value:
            found.append(value)
    if not found:
        raise SystemExit(
            "could not find a handler response in the SAM output.\n"
            "Did `sam build --use-container` run? Last 2000 characters:\n" + stdout[-2000:]
        )
    # The response is emitted after the log lines, and only the response carries `findings`.
    return max(found, key=lambda v: ("findings" in v, len(v)))


def preflight(require_postgres: bool = False) -> None:
    """Fail at the door, naming the service, rather than sixty seconds in.

    Both of these were paid for by hand before they were checked here, and they fail differently:

    * **No container runtime** — `sam local invoke` reports "requires a container runtime" after
      the script has already written an env-vars file and printed "real model calls, this takes
      ~20s". Loud, but at the wrong moment and about the wrong layer.
    * **No OpenSearch** — far worse, because it does not fail. Retrieval returns nothing, every
      criterion reports `nothing in the record matched`, the run completes, and the output reads
      like a broken *analysis* rather than a missing *service*. That is the same
      indistinguishable-from-a-clean-record failure this system exists to prevent, wearing
      infrastructure clothes.

    The cluster is checked from the host, at the host-side port, so a misconfigured
    `IREPORTS_OPENSEARCH_URL` still gets a clear message rather than a container-side timeout.
    """
    if shutil.which("docker") is None:
        raise SystemExit(
            "docker is not on PATH. SAM runs the function inside a Lambda container image, so a "
            "container runtime is required.\n  open -a Docker"
        )
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        raise SystemExit(
            "the docker daemon is not running, so SAM has nowhere to invoke the function.\n"
            "  open -a Docker    # then re-run this"
        )

    url = os.environ.get("IREPORTS_OPENSEARCH_URL") or HOST_OPENSEARCH
    health = url.replace("host.docker.internal", "localhost").rstrip("/") + "/_cluster/health"
    try:
        with urllib.request.urlopen(health, timeout=5) as response:
            json.loads(response.read())
    except (OSError, ValueError):
        raise SystemExit(
            f"OpenSearch is not reachable at {health}. The specialists retrieve their evidence "
            "from it, and without it every criterion reports 'nothing in the record matched' — a "
            "missing service that reads like a clean record.\n"
            "  docker compose -f infrastructure/docker/compose.yaml up -d\n"
            "  uv run --env-file .env python spikes/lambda_demo/index_cases.py"
        ) from None

    if not require_postgres:
        return

    # Checked from the host for the same reason OpenSearch is: a container-side failure surfaces
    # sixty seconds later as a connection error inside a Lambda log, and a developer cannot tell
    # it from a bad DSN.
    dsn = os.environ.get("IREPORTS_STATE_DSN") or os.environ.get("IREPORTS_SPIKE_DSN") or HOST_DSN
    host_dsn = dsn.replace("host.docker.internal", "localhost")
    try:
        import psycopg

        with psycopg.connect(host_dsn, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # any failure to reach it earns the same instruction
        raise SystemExit(
            f"PostgreSQL is not reachable at {host_dsn.rsplit('@', 1)[-1]}: "
            f"{type(exc).__name__}. "
            "The resume demo records paid calls and completed nodes there, so a second invocation "
            "has something to resume from — without it the two invocations are simply two runs.\n"
            "  docker compose -f infrastructure/docker/compose.yaml up -d"
        ) from None


def invoke(
    function: str, event: dict[str, Any], env_vars: Path, verbose: bool = False
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(event, handle)
        event_path = Path(handle.name)
    try:
        result = subprocess.run(
            [
                "sam",
                "local",
                "invoke",
                function,
                "--event",
                str(event_path),
                "--env-vars",
                str(env_vars),
            ],
            cwd=SPIKE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        event_path.unlink(missing_ok=True)

    if verbose:
        # Both streams, unfiltered. SAM's own chatter and the container mount go to stderr; the
        # handler's structured log lines and the Lambda runtime's START/END/REPORT records come
        # back on stdout. Printed rather than summarised because "show me what actually happened
        # inside the function" has no other answer — the summary below is a reading of the
        # response, not a record of the invocation.
        print(f"\n----- {function}: sam stderr " + "-" * 34)
        print(result.stderr.rstrip())
        print(f"----- {function}: container stdout " + "-" * 30)
        print(result.stdout.rstrip())
        print("-" * 72)

    if result.returncode != 0 and not result.stdout.strip():
        raise SystemExit(f"sam local invoke {function} failed:\n{result.stderr[-2000:]}")
    return _payload_from(result.stdout)


def _timeline_rows(trace: list[dict[str, Any]]) -> list[str]:
    """Render the run's node timings, reusing the package's own renderer.

    Imported here rather than at module scope so this script keeps starting without the
    orchestration package importable — it is a runner, and its job is to report what the Lambda
    returned even when the local environment is half-configured.
    """
    from ireports_orchestration import NodeSpan, timeline

    return timeline(
        tuple(
            NodeSpan(node_id=s["node_id"], started=float(s["started"]), ended=float(s["ended"]))
            for s in trace
        )
    )


def _report(payload: dict[str, Any], out_file: Path | None) -> None:
    candidate = payload["candidate"]
    tokens = payload.get("tokens", {})
    print(
        f"\n{candidate:<12} {payload['wall_seconds']}s  "
        f"{tokens.get('total', 0):,} tokens  "
        f"{payload['findings']} findings"
    )
    for criterion in payload.get("criteria", []):
        status = criterion.get("status", "completed")
        # "completed with 0 findings" and "refused" are different facts, and the run output is
        # where that distinction has to be visible or it is not visible anywhere.
        marker = "" if status == "completed" else f"  <-- {status.upper()}, NOT ANALYSED"
        print(
            f"  {criterion['criterion_id']:<14} "
            f"{criterion['findings']} findings, {criterion['rejected']} rejected{marker}"
        )
    synthesis = payload.get("synthesis")
    if synthesis:
        if synthesis.get("failed"):
            print("  synthesis   RAN AND FAILED — see the rejection below")
        elif not synthesis["ran"]:
            print("  synthesis   skipped — fewer than two findings to reason across")
        else:
            print(f"  synthesis    {synthesis['findings']} cross-criterion findings")
        for overlap in synthesis["overlaps"]:
            # The cheapest useful output in the whole run: set arithmetic, no model call.
            print(
                f"    {overlap['evidence_id']} carries findings under "
                f"{len(overlap['criterion_ids'])} criteria: {overlap['criterion_ids']}"
            )

    trace = payload.get("trace") or []
    if trace:
        # **The evidence, not a summary of it.** Everything else in this report is a count; this is
        # the only part that shows the orchestration *shape* — three specialists starting together,
        # then two, then synthesis waiting for all of them. A serial implementation would produce
        # the same counts above and a visibly different picture here.
        peak = payload.get("peak_concurrency", 0)
        print(f"  timeline — peak {peak} node(s) at once:")
        for row in _timeline_rows(trace):
            print(row)

    for reason in payload.get("rejected", []):
        # Not an error log. Every line here is the deterministic shell refusing something the
        # model produced, which is the part of this architecture worth watching.
        print(f"  rejected: {reason}")
    if payload.get("not_analysed"):
        print(f"  NOT ANALYSED: {payload['not_analysed']} — these criteria have no result")
    if payload.get("envelope") is None:
        print(f"  NO ENVELOPE — {payload.get('envelope_error', 'unknown reason')}")
    elif out_file is not None:
        print(f"  envelope -> {out_file.relative_to(REPO_ROOT)}")


def _resume_demo(candidate: str, case_id: str, stop_after: float, verbose: bool) -> bool:
    """**LAMB-01: a run that runs out of wall clock finishes in a second invocation.**

    Two invocations of the same `run_id`, against one durable store:

    1. The first carries a wall-clock ceiling below the work required. It stops, packages what it
       has, and reports which ceiling stopped it. **The criteria it skipped are deliberately not
       checkpointed** — they are the next invocation's work, and recording them as done would make
       the first invocation's ceiling permanent.
    2. The second carries the normal ceiling. It restores the nodes the first completed and runs
       only what is outstanding.

    A SAM container is a real process boundary — a different process, a different container — so
    the only thing connecting the two is what was written to PostgreSQL. That is exactly the shape
    of a Lambda timeout, where the platform retries the invocation and everything in memory is gone.

    **What "0 duplicate paid calls" means here, and it is subtler than it looks.** The gateway's
    call store would *replay* a re-executed call rather than re-buying it. But a checkpointed node
    is never re-executed at all, so the second invocation never asks — the replay count is
    typically **zero and that is the good outcome**, not a broken store. The number that shows the
    property is the total paid across both invocations against what one uninterrupted run costs.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"run_lamb01_{candidate.replace('-', '')}_{stamp}"
    function = FUNCTIONS[candidate]
    event = {"case_id": case_id, "candidate": candidate, "run_id": run_id}
    dsn = os.environ.get("IREPORTS_STATE_DSN") or DEFAULT_CONTAINER_DSN

    print(f"\n=== LAMB-01 · {candidate} · {run_id} ===")

    print(f"\ninvocation 1 — wall-clock ceiling {stop_after}s, below the work required")
    first = invoke(
        function,
        event,
        write_env_vars(
            {"IREPORTS_STATE_DSN": dsn, "IREPORTS_MAX_WALL_CLOCK_SECONDS": str(stop_after)}
        ),
        verbose=verbose,
    )
    _report(first, None)

    print("\ninvocation 2 — same run id, normal ceiling, new container")
    second = invoke(
        function,
        event,
        # No ceiling override: this invocation is meant to finish.
        write_env_vars({"IREPORTS_STATE_DSN": dsn}),
        verbose=verbose,
    )
    out_file = None
    if second.get("envelope") is not None:
        out_file = OUT_DIR / f"{candidate}-{run_id}.json"
        out_file.write_text(json.dumps(second, indent=2) + "\n")
    _report(second, out_file)

    return _report_lamb01(candidate, first, second)


def _report_lamb01(candidate: str, first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Read the two payloads as the LAMB-01 acceptance, and say plainly whether it holds."""
    if not (first.get("durable") and second.get("durable")):
        print("\n  FAIL — the function ran without a durable store, so there was nothing to resume")
        return False

    skipped = [c for c in first.get("criteria", []) if c.get("status") == "skipped_budget"]
    resumed = second.get("resumed_nodes", [])
    paid_1 = (first.get("model_calls") or {}).get("paid", 0)
    paid_2 = (second.get("model_calls") or {}).get("paid", 0)
    replayed_2 = (second.get("model_calls") or {}).get("replayed", 0)
    # One uninterrupted run pays for each criterion once, plus synthesis. Bounded retries make
    # this a floor rather than an equality, which is why it is printed rather than asserted.
    baseline = len(first.get("criteria", [])) + 1

    print(f"\n  {candidate} · LAMB-01")
    stopped_on = first.get("budget_breach") or "nothing — see below"
    print(f"    invocation 1 stopped on ...... {stopped_on}")
    print(f"    criteria it did not attempt .. {len(skipped)}")
    print(f"    invocation 2 restored ........ {len(resumed)} node(s): {resumed}")
    print(f"    paid model calls ............. {paid_1} + {paid_2} = {paid_1 + paid_2}")
    print(f"    one uninterrupted run costs .. ~{baseline} (criteria + synthesis)")
    print(f"    calls replayed by the store .. {replayed_2}  (0 is expected — see the docstring)")

    problems = []
    if not first.get("incomplete_due_to_budget"):
        problems.append(
            f"invocation 1 was not truncated — raise --stop-after above 0 or lower it below the "
            f"{first.get('wall_seconds')}s this run took"
        )
    if not skipped:
        problems.append("invocation 1 skipped no criteria, so there was nothing to leave behind")
    if not resumed:
        problems.append("invocation 2 restored nothing — the checkpoint did not cross the boundary")
    if second.get("incomplete_due_to_budget"):
        problems.append("invocation 2 was itself truncated, so the run never finished")
    if second.get("envelope") is None:
        problems.append("invocation 2 produced no envelope")
    if paid_1 + paid_2 > baseline + len(first.get("criteria", [])):
        problems.append(
            f"{paid_1 + paid_2} paid calls against ~{baseline} for one run — work was re-bought"
        )

    if problems:
        for problem in problems:
            print(f"    FAIL: {problem}")
        return False
    print("    PASS — the second invocation finished what the first started, and paid only for it")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", default="AMI-SYN-FIN-001")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print raw sam and container output, including the Lambda START/END/REPORT records",
    )
    parser.add_argument(
        "--candidate",
        choices=sorted(FUNCTIONS),
        action="append",
        help="run one orchestrator instead of both; repeatable",
    )
    parser.add_argument(
        "--resume-demo",
        action="store_true",
        help=(
            "LAMB-01: invoke twice with one run id, the first with a wall-clock ceiling below "
            "the work required. Needs the compose PostgreSQL. Costs roughly one full run."
        ),
    )
    parser.add_argument(
        "--stop-after",
        type=float,
        default=10.0,
        help=(
            "wall-clock ceiling for the first --resume-demo invocation, in seconds. It must be "
            "BELOW one specialist's duration (~15-25s on a thinking tier), not above: the first "
            "MAX_PARALLEL criteria start at t=0 and always run, and the ones queued behind them "
            "are reached at t of about one call. Set it above that and nothing is left for "
            "invocation 2."
        ),
    )
    args = parser.parse_args()

    if not BUILD_DIR.exists():
        raise SystemExit(
            f"{BUILD_DIR.relative_to(REPO_ROOT)} does not exist. Run:\n"
            "  uv run python spikes/lambda_demo/build.py\n"
            "  cd spikes/lambda_demo && sam build --use-container --parallel"
        )

    preflight(require_postgres=args.resume_demo)
    candidates = args.candidate or sorted(FUNCTIONS)
    OUT_DIR.mkdir(exist_ok=True)

    if args.resume_demo:
        results = [
            _resume_demo(candidate, args.case_id, args.stop_after, args.verbose)
            for candidate in candidates
        ]
        print("\n" + "-" * 72)
        for candidate, ok in zip(candidates, results, strict=True):
            print(f"{candidate:<14}{'PASS' if ok else 'FAIL'}")
        return 0 if all(results) else 1

    env_vars = write_env_vars()

    payloads: list[dict[str, Any]] = []
    for candidate in candidates:
        print(f"invoking {FUNCTIONS[candidate]} ({candidate}) — real model calls, this takes ~20s")
        payload = invoke(
            FUNCTIONS[candidate],
            {"case_id": args.case_id, "candidate": candidate},
            env_vars,
            verbose=args.verbose,
        )
        out_file = None
        if payload.get("envelope") is not None:
            out_file = OUT_DIR / f"{candidate}-{payload['run_id']}.json"
            out_file.write_text(json.dumps(payload, indent=2) + "\n")
        _report(payload, out_file)
        payloads.append(payload)

    print("\n" + "-" * 72)
    print(f"{'candidate':<14}{'wall':>8}{'tokens':>10}{'findings':>10}  envelope")
    for payload in payloads:
        ok = "OK" if payload.get("envelope") is not None else "none"
        print(
            f"{payload['candidate']:<14}"
            f"{payload['wall_seconds']:>7}s"
            f"{payload['tokens']['total']:>10,}"
            f"{payload['findings']:>10}  {ok}"
        )

    # Two orchestrators are not expected to find the same things — they are two runs of a
    # probabilistic analysis, not two evaluations of a function. What is expected is that both
    # produce a *valid envelope of citation-checked proposals*, which is the claim being made.
    if any(p.get("envelope") is None for p in payloads):
        print("\nAt least one run produced no envelope. See the rejection lines above for why.")
        return 1
    print(f"\nWrote {len(payloads)} envelope(s) to {OUT_DIR.relative_to(REPO_ROOT)}/ — open one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
