# Getting started

## Prerequisites

- Python 3.14. The repository's CI/image pin is 3.14.8.
- uv; CI/image currently pin 0.12.22. Use the committed lockfile.
- PostgreSQL 18 and Redis. Repository Compose/CI pin exact store images.
- Network access to the pinned Lexi GitHub reference release during initial setup,
  or an explicit local reference.sqlite for offline setup.
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
The migration gate downloads the pinned reference.sqlite into the standard user cache,
checks its SHA-256, and imports it into PostgreSQL schema `lexi_reference`. No reference
path environment variable or API file mount is required. Repeated setup uses the
installed dataset without a download. Offline setup accepts `--reference /path/reference.sqlite`
on the same migration command. Local artifacts must be standalone snapshots without pending WAL.

Direct API commands do not automatically read repository `.env`. Export values
in the process environment, or use uv's explicit `--env-file`. Existing exported values
take precedence over values in that file, so check the target environment before a migration.
Do not print or paste the complete resolved environment to diagnose a connection.

## 3. Prepare stores and schema

The API does not migrate on startup. On a deliberately selected development target,
run the explicit migration gate from `apps/api`:

```sh
uv run --locked --env-file /absolute/path/to/development.env python -m pycil.migrate
```

The gate upgrades Lexi -> application Alembic -> imports reference and bundled content -> native checkpoints
and verifies all schema owners plus the reference marker. The fresh baseline requires
an empty application `public` schema. Historical revisions are unsupported; existing data requires a separately reviewed
transfer. Read [migrations](operations/migrations.md) before selecting a target.

The generated vocabulary snapshot is bundled at `vendor/lexi-ai/content.sqlite`,
including in the API image. Setup imports it automatically through Lexi, preserving
Word/Sense IDs without inference. Repeated setup skips an unchanged installed snapshot.
`--content /path/content.sqlite` selects another compatible standalone snapshot.

## 4. Run the API

From `apps/api`:

```sh
uv run --locked --env-file /absolute/path/to/development.env uvicorn pycil.main:app --reload
```

Use one API process. It builds search at startup and runs requested word/question
jobs in memory with singleflight. Generation can invoke paid providers; restart
interrupts active tasks while committed content remains.

## Container alternative

From the repository root, using an explicitly chosen private environment file:

```sh
python scripts/compose.py --env-file /absolute/path/to/development.env config -q
python scripts/compose.py --env-file /absolute/path/to/development.env up --build --remove-orphans
```

This starts stores, the one-shot migration service, API and Caddy. Unlike
the direct-process path, Compose includes the migration dependency. It initializes the selected current schemas and enables requested paid generation work; do not treat it as a
read-only inspection command. Review the target before running it.

Use the wrapper, not raw `docker compose`: internal DB/Redis variables are derived.
The API defaults to loopback port 8000. Caddy handles the chosen domain; its localhost
certificate uses a local CA. Reference data is read from PostgreSQL after setup. See
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
| Runtime initialization failure | Required variables, imported reference, store connectivity and all schema versions |
| Schema version mismatch | Explicit migration gate for the exact target, not startup repair |
| Missing application tables despite version rows | Schema integrity; investigate drift before rerunning anything |
| Invalid credentials | Issuer, JWKS, expiry, subject, optional audience, and Clerk identity existence |
| Empty study preparation | Saved deck memberships and effective preferences; preparation generates missing question artifacts on demand |
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
