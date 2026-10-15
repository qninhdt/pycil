# Configuration

## Policy and deployment values

Backend product and runtime policy live in [config/config.yaml](../../config/config.yaml). Its loader is
[app/config.py](../../apps/api/pycil/app/config.py); domains own their policy models.
Unknown fields, duplicate YAML keys, invalid enum values, missing plans and infeasible
defaults fail validation. Policies are immutable. Restart processes after changes.

`CONFIG_PATH` selects the policy file. The default resolves relative to source;
the image sets `/app/config/config.yaml`. Credentials belong only in the environment.

## Runtime environment

[Deployment validation](../../apps/api/pycil/app/settings.py) owns this contract:

| Variable | Meaning |
| --- | --- |
| `DB_URL` | PostgreSQL application URL using `postgresql+asyncpg://`, with host and database |
| `REDIS_URL` | Explicit Redis server using `redis://` or `rediss://` |
| `CLERK_JWKS_URL`, `CLERK_ISSUER` | Required HTTP(S) signature-key endpoint and issuer |
| `CLERK_AUDIENCE` | Optional JWT audience verification |
| `CLERK_SECRET_KEY` | Required server-side identity lookup credential |
| `LLM_API_KEY`, `LLM_BASE_URL` | Required chat/structured generation provider credential and endpoint |
| `DECISION_API_KEY`, `DECISION_BASE_URL` | Required OpenRouter credential and complete Decisions endpoint |
| `ALLOWED_ORIGINS` | Optional comma-separated exact HTTP(S) origins |
| `CONFIG_PATH` | Optional backend configuration path |
| `SEARCH_INDEX_PATH` | Optional directory for the shared on-disk search index; in memory when unset |

Service URLs reject embedded credentials. Origins also reject paths, queries and
fragments. Direct commands need exported values or uv's explicit `--env-file`.
Never print resolved credentials or put them in policy files.

`DECISION_BASE_URL` is the full request URL, such as
`https://openrouter.ai/api/alpha/decisions`; Instructor does not append a path.
`runtime.providers.vocabulary.decision_model` is the OpenRouter model ID, including its
vendor prefix. Infrastructure selects Instructor's OpenRouter Decisions transport
without stripping that prefix from the model sent to the provider.

## Policy ownership

| Group | Owner and purpose |
| --- | --- |
| `product.account.preferences`, `product.account.plans` | Preference defaults/choices, feature grants and monthly allowances |
| `product.study` | Study defaults/limits, pairs, artifact output policy, mastery and FSRS |
| `product.vocabulary` | Generation examples and supported search behavior |
| `product.assistant` | Defaults, limits, model catalog/efforts and accounting rates |
| `product.library` | Quotas and pagination |
| `product.projections` | Bounded response assembly; includes inline examples/sources |
| `runtime.caches` | Independent user-ID, Word metadata, Sense and artifact TTL/entry capacities |
| `runtime.generation`, `runtime.assistant` | Concurrency, admission, deadlines, batches, status retention and leases |
| `runtime.providers`, `runtime.identity` | Provider/identity transport, JWKS and retry timing |
| `runtime.database`, `runtime.redis` | Per-process pools and connection/operation deadlines |
| `runtime.search` | Rebuild/writer resources, polling, retry, publication and progress budgets |
| `runtime.library`, `runtime.http`, `runtime.health`, `runtime.lifecycle` | SQL/scope, body/client, readiness and cleanup budgets |

Every YAML leaf has English comments describing purpose, units, range, configured value,
tuning effect and restart behavior. Values are required by typed `AppConfig`; there are
no flat-key aliases, YAML includes, environment interpolation or per-domain YAML files.
Schema versions, algorithms, protocol ceilings and operator/test fixture defaults remain
with their code owners. Provider retry timing is owned by `runtime.providers.vocabulary`.

Frontend public policy lives in [config.ts](../../apps/web/src/config.ts), separate from
backend YAML and secrets. Study answer length reuses the limit already supplied by `/me`.
Dictionary/picker inputs now respect the existing 256-character API ceiling. Expanded
assistant examples use `product.projections.inline_examples`; search snippets intentionally
keep one example. CORS keeps its existing localhost additions plus `ALLOWED_ORIGINS`;
this refactor does not change that access policy.

Memory caches store shared detached DTOs directly, with TTL measured from insertion/update
and LRU eviction by entry count. Neutral Word metadata and Senses have separate caches under
`runtime.caches.words` and `runtime.caches.senses`; themed reads bypass both. Retained lexical
DTOs are frozen slotted Pydantic dataclasses with tuple collections. Build separate response
values before trimming/enriching. The configured entry counts are not byte limits. Multiply memory,
connection pools, generation slots and queues by API process count. See the measured local
cache budget in [the implementation plan](../../caching.md#implementation-evidence).
Optional typed Redis caches bind model/prefix/TTL at construction and serialize bytes;
required task status, rate limits and leases retain native Redis failure behavior.

The application pool caps simultaneous connections at `size + max_overflow`; the separate
native checkpoint pool adds up to `max_size`. The application pool's `timeout_seconds`
bounds waiting for a free pool slot, not SQL execution or opening a new connection.
Checkpoint checkout uses psycopg's own timeout; application pool timeout settings do not
apply to it. Neither pool's maximum reserves that many PostgreSQL slots in advance.
Budget for every API process, rollout overlap and maintenance clients against the
server-wide connection limit. Restart with rebuilt images to apply baked policy changes.

## Compose

[scripts/compose.py](../../scripts/compose.py) derives `_DB_*` and `_REDIS_*` from canonical
URLs. Do not configure those internal keys. Loopback hosts become Docker service DNS;
remote addresses remain remote. The wrapper requires database credentials and a Redis
password. Only quiet Compose configuration validation is allowed.

Optional operator values include `API_IMAGE`, `API_HOST_PORT`, `DOMAIN`,
`CADDY_HTTP_PORT` and `CADDY_HTTPS_PORT`. The migration service imports the repository's
JSONL through a read-only mount. There is no runtime content seed configuration.
See [getting started](getting-started.md) and [deployment](operations/deployment.md).
