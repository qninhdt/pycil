# Background jobs

Word generation and study preparation run in native Taskiq workers, independently of
FastAPI. Both commands use the same package/image and environment's PostgreSQL/Redis.
No new database table, worker framework, outbox or DLQ is introduced.

## HTTP contract

Authenticated submissions:

- `POST /v1/words:generate` with `{ "reference_id": "<search reference>" }`.
- `POST /v1/study:prepare` with the existing preparation inputs.

Both return **202**, `Location: /v1/jobs/<id>`, `Retry-After: 2` and
`{ "job_id": "<UUIDv7>", "status_url": "/v1/jobs/<id>" }`.
Acceptance does not mean completion. GET the status URL using the same authentication:

```json
{"job_id":"019a08b8-0000-7000-8000-000000000001","status":"succeeded","result":{"word_id":12},"error":null}
```

Status is `queued`, `running`, `succeeded` or `failed`. Successful preparation's
`result` is the former preparation response (questions, lexical bundles and preferences).
Failures expose only `job_failed`. Unknown, foreign and expired references all return
404 `job_not_found`; Redis failure returns 503 `job_status_unavailable`.
UUIDs do not replace authorization. Ownership is an expiring Redis user-ID string;
Taskiq owns results/progress. Polling neither consumes results nor extends ownership.
The public reference lasts 24 hours from acceptance, not permanent history.

Clients use the existing TanStack Query client to poll every two seconds, slowing
to five seconds after 30 seconds, respect `Retry-After`, pause interval polling while
hidden and back off on network/503 failures. Screens retain
accepted references in sessionStorage to resume without another submission. Aborting
client waiting does not cancel the job. A ten-minute client waiting limit is not proof
of task failure. There is no job-list, cancel endpoint or old word-status route.

## Native worker command

From `apps/api`, after the explicit migration/reference gate succeeds:

```sh
uv run --locked --env-file /absolute/path/to/worker.env taskiq worker \
  pycil.app.broker:worker_broker \
  pycil.vocabulary.generation.tasks pycil.study.tasks \
  --workers 1 --max-async-tasks 4 --max-prefetch 0 \
  --ack-type when_saved --wait-tasks-timeout 90 --shutdown-timeout 10 \
  --no-configure-logging
```

[Broker configuration](../../../apps/api/pycil/app/broker.py) uses Taskiq 0.13.0 and
taskiq-redis 1.2.4. Taskiq's shared broker registers decorators without import-time I/O;
the CLI calls the broker factory inside each worker process. Native lifecycle events
open/close shared resources. Workers need `DB_URL`, `REDIS_URL`, `LLM_API_KEY`,
`LLM_BASE_URL` and optional `CONFIG_PATH`/OTel settings. They need no Clerk, decision
provider, CORS or search-path secrets, initialize no Tantivy/checkpoint pool, and expose
no HTTP port. The API is a producer and does not execute queued jobs.

Four concurrent tasks is an initial measurement setting, not measured production
capacity. Include worker DB/Redis pools, provider fan-out and rollout overlap in budgets.
`jobs` owns native execution timeout, longer domain-lock expiry and result TTL;
submission functions pass the native timeout label. Keep callers on those domain entry
points so normalization, ownership and timeout labels are applied together.
Native SIGTERM drains within the CLI budget; a longer job may be interrupted. Infrastructure
service commands/stop deadlines and deployment remain a later authorized course phase.

## Domain behavior

Same-user identical in-flight requests reuse their accepted ID through the shared
[`singleflight` submission guard](../../../apps/api/pycil/jobs/singleflight.py). Domain
modules define request keys and publish through Taskiq directly. Preparation fingerprints
include effective preferences, selected scope and policy; tasks recheck current access
and entitlements before work. Different users retain separate private job references.

Word tasks acquire a native Redis lock, then reuse completed canonical PostgreSQL content
before calling providers. Artifact refill remains internal to preparation and allows
concurrent generation into the same bank. Existing PostgreSQL transactions merge
singleton increments and append other unique artifacts; surplus valid content is kept.
There is no Redis artifact-bank lock or whole-preparation execution lock. Random
question assembly is not globally deduplicated. Database publication
constraints and content revisions remain the durable correctness boundary. API search
owners reconcile revisions independently; worker completion is not a fleet-wide search
visibility barrier. Read a completed word directly by its returned ID.

Native retry middleware permits two total attempts only for sanitized infrastructure
failures before paid/domain work. Domain/provider failures and execution timeouts are
terminal; provider clients keep their existing bounded retries. No retry/ACK/ownership
loop is implemented in Pycil. A publish timeout returns safe 503 but retains owner metadata:
Redis might have accepted the message. The accepted-job pointer is written only after
confirmed publish. Neither submission nor provider billing is exactly once.

## Telemetry and operational limits

Native `OpenTelemetryMiddleware` emits `send/<task_name>`, `execute/<task_name>` and
propagates their trace through Redis labels. Existing SQL/outbound HTTP spans nest under
execution. It also supplies sent/success/error counts, execution/wait histograms, active
tasks and worker CPU/memory. Counts represent attempts. Task IDs stay in logs/spans, never
metric dimensions. Pycil reuses its existing SDK lifecycle, safe structured logging and
OTLP export; set `OTEL_SERVICE_NAME=pycil-worker`. No second jobs telemetry module,
SDK provider, Prometheus middleware or generic manual execution span is added.

Keep Taskiq logging at INFO; DEBUG can print arguments. Task boundaries suppress raw
provider exception context before native result/telemetry serialization. No prompts,
answers, credentials or raw result labels belong in telemetry or public job status.

Known limits remain explicit:

- **Deferred by user:** taskiq-redis 1.2.4 may not reclaim a crashed delivery on an idle
  queue until fresh traffic arrives. Its integration test is visibly skipped. Revisit
  the upstream fix after worker implementation; no copied broker or heartbeat workaround.
- Native Receiver can ACK even when saving a result fails. `when_saved` does not make
  execution/result persistence/ACK atomic. A pending status is not proof work is running.
- XACK retains stream entries. Result TTL does not limit stream storage. Later operations
  must provide safe acknowledged-history retention (Redis >=8.2 `XTRIM MINID ... ACKED`),
  not an approximate maxlen that can delete unread/pending work.
- Redis persistence/eviction/failover affects accepted work. Cache flushes must exclude
  task/coordination keys. Redelivery can repeat paid calls after ambiguous failures.
- Collect stream lag/pending separately from Taskiq wait histograms: a stalled queue starts
  no tasks. VPS Alloy Redis stream collection is planned; AWS's supported backlog
  collection path remains an observability-phase decision, with no new exporter provisioned.

[Integration evidence](../../../apps/api/tests/integration/jobs/test_jobs.py) uses real
Redis/PostgreSQL and a separate native CLI process. [Implementation record](../../../job.md)
contains the detailed scope and remaining operational gates.
