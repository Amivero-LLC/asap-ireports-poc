# Data Contracts

**Milestone 1a** · **Date: 2026-08-10** · **Contract version 1.0.0** · **Envelope version 1.0.0**

Thirteen contracts as Pydantic v2 models with generated JSON Schema. They come before the
orchestration bake-off on purpose: **the contracts are the interface the orchestration decision
has to satisfy** (ROADMAP 1a). A framework that cannot carry this state cheaply through a
checkpoint, or cannot pause between a proposal and its disposition, is disqualified by these
types rather than by opinion.

| Where | What |
|---|---|
| `packages/domain/src/ireports_domain/` | The models. Source of truth. |
| `schemas/*.schema.json` | Generated JSON Schema, for non-Python consumers. |
| `scripts/generate_schemas.py` | Regenerates. `--check` fails on drift; run it in CI. |
| `tests/contract/` | The rules, asserted. 56 tests. |

```bash
uv sync
uv run python scripts/generate_schemas.py          # regenerate schemas/
uv run python scripts/generate_schemas.py --check  # CI: fail if schemas/ drifted
uv run pytest -q                                   # 56 passed
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
| `ProposedFinding` | `finding` | A machine proposal, pending disposition |
| `RunManifest` | `run` | Everything needed to explain a past run |
| `HumanDisposition` | `human-disposition` | One officer decision about one finding |
| `ReviewSummary` | `review-summary` | The run-level review record |
| `ASAPEnvelope` | `asap-envelope` | One versioned delivery per approved run |
| `OutboxMessage` | `outbox-message` | Transactional-outbox delivery intent |
| `DeliveryReceipt` | `delivery-receipt` | What ASAP said, for reconciliation |

Supporting types (`Subject`, `CaseContext`, `EvidenceSpan`, `AuthorityRoute`, `FindingAuthority`,
`InformationGap`, `Budgets`, `DispositionedFinding`, `EvidenceExcerpt`, …) are nested inside these
and appear in the generated `$defs`.

---

## 2. The constraints, and how each is enforced

The point of doing contracts first is that the project's non-negotiable rules stop being prose.
Each row below is a rule from `CLAUDE.md` or an ADR, the mechanism that enforces it, and the test
that proves the mechanism works.

| Rule | Mechanism | Test |
|---|---|---|
| **No aggregate person-risk score** (ADR-014) | A test walks every published schema, following `$defs`, and rejects any property whose name functions as an aggregate score or determination | `test_no_contract_carries_an_aggregate_score` |
| **No determinations, ever** (decision-support boundary) | `DecisionSupportText` — every narrative field a model can write into runs an `AfterValidator` that rejects determinative phrasing | `test_determinative_language_is_rejected`, `test_a_finding_cannot_state_a_determination` |
| **Nothing reaches ASAP without a human disposition** (ADR-011) | A run in any delivery-side status with `human_review_recorded=False` fails validation; and the transition table is walked to prove no path reaches delivery without passing the gate | `test_no_path_reaches_delivery_without_human_review` |
| **Both machine proposal and approved version retained** (ADR-011) | `ContractModel` is `frozen=True`; `HumanDisposition` references the proposal by id and carries `approved_text` alongside it | `test_the_machine_proposal_is_immutable`, `test_modification_retains_both_versions` |
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

**`frozen=True` on every contract.** ADR-011's "both versions are retained" only holds if the
machine proposal cannot be edited in place.

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

**It is a guard, not a proof.** It cannot catch every possible phrasing and it is not a substitute
for the human review gate. Its value is that the common failure modes become impossible rather
than merely discouraged.

---

## 3. Deliberate divergences from `blueprint.md`

Per `CLAUDE.md`, where this repo's decisions diverge from the blueprint, the divergence is
recorded and this repo's decisions win.

| # | Blueprint | Here | Why |
|---|---|---|---|
| 1 | §10.3, §10.4 name a concrete model (`case-analysis-sonnet`) | `ModelAlias` enum only | ADR-008. A partition or model-generation change must be a LiteLLM config change, not a contract change. |
| 2 | §10.6 example uses `evidence_mode: "references_only"` | Bounded excerpts **and** stable references | ADR-010. An excerpt makes a delivered finding reviewable without a second lookup and without depending on ASAP's ability to resolve references into our stores. |
| 3 | §10.6 has a free-text run-level `summary` | `reviewer_summary`, optional, reviewer-authored only, language-guarded | A machine-written run-level narrative is the most likely place for an aggregate characterization of a person to reappear (ADR-014). |
| 4 | §10.4 validation field named `schema` | `schema_check` | `schema` shadows a `BaseModel` attribute. Cosmetic. |
| 5 | §10.2 case example includes a `documents_root` and flat context | Same, plus `position_risk_level` / `position_sensitivity` made **optional** | Routing needs them, but a case genuinely may not have them. Optional-plus-blocking-gap is honest; a required field would force a caller to invent a value, which is exactly the inference §10.2 prohibits. |
| 6 | §10.5 disposition is flat | Adds `DispositionedFinding` binding proposal to disposition, with `effective_*` accessors | Makes "which wording does delivery carry" a resolved question rather than a convention, without discarding either version. |
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
2. **The run must be pausable between a proposal and its disposition,** and resumable in a
   different process — because `AWAITING_HUMAN_REVIEW` is a real state with no bypass, and the
   disposition arrives out of band. This is ADR-012 spike legs 1 and 2, and the contracts are why
   they are non-negotiable.
3. **Bounded fan-out must be enforceable.** `Budgets` is enforced by the deterministic shell, not
   requested of the model. A node that hits a ceiling must produce `INCOMPLETE_DUE_TO_BUDGET`,
   which routes to human review rather than to failure — a truncated analysis must be visible to
   a reviewer (blueprint §8.5).
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
- **Retrieval-side contracts are not here yet.** `ChunkRecord`, `EntityCandidate`, `TimelineEvent`,
  `PolicyRecord`, and `SpecialistResult` from blueprint §10.1 are deferred. The first three depend
  on Q-02 (the AWS collection's real schema); `SpecialistResult` is deliberately deferred until
  ADR-012 resolves, since its shape is the one most likely to be influenced by the framework.
- **`ReviewerRole` has one member.** ADR-011 specifies a single authorized reviewer role. Widening
  it is a contract change reviewed against Q-07 (policy ownership), not an incidental string.
- **The language guard is regex-based.** It will not catch a determination phrased in a way we did
  not anticipate. The human review gate, not this validator, is the actual control.
- **Bandit flags three `B105` "possible hardcoded password"** on the `ClearanceRequirement` enum
  members (`secret`, `top_secret`, `top_secret_sci`). False positives; no high- or medium-severity
  findings.

---

## 6. Verification, as run

macOS arm64, Python 3.13.x via `uv`, 2026-08-10.

| Gate | Result |
|---|---|
| `ruff check` | All checks passed |
| `ruff format --check` | 20 files already formatted |
| `mypy --strict` | Success: no issues found in 11 source files |
| `pytest` | 56 passed |
| `generate_schemas.py --check` | schemas/ is current (13 contracts) |
| `bandit` | 0 high, 0 medium severity (3 low-severity false positives, §5) |
