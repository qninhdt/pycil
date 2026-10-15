# Architecture

Pycil is one private backend organized by business domain. The API process owns HTTP,
process-local generation jobs and a Tantivy search projection (on disk when configured). PostgreSQL stores all
application, content-revision and native checkpoint tables in `public`; Redis supplies optional typed caching,
shared generation task status and coordination. The migration command is a separate finite process.

## Ownership

| Package | Owns |
| --- | --- |
| `account` | Identity mapping, preferences, profiles, plans, allowances and usage settlement. |
| `vocabulary` | Words, senses, lexical content, immutable references, relations, translation, generation and search. |
| `library` | Nodes, deck memberships, physical paths, publication and authorized scopes. |
| `study` | Artifact banks, exercise generation, preparation, grading, reviews and personal progress. |
| `themes` | Theme identity, descriptors, namespaces and lifecycle. |
| `assistant` | Conversations, agent execution, tools, approvals, streaming and checkpoint usage. |
| `app` | HTTP adapters, resource assembly, deployment/product configuration and response composition. |
| `infrastructure` | PostgreSQL, Redis, identity/provider transports, prompt rendering and observations. |

Theme descriptors belong to `themes`; themed lexical content belongs to `vocabulary`
and themed exercises to `study`. Vocabulary does not call study services. There is no
external vocabulary facade or duplicate ORM metadata. Models stay with their owning
domain and share one application metadata registry.

Routers parse contracts and call business functions. Assistant tools call those same
functions, including live authorization and transaction rules. Resource ownership is
explicit; business functions do not need a FastAPI request or application state.

## Lifecycle

[The factory](../../apps/api/pycil/app/factory.py) constructs the application without
opening stores, calling providers or changing schema. Lifespan loads policy/deployment
configuration and enters [process resources](../../apps/api/pycil/app/resources.py).

Resources verify the application/native setup and required reference data, ping Redis,
create scoped caching, open HTTP/provider clients and the native checkpoint pool, then
open the Tantivy projection and start one owner/standby task per worker. An exit stack closes acquired resources after startup
failure and shutdown; jobs close before the resources they use. Closed resources are
removed from application state.

`/health` reports process liveness. `/ready` checks PostgreSQL, Redis and the published
search snapshot within a bounded deadline; failures return a sanitized 503 response.
Startup never runs migrations or downloads reference data.

## Main flows

- First authenticated access verifies identity and atomically provisions the account
  and three library roots. Only the internal UUID is cached in RAM; profile/settings/plan
  reads remain lazy database reads. A cached UUID is not an authorization grant.
- Library writes take an owner transaction lock, check current paths/permissions and
  quotas, and commit the operation atomically. Reference access is resolved live.
- Preparation reads current preferences/plan, selects authorized senses in a consistent
  SQL snapshot, retrieves or fills exercise banks, and builds public questions.
- Grading reads lexical facts and returns diagnostics. Review submission owns progress,
  scheduler updates, idempotency receipts and daily activity.
- Generation performs inventory and enrichment, validates evidence, publishes content
  atomically, then incrementally updates Tantivy before reporting `ready`. Database
  content stays committed if its derived index publication fails.
- Assistant turns use an owned conversation, renewable Redis lease, persisted approval
  state, current allowance admission, graph execution/SSE and usage settlement.
  Checkpoints are native library storage in `public`, separate from learning state.

## Consistency and limits

Library writes serialize per owner; reviews serialize per learner; usage settlement
serializes per execution key and user. These transactions are separate from checkpoint
persistence and Redis leases. Admission is not a quota reservation.

Generation execution and singleflight belong to one process; polling reads shared Redis
status. Restart loses unfinished jobs, while committed vocabulary and checkpoint data
remain. Task status expires 24 hours after each initial/final write; a worker crash or
failed final Redis write can leave `running` until expiry. Workers share a configured disk
index directory. One lifetime Tantivy writer polls commit-ordered content revisions;
other workers read its atomic commits and retry ownership with jitter. Independent task
local directories each reconcile all changes. Document batches and their revision cursor
commit together. Bootstrap uses one repeatable-read snapshot and catches up after its
high-water revision; compatible restarts and takeover reuse the checkpoint.

Content mutations and JSON Patch revisions share a PostgreSQL transaction. Owner locks
precede the short global publication lock; revision IDs are allocated last with `CACHE 1`
and commit in scan order. Graph mutation/deletion also stabilizes inbound edges before
capturing their source owners. The explicit adoption baseline runs with content writes
paused, never from API startup. History survives deletion and has no time-based pruning.
Readers use current tables; history is for replay and derived-index synchronization.

Separate Word metadata, Sense and artifact memory caches hold detached objects, never user
progress or ORM instances. Cached Words retain Sense IDs; responses reuse the shared Senses.
Lexical DTOs use frozen slotted dataclasses and tuples. TTL and entry capacities are independent;
themed lexical reads bypass the neutral caches.
Optional typed Redis cache failures degrade to misses; native required coordination failures
remain visible. Search publication receipts wait without holding a DB connection. A timeout
keeps valid committed content, which the owner still reconciles. Readiness compares head and
cursor/progress; an idle caught-up index remains healthy. See [search](modules/vocabulary.md)
and [migration/recovery](operations/migrations.md) for maintenance boundaries.

Provider attempts share bounded concurrency, explicit timeouts/retries, validated output
schemas and normalized token measurements. Structured observations bind correlation
context and record operation outcome, duration and sanitized error category. The API owns
optional OpenTelemetry trace/metric export; see [configuration](configuration.md) for SDK
lifetime and export settings. Langfuse setup remains deferred.

See [the redesign](../../plans/260924-0608-pycil-complete-redesign/plan.md) for accepted constraints, [testing](testing.md)
for current verification boundaries and [database setup](operations/migrations.md)
for the explicit migration/import command.
