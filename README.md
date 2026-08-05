# Pycil

AI-powered vocabulary learning with FSRS-driven spaced repetition and the
GitHub-pinned `lexi-ai` domain library, plus a folder/deck/reference hierarchy.

- **Architecture:** [`docs/current-system-architecture.md`](docs/current-system-architecture.md)
- **Codebase map:** [`docs/codebase-summary.md`](docs/codebase-summary.md)
- **Frontend BFF contract:** [`docs/frontend-integration-guide.md`](docs/frontend-integration-guide.md)
- **Roadmap:** [`docs/project-roadmap.md`](docs/project-roadmap.md)
- **Active plan:** [`plans/260716-1321-system-design-alignment-hardening/plan.md`](plans/260716-1321-system-design-alignment-hardening/plan.md)

## Architecture

```
[API clients] ── bearer JWT + REST ─┐
                                     ▼
                              apps/api (FastAPI, :8000)
                                     │
                     ┌───────────────┼────────────────┐
                     ▼               ▼                ▼
               Postgres         Redis 7          Centrifugo (realtime)
              (public + `lexi` schemas)           (owner-scoped channels)
                     ▲
                     │ single writer
              apps/worker (arq: generate_word, prepare_questions, grade_answer_v1,
              reconcile_pending_grades)
                     │
                     ▼
               embedded `lexi-ai` (words/senses/questions in `lexi` schema)
```

Pycil does not duplicate dictionary content in its application schema. The
embedded `lexi-ai` library owns the isolated `lexi` schema; API and worker use
independent pools.

The repository also contains the web client in `apps/web`: a Next.js 16 App
Router BFF that seals bearer tokens in an encrypted `HttpOnly` `iron-session`
cookie and forwards `Authorization: Bearer` only from the server, so a token
never reaches the browser. It talks to the API over REST and receives task
updates over Centrifugo SSE.

## Local development

Prereqs: Docker 24+, docker-compose v2, `uv`, a Google OAuth client, and network
access to the pinned public `lexi-ai` Git revision during dependency installation.

### 1. Environment

```bash
cp .env.example .env
# Fill in at minimum: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
# AUTH_JWT_SECRET (openssl rand -base64 32),
# CENTRIFUGO_API_KEY + CENTRIFUGO_TOKEN_HMAC_SECRET (openssl rand -hex 32).
# Set LEXI_REFERENCE_DATASET_PATH to the immutable reference artifact and
# LEXI_REFERENCE_DATASET_FINGERPRINT to its approved identity.
```

### 2. Run the stack

```bash
docker compose up --build
```

The `migrate` service runs `alembic upgrade head` once and must succeed
before `api`/`worker` start (compose `depends_on: service_completed_successfully`
— no manual migration step needed). Caddy is the public API/SSE ingress on
`https://localhost` (Caddy's local certificate); the API debug bind remains
`http://127.0.0.1:8000`. Centrifugo has no public host port.

For production, set `ENVIRONMENT=production`, non-placeholder secrets, exact
`DOMAIN`, `ALLOWED_ORIGINS`, and `OAUTH_REDIRECT_URIS` (the Next.js BFF callback URL).
The API refuses to start if any of those production safeguards are missing.

### Running the backend without Docker

```bash
cd apps/api && uv sync && uv run alembic upgrade head && uv run uvicorn pycil.main:app --reload
cd apps/worker && uv sync && uv run arq pycil_worker.main.WorkerSettings
```

Both need Postgres/Redis plus the read-only reference artifact configured by
`LEXI_REFERENCE_DATASET_PATH`.

### Running the web app without Docker

```bash
cd apps/web && pnpm install
pnpm dev                            # http://localhost:3000
pnpm build && pnpm start            # production build
```

`apps/web` reads four variables of its own, seeded from `apps/web/.env.example`:

| Variable | Purpose |
|----------|---------|
| `SESSION_PASSWORD` | iron-session encryption password, at least 32 bytes (`openssl rand -base64 32`). No default — the app refuses to boot without it rather than sealing cookies with a shared key. |
| `SESSION_COOKIE_NAME` | Cookie name, `pycil_session` by default. |
| `PYCIL_API_URL` | Server-side API origin. Never reaches the browser, so under Compose it is the container-internal `http://api:8000`. |
| `NEXT_PUBLIC_APP_URL` | Public origin and OAuth callback base. Inlined into the bundle at build time, so Compose passes it as a build arg rather than an environment variable. |

Under `docker compose up` the `web` service supplies all four; only
`SESSION_PASSWORD` has to be present in the root `.env`.

## Tests

```bash
cd apps/api && uv run pytest        # disposable Postgres (Testcontainers) + fakeredis
cd packages/shared-py && uv run pytest
cd apps/web && pnpm test            # Vitest: reducer, mastery, SSE frames, taxonomy
cd apps/web && pnpm audit:design    # ten mechanical design-system rules
cd apps/web && pnpm test:e2e        # Playwright, against a running stack
```

The worker has registration plus durable generation/grade-job coverage. API
and shared-package tests cover the remaining domain behaviour. The web suite is
three layers: Vitest for pure logic, Storybook for component states, and
Playwright against the live stack — the last needs `docker compose up` first,
since it drives real sessions and real grading.

## Production deploy

```bash
cd /opt/pycil && git pull && IMAGE_TAG=<sha12> bash scripts/deploy.sh
```

Migration-then-swap: pulls new images, runs Lexi's domain migration before
Pycil's migration in the `migrate` one-shot service, aborts before swapping if
either fails, then swaps containers and health-gates `api`/`worker`. API
readiness includes Postgres, Redis, a live worker heartbeat, and Centrifugo.
Run `bash scripts/rehearse-fresh-schema.sh` against an empty Compose project
before an external deploy.

Back up the shared Postgres database before a deploy; it contains Pycil's
`public` schema and Lexi's isolated `lexi` schema.

## Repo layout

```
apps/
  api/         FastAPI + SQLModel + Alembic — current backend
  worker/      arq — current worker (4 jobs, including durable-grade reconciliation)
packages/
  shared-py/   Cross-service package: FSRS engine, realtime channel/payload builders
docs/          Architecture, codebase map, roadmap, changelog
plans/         Migration + feature plans
docker-compose.yml          Current stack: postgres, redis, centrifugo, migrate, api, worker, backup
```

## Scope

Google sign-in (OAuth 2.1 + PKCE) · folder/deck/reference hierarchy · durable
Lexi word-generation jobs · 4 question formats
(definition MCQ, contextual MCQ, cloze, use-in-sentence) mastery-gated per
sense · FSRS-4.5 spaced repetition · Centrifugo realtime grading/job updates.

Learning sessions issue one canonical question at a time from a Redis-backed
queue. First attempts are claimed durably in Postgres; `use_in_sentence`
answers return a pending task receipt and are reconciled if enqueueing or a
worker lease is lost. Clients receive owner-authorized task snapshots through
Centrifugo SSE only.

The API also provides an owner-scoped conversational assistant under
`/assistant`. It uses a bounded LangChain tool set for hierarchy/content/stats,
recoverable SSE runs, and durable human approval for move, publication, delete,
and sense-removal actions. It is enabled only when its separate
OpenAI-compatible credential and base URL are configured; it is not an
OpenRouter integration. Threads/checkpoints expire after 30 inactive days,
while minimized action-audit records are retained for 90 days.
