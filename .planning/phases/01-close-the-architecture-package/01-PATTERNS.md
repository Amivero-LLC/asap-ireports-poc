# Phase 1: Close the architecture package - Pattern Map

**Mapped:** 2026-08-11
**Files analyzed:** 7 (2 new domain module changes, 1 new schema, 1 new/modified contract test,
1 new handoff doc, 2 targeted edit sites, 1 new architecture test)
**Analogs found:** 7 / 7 (all files have a close in-repo analog; the Mermaid convention itself
has no prior instance — noted explicitly below)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `packages/domain/src/ireports_domain/specialist.py` (new module; name at planner's discretion — candidate `SpecialistResult`/`SpecialistCriterion`) | model (Pydantic contract) | transform (typed return value of one sub-agent call) | `packages/domain/src/ireports_domain/finding.py` | exact |
| `packages/domain/src/ireports_domain/__init__.py` (edit: import + `ROOT_CONTRACTS` + `__all__`) | config (export barrel) | N/A | itself (existing file, pattern is additive) | exact |
| `schemas/specialist-result.schema.json` (generated, not hand-written) | config (generated artifact) | batch (generation script output) | `schemas/finding.schema.json` (shape reference only — do not hand-copy, regenerate) | exact |
| `tests/contract/test_contract_chain.py` and/or a new `tests/contract/test_specialist_result.py` | test | request-response (construct → validate → assert) | `tests/contract/test_contract_chain.py` (fixture style) and `tests/contract/test_decision_support_boundary.py` (isolated-rule style) | exact |
| `docs/handoff/component-architecture.md` (new; exact filename at planner's discretion) | config/doc (handoff markdown) | N/A | `docs/handoff/orchestration-landscape.md`, `docs/handoff/checkpoint-threat-model.md`, `docs/handoff/orchestration-scorecard.md` | role-match (structure yes; Mermaid content has no analog) |
| `CLAUDE.md` § Target layout / § Stack (targeted edit) | config (project doc) | N/A | itself — see "current text" below | exact |
| `README.md` § Status (targeted edit) | config (project doc) | N/A | itself — see "current text" below | exact |
| `tests/architecture/test_build_state_table.py` (new; home directory at planner's discretion — `tests/docs/` or `tests/architecture/`) | test | file-I/O (parses a markdown file, resolves paths against the repo root) | No close analog exists in `tests/` — see "No Analog Found" below. Closest structural relative is `scripts/generate_schemas.py --check` (drift-detection pattern), not a pytest test. | partial |

## Pattern Assignments

### `packages/domain/src/ireports_domain/specialist.py` (model, transform)

**Analog:** `packages/domain/src/ireports_domain/finding.py` (module docstring, `FindingAuthority`,
`GeneratedBy`), plus `run.py` for `ContractVersion`/`CONTRACT_VERSION` usage, plus `common.py` for
the base class and scalar types.

**Module docstring density** (`finding.py` lines 1-14) — every contract module opens with what it
enforces and which ADR/blueprint section demands it:
```python
"""Proposed findings and information gaps.

Blueprint §10.4. This is the contract ADR-014 and the decision-support boundary constrain most
tightly, so the constraints are structural rather than documentary:

- There is no aggregate risk score, risk level, or overall recommendation field, at any level
  (ADR-014). `tests/contract/test_no_aggregate_score.py` asserts this against the generated
  schemas so it cannot reappear under a new name.
- A finding is *proposed* until a human records a disposition (ADR-011). The type is named for
  that, and delivery is gated on a disposition, not on a flag.
- Every material claim carries a resolvable citation, enforced here rather than requested in a
  prompt (`CLAUDE.md`, "evidence before inference").
- Narrative fields use `DecisionSupportText`, which rejects determinative language.
"""
```
`SpecialistResult`'s docstring should cite ADR-021 (retrieval restored to spine; no completion
status) and D-01 through D-05 from `01-CONTEXT.md`, the way this one cites ADR-014/ADR-011.

**Imports pattern** (`finding.py` lines 16-40):
```python
from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .common import (
    CONTRACT_VERSION,
    CaseId,
    Confidence,
    ContractModel,
    ContractVersion,
    DecisionDomain,
    DecisionSupportText,
    EvidenceId,
    FindingId,
    GapId,
    ModelAlias,
    NonEmptyStr,
    PolicyCitationId,
    PolicyPackId,
    RunId,
    UtcDatetime,
    ValidationOutcome,
)
```
Note the alphabetized `from .common import (...)` block — this ordering (case-sensitive,
capitals-first) is `ruff`'s `I` rule and must be preserved; do not hand-order.

**`FindingAuthority` — read closely, this is what the new criterion descriptor is a sibling to**
(`finding.py` lines 70-89):
```python
class FindingAuthority(ContractModel):
    """The single authority and criterion this finding is analysed under.

    One authority per finding, always. Blueprint §2.1: collapsing distinct authorities produces
    analysis that is wrong in a way that is hard to detect. If the same conduct is relevant under
    both 5 CFR 731 and SEAD-4, that is two findings with two criteria, joined at synthesis by
    de-duplication that preserves both — not one finding with a merged rationale.
    """

    decision_domain: DecisionDomain
    policy_pack_id: PolicyPackId
    policy_id: NonEmptyStr
    criterion_id: NonEmptyStr
    policy_citations: list[PolicyCitationId] = Field(
        min_length=1,
        description=(
            "At least one. A policy-relevance claim with no resolvable policy citation is "
            "exactly what the deterministic validator exists to reject."
        ),
    )
```
Per D-04, `SpecialistCriterion` (or chosen name) copies the first four fields
(`decision_domain`, `policy_pack_id`, `policy_id`, `criterion_id`) verbatim in type and must
**omit** `policy_citations` and its `min_length=1` constraint entirely — a query does not cite,
a finding does. State that omission explicitly in the new type's docstring, matching this
project's convention of recording deliberate divergence rather than leaving it silent (see
`GeneratedBy`'s docstring below, and `docs/handoff/contracts.md` §3 "Deliberate divergences").

**`GeneratedBy` — reused verbatim, not re-derived** (`finding.py` lines 92-102):
```python
class GeneratedBy(ContractModel):
    """Provenance of the machine proposal.

    `model_alias` is an alias, never a model ID (ADR-008). Blueprint §10.4's example carries a
    concrete model name; this is a deliberate divergence so that a partition or model-generation
    change stays a LiteLLM config change.
    """

    node: NonEmptyStr
    model_alias: ModelAlias
    prompt_version: NonEmptyStr
```
D-04 says `SpecialistResult.generated_by: GeneratedBy` — import it from `.finding`, do not
redefine it.

**`model_validator(mode="after")` cross-field rule pattern** — two live examples to copy the
shape from. `finding.py` lines 219-250 (`_material_claims_are_cited`) and lines 252-273
(`_evidence_ids_are_not_reused_across_roles`); also `run.py` lines 219-238
(`_delivery_requires_review`). Common shape: a docstring stating *why* the rule exists and which
ADR/decision it enforces, then a plain `if ...: raise ValueError(...)` with a message that names
the rule, then `return self`. Example (`run.py` lines 219-238):
```python
@model_validator(mode="after")
def _delivery_requires_review(self) -> RunManifest:
    """The hard gate (ADR-011), expressed as a validation error.

    A `RunManifest` in a delivery-side state with `human_review_recorded=False` is not a
    valid object. This makes the gate impossible to bypass by constructing the state
    directly, which is the failure mode a config flag would leave open.
    """
    post_review = {
        RunStatus.REVIEW_RECORDED,
        RunStatus.PACKAGING,
        RunStatus.DELIVERING,
        RunStatus.DELIVERED,
    }
    if self.status in post_review and not self.human_review_recorded:
        raise ValueError(
            f"run status {self.status.value!r} requires human_review_recorded=True; "
            "nothing reaches ASAP without a recorded human disposition (ADR-011)"
        )
    return self
```
D-05 ("the criterion is present even when zero findings come back") does not need a validator —
`criterion` should simply be a required (non-`Optional`) field. There is no "must have at least
one finding" rule to enforce (unlike `EnvelopeAnalysis.findings` elsewhere, which does use
`min_length=1` — do **not** copy that constraint onto `SpecialistResult.findings`; D-05 explicitly
wants zero-findings results to validate).

**`schema_version` field convention** (`finding.py` line 166, `run.py` line 178):
```python
schema_version: ContractVersion = CONTRACT_VERSION
```
Every root contract carries this as its first field after the docstring. Copy verbatim.

**`ContractModel` base and its settings** (`common.py` lines 62-81):
```python
class ContractModel(BaseModel):
    """Base for every contract.

    `extra="forbid"` is the load-bearing setting. ...
    `frozen=True` supports ADR-011: ...
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
        use_enum_values=False,
    )
```
`SpecialistResult` and the new criterion type both inherit `ContractModel` directly — nothing to
override.

**No new identifier type is obviously needed.** `RunId`, `CaseId`, `EvidenceId` already exist in
`common.py` (lines 108-127) and should be reused for `SpecialistResult`'s provenance fields
(`run_id`, `case_id`) and its `findings: list[ProposedFinding]`. If a `SpecialistResult` needs its
own id (not required by D-01 through D-06, which describe it as a return value, not a persisted
record with an id) do not invent a prefix without checking `common.py`'s existing prefix list
first.

---

### `packages/domain/src/ireports_domain/__init__.py` (config, export barrel)

**Analog:** itself — this is an additive edit, not a new-file pattern. Copy the existing shape.

**Import-from-submodule block** (lines 73-81, the `finding` import as the closest sibling):
```python
from .finding import (
    FindingAuthority,
    FindingClassification,
    FindingValidation,
    GeneratedBy,
    InformationGap,
    ProposedFinding,
    ReviewUrgency,
)
```
Add a parallel `from .specialist import (SpecialistResult, SpecialistCriterion, ...)` block,
alphabetized by module name among the existing `from .X import (...)` blocks (asap, case, common,
disposition, document, evidence, finding, policy, run — specialist would sort between `run` and
the end, i.e. last, since modules are alphabetized: asap < case < common < disposition < document
< evidence < finding < policy < run < specialist).

**`ROOT_CONTRACTS` registration** (lines 101-116):
```python
ROOT_CONTRACTS: dict[str, type[ContractModel]] = {
    "case": CaseManifest,
    ...
    "delivery-receipt": DeliveryReceipt,
}
"""Contracts published to `schemas/` as JSON Schema. Keys are the schema file stems."""
```
Add `"specialist-result": SpecialistResult,` (or chosen stem). This is what makes
`scripts/generate_schemas.py` emit the schema and what makes
`test_no_contract_carries_an_aggregate_score` (parametrized over `ROOT_CONTRACTS.items()`) cover
it automatically — no new test needed for that rule per D-06.

**`__all__` list** (lines 118-188): alphabetically sorted, one name per line. Add
`SpecialistResult`, `SpecialistCriterion` (or chosen names) in alphabetical position.

---

### `schemas/specialist-result.schema.json` (config, generated)

**Do not hand-write.** Generated by `scripts/generate_schemas.py` (full file read; 80 lines):
```python
REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
SCHEMA_BASE_URI = "https://github.com/Amivero-LLC/asap-ireports/schemas"


def build_schema(stem: str, model: Any) -> dict[str, Any]:
    schema = model.model_json_schema(mode="serialization")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_BASE_URI}/{stem}.schema.json",
        "x-contract-version": CONTRACT_VERSION,
        **schema,
    }
```
Run `uv run python scripts/generate_schemas.py` after adding the contract to `ROOT_CONTRACTS`;
verify currency with `uv run python scripts/generate_schemas.py --check` (this is the CI gate,
not a pytest test — see the "No Analog Found" note below on why the new build-state test needs
its own home rather than piggybacking on this script).

---

### `tests/contract/test_specialist_result.py` (or extend `test_contract_chain.py`) (test, request-response)

**Analog:** `tests/contract/test_contract_chain.py` for the fixture-and-chain style;
`tests/contract/test_decision_support_boundary.py` for the isolated-rule style.
`tests/contract/conftest.py` for hermeticity.

**Hermetic environment fixture, autouse, inherited by existing rather than opted into**
(`conftest.py`, full file, 29 lines):
```python
"""Contract tests are hermetic: no `IREPORTS_*` variable reaches them from anywhere. ...
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _hermetic_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in [n for n in os.environ if n.startswith("IREPORTS_")]:
        monkeypatch.delenv(name, raising=False)
    yield
```
A new `tests/contract/*.py` file gets this for free by virtue of living in `tests/contract/` — no
action needed, just confirm the new test file is placed there (not in a new directory) so the
conftest applies.

**Fixture-per-contract style** (`test_contract_chain.py` lines 179-230, the `finding` fixture) —
build a realistic instance with a docstring-free but self-explanatory literal:
```python
@pytest.fixture
def finding() -> ProposedFinding:
    return ProposedFinding(
        finding_id="fnd_01J8ZR",
        run_id=RUN_ID,
        case_id=CASE_ID,
        authority=FindingAuthority(
            decision_domain=DecisionDomain.NATIONAL_SECURITY_ELIGIBILITY,
            policy_pack_id="sead4-current",
            policy_id="SEAD-4",
            criterion_id="GUIDELINE-B",
            policy_citations=["pol_sead4_b_12", "pol_sead4_b_21"],
        ),
        ...
        generated_by=GeneratedBy(
            node="foreign_influence_specialist",
            model_alias=ModelAlias.THINKING,
            prompt_version="foreign-v4",
        ),
        ...
    )
```
A `SpecialistResult` fixture should reuse this file's `NOW`, `CASE_ID`, `RUN_ID`, `HASH_A` module
constants (lines 67-72) rather than redefining them, and can wrap the existing `finding` fixture
as its `findings=[finding]` list — this file's whole point (module docstring, lines 1-10) is that
the chain composes, so a `SpecialistResult` test belongs here if it's meant to prove it slots into
the existing chain, or in a new file if it's meant to test D-01–D-06 in isolation the way
`test_decision_support_boundary.py` tests ADR-014/ADR-008/etc. in isolation.

**Isolated-rule test style, with a docstring explaining which rule** (`test_decision_support_boundary.py`
lines 102-115, the schema-walking no-aggregate-score test — this one will cover `SpecialistResult`
automatically once registered in `ROOT_CONTRACTS`, no new test needed for D-06's "no aggregate
score" clause):
```python
@pytest.mark.parametrize("stem,model", sorted(ROOT_CONTRACTS.items()))
def test_no_contract_carries_an_aggregate_score(stem: str, model: type[BaseModel]) -> None:
    schema = model.model_json_schema(mode="serialization")
    names = _walk_property_names(schema, schema.get("$defs", {}))
    offenders = {
        name
        for name in names
        if name not in ALLOWED_EXCEPTIONS
        and any(bad in name.lower() for bad in FORBIDDEN_FIELD_SUBSTRINGS)
    }
    assert not offenders, (
        f"contract {stem!r} carries field(s) {sorted(offenders)} that function as an aggregate "
        f"score or a determination. ADR-014 forbids this in any contract, under any name."
    )
```
For D-02 ("no completion-status field, no `is_complete` boolean, no `incomplete_reason` string"),
a targeted test in the same file/style should assert the field is absent from
`SpecialistResult.model_fields` — no existing analog test asserts a field's *absence* by name in
this codebase; write it as a direct `assert "status" not in SpecialistResult.model_fields` style
check plus a JSON-schema property-name check mirroring `_walk_property_names` if the planner wants
schema-level coverage rather than just Python-level.

**Round-trip test convention** (`test_contract_chain.py` line 481, inside
`test_full_chain_reaches_a_delivered_envelope`):
```python
# Round-trips through JSON without loss — the contract has to survive a checkpoint.
assert ASAPEnvelope.model_validate_json(envelope.model_dump_json()) == envelope
```
D-06 requires the same for `SpecialistResult`; copy this one-line pattern.

---

### `docs/handoff/component-architecture.md` (doc)

**Analog:** all four existing handoff docs share one skeleton — `orchestration-landscape.md`,
`checkpoint-threat-model.md`, `orchestration-scorecard.md`, `model-gateway.md`. **No existing
handoff doc uses a Mermaid fence** (confirmed by grep across `docs/handoff/*.md` — only ` ```bash `,
` ```python `, and ` ```yaml ` fences exist today). ARCH-01 is the first Mermaid usage in this
repo; there is no in-repo Mermaid-fence convention to copy, only the surrounding markdown
conventions below.

**Title-and-metadata-line convention**, three real examples:
```markdown
# Orchestration Landscape Scan

**Milestone 1b** · **Date of scan: 2026-08-10** · **Status: complete — feeds ADR-012**
```
```markdown
# Checkpoint-Store Threat Model

**Milestone 1c** · **Date: 2026-08-11** · **Status: complete — an ADR-012 spike deliverable**
```
```markdown
# Model Gateway

**Date: 2026-08-10** · **ADR-015** (amends ADR-008) · `packages/gateway/`
```
Bold segments separated by ` · ` (middle dot), no table for the header line. The new doc should
open `# Component Architecture` (or similar) with a metadata line naming the milestone/phase,
date, and status — e.g. `**Milestone 1a** · **Date: 2026-08-11** · **Status: complete — closes
Milestone 1a**`.

**ADR-001 claim-tagging convention, stated once near the top and then used inline** — this is the
mechanism for "how they mark verified vs unverified claims," directly reusable for D-10's
build-state markers even though the tag vocabulary differs (verification-confidence tags here,
build-state tags there — same *placement* convention: a blockquote near the top defining the tag
set, then bracketed tags used inline or in table cells):
```markdown
> **Read this before relying on any claim below.** Every claim is tagged with how it was
> established. `[measured]` means we ran it on this machine and the number is reproducible.
> `[first-party]` means it comes from the project's own source code, package metadata, or official
> documentation, and the URL is in §11. `[secondary]` means a third party said it and we did not
> independently confirm it. `[unverified]` means we could not confirm it and it should be treated as
> an open question, not a fact.
```
(`orchestration-landscape.md` lines 9-13; nearly identical blocks appear in
`orchestration-scorecard.md` lines 13-16 and `checkpoint-threat-model.md` lines 17-20, each
re-stated rather than cross-referenced only by `checkpoint-threat-model.md`, which says "as in
`orchestration-landscape.md`" — so either re-state the tag legend in the new doc, or reference it
the same way `checkpoint-threat-model.md` does.) For D-10's four-value build-state marker
(`BUILT` / `PLANNED` / `NOT OURS` / `DESIGNED-NOT-BUILT`), open with an equivalent blockquote
defining all four before the first table that uses them.

**Numbered `## N. Section Title` structure**, sections separated by `---`:
```markdown
## 5. Controls this project has actually implemented
...
---

## 6. Controls this project has *not* implemented — the honest list

Stated plainly because a threat model that lists only what was done reads as complete when it is
not. Each of these is Milestone 2 work or a program decision, not something the bake-off settled.

- **Row-level integrity.** Nothing today would detect a tampered checkpoint row that still parses.
  ... **Not built.**
```
(`checkpoint-threat-model.md` lines 108, 136-146.) This "stated plainly, because a document that
lists only what was done reads as complete when it is not" framing is the direct precedent for
D-10's `DESIGNED-NOT-BUILT` marker — copy its honesty-framing sentence structure for the new
doc's own equivalent section, and copy `checkpoint-threat-model.md` §6's `**Bold label.** ...
**Not built.**` per-item shape as one candidate row format if the build-state table is prose-list
rather than table for that subsystem.

**Table formatting**, three real examples confirm a consistent GFM pipe-table style with `---`
header separators and no cell wrapping:
```markdown
| Rule | Mechanism | Test |
|---|---|---|
| **No aggregate person-risk score** (ADR-014) | A test walks every published schema... | `test_no_contract_carries_an_aggregate_score` |
```
(`docs/handoff/contracts.md` lines 57-68 — this is also the best analog for D-10's build-state
table shape: rule/mechanism/test becomes component/build-state/path-or-reason.)

**Sources section at the end**, numbered, present in three of four docs (`orchestration-landscape.md`
§10, `checkpoint-threat-model.md` §8, `orchestration-scorecard.md` implicitly via inline citation) —
if the new doc cites external material (e.g. LangGraph docs for the port-obligations discussion),
close with a `## N. Sources` section in the same style.

---

### `CLAUDE.md` § Target layout / § Stack (targeted edit)

**Current exact text — § Target layout** (`CLAUDE.md` lines 67-85):
```markdown
## Target layout

Adapted from `blueprint.md` §5.2, trimmed to the decisions in `docs/DECISIONS.md`
(no `ui/`, no Neo4j, no offline fixture profile):

```
.planning/       GSD planning state — PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, intel/
docs/            DECISIONS.md, ROADMAP.md, OPEN-QUESTIONS.md, handoff/
spikes/          orchestration bake-off — one directory per candidate framework
schemas/         JSON Schema contracts (case, document, evidence, finding, run, asap-envelope)
packages/        domain, orchestration, retrieval, ingestion, policy, delivery, observability
apps/            api (FastAPI), lambda_adapter, asap_mock
workers/         ingestion, analysis
policy-packs/    versioned, approved authority content
cases/synthetic/ synthetic case fixtures with expected/ results
evals/           datasets, expected, scorers
tests/           unit, contract, integration, retrieval, orchestration, security, end_to_end
infrastructure/  sam, docker, opensearch, postgres, otel
```
```
**This is the D-12 "flagged for the planner" contradiction**: it still lists `policy/`,
`delivery/`, `workers/`, `policy-packs/`, and `evals/` as if buildable, and ADR-020/021 cut all of
those from the 3-phase spine (moved to "designed, not built" per HAND-01). D-12 scopes ARCH-04
narrowly (fix provably-wrong claims + state the 3-phase spine scope) but explicitly says a planner
who notices this outright contradiction should surface it rather than leave `CLAUDE.md`
self-inconsistent.

**Current exact text — § Stack** (`CLAUDE.md` lines 87-105, full table): retrieval is described as
`OpenSearch (local, Docker) mirroring the AWS vector collection` and observability as
`OpenTelemetry + Jaeger` with no indication these are Phase-2/Phase-3-scoped rather than already
built. Same D-12 flag applies.

**What is already correct and should NOT be touched** (already fixed by commit `4de0ad1`, predates
this phase): § Current state (lines 42-59, dated inventory, no longer says "application code does
not exist"), and the Orchestration row of § Stack (line 96, already names LangGraph + ADR-012 as
accepted, not undecided). Do not re-diagnose these as stale — CONTEXT.md's phrasing describing them
as stale claims to fix predates this fix; the current file state (read fresh, 2026-08-11) already
resolves them.

**What ARCH-04 must add per D-12**: "state the three-phase spine scope from ADR-020/021" — no
existing sentence in `CLAUDE.md` currently states there are 3 phases (vs. the pre-ADR-020 9-phase
shape `docs/ROADMAP.md` still describes, marked stale by CONTEXT.md). The closest in-repo
precedent for how to phrase this is `.planning/PROJECT.md` line 21: `**Scope is the orchestrator
spine (ADR-020).** Three phases, not nine.` — reuse this phrasing rather than inventing new
wording, so the two documents agree word-for-word.

---

### `README.md` § Status (targeted edit)

**Current exact text** (`README.md` lines 21-45):
```markdown
## Status

Milestone 1 in progress.

- **1a — contracts: done.** Thirteen data contracts as Pydantic v2 models with generated JSON
  Schema, in `packages/domain/`. The component-architecture write-up is still outstanding.
- **1b — orchestration landscape scan: done.** ADR-012's candidate set amended on evidence:
  four candidates became three.
- **1c — orchestration bake-off: done (2026-08-11). ADR-012 accepted — the framework is
  LangGraph.** All three candidates — hand-rolled (195 lines), LangGraph (266), Strands (373) —
  pass all four legs, so the decision turned on cost rather than correctness. Durable
  checkpointing over PostgreSQL cost two lines with LangGraph's first-party `PostgresSaver`,
  against 56 and 166 for the others. Losing spikes are retained and still run.
  See [`docs/handoff/orchestration-scorecard.md`](docs/handoff/orchestration-scorecard.md)
  and [`spikes/README.md`](spikes/README.md).

```bash
uv sync
uv run pytest -q                                   # 111 passed, 8 skipped
uv run python scripts/generate_schemas.py --check  # schemas/ current with the models

# bake-off (needs Docker)
docker compose -f infrastructure/docker/compose.yaml up -d
uv run pytest spikes -v -s
```
```
**Already largely correct** (also fixed by `4de0ad1`): correctly shows 1a/1b/1c states and does
not claim the framework is undecided. What ARCH-01/ARCH-04 must still change here once CONT-01 and
ARCH-01 land: the 1a bullet's "The component-architecture write-up is still outstanding" clause
becomes false the moment ARCH-01 is written — flip it to done and cite the new
`docs/handoff/` filename, following this bullet's own established citation style (`See
[...](docs/handoff/orchestration-scorecard.md})`). The bullet should also gain a note that
`SpecialistResult` (CONT-01) is published, mirroring how the 1a bullet already names "Thirteen
data contracts" — the count becomes fourteen (or however many after CONT-01's contract is added
to `ROOT_CONTRACTS`) and `test count` `111 passed` in the `bash` block should be regenerated to
match the actual post-Phase-1 `pytest -q` count.

---

### `tests/architecture/test_build_state_table.py` (test, file-I/O)

**No close analog exists.** `tests/` currently contains only `tests/contract/` (imports
`ireports_domain`, validates Pydantic models in memory) and `tests/live/` (imports
`ireports_gateway`, calls a real endpoint). Neither reads a markdown file from disk and parses its
prose content — every existing test in this repo tests *imported Python objects*, not *repo files
as text*. This is a genuinely new test shape for this repo.

**Closest structural relative (not a pytest analog, a script analog):**
`scripts/generate_schemas.py`'s `--check` mode (full file read, 80 lines) is the only existing
code in the repo that (a) resolves paths against `REPO_ROOT = Path(__file__).resolve().parent.parent`
and (b) fails loudly on a repo-state mismatch:
```python
REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
...
    for stem, model in sorted(ROOT_CONTRACTS.items()):
        target = SCHEMA_DIR / f"{stem}.schema.json"
        rendered = render(stem, model)
        if args.check:
            if not target.exists() or target.read_text() != rendered:
                drifted.append(target.name)
```
The new test's `REPO_ROOT` resolution idiom should follow this shape
(`Path(__file__).resolve().parent...` walked up to the repo root — for a test at
`tests/architecture/test_build_state_table.py` that's `.parent.parent.parent`, two levels above
`scripts/generate_schemas.py`'s one level, so get the arithmetic right rather than copying the
literal `.parent.parent`).

**No `__init__.py` exists in either sibling test directory** (`tests/contract/`, `tests/live/`
both confirmed to have no `__init__.py` file currently, despite a stale `__pycache__` entry
suggesting one existed and was removed) — do not add one to the new test directory either; pytest's
rootless import mode is already in effect for the two existing test packages.

**`pyproject.toml` test-path registration** (`[tool.pytest.ini_options]`, lines 58-63):
```toml
[tool.pytest.ini_options]
testpaths = ["tests", "spikes"]
markers = [
    "requires_postgres: needs the compose stack in infrastructure/docker",
    "live: calls a real model endpoint; opt-in via IREPORTS_LIVE_SMOKE=1, never in CI",
]
```
`testpaths = ["tests", "spikes"]` already covers any new subdirectory under `tests/` — **no
change to `pyproject.toml` is needed** for pytest to discover a new `tests/architecture/` or
`tests/docs/` directory, since pytest walks the whole `tests/` tree. (This corrects the phase
brief's suggestion to "note where `pyproject.toml` declares test paths / markers, since a new
top-level test package may need registering" — it does not need registering; only note this if the
planner intends a marker, e.g. a hypothetical `docs` marker, which D-11's ~20-line test does not
obviously need since it should run in the default suite, not be opt-in.)

**mypy exclusion precedent for a second `conftest.py`** (`pyproject.toml`, comment above
`[tool.mypy]` `exclude`): only relevant if the new test directory adds its own `conftest.py` with
a name collision; otherwise no action needed. Current `exclude = ["^conftest\\.py$"]` only excludes
the repo-root one.

**Suggested shape for the new test** (no verbatim analog to copy — described, not quoted, since it
does not exist yet): parse the build-state table(s) out of the new `docs/handoff/*.md` file with a
simple line-based markdown table parser (no new dependency; the file has no existing markdown
table parser in the repo — regex/split on `|` is consistent with this repo's "ordinary code over
machinery" ethos, e.g. `common.py`'s regex-based `reject_determinative_language`), then for each
row: if marker is `BUILT`, `assert (REPO_ROOT / path).exists()`; if marker is `PLANNED`, `assert
not (REPO_ROOT / path).exists()`. Follow `test_decision_support_boundary.py`'s pattern of one
focused `test_*` function per rule, each with a one-line docstring naming what it guards
(`test_the_guard_actually_catches_something`, lines 118-… is the model for "prove the check can
actually fail," which D-11's test should also satisfy — a build-state test with no failing example
in its own suite is a check that cannot be trusted to have ever run correctly).

## Shared Patterns

### Docstring density and ADR citation
**Source:** `finding.py` lines 1-14, `run.py` lines 1-12, `common.py` lines 1-10
**Apply to:** the new `specialist.py` module and every class inside it
Every module and every non-trivial class opens with what it enforces and cites the ADR or
blueprint section by number. Match this density on `SpecialistResult` and the new criterion type —
cite ADR-021 §2 (no completion status) directly in the class docstring, the way `finding.py` cites
ADR-014 directly.

### Deliberate divergence recorded, not silent
**Source:** `GeneratedBy` docstring (`finding.py` lines 92-98); `docs/handoff/contracts.md` §3
**Apply to:** the new criterion descriptor's docstring (must state it omits
`policy_citations`/`min_length=1` and why — D-04); `docs/handoff/contracts.md` §5, which must be
edited to remove `SpecialistResult` from its "deferred" list (lines 157-160) and, per §3's table
convention, gain a divergence-table row if the new type's shape differs from blueprint §10.1 in
any way.

### `model_validator(mode="after")` for structural rules, never prose
**Source:** `finding.py` lines 219-273, `run.py` lines 219-247
**Apply to:** any cross-field rule the planner identifies for `SpecialistResult` beyond what D-01
through D-06 already rule out (most obligations here are field-shape, not cross-field, so this
contract may need zero validators — that is fine and consistent with D-01's "it is thin").

### ADR-001 claim tagging in handoff docs
**Source:** `docs/handoff/orchestration-landscape.md` lines 9-13 (`[measured]` / `[first-party]` /
`[secondary]` / `[unverified]`); reused verbatim in `orchestration-scorecard.md` and
`checkpoint-threat-model.md`
**Apply to:** `docs/handoff/component-architecture.md` — either restate the four-tag legend or
reference it the way `checkpoint-threat-model.md` does ("Claim tagging, as in
`orchestration-landscape.md`"). This is a distinct convention from D-10's build-state markers
(`BUILT`/`PLANNED`/`NOT OURS`/`DESIGNED-NOT-BUILT`) — the new doc likely needs **both** tag
vocabularies side by side: one for factual/measurement confidence, one for build state.

### GFM pipe tables, `---` section separators, numbered `## N.` headings
**Source:** all four `docs/handoff/*.md` files, consistently
**Apply to:** `docs/handoff/component-architecture.md`

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/architecture/test_build_state_table.py` (or `tests/docs/...`) | test | file-I/O | No existing test in this repo reads and parses a repo markdown file as text; both existing test directories (`contract/`, `live/`) test imported Python objects only. Closest available precedent is the non-test script `scripts/generate_schemas.py --check`, cited above for its path-resolution and drift-detection idiom, not as a test-shape analog. |
| Mermaid fences inside `docs/handoff/*.md` | N/A (markdown content) | N/A | Confirmed by grep: zero `\`\`\`mermaid` fences exist anywhere in `docs/handoff/`. ARCH-01 is the first. Only the surrounding prose/table/heading conventions transfer. |

## Metadata

**Analog search scope:** `packages/domain/src/ireports_domain/` (all 10 modules), `schemas/` (13
files), `tests/contract/` (4 files), `tests/live/` (1 file), `docs/handoff/` (6 files, one is JSON
not markdown), `scripts/generate_schemas.py`, `pyproject.toml` (root and `packages/domain/`),
`CLAUDE.md`, `README.md`, `docs/DECISIONS.md` (§ADR-020, §ADR-021), `.planning/STATE.md`,
`.planning/PROJECT.md`.
**Files scanned:** 24
**Pattern extraction date:** 2026-08-11
