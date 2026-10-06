# Architecture

## Scope and shape

Pycil is a modular Python backend, not a collection of independently deployed business
microservices. Its two long-running processes share application code, product policy,
PostgreSQL, and Redis:

```text
HTTP client -> Caddy -> API
                       |-- account identity and preferences
                       |-- Library hierarchy and live scope reads
                       |-- study preparation, grading, and reviews
                       |-- dictionary reads and generation submission
                       `-- assistant SSE and approved tools

Worker -> generation queue -> Lexi content/question generation
       `-> expired conversation cleanup

API / worker -> PostgreSQL: public | lexi | checkpoints
             -> Redis: bounded cache | conversation leases | start counters
             -> Cambridge SQLite reference artifact (read-only)
             -> configured inference / decision services
API          -> Clerk identity verification
```

The migration process is separate and finite. It upgrades Lexi, Pycil, and native
checkpoint storage before API/worker startup. No business route creates schema.

## Module boundaries

| Module | Owns | Delegates |
| --- | --- | --- |
| `account` | User mapping, JSON preferences, plan gates, anchored usage accounting | JWT key verification and missing-identity lookup to Clerk |
| `library` | Nodes, memberships, physical closure, publication, authorized scopes | Lexical preview enrichment to Lexi; state lookup to study models |
| `vocabulary` | Durable shared generation request/status | Word content, lexical search, question banks and generation to Lexi |
| `study` | Per-user scheduling state, current review receipts, selection and progress queries | Question retrieval/grading to Lexi; scheduling to native FSRS |
| `assistant` | Conversation metadata, leases, input boundary, tool approval and metering | Agent execution/checkpoints to LangChain/LangGraph; content changes to shared services |

HTTP routers are thin adapters, not a second implementation of business rules. Assistant
tools call the same Library mutation/read functions as HTTP. Ownership and publication
must therefore remain in the shared service rather than only at a route boundary.

## Process lifecycle

`main.create_app()` is import-safe: constructing the application does not open a database,
contact a provider, or migrate. The lifespan loads strict policy and deployment values
and acquires resources through `dependencies.process_resources()`.

Initialization checks the Cambridge file, connects application SQLAlchemy sessions,
verifies schema versions and required tables, pings Redis, creates a namespaced cache,
opens an HTTP client and native checkpoint pool, and starts Lexi. Resources belong to
one process and are released through an exit stack, including partial-startup failures.
Shutdown removes them from application state so closed clients are not reused on restart.

API requests receive an `AsyncSession`, product policy, and/or Lexicon through explicit
dependencies. Closing a request session discards uncommitted transactions. Services
use explicit transaction boundaries for writes. An SQL cancellation with PostgreSQL
code `57014` becomes a retryable `query_timeout` response at the request dependency.

## Representative paths

### First authenticated access

JWT verification -> map Clerk subject -> verify a missing user with Clerk -> insert user
and three system roots atomically -> return detached actor context -> optionally cache.
Existing migrated accounts already have roots. User insertion handles concurrent first access.

### Deck save

Actor -> owner-scoped transaction lock -> live edit authorization -> parent/publication
validation -> closure/space move if required -> complete membership diff -> commit ->
optional editor-cache invalidation. Invalid membership rolls back metadata and movement too.

### Study preparation

Actor -> current plan lookup -> effective preferences -> repeatable-read selection ->
authorized scope expansion -> bounded SQL membership relation -> question-readiness
selection -> native batch counts/retrieval -> bundles. Preparation does not write progress
or generate missing questions. Native retrieval occurs after selection and can detect bank changes.

### Generation

Authenticated submission -> shared durable request -> worker claims a queued row ->
Lexi generates/resumes the word -> fills missing neutral question banks -> marks READY.
The worker owns a PostgreSQL session advisory lock and verifies its connection identity
while processing. A restarted owner recovers interrupted jobs before polling.

### Assistant turn

Owned conversation -> validated input -> renewable Redis lease -> persisted approval
validation -> current allowance admission -> agent execution and SSE -> usage settlement
and conversation timestamp update. Rejection resolves the pending tools without a new
model invocation. Conversation checkpoints are distinct from learning sessions.

## Concurrency and consistency boundaries

- Library changes serialize per owner with transaction advisory locks; quotas are checked inside the lock.
- Review batches lock the user's event key and sorted sense resources, committing
  scheduler writes, immutable receipt and daily activity together.
- Usage settlement serializes by execution key and user; admission is not a reservation.
- Conversation leases coordinate across API processes and must not silently fail open.
- Generation has a single lock-owning worker, not an unrestricted horizontally scaled worker pool.
- Lexi and checkpoint persistence use native connections and transactions; one application
  transaction does not imply a global transaction across every resource.
- Scope reference permissions are resolved live. There is no background permission fan-out.

## Caches and work limits

Detached actor and owner editor values have bounded optional Redis caching. Cached values
are not access grants. Scopes, preparation, and personal summaries read current data;
there is no default personal-statistics cache or `library_senses` projection.

Scope expansion limits metadata and raw membership work before sense deduplication,
then keeps the unique sense relation in PostgreSQL. Statement/expansion deadlines are
safety limits, not demonstrated response-time targets. Lexi search is a separate path:
its process-local Tantivy reload reads the full published lexical projection, not just
the selected Library scope.

## Sources

- [Application](../../apps/api/pycil/main.py), [resources](../../apps/api/pycil/dependencies.py), [database](../../apps/api/pycil/database.py)
- [Worker](../../apps/api/pycil/worker.py), [migration gate](../../apps/api/pycil/migrate.py)
- [Compose](../../docker-compose.yml), [Caddy](../../Caddyfile)
- Detailed transaction and failure contracts: [Library](modules/library.md), [Study](modules/study.md), [Assistant](modules/assistant.md)
