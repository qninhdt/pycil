# Getting started

## Prerequisites

Python 3.14, uv, PostgreSQL 18, Redis, and Docker for Testcontainers or the Compose
workflow. Use committed dependency locks. A complete runtime also requires Clerk and
model provider configuration. Tests never call paid providers.

## Install and configure

From `apps/api`:

```sh
uv sync --locked
```

Use the root `.env.example` as a checklist for a private environment file. Choose an
explicit development database. Direct commands require exported environment variables
or uv's `--env-file`; the application does not load dotenv files automatically.
See [configuration](configuration.md).

## Initialize an empty development database

From `apps/api`, with the intended stores already running:

```sh
uv run --locked --env-file /absolute/path/to/development.env python -m pycil.app.migrate --reference ../../data/reference.jsonl.gz
```

This applies the single application baseline, sets up native checkpoints in `public`,
and imports the reference JSONL transactionally. An identical reimport is safe; conflicting
content fails. There are no automatic downloads or mandatory generated-content seeds.
The schema-only command omits `--reference`, but API startup requires imported reference.
Old schema revisions require an explicit export/transfer; see [migrations](operations/migrations.md).

## Run

```sh
uv run --locked --env-file /absolute/path/to/development.env uvicorn pycil.main:app --reload
```

Search uses an in-memory index unless `SEARCH_INDEX_PATH` is set. Multiple API workers
must share the disk index directory and Redis namespace; task polling reads shared Redis
status, while generation execution and singleflight stay per process. Restart interrupts
active work while committed content survives. See [runtime operations](operations/deployment.md)
for status expiry and crash limits. Requested generation may call paid providers.

For Compose, run from the repository root:

```sh
python scripts/compose.py --env-file /absolute/path/to/development.env config -q
python scripts/compose.py --env-file /absolute/path/to/development.env up --build --remove-orphans
```

Compose mounts `data/reference.jsonl.gz` read-only into its one-shot migration service.
The API reads reference rows from PostgreSQL and has no artifact mount. The wrapper
derives store addresses; use it instead of raw Compose. This workflow writes the selected
database. Review its target before running it.

## Check runtime and code

```sh
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

Health checks liveness. Readiness checks PostgreSQL, Redis and the initialized search
snapshot; it does not call identity or model providers. `/docs` and `/openapi.json`
describe the API. Private requests require real valid Clerk JWTs; there is no auth bypass.

Use [backend tests](testing.md) to verify code against disposable stores without deployment
credentials. `make test-api` starts only fixture-owned Testcontainers infrastructure.
