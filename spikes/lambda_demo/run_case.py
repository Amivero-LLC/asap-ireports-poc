"""Run one synthetic case through both Lambdas and write the envelopes where you can open them.

    docker compose -f infrastructure/docker/compose.yaml up -d    # not needed; no Postgres here
    uv run python spikes/lambda_demo/build.py
    cd spikes/lambda_demo && sam build --use-container --parallel && cd -
    uv run --env-file .env python spikes/lambda_demo/run_case.py

The last command is the point of the whole spike. It invokes both functions under SAM local, and
each writes `out/<candidate>-<run_id>.json` — a validated `ASAPEnvelope` plus the run's accounting.
Open one. That file is what the architecture produces.

**Real model calls, real money.** A full run is roughly 22k tokens across six thinking-tier calls
(three specialists x two candidates, plus any bounded retry). Nothing in CI runs this, and nothing
should: `--candidate` narrows it to one orchestrator when you only need to see it work.

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
import subprocess
import sys
import tempfile
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
ENV_EXCLUDE = frozenset(
    {
        # Postgres for the bake-off's crash/resume legs. This demo has no checkpointer, and a DSN
        # pointing at localhost would not resolve from inside the container anyway.
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


def _env_vars_payload() -> dict[str, dict[str, str]]:
    """The `--env-vars` document: every declared gateway variable, per function.

    Empty values are dropped rather than forwarded as `""`. `GatewayConfig.validate()` treats an
    empty string as absent and names the missing variable, which is the error you want; an empty
    string forwarded into the container produces the same failure one layer further away.
    """
    declared = _declared_variables()
    candidates = {
        key: value
        for key, value in os.environ.items()
        if key.startswith(ENV_PREFIXES) and key not in ENV_EXCLUDE and value.strip()
    }
    if not candidates:
        raise SystemExit(
            "no IREPORTS_* variables are set, so the gateway has nothing to authenticate with.\n"
            "Run this as:  uv run --env-file .env python spikes/lambda_demo/run_case.py"
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


def write_env_vars() -> Path:
    ENV_VARS_FILE.write_text(json.dumps(_env_vars_payload(), indent=2) + "\n")
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


def invoke(function: str, event: dict[str, Any], env_vars: Path) -> dict[str, Any]:
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

    if result.returncode != 0 and not result.stdout.strip():
        raise SystemExit(f"sam local invoke {function} failed:\n{result.stderr[-2000:]}")
    return _payload_from(result.stdout)


def _report(payload: dict[str, Any], out_file: Path | None) -> None:
    candidate = payload["candidate"]
    tokens = payload.get("tokens", {})
    print(
        f"\n{candidate:<12} {payload['wall_seconds']}s  "
        f"{tokens.get('total', 0):,} tokens  "
        f"{payload['findings']} findings"
    )
    for criterion in payload.get("criteria", []):
        print(
            f"  {criterion['criterion_id']:<14} "
            f"{criterion['findings']} findings, {criterion['rejected']} rejected"
        )
    synthesis = payload.get("synthesis")
    if synthesis:
        if not synthesis["ran"]:
            print("  synthesis   skipped — fewer than two findings to reason across")
        else:
            print(f"  synthesis    {synthesis['findings']} cross-criterion findings")
        for overlap in synthesis["overlaps"]:
            # The cheapest useful output in the whole run: set arithmetic, no model call.
            print(
                f"    {overlap['evidence_id']} carries findings under "
                f"{len(overlap['criterion_ids'])} criteria: {overlap['criterion_ids']}"
            )

    for reason in payload.get("rejected", []):
        # Not an error log. Every line here is the deterministic shell refusing something the
        # model produced, which is the part of this architecture worth watching.
        print(f"  rejected: {reason}")
    if payload.get("envelope") is None:
        print(f"  NO ENVELOPE — {payload.get('envelope_error', 'unknown reason')}")
    elif out_file is not None:
        print(f"  envelope -> {out_file.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", default="AMI-SYN-FIN-001")
    parser.add_argument(
        "--candidate",
        choices=sorted(FUNCTIONS),
        action="append",
        help="run one orchestrator instead of both; repeatable",
    )
    args = parser.parse_args()

    if not BUILD_DIR.exists():
        raise SystemExit(
            f"{BUILD_DIR.relative_to(REPO_ROOT)} does not exist. Run:\n"
            "  uv run python spikes/lambda_demo/build.py\n"
            "  cd spikes/lambda_demo && sam build --use-container --parallel"
        )

    candidates = args.candidate or sorted(FUNCTIONS)
    env_vars = write_env_vars()
    OUT_DIR.mkdir(exist_ok=True)

    payloads: list[dict[str, Any]] = []
    for candidate in candidates:
        print(f"invoking {FUNCTIONS[candidate]} ({candidate}) — real model calls, this takes ~20s")
        payload = invoke(
            FUNCTIONS[candidate],
            {"case_id": args.case_id, "candidate": candidate},
            env_vars,
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
