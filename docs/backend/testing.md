# Backend testing

The backend suite was rebuilt for the consolidation described in
[the redesign](../../plans/260924-0608-pycil-complete-redesign/plan.md). Historical verification records describe earlier
revisions and are not evidence for the current implementation.

## Structure and boundaries

```text
apps/api/tests/
├── unit/
├── integration/
├── support/
└── conftest.py
```

Unit and integration tests use domain directories when there are tests for that domain.
Application lifecycle tests belong in `integration/app`; infrastructure contracts belong
in `integration/infrastructure`. There is no backend system or browser E2E suite. Small explicit cache/search benchmarks
are in `tests/benchmarks`; they report declared local workloads, not production capacity.

| Layer | What runs | External services |
| --- | --- | --- |
| Unit | An isolated component or pure contract; dependencies may be replaced. | No PostgreSQL, Redis, Docker or paid provider calls. |
| Integration | Real collaborating services, validation, transactions and persistence. | PostgreSQL and Redis from Testcontainers when requested; real Tantivy where relevant. |

Controlled completion/decision responses replace the external provider boundary only.
Internal business services, SQL constraints, artifact validation, search publication and
native checkpoint persistence remain real. ASGI transports can exercise real HTTP routes
without a separate server process.

Product browser E2E belongs to the root [`e2e/`](../../e2e/README.md) package.
It runs the production API with disposable infrastructure and real development
identity. Its fixtures do not import backend integration fixtures.

## Infrastructure ownership

[Container fixtures](../../apps/api/tests/support/containers.py) lazily start pinned
PostgreSQL and Redis containers. Selecting only unit tests starts neither container.
The same fixtures run locally and in CI; CI does not provision duplicate services.

Each PostgreSQL test creates a unique database, applies the application baseline and additive migrations
and native checkpoint setup, disposes its engine and drops that database. Redis fixtures
use unique key namespaces and remove only their own keys. Clients and pools close before
their stores are stopped. Testcontainers cleanup support stays enabled.

No application `.env`, `DB_URL`, `REDIS_URL`, manually supplied test endpoints or Compose
manifest is needed. Tests do not infer a test target from deployment credentials, use
SQLite as a substitute for PostgreSQL, or flush a shared Redis server.

Reference fixtures construct small valid JSONL artifacts. They exercise the real
transactional importer and preserve source IDs. The full reference artifact is validated
separately; normal tests do not import its entire contents for every case.

## Commands

From the repository root:

```sh
make test-unit
make test-integration
make test-api
make lint
make openapi
```

Integration tests require a running Docker daemon. For focused checks, run from `apps/api`:

```sh
uv run --locked pytest tests/integration/study -q
uv run --locked pytest tests/integration/assistant -q
uv run --locked pytest tests/unit/infrastructure -q
```

For local cache-only and small revision/index cost measurements (no live credentials):

```sh
uv run --locked pytest -s tests/benchmarks -q
```

RAM versus Redis uses the same verified-ID-sized UUID, with no SQL in either timed path.
Capacity measurements decode independent DTOs rather than sharing nested objects.
Search failure tests use real disk indexes, four spawned processes, owner SIGKILL and
crashes immediately before/after native commit; all child processes are joined/terminated.

`pytest` owns fixture setup and cleanup directly. There is no custom Compose test runner.

To build the wheel from `apps/api`:

```sh
uv build --wheel --out-dir /tmp/pycil-wheel
```

Inspect the actual wheel when changing prompt packaging. Prompts live in the owning
modules, including `assistant/prompts/system_prompt.txt`; building a wheel alone does
not verify deployment startup or a live model provider.

## Meaningful assertions

Tests protect source import atomicity/idempotency, evidence validation, incremental
search, artifact bank integrity, grading without writes, review and usage replay,
concurrent preference updates, publication revocation, checkpoint persistence and
resource cleanup. See the current test files for exact assertions.

Do not add tests solely for coverage, directory names or the absence of retired names.
Keep batching or query-bound assertions with the behavior they protect. Use controlled
provider output without bypassing the application's validation.

Live identity/model calls, browser E2E, image builds and deployment restore rehearsals
are separate checks. A passing local backend suite does not establish those outcomes.

## Sources

- [Test registration](../../apps/api/tests/conftest.py)
- [Shared test support](../../apps/api/tests/support/)
- [Build and test configuration](../../apps/api/pyproject.toml)
- [Commands](../../Makefile), [CI workflow](../../.github/workflows/test.yml)
