# Pycil — Codebase Summary

**Last sync:** 2026-06-11 (post rehab Phase 11 — structured logging)
**Plans:** `plans/260525-0124-pycil-mvp-implementation/plan.md` (v1), `plans/260525-1446-pycil-v02-feature-fill/plan.md` (v0.2)
**Source design:** `docs/project-overview-pdr.md` (locked)

## v0.2 additions (post v1)

- **pycil-core services**: `cache.py` (Redis + advisory_lock), `notification_service.py`, `gamification_service.py`, `image_upload_service.py`, `search_service.py`, `share_link_service.py`, `answer_grading_service.py` (rapidfuzz tier ladder), `clone_service.py` (deep deck-clone), `chat_service.py`, `test_mode_service.py` (answer-stripped projection), `billing_service.py` (Stripe idempotency), `llm_streaming.py` (httpx OpenRouter SSE).
- **pycil-core routes**: `admin.py`, `billing.py`, `chat.py`, `notifications.py`, `public_decks.py`, `question_regenerate.py`, `search.py`, `share_links.py`, `test_mode.py`, `translate_tts.py`.
- **pycil-core middleware**: `rate_limit.py` (Redis sliding window 60 RPM/IP).
- **pycil-core cron**: apscheduler in `cron.py` runs `hard_delete_expired_users` (daily) + `compute_league_rank` (weekly), each under `pg_advisory_xact_lock`.
- **Worker jobs**: `translate_definition.py`, `tts_render.py` (Gemini Flash + B2 upload), `generate_question.py` extended for WRITE/FILL dispatch via `_TYPE_MAP`.
- **Worker observability**: `worker/observability/spend_metrics.py` structured logger (fields serialize via the shared JSON log config — see Observability section).
- **shared-py**: `shared/questions/write.py`, `fill_in_blank.py` ABCs.
- **Web FE**: `(dashboard)/explore/page.tsx`, `legal/{privacy,terms}/page.tsx`, `components/study/{learn/write-question, learn/fill-in-blank-question, chat/chat-panel, test/test-runner, tts-play-button, translation-button}.tsx`, `components/file-browser/share-link-dialog.tsx`, `components/search/search-palette.tsx`, `hooks/use-broadcast-sync.ts`.
- **Web config**: `next.config.ts` wraps with `next-pwa`, manifest.webmanifest, NetworkOnly for `/api/core/*`.
- **Infra**: `infra/backup/{Dockerfile,backup.sh,restore.sh}`; `docker-compose.yml` adds backup service profile + restic_password secret.
- **Tests**: `apps/pycil-core/tests/{conftest,test_migration_0004,test_answer_grading,test_gamification}.py`; `packages/shared-py/tests/test_questions.py`; `apps/worker/tests/conftest.py`.

---

## Admin dashboard additions (post v0.2)

`plans/260529-2356-admin-dashboard-implementation/` — admin-only `/admin` surface gated by `users.role`.

- **Migrations**: `0019_user_role_and_ban` (role enum + ban cols + `token_version` widen), `0020_llm_spend_events` (persistent spend ledger), `0021_content_reports` (moderation reports + `nodes.deleted_at`).
- **shared-py**: `UserRole` enum; `LlmSpendEvent`, `ContentReport` models; `User.role/banned_at/ban_reason`, `Node.deleted_at`.
- **pycil-core auth/deps**: `CurrentUser.role/banned_at`, ban lockout in `get_current_user`, `require_admin`/`AdminDep`.
- **pycil-core services**: `spend_ledger_service.py` (aggregations), `content_report_service.py` (create/list/resolve), `feature_flag_service.py` (+CRUD), `product_metrics_service.py` (+signup_funnel), `user_service.py` (+ban/search/detail), `node_service.py` (+admin_soft_delete_node).
- **pycil-core routes** (`/admin-api/*`): `admin_human.py` (ping), `admin_users.py`, `admin_metrics.py`, `admin_reports.py`, `admin_flags.py`, `admin_health.py`; user `reports.py` (`/reports`); `me_extras.py` audit handler re-gated → `/admin-api/audit`.
- **worker**: `observability/spend_ledger.py` (best-effort dedicated-session writer); `main.py` heartbeat cron.
- **Web FE** (`app/admin/`): `layout.tsx` (role re-check + noindex shell), `users/`, `metrics/`, `reports/`, `flags/`, `health/`, `audit/` pages; `components/reports/report-dialog.tsx`; `lib/api-client/admin.ts` + `api-hooks/use-admin-{users,metrics,reports,flags,system}.ts`.
- **Routing**: human admin routes mount under `/admin-api/*` (Caddy catch-all `/api/core/*`); internal-secret routes stay `/admin/*` (404'd publicly).

---

## Repository Layout

```
pycil/
├── apps/
│   ├── web/             # Next.js 15 (App Router) + Auth.js v5 + Shadcn
│   │   └── e2e/           # Playwright E2E test suite (6 specs)
│   ├── pycil-core/      # FastAPI + SQLModel + Alembic (sync API)
│   └── worker/          # arq consumer + LangChain + Jinja2 prompts
├── packages/
│   └── shared-py/       # Cross-service Python package (pycil-shared)
├── docs/                # This folder — design + architecture docs
├── plans/               # Sprint plans (incl. v1 MVP plan)
├── docker-compose.yml   # web + pycil-core + worker + postgres + redis + caddy
├── Caddyfile            # Production reverse proxy
└── Caddyfile.local      # Dev reverse proxy (uses Caddy internal CA)
```

Three runnable services + one shared Python package. Single Postgres, single Redis. All services on the internal docker network; only Caddy exposes 80/443.

---

## Service: `apps/web` (Next.js 15)

Port 3000. Owns the UI, Auth.js Google OAuth, the SSE bridge for job progress, and lightweight server actions that proxy to `pycil-core`.

```
apps/web/
├── auth.config.ts             # Auth.js v5 config (Google provider, SameSite=Strict)
├── auth.ts                    # @auth/pg-adapter wiring
├── middleware.ts              # Protect /dashboard/* and /learn/*
├── app/
│   ├── page.tsx               # Marketing landing
│   ├── layout.tsx             # Root layout
│   ├── error.tsx              # Global error boundary
│   ├── not-found.tsx
│   ├── api/
│   │   ├── auth/[...nextauth]/route.ts
│   │   └── jobs/[id]/stream/route.ts   # SSE handler (Postgres-first + Redis pub/sub)
│   ├── dashboard/
│   │   ├── page.tsx                    # Root nodes list
│   │   └── [nodeId]/page.tsx           # Folder/deck detail
│   ├── learn/[sessionId]/page.tsx      # Learning session loop
│   └── legal/{privacy,terms}/page.tsx  # Legal stubs
├── components/
│   ├── learning-session-runner.tsx     # Round / question / feedback driver
│   ├── multiple-choice-card.tsx        # MCQ render (Shadcn RadioGroup)
│   ├── question-renderer.tsx           # Type dispatcher (v1: MCQ-only; throws on others)
│   └── term-card.tsx                   # Enriched-term render + "Generating..." skeleton
└── lib/
    ├── api.ts                          # Cookie-passthrough fetch wrapper
    ├── db.ts                           # pg pool used by SSE handler
    ├── actions.ts                      # Node + term server actions
    ├── learning-actions.ts             # Session start / next / submit
    ├── question-actions.ts             # Question fetch
    ├── questions.ts                    # Question shape helpers
    ├── types.ts                        # Shared TS types
    └── use-job-stream.ts               # EventSource hook for SSE consumption
```

**SSE flow** (`apps/web/app/api/jobs/[id]/stream/route.ts`): authenticate, verify ownership via `user_term_jobs(user_id, job_id)`, **read `jobs` row from Postgres FIRST** — if status terminal, emit one event and close without subscribing. Otherwise subscribe to `results:{term_id}` (term-keyed channel — multiple users adding the same term share a single worker run), then re-check Postgres post-subscribe to close the publish-before-subscribe race window. Heartbeat every 15s, hard timeout at 5min, response headers include `x-accel-buffering: no` to defeat any upstream buffering.

---

## Service: `apps/pycil-core` (FastAPI)

Port 8000. Domain logic: nodes/terms CRUD, learning session orchestration, ELO math, job enqueue, rate limit + budget checks, onboarding seed.

```
apps/pycil-core/
├── alembic/versions/0001_init.py       # Initial schema (users, nodes, ..., user_term_jobs, jobs)
├── pycil_core/
│   ├── main.py                         # FastAPI app + router include + CSRF middleware
│   ├── config.py                       # Pydantic Settings (DATABASE_URL, REDIS_URL, ...)
│   ├── db.py                           # async engine + session
│   ├── auth.py                         # Auth.js cookie -> users row (WHERE expires > NOW())
│   ├── api/
│   │   ├── deps.py                     # get_current_user dep
│   │   └── routes/
│   │       ├── nodes.py                # /nodes CRUD + star/pin
│   │       ├── terms.py                # POST /decks/{id}/terms (fires generate_term)
│   │       ├── questions.py            # GET /definitions/{id}/question, POST /questions/{id}/check
│   │       ├── learning.py             # /decks/{id}/learn, /sessions/{id}/question|answer
│   │       └── onboarding.py           # POST /onboarding/seed (idempotent first-login seed)
│   ├── learning/
│   │   ├── elo.py                      # Pure ELO math (constants + 6 functions)
│   │   ├── elo_test.py                 # ONLY formal test suite in v1 (pytest)
│   │   ├── intervals.py                # Snap to predefined ladder (15min .. 2mo)
│   │   ├── mastery_levels.py           # 11-level ELO bucketing
│   │   └── term_selection.py           # due -> new -> upcoming priority
│   ├── middleware/
│   │   ├── csrf.py                     # Origin allowlist on mutating verbs
│   │   └── rate_limit.py               # Redis sliding-window per-user
│   ├── schemas/                        # Pydantic models per domain
│   └── services/
│       ├── node_service.py             # Folder/deck CRUD + breadcrumb (recursive CTE)
│       ├── term_service.py             # Add term to deck + enqueue generate_term
│       ├── question_service.py         # get_or_generate(definition_id, difficulty)
│       ├── learning_service.py         # Session orchestration (Redis state + per-session lock)
│       ├── job_service.py              # enqueue_generate_term + lock-or-get + budget/rate
│       └── onboarding_service.py       # Seed sample folder + deck (no LLM cost)
├── alembic.ini
└── Dockerfile
```

**Learning module** (`pycil_core/learning/elo.py`): pure functions, no I/O. Constants `K=32, D=400, ALPHA=0.5, F=2.0, S=200`, ELO clamped to `[0, 3000]`, `INITIAL_ELO=1000`, `INITIAL_INTERVAL_SECONDS=1800` (30min). Cold-start fix: `lapsed_seconds=None` returns `T=1.0` and `interval_old=0` floors at 30min so first review is non-zero. ELO unit tests in `elo_test.py` are the only formal tests in v1 (PDR §9 tradeoff).

**Session state** (`learning_service.py`): keyed at `learning_session:{session_id}` in Redis with 4h TTL. Every mutation acquires `SET session_lock:{session_id} {request_id} NX EX 5` and releases via Lua-checked DEL (multi-tab race protection — returns 409 `session_busy` on contention, client retries after 200ms). ELO/interval write hits Postgres only when a term is reviewed (Q=2 correct first-answers); per-question round work stays in Redis.

**Job service** (`job_service.py`): pre-flight checks (1) global daily budget cap via `GET openrouter:spend:daily` against `OPENROUTER_BUDGET_DAILY_USD`, (2) per-user 5/hr via `INCR rl:gen_term:{user_id}` with `EXPIRE 3600`. Then Lua-atomic lock-or-get on `lock:generate_term:{term_id}` (TTL 600s) — same-term concurrent enqueues collapse to one worker run. Always writes a per-user `user_term_jobs(user_id, term_id, job_id)` row so SSE ownership checks scale cross-user. On `arq.enqueue_job` failure, releases lock and marks `jobs.status='failed'` so the user sees an error instead of a 10-minute spinner.

**Onboarding** (`onboarding_service.py` + `routes/onboarding.py`): `POST /onboarding/seed` is idempotent — checks `user_nodes` count before seeding "Welcome" folder + "Starter Verbs" deck with 5 pre-enriched terms (no LLM cost). Web fires this once on first sign-in.

---

## Service: `apps/worker` (arq + LangChain)

Background LLM worker. arq consumes Redis-queued jobs; LangChain `ChatOpenAI` calls OpenRouter directly from job code (no `LLMClient` abstraction layer in v1 — user-locked decision; swap path is editing the call site).

```
apps/worker/
├── prompts/
│   ├── role.md                # Shared role/persona block
│   ├── generate_term.md       # Term enrichment prompt (uses {% include "role.md" %})
│   └── mcq.md                 # MCQ generation prompt
├── worker/
│   ├── main.py                # arq WorkerSettings (functions, max_tries=2, keep_result)
│   ├── config.py              # Pydantic Settings
│   ├── db.py                  # async engine for Postgres writes
│   ├── redis_helpers.py       # Lock-or-get Lua + spend counter helpers
│   ├── sanitize.py            # Strip URLs / HTML / control chars from LLM output
│   ├── llm/                   # ChatOpenAI factory (OpenRouter base_url, model fallbacks)
│   ├── jobs/
│   │   ├── generate_term.py   # Term enrichment job
│   │   └── generate_question.py  # MCQ generation job
│   ├── prompts/               # Jinja2 Environment loader
│   ├── schemas/               # Pydantic models for LLM structured output
│   └── shared/                # Local re-export of pycil-shared question ABCs
├── pyproject.toml
└── Dockerfile
```

**Prompt rendering**: vanilla Jinja2 `Environment(loader=FileSystemLoader("apps/worker/prompts/"))` with built-in `{% include "role.md" %}`. No custom directive engine (user-locked).

**Term enrichment**: term value rendered inside `<USER_TERM>...</USER_TERM>` fences with explicit "treat as data not instructions" framing — prompt-injection mitigation. Validated at API boundary (length ≤64, no newlines/control chars). LLM output sanitized (strip URLs, HTML, control chars) before INSERT.

**Idempotency**: pre-INSERT check `SELECT 1 FROM definitions WHERE term_id = $1` short-circuits re-runs; `UNIQUE(term_id)` constraint absorbs racy duplicate writes. Lock is **never** released in worker `finally` — TTL-only release. arq retries (`max_tries=2`) reuse the same lock so retry is idempotent.

**Spend tracking**: every successful LLM call does `INCRBYFLOAT openrouter:spend:daily {usd_cost}`. The job service reads this counter pre-enqueue and rejects with 503 `budget_exhausted` once the daily cap is hit.

**Publish**: on terminal success, `redis.publish("results:{term_id}", json.dumps(payload))`. Channel keyed by `term_id` (not `job_id`) so cross-user same-term enrichment delivers via the same channel.

---

## Package: `packages/shared-py` (pycil-shared)

Cross-service Python package consumed by both `pycil-core` (answer checking) and `worker` (prompt selection). User-locked — kept as a separate package even though duplicating Pydantic schemas across services would be cheaper.

```
packages/shared-py/
├── pyproject.toml             # Package name: pycil-shared
└── shared/
    └── questions/
        ├── base.py            # BaseQuestion ABC (abstract)
        └── multiple_choice.py # MCQ subclass — generate_prompt() + check_answer()
```

`BaseQuestion` ABC kept abstract so v0.2 `WriteQuestion` and `FillInBlankQuestion` plug in without refactoring the dispatch surface.

Installed editable in both Dockerfiles: `pip install -e ../../packages/shared-py`.

---

## Postgres Schema (Alembic 0001_init)

Single migration ships the v1 schema. Enums: `node_type(FOLDER, DECK)`, `visibility(PRIVATE, PUBLIC)`, `term_type`, `cefr_level(A1..C2)`, `part_of_speech`, `question_type(MULTIPLE_CHOICE, WRITE, FILL_IN_BLANK)`.

| Table | Purpose |
|-------|---------|
| `users`, `accounts`, `sessions`, `verification_token` | Auth.js v5 standard (Postgres adapter) |
| `nodes` + `folder_attributes` + `deck_attributes` | Hierarchical content (FOLDER / DECK only in v1) |
| `terms` | Canonical term value (unique) |
| `definitions` | One canonical sense per term — `UNIQUE(term_id)` enforced |
| `definition_paraphrases`, `term_example_sentences` | A2/B1/C1-tagged enrichment rows |
| `questions(type, definition_id, data jsonb)` | MCQ rows in v1 (Write/Fill enum kept for v0.2) |
| `user_term_stats` | Per-user ELO + mastery_level + next_review_date + interval_seconds |
| `user_nodes` | Star/pin per user |
| `deck_definitions(deck_id, definition_id, position)` | Deck membership junction |
| `jobs` | Async job tracking (status, payload, result, error) |
| `user_term_jobs(user_id, term_id, job_id)` | Per-user SSE ownership for cost-deduped jobs |

Auth.js session lookup is mandatory `WHERE expires > NOW()` so revoked / expired cookies cannot be reused.

---

## Redis Key Map

| Pattern | Owner | TTL | Purpose |
|---------|-------|-----|---------|
| `learning_session:{session_id}` | pycil-core | 4h | Session state JSON (round_queue, term_tracking, ELO start) |
| `session_lock:{session_id}` | pycil-core | 5s | Per-session mutation lock (multi-tab race protection) |
| `lock:generate_term:{term_id}` | pycil-core (set) / worker (TTL release) | 600s | Cost-dedup lock; never deleted by worker |
| `rl:gen_term:{user_id}` | pycil-core | 3600s | Per-user 5/hr rate limit counter |
| `openrouter:spend:daily` | worker (incr) / pycil-core (read) | rolling | Daily LLM USD spend counter |
| `results:{term_id}` (Pub/Sub channel) | worker -> web | n/a | Term-keyed enrichment publish (cross-user dedup) |
| arq queue + `arq:result:{job_id}` | arq | varies | Job queue + result store |

---

## Cross-Service Trust Boundaries

- **Web auth -> pycil-core**: cookie passthrough through Caddy; `pycil_core/auth.py` reads `__Secure-authjs.session-token` (prod) or `authjs.session-token` (dev), joins `sessions` + `users` with the mandatory `expires > NOW()` clause.
- **CSRF**: `apps/pycil-core/pycil_core/middleware/csrf.py` rejects POST/PATCH/PUT/DELETE when `Origin` header is missing or not in `ALLOWED_ORIGINS`. Auth.js cookie configured `SameSite=Strict`.
- **User input -> LLM**: term value validated at API boundary, fenced inside `<USER_TERM>` in the prompt, output sanitized before INSERT.

---

## Observability

Coherent strategy across the three pillars — what's wired, what's deferred:

- **Logs (active).** `shared/logging_config.py` `configure_logging()` installs one stdlib JSON formatter on the root logger; called once at startup by both `pycil_core/main.py` (lifespan) and `worker/main.py` (module load). Every call site already uses `logger.info(msg, extra={...})`; the formatter emits each non-reserved `LogRecord` attribute, so those `extra` fields actually reach stdout (the prior text formatter silently dropped them). Knobs: `LOG_LEVEL` (default INFO), `LOG_FORMAT=text` for a human-readable line locally (anything else → JSON). The handler is rebuilt each call, so uvicorn `--reload` / test re-entry never stacks duplicate handlers. Worker spend lines (`worker/observability/spend_metrics.py` `emit_spend`) and the best-effort ledger writer (`spend_ledger.py`) ride this same shape.
- **Traces (active, opt-in).** `pycil_core/observability/telemetry.py` `setup_telemetry()` wires an OTLP **trace** exporter + auto-instrumentation (FastAPI / SQLAlchemy / Redis / httpx). No-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, and skips cleanly if the OTEL SDK isn't installed. Traces only — no MeterProvider (the docstring previously overclaimed "metrics").
- **Errors (active, opt-in).** Sentry init in `pycil_core/main.py` lifespan, guarded by `SENTRY_DSN_CORE`; no-op + `ImportError`-safe when unset (`traces_sample_rate=0.1`, `send_default_pii=False`).
- **Product metrics (active).** `/admin-api/metrics` serves a DB-derived product snapshot; `/admin-api/health` reports DB / Redis / queue depth / worker-heartbeat age. These are the metrics surface in v1.
- **Deferred (post-v1).** A real MeterProvider + OTLP metric export, and the full Grafana / Loki / Tempo stack, are explicitly out of v1 scope. The OTLP trace export hook is the only external-collector integration wired.

---

## Where Things Live (Quick Reference)

| Concern | Path |
|---------|------|
| ELO math | `apps/pycil-core/pycil_core/learning/elo.py` |
| Mastery levels (11 buckets) | `apps/pycil-core/pycil_core/learning/mastery_levels.py` |
| Interval ladder | `apps/pycil-core/pycil_core/learning/intervals.py` |
| Term selection | `apps/pycil-core/pycil_core/learning/term_selection.py` |
| Session orchestration | `apps/pycil-core/pycil_core/services/learning_service.py` |
| SSE handler | `apps/web/app/api/jobs/[id]/stream/route.ts` |
| Onboarding seed | `apps/pycil-core/pycil_core/services/onboarding_service.py` |
| Term enrichment job | `apps/worker/worker/jobs/generate_term.py` |
| MCQ generation | `apps/worker/worker/jobs/generate_question.py` + `apps/worker/prompts/mcq.md` |
| Question dispatch | `apps/web/components/question-renderer.tsx` |
| Shared question ABC | `packages/shared-py/shared/questions/base.py` |
| Initial schema | `apps/pycil-core/alembic/versions/0001_init.py` |

---

## Data-access convention (post raw-SQL→SQLModel conversion)

`pycil-core` services and `worker` jobs persist via SQLModel models in
`packages/shared-py/shared/db/` (43 `table=True` models + PG enums). Query
convention and the one hard rule learned from the 2026-05-29 audit:

- **Import `select` from `sqlmodel`, NOT `sqlalchemy`, whenever the result is
  fed to `session.exec()`.** SQLModel's `AsyncSession.exec()` auto-scalarizes a
  single-column `sqlmodel.select(Model.col)` to the bare value; a
  `sqlalchemy.select(Model.col)` returns a `Row` (e.g. `('x',)`), silently
  breaking any scalar comparison/consumption. Multi-column selects return a
  `Row` with attribute access either way. The mechanical conversion's main
  defect was importing `select` from `sqlalchemy`; fixed at every
  scalar-consumed site.
- Shape rules (proven on live PG): `select(Model).first()` → model instance;
  `sqlmodel.select(Model.col).first()` → scalar; `select(a, b).first()` → `Row`
  (use `row.a` / `row._mapping`). Use `.first()` (returns `None` on 0 rows), not
  `.one()`, where the original SQL tolerated an empty result.
- Raw `session.execute(text(...))` holdouts remain for JSONB `jsonb_set` updates
  and a few aggregates. When binding a param adjacent to a Postgres cast, use
  `CAST(:param AS type)` — `text()` ignores `:param` immediately before `::`.
- `alembic/env.py` is wired to `SQLModel.metadata`, so `--autogenerate` works.
  Model–schema parity is asserted by `tests/service/test_model_schema_parity.py`.

## v1 Scope Reminders (User-Locked)

- LangChain `ChatOpenAI` called directly — no `LLMClient` abstraction layer.
- Vanilla Jinja2 prompts — no custom directive engine.
- 11 mastery levels (canonical mapping in `mastery_levels.py`).
- MCQ-only question type — Write/Fill deferred to v0.2.
- `apps/shared-py` (package `pycil-shared`) keeps `BaseQuestion` ABC for v0.2 plug-in.
- Sentry / backups / formal test suite deferred to post-launch (only ELO unit tests in v1).

---

## v1 Frontend Scope (Phase 8 — Dead Links + Profile)

**Hidden / placeholder features in v1.** The new FE (migrated from `openlet-web-legacy`) ships with a deliberately reduced surface vs. the legacy app:

- Sidebar: only Home (`/`) + Profile (via avatar `/profile`) + Settings (via avatar `/settings`). Removed: `/classes`, `/saved`, `/trash`, `/decks/new`, `/decks/[id]/edit`, `/decks/[id]/chat`, `/decks/[id]/test`, "Get Started 7/10" widget, `MAIN_MENU_ITEMS`, `SECONDARY_MENU_ITEMS`.
- Hosted on **Vercel** (separate platform from the VPS docker stack). The repo no longer ships a `web` Dockerfile or compose service.
- Header: search box (UI-only, returns "No results" — search backend deferred), `NotificationDropdown`, `UserDropdown`. Removed: "Create" button, "Rewards" gift button, command-palette deck/action shortcuts.
- File browser: `CreateShortcutDialog` deleted (file-level removal). "New" button on toolbar wires only Folder + Deck creation via `useCreateNode`.
- Verified (2026-05-29 audit): `study-modes.tsx` had shipped live `/decks/[id]/chat` + `/decks/[id]/test` links despite those routes being cut — now reduced to Flashcard + Learn. `grep -rE "/classes|/saved|/trash|/decks/new|/decks/\[id\]/(edit|chat|test)"` over live `<Link>`/router targets in `apps/web/src` → 0 hits (the remaining `/test/` strings are the Test-mode API paths in the unrouted `test-runner.tsx`).

**Profile gamification gap.** Legacy profile rendered streaks, XP, level, badges, league rank — none of these fields exist on the v1 BE `users` table. `/profile` shows: avatar, name, email, "Stats coming soon" badge, "Edit profile" dialog (PATCH `/me` — name only). Gamification deferred post-MVP.

**Settings page.** Two cards only: appearance (mode + color theme + font via `next-themes` + custom theme provider) and account (email display + sign-out button that runs `qc.clear()` before `signOut({ callbackUrl: "/sign-in" })` to prevent 401 cache leak).

---

## E2E Tests (Playwright)

`apps/web/e2e/` — 6 browser-level specs covering critical user paths:

| # | Spec | Description |
|---|------|-------------|
| 01 | auth-flow | Sign-in page renders; auth user redirected to dashboard |
| 02 | create-deck-and-term | Pre-seeded deck loads; terms page shows "ephemeral" |
| 03 | learn-session | Learn mode loads with pre-seeded enriched terms |
| 04 | flashcard-mode | Flashcard mode loads with pre-seeded enriched terms |
| 05 | explore-page | Explore public decks page loads for auth user |
| 06 | sign-out | Log out clears session → redirects to sign-in |

**Fixtures** (`e2e/fixtures/`):
- `auth.ts` — JWT cookie injection via `jose` (bypasses Google OAuth entirely)
- `db-seed.ts` — idempotent psql seed (test user + pre-enriched "E2E Starter Deck" with term `ephemeral`)
- `docker-stack.ts` — docker compose health-check waiter

**Page objects** (`e2e/pages/`): sign-in, dashboard, deck, learn, flashcard, explore.

**LLM cost avoidance** — tests never call OpenRouter:
- `WORKER_LLM_STUB=true` → `invoke_with_fallback` returns canned responses from `apps/worker/tests/fixtures/llm_responses.json`
- `LLM_STUB_MODE=true` → `stream_chat` yields canned chat response
- Pre-seeded data: `ephemeral` term is fully enriched in DB seed

**CI:** `.github/workflows/test.yml` `e2e` job spins up Postgres + Redis, runs migrations, builds Next.js, executes `pnpm e2e`, uploads `playwright-report/` on failure.

**Config:** `apps/web/playwright.config.ts` — Chromium only, `webServer` boots `next dev` on port 3000.

---

## LLM Stub Mode

Two env vars prevent real LLM calls in CI/tests:

| Var | Service | Behavior |
|-----|---------|----------|
| `WORKER_LLM_STUB=true` | worker | `invoke_with_fallback` returns canned JSON from `apps/worker/tests/fixtures/llm_responses.json` keyed by schema class name |
| `LLM_STUB_MODE=true` | pycil-core | `stream_chat` yields canned chat response without calling OpenRouter |

Both are set in the CI e2e job and can be used for local dev/test runs to avoid LLM costs.

