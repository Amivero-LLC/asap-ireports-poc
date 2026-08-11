"""The Milestone 1c scorecard, as a validated contract instance.

`harness/scorecard.py` argues that the bake-off's output is a *comparison*, and that a comparison
assembled by hand from three authors' notes is not one. This module is where that argument is
cashed: importing it constructs a `Scorecard`, which fails at import if a candidate is missing a
leg, if a judged score has no rationale, or if the recommendation does not carry a recorded reason
for every candidate it beat.

    uv run python spikes/bakeoff_scorecard.py    # writes docs/handoff/orchestration-scorecard.json

**Measured** fields come from `spikes/measure.py` (2026-08-11) and are reproducible.
**Observed** fields come from `uv run pytest spikes`. **Judged** fields are one engineer's
assessment after building all three, and are marked as such so a reader can see which numbers are
facts and which are opinions. The narrative version, with the evidence behind each judgement, is
`docs/handoff/orchestration-scorecard.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ireports_spike_harness.scorecard import (
    CandidateScore,
    JudgedQualities,
    Judgement,
    LegOutcome,
    LegScore,
    MeasuredFootprint,
    Scorecard,
)

REPO = Path(__file__).resolve().parent.parent
OUTPUT = REPO / "docs" / "handoff" / "orchestration-scorecard.json"

SCORED_ON = "2026-08-11"


def _legs(*details: str) -> list[LegScore]:
    """All four legs passed for all three candidates, so only the detail differs."""
    names = (
        "1-durable-resume",
        "2-human-interrupt",
        "3-timeout-survival",
        "4-bounded-fanout",
    )
    return [
        LegScore(leg=name, outcome=LegOutcome.PASSED, detail=detail)
        for name, detail in zip(names, details, strict=True)
    ]


HAND_ROLLED = CandidateScore(
    candidate="hand-rolled",
    module="spike_handrolled",
    framework_version="none — Python 3.12+ standard library over psycopg 3.2",
    legs=_legs(
        "Crashed after `commit_node`; the completed specialist ran exactly once across the crash.",
        "Paused in `awaiting_human_review`, took a disposition out of band, delivered on resume.",
        "Bounded retry (MAX_MODEL_ATTEMPTS=2) absorbed the one-shot timeout in the same process.",
        "ThreadPoolExecutor bounded by `max_parallel_specialists`; join kept both authorities.",
    ),
    footprint=MeasuredFootprint(
        framework_lines_of_code=195,
        serialized_state_bytes=16_346,
        distributions=0,
        installed_megabytes=0,
        known_vulnerabilities=0,
    ),
    judged=JudgedQualities(
        budget_and_allowlist_enforcement=Judgement.ADEQUATE,
        budget_and_allowlist_rationale=(
            "Nothing helps and nothing gets in the way. The retry bound is four lines and "
            "trivially auditable; token budgets, tool allowlists, cancellation, and no-progress "
            "detection are entirely unwritten. Rated on what exists, not on what is possible."
        ),
        state_inspectability=Judgement.ADEQUATE,
        state_inspectability_rationale=(
            "Inspection is the best of the three — one JSONB row per run, legible in a single "
            "SELECT, keyed by node id. Replay is the worst: there is no history, so 'what did "
            "this run look like three nodes ago' has no answer at all."
        ),
        test_determinism=Judgement.GOOD,
        test_determinism_rationale=(
            "Identical output across every run of the suite. The only nondeterminism is the "
            "wall-clock interleaving of the two specialist threads, which is a property of the "
            "scenario rather than of the candidate — and which the duplicate probe measures "
            "rather than suffers."
        ),
        developer_comprehension=Judgement.GOOD,
        developer_comprehension_rationale=(
            "One idea repeated: skip what is committed, run what is not, commit immediately. "
            "195 lines readable end to end in a sitting, with no concept that is not visible in "
            "the file. What is confusing is not the code but the absence — a reader has to keep "
            "the 'still owes' list in their head to judge it fairly."
        ),
    ),
    notes=[
        "195 lines is a floor, not a total. No-progress and duplicate-query detection, "
        "cancellation, tool allowlists, budget accounting, OTel spans, and any scheduler or "
        "supervisor are all absent and all genuinely needed for Milestone 2.",
        "Stores full finding JSON at three stages, so each finding is serialized about three "
        "times. A known inefficiency rather than an intrinsic cost (blueprint §8.2).",
        "Re-executes an in-flight sibling's model call in 12 of 24 mid-fan-out crashes. Correct "
        "at-least-once behaviour, and a real cost; shared with LangGraph.",
    ],
)


LANGGRAPH = CandidateScore(
    candidate="langgraph",
    module="spike_langgraph",
    framework_version="langgraph 1.2.10, langgraph-checkpoint-postgres 3.1.2, "
    "langgraph-checkpoint 4.2.0, langchain-core 1.5.3, langsmith 0.10.17",
    legs=_legs(
        "Crashed inside `put_writes` after the row committed; the completed task's pending "
        "writes were applied on resume and the node did not re-execute.",
        "`interrupt()` suspended the run; `Command(resume=...)` in a later process delivered.",
        "Declarative per-node `RetryPolicy(max_attempts=2, retry_on=(ModelTimeoutError,))`.",
        "One super-step ran both specialists; the `operator.add` reducer joined without "
        "collapsing the two authorities.",
    ),
    footprint=MeasuredFootprint(
        framework_lines_of_code=266,
        serialized_state_bytes=16_115,
        distributions=31,
        installed_megabytes=18,
        known_vulnerabilities=0,
    ),
    judged=JudgedQualities(
        budget_and_allowlist_enforcement=Judgement.ADEQUATE,
        budget_and_allowlist_rationale=(
            "Retry is declarative, per-node, and was exercised by leg 3. `recursion_limit` and "
            "per-node `timeout` are documented bounds that this spike did **not** exercise, so "
            "they are not credited. Token budgets and tool allowlists are not framework concepts "
            "in any candidate. Rated the same as the others because what separates them here is "
            "ergonomics, not capability."
        ),
        state_inspectability=Judgement.GOOD,
        state_inspectability_rationale=(
            "The only candidate with real replay: `get_state`, `get_state_history`, and a "
            "checkpoint per super-step. The cost is that raw inspection is much harder — state "
            "is spread across three tables as msgpack in BYTEA, which is why measuring one "
            "checkpoint's size took 57 lines here against 3 elsewhere. Good through the API, "
            "poor through psql."
        ),
        test_determinism=Judgement.GOOD,
        test_determinism_rationale=(
            "Deterministic output across every run, helped by the harness's frozen clock and "
            "derived ids. Persistence runs on a background executor, so *timing* varies — which "
            "showed up as an early 2-of-6 result that would not reproduce in 30 further trials. "
            "That is a caution about how much any single timing run is worth, not a defect."
        ),
        developer_comprehension=Judgement.ADEQUATE,
        developer_comprehension_rationale=(
            "The largest conceptual surface of the three: super-steps, channels, reducers, "
            "pending writes, task ids, and three durability modes are all load-bearing when "
            "reasoning about a crash. Worse, the two most consequential behaviours are defaults "
            "that are invisible in the code — a graph reads identically whether persistence is "
            "synchronous and whether deserialization is allowlisted. Against that: the graph "
            "definition itself is the clearest of the three, and the documentation is the best."
        ),
    ),
    notes=[
        "Persistence cost two lines. This is the dimension ADR-012 predicted would separate the "
        "candidates, and it did: 2 against Strands' 166-line SessionRepository and the "
        "hand-rolled candidate's 56-line checkpoint store.",
        "Net orchestration wiring is ~192 lines: 57 of the 266 are the byte-measuring query that "
        "exists only for this scorecard, and 17 are the --crash-after hook.",
        "Two defaults are wrong for this architecture and are now pinned in code with tests: "
        "`durability` defaults to `async` (we set `sync`), and checkpoint deserialization "
        "defaults to permissive — the library's own source says any Python callable stored in "
        "checkpoint data will be imported and executed on load.",
        "Retains every super-step: 37,033 bytes for the run against a 16,115-byte latest "
        "checkpoint. Real feature, real growth, no retention policy attached (Q-09).",
        "`langsmith` is a mandatory transitive dependency. Pinned closed via "
        "`langsmith.configure(enabled=False)` and proven closed with a negative control that "
        "shows an unpinned run POSTs ~90 KB of graph state — including finding text — to "
        "api.smith.langchain.com and still succeeds, because the failure is swallowed.",
        "Re-executes an in-flight sibling's model call in 11 of 24 mid-fan-out crashes. Shared "
        "with the hand-rolled candidate; the measurement that proved the window is universal.",
    ],
)


STRANDS = CandidateScore(
    candidate="strands",
    module="spike_strands",
    framework_version="strands-agents 1.51.0",
    legs=_legs(
        "Crashed inside `update_multi_agent` after the row committed; no completed node "
        "re-executed, settling the landscape scan's unconfirmed conversation-restore claim.",
        "`Interrupt` suspended the graph; the disposition returned as an `interruptResponse`.",
        "Recovered on the harness's second invocation; the candidate declares no retry policy.",
        "Strands scheduled the parallel batch; the join preserved both authorities.",
    ),
    footprint=MeasuredFootprint(
        framework_lines_of_code=373,
        serialized_state_bytes=23_739,
        distributions=42,
        installed_megabytes=47,
        known_vulnerabilities=0,
    ),
    judged=JudgedQualities(
        budget_and_allowlist_enforcement=Judgement.ADEQUATE,
        budget_and_allowlist_rationale=(
            "No budget or allowlist primitive was exercised, and this candidate declares no "
            "retry policy at all — leg 3 passed because the harness re-invoked the process. "
            "`Graph` owning run status also means the domain state machine is not enforced here, "
            "which is a control the hand-rolled candidate does apply."
        ),
        state_inspectability=Judgement.ADEQUATE,
        state_inspectability_rationale=(
            "One JSONB row, so inspection is structurally easy — but the payload is a transcript, "
            "and each node's typed output sits inside an assistant message body as escaped JSON. "
            "A human reading the row sees findings through two layers of encoding. No replay."
        ),
        test_determinism=Judgement.GOOD,
        test_determinism_rationale=(
            "The most deterministic of the three in practice, and for a reason that is not to "
            "its credit: our synchronous node bodies stop its asyncio tasks from interleaving, so "
            "there is no concurrency for timing to vary. With genuinely async model calls this "
            "would look like the other two."
        ),
        developer_comprehension=Judgement.ADEQUATE,
        developer_comprehension_rationale=(
            "The graph model itself is the simplest to read. What costs a reader time is the "
            "persistence: `SessionRepository` requires session, agent, and message CRUD that a "
            "graph of deterministic nodes never calls, so most of the largest file is dead "
            "weight, and the AgentResult-shaped state container is not obvious until the "
            "encode/decode tax is hit."
        ),
    ),
    notes=[
        "The PostgreSQL SessionRepository is ours to build and is the largest file in the "
        "candidate — 166 of 373 lines, most of it never called.",
        "State is conversation-shaped: a node's durable result must be an `AgentResult`, which "
        "persists only `message` and `stop_reason`, so typed contracts are flattened into a "
        "message body and re-validated on the way out. This is why its checkpoint is 47% larger "
        "than LangGraph's for identical content.",
        "botocore dominates the footprint — the 1b scan measured it at 20.1 MB — pulled in "
        "whether or not a run touches AWS.",
        "Scores 0 of 24 on the duplicate-call probe, which is an artifact of our synchronous node "
        "bodies and must not be read as a durability property. Confirmed by LangGraph, which "
        "does interleave and does show the window.",
    ],
)


SCORECARD = Scorecard(
    scored_on=SCORED_ON,
    candidates=[HAND_ROLLED, LANGGRAPH, STRANDS],
    recommendation="langgraph",
    recommendation_rationale=(
        "All three pass all four legs, so this is not a correctness decision. It is a decision "
        "about which costs the program should carry for the life of the system.\n\n"
        "LangGraph is recommended on four grounds. First, the thing this milestone existed to "
        "de-risk — durable checkpointing over PostgreSQL — cost two lines, against 56 for the "
        "hand-rolled store and 166 for the SessionRepository Strands does not ship; and its "
        "durability is per-task inside a super-step, finer-grained than either alternative. "
        "Second, once the 57 lines of scorecard-only instrumentation and the 17-line crash hook "
        "are set aside, its orchestration wiring is ~192 lines — below the hand-rolled floor of "
        "195 — while additionally providing scheduling, a native interrupt, and declarative "
        "retry. Third, it is the only candidate with a written semver commitment (1.0 ACTIVE "
        "until 2.0, majors at least 6-12 months apart, a year of maintenance after), which is "
        "the single most valuable property for a program that must pin and defend versions "
        "through an ATO. Fourth, its costs are real, bounded, and now controlled rather than "
        "argued about: both wrong defaults are pinned in code with tests, and the mandatory "
        "LangSmith client is pinned closed and proven closed with a negative control.\n\n"
        "Two qualifications the program should carry forward with the recommendation. Cold start "
        "and packaging under SAM local have NOT been measured for any candidate, and that is the "
        "one measurement most likely to reopen this — 31 distributions and 18 MB is either "
        "irrelevant or decisive depending on what it does to a Lambda cold start. And the "
        "hand-rolled candidate is a genuine runner-up rather than a strawman: if the program "
        "refuses the dependency surface, 195 lines that pass the same four legs is a defensible "
        "answer, with a known and growing maintenance ledger attached."
    ),
    why_not_the_others={
        "hand-rolled": (
            "Not rejected on the measured evidence, which is excellent: all four legs, 195 "
            "lines, zero added distributions, zero advisory surface, and the most legible state "
            "of the three. Rejected on the ledger behind the 195. No-progress detection, "
            "duplicate-query detection, cancellation, tool allowlists, budget accounting, OTel "
            "spans, replay, and a scheduler are all absent and all needed, and every one of them "
            "is something this program would own and maintain forever rather than inherit. The "
            "195 is a floor that grows; LangGraph's ~192 of wiring is much closer to a total for "
            "the same scope. Retained as the fallback if the dependency surface is refused, and "
            "as the standing check that a framework is earning its place."
        ),
        "strands": (
            "Dominated by LangGraph on every measured dimension: 373 lines against 266 (166 of "
            "them a SessionRepository whose interface is mostly unused), a 23,739-byte "
            "checkpoint against 16,115 for identical content, and 42 distributions / 47.3 MB "
            "against 31 / 18.0 MB. Its distinguishing asset is real — AWS alignment, documented "
            "Lambda packaging, a published layer ARN, which matter to a GovCloud target — but it "
            "does not offset that spread, and AWS publishes prescriptive guidance for LangGraph "
            "on Lambda as well. The structural objection is that its state container is a "
            "transcript, so a workflow carrying typed contract records pays a serialize/parse "
            "tax at every node boundary; that is a poor fit for an architecture whose central "
            "discipline is typed, citable, validated records. Retained, and worth revisiting if "
            "the SAM cold-start measurement favours it or if the program mandates AWS-native "
            "agent tooling."
        ),
    },
)


if __name__ == "__main__":
    OUTPUT.write_text(SCORECARD.model_dump_json(indent=2) + "\n")
    payload = json.loads(OUTPUT.read_text())
    print(f"wrote {OUTPUT.relative_to(REPO)}: {len(payload['candidates'])} candidates")
    for candidate in SCORECARD.candidates:
        print(f"  {candidate.candidate:12s} {candidate.legs_passed}/4 legs")
    print(f"  recommendation: {SCORECARD.recommendation}")
