# Pycil — System Architecture

**Last sync:** 2026-05-30 (post Phase 5 Playwright E2E suite)
**Source design:** `docs/project-overview-pdr.md` (locked)
**Implementation map:** `docs/codebase-summary.md`

## v0.2 surface (added since v1)

- Auth: JWT `iat` + `JWT_MAX_AGE_SECONDS`; account soft-delete + 14d hard-delete cron under `pg_advisory_xact_lock`; admin token-revoke gated by `X-Internal-Secret`.
- Notifications persisted in `notifications` table; FE polls `/notifications?since=` every 30s.
- Gamification (`xp_total`, `streak_days`, `level`, `badges`, `league_rank`) hooked into `learning_service.submit_answer` via `gamification_service`.
- Profile image upload: `POST /me/image-upload-url` returns B2 presigned PUT URL with server-generated UUID4 in key.
- Search: pg_trgm GIN indexes; `GET /search` returns grouped nodes/terms/definitions.
- Share links: `node_share_links` table; create/revoke/list endpoints.
- Write/Fill questions: `WriteQuestion` + `FillInBlankQuestion` ABCs in shared-py; `answer_grading_service` tier ladder (exact → normalize → rapidfuzz → LLM).
- SHORTCUT nodes via `nodes.target_node_id`; topic tags via `definitions.tags`; public decks via `nodes.visibility = 'PUBLIC'`; deep-clone via `clone_service`.
- Translation + TTS: on-demand worker jobs cache results in `definitions.translation`/`definitions.tts_url` JSONB. TTS uploads MP3 to S3-compatible storage (MinIO local, any S3 provider in prod) with a signed URL. (Kept in v1 — originally listed out-of-scope; reconciled in rehab.)
- Chat-with-AI: `chat_sessions` + `chat_messages`; `GET /chat/sessions/{id}/stream` is SSE from pycil-core via httpx OpenRouter streaming.
- Test mode: `test_runs` + `test_run_items`; `_to_client_payload` strips `expected_answer`/`alt_answers`/`correct_index` before sending to FE.
- Mobile PWA: `next-pwa` wrap, NetworkOnly for `/api/core/*`, online-only.
- Sentry init in pycil-core lifespan; nightly `pg_dump | restic` backup container.
- Stripe billing scaffold: webhook reads raw bytes, INSERT-event-before-dispatch in single txn, `subscription_data.metadata.user_id` for propagation.
- Rate limit: Redis sliding-window middleware on `/public/*` (60 RPM/IP).

---

## Topology

VPS (Hetzner CCX13 / DO 2vCPU/4GB) hosts the API + worker. Frontend runs on Vercel (separate platform). All API processes run via docker-compose on the VPS host. Caddy is the only port-exposed container; everything else lives on the internal docker network.

```
[Browser]
   |
   |  /  + /api/auth/*  -> Vercel (Next.js)
   |  /api/core/*       -> proxied via Vercel/Next rewrites OR direct to api.${DOMAIN}
   v
+--------+        +----------+
| Vercel |        |  Caddy 2 |  auto-TLS (Let's Encrypt) | gzip+zstd | SSE carve-out
+---+----+        +-----+----+
    |                   |
    | /api/core/* (server-side rewrite or browser direct)
    v                   v
                  +--> /api/core/jobs/*/stream  --> pycil-core:8000  (SSE, flush_interval -1)
                  +--> /api/core/*             --> pycil-core:8000  (handle_path strips prefix)
                  +--> /health                 --> pycil-core:8000

(internal docker network)
   pycil-core --asyncpg--> postgres:5432
   pycil-core --redis-py--> redis:6379  (SSE subscribe results:{term_id})
   worker     --asyncpg--> postgres:5432
   worker     --redis-py--> redis:6379  (arq queue + Pub/Sub publish)
```

Five containers on the VPS: `pycil-core`, `worker`, `postgres:16-alpine`, `redis:7-alpine`, `caddy:2`. Named volumes: `pgdata`, `redisdata`, `caddydata`, `caddyconfig`. Web runs on Vercel — no docker container, no VPS footprint.

---

## Caddy Configuration Notes

Two Caddyfiles ship with the repo:

- **`Caddyfile`** (production) — uses `{$DOMAIN}`, real Let's Encrypt certificates.
- **`Caddyfile.local`** (dev) — uses `local_certs` (Caddy internal CA) so dev never burns the Let's Encrypt 5-cert/wk-per-host limit.

Critical directives:

- `@sse path /jobs/*/stream` matcher (declared INSIDE the `handle_path /api/core/*` block, post-strip path) with `flush_interval -1` and `header_up X-Accel-Buffering no` — defeats Caddy's `encode` buffering for SSE chunks. Without this, "real-time" enrichment arrives at end-of-stream.
- `respond /api/core/auth/* 404` BEFORE `handle_path /api/core/*` — blocks the internal `POST /auth/upsert-user` endpoint from being reachable through the public proxy.
- `handle_path /api/core/*` strips the `/api/core` prefix before forwarding to `pycil-core:8000`. `reverse_proxy /api/core/*` (without `handle_path`) would forward the prefix and 404 every backend route.
- `header_up Origin {http.request.header.Origin}` propagates the browser's `Origin` header so the FastAPI CSRF middleware can validate it.

---

## Auth Flow (Auth.js v5 + FastAPI cookie share)

1. Browser hits `/api/auth/signin` -> Auth.js v5 redirects to Google OAuth.
2. Google callback -> Auth.js writes to `users`, `accounts`, `sessions`, `verification_token` via `@auth/pg-adapter`.
3. Cookie set: `__Secure-authjs.session-token` (prod, HTTPS) or `authjs.session-token` (dev, HTTP). Auth.js v5 cookie name — NOT v4's `next-auth.session-token`. SameSite=Strict (configured in `auth.config.ts`).
4. Subsequent web requests: Auth.js middleware reads cookie -> validates against `sessions` row.
5. Subsequent pycil-core requests (proxied via Caddy `/api/core/*`): `pycil_core/auth.py` reads cookie name from `SESSION_COOKIE_NAME` env, runs `SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.session_token = $1 AND s.expires > NOW()`.

The `WHERE expires > NOW()` clause is mandatory — it prevents leaked / revoked cookies from outliving their session row.

**CSRF defense (two-layer)**:

1. Auth.js cookie configured `SameSite=Strict` in `auth.config.ts`.
2. `pycil_core/middleware/csrf.py` rejects POST/PATCH/PUT/DELETE when `Origin` header is missing or not in `ALLOWED_ORIGINS`. Returns `403 csrf_mismatch`.

---

## SSE Flow (Term Enrichment)

The race-safest path that survives "worker publishes before client subscribes":

```
client                    web SSE handler                  postgres                  redis                     worker
  |                            |                              |                        |                          |
  |-- GET /api/jobs/{id}/stream|                              |                        |                          |
  |--------------------------->|                              |                        |                          |
  |                            |--auth + ownership check----->|                        |                          |
  |                            |  (user_term_jobs)            |                        |                          |
  |                            |                              |                        |                          |
  |                            |--SELECT jobs WHERE id=$1---->|                        |                          |
  |                            |<--row{status, result}--------|                        |                          |
  |                            |                              |                        |                          |
  |    if status terminal:                                                              |                          |
  |<-- emit final, close ------|                                                        |                          |
  |                            |                              |                        |                          |
  |    else (status pending):                                                           |                          |
  |                            |--SUBSCRIBE results:{term_id}--------------------->     |                          |
  |                            |--SELECT jobs again (race-safe re-check)--->|           |                          |
  |                            |<--row--------------------------------------|           |                          |
  |    if terminal post-subscribe: emit, close                                          |                          |
  |                            |                              |    (worker lifecycle)                              |
  |                            |                              |                        |<--LLM result--from job---|
  |                            |                              |                        |--PUBLISH results:{term_id}>
  |                            |<-- pubsub message ----------------------------+        |                          |
  |<-- emit result, close -----|                                                        |                          |
```

Key design points:

- **Ownership table is per-user**: `user_term_jobs(user_id, term_id, job_id)`. Multiple users adding the same term get separate rows pointing at the shared `job_id`. The SSE handler checks `WHERE user_id = $1 AND job_id = $2`.
- **Channel is term-keyed, not job-keyed**: `results:{term_id}`. Cross-user same-term enrichment delivers via the same publish.
- **Postgres-first read** before subscribing: if the worker published already (race), the SSE handler emits the terminal result from the `jobs` row and closes without subscribing.
- **Re-check after subscribe**: closes the narrow window between initial SELECT and SUBSCRIBE landing.
- **Heartbeat 15s, hard timeout 5min**, `x-accel-buffering: no` response header.

---

## Job Lifecycle (`generate_term`)

```
POST /api/core/decks/{id}/terms { value }
   -> term_service.add_term_to_deck
       -> validate term (length<=64, no newline/control)
       -> upsert terms row, attach to deck via deck_definitions
       -> job_service.enqueue_generate_term(user_id, term_id):
           1. _check_global_budget(redis)        # 503 budget_exhausted if cap hit
           2. _check_user_rate(redis, user_id)   # 429 rate_limited at >5/hr
           3. EVAL lock-or-get on lock:generate_term:{term_id} (NX EX 600)
           4. INSERT user_term_jobs (per-user ownership) with shared job_id
           5. if owner: INSERT jobs(status=pending) + arq.enqueue_job
              else: skip enqueue (cost-dedup), reuse existing job_id
   <- {job_id, deduped: bool}

worker (arq):
   load term value
   pre-INSERT idempotency: SELECT 1 FROM definitions WHERE term_id=$1
   render prompt (Jinja2 + role.md include) with term value inside <USER_TERM> fences
   ChatOpenAI(...).with_structured_output(schema, method="json_mode").invoke(prompt)
   sanitize output (strip URLs / HTML / control chars)
   INSERT definitions, definition_paraphrases, term_example_sentences
   UPDATE jobs SET status='completed', result=...
   INCRBYFLOAT openrouter:spend:daily {usd_cost}
   PUBLISH results:{term_id} {payload}
   (lock NEVER released in finally; TTL is the safety net so retries reuse the lock)
```

**Failure modes**:

- LLM returns invalid JSON -> Pydantic validation fails -> retry once with stricter prompt suffix -> on second failure, `jobs.status='failed'`, `jobs.error=...`, `PUBLISH {error: ...}`.
- arq enqueue fails after lock acquired -> `job_service` releases lock, marks `jobs.status='failed'` so user sees error instead of 10-minute spinner.
- Worker crashes mid-job -> arq retries (`max_tries=2`) reuse the same `job_id`. Pre-INSERT idempotency + `UNIQUE(term_id)` on `definitions` absorbs duplicate writes.
- Budget exhausted at runtime (not just startup) -> next enqueue returns 503; existing in-flight jobs complete.

---

## Learning Session Flow

---

## Test Strategy

### Backend unit tests

`pytest` suites per service:
- `apps/pycil-core/tests/` — conftest, migration, answer grading, gamification, model-schema parity
- `apps/worker/tests/` — conftest + canned LLM responses (no OpenRouter calls)
- `packages/shared-py/tests/` — question ABCs

### E2E tests (Playwright)

`apps/web/e2e/` — 6 Chromium specs covering auth, CRUD, learn, flashcard, explore, sign-out. See `apps/web/e2e/README.md` for architecture.

**Auth bypass**: JWT cookie injection via `jose` — no Google OAuth flow runs.

**LLM cost avoidance**: `WORKER_LLM_STUB=true` + `LLM_STUB_MODE=true` env vars prevent all OpenRouter calls. Worker returns canned responses from `apps/worker/tests/fixtures/llm_responses.json`. Core `stream_chat` yields a canned SSE response. Pre-seeded DB data eliminates enrichment needs.

**CI**: `.github/workflows/test.yml` `e2e` job — Postgres + Redis services, Alembic migrate, `next build`, `pnpm e2e` against `localhost:3000`.