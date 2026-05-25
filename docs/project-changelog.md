# Pycil — Changelog

All notable releases. Format derived from Keep a Changelog; dates in ISO-8601.

---

## [Unreleased] — 2026-05-25 — Frontend migration + BFF removal

`plans/260525-0411-frontend-migration/` (11 phases, all completed).

### Changed — Architecture

- **Frontend replaced wholesale**: `apps/web/` swapped to a copy of `openlet-web-legacy/`, rebranded openlet → pycil throughout. Old web preserved on the prior commit; `apps/web-legacy-backup/` removed.
- **BFF layer removed**: deleted `apps/web/src/lib/db.ts`, `lib/api.ts`, `lib/actions.ts`, `lib/learning-actions.ts`, `lib/questions.ts`, and the Next-side SSE route at `app/api/jobs/[id]/stream/route.ts`. Browser now talks directly to FastAPI through Caddy `/api/core/*`.
- **Auth.js v5 strategy switched from DB-session to JWT-cookie** (HS256 via `jose` custom encode/decode). FastAPI verifies the same JWT with PyJWT. Cookie renamed to `pycil-session` / `__Secure-pycil-session`. `@auth/pg-adapter` and the `sessions`/`accounts`/`verification_token` tables were dropped from the web's responsibilities (Alembic migration 0003).
- **SSE moved to FastAPI**: `GET /jobs/{id}/stream` is now served by `pycil-core` via `redis.asyncio.pubsub` + `StreamingResponse`. Caddy SSE matcher path is now `/api/core/jobs/*/stream` (declared inside `handle_path /api/core/*` post-strip block).
- **Internal endpoint isolation**: `respond /api/core/auth/* 404` rule blocks the public proxy from reaching `POST /auth/upsert-user`, which is reachable only from the web container via the docker network using `INTERNAL_API_SECRET`.

### Added — Frontend

- **TanStack Query v5** as the only data layer. Single `query-keys.ts` factory, global 401 interceptor that clears the cache and redirects to `/sign-in?reason=expired`.
- **`api-client/`** layer (one module per resource: `nodes`, `terms`, `learning`, `questions`, `auth`, `onboarding`, `jobs`).
- **`api-hooks/`** layer (TanStack mutations + queries with cache invalidation).
- **Sonner toasts** + centralized `apiErrorMessage(error, fallback)` helper.
- **Job stream watcher** consumes the new BE-served SSE.

### Removed — Frontend dead links

- Removed: `/classes`, `/saved`, `/trash`, `/decks/new`, `/decks/[id]/edit`, `/decks/[id]/chat`, `/decks/[id]/test`, "Get Started 7/10" widget, command-palette deck/action shortcuts, `CreateShortcutDialog`, `MAIN_MENU_ITEMS`, `SECONDARY_MENU_ITEMS`. Sidebar reduced to Home + (avatar) Profile + (avatar) Settings. Header reduced to search + notifications + user dropdown.

### Schema

- Migration `0002_jwt_auth_drop_sessions.py`: adds `users.token_version SMALLINT NOT NULL DEFAULT 0` for JWT revocation; drops `sessions`, `accounts`, `verification_token`. Migration `0003_partial_unique_onboarding_seed.py`: partial unique index for idempotent onboarding seed.

### Infrastructure

- Web hosted on **Vercel** (separate platform). The repo no longer ships an `apps/web/Dockerfile` or a `web` service in `docker-compose.yml`. VPS docker stack is now api-only: `pycil-core`, `worker`, `postgres`, `redis`, `caddy`.
- Caddy reduced to api-only routing: `/api/core/*` → pycil-core (with SSE matcher), `/health` passthrough, everything else returns 404. No more `reverse_proxy web:3000`.
- `docker-compose.yml`: removed `web` service entirely. Worker explicit `environment:` block — never inherits `AUTH_JWT_SECRET` / `INTERNAL_API_SECRET`.
- `.github/workflows/deploy.yml`: drops the `web` image build step; deploy script no longer exports `WEB_IMAGE`. Health check waits on `pycil-core /health` only.

### Deferred to v0.2

Notifications BE, gamification (streaks/XP/level/badges/league), write/fill question types, deck-edit endpoint, profile-image upload, shortcut node type, full Playwright E2E. Captured in `plans/260525-0411-frontend-migration/reports/v0.2-backlog.md`.

---

## [v1.0.0] — 2026-05-25

First public release. 7-day MVP sprint completed (`plans/260525-0124-pycil-mvp-implementation/`). Live launch event still pending — docs and assets ready.

### Added — Core platform

- **Three-service docker-compose stack**: `web` (Next.js 15), `pycil-core` (FastAPI), `worker` (arq + LangChain), plus Postgres 16, Redis 7, and Caddy 2 with auto-TLS via Let's Encrypt.
- **Auth.js v5 + Google OAuth** sign-in via `@auth/pg-adapter`. Cookies use `__Secure-authjs.session-token` (prod) / `authjs.session-token` (dev) with `SameSite=Strict`. FastAPI shares the `sessions` table read-side and enforces mandatory `WHERE expires > NOW()` on session lookups.
- **CSRF defense**: Origin-allowlist middleware (`apps/pycil-core/pycil_core/middleware/csrf.py`) on every mutating verb, complementing `SameSite=Strict` cookies.
- **Caddy config**: SSE carve-out (`flush_interval -1` + `X-Accel-Buffering no`), `handle_path /api/core/*` prefix strip, separate `Caddyfile.local` with `local_certs` so dev never burns the Let's Encrypt rate limit.
- **GitHub Actions deploy**: SSH-based with `pg_dump` snapshot, **migration-then-swap order** (one-shot Alembic against new image before `docker compose up -d`), and per-migration rollback playbook.

### Added — Content + AI pipeline

- **Folder/deck/term CRUD** with breadcrumb (recursive CTE on `parent_node_id`).
- **AI term enrichment**: `POST /decks/{id}/terms` -> `generate_term` arq job. Worker calls OpenRouter via LangChain `ChatOpenAI(...).with_structured_output(method="json_mode")` with default model `openai/gpt-4o-mini`. Output: 1 canonical definition + 3 paraphrases (A2/B1/C1) + 3 example sentences.
- **Term-keyed SSE channel** (`results:{term_id}`) for cross-user enrichment dedup. SSE handler reads `jobs` row from Postgres FIRST and re-checks after subscribe to defeat the worker-publishes-before-client-subscribes race.
- **Per-user `user_term_jobs(user_id, term_id, job_id)` ownership table** so multiple users adding the same term share a single worker run while keeping per-user SSE access checks.
- **Cost-dedup lock**: `lock:generate_term:{term_id}` (NX EX 600) via Lua. Lock is **never** released in worker `finally` — TTL-only release so arq retries (`max_tries=2`) reuse the same lock. Pre-INSERT idempotency + `UNIQUE(term_id)` on `definitions` absorbs duplicate writes.
- **Prompt injection mitigation**: term value validated at API boundary (length <=64, no newlines/control chars), fenced inside `<USER_TERM>...</USER_TERM>` in the prompt, output sanitized (strip URLs / HTML / control chars) before INSERT.
- **Cost controls**: per-user 5/hr rate limit + global daily spend cap (`OPENROUTER_BUDGET_DAILY_USD`, default $20) tracked via `INCRBYFLOAT openrouter:spend:daily`. Budget enforced at runtime, not just startup.

### Added — Question generation

- **MCQ-only in v1** (Write + Fill deferred to v0.2 — scope cut to keep Day 4 safe).
- **`BaseQuestion` ABC** in `packages/shared-py/shared/questions/base.py` (package name `pycil-shared`), kept abstract for v0.2 plug-in subclasses.
- **`generate_question` job** + `mcq.md` Jinja2 prompt. Question cache by `definition_id` (no duplicate LLM call on second fetch).
- **Answer check**: `POST /questions/{id}/check` dispatches via `MultipleChoiceQuestion.check_answer`.

### Added — Learning Mode + ELO

- **Pure ELO module** (`apps/pycil-core/pycil_core/learning/elo.py`): constants `K=32, D=400, ALPHA=0.5, F=2.0, S=200`, ELO clamped to `[0, 3000]`, `INITIAL_ELO=1000`. Cold-start fixes: `lapsed_seconds=None` returns `T=1.0`; `interval_old=0` floors at `INITIAL_INTERVAL_SECONDS=1800` (30 min).
- **11 mastery levels** mapped from ELO buckets (`mastery_levels.py`).
- **Interval ladder snapping** in `intervals.py` (15min .. 2 months).
- **Term selection priority** (due -> new -> upcoming) in `term_selection.py`.
- **Redis-backed session state** at `learning_session:{session_id}` with 4h TTL. ELO/interval write hits Postgres only on term-reviewed event (Q=2 correct first-answers).
- **Per-session lock** (`session_lock:{session_id}` NX EX 5) with Lua-checked release. Multi-tab races return `409 session_busy`; client retries after 200ms.
- **ELO unit tests** (`elo_test.py`) — only formal test suite in v1 per PDR §9.

### Added — Polish + launch

- Marketing landing, Privacy/Terms stubs, global error boundary.
- **Onboarding seed**: idempotent `POST /onboarding/seed` creates "Welcome" folder + "Starter Verbs" deck with 5 pre-enriched terms (no LLM cost). Web fires this on first sign-in.
- Toasts, skeleton states, mobile responsiveness pass.
- Show HN + Product Hunt copy in `docs/launch-copy/`.
- Launch checklist + retro template in `docs/`.

### User-locked stack decisions (do not propose changes)

- LangChain `ChatOpenAI` called directly — no `LLMClient` abstraction layer.
- Vanilla Jinja2 prompts — no custom directive engine.
- 11 mastery levels.
- MCQ-only in v1 (Write/Fill deferred to v0.2).
- `apps/shared-py` (package `pycil-shared`) for `BaseQuestion` ABC + cross-service Pydantic schemas.
- Sentry / backups / formal test suite deferred to post-launch (only ELO unit tests in v1).

### Deferred to v0.2

Backups (off-VPS daily `pg_dump`), Sentry / monitoring, Write + Fill question types, i18n (Vietnamese first), formal test retrofit, public/cloned decks, topic/usage tags, TTS, translation pipeline, SHORTCUT node type, mobile PWA polish, payment / premium tier, question diversification across reviews, question ELO calibration.

### Known limitations

- All questions stored at ELO 1000 (no per-question calibration in v1).
- Same MCQ returned on every review of a definition (no diversification yet).
- Single-language UI (English).
- Backups are a single manual `pg_dump` pre-launch — accepted risk per PDR §9.

---

## See Also

- `docs/project-roadmap.md` — phase status and v0.2 priorities.
- `docs/project-overview-pdr.md` — locked source design.
- `docs/system-architecture.md` — runtime topology and flow diagrams.
- `docs/codebase-summary.md` — file-level map.
- `plans/260525-0124-pycil-mvp-implementation/plan.md` — sprint plan with red-team review notes.
