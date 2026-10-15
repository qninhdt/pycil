# Configuration, user identity and caching refactor

Status: implementation and verification are in progress. The neutral-content design below supersedes the initial mixed Word/Sense cache. Its separate caches, lexical dataclasses and consumer wiring are implemented and locally verified. Keep the name `projections`. Approval covers the design and configuration ownership, not arbitrary capacity values. The current complete backend run has 493 passes and the same two logging-capture failures recorded before this content change; current verification is recorded below. Frontend typechecking is outside this lexical-only implementation.

## Outcome

Replace the Redis-cached actor snapshot with a process-local `clerk_id -> user_id` mapping. Authenticated endpoints that only need the internal user ID must return that ID on a memory-cache hit without querying PostgreSQL or Redis. Profile, settings and plan data must be loaded from PostgreSQL only when the operation needs them.

Move reusable memory and Redis cache primitives into infrastructure, store Python objects directly in memory, and preserve explicit ownership, bounded capacity, expiration, isolation and failure behavior.

Organize configuration by product policy and runtime operation, give shared frontend settings a separate public owner, and document every configurable value in English. Preserve existing configured behavior while removing duplicated defaults and scattered operational literals.

## Scope and decisions

- Remove actor terminology from the affected application contracts, dependencies, configuration, logs, tests, fixtures and documentation. Use user terminology instead.
- Rename the application's `clerk_subject` field and database column to `clerk_id`. The JWT claim remains the standard `sub` claim.
- Remove `ActorContext` and its Redis cache. Do not replace it with another eagerly hydrated aggregate containing every account field.
- Separate access to user ID, profile, settings and plan. This does not require splitting the existing users table.
- Introduce `MemoryCache[K, V]` and `RedisCache[T]` in `apps/api/pycil/infrastructure/cache.py`.
- Replace the existing `ContentCache` implementation and imports with the infrastructure memory cache. Preserve lexical content and artifact caching as separate logical instances.
- Keep the existing cachetools and redis-py dependencies. Do not adopt cashews or aiocache for this change.
- Do not add Redis cache-aside for profile, settings, plan or neutral content in this phase. The later DevOps course work owns the additional cache-aside release.
- Preserve current public HTTP response shapes. Internal authentication does not need to reuse the aggregate `/v1/me` response model.

## Identity resolution

1. Validate the bearer token and verify its JWT signature and claims before consulting the identity mapping cache.
2. Extract the verified Clerk ID from `sub`.
3. Read the process-local user ID cache.
4. On a hit, return the cached UUID immediately. Do not perform SQL, call Redis, load account fields or call Clerk.
5. On a miss, resolve the ID from PostgreSQL. Provision a missing account through the existing verified Clerk lookup and atomic account/library provisioning flow.
6. Publish the mapping only after the relevant transaction succeeds.
7. Preserve optional authentication behavior: absent credentials may remain anonymous; supplied invalid credentials must still fail.

Concurrent first access must still create one account and its required library roots. Preserve existing uniqueness, collision handling and transaction safety. Missing/incomplete legacy profiles must retain their supported completion path without making every ID-only cache hit load a profile.

A cached UUID is identity routing information, not proof of account existence or an authorization grant. Ownership, account existence, plan-sensitive admission, allowance and settlement must continue to use the authoritative checks required by their business operation. Remove a mapping when a known account deletion or identity-link change occurs; TTL bounds stale mappings in other processes. Do not add a distributed invalidation system in this phase.

## Separate account reads

Expose clear account-owned functions/dependencies for the data an operation actually needs:

```text
verified identity -> current user ID
user ID -> profile from PostgreSQL, when needed
user ID -> settings from PostgreSQL, when needed
user ID -> plan from PostgreSQL, when needed
```

Do not automatically issue three database queries or reconstruct a complete context in authentication. Existing business operations may keep a combined SQL read when they need multiple fields in one transaction. Keep plan and usage checks in the appropriate authoritative transaction rather than treating a request snapshot as permanent entitlement authority.

Future cache-aside belongs at these account/data read boundaries. Do not add a generic cache manager, backend selection framework, decorators or placeholder cache settings for uncached resources.

## Memory cache contract

```python
MemoryCache[K, V](max_entries, ttl)

cache.get(key)          # V | None
cache.put(key, value)   # None
cache.discard(key)      # None; a missing key is harmless
cache.clear()          # None
```

- Operations are synchronous and process-local.
- Store and return Python objects directly. Do not convert them to JSON, strings or bytes, and do not attach a Pydantic model or TypeAdapter to this cache.
- Use cachetools `TTLCache` for the caches currently required. It provides LRU eviction plus per-entry expiration measured from insertion/update. Reading an entry does not extend its TTL.
- TTL is required for the current instances. Do not add `ttl=None` or a configurable backend choice without an actual use case.
- Capacity is bounded by entry count. Choose explicit capacities during implementation using representative payloads; do not imply that entry count is equivalent to the current serialized-payload byte budget.
- Separate neutral Word metadata, neutral Sense objects and artifact objects into their own instances. Integer IDs are sufficient within each neutral instance. Do not put themed data under neutral keys; keep existing themed behavior outside this optimization.
- Cache detached data transfer objects and UUIDs, not live ORM entities or database sessions.
- Treat cached DTOs as read-only shared objects. A caller that needs to mutate data must create its own mutable collection/value.
- Do not add blanket deep copies. Pydantic `frozen=True` does not make nested lists/dictionaries immutable; inspect consumers and protect their read-only behavior with focused regression checks. The audit has not established an existing production mutation bug.
- Clear owned memory caches during process-resource cleanup.

The existing ContentCache limits serialized payload bytes and expires entries after 30 seconds. Replacing it deliberately changes storage and object-sharing semantics; keep expiration and validate the replacement's actual memory footprint rather than silently claiming an equivalent byte limit.

## Part 2: neutral content caching

### Approved representation

Use the existing infrastructure `MemoryCache` without adding methods, loaders, cache decorators or a replacement `ContentCache` class:

```python
word_cache: MemoryCache[int, CachedWord]
sense_cache: MemoryCache[int, Sense]
```

`CachedWord` is a detached Pydantic dataclass containing `id`, `lemma`, `type`, `generation_state`, `aliases`, `related` and the ordered `sense_ids`. It does not contain Sense objects. Use `Sense` directly, without a `CachedSense` alias or a second family of cached child classes.

Convert the existing retained lexical DTOs (`Sense`, `Definition`, `Example`, `Form`, `SenseRelation` and `WordRelation`) to Pydantic dataclasses with `slots=True`, `frozen=True` and forbidden extra fields. Use tuples for their nested collections and for the collections in `CachedWord`. Keep field validation, aliases, defaults and public JSON shapes. Patterns and collocations remain strings, not new wrapper classes. Other request, PATCH, configuration and LLM schemas remain BaseModels.

Keep TypeAdapters at lexical validation/serialization boundaries and construct them once. Update affected `model_validate`, `model_dump` and `model_copy` callers using adapters or `dataclasses.replace`; do not reconstruct a duplicate BaseModel graph on cache hits. Response trimming creates a separate value and never changes retained tuples or shared children.

Do not implement scalar deduplication, global interning, identical-child pooling or extra hydration queries to enable sharing. The measured tuple/slotted representation without scalar deduplication retained about 59.7 MiB RSS for all 4,591 DONE Words and 19,388 Senses from the local content database. Scalar deduplication saved about 6.9 MiB more and was explicitly rejected as unnecessary complexity. This full-residency measurement is not a preload requirement, production memory bound or approval of cache capacities. Do not cache PENDING Word metadata.

Keep the public `Word` response model unchanged: it still contains `senses: list[Sense]`. Assemble it from cached metadata and the shared Sense objects when needed, without deep-copying them or keeping the assembled Word in the cache. This avoids retaining a second set of Sense objects inside cached Words. Requests already holding an older object may retain it until they complete; this is not process-wide object interning.

Theme integration is deferred. Preserve existing themed reads and validation through their existing uncached path rather than introducing themed keys into these neutral caches or removing theme support.

### Read paths

- `get_senses()` already exists in `vocabulary/words.py`. Keep its hit/miss handling, missing-ID deduplication, bounded SQL batching and requested ordering. Pass it the neutral Sense cache; do not reimplement those behaviors inside `get_word()`.
- On a Word metadata hit, `get_word()` calls `get_senses(sessions, cached.sense_ids, cache=sense_cache)` and constructs the existing public Word response. A complete cache hit performs no SQL; a metadata hit alone does not guarantee all Sense entries are resident.
- On a Word metadata miss, use the existing complete Word read, populate its Senses into `sense_cache` and store only its metadata and ordered Sense IDs in `word_cache`. Reuse those Sense instances in the immediate response.
- If a requested Sense no longer exists in PostgreSQL, discard the stale Word metadata and perform one authoritative Word reload. Preserve the existing missing-Word result; do not silently return an incomplete Word or retry indefinitely.
- Keep the complete-Word publication checks (`DONE`, available senses) and the existing direct-Sense read contract. A refactor must not silently make direct Sense reads require loading a complete Word.
- Do not add a `sense_id -> word_id` query to serve a Sense cache hit. Direct Sense reads do not require Word metadata.

### Consumer integration after the cache design

| Consumer | Existing lexical read | Required integration |
| --- | --- | --- |
| `GET /v1/words/{word_id}` and Word generation | Complete Word with the initial shared content cache | Use the separate Word/Sense instances through `get_word()` |
| `POST /v1/words:batchPreview` | Word IDs and complete Sense groups, currently without cache | Pass the relevant caches and preserve complete groups and response trimming |
| Library, Discovery, flashcards and Assistant library reads | SQL selects a page of Sense IDs; preview fields and optional examples are hydrated without cache | Reuse neutral content caches for hydration after authoritative selection |
| `POST /v1/study:prepare` | SQL selects Sense IDs; full Senses and lemma are hydrated without content cache | Pass content caches independently of the already-used artifact cache |
| Assistant `search_words` / `read_vocabulary` | Compact preview SQL plus cached full Senses for optional examples/lexical details | Reuse the neutral caches while preserving include behavior and batch bounds |

Permission, membership, visibility, filtering, ordering, learning-state selection and learner-specific results remain authoritative SQL operations. Do not cache an entire personalized response under a Word/Sense key. Existing compact projection queries must be considered separately from full DTO hydration; do not claim that a Sense payload hit removes every query in these operations.

### Ownership, expiration and invalidation

- Construct and clear both instances in `process_resources()`. Update runtime/dependency protocols, generation and other callers together.
- Give Word metadata and Sense objects separate `max_entries` and `ttl_seconds` nodes under `runtime.caches.words` and `runtime.caches.senses`. Both initial TTLs are 30 seconds. The initial mixed `runtime.caches.content` policy is removed.
- Keep artifact cache storage and its configuration independent, keyed by artifact ID. Artifacts are not part of `CachedWord` or `Sense`.
- After committed lexical mutations, initially clear both Word and Sense caches in the writing process. Clear artifact cache too when the mutation affects artifacts. Do not invalidate on a rolled-back transaction. Other processes remain bounded by TTL; distributed invalidation is outside this phase.
- Cache values and their nested collections are shared read-only data. A response that trims examples must use a new list/response value.
- Initial implementation capacities are 5,000 Word metadata entries and 20,000 Sense entries per process, selected to fit the measured 4,591 DONE Words and 19,388 Senses. These are independently configurable entry limits, not byte budgets or preload targets; the old mixed-cache count of 512 is superseded.

### Measurement and acceptance

Measure retained Python allocations for Word metadata, Sense objects, cache structures and their combined total. Compare the initial complete-Word-plus-shared-Sense representation with normalized metadata/Sense storage for the same data and residency; do not assume normalization saves most RAM when the initial entries already share Sense references. Include an independently hydrated Sense scenario to expose possible duplicate retention.

Report the source, sample size, sense/example counts, JSON payload size, Python/library versions and measurement method. Separate actual local lexical rows, repository mock fixtures and synthetic scenarios. Replicated fixture content is a controlled workload, not a representative vocabulary distribution. `tracemalloc` retained allocations are not process RSS, a deployment memory ceiling or a production hit-rate estimate. Never choose final capacity from the earlier synthetic 25 MiB extrapolation.

Checks must cover a full Word hit without SQL, batched partial Sense misses through `get_senses()`, correct requested ordering, no retained full Word in `word_cache`, shared Sense identity during response assembly, independent expiration/eviction, deletion recovery and consumer non-mutation. Benchmarks do not establish these production contracts until the read-path refactor is implemented.

Verify slotted storage, frozen fields and tuple collections, invalid-input rejection, alias/default handling and unchanged public JSON. Keep exploratory benchmark scripts outside the repository; production regression checks belong in the existing test suites.

## Redis cache contract

```python
RedisCache[T](redis, model, prefix, ttl)

await cache.get(key)          # T | None
await cache.put(key, value)   # None
await cache.discard(key)      # None
```

- The Redis client, payload type, prefix and positive TTL are fixed when constructing an instance.
- Create and reuse instances in `process_resources()`. Callers do not repeat the model, prefix or TTL for each operation. Logical instances share the owned Redis client.
- Create a Pydantic `TypeAdapter` once per instance so both UUIDs and Pydantic model payloads are supported without wrapper models.
- Serialize with `TypeAdapter.dump_json()` directly to bytes, and read with `validate_json()`. Avoid JSON-to-text-to-bytes conversions.
- A missing value, malformed payload or Redis read failure produces a cache miss with the existing sanitized logging behavior.
- Redis write/invalidation failures are best-effort and logged. Do not hide caller serialization/programming errors as successful cache writes.
- The generic cache does not query PostgreSQL, invoke loaders or implement cache-aside.
- Keep Redis connection/read deadlines explicit at resource construction. Review the current five-second deadlines before using this wrapper on latency-sensitive optional-cache paths; no new timeout value has been approved yet.

Reset payload schema versions to `v1` under new logical prefixes. Preserve environment/database/Clerk-issuer isolation. Do not reuse an incompatible old payload namespace or flush shared Redis:

```text
pycil:<scope>:cache:<resource>:v1:<key>
```

The `user_id` mapping in this phase uses memory, not this Redis wrapper.

## Required Redis state is separate

Generation task status currently accesses `.redis` and `.key()` through RedisCache. Give it the native Redis client and its own isolated prefix instead of borrowing an optional typed-cache instance. Preserve its required write/read failure behavior, retention semantics and cross-instance polling.

Assistant leases, rate limiting and other coordination must also keep their existing correctness behavior. Do not convert their failures into optional cache misses, reset their key versions indiscriminately, or make coordination state evictable as part of this refactor.

## Approved configuration design

The repository-wide scout is complete. Its source inventory and hardcoded-value findings are recorded in the [configuration scout](plans/reports/configuration-scout-2026-10-15.md). That report is an investigation record; the approved decisions below are the implementation direction. The report lives under the currently Git-ignored `plans/` directory, so retain the decisions needed to execute in this root document.

### Ownership and hierarchy

Keep one backend configuration file, `config/config.yaml`, with two top-level sections. `product` describes supported product behavior and limits; `runtime` describes how the application executes that behavior. Do not introduce per-domain YAML files or an include system.

```text
config/config.yaml
  product
    account
      preferences                 # defaults and supported choices
      plans                       # grants and allowance policy
    study
      defaults / limits / pair_levels / mastery / fsrs
      artifacts                   # correct/distractor counts and output policy
    vocabulary
      generation                  # examples and lexical output policy
      search                      # supported default search behavior
    assistant
      defaults / limits / models  # preferences, content bounds and accounting rates
    library
      quotas / pagination
    projections                   # bounds on data assembled for reads
  runtime
    caches
      user_id / words / senses / artifacts  # independent ttl_seconds and max_entries
    generation                    # concurrency, queues, deadlines, retention, batches
    assistant                     # execution deadlines, leases and admission controls
    providers                     # provider models and transport/retry policy
    database
      application_pool / checkpoint_pool
    redis                         # connection and operation deadlines
    identity                      # Clerk profile/JWKS operational timing
    search                        # index rebuild and writer resources
    library                       # SQL and scope execution budgets
    http                          # application body limit and needed client budgets
    health                        # readiness deadlines
    lifecycle                     # resource cleanup budget
```

This tree defines ownership, not a requirement to add empty sections or expose every library option. Add a leaf only for an existing, supported tuning need. Reference import batching may have an operator-owned config/CLI boundary if the actual invocation warrants it; do not invent a new worker to justify a setting.

`projections` is the established name for selecting and assembling data for a read result. Keep it in both the configuration and existing code. Its settings cover such values as maximum returned senses and inline examples/sources. Do not rename it to `responses` or infer that a projection requires event sourcing, a separate database or materialized views.

Other configuration owners remain explicit:

| Owner | Responsibility |
| --- | --- |
| `config/config.yaml` | Canonical non-secret backend product/runtime policy. |
| `apps/web/src/config.ts` | Small typed public frontend policy, grouped by query, requests, polling, pagination, study and auth where needed. |
| Deployment environment and its validation/example files | Secrets, service addresses, paths and explicit environment choices. |
| Docker/Compose/Caddy manifests | Process/container resources, ingress and deployment lifecycle controls. |
| CI, test configuration and E2E harness | Test timeouts, concurrency, deterministic ports and isolated fixtures. |

Frontend code must reuse the existing locale registry and policy already exposed by API responses where appropriate. Do not import the backend YAML into the browser, duplicate server limits unnecessarily, add a public configuration endpoint, or build a generated cross-language export pipeline for this change.

### Migration of current settings and hardcoded values

- Move plan grants/allowances into `product.account.plans` and account defaults/supported choices into `product.account.preferences`.
- Move learning defaults, limits, pair levels, mastery and FSRS into `product.study`. Separate study artifact output counts from generation execution batches.
- Move vocabulary examples-per-sense policy into `product.vocabulary.generation`; move job deadlines out of the old mixed generation policy into `runtime.generation`.
- Group assistant defaults, content limits and model catalog/rates under `product.assistant`; keep execution deadlines, leases and rate admission under `runtime.assistant` and provider transport/retry policy under `runtime.providers`.
- Split library quotas/pagination from SQL/scope execution budgets. Retain shared read-result bounds in `product.projections`.
- Replace actor TTL with the independent cache policies below. Add explicit measured entry capacities rather than carrying over the old serialized-byte limit as an entry count.
- Give currently hardcoded job concurrency (8 active / 16 pending per process), task-status retention (86,400 seconds), tool wait cap (30 seconds) and enrichment batch target (8) an explicit runtime owner. Preserve the supported enrichment schema ceiling and derive the tool wait as the minimum of its cap and job deadline.
- Give existing connection timeouts, database/checkpoint pool budgets, assistant lease timing, search rebuild/writer resources and cleanup timing an explicit runtime owner where tuning is supported. Preserve current behavior; do not silently retune implicit native-client defaults.
- Consolidate shared frontend query freshness/GC/retry settings, request timeout overrides, generation polling, pagination and study-session behavior. Retain their current values and separate independent meanings even when their numbers match, such as an API request timeout and an auth loading fallback.
- Remove the eight duplicated projection defaults and four duplicated learning-limit defaults from Python. Required configuration values belong in YAML; user preference initialization remains supported behavior.

Do not convert every literal into configuration. Keep schema/key versions, JWT algorithms/required claims, protocol enums, database column constraints, supported schema ceilings, SQLSTATE classifications and algorithm/unit-conversion constants in code. Consolidate repeated implementation values under a named owner only when useful. Derive values such as lease renewal `TTL / 3` and query sentinels `limit + 1` from their governing setting.

### Typed models, loading and injection

- Keep `app/config.py` as the loader and composition boundary. Use a root `AppConfig` with typed `product` and `runtime` sections; update imports, state protocols and consumers together.
- Keep domain policy models in the existing domain `config.py` modules and shared validation primitives in `infrastructure/configuration.py`. Do not create a separate module for every YAML node.
- Pass the relevant domain/product policy to business operations and runtime policy to resource construction. Infrastructure primitives receive concrete constructor values rather than a global config singleton or HTTP request.
- YAML owns configured values; Python owns types, supported constraints, cross-field validation and derived behavior. Do not add fallback constructor values that silently bypass required file settings.
- Preserve rejection of duplicate keys, unknown fields, invalid types/enums and invalid cross-field combinations. Missing required settings fail at startup. Preserve sanitized errors that do not reveal credentials or full configuration values.
- Load configuration once and treat it as immutable. `CONFIG_PATH` selects the file; process restart applies backend changes. Public frontend configuration changes require the normal browser build/redeploy.
- Do not introduce YAML environment interpolation, per-leaf environment override machinery, hot reload, a generic settings registry or backend-selection framework.
- Update production, CLI, test and deployment construction paths together. Migration commands must not acquire unrelated live API resources merely to read configuration.

### Required English comments

Every configurable leaf must have adjacent detailed English comments explaining:

1. Purpose and consuming operation.
2. Unit and scope: for example seconds versus milliseconds, per process versus per user, and deadline versus retention versus freshness.
3. Meaning of the configured value, accepted range/enum and `0`/`null` behavior when supported.
4. Effect of increasing/decreasing the value, including relevant memory, freshness, latency, quality or cost trade-offs.
5. Related limits/constraints and when a change takes effect.

Apply this convention to backend YAML, shared frontend settings, and environment/deployment settings changed by the refactor. For repeated model catalog entries, a shared field explanation may cover identical semantics, but explain each entry's distinct meaning and values. Do not copy an entire manual per model or leave configurable fields unexplained.

Correct the existing model-rate comment against the actual metering formula and rounding, with a verified worked example. Do not assume that a comment saying USD per million tokens defines the accounting scale, and do not change configured rates or allowances as part of reorganizing them.

### Preserve behavior and resolve mismatches explicitly

The first migration preserves configured values, grants, rates, learner behavior and public API shapes. The scout found decisions that must be resolved with source/caller evidence before changing their behavior:

- Dictionary inputs allow 512 characters while search accepts 256. Choose a consistent supported contract; do not automatically expand the backend limit.
- A word-context query uses literal 101 next to configured `max_context_senses: 100`. Derive the lookahead bound from the policy if it is the same contract.
- Assistant example slices of one/two coexist with configured inline examples. Verify intentional differences before consolidating or defining separate named budgets.
- CORS currently appends localhost origins even when configured origins are supplied. Make ownership explicit; changing which origins are accepted requires a deliberate decision and coverage.
- Memory entry capacities require representative object-memory measurements. No final entry counts have been approved.
- Import/relation batching needs a real supported operator invocation before gaining a new configuration surface.

Keep deployment relationships checked and documented, including application/ingress body limits, application cleanup versus server/container shutdown budgets, and pool/concurrency budgets per process multiplied by worker count. Preserve rejection and required failure handling at each boundary.

## TTL configuration

TTL belongs in the canonical validated configuration, separately for each logical cache. Remove `actor_ttl_seconds` completely, including schema, callers, fixtures and documentation. The approved initial policies are:

| Logical cache | Initial TTL | Meaning |
| --- | --- | --- |
| User ID mapping | 60 seconds | Maximum residence after insertion/update before identity mapping must be resolved again. |
| Word metadata | 30 seconds | Bound stale Word metadata and Sense IDs between processes. |
| Senses | 30 seconds | Independently bound stale Sense content between processes. |
| Question artifacts | 30 seconds | Independently bound stale artifact values. |

The approved representation within the new hierarchy is:

```yaml
runtime:
  caches:
    user_id:
      # Lifetime in seconds of a verified clerk_id -> user_id mapping per
      # API process, measured from insertion/replacement; reads do not renew it.
      # 60 means the next access after one minute resolves the mapping again.
      # Integer > 0. Higher values reduce SQL lookups but retain stale mappings
      # longer; the mapping does not grant authorization. Restart to apply.
      ttl_seconds: 60
    words:
      # Word metadata and Sense-ID freshness per API process, in seconds.
      # Measured from insertion/update, not renewed by reads.
      # 30 bounds stale content without distributed invalidation. Integer > 0.
      # Higher values reduce reads but retain stale values longer. Restart to apply.
      ttl_seconds: 30
    senses:
      # Sense DTO freshness per API process, in seconds from insertion/update.
      # 30 is independent of Word metadata residence. Integer > 0.
      # Higher values reduce reads but retain stale values longer. Restart to apply.
      ttl_seconds: 30
    artifacts:
      # Question artifact DTO freshness in seconds per API process after insertion.
      # 30 is independent of lexical content freshness. Integer > 0.
      # Higher values reduce reads but retain stale values longer. Restart to apply.
      ttl_seconds: 30
```

Each cache node also requires its own positive `max_entries`. The implementation selects 5,000 Words and 20,000 Senses from the local full-DONE-corpus measurement; see the Part 2 capacity rationale above. The example records only TTLs; `config/config.yaml` owns the current capacities. The old flat `cache.*_ttl_seconds` proposal is superseded by this hierarchy; remove the old root `cache` section and `actor_ttl_seconds` without compatibility aliases.

Keep authoritative values in YAML, not duplicated Python constructor defaults. Validate positive TTLs/capacities at startup, pass them once during resource assembly, and apply changes through the normal process restart.

Do not add profile/settings/plan TTL settings before those caches exist. Generation status retention and lease timing are separate operational policies, not these read-cache TTLs.

## Implementation reach

Review and update the affected contracts together:

- Account identity resolution, optional authentication, provisioning, lifecycle and profile/settings/plan reads.
- ORM field, SQL queries, provisioning conflict targets, applicable database migration, uniqueness and data preservation.
- API dependency annotations and downstream account, library, vocabulary, study and assistant consumers.
- Assistant profile/context rendering that currently reads display name/handle from ActorContext.
- Infrastructure cache primitives; vocabulary/artifact read paths and their invalidation after committed writes.
- Runtime state, dependency protocols, process-resource assembly and cleanup.
- Generation task status and its resource wiring.
- Root/domain configuration models, YAML policy, configuration injection and validation, independent cache settings and removal of actor TTL.
- Frontend shared configuration, its production callers and environment parsing; preserve server/browser and public/secret boundaries.
- Existing CLI, Docker/Compose/Caddy, test and E2E wiring affected by configuration moves; preserve their separate ownership.
- Unit/integration fixtures, identity tests, cache tests, E2E identity/seed helpers and cache namespace assumptions.
- Observability user ID field names and affected owning documentation.

Preserve unrelated working-tree changes. For an existing database whose data must survive, use a proper column rename migration rather than only editing an already-applied baseline. Reconcile the repository's baseline workflow explicitly when implementing the rename.

## Execution order

1. Completed: repository-wide configuration scout and user approval of the product/runtime hierarchy, separate frontend ownership and comment convention. Keep `projections`.
2. Completed: consolidate the approved configuration design and caching decisions in this root document. Implementation remains a separate step from recording this plan.
3. Before changing behavior, resolve remaining contract questions above, measure cache capacities, and confirm the data-preserving schema migration path. Record evidence and exact decisions here; do not treat design approval as approval to invent new defaults.
4. Implement the backend typed hierarchy and YAML comments together with resource/domain callers, required settings and validation. Make the cache settings and cache/user changes as connected steps so the application remains runnable; preserve existing migration constraints.
5. Consolidate shared frontend settings and update connected callers. Align affected environment/deployment/CLI/test wiring and verify budget relationships without moving those owners into backend YAML.
6. Run focused verification, broaden for shared contracts, review connected callers and update the smallest owning documentation surfaces. Record implementation progress and actual validation evidence separately from the approved design.

## Verification and acceptance

- A verified identity mapping memory hit returns the correct UUID with zero SQL, Redis or Clerk profile requests.
- Invalid tokens cannot use a warmed cache. Anonymous optional-authentication behavior remains correct.
- Misses, concurrent provisioning, identity-service failure and missing/deleted account handling preserve existing safety.
- Profile/settings/plan are fetched only by operations needing them; sensitive operations observe authoritative values.
- Memory tests cover hit/miss, replacement, TTL expiration, LRU eviction, discard, clear and independent content/artifact policies.
- Inspect cached DTO consumers and verify response/question construction does not mutate shared cached values.
- Real Redis integration covers UUID/model round trips, configured TTL, invalidation, corrupt data, wrong Redis types, namespace isolation and failure behavior.
- Required generation status retains cross-instance visibility and rejects the same failure cases rather than failing open.
- Configuration validates all required settings, rejects invalid values and no longer accepts the removed actor setting.
- Backend YAML has the approved product/runtime hierarchy; required configured defaults are not duplicated in Python. Each moved setting has detailed English comments and a clear typed owner.
- Configuration regression checks preserve existing grants, rates, defaults and limits, and cover cross-field constraints, unknown/duplicate keys, missing values and sanitized failures.
- Frontend shared settings retain existing query, request, polling, pagination and study behavior; reuse existing public limits/locale ownership and keep secrets out of browser configuration.
- Production/CLI/test/deployment construction paths consume the new structure consistently. Verify related body, shutdown and per-process resource budgets where affected.
- Schema migration preserves existing user IDs/data and Clerk ID uniqueness where data retention is required.
- Public API shapes and affected E2E setup contracts remain compatible apart from the explicitly approved internal terminology changes.
- Benchmark cache-only hits separately from database/business-operation paths. Compare equivalent values/workloads, report payload size and versions, and never label RAM-plus-SQL time as RAM cache lookup time.
- Measure representative memory consumption before selecting final entry capacities. Local timings are not a production throughput or p95/p99 claim.

Prior investigation ran seven existing cache/identity tests successfully. A local synthetic Word DTO benchmark showed that direct-object memory reads avoid JSON parsing overhead; blanket deep copies were slower than the JSON path for both tested payload sizes. Those checks verify the old implementation and exploratory alternatives, not the complete current refactor. No verified existing application mutation bug was found.

## Implementation evidence

The generic direct-object cache and normalized neutral Word/Sense read paths are implemented. `CachedWord` retains metadata and ordered Sense IDs; `Sense` and its retained children are frozen slotted Pydantic dataclasses with tuple collections. There is no scalar deduplication, cached-Sense alias, child-model clone family or memory-cache serialization. Batch previews, library examples, study preparation and Assistant lexical hydration use the separate Sense cache; themed reads bypass neutral caches. The earlier approximately 25 MiB claim was extrapolated from 1,024 synthetic Words with eight Senses and five long examples per Sense; it did not measure 512 real project Words. It is not a valid basis for selecting capacities.


### Neutral-content implementation checks

- The production classes were checked against all 4,591 DONE Words and 19,388 Senses from the read-only export of `../lexi-ai/data/content.sqlite`; every public Word JSON payload matched. The export was 24,678,831 bytes (SHA-256 `fb7d70c2ca4d431650cddb85f15294e48f691bc4fb68dd6548ccc2b652ed324f`). Source JSON was decoded independently with the standard-library JSON parser, with no database queries, scalar deduplication or child pooling.
- With Python 3.14.8, Pydantic 2.13.5 and cachetools 7.2.1 in a fresh process, garbage-collected RSS increased by 59.62 MiB while retaining the complete separate stores. Measurement used a 3,600-second TTL only to prevent expiry during the experiment; the configured application TTLs remain 30 seconds. This is a local full-residency observation, not an RSS cap or a hit-rate forecast.
- The entire generated OpenAPI document matched the preceding contract, including aliases, defaults and array shapes.
- Focused checks passed: 285 unit tests and 109 integration tests covering the connected vocabulary, generation, library, study, Assistant and resource-lifecycle paths. The complete backend run finished with 493 passes, two logging-capture failures and 12 upstream LangGraph deprecation warnings. The failures are `test_failed_call_preserves_known_charge_and_records_unknown_usage_safely` and `test_cancelled_provider_attempt_is_observed_without_retry`: both expect `structlog.testing.capture_logs()` to collect events after application logging has been configured; the events are emitted but the capture lists are empty. Both also occurred before this lexical change.
- Changed-file lint and formatting pass. The full-repository checks still report unrelated formatting in `tests/benchmarks/test_search_budgets.py` and `tests/integration/infrastructure/test_user_identity_migration.py`; their existing work is left intact. Browser E2E and deployment measurements were not run for this backend lexical change.
- Regression checks cover shared Sense identity, zero-SQL full hits, batched partial misses and ordering, independent caches, stale-Word deletion recovery, invalidation after commit rather than rollback, tuple/frozen/slot behavior and response trimming without mutation.


## Risks and rollback

- Shared mutable objects require read-only consumers; frozen outer models alone do not enforce deep immutability.
- Process-local invalidation does not invalidate other workers. Keep bounded TTLs and authoritative business checks.
- Entry limits are not byte budgets, and deployment replica count multiplies local cache memory.
- A database column rename must be coordinated with application rollout. Do not assume old/new application versions can share the renamed schema without a compatibility design.
- Keep schema/key changes isolated. Roll back an application and its schema deliberately; do not revive incompatible actor payloads under a new typed prefix or delete required coordination state.

Rollback details and final migration strategy must be finalized against the approved configuration plan and the actual deployment target before implementation.
