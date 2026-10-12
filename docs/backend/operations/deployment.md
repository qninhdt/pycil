# Deployment and runtime operations

## Scope and approval boundary

The deployment unit is a tested immutable API image used for the API and migration gate.
The repository includes a Compose manifest, Caddy ingress, and an operator-only
`scripts/deploy.sh`. There is no automatic production deployment in the test workflow.
Reading or editing these docs does not authorize deploying or migrating a real installation.

The repository implements the reduced backend contract, not a deployed release.
Review [implementation status](../implementation-status.md), external gates and client
compatibility before planning a cutover.

## Image and runtime dependencies

The [Dockerfile](../../../apps/api/Dockerfile) pins Python 3.14.8 and uv 0.12.22, verifies
the vendored Lexi wheel and content snapshot checksums, installs locked non-dev dependencies, bakes product
policy, and runs as UID 10001. WordNet is optional. API starts with Uvicorn on 8000;
the finite migration gate uses the same image with a different command. Run one API process.

Runtime requires PostgreSQL with imported reference data, Redis, Clerk configuration,
and inference/decision endpoints. Initial setup downloads the pinned reference release,
verifies its checksum, and imports it into `lexi_reference`; API have no SQLite
mount. An existing import needs no network access. For offline migration, provide a
standalone local artifact with `python -m pycil.migrate --reference /path/reference.sqlite`.
The image includes `vendor/lexi-ai/content.sqlite`; the same migration gate imports
this generated vocabulary automatically before the API starts. Deploy needs no
separate Lexi service, sibling checkout, or manual content-import command.
A successful image build does not validate deployment credentials, a populated upgrade,
or paid provider billing.

Build from the repository root:

```sh
docker build -f apps/api/Dockerfile -t pycil-api:local .
```

This is a local artifact tag, not a suitable immutable production deployment identifier.
The operator script requires an image reference containing `@sha256:`. Build/test/publish
authorization and artifact promotion are separate from running the deployment script.

## Compose topology

| Service | Role / startup condition |
| --- | --- |
| `postgres` | PostgreSQL 18.6; local store health check |
| `redis` | Redis 8.10.2 with AOF and authentication |
| `migrate` | One-shot explicit migration; waits for PostgreSQL |
| `api` | Waits for both stores healthy and migration success |
| `caddy` | Public HTTPS ingress; waits for API health |

Use `python scripts/compose.py --env-file <private-file> ...`. It validates canonical
URLs and derives internal variables without dumping secrets. Only `config -q` or
`config --quiet` is allowed; full resolved Compose config can contain credentials.
Process environment overrides file values, so exported stale URLs can change the target.

Loopback store URLs are translated to `postgres`/`redis` inside containers. Remote
URLs stay remote; the wrapper does not infer permission to migrate them and the manifest
still declares local store services. Carefully review a remote-store installation
rather than assuming those services or dependencies are automatically omitted.

Persistent volumes are `pgdata`, `redisdata`, `caddy_data`, and `caddy_config`. Store
ports default to loopback; the API defaults to `127.0.0.1:8000`. Caddy exposes HTTP/HTTPS
and serves only API/documentation/health paths; other paths return 404. It does not
serve the local web starter/showcase or a product FE application.
Do not remove volumes to resolve a configuration or migration error.

## Supported migration-then-swap procedure

Before running the script:

1. Obtain separate deployment approval and agree on a maintenance window.
2. Identify the exact database and expected current/schema target revisions.
3. Produce a backup and independently rehearse restoring it. Include all PostgreSQL
   schemas, reference/artifact provenance, and the necessary private deployment configuration.
4. Test the exact immutable image and populated upgrade on a disposable restore.
5. Arrange matching clients: old node routes/visibility, scalar reviews, budget fields,
   raw history and raw cursor parameters are removed, not aliased. Deploy clients using
   NEW/DUE/AUTO, `max_sense_count`, frozen UUID/body batch retries and opaque cursors.
6. Confirm provider, reference, store, and ingress configuration without printing secrets.

Operator environment variables:

| Variable | Meaning |
| --- | --- |
| `ENV_FILE` | Explicit private deployment environment file |
| `API_IMAGE` | Tested immutable digest reference |
| `DEPLOY_APPROVED` | Must be exactly `yes`, set only after actual approval |
| `VERIFIED_BACKUP_FILE` | Existing independently verified backup artifact |
| `VERIFIED_BACKUP_SHA256` | Expected checksum for that artifact |

After these have been supplied deliberately, the operator invokes `bash scripts/deploy.sh`.
The script validates approval, digest shape, file existence and checksum, validates
Compose quietly, pulls API/migration images, stops the API writer, removes orphan services while
ensuring stores are ready, runs the explicit migration, and starts the API with wait.

**The script checks a checksum, not backup restorable completeness.** Independent restore
verification is a prerequisite, not something the script implements. It does not build
a backup, perform a restore, automatically reopen old services after failure, or make
an old image compatible with a new schema.

## Health and operational checks

- `/health` returns process liveness without querying all dependencies.
- `/ready` probes current PostgreSQL and Redis. Native schema is verified at startup;
  readiness does not rerun migrations, check provider inference, or measure dictionary capacity.
- Generation task status is in memory; a restart interrupts it. Committed content survives.
- Search builds at startup and receives per-word updates from the same API process.
- Correlate HTTP failures with X-Request-ID. Keep secrets/content out of diagnostic bundles.

SSE at `/v1/assistant:run` must not be compressed or fully buffered by an added proxy.
Caddy currently excludes it from compression, disables upstream compression, and uses
a 3-minute response-header timeout. The Assistant SDK has a 180-second per-request
network timeout, and the Next rewrite has a 210-second socket inactivity timeout.
There is no whole-turn deadline; these transport timers are different boundaries. An interrupted SSE stream is not successful completion.

## Failure response

| Failure | Operator response |
| --- | --- |
| Migration fails after writers stop | Leave writers stopped; inspect migration stage and target; do not run old code against an assumed rolled-back schema |
| API startup rejects schema/reference/config | Correct verified deployment inputs or execute approved recovery; never add startup auto-repair |
| Worker ownership error | Find the existing/lost owner; do not disable the coordination lock |
| Redis unavailable | Readiness and leases can fail; optional value-cache fallback does not make Redis optional infrastructure |
| Generation repeatedly fails | Inspect sanitized queue state, provider/reference readiness, and attempt policy; avoid unlimited retry loops |
| Query/scope timeout | Retry safe reads or choose a smaller scope; investigate query plans rather than returning partial counts |
| Post-upgrade rollback required | Follow [migration recovery](migrations.md), not an image-only downgrade |

A deployment that stops after one migration stage may have mixed schema versions.
The gate does not make native checkpoint setup and all external migrations one atomic
operation. Verify stage-specific state before deciding to rerun or restore.

## CI versus production evidence

The test workflow runs for PRs targeting main/dev and pushes to main. It verifies wheel
bytes, lint/format, tests on disposable stores, image build, safe Compose validation, and
Caddy config. A direct push to dev alone does not prove that workflow executed.

These gates do not prove restore readiness, production load capacity, model billing
rates, or the availability of every target product feature. See [testing](../testing.md).
The retained backend scope is documented in [frontend handoff](../frontend-handoff.md);
large performance testing needs separate resource approval and agreed thresholds.

## Sources

- [Operator script](../../../scripts/deploy.sh), [Compose wrapper](../../../scripts/compose.py), [manifest](../../../docker-compose.yml)
- [Ingress](../../../Caddyfile), [test workflow](../../../.github/workflows/test.yml)
- [Runtime resource lifecycle](../../../apps/api/pycil/dependencies.py), [generation tasks](../../../apps/api/pycil/vocabulary/generation.py)
