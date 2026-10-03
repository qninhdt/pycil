# Pycil

Pycil is a subscription-based English-vocabulary tutor with user–Sense FSRS memory,
client-owned learning, a folder/deck/reference library and an assistant.

> **Backend integration fixes verified.** The API and disposable native checks pass;
> no application stack is provisioned or deployed by this work. Use the current
> [frontend/backend contract](./docs/frontend-backend-contract.md), not historical
> rewrite checkpoints or runbooks, when implementing the frontend.

## Design authority

The local, Git-ignored `plan.md` records the accepted backend design. Current API
integration contracts are documented in `docs/frontend-backend-contract.md` and
`docs/library-api.md`; the source and generated OpenAPI describe the implemented
surface. Older designs, journals and rewrite checkpoints are historical references.

## Repository

```text
apps/api       Five business modules, migrations, API and one generation worker
config         Validated YAML product policy (no credentials)
vendor/lexi-ai  Checksummed, unpublished enum-capable Lexi wheel and provenance
docs/design    Historical design pending rewrite reconciliation
docs           operational reference and history
plans          retained implementation history
```

## Local development

The frontend was intentionally removed; this rewrite does not recreate `apps/web`.

Backend requirements are Docker Compose v2 and Python 3.14.8 with `uv` 0.12.22.
Copy the environment template to your local environment file and fill required
values. Never point a fresh-schema migration at an existing application database
without an independently verified backup and explicit target approval.

The following command starts the configured stack, **not** a disposable test stack:

```bash
python scripts/compose.py up --build
```

The migration service must finish before application services start. Caddy is the
only public edge; local debug ports bind to loopback.

Only one `DB_URL` and one `REDIS_URL` are configured, including their credentials.
The Compose launcher derives official-image bootstrap fields and maps loopback
hosts to Docker DNS. No separate username/password, host-port or Docker URL
variables are required. Remote URLs remain unchanged. Use
`python scripts/compose.py config -q` for safe validation, not resolved config
output containing secrets.

`scripts/` contains only the current operational helpers:

- `compose.py`: derives Docker settings from canonical store URLs; used by Makefile/CI.
- `package-lexi.py`: rebuilds the reviewed local Lexi wheel with provenance/checksums.
- `deploy.sh`: operator-approved migration/deploy using an immutable image and a
  supplied backup file/checksum; it does not create backups.

Rehearsal scripts are removed; native schema/startup checks remain in backend tests.

### Stable infrastructure and dependency baseline (2026-10-03)

- Runtime/build: Python **3.14.8**, uv **0.12.22**, Debian **trixie**.
- Application and CI stores: PostgreSQL **18.6** (Alpine 3.24), Redis **8.10.2**
  (Alpine 3.23); edge: Caddy **2.11.6**.
- Python dependencies in Pycil and the local Lexi checkout are re-resolved to
  latest compatible stable releases; both projects explicitly disallow prereleases.
  SQLAlchemy is **2.1.3**, Tantivy **0.26.2**, OpenAI **3.24.0**, and AG-UI LangGraph
  **0.0.46**. The FSRS library remains **0.9.3**, its latest stable release.
- Upstream constraints retain `pydantic-core==2.46.5` (Pydantic),
  `uuid-utils==0.17.1` (LangChain/LangSmith require `<1`) and `websockets==16.1.1`
  (LangGraph SDK requires `<17`). These are not independently force-upgraded.
- CI uses checkout **7.0.1**, setup-uv **10.2.0**, setup-buildx **4.4.1**,
  login-action **4.6.0**, and build-push-action **7.4.0**.
- The entire `infra/` directory (rehearsals and optional WAL-G image) was removed
  at the user's request. API/worker, the application Dockerfile, production Compose,
  CI and deploy scripts do not depend on it. Production uses the stock PostgreSQL
  image, not WAL-G or MinIO; backups must be provisioned separately by the operator.

PostgreSQL 18 mounts the named volume at `/var/lib/postgresql`, with PGDATA at
`/var/lib/postgresql/18/docker`. The local old volumes were removed by the authorized
Docker reset. An existing PostgreSQL 16 cluster on any other host still requires a
verified backup and explicit `pg_upgrade` or dump/restore; changing the image is
**not** a data migration. No application services are recreated by this update.

Latest integration-fix verification: **147 Pycil tests passed** on PostgreSQL
18.6/Redis 8.10.2 and Python 3.14.8, with Ruff lint/format passing. Native persisted
approval reload and HTTP resume are covered. Disposable Caddy checks verified
uncompressed first-event delivery, upstream cancellation on disconnect, and the
exact 15,000,000-byte request boundary. AG-UI still emits 11 upstream LangGraph
deprecation warnings. No paid inference, Lexi benchmark, publication or deployment
was performed. Earlier stable-upgrade verification included **629 non-benchmark
Lexi tests**, lock/import contracts, the API image and Compose/Caddy configuration;
those builds are prior evidence, not a new build claimed for this patch.

`INFERENCE_BASE_URL`/`INFERENCE_API_KEY` are shared by generation and assistant.
The decision service has its own genuinely different endpoint/key. One
`LEXI_CAMBRIDGE_DB_PATH` works for host runtime and the read-only Compose mount.
Existing private `.env` files are not automatically rewritten; migrate old names
to the template without exposing credentials.

For host-run development, export the required variables from your own secret
manager/environment. The runtime does not automatically load `.env` files.
Run the explicit migration once against the intended application target before
starting either process:

```bash
cd apps/api
uv sync --locked
uv run --locked python -m pycil.migrate --database-url "$DB_URL"
uv run --locked python -m pycil.worker --check
uv run --locked uvicorn pycil.main:app --reload
# In another process: uv run --locked python -m pycil.worker
```

Startup verifies `public`, `lexi`, and `checkpoints` versions but never migrates or
repairs them. Worker `--check` is read-only; `--once` processes at most one request
and may run configured retention. See [dependency provenance](./vendor/lexi-ai/README.md)
for the locked library artifact; no sibling checkout or unverified PyPI release
is needed to install/build Pycil.

Pycil-generated IDs use Python 3.14 UUIDv7; existing identities, client retry keys
and Lexi's integer Word/Sense IDs remain unchanged. Explicit migration head is
`0001_baseline`, creating the current unordered membership schema. This is a fresh
baseline requiring an empty public schema, not an upgrade path for old data.

Deck details embed all `senses`, with no `sense_page` wrapper or Sense pagination.
`GET /v1/library/nodes/{id}/senses` also returns the whole deck; only folder/reference
scopes support the integer `after_id` cursor. Each Sense includes lexical display
fields and viewer-owned learning status, not full Questions/examples/relations.
Anonymous viewers receive no learner state. Editor saves use one atomic final-state
PUT. See [library UI payload](docs/library-api.md).

## Tests

Three fresh test roots. Integration/system tests require **explicit disposable**
services; fixtures refuse application database names and use only isolated
`pycil_test_<uuid>` databases and UUID-scoped Redis keys:

```bash
cd apps/api
uv run --locked pytest tests/unit -q
PYCIL_TEST_DB_URL=postgresql+asyncpg://test:test@127.0.0.1:5432/rewrite_test \
PYCIL_TEST_REDIS_URL=redis://127.0.0.1:6379/15 \
uv run --locked pytest tests -q
```

Native Lexi storage, validation, migrations and assistant graph/checkpoints remain
real; only external identity/inference boundaries are controlled. Licensed
reference data and retained benchmark evidence are not fixtures or CI downloads.
There is no frontend/browser target in this repository.

## Data safety

Postgres is canonical and contains the Pycil, Lexi, and assistant-checkpointer
schemas. Back up and verify the complete database before every schema or data
change. Redis contains short-lived assistant admission/coordination and optional
detached actor/deck caches, never learning sessions, exposures, answers or scheduling
state. PostgreSQL remains canonical.
