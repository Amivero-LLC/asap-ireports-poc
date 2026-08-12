# Data Contracts

**Milestone 1a** · **Date: 2026-08-10, updated 2026-08-11 (ADR-022)** · **Contract version 2.0.0**
· **Envelope version 2.0.0**

**Breaking change, 2026-08-11.** ADR-022 supersedes ADR-011: iReports has no human interaction, so
review happens in ASAP after a run finishes rather than as an in-run pause. `HumanDisposition` and
`ReviewSummary` are **removed**, along with `AWAITING_HUMAN_REVIEW` / `REVIEW_RECORDED`, the
`human_review_recorded` flag, and the envelope's `human_reviewed` / `reviewer_summary` /
`human_disposition` / `reviewer_modified` fields. Fourteen contracts became twelve, and both
versions moved to 2.0.0 because removing a published contract breaks any consumer that had started
against it.

Twelve contracts as Pydantic v2 models with generated JSON Schema. They come before the
orchestration bake-off on purpose: **the contracts are the interface the orchestration decision
has to satisfy** (ROADMAP 1a). A framework that cannot carry this state cheaply through a
checkpoint is disqualified by these types rather than by opinion. (That sentence used to end "or
cannot pause between a proposal and its disposition" — the bake-off's leg 2 tested exactly that
pause, and ADR-022 removed the workflow it modelled. The spikes retain the v1.0.0 types locally so
the recorded evidence still runs; see `spikes/harness/.../bakeoff_v1_contracts.py`.)

| Where | What |
|---|---|
| `packages/domain/src/ireports_domain/` | The models. Source of truth. |
| `schemas/*.schema.json` | Generated JSON Schema, for non-Python consumers. |
| `scripts/generate_schemas.py` | Regenerates. `--check` fails on drift; run it in CI. |
| `tests/contract/` | The rules, asserted. 114 tests. |

```bash
uv sync
uv run python scripts/generate_schemas.py          # regenerate schemas/
uv run python scripts/generate_schemas.py --check  # CI: fail if schemas/ drifted
uv run pytest tests/contract -q                    # 114 passed
```

---

## 1. The set

| Contract | Schema | Purpose |
|---|---|---|
| `CaseManifest` | `case` | Routing metadata a run is initialized from |
| `DocumentManifest` | `document` | One expected or present document |
| `CanonicalDocument` | `canonical-document` | Normalized text, addressable by block |
| `EvidenceRecord` | `evidence` | A citable span snapshot with retrieval provenance |
| `ContradictionRecord` | `contradiction` | Two case assertions that cannot both be true |
| `AuthorityRoutingResult` | `authority-routing` | Which authorities apply, and why |
| `ProposedFinding` | `finding` | A machine proposal. The only finding type there is |
| `SpecialistResult` | `specialist-result` | The typed return value of one specialist sub-call |
| `RunManifest` | `run` | Everything needed to explain a past run |
| `ASAPEnvelope` | `asap-envelope` | One versioned delivery per completed run, pinned `machine_generated` |
| `OutboxMessage` | `outbox-message` | Transactional-outbox delivery intent |
| `DeliveryReceipt` | `delivery-receipt` | What ASAP said, for reconciliation |

Supporting types (`Subject`, `CaseContext`, `EvidenceSpan`, `AuthorityRoute`, `FindingAuthority`,
`InformationGap`, `Budgets`, `EvidenceExcerpt`, `SpecialistCriterion`, …)
are nested inside these and appear in the generated `$defs`.

---

## 2. The constraints, and how each is enforced

The point of doing contracts first is that the project's non-negotiable rules stop being prose.
Each row below is a rule from `CLAUDE.md` or an ADR, the mechanism that enforces it, and the test
that proves the mechanism works.

| Rule | Mechanism | Test |
|---|---|---|
| **No aggregate person-risk score** (ADR-014) | A test walks every published schema, following `$defs`, and rejects any property whose name functions as an aggregate score or determination | `test_no_contract_carries_an_aggregate_score` |
| **No determinations, ever** (decision-support boundary) | `DecisionSupportText` — every narrative field a model can write into runs an `AfterValidator` that rejects determinative phrasing | `test_determinative_language_is_rejected`, `test_a_finding_cannot_state_a_determination` |
| **iReports models no human decision** (ADR-022) | A test walks every published schema for any field meaning disposition, approval, sign-off, `human_reviewed`, or `release_to_asap`. What an officer decides is ASAP's contract, not ours to guess at | `test_no_contract_models_a_human_decision` |
| **A run never waits for a person** (ADR-022) | No `RunStatus` member implies waiting; the transition table is walked to prove every state can reach a terminal state unattended, and that `DELIVERED` is reachable with no human step | `test_no_run_state_waits_for_a_person`, `test_every_state_can_reach_a_terminal_state_unattended` |
| **An envelope never claims to have been reviewed** (ADR-022) | `machine_generated` is pinned `Literal[True]`; `human_reviewed` is absent. An envelope is what gets reviewed, not the product of a review | `test_the_envelope_never_claims_to_have_been_reviewed` |
| **The machine proposal cannot be edited in place** (ADR-014) | `ContractModel` is `frozen=True` **and** no contract carries a mutable container — every sequence field is `tuple[X, ...]`, because `frozen=True` alone leaves list contents appendable | `test_no_contract_field_is_a_mutable_container`, `test_the_machine_proposal_is_immutable` |
| **Evidence before inference** (`CLAUDE.md`) | A finding that asserts something about the record must cite it; a span cannot serve two roles; `policy_citations` has `min_length=1` | `test_a_potential_issue_must_cite_evidence`, `test_a_span_cannot_serve_two_roles` |
| **Never hard-code a model ID** (ADR-008) | `ModelAlias` is a three-member enum; no contract has a free-text model field | `test_model_reference_must_be_an_alias` |
| **Routing is never inferred** (blueprint §10.2) | `RoutingBasis` has no `INFERRED` member; missing metadata produces `BLOCKED_MISSING_METADATA` with a required `blocking_gap` | `test_missing_routing_metadata_produces_a_blocking_gap` |
| **Fail closed on policy** (blueprint §2.7) | `PolicyPackRef` refuses to construct unless `status == APPROVED`; effectivity is a date comparison in code | `test_an_unapproved_policy_pack_cannot_be_referenced` |
| **Synthetic data only** (`CLAUDE.md`) | `DataClassification` has exactly one member | — |
| **Q-03 embedding parity is silent** (ADR-007) | Vector retrieval must record `embedding_model_id`, or the record will not validate | `test_vector_retrieval_records_its_embedding_model` |

Three design choices carry most of this weight:

**`extra="forbid"` on every contract.** These models sit at boundaries between ingestion,
orchestration, review, and delivery. A silently-dropped unknown field at a boundary is how a
contract mismatch becomes a data-loss bug; forbidding extras turns it into a validation error at
the seam where it happened.

**`frozen=True` on every contract, and no mutable container fields.** ADR-011's "both versions
are retained" only holds if the machine proposal cannot be edited in place. `frozen=True` alone
does not deliver that: it blocks attribute *rebinding*, not mutation of the object an attribute
already points at, so a `list` field on a frozen model stays appendable. That gap was real and is
closed — every sequence field is `tuple[X, ...]`, which emits identical JSON Schema
(`{"type": "array", …}`) and so costs nothing at the boundary. Without it, appending to a
validated `SpecialistResult.findings` bypassed the cross-field validator that had just rejected
foreign findings at construction, letting a case-A result carry a case-B finding.
`test_no_contract_field_is_a_mutable_container` walks every contract in `ROOT_CONTRACTS`,
following nested models, and enforces this mechanically; a paired negative control proves the
walk can still fail.

**Prefixed identifier types.** `run_id` and `finding_id` travel adjacently through orchestration,
delivery, and audit records. If both are bare strings, transposing them is invisible; with
`^run_…` and `^fnd_…` patterns it is a validation error.

### A note on the language guard

`reject_determinative_language` catches the formulations blueprint §10.4 lists as prohibited —
"is unsuitable", "eligibility should be denied", "recommend denial", "violated SEAD-4", "the
subject is deceptive", and predictions of future misconduct. It is tested in both directions:
eight prohibited phrasings must be rejected, and fourteen permitted ones — including deliberate
near-misses like *"the record indicates a security clearance was granted in 2019"* — must pass.
The near-miss tests matter as much as the rejections; an over-broad guard would push nodes toward
vaguer, less useful language, and describing the record's own history is exactly what a finding
is for.

**It is a guard, not a proof — and since ADR-022 it is doing more work than it was designed for.**
It cannot catch every possible phrasing. Under ADR-011 that was tolerable because an in-run review
gate stood behind it; that gate is gone, so this validator and the fact that `ProposedFinding` is
the only finding type are what the decision-support boundary now rests on. Its value is that the
common failure modes become impossible rather than merely discouraged — but it is a filter, not a
second opinion.

---

## 3. Deliberate divergences from `blueprint.md`

Per `CLAUDE.md`, where this repo's decisions diverge from the blueprint, the divergence is
recorded and this repo's decisions win.

| # | Blueprint | Here | Why |
|---|---|---|---|
| 1 | §10.3, §10.4 name a concrete model (`case-analysis-sonnet`) | `ModelAlias` enum only | ADR-008. A partition or model-generation change must be a LiteLLM config change, not a contract change. |
| 2 | §10.6 example uses `evidence_mode: "references_only"` | Bounded excerpts **and** stable references | ADR-010. An excerpt makes a delivered finding reviewable without a second lookup and without depending on ASAP's ability to resolve references into our stores. |
| 3 | §10.6 has a free-text run-level `summary` | **No run-level narrative field at all** | A machine-written run-level narrative is the most likely place for an aggregate characterization of a person to reappear (ADR-014). ADR-011 kept it as a reviewer-authored `reviewer_summary`; ADR-022 removed even that, since no reviewer exists at this point in the pipeline. The stricter outcome. |
| 4 | §10.4 validation field named `schema` | `schema_check` | `schema` shadows a `BaseModel` attribute. Cosmetic. |
| 5 | §10.2 case example includes a `documents_root` and flat context | Same, plus `position_risk_level` / `position_sensitivity` made **optional** | Routing needs them, but a case genuinely may not have them. Optional-plus-blocking-gap is honest; a required field would force a caller to invent a value, which is exactly the inference §10.2 prohibits. |
| 6 | §10.5 has a disposition contract | **No disposition contract at all** (ADR-022) | Review happens in ASAP after the run. What an officer decides is ASAP's contract to define; publishing our guess at it would invite a downstream system to implement against a shape we do not own. |
| 7 | — | `AuthorityRoutingResult` requires an explicit decision for **every** authority, including those that do not apply | An absent route is indistinguishable from an oversight. A reviewer needs to see that SEAD-4 was considered and declined, and on what basis. |

`ReviewUrgency` deserves a specific note. It is a sequencing hint for the reviewer's queue — how
soon a human should look — and **not** a severity score. It is per-finding and never aggregated
across findings or across a person. It is the field most likely to drift into an ADR-014
violation, so it is called out here and in the model docstring.

---

## 4. What these contracts demand of the orchestrator

This is the part Milestone 1c should read. Each of these is a property the winning framework has
to have, derived from the contracts rather than asserted in advance.

1. **State is identifiers, not transcripts.** `RunManifest` carries `evidence_snapshot_ids` and
   `proposed_finding_ids`, not evidence text — blueprint §8.2. Checkpoints stay small, and case
   text stays out of anything widely serialized. This bears directly on the checkpoint-store
   threat model the 1b scan raised: the less that is in the blob, the less a deserialization
   trust boundary can leak.
2. **The run must survive dying mid-flight and resume in a different process.** Under ADR-011 this
   was framed as pausing between a proposal and its disposition (ADR-012 spike legs 1 and 2).
   ADR-022 removed that pause, but the requirement is unchanged and now rests on a harder case: a
   crash mid-fan-out, and — under ADR-023's Lambda shape — a wall-clock timeout, which is the same
   thing. Leg 1, `1-durable-resume`, is the live one; leg 2 tested the workflow that was removed.
3. **Bounded fan-out must be enforceable.** `Budgets` is enforced by the deterministic shell, not
   requested of the model. A node that hits a ceiling must produce `INCOMPLETE_DUE_TO_BUDGET`,
   which is packaged and delivered rather than failing — a truncated analysis must be visible to a
   reviewer in ASAP rather than vanishing (blueprint §8.5). The requirement was never that the run
   pause; only that the partial result arrive.
4. **Contracts must round-trip through JSON without loss.** Asserted directly in
   `test_full_chain_reaches_a_delivered_envelope`, because a checkpoint is a serialization.

---

## 5. Known gaps and open questions

Stated plainly, because this package will be read as authoritative.

- **The ASAP envelope is our proposal, not an agreed interface (Q-04).** The authoritative
  ingestion contract is unavailable. Contract tests pin our side so the delta is *measurable* when
  the real specification lands rather than discovered during integration. Endpoint, auth,
  idempotency semantics, error and retry contract, attachment handling, and whether ASAP stores
  excerpts or only references are all unknown.
- **`MAX_EXCERPT_CHARS = 2000` is a starting value, not a researched threshold.** ADR-010 says
  "bounded," which needs a number to be a constraint. Revisit against real ASAP payload limits.
- **Retrieval-side contracts are not here yet.** `ChunkRecord` and `PolicyRecord` from blueprint
  §10.1 stay cut (CONT-02): ADR-020 cut them and ADR-021 Consequence 3 keeps them cut, because the
  indexed record shape lives inside the retrieval package rather than being published against an
  unconfirmed collection. `EntityCandidate` and `TimelineEvent` remain blocked on Q-02 (the AWS
  collection's real schema is unconfirmed) and have no consumer yet.
- **An empty `findings` list is indistinguishable from a criterion that came back clean.**
  `SpecialistResult` deliberately carries no completion status (ADR-021 Decision 2), so a refused
  or budget-truncated specialist sub-call and a criterion with genuinely nothing to report produce
  the same artifact shape. The distinction lives in the log (`run_id`, `case_id`, the criterion),
  not in the contract (ADR-021 Consequence 2). This is the weakest point in the spine, stated
  plainly here because a handoff reader who assumes an empty list means "clean" would be wrong
  without warning.
- **The language guard is regex-based, and it now carries more weight than it was designed to.**
  It will not catch a determination phrased in a way we did not anticipate. Under ADR-011 that was
  acceptable because the human review gate was the actual control; **ADR-022 removed that gate**,
  so this validator and the fact that `ProposedFinding` is the only finding type are what the
  decision-support boundary rests on. Stated plainly because it is the most likely place for the
  boundary to fail quietly.
- **Bandit flags three `B105` "possible hardcoded password"** on the `ClearanceRequirement` enum
  members (`secret`, `top_secret`, `top_secret_sci`). False positives; no high- or medium-severity
  findings.

---

## 6. Verification, as run

macOS arm64, Python 3.13.x via `uv`, 2026-08-10; re-verified 2026-08-11 for CONT-01 and again
after the mutable-container fix. Each row names its scope — an unscoped file count is the kind of
figure that goes stale without anyone noticing.

| Gate | Result |
|---|---|
| `ruff check packages tests scripts` | All checks passed |
| `ruff format --check packages tests scripts` | 22 files already formatted |
| `mypy --strict packages tests scripts` | Success: no issues found in 22 source files |
| `pytest tests/contract` | 114 passed |
| `pytest` (whole suite) | 160 passed, 8 skipped (skips are live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`) |
| `generate_schemas.py --check` | schemas/ is current (12 contracts) |
| `bandit -r packages` | 0 high, 0 medium severity (3 low-severity false positives, §5) |

These gates are run by hand. There is no CI workflow in this repository yet, so nothing runs them
on a push — treat the figures as of the date above, not as a live signal.
