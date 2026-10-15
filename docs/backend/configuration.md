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
| `product.study` | Study defaults/limits, grading decision threshold, pairs, artifact output policy, mastery and FSRS |
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
| `runtime.telemetry.traces`, `runtime.telemetry.metrics` | Per-process trace queue/batches and trace/metric export timing |

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
`application_pool.connect_timeout_seconds` separately bounds opening a new asyncpg
connection. `checkpoint_pool.timeout_seconds` is the native default checkout deadline
(an explicit caller timeout overrides it); `startup_timeout_seconds` bounds waiting for
the minimum checkpoint connections at startup. These preserve the previous native defaults
of 60, 30 and 30 seconds respectively. They are not SQL execution timeouts, and application
pool settings do not apply to checkpoint connections. Neither pool's maximum reserves that
many PostgreSQL slots in advance.
Checkpoint startup timeout still joins native connection workers before raising, so
cleanup can finish after the configured waiting budget.
Budget for every API process, rollout overlap and maintenance clients against the
server-wide connection limit. Restart with rebuilt images to apply baked policy changes.

The shared DB owners record OTel histograms `pycil.db.pool.acquire.duration` for
both pools and `pycil.db.query.duration` for SQLAlchemy cursor execution, in seconds.
Acquisition includes queueing, connection opening and validation; it is not pure queue
wait. Cursor timing excludes acquisition, transaction commit/rollback and subsequent
streamed-result consumption. Dimensions are only `pool` (`application` / `checkpoint`)
and `outcome` (`succeeded` / `failed` / `cancelled`); SQL, parameters and connection
URLs are never recorded. Both instruments advise latency buckets from 1 ms to 5 s.
An OTel SDK/provider must be configured to collect/export them; the API alone is a
no-op until then. Tests use the real SDK with an in-memory reader and PostgreSQL.

### OpenTelemetry export

[SDK ownership](../../apps/api/pycil/infrastructure/observability.py) is entered once by
the API's existing resource lifecycle, before database/client initialization, and
closed after those resources. With no `OTEL_EXPORTER_OTLP_ENDPOINT`, no SDK/export
workers start. This also leaves migrations and ordinary local development without
an implicit collector dependency. A configured API process installs the global
providers once; replace the process to restart or reconfigure the SDK.

| Variable | Meaning |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional HTTP(S) base URL; export uses HTTP/protobuf at `/v1/traces` and `/v1/metrics`, retaining any base path |
| `OTEL_SERVICE_NAME` | Service identity, default `pycil-api` |
| `SERVICE_VERSION` | Required when exporting; actual immutable release tag or source SHA |
| `DEPLOYMENT_ENVIRONMENT` | Required when exporting: `local`, `vps-docker` or `aws-fargate` |
| `GIT_SHA` | Optional source commit, emitted as `vcs.ref.head.revision` |
| `OTEL_TRACES_SAMPLER_ARG` | Finite root trace sampling ratio, default `0.1`, range `0`–`1`; parent sampling decisions are respected |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional standard SDK resource attributes; explicit service/version/environment/instance fields above take precedence |

Endpoints reject embedded credentials, queries and fragments. This owner uses one
base endpoint and a fixed parent-based ratio sampler; per-signal endpoint overrides
and alternate sampler names are not configuration inputs. Each process receives a
fresh `service.instance.id`. Deployment manifests must explicitly forward these
variables; the existing base Compose configurations do not enable export automatically.

`runtime.telemetry.traces` configures the native batch processor queue, batch size,
schedule delay and exporter timeout. Validation rejects a batch larger than the queue.
`runtime.telemetry.metrics` configures collection/export interval, timeout and cooperative
shutdown budget. YAML uses seconds; the owner converts SDK millisecond arguments.
Configured defaults preserve the previous queue (2,048), batch (256), trace schedule
(5 seconds), metric interval (15 seconds) and export budgets (2 seconds).
Collector failures are handled by the SDK and
do not enter readiness checks. Queue overflow or process death can lose spans.
Shutdown runs off the event loop inside the existing application cleanup budget:
the native span processor has a fixed 30-second join budget, followed by the configured
metric reader shutdown budget (5 seconds initially). These are cooperative limits,
not preemption of blocked native/DNS code; the container stop deadline remains the hard bound.

Application body limits must agree with ingress/web upload bounds. Application cleanup must
fit inside server/container shutdown grace. Deployment owners remain Compose/Caddy; this
YAML does not configure processes, hosts or collector endpoints.

Controlled values serialize in lowercase `snake_case`, including plan keys, feature
names, question types, response formats and reasoning efforts. No uppercase aliases exist.
Use the policy itself for current numeric limits and rates rather than a second copy here.
Token rates are configured accounting inputs, not live pricing or invoice reconciliation.

Generation has one bounded retry policy per provider operation; SDK transport retries
are disabled. `structured_llm` passes that policy to Instructor's native retry engine,
which validates Pydantic responses and reasks with validation feedback. `decision_llm`
uses Instructor's native Decisions models and transport; its client currently has no
native retry engine, so infrastructure applies the same bounded policy around requests.
The deadline includes requests and backoff. Provider usage preserves unknown measurements
and includes failed attempts without counting cumulative reports twice. Application-owned
HTTP clients close at shutdown; their response hooks measure usage before parsing.
Retry diagnostics omit raw model output. Grading does not settle assistant allowance.
Generation prompts remain packaged in their owning modules; decision instructions live
in domain Pydantic models, without JSON-e templates.

## Compose

[scripts/compose.py](../../scripts/compose.py) derives `_DB_*` and `_REDIS_*` from canonical
URLs. Do not configure those internal keys. Loopback hosts become Docker service DNS;
remote addresses remain remote. The wrapper requires database credentials and a Redis
password. Only quiet Compose configuration validation is allowed.

Optional operator values include `API_IMAGE`, `API_HOST_PORT`, `DOMAIN`,
`CADDY_HTTP_PORT` and `CADDY_HTTPS_PORT`. The migration service imports the repository's
JSONL through a read-only mount. There is no runtime content seed configuration.
See [getting started](getting-started.md) and [deployment](operations/deployment.md).
