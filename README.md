# Pycil

AI-powered vocabulary learning with FSRS-driven spaced repetition, backed by
the separately deployed public dictionary/grading service `lexi-ai`, plus a
folder/deck/reference hierarchy.

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
             (pycil's own DB:                    (owner-scoped channels)
              users/nodes/decks/
              FSRS stats)
                     ▲
                     │ single writer
              apps/worker (arq: generate_word, generate_question, grade_answer_v1,
              reconcile_pending_grades)
                     │
                     ▼
              lexi-service (internal HTTP) ── its OWN Postgres (words/senses/questions)
```

Pycil never stores dictionary content — that's `lexi-ai`'s job, behind a
`LexiClient` HTTP port. See
[system-architecture.md](docs/system-architecture.md#two-database-boundary)
for the full two-database boundary rationale and
[Known Gaps](docs/system-architecture.md#known-gaps) for what isn't finished
yet (CI/CD, deploy tooling).

This repository is backend-only (API + worker + shared Python). There is no
frontend in this repo; any client consumes the API over REST + bearer JWT.

## Local development

Prereqs: Docker 24+, docker-compose v2, `uv`, a Google OAuth client, and a
separately deployed checkout of public [`lexi-ai`](../lexi-ai).

### 1. Environment

```bash
cp .env.example .env
# Fill in at minimum: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
# AUTH_JWT_SECRET (openssl rand -base64 32),
# CENTRIFUGO_API_KEY + CENTRIFUGO_TOKEN_HMAC_SECRET (openssl rand -hex 32).
# Also set the shared LEXI_SERVICE_INTERNAL_SERVICE_TOKEN and the verified
# LEXI_REFERENCE_DATASET_SHA256 used by the Lexi deployment.
```

### 2. Run the stack

```bash
docker compose up --build
```

The `migrate` service runs `alembic upgrade head` once and must succeed
before `api`/`worker` start (compose `depends_on: service_completed_successfully`
— no manual migration step needed). Caddy is the public API/WSS ingress on
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

Both need Postgres/Redis and an available `lexi-service` reachable on the
shared Docker network. Create it once before starting either compose project:

```bash
docker network create --internal pycil-backend
```

## Tests

```bash
cd apps/api && uv run pytest        # disposable Postgres (Testcontainers) + fakeredis
cd packages/shared-py && uv run pytest
```

The worker has registration plus durable generation/grade-job coverage. API
and shared-package tests cover the remaining domain behaviour.

## Production deploy

```bash
cd /opt/pycil && git pull && IMAGE_TAG=<sha12> bash scripts/deploy.sh
```

Migration-then-swap: pulls new images, runs the `migrate` one-shot service
against the new image, aborts before swapping if migration fails, then swaps
containers and health-gates `api`/`worker`. API readiness includes Postgres,
Redis, a live worker heartbeat, Lexi, and Centrifugo. See the script for details.

Back up **both** Postgres databases before a deploy: Pycil's database (`backup`
compose profile) and Lexi's service database.

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
answers return a pending response and are reconciled if enqueueing or a worker
lease is lost. Clients can poll `GET /responses/{id}`; realtime channels end in
the owner's Centrifugo-enforced `#userId` boundary.

The API also provides an owner-scoped conversational assistant under
`/assistant`. It uses a bounded LangChain tool set for hierarchy/content/stats,
recoverable SSE runs, and durable human approval for move, publication, delete,
and sense-removal actions. It is enabled only when its separate
OpenAI-compatible credential and base URL are configured; it is not an
OpenRouter integration. Threads/checkpoints expire after 30 inactive days,
while minimized action-audit records are retained for 90 days.
