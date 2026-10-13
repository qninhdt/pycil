# Deployment and runtime operations

## Runtime image

The [Dockerfile](../../../apps/api/Dockerfile) installs locked non-development dependencies,
bakes product policy, and runs as UID 10001. Local prompts are application package assets.
Build from the repository root:

```sh
docker build -f apps/api/Dockerfile -t pycil-api:local .
```

API processes share generation task status through Redis; job execution, singleflight
and concurrency limits remain per process. Workers must use the same Redis namespace
(derived from database URL and Clerk issuer) and disk index directory. The Tantivy index
lives in the `search` volume (`SEARCH_INDEX_PATH`) and is shared safely by processes. Runtime
requires PostgreSQL with imported reference, Redis, Clerk and model provider configuration.
WordNet is optional. There is no separate vocabulary package or service.

## Compose topology

[Compose](../../../docker-compose.yml) runs PostgreSQL, Redis, an explicit one-shot
migration service, API and Caddy. Migration imports `data/reference.jsonl` through a
read-only bind mount, applies the application baseline and runs native checkpoint setup.
The API waits for stores and migration success. It neither migrates nor imports on startup.

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

- `/health` checks process liveness.
- `/ready` checks current PostgreSQL, Redis and initialized search within a bounded deadline.
- Startup verifies schema and reference without repairing either.
- Generation status remains in Redis for 24 hours after each initial/final write. Graceful
  shutdown records interruption; a worker crash loses unfinished jobs and can leave
  `running` status until expiry. Final Redis publication failures are logged and can also
  leave stale status. Committed vocabulary remains available for reuse on retry.
- New words are committed before incremental search publication; index failure fails the job.
- `X-Request-ID`, task and conversation context correlate structured events. Logs redact
  provider payloads, tokens and credentials.

Provider availability is not tested by readiness. OpenTelemetry exporters and Langfuse
remain deferred. Assistant SSE must remain unbuffered; HTTP 200 alone does not establish
successful completion. [Caddy](../../../Caddyfile) owns ingress limits and streaming behavior.

## Verification

[CI](../../../.github/workflows/test.yml) checks backend lint/format, Testcontainers tests,
image build, quiet Compose validation and Caddy configuration. Those checks do not prove
production load capacity, backup restoration or paid provider correctness.
See [testing](../testing.md) and [configuration](../configuration.md).
