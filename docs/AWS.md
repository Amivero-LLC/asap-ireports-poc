# Running this on AWS

What this design needs from AWS, whether GovCloud has it, and what the local Docker stack stands in
for. Written for a developer who has to build the real thing in a government account.

**Availability moves.** Everything below is dated and cited. Before committing, re-check against the
[AWS Regional Services List](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/)
and your own account — **documented availability is not account entitlement**, and Bedrock model
access is granted per account.

---

## The short version

The architecture is a good fit for GovCloud. The two things that were genuinely uncertain — Claude
on Bedrock, and a managed vector store — are both available, and Claude carries FedRAMP High and
DoD IL4/5 approval there.

**Target region: AWS GovCloud (US-West)** — stated by the project owner 2026-08-12, `[believed]`
not yet confirmed against the account. Everything this design needs exists there, and it is the
better of the two GovCloud regions for us:

| | US-West | US-East |
|---|---|---|
| Claude Sonnet 5 on `bedrock-runtime` | Yes | Yes |
| Claude Sonnet 5 on `bedrock-mantle` | **Yes** | **No** |
| OpenSearch Serverless + vector engine | Yes | Yes |
| Our `bedrock` adapter works as written | **Yes** | No — needs a `bedrock-runtime` sibling |

So the `bedrock-runtime` adapter that ADR-015 named as scoped-but-unbuilt work **is not needed**,
as long as the region holds. If the target moves to US-East, that work comes back — it needs its
own translation layer for thinking, effort, and refusals.

**What would confirm it:** an account and region that someone has actually called. See § What is
still open.

---

## Service-by-service

| Need | Service | GovCloud | Notes |
|---|---|---|---|
| Model inference | Bedrock + Claude | **Yes** `[documented]` | Sonnet 5 since 2026-07-23; Opus 4.8 since 2026-05. See endpoint constraint below |
| Vector + lexical retrieval | OpenSearch Serverless | **Yes** `[documented]` | US-West since 2024-08, US-East since 2024-10; vector engine GA |
| Compute | Lambda | Yes | One invocation per run, in-process fan-out (ADR-023) |
| Workflow state | RDS / Aurora PostgreSQL | Yes | System of record for run state. Never the search index |
| Documents | S3 | Yes | Owned by the ingestion pipeline, not by us (ADR-007) |
| Credentials | Secrets Manager | Yes | Proxy keys, DB credentials |
| Traces and logs | CloudWatch, X-Ray | Yes | OTel-compatible. Identifiers only — never case text |

### The endpoint constraint — read this before choosing a region

Claude Sonnet 5 in GovCloud, per the [AWS announcement of 2026-07-23](https://aws.amazon.com/about-aws/whats-new/2026/07/claude-sonnet-5-govcloud/):

- `bedrock-runtime` endpoints — **US-West and US-East**
- `bedrock-mantle` endpoints — **US-West only**

Our `bedrock` adapter uses `AnthropicBedrockMantle`, because the Mantle endpoint speaks the Messages
API, which keeps thinking, `effort`, structured output, and refusal handling identical to the
LiteLLM adapter path.

| If you deploy to | Then |
|---|---|
| **GovCloud US-West** ← current target | The `bedrock` adapter works as written |
| **GovCloud US-East** | It does not. You need a `bedrock-runtime` adapter with its own translation layer for thinking, effort, and refusals — real work, scope it |

**This is the single highest-leverage fact in this document.** It is one line of configuration and
it decides whether an adapter we already have is deployable or whether a new one has to be built.

### Compliance

Claude in Amazon Bedrock is approved for **FedRAMP High and DoD Impact Level 4 and 5** workloads in
AWS GovCloud (US) regions ([Anthropic, 2025-06-11](https://www.anthropic.com/news/claude-in-amazon-bedrock-fedramp-high)).
That announcement enumerates Claude 3.5 Sonnet v1 and Claude 3 Haiku with more models expected;
**confirm the authorization boundary covers the specific model you intend to use** rather than
assuming it extends to every model later added to the region.

---

## Two ways to reach a model

The gateway (`packages/gateway/`) has one port and two production adapters. Application code names a
tier and never learns which is running.

| | `litellm` | `bedrock` |
|---|---|---|
| Path | App → LiteLLM proxy → Bedrock | App → Bedrock |
| Alias → model mapping lives in | The proxy's config | Our environment |
| Needs | A proxy deployed and permitted | AWS credentials only |
| Status | **Proven** against a live commercial-partition proxy | **Never run in any partition** |

Both use the official `anthropic` SDK rather than an OpenAI-compatible surface. That is deliberate:
adaptive thinking, `output_config.effort`, the `refusal` stop reason, and structured output all live
on the Anthropic request surface, and this architecture depends on them.

**The one genuinely open question is organizational, not technical:** whether a LiteLLM proxy is
permitted in your approved environment. If it is not, the `bedrock` adapter becomes the only path
and the alias→model table moves into your environment — which is a config change, not a code change,
which is the whole point of the tier-alias rule.

---

## Local ↔ AWS parity

You can run everything locally except model calls. Model calls go to a real endpoint — there is no
offline model fixture, deliberately, because a fixture would let us claim things about model
behaviour that we have not observed.

| Concern | Local | AWS | Fidelity |
|---|---|---|---|
| Compute | SAM local + Docker | Lambda | **Good for packaging, poor for timing.** SAM local does not emulate the init/invoke split |
| Workflow state | PostgreSQL container | RDS / Aurora | **High.** Same engine, same SQL |
| Retrieval | OpenSearch container | OpenSearch Serverless | **Structurally good, schema unconfirmed.** See below |
| Documents / triggers | LocalStack (opt-in) | S3 + events | **Not built.** The trigger chain is the ingestion pipeline's, not ours |
| Model | Real endpoint | Real endpoint | **Identical** — same SDK, same request shape |

### Where local parity is weakest

**The retrieval schema is assumed, not confirmed.** We do not have the AWS collection's real index
mappings. The containment strategy is that *every* field name, filter, and facet mapping lives in
one module, so adapting is a single-file change. When you get the real mappings, that is the file to
edit — and the mismatch will not error, it will just retrieve worse, so verify it deliberately.

**Query-time embedding parity is unverified and silent.** If the model that embeds queries differs
from the model that populated the collection, nothing fails — retrieval quality degrades and every
downstream number becomes meaningless without anyone noticing. Local embedding is a development
convenience only. **Never present locally-measured retrieval quality as predictive of AWS
behaviour.**

**Cold start is not measurable locally.** See `docs/LESSONS.md`.

---

## Deployment shape

One Lambda invocation runs one case start to finish, fanning out to specialists in-process (ADR-023).

```
case ready ──▶ Lambda (one invocation)
                 ├── specialist A ─┐
                 ├── specialist B ─┼─▶ join ─▶ validate ─▶ ASAPEnvelope ─▶ ASAP
                 └── specialist C ─┘
```

**Why not Step Functions with a Lambda per node.** It moves control flow out of the application and
splits the deterministic shell across Python and ASL — a large cost to buy a ceiling this workload
can already survive. Fan-out here is a handful of concurrent model calls, not a distributed job.

**The 15-minute ceiling.** The shell stops at its own wall-clock budget *before* Lambda's limit,
checkpoints, and returns; the next invocation resumes. **This is currently an argument, not a
demonstration** — it depends on model-call idempotency, which is not yet built. Until it is, a
timeout means Lambda retries automatically and you pay for the same model calls again.

**Packaging.** Build with `sam build --use-container` (native extensions need Linux wheels), and
exclude the boto3 family — the runtime already has it. Both covered in `docs/LESSONS.md`.

---

## What is still open

Choosing US-West removes the endpoint question. Four things it does not remove:

1. **Account entitlement.** Documented regional availability is not access — Bedrock model access
   is granted per account. Nobody has confirmed this account has it.
2. **Concrete inference-profile IDs**, which have to come from the target account.
3. **Whether a LiteLLM proxy is permitted in the approved enclave.** An organizational question,
   not an AWS one. If it is refused, the `bedrock` adapter becomes the only path — which is a
   config change, not a code change, and is exactly why the tier-alias rule exists.
4. **The `bedrock` adapter has never been run in any partition.** It is verified as correctly
   constructed and nothing more. Do not read the green test suite as connectivity.

All four collapse into one action: run the live smoke check against the target account and paste
the result into `docs/handoff/compatibility-matrix.md` as a second run-of-record.

## Not evaluated

- **Bedrock AgentCore** as a deployment target. It reached GovCloud US-West on 2026-05-05
  `[documented]` and is a live alternative to the Lambda adapter. We did not evaluate it — it is a
  managed runtime rather than a Python library, so it was out of scope for an orchestration
  comparison. Worth a look before committing to Lambda.
- **Cross-region inference profiles** and their GovCloud restrictions.
- **Data-routing behaviour** in GovCloud beyond AWS's general statement that Bedrock keeps data
  within AWS infrastructure.
- **VPC egress** from Lambda to a proxy, and whether your enclave permits it.
