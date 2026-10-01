# Test setup and CI secrets

Four levels, each a directory root. The level is where a file lives, so a test
cannot be collected at one level and reported at another.

| Level | Where | Command | Needs |
|---|---|---|---|
| unit | `apps/api/tests/unit`, `apps/api/tests/worker/unit`, `apps/web/tests/unit` | `uv run pytest tests/unit tests/worker/unit` | nothing |
| integration | `apps/api/tests/integration`, `apps/api/tests/worker/integration`, `apps/web/tests/integration` | `uv run pytest tests/integration tests/worker/integration` | PostgreSQL; Redis for the worker |
| system | `apps/api/tests/system` | `uv run pytest tests/system` | PostgreSQL, Redis, the Cambridge artifact |
| browser | `apps/web/tests/e2e/specs` | `pnpm test:e2e` | a running backend stack and a Clerk test instance |

Locally, the integration and system levels provision PostgreSQL and Redis with
Docker through `testcontainers`. In CI the services are already present, and
`TEST_DB_URL`, `TEST_REDIS_URL`, `TEST_STACK_DB_URL` and `TEST_STACK_REDIS_URL`
point at them instead — a container inside the job would be a second one.

## The Cambridge reference artifact

The system level reads dictionary content from a Cambridge SQLite artifact. It is
a licensed 142 MB file, **not** a build output, so CI cannot generate it. The
`test-system` job downloads it and verifies its SHA-256 before running.

Configure these repository secrets:

| Secret | Value |
|---|---|
| `LEXI_REFERENCE_DATASET_URL` | A download URL for the artifact |
| `LEXI_REFERENCE_DATASET_SHA256` | Its SHA-256, as recorded in `.env.example` |

**When either is absent the job fails, it does not skip.** A gate that reports
green while proving nothing is worse than a red one: it is the failure mode this
test architecture was written to remove. The same rule applies to the browser job
and `CLERK_PUBLISHABLE_KEY`.

## The Clerk test instance

The browser level needs a Clerk **test** instance — `pk_test_`/`sk_test_` values,
never production keys. With no publishable key, Clerk's `<SignIn>` renders no
markup, so no spec can reach a signed-in state.

| Secret | Value |
|---|---|
| `CLERK_PUBLISHABLE_KEY` | The test instance's publishable key |
| `E2E_API_URL` (variable) | The backend origin the browser build targets |

`NEXT_PUBLIC_*` values are inlined into the bundle at build time, so the browser
job sets `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` before `pnpm build`, not only before
`pnpm test:e2e`.

## Fail closed

A test that cannot reach its dependency fails rather than skipping. The system
level is skipped only when neither Docker nor configured stores exist, which is a
statement about the machine, not about the code — and CI always configures stores,
so the skip never applies there.
