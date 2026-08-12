# Phase 1: Close the architecture package - Context

**Gathered:** 2026-08-11
**Status:** Ready for planning

> **Read this first.** This discussion changed the project's scope mid-session. ADR-020 pared
> 9 phases to 3; ADR-021 corrected one of its cuts. Both were written and committed during this
> discussion. **`.planning/ROADMAP.md` and `REQUIREMENTS.md` as they stand now are correct** — any
> Phase 1 artifact predating 2026-08-11 that references ARCH-05, a port specification, or a
> dual-adapter bake-off is stale.

<domain>
## Phase Boundary

Phase 1 delivers **three documents-and-a-contract**, nothing runnable beyond a schema and a test:

1. **ARCH-01** — the component-architecture write-up. The last item blocking program sign-off on
   Milestone 1a.
2. **CONT-01** — the `SpecialistResult` contract, published to `schemas/` with contract tests.
3. **ARCH-04** — `CLAUDE.md` § Current state and `README.md` § Status made true.

**Not in Phase 1:** the orchestration port (built in Phase 2 under ORCH-01, not specified in prose
first), ADR-012's supersession criteria (ARCH-05, cut with the bake-off), retrieval, routing,
the human gate, or anything that calls a model.

**The governing steer, in the user's words:** *"We are just proving out the architecture, not
building the full solution or doing Model Evaluation."* When a Phase 1 choice is between more
machinery and less, choose less.

</domain>

<decisions>
## Implementation Decisions

### `SpecialistResult` (CONT-01)

- **D-01: It is thin.** Three things and nothing else — the criterion analyzed, the provenance of the
  run, and the proposed findings with their citations. It is the return value of one sub-agent call:
  the orchestrator says "check this case against 5 CFR 731 financial considerations," the sub-agent
  does its RAG search, and this is what comes back.

- **D-02: No completion-status field.** Explicitly considered and rejected. An earlier turn in this
  discussion selected a five-member status enum (`COMPLETE` / `INCOMPLETE_DUE_TO_BUDGET` / `REFUSED`
  / `STRUCTURED_OUTPUT_ERROR` / `BLOCKED`); the user reversed it once the contract's purpose was
  clear: *"We should LOG things and check the logs, but not require the orchestrator to do anything
  special."* **Do not reintroduce a status field, an `is_complete` boolean, or an `incomplete_reason`
  string.** This is recorded in ADR-021 § Decision 2.

- **D-03: No per-query budget accounting.** `BudgetConsumption` already exists and accumulates at run
  level on `RunManifest`. `SpecialistResult` does not duplicate it.
  *Recorded trade:* a truncated analysis reaches a reader with no per-query account of what it spent.

- **D-04: The criterion descriptor is a new sibling type to `FindingAuthority`.**
  `decision_domain`, `policy_pack_id`, `policy_id`, `criterion_id` — but **without**
  `FindingAuthority`'s `policy_citations: min_length=1` requirement, because a *query* does not cite;
  a *finding* does. Reusing `FindingAuthority` verbatim will not work. Provenance reuses the existing
  `GeneratedBy` (`node`, `model_alias`, `prompt_version`) as-is.

- **D-05: The criterion is present even when zero findings come back.** This is the whole reason the
  wrapper exists rather than returning `list[ProposedFinding]` — a result with no findings must still
  say what was checked.

- **D-06: Given by acceptance, restated so it is not lost.** Pydantic v2 in `packages/domain/`,
  generated JSON Schema in `schemas/`, contract tests, `extra="forbid"`, `frozen=True`, **no
  aggregate score field of any kind** (ADR-014, enforced by an existing schema-walking test), and
  round-trips through JSON without loss.

### Component-architecture write-up (ARCH-01)

- **D-07: One document in `docs/handoff/`,** alongside the six that are already there — that is where
  a program reader looks. Not a new `docs/architecture/` tree, not split into a boundaries doc plus a
  design doc.

- **D-08: Boxes plus the workflow steps inside them.** Two levels. The outer level is packages and
  external systems — orchestration, gateway, retrieval, domain contracts, and the systems around us
  (AWS ingestion, OpenSearch, ASAP, the human reviewer). The inner level opens up the orchestrator:
  what kicks off a sub-agent call, what the sub-agent does with its RAG search, where budgets are
  checked, where the run pauses for the human. Not a walked narrative example; not boxes alone.

- **D-09: Diagrams are Mermaid fences inline.** Canonical in the document, never exported to image
  files — the diagram and the prose stay one reviewable artifact, and it diffs. (Carried from the
  roadmap reshape, not re-litigated.)

- **D-10: Every component carries a build-state marker.** Four values:
  | Marker | Meaning |
  |---|---|
  | `BUILT` | exists now; the row names a real path |
  | `PLANNED` | names the phase that delivers it |
  | `NOT OURS` | AWS ingestion, ASAP, the reviewer |
  | `DESIGNED-NOT-BUILT` | cut by ADR-020/021; the row names the reason |

  **`DESIGNED-NOT-BUILT` is the load-bearing addition.** A reader must never have to infer the
  difference between "coming in Phase 3" and "deliberately not coming." A handoff package that
  quietly omits what it did not build is the exact failure ADR-001 is written against.

- **D-11: A test enforces the table.** ~20 lines: parse the markdown table, fail if a `BUILT` row's
  path does not resolve, fail if a `PLANNED` row's path already exists. This exists because
  `CLAUDE.md`'s state narrative went stale and nothing caught it — that already happened in this
  repository, which is why ARCH-04 exists at all.

### Entry-document refresh (ARCH-04)

- **D-12: Bounded to the stale claims plus the new scope.** Fix what is provably wrong —
  `CLAUDE.md` § Current state says application code does not exist, and both files imply the
  orchestration framework is undecided — and state the three-phase spine scope from ADR-020/021.
  **Not** a full coherence pass over `CLAUDE.md`'s target layout, stack table, and rules sections.

  *Flagged for the planner:* `CLAUDE.md` § Target layout still lists `policy/`, `delivery/`,
  `workers/`, `policy-packs/`, and `evals/`, and § Stack still describes retrieval and observability
  as if being built. The user scoped ARCH-04 narrowly and that scoping is respected — but a planner
  who notices an outright contradiction (not merely an omission) should surface it rather than
  leaving `CLAUDE.md` self-inconsistent, since it is the first thing a fresh session reads.

### Claude's Discretion

- Section ordering and headings within the write-up.
- Exact field names on `SpecialistResult` and the name of the new criterion-descriptor type
  (`SpecialistCriterion` is the obvious candidate; nothing turns on it).
- Whether the build-state table lives in one table or one per subsystem, provided the enforcing test
  can parse it.
- Whether the contract-version constant bumps for this addition.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope — read these first, they were written during this discussion
- `docs/DECISIONS.md` § ADR-020 — the pare-down to the orchestrator spine, 9 phases → 3. What was
  cut, what was explicitly retained and why.
- `docs/DECISIONS.md` § ADR-021 — retrieval restored to the spine; `SpecialistResult` carries no
  status; VAL-02 reduced to logging.
- `.planning/ROADMAP.md` § Phase 1 — the five success criteria this phase is judged on.
- `.planning/REQUIREMENTS.md` — ARCH-01, ARCH-04, CONT-01 acceptance; § v2 § Cut by ADR-020 lists
  everything owed a `DESIGNED-NOT-BUILT` row.

### Decisions that constrain the contract
- `docs/DECISIONS.md` § ADR-014 — no aggregate risk score on any contract, whatever it is named.
  NON-NEGOTIABLE; considered for ADR-020's cut and explicitly kept.
- `docs/DECISIONS.md` § ADR-011 — the human disposition gate. Same status.
- `docs/DECISIONS.md` § ADR-008 / ADR-017 — models by tier alias only, never a model id.
- `docs/DECISIONS.md` § ADR-006 — **no Neo4j, no graph database, in any milestone.** Retrieval is
  vector + lexical only. Reaffirmed by the user during this discussion.
- `docs/DECISIONS.md` § ADR-001 — the deliverable is a proven architecture and a handoff package.
  Every claim cited or explicitly marked unverified.

### Existing contracts this one sits beside
- `packages/domain/src/ireports_domain/finding.py` — `ProposedFinding`, `InformationGap`,
  `FindingAuthority`, `GeneratedBy`, `FindingValidation`. **Read `FindingAuthority` before designing
  the criterion descriptor** (D-04).
- `packages/domain/src/ireports_domain/run.py` — `Budgets`, `BudgetConsumption`, `RunManifest`,
  `RunStatus`.
- `packages/domain/src/ireports_domain/common.py` — `ContractModel`, `DecisionSupportText`, the
  prefixed id types, `CONTRACT_VERSION`.
- `docs/handoff/contracts.md` — the contract set and what each rule enforces. §5 records
  `SpecialistResult` as deferred; **that block is lifted** and §5 needs updating.
- `schemas/` — 13 generated JSON Schema files; `SpecialistResult` joins them.
- `scripts/generate_schemas.py` — the generator; `--check` is the currency gate.

### For the write-up's content
- `docs/handoff/orchestration-scorecard.md` — what the bake-off measured and, in §5, what it did not.
- `docs/handoff/model-gateway.md` — the gateway port, its two production adapters, the refusal path.
- `docs/handoff/checkpoint-threat-model.md` — T1–T6; §6 lists controls built and not built. Source
  for several `DESIGNED-NOT-BUILT` rows.
- `docs/OPEN-QUESTIONS.md` — Q-01, Q-02, Q-03 and their blast radius.
- `spikes/harness/src/ireports_spike_harness/port.py` — prior art: an orchestrator port that survived
  three implementations. Cited as evidence in the write-up, **not** promoted into `packages/`.
- `blueprint.md` — the project's **input**, lowest precedence. Where it conflicts with
  `docs/DECISIONS.md`, DECISIONS.md wins.

### Stale — do not follow
- `docs/ROADMAP.md` — describes the pre-ADR-020 milestone shape. Reconciling or retiring it is a
  **Phase 3** obligation under HAND-01. Do not treat it as current.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`ContractModel`** (`common.py`) — the frozen, `extra="forbid"` base every contract inherits.
  `SpecialistResult` inherits it and gets D-06's hygiene rules for free.
- **`GeneratedBy`** (`finding.py`) — reusable verbatim for provenance (D-04). Already carries `node`,
  `model_alias` (alias-typed, so ADR-008 is enforced by the type), and `prompt_version`.
- **`scripts/generate_schemas.py --check`** — the existing schema-currency gate. The new contract
  plugs into it; no new tooling.
- **`tests/contract/`** — 56 contract tests including the schema-walking no-aggregate-score test,
  which will cover `SpecialistResult` automatically once it is published.

### Established Patterns
- **Structural enforcement over documentation.** Constraints are `model_validator`s and tests, not
  prose. `ProposedFinding` has two cross-field validators enforcing evidence rules. A Phase 1 rule
  that could be a validator should be one.
- **Deliberate divergence from `blueprint.md` is recorded, not silent.** `GeneratedBy` uses an alias
  where the blueprint used a model name, and says so in its docstring. Follow that.
- **Docstrings carry the *why*.** Every contract module opens with what it enforces and which ADR
  demands it. Match that density.
- **`mypy --strict` is clean across 48 source files** and `ruff` passes. Both must stay clean.

### Integration Points
- `packages/domain/src/ireports_domain/__init__.py` — the export list; new contract registers here.
- `schemas/` — generated output; regenerate rather than hand-write.
- `docs/handoff/contracts.md` §5 — remove `SpecialistResult` from the deferred list.
- The new build-state test needs a home. `tests/` currently has `contract/` and `live/` only;
  planner picks (`tests/docs/` or `tests/architecture/`).

### Repo health baseline (2026-08-11)
111 tests passing, 8 skipped (live-model, opt-in via `IREPORTS_LIVE_SMOKE=1`). `ruff` clean.
`mypy --strict` clean. `pip-audit` clean over the pinned set.

</code_context>

<specifics>
## Specific Ideas

- **The architecture in the user's own words:** *"we have the orchestration model that is kicking off
  a sub-agent call/skill (with opensearch RAG search) to review the adjudication case. We don't need
  to do a lot more than get a list of the issues by policy finding/violation with citations."*
  This sentence is the spine, and it is why ADR-021 reversed ADR-020's retrieval cut — the RAG search
  is not incidental to the sub-agent, it is what the sub-agent does.

- **On scope discipline:** *"We are just proving out the architecture, not building the full solution
  or doing Model Evaluation."* Applied twice in this discussion — to drop `SpecialistResult`'s status
  field, and to reduce VAL-02 to a log line.

- **On observability over machinery:** *"We should LOG things and check the logs, but not require the
  orchestrator to do anything special."*

- **Reaffirmed unprompted:** *"No Graph Database! only vector in this architecture."* Already ADR-006,
  now doubly recorded.

</specifics>

<deferred>
## Deferred Ideas

Raised or settled during this discussion, then cut. Recorded so nobody re-derives them.

- **The orchestration port's prose specification.** Discussed at length and settled — prose only,
  typed signatures plus a numbered obligations list, derived from the domain contracts with
  `spikes/harness/port.py` cited as prior art, and the durability invariants (state durable before a
  node returns, nothing carried in memory across the process boundary, deserialized state
  re-validated) stated as **adapter-neutral port obligations** rather than as LangGraph settings.
  **Then cut** — its purpose was letting two adapters be written without either shaping the port, and
  ADR-020 cut the second adapter. The port is built directly in Phase 2 under ORCH-01.
  *Worth carrying forward anyway:* those durability invariants are real and are currently recorded
  only as ORCH-01's acceptance (`durability="sync"`, strict deserialization). Phase 2 should not lose
  them.

- **ADR-012's pre-registered supersession criteria (ARCH-05).** Cut with the bake-off. The instinct
  behind it — criteria invented after the effort is spent get judged against the effort — is worth
  keeping for any future measurement.

- **A result-level `information_gaps` list on `SpecialistResult`,** with a cross-field validator
  requiring a blocking gap on refusal. Superseded by D-02 and ADR-021 § 3. Logged instead.

- **Per-query budget accounting with the specific ceiling that fired.** Rejected as D-03.

- **Tool-allowlist id and evidence-considered list on `SpecialistResult`.** Rejected as part of D-04
  — the allowlist registry does not exist until Phase 2, and evidence ids duplicate
  `RunManifest.evidence_snapshot_ids`.

- **A full coherence pass over `CLAUDE.md`.** Out of ARCH-04's scope by D-12; see the flag there.

- **`docs/ROADMAP.md` reconciliation.** Phase 3, HAND-01.

</deferred>

---

*Phase: 1-close-the-architecture-package*
*Context gathered: 2026-08-11*
