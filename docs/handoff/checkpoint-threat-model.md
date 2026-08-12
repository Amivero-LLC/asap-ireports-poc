# Checkpoint-Store Threat Model

**Milestone 1c** · **Date: 2026-08-11** · **Status: complete — an ADR-012 spike deliverable**

Required by ADR-012, which added it to the bake-off with a deliberately framework-neutral framing:

> A recurring class of deserialization vulnerabilities on the checkpoint path. … **The versions we
> would use are patched.** The finding is not "LangGraph is insecure." It is that **the checkpoint
> blob is a deserialization trust boundary**, it has been exercised repeatedly, and our
> architecture must treat the checkpoint store as a security-relevant asset — integrity-controlled,
> access-controlled, never fed from anything outside our own PostgreSQL. That obligation is
> framework-independent and applies equally to a hand-rolled checkpointer.

This document is that obligation written down. It applies to whichever candidate ADR-012 selects,
including the hand-rolled one.

> **Claim tagging**, as in `orchestration-landscape.md`. `[measured]` — reproduced on this machine.
> `[first-party]` — from the project's own source, package metadata, or official documentation.
> `[secondary]` — a third party said it and we did not confirm it. `[unverified]` — could not be
> confirmed; treat as an open question.

---

## 1. What the asset is

A checkpoint is the run's resumable state. In this architecture it holds identifiers, typed
contract records, node results, and the run's position in the graph. It also holds proposed
findings — machine output that no authorized officer has seen. That was true under ADR-011 and is
**more** true under ADR-022: with review moved to ASAP, *every* finding in a checkpoint is
un-reviewed by definition, and nothing downstream of the checkpoint will ever mark one otherwise
inside this system.

Three properties make it worth a threat model of its own rather than a line in a general one.

1. **It is read back and acted upon.** Unlike a log, a checkpoint is deserialized into live objects
   and used to decide what executes next. Its integrity is an execution-control property, not only
   a data-confidentiality one.
2. **It is written by machine and read by machine.** No human reviews a checkpoint between write
   and read, so a tampered row has no natural detection point.
3. **It carries case-derived text.** `CLAUDE.md` forbids raw case text in logs and traces
   specifically because those travel; the checkpoint is where such text legitimately lives, which
   makes it the thing the log rule is protecting.

---

## 2. The trust boundary, stated precisely

**The boundary is between the checkpoint store and the process that deserializes from it.**

Everything that crosses it is untrusted input. That sentence is uncomfortable — the store is our own
PostgreSQL, written by our own orchestrator — and it is still the right stance, because the
alternative is that a single write primitive anywhere (a SQL injection in an unrelated feature, an
over-broad database grant, a restored backup, a misconfigured replica, an operator with `psql`)
converts into control over what the orchestrator executes.

This is not a hypothetical for the frameworks in the bake-off. It is the frameworks' own position:

> "This serializer is intended for use within the `BaseCheckpointSaver` class and called within the
> Pregel loop. **It should not be used on untrusted python objects. If an attacker can write
> directly to your checkpoint database, they may be able to trigger code execution when data is
> deserialized.**"
> — `langgraph/checkpoint/serde/jsonplus.py`, `JsonPlusSerializer` docstring, 4.2.0 `[first-party]`

> "Set `LANGGRAPH_STRICT_MSGPACK=true` to restrict checkpoint deserialization to the types listed in
> `SAFE_MSGPACK_TYPES`. **Without this, any Python callable stored in checkpoint data will be
> imported and executed on load.**"
> — `langgraph/checkpoint/serde/_msgpack.py`, module docstring, 4.2.0 `[first-party]`

---

## 3. Advisory history — what it does and does not show

Four advisories on LangGraph's checkpoint path between November 2025 and June 2026, catalogued by
the 1b scan `[first-party]`:

| Advisory | Nature | Fixed in |
|---|---|---|
| `GHSA-wwqv-p2pp-99h5` | RCE in `JsonPlusSerializer` "json" mode | `langgraph-checkpoint` 3.0.0 |
| `GHSA-mhr3-j7m5-c7c9` | `BaseCache` untrusted deserialization → RCE | `langgraph-checkpoint` 4.0.0 |
| `GHSA-g48c-2wqr-h844` | Unsafe msgpack deserialization in checkpoint loading | `langgraph` 1.0.10 |
| `GHSA-fjqc-hq36-qh5p` | Unsafe JSON deserialization in checkpoint loading | `langgraph-checkpoint` 4.1.1 |

**Every one is fixed at or below the versions this project resolves** — `langgraph` 1.2.10,
`langgraph-checkpoint` 4.2.0 `[measured]`. `uv run pip-audit` over the full workspace, including
both framework candidates, reports **no known vulnerabilities** `[measured, 2026-08-11]`.

What the history shows is not that a library is careless. It is that **this specific surface is
where the bugs land**, in a component whose job is to turn stored bytes back into live objects, and
that a design which treats the checkpoint as trusted has been wrong four times in nine months in one
codebase. A hand-rolled checkpointer does not inherit those CVEs; it inherits the surface.

---

## 4. Threats, and what actually mitigates each

| # | Threat | Realistic path | Mitigation |
|---|---|---|---|
| T1 | **Code execution on load.** A checkpoint value names a type; the deserializer imports and constructs it. | Any write primitive against the checkpoint tables. | Store plain JSON; restrict deserialization to an allowlist; never `pickle`. §5. |
| T2 | **Findings altered before delivery.** A proposed finding's text, citations, or authority is changed between checkpoint write and the envelope being emitted. | Same write primitive; also a stale or restored backup. | Re-validate through the domain contracts on load; deterministic citation validation before anything is packaged; contracts are frozen with no mutable container fields, so an in-memory edit after validation is not possible. **Note ADR-022 narrows this:** the "retain both machine proposal and approved version" leg was ADR-011's, and there is no approved version here — ASAP holds it. An alteration before delivery reaches ASAP as though it were ours. |
| T3 | **A run is made to look further along than it is.** State is edited so a run appears ready to package and deliver. | Direct row edit setting a status. | **Weaker than it was, and stated plainly.** ADR-011's mitigation was a gate over `HumanDisposition` records that `package` refused to pass without; ADR-022 removed that gate, because review happens in ASAP rather than in a run. What remains is the transition table and re-validation on load. Row-level integrity (§6, unbuilt) is what would make an edit detectable. **The compensating control is that iReports no longer claims anything was reviewed** — an envelope is pinned `machine_generated` and carries no approval field, so a forged run state cannot forge a human decision that this system never recorded. |
| T4 | **Disclosure of case content.** The checkpoint holds case-derived text at rest. | Over-broad database grants, an unencrypted backup, a shared analytics replica. | Encryption at rest, least-privilege grants, retention limits, no replication of checkpoint tables into analytics. Q-08 and Q-09 own the policy side. |
| T5 | **Cross-run contamination.** One run resumes into another run's state. | A thread/session id collision, or an id supplied from outside. | Run ids are server-generated and never client-supplied. Note `PostgresSaver` truncates `thread_id` at a length-limited column (1b scan §5.1) — a truncating id scheme could *create* collisions. |
| T6 | **Unbounded state growth.** Checkpoint history accumulates case text indefinitely. | Normal operation. | LangGraph retains every super-step by default — measured at 37,033 bytes of thread storage against a 16,115-byte latest checkpoint for the same three findings `[measured]`. Retention and pruning are a design decision, not a default. |

T1 and T3 are the two that turn a data problem into an execution problem. They are the reason this
boundary gets its own document.

---

## 5. Controls this project has actually implemented

**Store data, not objects.** All three bake-off candidates persist JSON built from Pydantic
contracts and re-validate on load: the hand-rolled candidate by construction
(`checkpoint.RunState`), Strands because its container is a message body it must parse back
(`nodes.decode`), and LangGraph because `SpikeState` declares `dict` channels rather than model
types. A tampered row then fails validation instead of executing.

**Restrict deserialization at the library level, in code.** The LangGraph candidate constructs its
serializer as `JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)`
(`checkpointer.strict_serde`), which is the same strict mode as `LANGGRAPH_STRICT_MSGPACK=true` but
cannot be lost by an environment that forgot to set it. **The library default is permissive**, and
the difference is demonstrated rather than described in
`spikes/langgraph/test_checkpoint_trust_boundary.py` `[measured]`:

- Default serializer: a blob naming an arbitrary importable class causes that class to be imported
  and constructed on load. The library logs a warning and proceeds.
- Strict serializer: refused, nothing constructed.
- **Strict mode fails *soft*** — the refused value returns as a plain `dict`, not an exception.
  This is why the contract re-validation above is load-bearing rather than belt-and-braces: without
  it, a blocked value becomes a structurally wrong object that no one is told about.

**Never `pickle`.** Off by default in 4.2.0, passed explicitly so a changed default appears in a
diff, and asserted by test.

**Pin and audit.** Exact pins in each spike's `pyproject.toml`; `pip-audit` is a declared dev
dependency and `CLAUDE.md` already mandates it in CI.

---

## 6. Controls this project has *not* implemented — the honest list

Stated plainly because a threat model that lists only what was done reads as complete when it is
not. Each of these is Milestone 2 work or a program decision, not something the bake-off settled.

- **Row-level integrity.** Nothing today would detect a tampered checkpoint row that still parses.
  The intended control is a keyed MAC over the serialized state, computed with a key the database
  role cannot read, verified on load. This is the single largest gap and the one that converts T2
  and T3 from "difficult" to "detectable". **Not built.**
- **Least-privilege database roles.** The spike runs as a single superuser-ish role against a local
  container. Production needs a role that can write checkpoints and a separate role for everything
  else, and neither should be the migration role. **Not built.**
- **Encryption at rest and backup handling.** Assumed to be platform-provided in GovCloud; not
  verified, and it rides on Q-01 alongside everything else about that partition. `[unverified]`
- **Retention and pruning.** No policy exists for how long a checkpoint carrying case-derived text
  is kept. Tied to Q-09. Material given T6's measured history growth.
- **Provenance on load.** A resumed run does not record which checkpoint id it resumed from into the
  run manifest, so an audit cannot reconstruct the resume chain. Cheap to add; not added.

---

## 7. What this means for the ADR-012 decision

**It does not select a candidate.** T1 through T6 apply to all three, and the mitigations in §5 are
available in all three. A hand-rolled checkpointer avoids the four catalogued CVEs and acquires the
obligation to not reintroduce them; a framework brings a maintained serializer with a published
advisory history and a security posture we can read.

The one asymmetry worth recording is direction of default: **LangGraph's serializer defaults to
permissive deserialization and must be explicitly hardened**, which the candidate now does, while
the hand-rolled checkpoint store has no deserialization surface beyond `json.loads` because it never
had a reason to grow one. That is a point for the hand-rolled candidate on this dimension, and it is
a small one — the hardening is one constructor argument and a test.

The larger point is the one ADR-012 anticipated: choosing a framework relocates this boundary into
code we do not control and must track advisories for. It does not remove it.

---

## 8. Sources

- `langgraph/checkpoint/serde/jsonplus.py` and `serde/_msgpack.py`, `langgraph-checkpoint` 4.2.0, as
  installed — quoted above `[first-party]`.
- `langgraph/pregel/_loop.py`, `langgraph` 1.2.10 — durability modes and background persistence
  `[first-party]`.
- Advisory identifiers and fixed-version ranges: `docs/handoff/orchestration-landscape.md` §5.1,
  which sourced them from OSV `[first-party]`.
- `uv run pip-audit`, 2026-08-11, full workspace `[measured]`.
- `spikes/langgraph/test_checkpoint_trust_boundary.py` — the permissive-versus-strict demonstration
  `[measured]`.
