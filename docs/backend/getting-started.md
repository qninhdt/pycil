# Getting started

## Prerequisites

- Python 3.14. The repository's CI/image pin is 3.14.8.
- uv; CI/image currently pin 0.12.22. Use the committed lockfile.
- PostgreSQL 18 and Redis. Repository Compose/CI pin exact store images.
- A valid native Cambridge SQLite reference dataset, kept outside source control.
- Clerk configuration plus inference/decision service addresses and credentials for a
  complete runtime. Tests substitute provider boundaries; normal runtime does not.
- Docker for the repository's container workflow, or independently managed local stores.

No product FE client is required for backend setup. Leave existing local `apps/web`
starter/showcase work intact; do not silently overwrite it or scaffold another app.

## 1. Install the locked application

From the repository root, verify the committed Lexi artifact without rebuilding it:

```sh
cd vendor/lexi-ai
sha256sum --check SHA256SUMS
```

From `apps/api`:

```sh
uv sync --locked
```

The local wheel at `vendor/lexi-ai` is an unpublished reviewed dependency, not a promise
that the same code is available on PyPI. A missing/mismatched wheel must be resolved
through its documented provenance process, not a silent switch to the released package.
See [vendor documentation](../../vendor/lexi-ai/README.md).

## 2. Supply a private environment

Use `.env.example` as a field checklist, but create your own private file and do not
overwrite an existing `.env`. Fill the values listed in [configuration](configuration.md).
Choose an explicit development database; never use production as a quickstart target.
Use an absolute path for `LEXI_CAMBRIDGE_DB_PATH`.

Direct API/worker commands do not automatically read repository `.env`. Export values
in the process environment, or use uv's explicit `--env-file`. Existing exported values
take precedence over values in that file, so check the target environment before a migration.
Do not print or paste the complete resolved environment to diagnose a connection.

## 3. Prepare stores and schema

The API does not migrate on startup. On a deliberately selected development target,
run the explicit migration gate from `apps/api`:

```sh
uv run --locked --env-file /absolute/path/to/development.env python -m pycil.migrate
```

The gate upgrades Lexi -> application Alembic -> native checkpoints and verifies all
three. The fresh baseline requires an empty application `public` schema. For existing
data, read [migrations](operations/migrations.md) first; placement changes require
quiesced writers, a verified backup, and cannot be undone by merely downgrading an image.

## 4. Run API and worker

In separate terminals, both from `apps/api`:

```sh
uv run --locked --env-file /absolute/path/to/development.env uvicorn pycil.main:app --reload
```

```sh
uv run --locked --env-file /absolute/path/to/development.env python -m pycil.worker
```

The worker can invoke paid providers for queued generation. If you only need bootstrap
verification without processing jobs, use:

```sh
uv run --locked --env-file /absolute/path/to/development.env python -m pycil.worker --check
```

`--check` initializes/verifies resources but performs no generation or user-unit debit.
`--once` is different: it can process a queued generation request and incur provider usage.
Do not run a second normal worker; a session advisory lock enforces one owner.

## Container alternative

From the repository root, using an explicitly chosen private environment file:

```sh
python scripts/compose.py --env-file /absolute/path/to/development.env config -q
python scripts/compose.py --env-file /absolute/path/to/development.env up --build
```

This starts stores, the one-shot migration service, API, worker, and Caddy. Unlike
the direct-process path, Compose includes the migration dependency. It can upgrade
an existing selected database and start paid generation work; do not treat it as a
read-only inspection command. Review the target before running it.

Use the wrapper, not raw `docker compose`: internal DB/Redis variables are derived.
The API defaults to loopback port 8000. Caddy handles the chosen domain; its localhost
certificate uses a local CA. The reference artifact is mounted read-only. See
[deployment](operations/deployment.md) for store, port, and operator constraints.

## 5. Verify basic behavior

Against the direct API:

```sh
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
```

- `/health`: process liveness, not complete dependency verification.
- `/ready`: current PostgreSQL query and Redis ping; provider billing/reachability is
  not tested by this response.
- `/docs`, `/redoc`, `/openapi.json`: generated HTTP documentation.

Use a real valid Clerk bearer token for private routes; there is no documented dev-auth
bypass. First valid access provisions the user and Library roots. A token from the wrong
issuer does not become valid because its email matches a known user.

## Common setup failures

| Symptom | Check |
| --- | --- |
| Runtime initialization failure | Required variables, reference artifact, store connectivity and all schema versions |
| Schema version mismatch | Explicit migration gate for the exact target, not startup repair |
| Missing application tables despite version rows | Schema integrity; investigate drift before rerunning anything |
| Invalid credentials | Issuer, JWKS, expiry, subject, optional audience, and Clerk identity existence |
| Empty study preparation | Saved memberships, eligible question banks, preferences; preparation does not generate missing banks |
| Worker already running | Existing lock-owning process; do not bypass the lock |
| Library quota/scope error | Choose a smaller scope or reduce content; do not truncate counts |

For code verification without a configured production-like runtime, use the disposable
test workflow in [testing](testing.md): `make test-api` automatically prepares and cleans
its own PostgreSQL/Redis with Docker, without `.env` or manual test URLs.
Documentation commands are not authorization
to run a migration, deployment, or paid generation on somebody else's installation.

## External references

- [uv environment files](https://docs.astral.sh/uv/concepts/configuration-files/)
- [uv project commands](https://docs.astral.sh/uv/guides/projects/)
- [FastAPI generated documentation](https://fastapi.tiangolo.com/tutorial/metadata/)
