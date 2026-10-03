# Fresh backend verification

Use Python 3.14 and `uv sync --locked` in `apps/api`. The checksummed local Lexi
wheel is installed from `vendor/lexi-ai`, not a missing sibling or presumed release.

| Root | Command | Requirements |
| --- | --- | --- |
| unit | `uv run --locked pytest tests/unit -q` | no external services |
| integration | `uv run --locked pytest tests/integration -q` | dedicated PostgreSQL; real Redis for assistant/bootstrap |
| system | `uv run --locked pytest tests/system -q` | dedicated PostgreSQL/Redis; controlled identity/provider boundaries |

Integration/system fixtures require explicit `PYCIL_TEST_DB_URL` pointing to the
administration database **`rewrite_test`**, plus `PYCIL_TEST_REDIS_URL` pointing to
**loopback DB 15**. Each test creates and removes only its own UUID-named application
database and exact namespaced Redis keys. Fixtures never infer/reset an application
target or flush Redis. Missing dependencies fail, rather than yielding skipped gates.

```sh
PYCIL_TEST_DB_URL=postgresql+asyncpg://test:test@127.0.0.1:5432/rewrite_test \
PYCIL_TEST_REDIS_URL=redis://127.0.0.1:6379/15 \
uv run --locked pytest tests -q --tb=short
uv run --locked ruff check pycil migrations tests
uv run --locked ruff format --check pycil migrations tests
```

Native Lexi storage/validation/migrations and assistant graph/protocol/checkpoints
are real. External provider/identity boundaries are deterministic. Reference SQLite
records are freshly authored native fixtures, not licensed corpus/golden evidence.
There are no live model calls, benchmark reruns, Clerk secrets, browser tests,
`tests/worker` compatibility root or frontend CI downloads.

CI provisions PostgreSQL 18 and Redis, runs the entire fresh suite without skips,
checks wheel hashes and lint/format, builds the one API/worker/migration image, and
validates Compose/Caddy with dummy variables. It does not deploy a database or
perform the approved development reset. Image publication remains a separate
workflow; no publication has been performed during this rewrite.

Latest frontend-integration checks: **147 passed**, with 11 upstream AG-UI/LangGraph
warnings. Existing tests cover PUT preflight, typed OpenAPI/auth/errors/SSE,
persisted approval reload through a fresh runtime and HTTP approve/reject resume.
Disposable Caddy transport checks verified a 1.2 MB SSE request, uncompressed
first-event delivery, upstream disconnect cancellation and acceptance/rejection at
15,000,000/15,000,001 bytes. These are offline/provider-controlled checks, not a
production deployment or browser/paid-provider certification.

The full Lexi suite must also pass in its own reviewed source checkout:

```sh
LEXI_REQUIRE_PG=1 \
LEXI_TEST_PG_URL=postgresql+asyncpg://test:test@127.0.0.1:5432/rewrite_test \
.venv/bin/python -m pytest tests -q --tb=short
```

Rebuild the local artifact only after reviewed library changes, refresh its
provenance/lock, and repeat package/Pycil/container gates. See
[`vendor/lexi-ai/README.md`](../vendor/lexi-ai/README.md).
