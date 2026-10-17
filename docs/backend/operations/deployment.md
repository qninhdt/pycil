# Deployment and runtime operations

## Runtime image

The [Dockerfile](../../../apps/api/Dockerfile) installs locked non-development dependencies,
bakes product policy, and runs as UID 10001. Local prompts are application package assets.
Build from the repository root:

```sh
docker build -f apps/api/Dockerfile -t pycil-api:local .
```

The same image supports the [native Taskiq worker command](../modules/jobs.md#native-worker-command)
as a separate process/service. Worker application code is implemented; Compose/ECS/CI
worker deployment is deferred to the separately authorized course phase. The API retains
its local Tantivy projection; workers initialize neither search nor checkpoint pools.

The image starts one Uvicorn worker with a 75-second HTTP drain deadline,
five-second keep-alive and a concurrency limit of 64 connections or tasks; excess
traffic receives 503. Uvicorn access logs are disabled because the application
already emits structured request logs. Compose gives the API 120 seconds after
SIGTERM before SIGKILL. Long streams can be interrupted; the HTTP drain deadline
does not include lifespan cleanup. The exit stack has a cooperative 40-second
cleanup budget; cancellation requests remaining closers to run. Code that blocks
the event loop or suppresses cancellation can still reach the container's hard
stop deadline.

## Compose topology

[Compose](../../../docker-compose.yml) runs PostgreSQL, Redis, an explicit one-shot
migration service, API and Caddy. Migration imports `data/reference.jsonl.gz` through a
read-only bind mount, applies the application baseline and runs native checkpoint setup.
The API waits for stores and migration success. Any later worker service must use the same migration-before-start gate. It neither migrates nor imports on startup.

Use [the wrapper](../../../scripts/compose.py) with an explicitly selected private file.
Only `config -q` / `config --quiet` is permitted because resolved configuration exposes
credentials. Remote store URLs remain remote; selecting them is an operator decision.
Persistent volumes contain stores and Caddy state; never delete volumes as a migration fix.

## Cutover and recovery

This rewrite has one fresh application baseline and no compatibility upgrade chain.
Export desired data before replacing development databases. A populated installation
needs a separately validated transfer into the target schema, preserving identities and
relationships. See [migrations](migrations.md). An image-only downgrade cannot undo DDL.

[scripts/deploy.sh](../../../scripts/deploy.sh) requires an approved immutable image digest
and a backup checksum before migration and swap. A checksum does not prove a backup is
restorable. Rehearse restoration independently. Schema migration, native checkpoint setup
and reference import have separate transaction boundaries; inspect the failed stage before
retrying. No production deployment was performed as part of this rewrite.

## Operational signals

- `/livez` checks process liveness.
- `/readyz` checks current PostgreSQL, Redis and initialized search within a bounded deadline.
- Startup verifies schema and reference without repairing either.
- `X-Request-ID` and conversation context correlate structured events. Logs redact
  provider payloads, tokens and credentials.

Provider availability and worker backlog are not tested by API readiness. Native Taskiq
OTel shares the existing SDK/export path; collector deployment and Langfuse remain deferred.
Monitor worker execution and Redis stream lag/pending independently. Assistant SSE must remain unbuffered; HTTP 200 alone does not establish
successful completion. [Caddy](../../../Caddyfile) owns ingress limits and streaming behavior.

## Verification

[CI](../../../.github/workflows/test.yml) checks backend lint/format, Testcontainers tests,
image build, quiet Compose validation and Caddy configuration. Those checks do not prove
production load capacity, backup restoration or paid provider correctness.
See [testing](../testing.md) and [configuration](../configuration.md).
