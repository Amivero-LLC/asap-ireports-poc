---
phase: 01-close-the-architecture-package
reviewed: 2026-08-11T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - docs/handoff/component-architecture.md
  - docs/handoff/contracts.md
  - packages/domain/src/ireports_domain/__init__.py
  - packages/domain/src/ireports_domain/specialist.py
  - schemas/specialist-result.schema.json
  - tests/architecture/test_build_state_table.py
  - tests/contract/test_specialist_result.py
findings:
  critical: 3
  warning: 16
  info: 6
  total: 25
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-08-11
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the CONT-01 contract (`SpecialistResult` / `SpecialistCriterion`, its generated schema
and contract tests), the ARCH-01 component-architecture write-up, the contracts handoff update,
and the D-11 build-state enforcement test.

Verified against the running repository rather than taken on trust: `pytest tests/contract` is
91 passed, the full suite is 126 passed / 8 skipped, `generate_schemas.py --check` reports 14
contracts, `bandit` reports 0 high / 0 medium / 3 low, `mypy --strict packages tests scripts`
is clean, all thirteen test names cited in `contracts.md` §2/§4 exist, all fifty build-state rows
parse with zero problems today, all ADR and requirement ids cited in `component-architecture.md`
resolve, and `docs/OPEN-QUESTIONS.md` does carry exactly three GATE questions. `CLAUDE.md` was
correctly refreshed (14 contracts, 126 tests, seven handoff documents) — the ARCH-04 claim holds.

The prose is unusually honest about its own gaps, and that is real. What it is not honest about is
the machinery it points at. Three defects are load-bearing:

1. `check_rows` implements nine categories of problem and only four of them are asserted by any
   test. Over half of the D-11 guard is inert — it computes a violation and throws it away.
2. The guard's `PLANNED` rows are keyed on *directories*, eight rows sharing `packages/orchestration/`,
   and `test_all_four_markers_are_present` asserts marker-set *equality*. The first commit of
   Phase 2 turns eight rows red simultaneously, and the doc's own instruction ("flip that row to
   BUILT in the same commit") then demands seven false `BUILT` claims. At the end of Phase 3 the
   equality assertion cannot be satisfied without a permanently false `PLANNED` row.
3. `SpecialistResult.findings` is a mutable list on a `frozen=True` model. The cross-run/cross-case/
   cross-criterion invariant that `_findings_belong_to_this_criterion` exists to enforce can be
   defeated with one `.append()` after construction, and `contracts.md` §2 asserts frozen-ness as
   the ADR-011 mechanism.

Beyond those, a cluster of documentation-accuracy defects: a stale verification figure for a gate
that currently *fails*, two diagrams that visually contradict the document's own non-negotiable
claims (the review-gate bypass edge and the "never a model id" edge), a CI gate that does not
exist, and the only published JSON Schema in the repo that leaks internal `.planning/` decision
ids to external consumers.

No security vulnerability in the conventional sense was found. The path handling in
`test_build_state_table.py` is genuinely well contained (T-01-10) and the ADR-014 no-aggregate-score
guard does now cover `SpecialistResult` via `ROOT_CONTRACTS`. No decision-support-boundary
violation was found in the new contract.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Five of the nine `check_rows` violations are computed and then silently discarded

**File:** `tests/architecture/test_build_state_table.py:95-201`
**Issue:** `check_rows` returns a list of problem strings, but no test asserts `problems == []`.
Each test instead filters by substring:

| Test | Filter | Categories caught |
|---|---|---|
| `test_every_built_row_resolves` (169) | `"BUILT path" in p` | BUILT unsafe path, BUILT outside root, BUILT unresolved |
| `test_no_planned_row_already_exists` (176) | `"already exists" in p` | PLANNED path exists |
| `test_every_marker_is_one_of_the_four` (183) | `"is not one of" in p` | unknown marker |
| `test_designed_not_built_rows_name_a_requirement` (197) | `"do not name a requirement id" in p` | missing requirement id |

Nothing matches these five, so they can never fail a test run:

- `line N: PLANNED path {p!r} is absolute or contains '..'` (126-129)
- `line N: PLANNED path {p!r} resolves outside the repo root` (131-135)
- `line N: PLANNED row's notes do not name a phase (expected 'Phase N')` (141-145)
- `line N: {marker} row's path must be an em dash, got {path!r}` (148-152)
- `line N: {marker} row has no notes` (152-153)

Confirmed empirically: a `DESIGNED-NOT-BUILT` row with a real path instead of `—`, or a `PLANNED`
row whose notes say only "Someday", produces a problem string that no test in the file ever looks
at. `component-architecture.md:268` tells the reader "The tables above are enforced by
`tests/architecture/test_build_state_table.py`" — for over half the rules, they are not. This is
dead code masquerading as a guard, in the one artifact the phase delivers to stop state claims from
going stale.

**Fix:** Assert the whole list once, and keep the named tests as documentation of intent by
asserting the specific slice *in addition to* the whole:

```python
def test_the_build_state_table_is_honest() -> None:
    """Every check `check_rows` implements is a check that can fail the suite."""
    problems = check_rows(_load_document_rows(), REPO_ROOT)
    assert not problems, "\n".join(problems)
```

Add that test, and add a negative example to `test_the_check_actually_catches_a_bad_row` for each
of the five orphaned categories (an em-dash violation, an empty-notes row, a phase-less `PLANNED`
row, a `../` `PLANNED` path).

### CR-02: The build-state guard will demand false `BUILT` claims, then become unsatisfiable

**File:** `tests/architecture/test_build_state_table.py:124-146,190-194`; `docs/handoff/component-architecture.md:225-234,243-245,268-272`
**Issue:** Two independent defects that compound.

*Directory granularity.* Eight `PLANNED` rows share the path `packages/orchestration/` (lines
225-234), two share `packages/retrieval/` (231-232), three share `apps/api/` (243-245).
`check_rows` fails a `PLANNED` row when its path *exists*. The first commit of ORCH-01 creates
`packages/orchestration/` — and instantly fails ORCH-02, ORCH-03, ORCH-04, SPEC-01, VAL-02 and the
checkpoint-store row as well, none of which are built. `component-architecture.md:269-271` then
instructs: "that row must be flipped to `BUILT` in the same commit — the test failing at that point
is the intended signal." Following the instruction literally produces six false `BUILT` claims in a
document whose entire premise is that `BUILT` means "the row names a real path that resolves". The
guard built to prevent stale state claims actively rewards making them.

*Marker-set equality.* `test_all_four_markers_are_present` (190-194) asserts
`markers == VALID_MARKERS`, not `VALID_MARKERS <= markers` as its own docstring says ("At least one
row of each marker exists"). When Phase 3 completes and every `PLANNED` row has legitimately become
`BUILT`, this test goes red permanently. The only ways to green it are to keep a false `PLANNED`
row forever or to delete the test.

**Fix:** Give each `PLANNED` row a path with file granularity, so rows fail one at a time —
`packages/orchestration/port.py`, `packages/orchestration/checkpoint.py`,
`packages/orchestration/budgets.py`, and so on. Then relax the equality:

```python
def test_designed_not_built_cannot_be_quietly_dropped() -> None:
    """DESIGNED-NOT-BUILT and NOT OURS must always be represented; PLANNED legitimately empties."""
    markers = {marker for _, marker, _, _, _ in _load_document_rows()}
    assert {"BUILT", "NOT OURS", "DESIGNED-NOT-BUILT"} <= markers, markers
    assert markers <= VALID_MARKERS, markers
```

### CR-03: `SpecialistResult.findings` is mutable in place, defeating the cross-criterion invariant

**File:** `packages/domain/src/ireports_domain/specialist.py:71-116`; `docs/handoff/contracts.md:80-82`
**Issue:** `frozen=True` on `ContractModel` blocks attribute *assignment*; it does not freeze list
contents. `findings: list[ProposedFinding]` is therefore mutable after validation, and
`_findings_belong_to_this_criterion` runs exactly once at construction. Reproduced against the
running package:

```python
r = SpecialistResult(run_id="run_01J9AA", case_id="AMI-SYN-MIX-004", criterion=..., generated_by=..., findings=[])
r.findings.append(finding_from_a_different_run)   # succeeds, no error
len(r.findings)          # 1
r.findings[0].run_id     # 'run_OTHER'
```

A validated `SpecialistResult` for case A can be made to carry a `ProposedFinding` belonging to
case B, run B, and a different criterion, and every guarantee the validator's five branches were
written to provide is gone. In an adjudication artifact, a finding attributed to the wrong case is
the failure mode with the worst consequences.

`contracts.md:80-82` states the mechanism as settled: "**`frozen=True` on every contract.**
ADR-011's 'both versions are retained' only holds if the machine proposal cannot be edited in
place." For any list-valued field that claim is false, and CONT-01 is the first contract to pair a
mutable collection with a cross-field invariant that depends on it.

Mitigation that exists: `SpecialistResult.model_validate(r.model_dump())` does reject the mutated
value, so a checkpoint round-trip with strict deserialization would catch it. Nothing forces that
round-trip while the object is live in the orchestrator between nodes.

**Fix:** Make the collection immutable at the type level so mutation is a `TypeError` rather than a
silent invariant break:

```python
findings: tuple[ProposedFinding, ...] = ()
```

`tuple` serializes to a JSON array identically, `--check` will show no schema drift beyond the
default, and `model_copy(update=...)` remains the documented way to build a variant. If the list
type must stay for ergonomic reasons, add a test that asserts the mutation is caught, and state in
`contracts.md` §2 that frozen-ness does not extend to collection contents.

## Warnings

### WR-01: Duplicate `finding_id`s inside one `SpecialistResult` are accepted

**File:** `packages/domain/src/ireports_domain/specialist.py:73-116`
**Issue:** The validator checks five identity fields per finding but never checks that
`finding_id`s are distinct. `SpecialistResult(findings=[_finding(), _finding()])` validates with
two identical `fnd_01J9AB` entries. This contradicts the established pattern in the same package —
`asap.py:201-203` (`"envelope contains duplicate finding_ids"`) and `disposition.py:211` both
enforce it — and duplicates propagated into a run's finding set would double-count a proposal in
the reviewer's queue.
**Fix:**
```python
finding_ids = [f.finding_id for f in self.findings]
if len(set(finding_ids)) != len(finding_ids):
    raise ValueError("specialist result contains duplicate finding_ids")
```
Add it to the existing `model_validator` before the per-finding loop, with a failing test.

### WR-02: `SpecialistResult` is the only root contract with no timestamp, and ADR-021's log story needs one

**File:** `packages/domain/src/ireports_domain/specialist.py:66-71`
**Issue:** Every other root contract carries a required timestamp — `CaseManifest.created_at`,
`ProposedFinding.proposed_at`, `EvidenceRecord.snapshot_at`, `AuthorityRoutingResult.routed_at`,
`RunManifest.started_at`, `HumanDisposition.reviewed_at`, `ASAPEnvelope.created_at`,
`DeliveryReceipt.delivered_at`. `SpecialistResult` has none.

This is not cosmetic given ADR-021 Consequence 2, which both handoff documents state as the spine's
weakest point: a refused sub-call and a clean criterion produce the same artifact, and "the
distinction lives in the log (`run_id`, `case_id`, the criterion)". Those three fields are not
sufficient to join a log line to an artifact when a criterion is re-run after a crash-and-resume —
which is exactly the scenario ORCH-02 exists for. Two `SpecialistResult`s for the same
(run, case, criterion) are indistinguishable and unorderable.
**Fix:** Add `analyzed_at: UtcDatetime` as a required field, and state in the ADR-021 gap
paragraphs of both documents that the log correlation key is (`run_id`, `case_id`, `criterion_id`,
`analyzed_at`).

### WR-03: Only one of the validator's five branches has a failing test

**File:** `tests/contract/test_specialist_result.py:231-245`; `packages/domain/src/ireports_domain/specialist.py:80-115`
**Issue:** `_findings_belong_to_this_criterion` has five independent raise branches — `run_id`,
`case_id`, `authority.decision_domain`, `authority.policy_pack_id`, `authority.policy_id`,
`authority.criterion_id`. Exactly one (`criterion_id`) has a failing example. The file's own
docstring sets the standard it fails: "A rule with no failing example in its own suite is a rule
that cannot be trusted to have ever run" (line 233-234), echoing
`test_decision_support_boundary.py`. A typo in any of the other four branches — a copy-paste
comparing the wrong field, of which there are five near-identical blocks — would ship green.
**Fix:** Parametrize:
```python
@pytest.mark.parametrize(
    "override, expected",
    [
        ({"run_id": "run_OTHER"}, "run_id"),
        ({"case_id": "AMI-SYN-OTHER-1"}, "case_id"),
        ({"authority": _authority(decision_domain=DecisionDomain.SUITABILITY)}, "decision_domain"),
        ({"authority": _authority(policy_pack_id="cfr731-current")}, "policy_pack_id"),
        ({"authority": _authority(policy_id="5-CFR-731")}, "policy_id"),
        ({"authority": _authority(criterion_id="GUIDELINE-C")}, "criterion_id"),
    ],
)
def test_a_finding_that_disagrees_with_the_result_is_rejected(override, expected) -> None:
    with pytest.raises(ValidationError, match=expected):
        _result(findings=[_finding(**override)])
```

### WR-04: The copied `_walk_property_names` has no vacuity guard, so D-02 and D-03 can pass empty

**File:** `tests/contract/test_specialist_result.py:97-127,147-183`
**Issue:** `_walk_property_names` is copied verbatim from `test_decision_support_boundary.py`
(acknowledged at line 100-102). The original is protected by
`test_the_guard_actually_catches_something`, whose docstring says exactly why: "Without this, a
refactor that broke `_walk_property_names` would leave every ADR-014 test passing vacuously." The
copy carries no such control. `test_no_completion_field_exists_by_any_of_its_candidate_names` and
`test_no_per_query_budget_accounting` are both pure absence assertions
(`assert not forbidden & names`) — if the copied walker returns an empty set for any reason, both
pass and prove nothing. Two copies also drift: a fix to the canonical helper will not reach this
one.
**Fix:** Import the helper from a shared location (`tests/contract/_schema_walk.py`) so there is
one implementation with one vacuity guard, or at minimum add the positive control to this file:
```python
def test_the_property_walker_actually_finds_nested_names() -> None:
    schema = SpecialistResult.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    assert {"criterion_id", "policy_citations", "prompt_version"} <= names
```

### WR-05: The table parser silently drops malformed rows and cannot detect a deleted table

**File:** `tests/architecture/test_build_state_table.py:48-85`
**Issue:** Two gaps in coverage, both silent:

- A row line with fewer than six `|`-split fields is skipped without comment (line 72). Dropping a
  single trailing pipe removes a component from enforcement entirely, with no failure.
- Tables are found only by the *verbatim* `HEADER_LINE` (line 60). Reordering or renaming a column
  makes an entire table invisible to the guard, again with no failure.
- No test asserts an expected row count or that all five tables were found. Deleting the seven-row
  "Contracts, schemas, and the gateway" table leaves `BUILT` still represented by the evidence-base
  table, so `test_all_four_markers_are_present` still passes and the suite stays green.

The guard is designed to catch a claim that went *false*; it cannot catch a claim that was
*removed*, which is the cheaper way to make a red test green.
**Fix:** Assert a floor on structure:
```python
EXPECTED_TABLE_COUNT = 5
EXPECTED_MIN_ROWS = 50

def test_every_table_is_parsed_and_no_row_is_silently_dropped() -> None:
    text = DOC_PATH.read_text()
    assert text.count(HEADER_LINE) == EXPECTED_TABLE_COUNT
    assert len(parse_build_state_rows(text)) >= EXPECTED_MIN_ROWS
```
and turn the `len(cells) >= 6` skip into a recorded problem rather than a silent `continue`.

### WR-06: `REQUIREMENT_ID_PATTERN` matches ADR ids, so a cut can go unnamed

**File:** `tests/architecture/test_build_state_table.py:34,154-158`
**Issue:** `re.compile(r"[A-Z]{3,5}-\d{2}")` matches `ADR-01`, and therefore matches every
`ADR-0NN` reference. A `DESIGNED-NOT-BUILT` row whose notes say only "ADR-012 stands as decided"
satisfies the "names a requirement id" check without naming any requirement. The check that exists
to guarantee "a cut cannot go unnamed" (line 198) has a hole exactly the width of the most common
citation in the document. Current rows all happen to carry real ids, so this is latent, not live.
**Fix:** Anchor on the actual requirement-id vocabulary:
```python
REQUIREMENT_ID_PATTERN = re.compile(
    r"\b(ARCH|BAKE|CKPT|CONT|DEL|HAND|ORCH|RETR|REV|ROUT|SPEC|VAL)-\d{2}\b"
)
```

### WR-07: `contracts.md` §6 claims a `ruff format` result that is stale, and the gate currently fails

**File:** `docs/handoff/contracts.md:184-193`
**Issue:** The header says "re-verified 2026-08-11 for CONT-01", but the `ruff format --check` row
still reads "20 files already formatted" — the 2026-08-10 figure, unchanged in the diff. No
plausible scope reproduces 20 today: repo-wide is 86, `packages tests scripts` is 23,
`packages/domain tests/contract scripts` is 17, `packages` alone is 15.

Worse, the gate does not pass. Repo-wide `uv run ruff format --check` currently reports
`1 file would be reformatted, 85 files already formatted`, failing on
`.planning/phases/01-close-the-architecture-package/01-PATTERNS.md:274` — a file added by this
phase, inside ruff's configured scope (there is no `.planning` exclude in `[tool.ruff]`). A handoff
document asserting a green quality gate that is red is precisely the class of unbacked claim
`CLAUDE.md` forbids.

Cross-checked and *correct*, for the record: `ruff check` passes, `mypy --strict` over the domain
package is 11 source files, `pytest tests/contract` is 91, `--check` reports 14 contracts, and
`bandit` is 0 high / 0 medium / 3 low on `ClearanceRequirement`.
**Fix:** Re-run the gate, state the exact command and scope in the row (the bare invocation
`mypy --strict` in the same table now errors with "Missing target module"), and either fix the
`01-PATTERNS.md` fence or add a `.planning` exclude to `[tool.ruff]`.

### WR-08: The CONT-01 invariant is absent from `contracts.md`'s rule/mechanism/test table

**File:** `docs/handoff/contracts.md:60-71`
**Issue:** §2's table is presented as the authoritative map from rule to mechanism to test —
`component-architecture.md:376-377` cites it as such ("the rule/mechanism/test table"). CONT-01
adds a genuinely new structural rule: *every finding in a `SpecialistResult` agrees with that
result's `run_id`, `case_id`, and criterion*. It has a mechanism
(`_findings_belong_to_this_criterion`) and a test
(`test_a_finding_under_a_different_criterion_is_rejected`), and it appears in neither the table nor
§4. A reader auditing the contract set against this document will not learn the rule exists.
**Fix:** Add a row:

| Rule | Mechanism | Test |
|---|---|---|
| **A specialist sub-call analyzes exactly one criterion** (ADR-021 Decision 2) | `SpecialistResult` rejects any finding whose `run_id`, `case_id`, or `authority` disagrees with the result's own criterion | `test_a_finding_under_a_different_criterion_is_rejected` |

### WR-09: "State is identifiers, not transcripts" is now contradicted by the contract set it describes

**File:** `docs/handoff/contracts.md:131-135`; `packages/domain/src/ireports_domain/specialist.py:71`
**Issue:** §4.1 asserts, unqualified: "**State is identifiers, not transcripts.** `RunManifest`
carries `evidence_snapshot_ids` and `proposed_finding_ids`, not evidence text… Checkpoints stay
small, and case text stays out of anything widely serialized. This bears directly on the
checkpoint-store threat model… the less that is in the blob, the less a deserialization trust
boundary can leak."

CONT-01 adds the node *return value* — the thing that lands in orchestrator state and therefore in
the checkpoint blob — and it carries `list[ProposedFinding]` **by value**, not by id. Each
`ProposedFinding` carries `observation`, `policy_relevance`, `aggravating_factors`,
`mitigating_factors` and `recommended_officer_action`: case-derived narrative text. The paragraph
was written when `RunManifest` was the only checkpointed contract and was not revisited.

This matters because CKPT-01 (keyed MAC over checkpoint state) is `DESIGNED-NOT-BUILT` and is named
in `component-architecture.md:295,310-312` as "the single largest recorded security gap". The
volume of case-derived text in an unhardened checkpoint just went up, and the document that quantifies
that trade still says the opposite. (`checkpoint-threat-model.md` T4/T6 already records that
checkpoints hold case-derived text, so the underlying reality is known — it is `contracts.md` §4.1
that is now false.)
**Fix:** Amend §4.1 to distinguish run-level state (identifiers) from node return values
(`SpecialistResult`, by value), and add one sentence naming the consequence for the CKPT-01 gap.

### WR-10: The published schema leaks internal `.planning/` decision ids to external consumers

**File:** `schemas/specialist-result.schema.json:350,391`; `packages/domain/src/ireports_domain/specialist.py:41-64`
**Issue:** `contracts.md:16` states these schemas exist "for non-Python consumers". Two
descriptions in the generated artifact carry unresolvable internal references:

- `SpecialistCriterion.description`: "…required to have at least one entry **(D-04)**."
- root `description`: "Required, not `Optional` **(D-05)**: …"

`D-04` and `D-05` are decision ids from
`.planning/phases/01-close-the-architecture-package/01-CONTEXT.md`, a directory that is GSD planning
state, not part of the handoff package. Verified: `specialist-result.schema.json` is the **only**
one of the fourteen schemas that does this — the other thirteen cite ADRs and blueprint sections,
both of which a handoff reader can resolve.
**Fix:** Rewrite the two docstrings in `specialist.py` to state the rationale without the id (the
prose already does — "A query does not cite; a finding does"), keep the `D-0x` markers in the
plan/summary artifacts, and regenerate `schemas/`.

### WR-11: The §2 diagram draws a delivery edge that bypasses the human review gate

**File:** `docs/handoff/component-architecture.md:104-106`
**Issue:** The diagram contains three edges:

```
ORCH --> REVIEWER
REVIEWER --> ASAPSYS
ORCH -. "validated ASAPEnvelope, written to disk" .-> ASAPSYS
```

The third is a direct orchestrator-to-ASAP edge with no dependency on `REVIEWER`. §1 lines 42-50
insists the decision-support boundary "shows up as structure, not as prose the reader has to trust"
and that "Nothing reaches ASAP without that disposition — no bypass, in any profile." The single
most important claim in the document is visually contradicted by the document's own diagram, in the
one place where a reader is told to trust structure over prose. Mermaid flowcharts carry no
ordering semantics, so nothing in the notation says the dotted edge is downstream of the reviewer.
**Fix:** Route the envelope edge through the gate so the diagram has no ASAP-reaching path that
skips the reviewer:
```mermaid
    ORCH --> REVIEWER
    REVIEWER -- "disposition recorded, run resumes" --> ORCH
    ORCH -. "validated ASAPEnvelope, only after disposition" .-> ASAPSYS
```
or introduce an explicit `GATE["AWAITING_HUMAN_REVIEW - no bypass"]` node that every ASAP-bound
edge must traverse.

### WR-12: "tier alias, never a model id" is contradicted by ADR-017, and the `bedrock` path is missing

**File:** `docs/handoff/component-architecture.md:93,103,126-130`
**Issue:** Two problems with the gateway boundary as drawn.

*The edge label overstates.* `GATEWAY -. "tier alias, never a model id" .-> BEDROCK` and the §2
bullet "**Application code never references a concrete model id**". ADR-017 Decision 2 introduces
`IREPORTS_LITELLM_MODEL_ORCHESTRATOR|THINKING|FAST`, an optional per-tier alias→model override for
exactly the case where a shared organisational proxy does not carry our aliases, and ADR-017's own
Consequences say so unhedged: "The ADR-015 claim 'with the LiteLLM adapter no model id reaches our
repository at all' is now conditional on the proxy carrying our aliases." When that override is
configured, a concrete model id *does* travel that edge. The invariant that survives is narrower:
*application code* names a tier; the *gateway* may resolve it.

*The diagram omits a `BUILT` component.* `BEDROCK` is drawn as a single node labelled "LiteLLM to
Amazon Bedrock". §4:218 lists a `bedrock` adapter that goes direct with **no proxy** (ADR-015). The
system-context diagram has no edge for it, so a reader cannot see the second production path at the
level where the boundaries are supposed to be markable "without reading past the diagram" (line 67).
**Fix:** Relabel the edge `"tier alias; resolved to a model id only in gateway config (ADR-017)"`,
qualify the §2 bullet with ADR-017's conditional, and split `BEDROCK` into the proxied and direct
paths.

### WR-13: The §3 budget-stop path returns from a node without checkpointing

**File:** `docs/handoff/component-architecture.md:154-165,177-181`
**Issue:** The flow is:
```
SHELL -- "ceiling hit"     --> BUDGETSTOP --> STEP6
SHELL -- "within budget"   --> STEP5      --> STEP6
```
`STEP5` is "Checkpoint durably, before the node returns". The ceiling-hit path skips it and goes
straight to `AWAITING_HUMAN_REVIEW`. The prose immediately below states durability as an
*unconditional* property of the architecture: "State is durable before a node returns; nothing is
carried in memory across a process boundary." The diagram shows a path where a node returns without
its state being durable — and it is the path that matters most, since an `INCOMPLETE_DUE_TO_BUDGET`
run must survive to reach a reviewer or the truncated analysis "quietly disappears", which line 175
names as the thing to prevent.
**Fix:** Route both branches through `STEP5`:
```mermaid
    SHELL -- "ceiling hit"   --> BUDGETSTOP --> STEP5
    SHELL -- "within budget" --> STEP5
    STEP5 --> STEP6
```

### WR-14: "`--check` is the CI currency gate" — this repository has no CI

**File:** `docs/handoff/component-architecture.md:214,268`; `docs/handoff/contracts.md:17,23`
**Issue:** `component-architecture.md:214` states as fact: "Regenerated by
`scripts/generate_schemas.py`; `--check` is the CI currency gate." Verified: there is no
`.github/workflows/`, no `Makefile`, no `.pre-commit-config.yaml`, and no CI configuration of any
kind in this repository. Nothing automatically runs `--check`, `ruff`, `bandit`, or
`tests/architecture/`. `contracts.md:17` is phrased as an instruction ("run it in CI") and is fine;
the component-architecture sentence asserts existing infrastructure that does not exist.

This compounds `component-architecture.md:268-272`, which presents the D-11 test as the automatic
answer to "`CLAUDE.md`'s state narrative went stale in this repository once before and nothing
caught it". The remedy is a pytest file that runs only when someone runs the suite — the same
condition under which the previous staleness went uncaught. Under `CLAUDE.md`'s rule ("either cite
a source or mark it unverified"), this needs to be marked.
**Fix:** Change to "`--check` is the intended CI currency gate; **no CI pipeline exists in this
repository yet `[unverified]`** — the handoff team owns wiring it," and say the same about the
build-state test at line 268. Adding a minimal `.github/workflows/quality.yml` running
`ruff check && ruff format --check && mypy --strict packages tests scripts && pytest` would close
this and WR-07 together.

### WR-15: Present tense for an integration that is neither built nor scheduled

**File:** `docs/handoff/component-architecture.md:109-112`
**Issue:** "iReports **queries** the AWS-owned vector collection directly and **is** a consumer of
it, never a producer." In a document whose stated purpose is that "a reader must never have to
guess" which of four build states applies (lines 22-23), this is the only place a capability is
asserted in the present indicative. Nothing queries anything: `packages/retrieval/` is `PLANNED`
(§4:231), and RETR-01/RETR-02 build against **local** OpenSearch only under ADR-021 Decision 1. No
requirement in `.planning/REQUIREMENTS.md` schedules a query against the AWS collection at all; the
diagram correctly draws that edge dotted and annotated "Q-02", but the notation is undefined in the
legend, which governs boxes only.
**Fix:** "In the target deployment iReports **will query** the AWS-owned vector collection directly
as a consumer, never a producer (ADR-007) — `PLANNED`, and untestable until Q-02 is confirmed."
Also extend the build-state legend to say what dotted versus solid edges mean, or drop the
distinction.

### WR-16: The §3 diagram shows no fan-out and no loop, which is the spine's central claim

**File:** `docs/handoff/component-architecture.md:146-166`
**Issue:** `STEP2` reads "fan out one specialist sub-call per criterion" and the shell is described
as enforcing "loop and termination limits" plus "a no-progress detector" (lines 172-173). The
diagram draws a single linear chain — `STEP1 --> STEP2 --> STEP3A --> STEP3B --> STEP3C --> STEP3D
--> SHELL` — with no parallel branch, no aggregation, and no edge returning from `SHELL` to
`STEP3A`. There is nothing for a loop limit to bound and nothing being fanned out. This is the
diagram opening "the `ORCH` box from §2 into the workflow steps a single run passes through", and
the two properties ADR-020 names as the reason the spine exists (bounded fan-out, loop limits) are
the two the diagram omits.
**Fix:** Draw the fan-out and the return edge explicitly — one specialist subgraph, a
`STEP2 -- "per criterion" --> SPECIALIST` edge, `SHELL -- "criteria remain, within limits" -->
STEP3A`, and an aggregation node before `STEP5`.

## Info

### IN-01: The BUILT and PLANNED path-safety blocks are byte-identical duplicates

**File:** `tests/architecture/test_build_state_table.py:106-123,124-146`
**Issue:** Twelve lines — unsafe-path check, `resolve()`, `is_relative_to`, two problem appends,
two `continue`s — are repeated verbatim for the two markers, differing only in the marker name
interpolated into the message. Divergence between the two copies is how a check ends up applied to
one marker and not the other.
**Fix:** Extract `_resolved_or_problem(marker, path, line_number, repo_root) -> tuple[Path | None, str | None]`
and call it from both branches.

### IN-02: Five near-identical raise blocks in the validator invite a copy-paste error

**File:** `packages/domain/src/ireports_domain/specialist.py:80-115`
**Issue:** Thirty-six lines of `if a.x != b.x: raise ValueError(f"...")`, five times, differing only
in field name. With only one of the branches tested (WR-03), a wrong field name in a comparison
would not be caught.
**Fix:** Drive it from a tuple of field names:
```python
for field in ("decision_domain", "policy_pack_id", "policy_id", "criterion_id"):
    got, want = getattr(authority, field), getattr(self.criterion, field)
    if got != want:
        raise ValueError(
            f"finding {finding.finding_id!r} has authority.{field} {got!r}, which does not "
            f"match this result's criterion.{field} {want!r}"
        )
```

### IN-03: `generated_by` may disagree between the result and its findings

**File:** `packages/domain/src/ireports_domain/specialist.py:70-71`
**Issue:** `SpecialistResult.generated_by` and each `ProposedFinding.generated_by` are independent.
A result attributed to `node="foreign_influence_specialist"` on `ModelAlias.THINKING` may carry a
finding attributed to a different node and a different tier alias, and nothing objects. Provenance
becomes ambiguous exactly where ADR-008 wants it unambiguous.
**Fix:** Either extend the validator to require agreement, or state in the class docstring that the
result-level `generated_by` describes the sub-call and the finding-level one describes the
proposal, and that they may legitimately differ.

### IN-04: `contracts.md` narrowed its documented verification to the contract suite only

**File:** `docs/handoff/contracts.md:20-25,186-193`
**Issue:** The runnable block changed from `uv run pytest -q  # 56 passed` to
`uv run pytest tests/contract -q  # 91 passed`, and the §6 gate row from `pytest` to
`pytest tests/contract`. A handoff reader is no longer told how to run the whole suite
(126 passed, 8 skipped), and the new `tests/architecture/` guard is covered by no documented gate
in this file.
**Fix:** Keep the narrow command for the contract set and add `uv run pytest -q  # 126 passed,
8 skipped (live-model skips are opt-in via IREPORTS_LIVE_SMOKE=1)`.

### IN-05: `_walk_property_names` visits unreachable `$defs`, so its docstring overstates precision

**File:** `tests/contract/test_specialist_result.py:97-127`
**Issue:** The docstring says "Collect every property name **reachable** from a schema, following
`$defs`". In practice the generic `for key, value in node.items()` fallback (119-121) descends into
the top-level `$defs` dictionary directly, so every definition is visited whether referenced or
not, and `seen_defs` prevents little. Over-collection is safe for absence assertions but makes a
future false positive (an unrelated `$def` containing "token") confusing to diagnose.
**Fix:** Reword to "every property name in the schema and all of its `$defs`", or skip `$defs` in
the generic fallback so only `$ref`-reachable definitions are walked.

### IN-06: `_is_unsafe_path` misses `~`-prefixed and Windows-style absolute paths

**File:** `tests/architecture/test_build_state_table.py:88-92`
**Issue:** Absoluteness is tested with `path.startswith("/")`. A row path of `~/etc/passwd` or
`C:\Windows` is not flagged; both then resolve inside the repo root and fail harmlessly as
"does not resolve", so there is no exploitable consequence on this platform — but the module
docstring's containment claim (T-01-10) is stated more broadly than the code delivers.
**Fix:** `if not path or Path(path).is_absolute() or path.startswith(("/", "~")):` and note in the
docstring that the check is POSIX-shaped.

---

_Reviewed: 2026-08-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
