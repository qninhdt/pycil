# Pycil

Pycil is an English-vocabulary tutor with FSRS spaced repetition, a five-level
retrieval-depth model, a folder/deck/reference library, and an assistant operating
on the learner's own content.

## Design authority

[docs/design](./docs/design/README.md) is the current product and technical
design. Documents under [docs](./docs/) and [plans](./plans/) are operational
references and historical execution records. When they disagree with the redesign,
the redesign governs.

## Repository

```text
apps/api       FastAPI, background content tasks, SQLModel, Alembic, inline AG-UI assistant
apps/web       Next.js UI
docs/design    design authority; current behavior is reconciled per document
docs           operational reference and history
plans          retained implementation history
```

## Local development

Requirements: Docker Compose v2, Python 3.14 with `uv`, and Node.js with `pnpm`.
Copy the environment template to your local environment file, fill the required
values, then start the stack:

```bash
docker compose up --build
```

The migration service must finish before application services start. Caddy is the
only public edge; local debug ports bind to loopback.

Run packages directly when their dependencies are available:

```bash
cd apps/api && uv sync --extra dev && uv run pytest
cd apps/api && uv run pytest tests/worker
cd apps/web && pnpm install && pnpm test && pnpm build
```

See [the execution plan](./plans/260924-0608-pycil-complete-redesign/plan.md) for
the current sequence and phase status. Intermediate phases may intentionally break
contracts; the full gate must be green before deployment.

## Tests

Four levels, each a directory root rather than a marker:

```bash
cd apps/api && uv run pytest tests/unit tests/integration   # no services / containers
cd apps/api && uv run pytest tests/system                   # API + PG + Redis
cd apps/api && uv run pytest tests/worker
cd apps/web && pnpm test:unit && pnpm test:e2e              # browser needs a live stack
```

The system level starts a real API process against disposable
PostgreSQL and Redis, with a stub JWKS and a deterministic LLM gateway standing in
for Clerk and the model provider. It requires `LEXI_REFERENCE_DATASET_PATH`.

The browser level needs a Clerk test instance. See
[docs/testing-setup.md](./docs/testing-setup.md) for the secrets each CI level
requires and why a missing one fails the job rather than skipping it.

## Data safety

Postgres is canonical and contains the Pycil, Lexi, and assistant-checkpointer
schemas. Back up and verify the complete database before every schema or data
change. Redis contains transport, cache, and coordination state only.
