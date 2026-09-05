# ops/devops

Docker Compose, one VPS, one environment. Decisions `O1`–`O12`.

## 1. Stack

```text
caddy          public 80/443   TLS, routing, SSE pass-through
web            internal        Next.js UI only
api            internal        FastAPI, assistant execution and SSE
domain-worker  internal        durable content jobs
scheduler      internal        heartbeat, reconciliation, retention
postgres       internal        public + lexi + checkpointer schemas
redis          internal        Streams broker, cache, coordination
migrate        one-shot        blocking schema gate
backup         profile         coordinated dump and restore
```

Only Caddy publishes ports. API, domain worker, and scheduler share one image
with different entrypoints. The production override pins image digests, resource
limits, restart policy, and drain windows.

## 2. State and configuration

Postgres is canonical. Redis persistence remains enabled to reduce redispatch,
but losing Redis cannot lose a job, Run, or learner state. Postgres, Redis, and
Caddy certificates use named volumes.

Every value comes from the environment. Missing required values and placeholder
values fail boot with all offending names reported together. Debug ports are
parameterized and loopback-bound so a second Compose project can rehearse restore
beside the live stack.

## 3. Secret boundaries

```text
api             signing secrets, refresh pepper, OAuth secret,
                assistant provider key
domain-worker   content-generation provider keys
scheduler       no browser or provider credentials
web/caddy       no application credentials
```

No secret appears in an image, repository, or log.

## 4. Edge delivery

Assistant SSE routes disable proxy buffering and compression and allow a timeout
longer than the application Run deadline. Ordinary API and web responses keep
normal compression and caching policy. Job reads are ordinary authenticated HTTP.

## 5. Deploy

```text
1  CI builds once and pushes by digest
2  host pulls exact digests and takes the pre-deploy database snapshot
3  new image runs Lexi setup/head assertion, checkpointer setup, then Alembic
4  start and health-gate domain worker and scheduler
5  start and health-gate API
6  start web and Caddy
7  run smoke and golden journey
8  on failure restore the previous digest; restore data only when schema requires it
```

Migration is a blocking one-shot service. The squashed Pycil baseline is applied
to an empty pre-production database; incremental migrations resume after it.
Every schema change updates the explicit model aggregator.

## 6. Health and drain

Liveness checks the process. Readiness checks required configuration and reachable
dependencies. API readiness covers Postgres and Redis; job-system readiness also
requires a recent domain-worker heartbeat. It has no gateway dependency.

On `SIGTERM`, the API stops accepting new requests and gives active assistant
streams their bounded drain window. The domain worker stops claiming and finishes
or records interruption for current jobs. The scheduler stops between ticks.
`stop_grace_period` exceeds each component's application deadline.

## 7. Backup and restore

One coordinated Postgres dump covers public, Lexi, and checkpointer schemas. The
write path is stopped for the dump and restored even if the command fails. Restore
is rehearsed into an empty second Compose project. Any schema or data change runs
only after a verified backup when persistent data exists.

## 8. Runbook

| Situation | First move |
|---|---|
| Jobs pending, none running | Check domain-worker health and Redis Streams; scheduler will redispatch |
| Job stuck running | Inspect its attempt and timestamps; run the reconciliation tick |
| Job UI stale | Read `GET /v1/jobs/{id}`; Postgres is canonical |
| Assistant stream drops | Read Run and Thread; resume only if state says interrupted |
| Assistant capacity exhausted | Inspect per-learner admission and API concurrency |
| API healthy, jobs unavailable | Check the worker heartbeat age |
| Migration fails | Keep old services, fix the new image or restore the verified snapshot |
| Restore fails | Repair the rehearsed restore procedure before deployment |

## 9. Operational invariants

```text
only Caddy publishes ports
SSE is unbuffered and uncompressed at the edge
the API can execute assistant Runs and the domain worker cannot mint sessions
Redis loss cannot erase canonical state
a committed undispatched job is recovered by the scheduler
readiness distinguishes API health from job-worker health
migration completion blocks new application startup
the deployed image digest is the tested digest
one backup contains every Postgres schema and restore is rehearsed
```
