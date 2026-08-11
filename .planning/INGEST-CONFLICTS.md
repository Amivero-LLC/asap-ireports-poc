## Conflict Detection Report

Mode: new · Docs synthesized: 12 · Precedence: per-document integer, lower wins (0..11)
Precedence order: DECISIONS.md 0 · OPEN-QUESTIONS.md 1 · ROADMAP.md 2 · CLAUDE.md 3 ·
orchestration-scorecard.md 4 · orchestration-landscape.md 5 · contracts.md 6 · model-gateway.md 7 ·
compatibility-matrix.md 8 · checkpoint-threat-model.md 9 · README.md 10 · blueprint.md 11

### BLOCKERS (0)

None. No LOCKED-vs-LOCKED contradiction was found, no document classified UNKNOWN at low
confidence, and no cycle blocked synthesis. See INFO-01 for the cycle-detection judgment call and
INFO-24 for the one LOCKED-pair tension that was resolved rather than blocked.

### WARNINGS (3)

[WARNING] Three source documents still say the orchestration framework is undecided
  Found: CLAUDE.md (precedence 3, SPEC) states "Orchestration | Undecided — this is what
    Milestone 1 settles. Candidates: LangGraph, Strands Agents SDK, PydanticAI/Pydantic Graph,
    hand-rolled Python". README.md (precedence 10) states "1c — orchestration bake-off: in
    progress … LangGraph and Strands still to run; ADR-012 remains Open" and "Orchestration
    framework: undecided — Milestone 1 output", plus a stale hand-rolled figure of 202 lines.
  Found: docs/DECISIONS.md ADR-012 (precedence 0, LOCKED) is Accepted as of 2026-08-11 — the
    orchestration framework is LangGraph. docs/ROADMAP.md (precedence 2) records 1c complete.
    The candidate set was cut from four to three on 2026-08-10; PydanticAI / Pydantic Graph was
    dropped because Pydantic Graph 2.x has no state-persistence API.
  Impact: Precedence resolves the synthesized intel cleanly — ADR-012 wins and is recorded as
    Accepted. It does not fix the files. CLAUDE.md is the live instruction file every agent in this
    repository reads before working, so leaving it stale will keep telling downstream agents that a
    settled decision is open, and will keep offering a candidate that was removed on evidence. The
    README is the first thing a program reader lands on. A roadmapper generating PROJECT.md must
    also decide whether to describe the framework as decided or open.
  → Confirm that ADR-012 governs (recommended), then update CLAUDE.md's stack table to
    "Orchestration | LangGraph (ADR-012)" and refresh README.md's Status section and the
    "Stack (decided)" line. Both are precedence-losing restatements, not independent authority.

[WARNING] Milestone 3 has no exit criteria and explicitly refuses to be sequenced from its own list
  Found: docs/ROADMAP.md (precedence 2, the only PRD in the ingest) gives Milestone 3 a goal —
    "Widen and deepen against measurements from M2, in the order the evidence justifies" — an
    unordered candidate list, and the instruction "Sequence this from M2 findings — not from this
    list." No exit criteria are stated. Milestones 1 and 2 both carry verbatim exit criteria.
  Impact: Milestone 3 cannot be decomposed into phases from this intel without inventing scope and
    ordering the source deliberately withheld. Any downstream roadmap that turns the candidate list
    into sequenced phases would be manufacturing a plan the source declines to make.
  → Decide before routing: either scope Milestone 3 out of the generated roadmap and carry it as a
    named placeholder gated on M2 measurements, or supply exit criteria. Do not let a generator
    linearize the candidate list.

[WARNING] Q-02 is a GATE that blocks work Milestone 2 lists as in-scope
  Found: docs/OPEN-QUESTIONS.md (precedence 1) marks Q-02 as GATE — "Blocks: finalizing the
    retrieval mapping module and the local OpenSearch index definition" — and states that GATE
    items "must be answered before the work they block starts". Q-02 is OPEN.
  Found: docs/ROADMAP.md (precedence 2) lists Milestone 2 as including "One synthetic case,
    ingested locally and indexed into local OpenSearch", with no gate recorded, and frames M2 as
    the next milestone. Q-01 and Q-03 are also OPEN GATE items; Q-03 blocks "any claim that
    retrieval quality measured locally predicts retrieval quality in AWS", and Q-01 blocks GovCloud
    deployment work and the LiteLLM production configuration.
  Impact: Precedence alone would resolve this in favour of OPEN-QUESTIONS.md (1 beats 2) and mark
    Milestone 2's retrieval work blocked — which contradicts the roadmap's framing that M2 is next
    and is very likely not the authors' intent. Auto-resolving either way would misstate the plan.
    ADR-007 contains the containment argument: field names, filters, and facet mappings are
    isolated to one module so adapting is a one-file change, which suggests local indexing may
    proceed under the working assumption.
  → Decide before routing whether Milestone 2 starts under Q-02's working assumption with the
    mapping module explicitly marked provisional, or waits on the real index mappings from the
    ingestion team. Record the answer; do not let the generated roadmap imply the gate was cleared.

### INFO (24)

[INFO-01] Cycle detection: 21 cycles found, all resolved by the precedence total order
  Found: A three-color DFS over the cross_refs graph (12 nodes, 60 intra-set edges) found 21
    distinct cycles — six 2-cycles, eight 3-cycles, six 4-cycles, one 5-cycle. The 2-cycles are
    CLAUDE.md <-> DECISIONS.md, CLAUDE.md <-> OPEN-QUESTIONS.md, README.md <-> ROADMAP.md,
    OPEN-QUESTIONS.md <-> compatibility-matrix.md, OPEN-QUESTIONS.md <-> orchestration-landscape.md,
    and compatibility-matrix.md <-> model-gateway.md. Maximum traversal depth reached was 4, far
    under the cap of 50.
  Note: These were recorded as INFO rather than as blockers, and that is a judgment call worth
    review. Every cycle is an ordinary bidirectional documentation hyperlink — a decision record
    linking its open-questions register and being linked back — not a derivation loop where one
    document defers its content to another that defers back. Cycle detection guards against
    synthesis looping; two conditions make that impossible here. First, all twelve precedence
    values are distinct integers 0..11, a strict total order that linearizes the whole set
    regardless of link direction, and content conflicts are resolved by precedence rather than by
    traversal order. Second, this synthesis read each source exactly once and did not recurse
    through refs. Treating these as blockers would have halted the entire ingest on documentation
    hygiene with no unsafe write to prevent.
  → No action required. If you would rather the gate hold strictly, re-run and treat this entry as
    a blocker; the affected set is all 12 documents.

[INFO-02] Auto-resolved: ADR-006 over blueprint.md on a graph database
  Found: blueprint.md (precedence 11) §4.1 and §15.2 carry Neo4j forward as an optional component,
    conditional on demonstrated benefit.
  Note: docs/DECISIONS.md ADR-006 (precedence 0, LOCKED) declines a graph database in any milestone
    until evidence demands one, citing AmiLens's own Neo4j layer as scaffolding whose analysis
    pipeline never queries it. ADR wins. Recorded rather than dropped so the program team can see
    the divergence was deliberate. Cross-document relationships and timelines are served by
    structured entities and dated events in PostgreSQL plus OpenSearch retrieval.

[INFO-03] Auto-resolved: ADR-005 over blueprint.md on a Streamlit console
  Found: blueprint.md (precedence 11) Executive Summary and §4.1.2 propose Streamlit as a case
    selector, run console, evidence viewer, and JSON export interface; §4.3 lists a `ui` service in
    the Compose topology and §15.1 lists a Streamlit test UI as required.
  Note: ADR-005 (precedence 0, LOCKED) declines any UI in Milestone 1. FastAPI endpoints are the
    stable interface. The human-review state machine (ADR-011) is still built and enforced; only
    its presentation is deferred. ADR wins.

[INFO-04] Auto-resolved: ADR-009 over blueprint.md on an offline deterministic run profile
  Found: blueprint.md (precedence 11) §3.1, §12.7 and the Executive Summary require a strict
    offline deterministic profile that blocks all egress and replays recorded model fixtures or
    uses a local development model.
  Note: ADR-009 (precedence 0, LOCKED) declines it — no recorded-fixture provider, no local LLM
    server, Bedrock access required to run the system. Unit and contract tests mock at the gateway
    boundary instead; reproducibility comes from recorded run manifests, not replay. ADR wins.
    Note the `stub` gateway adapter (ADR-015) is not a reinstatement of this profile — it is
    ADR-009's own "mock at the gateway boundary" and is contract-test-only.

[INFO-05] Auto-resolved: the 1b landscape scan over blueprint.md §9.2 on AutoGen and Semantic Kernel
  Found: blueprint.md (precedence 11) §9.2 evaluates AutoGen and Semantic Kernel as live framework
    options in its comparison table, with sources at [T-19] and elsewhere.
  Note: Both moved to maintenance mode in April 2026 and merged into Microsoft Agent Framework.
    ADR-012 (precedence 0, LOCKED) removes them from consideration entirely; the 1b scan
    (precedence 5) records the evidence. Blueprint §9.2's comparison table is stale and must not be
    cited as current. ADR wins.

[INFO-06] Auto-resolved: ADR-008/ADR-019 over blueprint.md on naming a model
  Found: blueprint.md (precedence 11) names Claude Sonnet 4.6 as the single model in its title
    banner, Working assumptions, §8.8 ("Use Claude Sonnet 4.6 through a model alias"), §15.1, and
    §19; §10.3 and §10.4 use a concrete `case-analysis-sonnet` value in contract examples.
  Note: ADR-008 (precedence 0, LOCKED) forbids naming any model in application code at all — only
    the three LiteLLM aliases are permitted, and `ModelAlias` is a three-member enum with no
    free-text model field on any contract. The current verified development mapping is Sonnet 4.6
    (orchestrator), Sonnet 5 (thinking), Haiku 4.5 (fast), recorded in compatibility-matrix.md as a
    commercial-partition development mapping and explicitly not an answer to Q-01. ADR wins on both
    counts. The blueprint also predates the LiteLLM offline stub being dropped.

[INFO-07] Auto-resolved: ADR-012 over blueprint.md §9.3 — same answer, different authority
  Found: blueprint.md (precedence 11) §9.2–§9.3 recommends LangGraph on a criteria comparison.
  Note: ADR-012 (precedence 0, LOCKED) reached the same answer, but by a measured four-leg bake-off
    across three candidates with a validated `Scorecard` contract and retained losing spikes. The
    decision's authority is the bake-off, not the blueprint's recommendation. This distinction is
    load-bearing for the handoff: ADR-012 exists precisely because the blueprint supported its
    recommendation with a comparison rather than a demonstration. Do not cite blueprint §9.3 as the
    basis for the framework choice.

[INFO-08] Auto-resolved: ADR-010 over blueprint.md §10.6 on the ASAP evidence model
  Found: blueprint.md §10.6 example uses `evidence_mode: "references_only"`.
  Note: ADR-010 (precedence 0, LOCKED) chose bounded excerpts **and** stable references, so a
    delivered finding is reviewable without a second lookup and without depending on ASAP's ability
    to resolve references into our stores. Recorded as divergence 2 in contracts.md §3. ADR wins.

[INFO-09] Auto-resolved: ADR-014 over blueprint.md §10.6 on a run-level summary
  Found: blueprint.md §10.6 has a free-text run-level `summary` field.
  Note: Replaced by `reviewer_summary` — optional, reviewer-authored only, language-guarded —
    because a machine-written run-level narrative is the most likely place for an aggregate
    characterization of a person to reappear (ADR-014, precedence 0, LOCKED). Recorded as
    divergence 3 in contracts.md §3.

[INFO-10] Auto-resolved: contracts over blueprint.md on four further contract details
  Found and resolved, all recorded in contracts.md §3 (precedence 6) as deliberate divergences with
    this repo's decisions winning:
    - blueprint §10.4 names a validation field `schema`; here `schema_check`, because `schema`
      shadows a `BaseModel` attribute. Cosmetic.
    - blueprint §10.2's case example requires `position_risk_level` / `position_sensitivity`; here
      both are optional, because a case genuinely may not have them and a required field would
      force a caller to invent a value — which is exactly the inference §10.2 prohibits. Optional
      plus a blocking gap is the honest shape.
    - blueprint §10.5's disposition is flat; here `DispositionedFinding` binds proposal to
      disposition with `effective_*` accessors, making "which wording does delivery carry" a
      resolved question rather than a convention, without discarding either version.
    - Added with no blueprint equivalent: `AuthorityRoutingResult` requires an explicit decision for
      every authority, including those that do not apply, because an absent route is
      indistinguishable from an oversight.

[INFO-11] Auto-resolved: ADR-012/ROADMAP over README.md on Milestone 1c status
  Found: README.md (precedence 10) Status section states "1c — orchestration bake-off: in progress.
    Shared harness and the hand-rolled baseline pass all four legs (202 lines, no framework).
    LangGraph and Strands still to run; ADR-012 remains `Open`."
  Note: ADR-012 (precedence 0) is Accepted 2026-08-11 and ROADMAP.md (precedence 2) records 1c
    complete with all three candidates built and passing. The 202-line figure is itself superseded
    (see INFO-12). README.md's own classification records it as "SUMMARY SOURCE ONLY … the README
    is expected to lag." Higher precedence wins. Also covered by the WARNING above.

[INFO-12] Auto-resolved: re-measured line counts supersede the 2026-08-10 figures
  Found: The 2026-08-10 write-up recorded hand-rolled at 202 lines and Strands at 367, from an
    unrecorded method that could not be reproduced. README.md still carries 202.
  Note: Re-counted by `spikes/measure.py` they are 195 and 373 — within 4%, ordering unchanged.
    Both ROADMAP.md (precedence 2) and orchestration-scorecard.md (precedence 4) carry the
    corrected figures and record the supersession explicitly rather than quietly. Corrected figures
    win and are what the intel carries.

[INFO-13] Auto-resolved: ADR-015 over CLAUDE.md on which component may call Bedrock
  Found: CLAUDE.md (precedence 3, SPEC) states "Model gateway | LiteLLM — the only component
    permitted to call Bedrock."
  Note: ADR-015 (precedence 0, LOCKED) amends this on the reasoning that LiteLLM is "a good default
    and a bad single point of failure" — its availability and approval in the target partition is
    not established and its advisory history is substantial. Two production adapters now sit behind
    one `ModelGateway` port: `litellm` (default) and `bedrock` (direct, no proxy). The surviving
    constraint is the stronger one — the gateway port is the only component permitted to call a
    model. ADR-015 explicitly quotes and addresses the CLAUDE.md sentence, so this is a declared
    amendment, not an accidental drift. ADR wins; CLAUDE.md's sentence is stale.

[INFO-14] Auto-resolved: ADR-017 supersedes ADR-015's passthrough route
  Found: ADR-015 specified the `litellm` adapter point the Anthropic SDK at LiteLLM's
    Anthropic-native passthrough, `{base}/anthropic`.
  Note: ADR-017 (same file, precedence 0, declared "Amends ADR-015") reverses it on evidence from
    the first live call: `{base}/anthropic/v1/messages` is passthrough to `api.anthropic.com` and
    401s against a Bedrock-backed proxy, which has no first-party Anthropic credential. The correct
    route is LiteLLM's native `{base}/v1/messages`. `IREPORTS_LITELLM_BASE_URL` is now used verbatim
    and the gateway appends nothing. Self-declared supersession within one LOCKED file; the later
    entry governs. Also: ADR-015's claim "no model id reaches our repository at all" is now
    conditional on the proxy carrying our aliases.

[INFO-15] Auto-resolved: ADR-019 supersedes ADR-018's diagnosis; ADR-018's guard survives
  Found: ADR-018 concluded that `output_config.format` enforcement was a per-model-group property,
    with Opus groups enforcing and Sonnet/Haiku not — implying the tier mapping had to prefer Opus
    for anything structured. compatibility-matrix.md §5 records the same claim in an earlier
    revision and explicitly retracts it as a sample-size-1 artifact.
  Note: ADR-019 (precedence 0, declared "Supersedes the mechanism in ADR-015 and the diagnosis in
    ADR-018") measured eight trials per group: `output_config.format` is unreliable everywhere,
    including Opus 4.8 at 6 of 8; Sonnet 5, Sonnet 4.6, and Haiku 4.5 were 0 of 8. Structured output
    is now a single unforced tool call, 20 of 20 across four model groups. ADR-018's
    `StructuredOutputError` guard survives and is load-bearing for a different reason: with
    `tool_choice` left to the model, a turn could still answer in prose. "Did not occur is not
    cannot occur." Practical consequence: no tier requires an Opus-class model.

[INFO-16] model-gateway.md still describes the superseded structured-output mechanism
  Found: docs/handoff/model-gateway.md (precedence 7) §1 and §3.1 describe structured outputs via
    `output_config.format` and state that "schema enforcement is a per-model-group property."
  Note: ADR-019 (precedence 0, LOCKED) supersedes both — the mechanism is a single tool call, and
    the per-group diagnosis was retracted. The page's own header says "Where this page and
    docs/DECISIONS.md differ, DECISIONS.md wins." ADR wins in the intel. The page is a
    documentation-refresh candidate, not an authority conflict.

[INFO-17] Auto-resolved: the 1b scan's [unverified] Strands claim was measured and did not hold
  Found: orchestration-landscape.md (precedence 5) records a third-party claim, tagged
    `[unverified]` and attributed to a vendor selling a competing product, that Strands restores
    conversation rather than resuming execution.
  Note: The scan itself insists this is "a measurement, not a finding" and must never be extracted
    as fact. ADR-012's Resolution and the scorecard §4 record the measurement: it **does not hold**
    for `Graph` in `strands-agents` 1.51.0 — `serialize_state` carries `completed_nodes` and
    `next_nodes_to_execute`, state syncs after every node, and after a hard `os._exit(9)` no
    completed node re-executed. The same was asserted rather than assumed for LangGraph, same
    result. What is true and narrower: Strands' state container is transcript-shaped, so typed
    contracts are flattened into a message body and re-validated on the way out.

[INFO-18] Auto-resolved: Strands' 0/24 duplicate-call figure is an artifact, not a durability property
  Found: The 2026-08-10 write-up recorded Strands at 0 of 12 duplicate paid model calls and
    predicted the figure was an artifact of our synchronous node bodies rather than a real
    advantage.
  Note: Confirmed by the LangGraph run, which genuinely interleaves: over 24 trials the sibling's
    call was in flight at crash time in 24/24 and cost a duplicate paid call in 11/24, against
    hand-rolled's 12/24 and Strands' 0/24. Strands' numbers partition cleanly — in the 14 trials
    where the sibling had been called it never re-ran, and in the 10 where it re-ran it had never
    been called. The duplicate-model-call window is a property of at-least-once execution with
    uncommitted in-flight calls, **not** a discriminator between frameworks. Model-call-level
    idempotency is owed by all three and built by none; carried as `REQ-model-call-idempotency`.

[INFO-19] Scope clarification, not a conflict: two different mypy results are both true
  Found: contracts.md (precedence 6) §6 records `mypy --strict` as "Success: no issues found in 11
    source files" (2026-08-10). model-gateway.md (precedence 7) §6 records "13 pre-existing errors
    in three test modules" and states that an earlier revision wrongly recorded the gate as clean,
    and that the 13 errors "were present on the commit that made the claim."
  Note: Applying precedence naively would let the higher-precedence document (contracts.md, 6) win
    and record the repository as clean, which is the wrong answer — the lower-precedence document
    carries the correction and the measurement. The two claims are at different scopes and both
    hold: contracts.md's narrow claim about its 11 source files stands, and model-gateway.md
    confirms "no package under `packages/` is affected." The repo-wide gate is **not** clean.
    Synthesis records the repo-wide result and carries the 13 errors as outstanding work
    (`REQ-fix-mypy-tests-contract`): nine unused `# type: ignore` comments and four missing
    annotations in `tests/contract/test_decision_support_boundary.py`.
  → No action required for routing, but note the general pattern: a lower-precedence document may
    carry a correction to a higher-precedence one. Two such self-corrections exist in this set
    (this one and INFO-15); both were resolved in favour of the correction.

[INFO-20] SpecialistResult contract is unblocked by ADR-012's resolution
  Found: contracts.md (precedence 6) §5 defers `SpecialistResult` "until ADR-012 resolves, since its
    shape is the one most likely to be influenced by the framework." ROADMAP.md §1a records the same
    deferral.
  Note: ADR-012 resolved 2026-08-11. The block is lifted and `SpecialistResult` is now unblocked
    forward work. The other four deferred contracts — `ChunkRecord`, `EntityCandidate`,
    `TimelineEvent`, `PolicyRecord` — remain blocked on Q-02 and cannot be shaped until the AWS
    collection's real schema is known. Carried as `REQ-specialist-result-contract` and
    `REQ-deferred-contracts`.

[INFO-21] compatibility-matrix.md is commercial-partition only and does not narrow Q-01
  Found: compatibility-matrix.md (precedence 8) records live measurements including a working tier
    mapping, resolved model ids, request-surface support, and endpoint routing results.
  Note: Every measurement was taken against a **commercial-partition** AWS Bedrock deployment
    through an organisation-shared LiteLLM proxy. The document says so in a blockquote at the top
    and repeats it in §2, §7, and §8. Q-01 remains OPEN and is not narrowed. No extraction may
    present this document as evidence about GovCloud availability, model or inference-profile ids,
    cross-region inference, or data routing. The `bedrock` adapter has never been run in any
    partition. Q-01 is closed only by re-running the live smoke check in the target GovCloud account
    and appending it as a **second** run-of-record; §8 explicitly forbids overwriting §1–§6.

[INFO-22] Two LangGraph defaults are wrong for this architecture and invisible in the code
  Found: `durability` defaults to `async` rather than `sync`; checkpoint deserialization defaults to
    permissive, where the library's own source states that "any Python callable stored in checkpoint
    data will be imported and executed on load" without `LANGGRAPH_STRICT_MSGPACK`.
  Note: Not a conflict between documents — recorded consistently in ADR-012, scorecard §3, and
    checkpoint-threat-model.md §5 — but flagged here because the scorecard calls it "the most
    transferable finding in the whole bake-off": a LangGraph graph reads identically either way, so
    a reviewer cannot catch these by reading it. Both are now set in code with tests. Strict mode
    also fails **soft** — a refused value returns as a plain `dict`, not an exception — which is why
    contract re-validation on load is load-bearing rather than defence-in-depth.

[INFO-23] CLAUDE.md's target layout omits a package that exists
  Found: CLAUDE.md (precedence 3) lists `packages/` as "domain, orchestration, retrieval, ingestion,
    policy, delivery, observability".
  Note: `packages/gateway/` exists and is documented in model-gateway.md (precedence 7) and ADR-015
    (precedence 0). CLAUDE.md also states the target layout "is the plan, not the current state", so
    this is drift rather than contradiction. Recorded so a downstream generator does not treat the
    CLAUDE.md list as an exhaustive inventory.

[INFO-24] ADR-004's "via LiteLLM" wording predates ADR-015 — resolved, not blocked
  Found: ADR-004 (precedence 0, LOCKED, Accepted 2026-08-10) states "Develop against Docker Compose
    locally with Bedrock via LiteLLM as the only network egress." ADR-015 (precedence 0, LOCKED,
    same date) introduces a `bedrock` adapter using the standard AWS credential chain with **no
    proxy** — a Bedrock call that does not go via LiteLLM.
  Note: This is the only place in the ingest where two LOCKED entries touch the same scope without
    one formally superseding the other, so it was examined against the LOCKED-vs-LOCKED blocker
    rule and deliberately not escalated. The constraint ADR-004 actually governs is what network
    egress is permitted — nothing but Bedrock — and the `bedrock` adapter is still egress to
    Bedrock. "Via LiteLLM" is mechanism wording, and ADR-015 addresses that mechanism head-on: it
    quotes the equivalent CLAUDE.md sentence, argues LiteLLM is "a good default and a bad single
    point of failure", and states the reasoning for a second adapter. Outcome is unchanged; only
    the route differs. Recorded here rather than treated as a contradiction.
  → Optional documentation hygiene: refresh ADR-004's wording to "Bedrock through the model gateway
    port as the only network egress" so the two entries read consistently. This is a wording
    change, not a new decision — if you would rather treat it as a real LOCKED-vs-LOCKED conflict,
    it is the one candidate in the set.
