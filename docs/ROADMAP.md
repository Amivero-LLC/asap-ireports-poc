# What to build next

A working list, in rough priority order. Not a formal plan — no requirement IDs, no acceptance
criteria to sign off. If something here turns out to be wrong or unnecessary, change it.

**Where we are:** a case runs end to end through a Lambda, against real models, through both
orchestration paths, and produces a validated envelope. What is missing is everything that makes it
survive contact with production: retrieval, budgets, and crash recovery.

The previous milestone-based roadmap is in git history (`docs/ROADMAP.md` before 2026-08-12) if you
want the earlier sequencing reasoning.

---

## 1 · Shared orchestration core

**Why first:** ADR-024 keeps two orchestration paths alive, and the way that stays cheap is building
the logic *once* in framework-free code both paths call. Do this before adding features, or you will
add each of them twice.

- Budgets: ceilings on model calls, tokens, and wall clock — per node and per run
- Loop and fan-out limits, replacing the current `IREPORTS_DEMO_MAX_PARALLEL` env var
- A `BudgetConsumption` record on the run so spend is accountable after the fact

The orchestrators keep only what is genuinely theirs: how work is scheduled. Everything about
*what* work is allowed belongs in shared code.

**Watch for:** where a feature is easy in one path and awkward in the other. That is real evidence
for the framework decision, and it goes in `LESSONS.md`.

## 2 · Local AWS parity

**Why:** you asked for the local environment to be architecturally compatible with what GovCloud
actually offers, and today `infrastructure/docker/` is one PostgreSQL container.

- **OpenSearch in the compose file**, configured to mirror the Serverless vector collection —
  same index shape, same vector engine settings, so local behaviour predicts AWS behaviour
- **The mapping module**: every field name, filter, and facet in one file, so swapping to the real
  AWS collection schema is a single-file edit. Its header should say the schema is unconfirmed
- **LocalStack as an opt-in profile** for the S3 and trigger path — not in the default `pytest`
  loop, which stays fast and service-free
- A short "what runs where" check so a developer can confirm their local stack matches `docs/AWS.md`

**Decide early:** GovCloud US-West or US-East. `bedrock-mantle` is US-West only, and that decides
whether our `bedrock` adapter works as written or needs a `bedrock-runtime` sibling.

## 3 · Retrieval

**Why:** right now specialists are *handed* evidence from a file. A specialist that retrieves its
own evidence is the actual architecture — the fixture version demonstrates a fan-out, not this
system.

- Vector + lexical query against local OpenSearch, with a **mandatory case filter** and bounded K
- One synthetic case indexed and retrieved against
- No graph database, ever (ADR-006)

**Known limitation to write down, not solve:** if the embedding model used at query time differs
from the one that populated the AWS collection, nothing errors — retrieval just gets quietly worse.
Local retrieval quality is never predictive of AWS retrieval quality.

## 4 · Crash, resume, and idempotency

**Why:** this is the hard one, the highest technical risk, and **the thing that decides the
framework question**. It is the only seam where custom Python and LangGraph meaningfully differ.

- Checkpoint after each node; resume in a *separate process* without re-running completed work
- **A crash mid-fan-out must not re-run an in-flight model call.** Today that fails: the bake-off
  measured 11 of 24 duplicate paid calls for LangGraph and 12 of 24 hand-rolled
- Set `durability="sync"` and strict checkpoint deserialization on the LangGraph path — both
  defaults are wrong here and invisible when reading the graph
- Then prove it across a Lambda invocation boundary. **A Lambda timeout is a crash mid-fan-out**,
  and Lambda retries automatically, so without idempotency a timeout re-pays for every model call

**When this works, make the framework call** and close ADR-024.

## 5 · A case the system has never seen

**Why:** every run so far uses `AMI-SYN-FIN-001`, built alongside the system, and it contains real
concerns. So we have shown it finds issues when issues exist. We have *not* shown the opposite —
whether it manufactures concern on a clean record to look thorough.

- A second synthetic case with a different shape: a clean record, or one where concern is strongly
  mitigated
- The interesting result is **fewer findings, or none**. An empty envelope is refused by design, so
  a genuinely clean case should produce a run that says so rather than an envelope that invents
  something

This is cheap and it is the single strongest evidence improvement available.

## 6 · One command, end to end

Fold the demo into something a developer runs without knowing about SAM staging:

```
ireports run --case AMI-SYN-FIN-001
```

Load, retrieve, fan out, enforce budgets, validate, package, write the envelope. Unattended, no
point at which it waits for a person.

---

## Not scheduled, deliberately

| | Why not |
|---|---|
| Document ingestion | Not ours — the AWS pipeline owns upload, extraction, chunking, indexing (ADR-007) |
| Authority routing from policy packs | Criteria are hard-coded in `specialist.py` and that is honest for a PoC. Real routing needs approved policy content that does not exist yet |
| Checkpoint row integrity | The largest known security gap. A tampered checkpoint that still parses would not be detected. Worth doing before anything real runs on this, not before the PoC is proven |
| Agreement scoring against analyst findings | Needs synthetic cases with analyst-identified ground truth. Worth doing once there is something to measure |
| Bedrock AgentCore | Reached GovCloud US-West 2026-05-05 and is a live alternative to the Lambda adapter. Never evaluated — worth a look before committing to Lambda |

## The refusal gap

Worth stating plainly because it is the weakest point in the current design: **a refused specialist
produces an empty findings list that is indistinguishable, in the artifact, from a criterion that
came back clean.** The distinction exists only in the log.

Refusals are expected in normal operation here — adjudicative files routinely discuss criminal
conduct, substance use, and foreign contacts. Closing this means surfacing "this criterion was not
analyzed" as a first-class outcome rather than as silence. It is not hard; it just has not been done.
