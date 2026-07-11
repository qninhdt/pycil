# Pycil

AI-powered vocabulary learning with FSRS-driven spaced repetition, built on
an internalized dictionary/grading engine (`lexi-ai`) and a folder/deck/
reference hierarchy.

- **Architecture:** [`docs/system-architecture.md`](docs/system-architecture.md)
- **Codebase map:** [`docs/codebase-summary.md`](docs/codebase-summary.md)
- **Roadmap:** [`docs/project-roadmap.md`](docs/project-roadmap.md)
- **Active plan:** [`plans/260705-0032-python-greenfield-migration/plan.md`](plans/260705-0032-python-greenfield-migration/plan.md)

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
              apps/worker (arq: generate_word, generate_question, grade_answer)
                     │
                     ▼
              vendor/lexi-ai (in-process) ── its OWN database (words/senses/questions)
```

Pycil never stores dictionary content — that's `lexi-ai`'s job, behind a
`LexiClient` port. See
[system-architecture.md](docs/system-architecture.md#two-database-boundary)
for the full two-database boundary rationale and
[Known Gaps](docs/system-architecture.md#known-gaps) for what isn't finished
yet (CI/CD, deploy tooling).

This repository is backend-only (API + worker + shared Python). There is no
frontend in this repo; any client consumes the API over REST + bearer JWT.

## Local development

Prereqs: Docker 24+, docker-compose v2, `uv`, a Google OAuth client, an
OpenRouter (or compatible) API key, and a checkout of `lexi-ai` at
`~/projects/lexi-ai`.

### 1. Vendor lexi-ai

`apps/api` and `apps/worker` depend on `lexi-ai` as an editable path package
at `vendor/lexi-ai` (gitignored — not committed). Symlink or copy your
`lexi-ai` checkout in:

```bash
ln -s ~/projects/lexi-ai vendor/lexi-ai
```

Then copy its Cambridge dictionary SQLite source (~142MB, also gitignored)
so lexi's `search()` doesn't return empty:

```bash
cp -r ~/projects/lexi-ai/data vendor/lexi-ai/data
```

### 2. Environment

```bash
cp .env.example .env
# Fill in at minimum: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
# LEXI_LLM_API_KEY (OpenRouter key), AUTH_JWT_SECRET (openssl rand -base64 32),
# CENTRIFUGO_API_KEY + CENTRIFUGO_TOKEN_HMAC_SECRET (openssl rand -hex 32).
```

### 3. Run the stack

```bash
docker compose up --build
```

The `migrate` service runs `alembic upgrade head` once and must succeed
before `api`/`worker` start (compose `depends_on: service_completed_successfully`
— no manual migration step needed). API on `http://localhost:8000`,
Centrifugo on `http://localhost:8001`.

### Running the backend without Docker

```bash
cd apps/api && uv sync && uv run alembic upgrade head && uv run uvicorn pycil.main:app --reload
cd apps/worker && uv sync && uv run arq pycil_worker.main.WorkerSettings
```

Both need Postgres/Redis reachable per your `.env`, and `vendor/lexi-ai` in
place as above (`uv sync` installs it as an editable dependency via
`[tool.uv.sources]` in each `pyproject.toml`).

## Tests

```bash
cd apps/api && uv run pytest        # real Postgres (pytest-postgresql) + fakeredis
cd packages/shared-py && uv run pytest
```

`apps/worker` has no test suite yet (see Known Gaps).

## Production deploy

```bash
cd /opt/pycil && git pull && IMAGE_TAG=<sha12> bash scripts/deploy.sh
```

Migration-then-swap: pulls new images, runs the `migrate` one-shot service
against the new image, aborts before swapping if migration fails, then swaps
containers and health-gates `api`/`worker`. See the script for details.

Back up **both** databases before a deploy — pycil's Postgres (`backup`
compose profile, restic-based) and lexi-ai's own database. Only the former is
automated today; see [Known Gaps](docs/system-architecture.md#known-gaps).

## Repo layout

```
apps/
  api/         FastAPI + SQLModel + Alembic — current backend
  worker/      arq — current worker (3 jobs)
packages/
  shared-py/   Cross-service package: FSRS engine, realtime channel/payload builders
vendor/
  lexi-ai/     Editable path dep (gitignored) — dictionary/question/grading authority
docs/          Architecture, codebase map, roadmap, changelog
plans/         Migration + feature plans
docker-compose.yml          Current stack: postgres, redis, centrifugo, migrate, api, worker, backup
```

## Scope

Google sign-in (OAuth 2.1 + PKCE) · folder/deck/reference hierarchy · lazy
LLM-generated dictionary entries via lexi-ai · 4 question formats
(definition MCQ, contextual MCQ, cloze, use-in-sentence) mastery-gated per
sense · FSRS-4.5 spaced repetition · Centrifugo realtime grading/job updates.

Removed in this migration (deliberate, not deferred): billing, gamification,
admin dashboard, chat-with-AI, translation/TTS, ELO scoring, SSE-based
streaming.
