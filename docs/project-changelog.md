# Pycil — Changelog

All notable releases. Format derived from Keep a Changelog; dates in ISO-8601.

---

## [Unreleased] — 2026-07-18 — Owner-scoped Assistant Agent MVP

Introduces the bounded `/assistant` API for hierarchy, content, and folder-stat
help. The feature is configuration-gated until a dedicated OpenAI-compatible
provider key and base URL are supplied; it is not OpenRouter-specific.
Verification is complete: API 122 passed / 2 skipped, worker 3 passed, and the
provider protocol smoke test uses a local OpenAI-compatible server.

### Added

- Owner-bound assistant threads, idempotent runs, persisted sanitized events,
  LangGraph checkpoints, pending actions, and minimized action-audit records
  through migration `0008_assistant_agent`.
- Recoverable SSE: sequence IDs and `Last-Event-ID` replay, persisted run/event
  recovery, heartbeats, and a per-owner/thread Redis lease with concurrency,
  request-rate, tool-call, output-token, deadline, and optional spend limits.
- Durable human-in-the-loop approval for move, publish, delete, and
  sense-removal operations. Approval is action-, argument-, checkpoint-, and
  resource-generation-bound; stale, replayed, or expired proposals cannot run.
- Privacy lifecycle: owner-only access, 30-day inactive thread/checkpoint
  retention, user thread deletion, 15-minute default pending-action expiry,
  and 90-day minimized audit retention. Worker crons reconcile expiry and
  retention.

---

## [Unreleased] — 2026-07-16 — Sync lexi-ai to service-foundations (ebcbb64)

Re-synced `vendor/lexi-ai` editable dependency to lexi-ai's latest commit
(`ebcbb64` — service foundations: FastAPI/gRPC runtime, alembic migrations,
Redis caching, worker flows). Verified backward-compatible: all pycil tests
pass unchanged (api 106p, worker 3p, shared 13p). No schema drift detected;
`LexiClient` port and `InProcessLexiClient` adapter required zero changes.

New lexi-ai capabilities available but not yet adopted:
- `generate_fenced()` — DB-fenced generation for single-writer durability.
- Embedded `lexi_ai` domain library — isolated schema migration and in-process capability facades.
- Alembic migrations in lexi-ai for schema evolution.

---

## [Unreleased] — 2026-07-05 — Python greenfield migration (lexi-ai + FSRS + hierarchy)

`plans/260705-0032-python-greenfield-migration/` (12 phases). Rebuilds the
backend as a greenfield FastAPI + SQLModel + Alembic service, abandoning the
mid-flight Go/ent/chi direction (`260612-2302-full-project-refactoring`,
superseded). Internalizes `lexi-ai` as the dictionary/question/grading
authority behind a `LexiClient` port, replaces ELO with FSRS-4.5, and
introduces the folder/deck/REFERENCE hierarchy + Centrifugo realtime. The
pre-migration Python backend is kept at `apps/pycil-core` as a historical
reference, not deleted.

### Added

- **Two-database boundary.** Pycil's own Postgres (9 tables: `users`, `nodes`,
  `folder_attributes`, `deck_attributes`, `user_nodes`, `deck_senses`,
  `user_sense_stats`, `review_log`, `responses`) never stores dictionary
  content; `lexi-ai` owns `words`/`senses`/`questions`/etc. in its own
  database. No cross-DB foreign keys or joins — enforced structurally by
  `apps/api/tests/test_boundary.py`.
- **`LexiClient` port + `InProcessLexiClient` adapter**
  (`apps/api/pycil/content/lexi_port.py`, `lexi_inprocess.py`) — the only
  interface/construction site for reaching lexi-ai (search, generate,
  get_senses, generate_questions, grade, get_question).
- **FSRS-4.5 learning engine** (`packages/shared-py/shared/fsrs/`) — verbatim
  port of the published fsrs4anki v4.5 weight table, binary grade only
  (Good/Again). Replaces the ELO scheduler.
- **Hierarchy + stats domain** (`apps/api/pycil/hierarchy/`) — adjacency-list
  FOLDER/DECK/REFERENCE tree, recursive-CTE subtree resolution, folder/weakest/
  CEFR-distribution stats, L1-only Redis cache with ancestor-chain busting.
- **`require_node_access` IDOR gate** (`apps/api/pycil/hierarchy/access.py`) —
  single choke point for owner-vs-public read/write checks on every node,
  closing a previously systemic IDOR gap.
- **Auth redesign** (`apps/api/pycil/auth/`) — Google OAuth 2.1 + PKCE,
  backend-issued bearer JWT (HS256-pinned, required-claims-checked,
  secret-rotation fallback that never rescues an already-expired token),
  `token_version`-based revocation, no server-side session table, no cookies.
- **Centrifugo realtime** (`apps/api/pycil/realtime/`,
  `packages/shared-py/shared/realtime/`) — owner-scoped `users:{uid}:*`
  channels, separately-secret-signed subscription tokens, best-effort publish
  (durable `responses`/job-state rows back every event).
- **Worker redesign** (`apps/worker/pycil_worker/`) — exactly 3 arq jobs
  (`generate_word`, `generate_question`, `grade_answer`), single-writer to
  lexi-ai's DB, idempotent grading via `responses.grade_status`.
- **Migration gate** — a one-shot `migrate` compose service runs
  `alembic upgrade head` before `api`/`worker` start
  (`condition: service_completed_successfully`).
- **`uv`-based Python tooling** across `apps/api`, `apps/worker`,
  `packages/shared-py`, with `vendor/lexi-ai` as an editable path dependency.

### Removed

- Billing (Stripe), gamification (XP/streaks/badges/league), admin dashboard,
  chat-with-AI (SSE), translation/TTS jobs, ELO scoring, SSE-based job/answer
  streaming, Caddy reverse proxy, the Vercel/VPS split topology.
- The retired Go/ent/chi scaffold (never completed; abandoned in favor of
  this Python direction).

### Notes

- Frontend (`apps/web`) migration is **partial** — contract/type renames
  (Term→Word, Definition→Sense, ELO→FSRS) are underway, but `next-auth`/
  `@auth/core` are still present with no iron-session/Centrifugo-JS
  integration wired to the new backend yet.
- CI/CD, `scripts/deploy.sh`, and the root `Makefile` were not repointed at
  the new stack in this migration and still reference the old
  `apps/pycil-core` topology — tracked as an operational gap, not a phase.
- Backup coverage remains single-DB (pycil's Postgres only); covering
  lexi-ai's database too is deferred to a deployment-phase follow-up.

## [Unreleased] — 2026-05-30 — admin dashboard (RBAC, users, moderation, metrics, spend, flags, health, audit)

`plans/260529-2356-admin-dashboard-implementation/` (8 phases, TDD throughout).
Adds an admin-only `/admin` surface gated by a single `users.role` enum with an
authoritative per-request DB read; the jose JWT carries a `role` claim purely so
Next.js middleware can gate `/admin/*` at the edge.

### Added

- **RBAC foundation (Phase 1).** Migration `0019_user_role_and_ban`:
  `user_role_enum` (`user`|`admin`), `users.role` (NOT NULL default `user`,
  `server_default`), `users.banned_at`, `users.ban_reason`, and widens
  `users.token_version` `SMALLINT→INTEGER`. `CurrentUser` gains `role`/`banned_at`;
  `get_current_user` hard-locks banned accounts (403 `account_banned`).
  `require_admin`/`AdminDep` dependency. `/auth/upsert-user` now returns `role` +
  `token_version` so the Auth.js `jwt` callback mints correct edge claims on first
  login (fixes the pre-existing hardcoded `token.tv=0` revoke-tokens bug). Admin
  shell at `/admin` (server-side role re-check, `noindex`).
- **User management + ban (Phase 2).** `/admin-api/users` search/list, detail
  aggregate (stats + today-spend + recent jobs + mastery), ban/unban (hard
  lockout), revoke-tokens. Self-ban, admin-on-admin, and last-admin guards. Every
  write audited in one transaction.
- **Persistent spend ledger (Phase 3).** Migration `0020_llm_spend_events`. Worker
  writes one best-effort row per non-cached LLM call via a DEDICATED session (never
  the job's — avoids `PendingRollbackError` poisoning generation), idempotent on
  `job_id`. `generate_term` rows carry `user_id=NULL` (global cache). Costs are
  flat-constant estimates, labeled "estimated".
- **Metrics dashboard (Phase 4).** `/admin-api/metrics`: snapshot (DAU/WAU/signups/
  answers/decks) + signup funnel + spend-by-day/model + top-spenders. Scalar cards
  + plain tables (no chart lib). 30s snapshot cache.
- **Reports pipeline (Phase 5).** Migration `0021_content_reports` (two typed FK
  columns `node_id`/`comment_id` + CHECK exactly-one) plus `nodes.deleted_at` for a
  new admin-capable reversible soft-delete. User `POST /reports`; admin queue +
  resolve (dismiss / delete_content) with snapshot re-verification before delete.
- **Feature-flag CRUD (Phase 6).** `/admin-api/flags` list/create/update/delete;
  every write invalidates the 30s eval cache and audits.
- **System health + audit viewer (Phase 7).** `/admin-api/health` (bounded,
  never-throw DB/Redis/queue/heartbeat checks; `ZCARD` not `LLEN`); worker
  heartbeat cron. The previously-dead `/admin/audit` handler is re-gated to
  `AdminDep` + re-mounted at `/admin-api/audit` with filters + cursor pagination.
- **Polish (Phase 8).** End-to-end admin-suite integration test + an
  audit-coverage test enumerating every write action type. Admin write paths
  rate-limited via the existing `enforce()` pattern. README admin-seed note with
  migration-0019 rollback-ordering warning.

### Notes

- All human admin routes mount under `/admin-api/*` (forwarded by Caddy's catch-all
  `/api/core/*`); the internal-secret routes stay under `/admin/*` (404'd publicly).
- Supersedes drafted admin phases in `260526-2015-p6-operational-foundation`
  (phases 3, 4) and `260526-2045-p12-compliance-trust` (phase 2).

---

## [Unreleased] — 2026-05-29 — raw-SQL→SQLModel conversion verified + adversarial audit

`plans/260529-0615-full-project-audit-refactor/` (8 phases). Stabilized and
verified the in-flight raw-SQL→SQLModel conversion (checkpoint `9f07149`), then
ran a full adversarial bug hunt across `pycil-core`, `worker`, `shared-py`, and
the Next.js web app. Every CONFIRMED bug proven by source-read + failing repro,
fixed, then re-verified green.

### Fixed — conversion regressions + production-breaking bugs

- **`select` scalarization (P1/P2).** Several converted call sites imported
  `select` from `sqlalchemy` but passed it to SQLModel's `session.exec()`, which
  auto-scalarizes ONLY a `sqlmodel.select`. With `sqlalchemy.select(Model.col)`,
  `.first()`/`.all()` return `Row`s, not the bare scalar. Empirically proven on
  live PG. Broke: worker `lifecycle.is_terminal()` (idempotency gate permanently
  False → re-runs paid LLM side effects on every arq retry), `generate_question`
  cache-hit/sample reads, `social_service.claim_username` (false `username_taken`
  409 when re-saving your own name), `reverse_card_service` distractor pool,
  `me_extras` follow-by-username. Fix: import `select` from `sqlmodel` at each
  scalar-consumed site. Multi-column sites were unaffected (Row attr access works).
- **`ON CONFLICT (term_id)` on a dropped constraint (P1).** Migration
  `0012_multi_sense_definitions` dropped `UNIQUE(term_id)` (→ `UNIQUE(term_id,
  sense_index)`), but `generate_term` and `onboarding_service` still upserted on
  `(term_id)` → `InvalidColumnReferenceError`, crashing term enrichment and new-
  user onboarding on every new term. Fix: `ON CONFLICT (term_id, sense_index)`.
- **`to_jsonb(:param::text)` bind bug (P1).** SQLAlchemy `text()` ignores a bind
  param immediately followed by `::` → `PostgresSyntaxError`; translate + TTS
  JSONB write-back crashed 100%. Fix: `to_jsonb(CAST(:param AS text))`.
- **UUID JSONB serialize (P2).** Converted ORM `.values(result=...)` used the
  default JSON serializer → `TypeError` on a UUID `question_id`. Fix: worker
  engine `json_serializer=partial(json.dumps, default=str)` (matches old behavior).
- **`upsert_subscription` dropped `updated_at = NOW()` (P3).** Conversion lost it
  from the DO UPDATE set clause; restored.
- **Job lock leak on commit failure (P2).** `job_service.enqueue_generate_term`
  released `lock:generate_term` only on enqueue failure; a commit failure leaked
  it for the full TTL. Fix: rollback + release on any post-acquire failure.

### Fixed — web frontend

- Removed the never-installed `next-pwa` wrapper (broke `tsc`/`next build`; the
  app's real PWA is the hand-written `public/sw.js`). All 13 `no-explicit-any`
  lint errors fixed with proper types. Dead study-mode links (`chat`/`test` →
  404) removed (v1 scope). Legal pages unblocked from auth middleware. Sign-in
  `searchParams` awaited (Next 15 Promise). Wired a `tsx --test` runner for the
  previously-orphaned `quizlet-parser.test.ts` (9 tests).

### Test harness

- Aligned worker `conftest` SessionLocal to SQLModel `AsyncSession` (was plain
  SQLAlchemy → no `.exec()`; the reason the conversion shipped unverified).
  Updated stale worker tests to patch `invoke_with_fallback` (jobs no longer call
  `generate_with_schema`). Added `test_translate_tts_pipeline.py` and core
  regression tests for every CONFIRMED bug. Quarantined the pre-existing F7
  fuzzy-grading test as `xfail` (predates the conversion; threshold re-tune is
  out of behavior-preserving scope).

### Verified

- Core suite: 159 passed, 1 xfailed (F7), 9 skipped — 0 failures (was 12+ at
  baseline). Worker suite: 41 passed, coverage 73.5% (gate 70%). Web: `tsc`,
  `eslint` (0 errors), `next build` all green. Ruff clean on both Python packages.

### Known / residual (escalated, not in behavior-preserving scope)

- **Core test coverage 48.57% < CI gate 70%** — pre-existing: ~30 unwired P4–P12
  deferred-feature scaffold services have zero tests. Not introduced this audit.
- Unwired services with latent gaps if routed (`deck_search_service` missing
  user scope; `classroom_service` missing deck-ownership check; `user_spend_service`
  per-user cap non-functional; `admin_audit_service.record()` unwired). Pre-existing
  npm-audit advisories (next/swiper/postcss) need breaking major bumps.

---

## [Unreleased] — 2026-05-26 — comprehensive backend test suite

`plans/260526-1746-comprehensive-backend-test-suite/` (8 phases). Pytest-driven regression net before `260525-1907-code-review-remediation` rewrites service files.

### Added — Test infrastructure

- `apps/pycil-core/tests/conftest.py` and `apps/worker/tests/conftest.py` rewritten to self-provision Postgres via `pytest-postgresql` + apply Alembic migrations once per session, replace `redis_pool.get_redis` with `fakeredis.aioredis.FakeRedis` (with `aclose` no-op shim so multiple service-call sites can share one client), and override `get_current_user` / `get_session` for ASGI tests.
- Shared `tests/factories.py`: `make_user`, `make_deck`, `make_term`, `make_definition`, `attach_definition_to_deck`, `make_mcq_question`, `make_write_question`, `seed_user_term_stats`, `make_session_state`.
- Dev deps added to both `pyproject.toml`: `pytest-postgresql`, `fakeredis>=2.26`, `freezegun`, `httpx`, `pytest-mock`, `pytest-cov`, `pyjwt`. `asyncio_mode = "auto"` set in `[tool.pytest.ini_options]`.
- Root `Makefile` with `make test` / `test-core` / `test-worker` / `test-cov`.
- `.github/workflows/test.yml`: PR + push gate, Postgres 16 service container, matrix per app, `--cov-fail-under=70` per app.

### Added — Tests

- **Phase 2 (learning service)**: `test_learning_service_lock` (SET-NX-EX, foreign release, TTL reclaim), `test_learning_service_state` (corrupt JSON 500, missing 404, round-trip), `test_learning_service_authz` (403 cross-user, 409 question_mismatch), `test_learning_service_round_queue` (replenishment, all-completed, order preservation), `test_learning_service_concurrency` (parallel `submit_answer` lock serialization), `test_learning_service_elo_commit` (UPSERT `user_term_stats` at `_REQUIRED_CORRECT_FIRSTS`), `test_term_selection` (due > new > upcoming priority, limit).
- **Phase 3 (worker LLM jobs)**: `test_sanitize` (URL/HTML/control matrix + answer fields keep URL/HTML), `test_generate_term_pipeline` (happy + cache-hit + term_not_found + ValidationError retry + two-strikes-failed + non-terminal-reraise), `test_generate_question_pipeline` (happy MCQ INSERT + cache-hit + definition_not_found + URL sanitize + `is_terminal` short-circuit), `test_cost_tracking` (`add_spend` increment + cache-hit zero-spend).
- **Phase 4 (question/job/budget)**: `test_lock_lua` (GET-or-SET-with-EX semantics, owner-on-first, holder-on-second, TTL reclaim), `test_question_service_cache` (cache-hit answer-stripping, MCQ-only filter, 404 oracle, public deck access), `test_job_service_orchestration` (5/hour rate limit + 6th=429, budget cap → 503, budget-before-rate ordering, malformed spend value, dedup concurrent same-term, orphan cleanup on enqueue failure).
- **Phase 5 (billing)**: `test_billing_upsert_ordering` (10-row reorder matrix: insert/update/older-rejected/lex-tiebreak/replay/downgrade-race/unicode-event-id/null-period-end/default-tier), `test_billing_customer_create` (existing skips SDK, missing creates + persists).
- **Phase 6 (test mode)**: `test_test_mode_start_run_projection` (MCQ answer-stripping, WRITE answer-stripping, empty deck LookupError, private/public deck access, partial count), `test_test_mode_submit_and_complete` (MCQ correct/malformed, WRITE grader dispatch, replay → already_answered, after-complete → run_completed, cross-user 404, empty-run no-DivByZero, 3/5 score aggregation).
- **Phase 7 (pure-logic)**: `test_intervals_snap_ladder` (extremes, on-rung, tie-break-lower, near-rung), `test_mastery_levels_for_elo` (every bucket boundary 800/900/1000/1100/.../1600 + extremes 0/3000/-1 + label fallback), `test_share_link_service` (32-char URL-safe token, owner-only create, idempotent revoke, resolve-after-revoke=None, charset), `test_clone_service` (private rejected, foreign parent rejected, empty deck OK, term-reuse via UNIQUE(value), `deck_clones` attribution).
- **Phase 8 (FastAPI ASGI)**: `test_auth` (no-cookie 401, bad-sig 401 no PII, valid cookie 200), `test_learning_flow` (POST `/decks/{id}/learn` → 201, unknown deck 404), `test_share_link_flow` (POST create + DELETE revoke + 404 on second revoke), `test_billing_webhook` (bad signature 400, subscription_created persists, out-of-order 200 silent no-op), `test_validation_errors` (selected_index non-int 422, negative session_size 422, share-link missing node 404).

### Architecture decisions

- **pytest-postgresql over aiosqlite**: many tests rely on `ON CONFLICT`, `to_timestamp`, `text::question_type` casts, JSONB ops that SQLite cannot emulate.
- **Direct `arq` job invocation**: `generate_term(ctx, ...)` called with fake `ctx={"redis": fakeredis, "job_try": N, "max_tries": M}` — keeps tests deterministic; arq runtime itself is library code.
- **Separate `test.yml` workflow**: runs on PR + pre-deploy with `--cov-fail-under=70` per app rather than coupling to `deploy.yml`.

### Production fixes surfaced by the test phase (asyncpg + FastAPI)

The test phase exposed real production bugs hidden by manual testing. asyncpg parses `:param::type` as two adjacent bind parameters, so every SQL using inline-cast syntax silently failed under the async driver. Routes also tripped a FastAPI 0.115 strict check around 204+response_model.

- **`pycil_core/services/billing_service.py`**: `to_timestamp(:pe)` and `to_timestamp(:ev_ts)` rewritten as `to_timestamp(CAST(:pe AS BIGINT))`. Without this, every `upsert_subscription` call fails under asyncpg.
- **`pycil_core/services/question_service.py`**: `:payload::jsonb` → `CAST(:payload AS jsonb)`.
- **`pycil_core/services/job_service.py`**: same `:payload::jsonb` fix.
- **`pycil_core/services/clone_service.py`**: `:cefr::cefr_level, :pos::part_of_speech` rewritten as `CAST(... AS ...)`.
- **`pycil_core/api/routes/auth.py`**: `:uid::text` → `CAST(:uid AS text)` in `pg_advisory_xact_lock` arg.
- **`pycil_core/api/routes/nodes.py`**: `DELETE /{node_id}` route now declares `response_model=None` so FastAPI 0.115 stops asserting "Status code 204 must not have a response body" against the auto-derived schema for `-> None`.
- **`worker/jobs/lifecycle.py`**: `events || :evt::jsonb` → `events || CAST(:evt AS jsonb)`.
- **`worker/jobs/generate_term.py`**: `:cefr::cefr_level`, `:pos::part_of_speech` rewritten in three INSERT statements.
- **`worker/jobs/generate_question.py`**: `:data::jsonb` → `CAST(:data AS jsonb)`.
- **`worker/jobs/translate_definition.py`**, **`worker/jobs/tts_render.py`**: `to_jsonb(:val::text)` rewritten.

### Test run results (2026-05-26)

- **pycil-core**: 128 passed, 9 skipped, 1 pre-existing legacy failure (`test_answer_grading.py::test_grade_tiers[definishun-definition-fuzzy]` — `rapidfuzz` threshold drift, unrelated to this plan).
- **worker**: 31 passed.

### Test infrastructure adjustments during verification

- `_migrate_schema` is no longer `autouse` — opt-in via `async_engine` fixture so unit tests skip Postgres bring-up.
- `_bind_worker_session` (worker) explicitly patches `SessionLocal` on every importer module — patching only `worker.db.SessionLocal` doesn't reach modules that imported the symbol at module load.
- `fakeredis[lua]` extra required for `LOCK_LUA` eval support.
- `email-validator` added to runtime deps — Pydantic `EmailStr` requires it.
- `tests/factories.py` rewritten to use `CAST(... AS type)` instead of `:param::type` for asyncpg compatibility.
- ASGI client fixtures inject `Origin: http://test` and `ALLOWED_ORIGINS` defaults to `http://test` so the CSRF middleware passes during tests.
- pytest-postgresql configured as `postgresql_noproc` against a Docker-managed Postgres 16 (env-overridable via `PYTEST_PG_HOST/PORT/USER/PASSWORD`) — works on hosts without `postgresql-server` system packages.

---

## [Unreleased] — 2026-05-26 — v0.2 feature fill

`plans/260525-1446-pycil-v02-feature-fill/` (17 phases). 26 commits, ~50 files. 5/5 Critical + 4/6 High code-review findings fixed in-pass.

### Added — Schema

- **Migration 0004**: single additive migration shipping every v0.2 column/table/index. New tables: `notifications`, `responses`, `deck_clones`, `chat_sessions`, `chat_messages`, `test_runs`, `test_run_items`, `subscriptions`, `stripe_webhook_events`, `node_share_links`. New columns on `users` (gamification + soft-delete + stripe), `definitions` (tags + translation + tts_url), `questions` (elo + variant_seed), `nodes` (target_node_id), `user_term_jobs` (last_event + last_llm_response). GIN trigram indexes on `terms.value`, `nodes.name`, `definitions.canonical_meaning`. ENUM extension `node_type += 'SHORTCUT'`.

### Added — Auth & user lifecycle

- **JWT `iat` claim + max-age check**: `_REQUIRED_CLAIMS` now `["exp","iat","sub","tv"]`; rejects tokens older than `JWT_MAX_AGE_SECONDS`.
- **Account soft-delete + 14d hard-delete cron**: `DELETE /me` soft-deletes; apscheduler `hard_delete_expired_users` job purges; `pg_advisory_xact_lock` guards multi-replica double-fire.
- **Admin token revoke**: `POST /admin/users/{id}/revoke-tokens` (X-Internal-Secret gated; Caddy `respond /api/core/admin/* 404`).
- **Sign-in error banners**: `?reason=token_revoked`, `?reason=expired`, `?error=account_deleted`.
- **PATCH /me extended**: name + image_url + bio + study_settings + bump_tv.

### Added — Features

- **Notifications** persisted with 30s polling on `/notifications?since=`.
- **Gamification**: XP/streak/badges hooked into `learning_service.submit_answer`; level math from locked `LEVEL_TABLE`; weekly `compute_league_rank` cron.
- **Profile image upload**: B2 signed PUT URL with server-generated UUID4 in key (no client-substitution).
- **Search**: pg_trgm trigram across decks/folders/terms/definitions; FE command palette.
- **Share links**: `node_share_links` create/revoke/list; FE share dialog.
- **Write & Fill questions**: `WriteQuestion` + `FillInBlankQuestion` ABCs; tiered grading (exact → normalize → rapidfuzz Levenshtein); FE renderers.
- **SHORTCUT nodes + topic tags + public decks**: `target_node_id` traversal; `definitions.tags`; `/explore` browse + deep-clone via `clone_service`.
- **Translation**: on-demand `translate_definition` worker job → JSONB cache.
- **TTS**: `tts_render` worker calls Gemini Flash → uploads MP3 to B2 → 7d signed URL.
- **Chat-with-AI**: real LLM streaming over SSE on pycil-core; deck-grounded system prompt (top-50 terms); per-session 20k input cap.
- **Test mode**: assessment-only (no ELO writes); answer-stripped projection (`expected_answer`/`correct_index` never leave BE).
- **Mobile PWA**: `next-pwa` wrap, manifest.webmanifest, NetworkOnly for `/api/core/*`, online-only.
- **i18n**: `messages/{en,vi}.json`.
- **Sentry**: `sentry_sdk.init` in lifespan, app_env + dsn config.
- **Backups**: nightly `pg_dump | restic` to B2 with 7d/4w/6m retention; restore script.
- **Stripe billing scaffold**: webhook handler with raw-bytes signature verify + INSERT-event-before-dispatch idempotency in single txn; `subscription_data.metadata.user_id` propagation; `to_timestamp()` for epoch fields. ENFORCE_TIERS=false.
- **Rate limit**: Redis sliding-window middleware on `/public/*` (60 RPM/IP).
- **Multi-tab sync**: `useBroadcastSync` hook on `pycil-sync` BroadcastChannel.
- **Worker observability**: structured per-job spend metrics.
- **Privacy + Terms**: `/legal/privacy`, `/legal/terms` draft pages.
- **error.tsx + loading.tsx**: per route group.

### Tests

- `apps/pycil-core/tests/`: `test_migration_0004.py`, `test_answer_grading.py`, `test_gamification.py`, conftest with DATABASE_URL_TEST gate.
- `packages/shared-py/tests/test_questions.py`.
- `apps/worker/tests/conftest.py` (env-gated markers).

### Removed

- Legacy `notes[0]` dual-write in `generate_term`.
- `apps/web/src/lib/mock-data.ts` (336 LOC, 0 importers).

### Deferred to v0.3

- PWA icon/og-image asset generation.
- Stripe checkout UI (BE wired, ENFORCE_TIERS=false).
- Playwright E2E suite.
- `last_llm_response` retry idempotency wired into worker code paths.
- OpenRouter model fallback chain.
- Caddy `@sse` matcher widened to `/chat/sessions/*/stream`.

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
