# Configuration

## Policy and deployment values

Backend product and runtime policy live in [config/config.yaml](../../config/config.yaml). Its loader is
[app/config.py](../../apps/api/pycil/app/config.py); domains own their policy models.
Unknown fields, duplicate YAML keys, invalid enum values, missing plans and infeasible
defaults fail validation. Policies are immutable. Restart processes after changes.

`CONFIG_PATH` selects the policy file. The default resolves relative to source;
the image sets `/app/config/config.yaml`. Credentials belong only in the environment.

## Runtime environment

[Settings validation](../../apps/api/pycil/app/settings.py) owns this contract.
`ProcessSettings` defines common environment values; `ApiSettings` and `WorkerSettings`
are separate role-specific models. The API additionally requires Clerk and decision
settings and parses CORS origins. Workers require none of those API-only values.
Shared telemetry and broker setup accept `ProcessSettings`. Environment variable
names remain the same.

The following table describes the API environment:

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
`vocabulary.provider.decision_model` is the OpenRouter model ID, including its
vendor prefix. Infrastructure selects Instructor's OpenRouter Decisions transport
without stripping that prefix from the model sent to the provider.

## Policy ownership

| Group | Owner and purpose |
| --- | --- |
| `account` | Preference defaults/choices, feature grants, monthly allowances and JWKS timing |
| `study` | Study defaults/limits, grading decision threshold, pairs, artifact output policy, mastery and FSRS |
| `vocabulary` | Lexical search, preview limits, generation examples, search worker runtime and provider settings |
| `assistant` | Defaults, limits, model catalog/efforts, accounting rates and lease timing |
| `library` | Quotas, pagination, SQL/scope budgets and membership limits |
| `jobs` | Native job execution deadline, domain-lock expiry and temporary result TTL |
| `system` | Database pools, Redis, in-memory caches, HTTP boundaries, health budgets and OpenTelemetry |

Every YAML leaf has English comments describing purpose, units, range, configured value,
tuning effect and restart behavior. Values are required by typed `AppConfig`; there are
no flat-key aliases, YAML includes, environment interpolation or per-domain YAML files.
Schema versions, algorithms, protocol ceilings and operator/test fixture defaults remain
with their code owners. Provider retry timing is owned by `vocabulary.provider`.

Frontend public policy lives in [config.ts](../../apps/web/src/config.ts), separate from
backend YAML and secrets. Study answer length reuses the limit already supplied by `/me`.
Dictionary/picker inputs now respect the existing 256-character API ceiling. Expanded
assistant examples use `vocabulary.preview.inline_examples`; search snippets intentionally
keep one example. CORS keeps its existing localhost additions plus `ALLOWED_ORIGINS`;
this refactor does not change that access policy.

Memory caches store shared detached DTOs directly, with TTL measured from insertion/update
and LRU eviction by entry count. Neutral Word metadata and Senses have separate caches under
`system.caches.words` and `system.caches.senses`; themed reads bypass both. Retained lexical
DTOs are frozen slotted Pydantic dataclasses with tuple collections. Build separate response
values before trimming/enriching. The configured entry counts are not byte limits. Multiply memory,
connection pools and caches by API process count. See the measured local
cache budget in [the implementation plan](../../caching.md#implementation-evidence).
Optional typed Redis caches bind model/prefix/TTL at construction and serialize bytes;
required rate limits and leases retain native Redis failure behavior.

The [observed in-memory backend](../../apps/api/pycil/observability/stores.py) extends
the plain infrastructure store and emits OTel instruments from `pycil.store` through the existing SDK:
`pycil.store.requests` counts reads with `outcome=hit|miss`, and `pycil.store.evictions`
counts only native LRU capacity removals. TTL expiry, explicit discard/clear and replacing
an existing entry do not count as capacity evictions. Internal eviction reads are not
application cache hits. Composition supplies bounded `store` names with `backend=memory`: `word`, `sense`, `artifact`
and `user_id`; keys, content and user identifiers never become attributes.
`pycil.store.entries` and `pycil.store.capacity` are gauges in entries, not bytes.
Entries are sampled after store mutations; an idle/read-only cache can retain its
last reported count after TTL expiry until the next mutation. Reads do not scan or
purge expired entries for telemetry. There is no extra callback, thread or exporter.
Optional Redis cache instrumentation is outside these process-local measurements.

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

The existing `observe_operation` boundary emits `pycil.operation.duration`, a
histogram in seconds, alongside its completion log. Its only metric attributes are
`operation` and `outcome` (`succeeded`, `failed`, `cancelled`, and stream-only
`interrupted`). Current callers use fixed names: `word_generation`,
`artifact_generation`, `grading` and `assistant_stream`. Identifiers,
artifact types, prompts, answers, provider output and exception text are not metric
attributes. Histogram counts supply operation counts; no separate counter or span
is added. An artifact generation measurement covers context retrieval, provider
work and validation, and storage through completion. A sufficient existing bank
does not invoke generation and adds no generation sample. A provider response alone
does not determine success: unusable output or a storage failure fails the operation.
These durations overlap child HTTP/SQL work and must not be summed with it.

The [AG-UI observation](../../apps/api/pycil/observability/ag_ui.py) measures the
native assistant event stream through source closure, excluding subsequent usage
settlement and conversation cleanup. It reads native terminal events: an approval
interrupt is `interrupted`, a run error is `failed`, and closing an unfinished
stream is `cancelled`. Exhaustion without a terminal event is `failed`; HTTP 200
alone does not imply success. Events and cancellation propagate unchanged, and
no additional span or protocol event is created. Detailed LangGraph/model/tool
tracing remains deferred to the future Langfuse integration.

Tantivy's [observed index](../../apps/api/pycil/observability/search.py) emits
`pycil.search.duration` in seconds through the existing SDK. Attributes are the
fixed index name (`dictionary`), operation (`query`, `synchronize`, `rebuild`,
`publication_wait`) and outcome (`succeeded`, `failed`, `cancelled`, `rejected`,
`idle`). Only empty synchronization polls use `idle`; query validation uses
`rejected`. Histogram counts supply operation counts without a duplicate counter.
Query duration includes validation, readiness and query execution; synchronization
duration covers one poll/batch, and publication waiting ends when the reader sees
the requested revision. These durations overlap and must not be summed. Query text,
content, revision IDs, paths and exception text are not attributes.

`pycil.search.pending_age` is an observable gauge in seconds, labeled only by
`index`. Only the writer owner emits it. It uses the creation timestamp of the
first unapplied revision in publication order from the most recent successful
owner poll. Its age advances with a monotonic clock during slow work or poll
failures; a successful empty poll resets it to zero. Collection reads memory only,
without SQL, index access or a new polling task. It is a sampled view: after a batch
commits, its last observation can remain until the next successful poll. The age
starts at revision creation, not the exact transaction commit time. Before the
first successful poll, after ownership loss, or after shutdown there is no sample;
absence does not mean zero. Use synchronization failures and readiness alongside
this gauge when PostgreSQL is unavailable. No exact backlog count is collected.

[SDK ownership](../../apps/api/pycil/observability/__init__.py) is entered once by
the API and worker resource lifecycles, before database/client initialization, and
closed after those resources. With no `OTEL_EXPORTER_OTLP_ENDPOINT`, no SDK/export
workers start. This also leaves migrations and ordinary local development without
an implicit collector dependency. A configured API process installs the global
providers once; replace the process to restart or reconfigure the SDK.

| Variable | Meaning |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional HTTP(S) base URL; export uses HTTP/protobuf at `/v1/traces` and `/v1/metrics`, retaining any base path |
| `OTEL_SERVICE_NAME` | Service identity, default `pycil-api` for API and `pycil-worker` for workers |
| `SERVICE_VERSION` | Required when exporting; actual immutable artifact identity (for example, image digest or local image ID) |
| `DEPLOYMENT_ENVIRONMENT` | Required when exporting: `local`, `vps` or `aws` |
| `GIT_SHA` | Optional source commit, emitted as `vcs.ref.head.revision` |
| `OTEL_TRACES_SAMPLER_ARG` | Finite root trace sampling ratio, default `0.1`, range `0`–`1`; parent sampling decisions are respected |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional standard SDK resource attributes; explicit service/version/environment/instance fields above take precedence |

Endpoints reject embedded credentials, queries and fragments. This owner uses one
base endpoint and a fixed parent-based ratio sampler; per-signal endpoint overrides
and alternate sampler names are not configuration inputs. Each process receives a
fresh `service.instance.id`. Deployment manifests must explicitly forward these
variables; the existing base Compose configurations do not enable export automatically.

`system.telemetry.traces` configures the native batch processor queue, batch size,
schedule delay and exporter timeout. Validation rejects a batch larger than the queue.
`system.telemetry.metrics` configures collection/export interval, timeout and cooperative
shutdown budget. YAML uses seconds; the owner converts SDK millisecond arguments.
Configured defaults preserve the previous queue (2,048), batch (256), trace schedule
(5 seconds), metric interval (15 seconds) and export budgets (2 seconds).
Collector failures are handled by the SDK and
do not enter readiness checks. Queue overflow or process death can lose spans.
Shutdown runs off the event loop inside the existing application cleanup budget:
the native span processor has a fixed 30-second join budget, followed by the configured
metric reader shutdown budget (5 seconds initially). These are cooperative limits,
not preemption of blocked native/DNS code; the container stop deadline remains the hard bound.

HTTP requests use the official OTel ASGI middleware through the existing FastAPI
assembly. It receives a sanitized telemetry scope: route templates (or `unmatched`),
bounded methods and a fixed service host. The application still receives the original
scope for routing, authentication, headers and bodies. FastAPI's native telemetry
and environment-based SDK auto-configuration are disabled so this boundary and the
existing resource owner remain the sole HTTP/SDK owners. Only trace propagation headers
reach the telemetry scope; body/query/header capture is disabled. Do not additionally
enable FastAPI/ASGI auto-instrumentation, which would duplicate server spans.

With the default HTTP semantic conventions, `http.server.duration` is a histogram
in milliseconds (its count supplies completed requests) and
`http.server.active_requests` tracks in-flight requests. Duration dimensions use
templated `http.target`; spans also carry `http.route`. No extra per-request counter
duplicates the histogram count. Per-message ASGI send/receive spans are excluded.
HTTP completion is not proof that a streamed business operation succeeded.

Structured logs include current valid trace/span IDs, even when a span is unsampled;
outside a trace they omit these IDs. Configured service/version/environment fields
are added by a processor, independently of cleared request context. Request logs use
`route` rather than raw `path`. HTTPX/HTTPCore transport diagnostics below WARNING
are suppressed because they include raw URLs. Logging setup disables `uvicorn.access`
because its native messages contain raw paths/queries; sanitized completion events
supply request logs. Keep `--no-access-log` in the server command as well.

Application query spans use native `engine.sync_engine` cursor events in the
[observed database boundary](../../apps/api/pycil/observability/database.py) and the process-owned OTel SDK. The pinned contrib instrumentation `0.66b0`
declares SQLAlchemy `<2.1.0`, while this application uses `2.1.3`; it is not installed
and its dependency check is not bypassed. Do not add overlapping SQLAlchemy/asyncpg
auto-instrumentation to these hooks.

Each cursor execution produces one CLIENT span under the active request/operation.
Names and `db.operation.name` use a bounded operation set, falling back to `SQL`;
`db.system.name` is `postgresql`. Failure/cancellation ends the span with ERROR and
only the exception class in `error.type`. SQL text, bind values, connection URLs,
result content and exception messages/stack traces are never added. The span covers
the cursor round trip, excluding pool acquisition and later result consumption;
use the existing acquisition histogram to investigate the earlier wait. An executemany
call is one execution span, not one span per row. SQL statements hidden inside the
driver and transaction completion are outside this boundary.

The separate checkpoint pool sets psycopg's public `cursor_factory` to
[`ObservedPsycopgCursor`](../../apps/api/pycil/observability/database.py). Its `execute`
and `executemany` calls create CLIENT spans through the same SDK under the active
request/operation, with instrumentation scope `pycil.database` and `pycil.db.pool=checkpoint`. Each call has one
span, including an executemany batch. String queries use the same bounded operation
set; bytes, SQL composables and templates fall back to `SQL` without rendering input.
Attributes include `pycil.db.pool=checkpoint` and `pycil.db.execution.mode` (`direct`
or `pipeline`). Only the operation, PostgreSQL identity, execution mode and error
class are recorded; statement/parameter/result content and exception text/events
are excluded. Errors and cancellation are re-raised unchanged. Native row factories,
binary cursors, prepared statements and pipeline behavior remain owned by psycopg.

These spans measure driver calls after checkout, not PostgreSQL server execution time.
LangGraph's pipeline writes can enqueue work before synchronization; their spans
may end before the database finishes, and errors first raised on later sync/fetch
are outside the earlier execute span. An unset span status is not proof that the
pipeline committed successfully. Inspect the enclosing assistant/request outcome
for that result. Pool acquisition remains a separate histogram. Migration-only
connections and native fetch/sync/commit operations do not get separate spans.
Do not enable additional psycopg auto-instrumentation on this pool: the contrib
DB-API integration captures SQL text and would duplicate this boundary.

The shared HTTPX client (Clerk profile reads, structured/decision LLM calls) and
assistant's OpenRouter async client use `ObservedAsyncClient` in the existing
[observed HTTP boundary](../../apps/api/pycil/observability/http.py). It delegates
public `AsyncClient.send` calls to HTTPX with the original request/options and creates
one CLIENT span per send under the current context, using scope `pycil.http.client`.
Redirects/auth flows inside one send are not separate spans. Existing provider retries
produce separate send spans; instrumentation adds no retries, providers or workers.
The assistant owns and closes its supplied async client; SDK retry/timeout policy and
redirect behavior are preserved.

Only bounded method names (`_OTHER` for unknown methods), status codes,
`pycil.http.stream` and error classes/status codes are recorded. URLs, hosts, headers,
payloads and exception text/events are never attached. The native HTTPX instrumentor
collects URL attributes before its request hook, so it is not enabled alongside this
boundary. No propagation headers or baggage are automatically sent to external services.
HTTP error responses remain responses; transport failures and cancellation are re-raised
unchanged after closing the span with ERROR.

Duration covers `send`, including connection acquisition and existing hooks. Non-streamed
sends include body reading; streamed sends normally return after headers and hooks.
Instrumentation does not consume or wrap the response stream. Later stream-read errors
are outside that send span: a 200/unset span status does not prove a completed generation.
Use the enclosing operation's outcome for that result. PyJWT's separate synchronous
JWKS fetch is not an HTTPX call and is outside this boundary.

This connects HTTP server/client and query spans, log correlation and existing DB
histograms. Native Taskiq supplies job metrics; process-local cache measurements are
described above, alongside search, generation and assistant stream measurements.
The [lesson-10 lab](../../devops-course/lab/lesson10/README.md) verifies actual Alloy
ingestion and application independence during a collector outage; backend storage,
queries and dashboards remain subsequent course work.
See [jobs](modules/jobs.md).

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
