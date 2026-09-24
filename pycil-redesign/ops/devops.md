# ops/devops

Docker Compose, one VPS, one environment. Decisions `O1`–`O12`.

**Status: the target is five services; the repository currently runs six.** This
document separates the two rather than describing the destination as if it were
already deployed. The gap is
[Phase 15](../../plans/260924-0608-pycil-complete-redesign/phase-15-infrastructure-and-backup.md)'s
work, gated on the local browser harness and a rehearsed WAL-G restore.

## 1. Stack

### Current

```text
caddy          public 80/443   TLS, routing, SSE pass-through
web            internal        Next.js UI only                  <- target: Vercel
api            internal        FastAPI, assistant execution and SSE
worker         internal        durable content jobs + heartbeat
postgres       internal        public + lexi + checkpointer schemas
redis          internal        Streams broker, cache, coordination
migrate        one-shot        blocking schema gate
backup         profile         restic dump to B2                 <- target: WAL-G
```

### Target

```text
caddy          public 80/443   TLS, routing, SSE pass-through
api            internal        FastAPI, assistant execution and SSE
worker         internal        durable content jobs + heartbeat
postgres       internal        public + lexi + checkpointer schemas
redis          internal        Streams broker, cache, coordination
migrate        one-shot        blocking schema gate
```

Five long-lived services. Web is a Vercel build, not a container. A migration is a
one-shot command, not a sixth long-lived service.

**There is no scheduler in either state.** Earlier revisions of this folder listed
one owning heartbeat, reconciliation and retention. The worker owns its own
liveness: `pycil_worker/main.py` starts `_heartbeat_loop` in-process and refreshes
`worker:heartbeat`. See
[cross-cutting/messaging.md](../cross-cutting/messaging.md) §6.

API and worker are separate commands from one application image. Only Caddy
publishes ports; every other service's debug port is parameterized and
loopback-bound.

## 2. State and configuration

Postgres is canonical. Redis holds transport, cache and coordination, and it is
**not** a copy of canonical state: a content-job receipt lives only in Redis with
a 24-hour TTL, so a Redis loss loses in-flight content work. That is the accepted
trade, stated in [cross-cutting/messaging.md](../cross-cutting/messaging.md) §4.

Postgres, Redis, and Caddy certificates use named volumes.

Every value comes from the environment. Missing required values and placeholder
values fail boot with all offending names reported together.

## 3. Secret boundaries

```text
api             Clerk verification config, assistant provider key
worker          content-generation provider keys
web/caddy       no application credentials
```

The worker holds no browser-credential secret and cannot mint an identity. The API
holds the assistant provider key because it executes turns inline. That split is
enforced by which service each variable is injected into (`O6`).

No secret appears in an image, repository, or log.

## 4. Edge delivery

Assistant SSE routes disable proxy buffering and compression and allow a timeout
longer than the application turn deadline. Ordinary API and web responses keep
normal compression and caching policy. Job reads are ordinary authenticated HTTP.

**Both** assistant routes stream `text/event-stream`, and the edge matcher must
name both:

```text
/v1/assistant/ag-ui                          the browser's chat transport
/v1/assistant/threads/*/runs/stream          the plain-message variant
```

Naming only the second is a live defect this repository shipped: `/ag-ui` is the
route the web client actually uses, so it was compressed and buffered while the
unused route got the correct treatment — the stream would have arrived as one blob
after the turn ended. The matcher is verified against the adapted Caddy config
rather than by reading it: `caddy adapt` shows both paths in the flush/no-encode
route, and a probe confirms `*` matches exactly one path segment.

## 5. Deploy

```text
1  CI builds once and pushes API and worker by digest
2  host pulls exact digests and takes the pre-deploy database snapshot
3  new image runs Lexi setup/head assertion, checkpointer setup, then Alembic
4  start and health-gate the worker
5  start and health-gate the API
6  start Caddy
7  on failure restore the previous digest; restore data only when schema requires it
```

`scripts/deploy.sh` implements this and is the one deploy route. It refuses an
image reference that is not an `@sha256:` digest, because a tag can be moved and
"it worked in CI" is only useful if the artefact tested is the artefact deployed.
It also forces `ENVIRONMENT=production` rather than trusting the operator's `.env`
copy, and keeps the last five pre-deploy `pg_dump` snapshots.

**Build once, promote by digest** (`N8`). Migration is a blocking one-shot
service: new containers do not take traffic against an unmigrated schema, and the
migration runs in the **new** image before anything swaps, so a failure leaves the
old containers untouched.

## 6. Health and drain

Liveness checks the process. Readiness checks required configuration and reachable
dependencies. API readiness covers Postgres and Redis; job-system readiness also
requires a recent worker heartbeat. It has no gateway dependency.

On `SIGTERM` the API stops accepting new requests and gives active assistant
streams their bounded drain window. The worker stops claiming and finishes or
records interruption for current jobs. `stop_grace_period` exceeds each
component's application deadline.

## 7. Backup and restore

### Current

`scripts/backup-product.sh` stops the write path, runs the profiled `backup`
service (a `pg_dump` piped into `restic`), and restores services on exit even if
the command fails. One dump covers public, Lexi and checkpointer schemas.
`scripts/restore-product.sh` reverses it. The backup service applies a
7d/4w/6m restic retention policy.

### Target

WAL-G base backups plus continuous WAL archiving to S3-compatible storage, with a
rehearsed isolated restore. A base backup plus archived WAL recovers within the
actually archived window; it is **not** a zero-data-loss promise. Measure lag and
restore time rather than claiming a number.

**Do not erase the current backup scripts until a WAL-G restore has been
rehearsed.** A backup route is not replaced by a plan to replace it.

Any schema or data change runs only after a verified backup when persistent data
exists.

## 8. Runbook

| Situation | First move |
|---|---|
| Jobs pending, none running | Check worker health and the Redis Stream; a message unacknowledged past `idle_timeout` is reclaimed automatically |
| Job stuck running | Read `GET /v1/jobs/{id}`; a missing receipt means retry, not success |
| Job UI stale | Read `GET /v1/jobs/{id}`; the receipt is the state |
| Assistant stream drops | Read the Thread state; resume only if the checkpoint says interrupted |
| Assistant capacity exhausted | Inspect per-learner admission and API concurrency |
| API healthy, jobs unavailable | Check the worker heartbeat age |
| Anything else | `docker compose logs --since 30m <service>` on the deployment host — every service writes to its own stdout and Docker captures it. There is no shipper and no external log store, so a removed container takes its history with it, and a lost host takes all of it |
| Migration fails | Keep old services, fix the new image or restore the verified snapshot |
| Restore fails | Repair the rehearsed restore procedure before deployment |

## 9. Operational invariants

```text
only Caddy publishes ports
SSE is unbuffered and uncompressed at the edge
the API can execute assistant turns and the worker cannot mint an identity
migration completion blocks new application startup
the deployed image digest is the tested digest
readiness distinguishes API health from worker health
one backup contains every Postgres schema and restore is rehearsed
```

Two earlier lines are **withdrawn**, both because the implemented system does not
provide them:

- `Redis loss cannot erase canonical state` — true of learner state, false of an
  unclaimed content job, whose only record is the Redis receipt.
- `a committed undispatched job is recovered by the scheduler` — there is no
  scheduler, and a failed publication is recorded as failed for the learner to
  retry rather than recovered automatically.
