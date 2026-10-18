# Deployment and runtime operations

## Runtime image

The [Dockerfile](../../../apps/api/Dockerfile) installs locked non-development dependencies,
bakes product policy, and runs as UID 10001. Local prompts are application package assets.
Build from the repository root:

```sh
docker build -f apps/api/Dockerfile -t pycil-api:local .
```

The same image supports the [native Taskiq worker command](../modules/jobs.md#native-worker-command)
as a separate process/service. [VPS Compose and delivery](../../../infra/vps/README.md)
include the worker. VPS production is live; ECS deployment remains separate work. The API retains
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

[Local Compose](../../../infra/local/compose.yaml) runs PostgreSQL, Redis, an explicit one-shot
migration service, API and Caddy. Migration imports `data/reference.jsonl.gz` through a
read-only bind mount, applies the application baseline and runs native checkpoint setup.
The API waits for stores and migration success. Any later worker service must use the same migration-before-start gate. It neither migrates nor imports on startup.

Use [the wrapper](../../../scripts/compose.py) with an explicitly selected private env file.
It defaults to `infra/local/compose.yaml`; select another manifest with `--file`.
[Production Compose](../../../infra/vps/compose.yaml) has separate blue/green API
identities, a native worker, private stores and static origin TLS. Its
[controller/runbook](../../../infra/vps/README.md) owns bounded migration,
candidate checks, routing, observation and compatible application rollback.
Only `config -q` / `config --quiet` is permitted because resolved configuration exposes
credentials. Remote store URLs remain remote; selecting them is an operator decision.
Persistent volumes contain stores and Caddy state; never delete volumes as a migration fix.

## Cutover and recovery

This rewrite has one fresh application baseline and no compatibility upgrade chain.
Export desired data before replacing development databases. A populated installation
needs a separately validated transfer into the target schema, preserving identities and
relationships. See [migrations](migrations.md). An image-only downgrade cannot undo DDL.

[infra/vps/deploy.sh](../../../infra/vps/deploy.sh) requires an approved immutable image digest
and a recovery-evidence checksum before migration and switch. It rejects different
Alembic heads because current startup requires an exact schema version. Matching
heads still require queue/index/response compatibility review. A checksum does not prove a backup is
restorable. Rehearse restoration independently. Schema migration, native checkpoint setup
and reference import have separate transaction boundaries; inspect the failed stage before
retrying. The [VPS runbook](../../../infra/vps/README.md) records live bootstrap,
credential sources and recovery scope.

## Operational signals

- `/livez` checks process liveness.
- `/readyz` checks current PostgreSQL, Redis and initialized search within a bounded deadline.
- Startup verifies schema and reference without repairing either.
- `X-Request-ID` and conversation context correlate structured events. Logs redact
  provider payloads, tokens and credentials.

Provider availability and worker backlog are not tested by API readiness. Native Taskiq
OTel shares the existing SDK/export path. VPS Alloy, Prometheus, Loki, Tempo and
Grafana are deployed; Langfuse remains deferred.
Monitor worker execution and Redis stream lag/pending independently. Assistant SSE must remain unbuffered; HTTP 200 alone does not establish
successful completion. [Caddy](../../../infra/local/Caddyfile) owns ingress limits and streaming behavior.

## Verification

[CI](../../../.github/workflows/test.yml) checks backend lint/format, Testcontainers tests,
image build, quiet Compose validation and Caddy configuration. Those checks do not prove
production load capacity, backup restoration or paid provider correctness.
See [testing](../testing.md) and [configuration](../configuration.md).
