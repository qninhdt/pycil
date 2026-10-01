# ops/devops

Docker Compose, one VPS, one environment. Decisions `O1`–`O12`.

The application runs on one VPS with a single API process and no content worker.

## 1. Stack

### Current

```text
caddy          public 80/443   TLS, routing, SSE pass-through
api            internal        FastAPI, assistant SSE, post-response content tasks
postgres       internal        public + lexi + checkpointer schemas
redis          internal        receipts, cache, coordination
migrate        one-shot        blocking schema gate
```

### Target

```text
caddy          public 80/443   TLS, routing, SSE pass-through
api            internal        FastAPI, assistant SSE, post-response content tasks
postgres       internal        public + lexi + checkpointer schemas
redis          internal        receipts, cache, coordination
migrate        one-shot        blocking schema gate
```

Four long-lived services. Web is a Vercel build, not a container. Migration is
a one-shot command, not a long-lived service.

There is no scheduler or worker heartbeat. See
[cross-cutting/messaging.md](../cross-cutting/messaging.md).

The API runs from one application image. Only Caddy
publishes ports; every other service's debug port is parameterized and
loopback-bound.

## 2. State and configuration

Postgres is canonical. Redis holds receipts, cache and coordination, and it is
**not** a copy of canonical state: a content-job receipt lives only in Redis with
a 24-hour TTL, so a Redis loss loses in-flight content work. That is the accepted
trade, stated in [cross-cutting/messaging.md](../cross-cutting/messaging.md) §4.

Postgres, Redis, and Caddy certificates use named volumes.

Every value comes from the environment. Missing required values and placeholder
values fail boot with all offending names reported together.

## 3. Secret boundaries

```text
api             Clerk verification config, assistant and content provider keys
web/caddy       no application credentials
```

The API holds provider keys because assistant turns and content generation run
inside its process. It verifies browser credentials; tasks receive only validated
identifiers and content arguments, never bearer tokens.

No secret appears in an image, repository, or log.

## 4. Edge delivery

Assistant SSE routes disable proxy buffering and compression and allow a timeout
longer than the application turn deadline. Ordinary API and web responses keep
normal compression and caching policy. Job reads are ordinary authenticated HTTP.

**Both** assistant routes stream `text/event-stream`, and the edge matcher must
name both:

```text
/v1/assistant                                the browser's chat transport
/v1/assistant/threads/*/runs/stream          the plain-message variant
```

Naming only the second is a live defect this repository shipped: `/v1/assistant` is the
route the web client actually uses, so it was compressed and buffered while the
unused route got the correct treatment — the stream would have arrived as one blob
after the turn ended. The matcher is verified against the adapted Caddy config
rather than by reading it: `caddy adapt` shows both paths in the flush/no-encode
route, and a probe confirms `*` matches exactly one path segment.

## 5. Deploy

```text
1  CI builds once and pushes the API image by digest
2  host pulls exact digests and takes the pre-deploy database snapshot
3  new image runs Lexi setup/head assertion, checkpointer setup, then Alembic
4  start and health-gate the API and Caddy
5  on failure restore the previous digest; restore data only when schema requires it
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
dependencies. API readiness covers Postgres and Redis. It has no provider dependency.

On `SIGTERM` the API stops accepting new requests; an in-flight background job
can be abandoned. Its receipt eventually reads as `expired` and may be retried.

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
| Jobs pending, none running | Check API logs and provider availability; stale receipts become `expired` and require a new request |
| Job stuck running | Read `GET /v1/jobs/{id}`; an expired or missing receipt means retry, not success |
| Job UI stale | Read `GET /v1/jobs/{id}`; the receipt is the state |
| Assistant stream drops | Read the Thread state; resume only if the checkpoint says interrupted |
| Assistant capacity exhausted | Inspect per-learner admission and API concurrency |
| API healthy, jobs unavailable | Check API/provider logs; jobs share the API process |
| Anything else | `docker compose logs --since 30m <service>` on the deployment host — every service writes to its own stdout and Docker captures it. There is no shipper and no external log store, so a removed container takes its history with it, and a lost host takes all of it |
| Migration fails | Keep old services, fix the new image or restore the verified snapshot |
| Restore fails | Repair the rehearsed restore procedure before deployment |

## 9. Operational invariants

```text
only Caddy publishes ports
SSE is unbuffered and uncompressed at the edge
the API executes assistant turns and best-effort content tasks
migration completion blocks new application startup
the deployed image digest is the tested digest
readiness checks Postgres and Redis
one backup contains every Postgres schema and restore is rehearsed
```

Two earlier lines are **withdrawn**, both because the implemented system does not
provide them:

- `Redis loss cannot erase canonical state` — true of learner state, false of an
  in-flight content task, whose only visible status is the Redis receipt.
- `an accepted job survives a process restart` — there is no queue or scheduler;
  its stale receipt becomes expired for the learner to retry.
