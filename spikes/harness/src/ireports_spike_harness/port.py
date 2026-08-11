"""The orchestration port, and the process contract every candidate implements.

ADR-012: "The orchestration package is defined by a port so nodes depend on our interface, not
the framework's." This module is that port, pulled forward into the spike so that the interface
is settled *before* any framework shapes it.

**Why a subprocess CLI and not just a Python protocol.** Spike leg 1 is "durable checkpoint and
resume in a **separate process** after the first process exits." An in-process `resume()` call
cannot demonstrate that: object graphs, connection pools, and framework-level caches all survive
in memory and would let a candidate pass while depending on state that a real Lambda invocation
or a restarted worker would not have. So the port has two faces:

- `Orchestrator` — the Python protocol a candidate implements.
- A CLI contract — how the conformance suite drives it across a genuine process boundary.

`--crash-after` exits with `os._exit`, which skips `finally` blocks, atexit handlers, and
destructors. A graceful shutdown would let a framework flush state on the way out, which is
precisely the behaviour a crash must not be allowed to rely on.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ireports_domain import ASAPEnvelope, HumanDisposition, ProposedFinding, RunStatus


@dataclass(frozen=True)
class RunOutcome:
    """What a candidate reports after `start` or `resume`."""

    run_id: str
    status: RunStatus
    proposed_findings: tuple[ProposedFinding, ...] = ()
    envelope: ASAPEnvelope | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "status": self.status.value,
                "proposed_findings": [
                    json.loads(f.model_dump_json()) for f in self.proposed_findings
                ],
                "envelope": (
                    json.loads(self.envelope.model_dump_json())
                    if self.envelope is not None
                    else None
                ),
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> RunOutcome:
        data = json.loads(raw)
        return cls(
            run_id=data["run_id"],
            status=RunStatus(data["status"]),
            proposed_findings=tuple(
                ProposedFinding.model_validate(f) for f in data["proposed_findings"]
            ),
            envelope=(
                ASAPEnvelope.model_validate(data["envelope"])
                if data["envelope"] is not None
                else None
            ),
        )


@runtime_checkable
class Orchestrator(Protocol):
    """What each candidate must provide.

    Deliberately small. Anything a framework needs beyond this — a checkpointer, a session
    manager, a state schema — is the framework's cost, and counting that cost is the point.
    """

    name: str

    def start(self, run_id: str, crash_after: str | None = None) -> RunOutcome:
        """Run until the human-review interrupt, then stop and report proposals.

        `crash_after` names a node after which the process must die hard. Honouring it is the
        candidate's responsibility because only the candidate knows where its node boundaries
        are — and where the boundary sits relative to its checkpoint write is exactly what
        leg 1 measures.
        """
        ...

    def resume(self, run_id: str, dispositions: tuple[HumanDisposition, ...]) -> RunOutcome:
        """Rehydrate from durable state and carry the run to a delivered envelope."""
        ...


def die_hard() -> None:
    """Simulate a crash: no unwinding, no flush, no cleanup."""
    sys.stdout.flush()
    os._exit(9)


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------

CRASH_EXIT_CODE = 9


def main(orchestrator: Orchestrator, argv: list[str] | None = None) -> int:
    """Standard entry point. Each candidate's `__main__` calls this and nothing else.

    Keeping argument handling here means no candidate can accidentally advantage itself with a
    different invocation shape, and the conformance suite has exactly one contract to drive.
    """
    parser = argparse.ArgumentParser(description=f"{orchestrator.name} orchestration spike")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="run until the human-review interrupt")
    start.add_argument("--run-id", required=True)
    start.add_argument(
        "--crash-after",
        default=None,
        help="node id after which the process must die hard (no unwinding)",
    )

    resume = sub.add_parser("resume", help="resume from durable state and deliver")
    resume.add_argument("--run-id", required=True)
    resume.add_argument(
        "--dispositions",
        default="[]",
        help="JSON array of HumanDisposition objects recorded out of band",
    )

    args = parser.parse_args(argv)

    if args.command == "start":
        outcome = orchestrator.start(args.run_id, crash_after=args.crash_after)
    else:
        dispositions = tuple(
            HumanDisposition.model_validate(d) for d in json.loads(args.dispositions)
        )
        outcome = orchestrator.resume(args.run_id, dispositions)

    print(outcome.to_json())
    return 0


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def crashed(self) -> bool:
        return self.returncode == CRASH_EXIT_CODE

    def outcome(self) -> RunOutcome:
        if self.returncode != 0:
            raise RuntimeError(f"candidate exited {self.returncode}\nstderr:\n{self.stderr}")
        return RunOutcome.from_json(self.stdout.strip().splitlines()[-1])


def invoke(module: str, *args: str, timeout: float = 120.0) -> ProcessResult:
    """Run a candidate in a genuinely separate process."""
    completed = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return ProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
