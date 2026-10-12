# Testing and verification

Run the current suites below. Dated verification records describe earlier revisions
and do not establish current migration or API behavior.

The browser suite is a separate opt-in profile; ordinary API tests skip it.
See [web execution instructions](../../apps/web/README.md#live-integration-and-e2e)
and the [2026-10-12 coverage review](../../plans/261012-focus-e2e-hardening/reports/verification.md)
for historical execution evidence. Current ownership and commands are in
[frontend testing](../../apps/web/tests/README.md).

## Safety boundary

Tests use explicit disposable stores, not application data. Do not derive a test URL
from production `DB_URL`, weaken the fixture's guard, call a paid model to satisfy a
fixture, or use broad Redis FLUSH/SCAN cleanup against a shared server.

The default local workflow needs Python, uv, and a running local Docker daemon with
Docker Compose. **No test URLs or application `.env` are needed.** From repository root:

```sh
make test-api
```

`scripts/test_api.py` starts only PostgreSQL and Redis from `docker-compose.test.yml`,
using a unique project per run, dynamically allocated loopback ports, and temporary
in-memory storage. It waits for health, supplies the test URLs to pytest, and removes
that exact project's containers/network/volumes afterward, including failed tests,
startup failures, Ctrl-C, and SIGTERM. Concurrent runs use separate projects and ports.
An uncatchable SIGKILL or machine/daemon crash can still leave resources: clean only
the reported project with this test manifest, never with a broad Docker prune.

The runner does not load `.env`, use runtime `DB_URL`/`REDIS_URL`, or honor inherited
test endpoints. It disables uv dotenv loading and clears Compose overrides. It uses
repository product policy and forwards explicit pytest arguments, not inherited
`PYTEST_ADDOPTS`. It does not start API, Caddy, or paid generation jobs.
Docker may download the pinned store images the first time; subsequent runs reuse images.

Direct uv commands below run from `apps/api` unless stated otherwise. Native Lexi
reads/storage remain real; providers are replaced at inference boundaries, not by
replacing the entire dictionary with synthetic DTOs.

## Test layers

| Layer | Main coverage | Requirements |
| --- | --- | --- |
| `tests/unit` | Strict policy/preferences, identity, FSRS wrapper, configuration, pure boundaries | Locked environment; no disposable DB fixture for ordinary unit-only run |
| `tests/integration` | Actual schema/migrations, memberships, concurrency, native questions, approvals, usage | Dedicated PostgreSQL; Redis where requested; SQLite reference artifacts imported into PostgreSQL |
| `tests/system` | HTTP errors/auth/body/CORS, preferences contract, resource/process restart | Depends on selected tests; full run needs disposable stores |

The names are repository test directories, not separate invented test runners. HTTP
ASGI tests do not require starting a real external API port unless a test explicitly does so.

## Disposable PostgreSQL

The runner supplies `TEST_DB_URL` automatically. For advanced direct pytest or
CI usage only, set it to an explicitly selected `postgresql+asyncpg://` server whose
administrative database is named **`rewrite_test`**. The fixture rejects another database
name and never falls back to runtime `DB_URL`. Use a dedicated test server even though
the name guard exists: it is not proof that a host is safe.

The test role must be allowed to create/drop databases. Each fixture creates a
`pycil_test_<UUID>` database, runs the full current setup gate, disposes connections, and drops only that exact
database. Historical upgrade fixtures and tests have been removed.

On interrupted tests, inspect leftover test resources by exact identity before cleanup.
Do not drop a broadly matched set of databases or delete application volumes.

## Disposable Redis and reference fixtures

The runner supplies `TEST_REDIS_URL` automatically. A manually supplied URL
must use `redis://`, host `127.0.0.1`, and database **15**. It
must point at a dedicated test Redis instance, not production's logical DB 15. Exact
fixture keys and isolated application cache namespaces are used; no shared flush is needed.

Reference fixtures create native SQLite tables in test temporary directories and import
them into PostgreSQL through the migration gate. Lexical
fixtures insert real rows into `lexi`, with real sense FKs and question storage. They
are not production evidence artifacts and should not be reused as a production reference dataset.

`no_inference` forbids paid completion/decision calls. Learning/assistant tests that
exercise generation use deterministic external completion models while preserving native
validation, retrieval, storage, and checkpoint behavior. Do not remove the provider guard
to "fix" a test that is accidentally reaching an external service.

## Commands

From repository root, unit-only checks do not need Docker:

```sh
make test-unit
```

Managed full suite or individual layers, from repository root:

```sh
make test-api
make test-integration
make test-system
```

Each invocation manages its own fresh stores. To run a targeted selection, pass pytest
arguments to the runner from repository root:

```sh
python scripts/test_api.py tests/integration/test_library.py -q
python scripts/test_api.py tests/integration/test_nodes_migration.py -q
python scripts/test_api.py tests/integration/test_learning_pipeline.py -q
python scripts/test_api.py tests/integration/test_assistant.py -q
python scripts/test_api.py tests/integration/test_query_timeout.py -q
```

Arguments are resolved relative to `apps/api`, regardless of the runner's launch directory.
The pytest exit status is preserved. Failed cleanup is reported and cannot turn into success.

CI already provisions isolated services through GitHub Actions, so it continues to use
direct pytest with explicit test URLs rather than provisioning a second Docker project.
If deliberately using independently managed disposable stores, export both test URLs
and run `uv run --locked pytest tests -q` from `apps/api`; keep these variables out of
the application's `.env`. Missing variables give a hint to use `make test-api`.

Static and packaging checks:

```sh
uv run --locked ruff check pycil tests migrations ../../scripts/test_api.py
uv run --locked ruff format --check pycil tests migrations ../../scripts/test_api.py
uv build --wheel --out-dir /tmp/opencode/pycil-docs-build
```

Use an existing approved output directory appropriate to your environment. Inspect
the wheel for `pycil/assistant/system_prompt.txt`; ignored old `prompt.md` must not be
included as the canonical prompt. A wheel build is not a complete deployment artifact
verification; the Docker image carries migration/config/reference-runtime assumptions.

From repository root, `make lint` wraps lint/format checks. `make test` aliases the
automatically managed full `make test-api` workflow.

## Evidence map

| File | Behaviors to preserve |
| --- | --- |
| `test_library.py` | Roles/paths, public-private boundaries, retained references, cycle termination, depth, membership deltas, quota races |
| `test_fresh_schema.py` | Repeatable migration gate, schema comparison, real lexical FKs, idempotent usage |
| `test_learning_pipeline.py` | Ready native questions, read-only preparation, exact applied/practice rule, replay/concurrent reviews, HTTP contracts |
| `test_progress.py` | Unique scope and current reporting semantics |
| `test_completion.py` | Atomic batches, source/context/search revocation, opaque paging, profile races, 5/50-card query parity |
| `test_completion_contracts.py` | Strict request bounds, hashes/cursors, handle normalization, streak/window boundaries |
| `tests/performance/test_read_matrix.py` | Opt-in isolated EXPLAIN and smoke-load artifacts; skipped unless tier selected |
| `test_assistant.py` | Approved/rejected tools, live reauthorization, persisted interrupt recovery, cancellation and leases |
| `test_account_lifecycle.py` | Identity cache, current entitlement, anchored usage, plan changes |
| `test_query_timeout.py` | Retryable SQL cancellation and fresh request transaction recovery |
| `test_bootstrap.py` | Resource ownership, schema refusal, partial startup cleanup, separate schema owners |
| `test_test_runner.py` | Managed endpoint isolation, unique projects, cleanup on failures/interruption, exit statuses, safe port bindings |
| System HTTP/preferences/restart tests | Safe errors, CORS, bounded bodies, auth alternatives, lifecycle and public contracts |

## Baseline result and what it does not prove

The last implementation-stage run recorded **158 passing tests**, plus 11 upstream
LangGraph deprecation warnings. Ruff checks and wheel inspection passed. Those results
describe the foundation commit; they are not tests of unimplemented batch/activity/search
features or a claim that this documentation task executed the full database suite again.

Documentation-task verification on 2026-10-06 ran the unit suite (**50 passed**), checked
local links and balanced fences across all 16 Markdown files, schema-validated all 8
JSON request/error examples, and confirmed that the module route tables cover all 26
generated business operations. Schema inspection did not start the runtime lifespan,
run migrations, or call providers. These checks are distinct from the earlier full suite.

After adding the managed runner and renaming environment variables, `make test-api`
passed **181 tests** with the same 11 upstream warnings on automatically created stores.
Lint/format, deployment Compose validation, and deployment shell syntax passed. Separate
real runner checks verified cleanup after a pytest selection error (exit 4) and SIGTERM
during a running test (exit 130). The interruption check ran concurrently with the full
suite in a separate project without affecting that suite's stores.

The CI workflow uses PostgreSQL 18.6/Redis 8.10.2 and tests wheel integrity, lint/format,
the suite, Docker build, safe Compose config, and Caddy config. Trigger coverage is
PRs to main/dev and pushes to main, not every dev push.

The final working-tree suite adds actual batch/activity/search/context/profile and
opaque-cursor coverage. Historical counts above describe their own checkpoints, not
the final run. Current evidence lives in [implementation status](implementation-status.md).
[Performance procedure](operations/performance.md) distinguishes local query/smoke-load
artifacts from an approved production capacity gate. Production restore rehearsals,
live FE/provider-host acceptance and long-duration scale signoff remain external gates.

## Documentation checks

When updating these pages, validate local Markdown links, route names against generated
OpenAPI, shell command working directories, and examples against current request schemas.
Keep future contracts explicitly separate. Product acceptance criteria describe intended
behavior and should never be mistaken for evidence of a passing backend test.

## Sources

- [Fixtures](../../apps/api/tests/conftest.py), [test directory](../../apps/api/tests/)
- [Make targets](../../Makefile), [CI](../../.github/workflows/test.yml)
- [Managed test runner](../../scripts/test_api.py), [isolated Compose stores](../../docker-compose.test.yml)
- [Project tools](../../apps/api/pyproject.toml), [implementation status](implementation-status.md)
