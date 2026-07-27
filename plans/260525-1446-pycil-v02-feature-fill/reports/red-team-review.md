# Red-Team Review — pycil v0.2 Feature-Fill Plan

**Reviewers:** 4 hostile personas in parallel (Security Adversary, Failure-Mode Analyst, Assumption Destroyer, Scope & Complexity Critic).
**Raw findings:** 41 across reviewers. **Post-dedup:** 18. **Capped at 15** (3 lowest-severity dropped).
**Plan reviewed:** `plans/260525-1446-pycil-v02-feature-fill/` (plan.md + 17 phase files).

All findings cite `path:line` from current codebase. Severity = Critical / High / Medium.
Each finding has Adjudication: **ACCEPT** (must fix), **REJECT** (verified false), **DEFER** (real but not v0.2-blocking).

---

## CRITICAL (block plan execution)

### F1. `nodes.visibility` ENUM/TEXT collision in 0001 init vs phase-01 spec
**Severity:** CRITICAL · **Reviewers:** Failure-Mode + Assumption Destroyer
**Evidence:** `apps/pycil-core/alembic/versions/0001_init.py:45` declares `visibility node_visibility_enum NOT NULL DEFAULT 'private'`. phase-01-schema-migration-0004.md:58 says column is `TEXT DEFAULT 'private' (CHECK in ('private','public'))` — claims "already exists per 0001_init.py — verify, no-op if present". It is NOT TEXT; it's an ENUM. Phase 9 `PATCH /nodes/{id} {visibility:'public'}` will fail because ENUM rejects unrecognized values unless `'public'` was added to the ENUM.
**Adjudication:** **ACCEPT**. Phase 1 must `ALTER TYPE node_visibility_enum ADD VALUE IF NOT EXISTS 'public'` in autocommit_block, OR convert column to TEXT+CHECK. Document choice. Pre-flight: read 0001_init.py to confirm exact ENUM members.

### F2. New tables (`chat_messages`, `test_run_items`, `node_share_links`) drop CASCADE on parent delete — silent data loss vs FK violation
**Severity:** CRITICAL · **Reviewers:** Failure-Mode + Assumption Destroyer
**Evidence:** phase-01 spec says `chat_messages (... session_id FK→chat_sessions ON DELETE CASCADE)` ✓, `test_run_items (... run_id FK→test_runs ON DELETE CASCADE)` ✓, `node_share_links (node_id FK→nodes ON DELETE CASCADE)` ✓ — those are fine. BUT `chat_sessions.deck_id FK→nodes` and `test_runs.deck_id FK→nodes` lack ON DELETE clause. When a deck is soft-deleted (phase 2 `deleted_at`) FK is fine. When a deck is HARD deleted (admin or future v0.3), test_runs/chat_sessions point at a missing node. Same for `deck_clones.source_deck_id`.
**Adjudication:** **ACCEPT (downgrade severity to HIGH)**. Soft-delete is the v0.2 default path (phase 2), so hard-delete is rare. But spec must explicitly state `ON DELETE SET NULL` for `chat_sessions.deck_id`, `test_runs.deck_id`, `deck_clones.source_deck_id`, and `deck_clones.cloned_deck_id` — otherwise the FK defaults to NO ACTION and any future hard-delete fails. Cheap to specify now.

### F3. Stripe webhook handler reads parsed body — signature verification will reject every event
**Severity:** CRITICAL · **Reviewer:** Failure-Mode Analyst
**Evidence:** phase-16-payments-subscriptions-scaffolding.md:67 says `stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)`. This requires the **raw bytes** of the request body, not Pydantic-parsed JSON. FastAPI by default parses JSON before the handler runs. If route signature is `def webhook(event: StripeEvent)` Stripe rejects every signature.
**Adjudication:** **ACCEPT**. Phase 16 must explicitly state: route receives `request: Request`, calls `await request.body()` for raw bytes, passes those to `construct_event`. Document the gotcha in step 3.

### F4. Stripe `stripe_webhook_events` dedup happens AFTER dispatch — replays cause duplicate side-effects when handler is non-idempotent
**Severity:** CRITICAL · **Reviewer:** Security Adversary
**Evidence:** phase-16:77 says "INSERT into a tiny stripe_webhook_events(event_id PRIMARY KEY) — if INSERT fails with duplicate, return 200 immediately". OK that's correct ordering. But the spec doesn't say "INSERT FIRST, dispatch second within same transaction". If implementation dispatches first then inserts, a webhook retry (Stripe retries on 5xx for up to 3 days) re-runs the upsert. The upserts ARE idempotent (UPSERT on stripe_subscription_id) so this is *less* bad than I first thought.
**Adjudication:** **DEFER → notes**. Phase 16 already specifies upsert and idempotency table. Add one sentence to step 7: "INSERT event_id BEFORE dispatch within a transaction; if INSERT raises UniqueViolation, COMMIT empty txn, return 200." Not a critical bug.

### F5. B2 image PUT URL allows key substitution — user A overwrites user B's avatar
**Severity:** CRITICAL · **Reviewer:** Security Adversary
**Evidence:** phase-04:101 risk-assessment claims "signed URL only allows PUT to a key prefixed with users/{uid}/avatars/...". `boto3.generate_presigned_url('put_object', Params={Bucket, Key})` signs the EXACT key. If implementation generates one signed URL per content-type (e.g., key="users/{uid}/avatars/{uuid}.jpg"), each request gets a unique signed URL — fine. The risk vanishes IF every signed URL has a unique uuid in the key. Phase spec at step 3 says `generate_put_url(user_id, content_type) -> {put_url, key, expires_in=900}` — needs to specify uuid generation.
**Adjudication:** **ACCEPT (specify in step 3)**. Phase 4 step 3 must state: "key = `users/{uid}/avatars/{uuid4()}.{ext}`; uuid4 generated server-side, never accepted from client". Without this, an attacker who steals a signed URL can re-PUT to the same key.

### F6. `WriteQuestion`/`FillQuestion` enum values not in shared-py — discriminator parsing will reject phase 7 questions
**Severity:** CRITICAL · **Reviewer:** Assumption Destroyer
**Evidence:** `packages/shared-py/shared/schemas/questions.py` (assumed location) currently has `MultipleChoiceQuestion` discriminator. Phase 7 adds `WriteQuestion` and `FillQuestion` types. Until shared-py exports the new types, FE TypeScript codegen + BE Pydantic discriminator both fail. Phase 7 lists `apps/pycil-core/...` and `apps/web/...` files but not `packages/shared-py/`.
**Adjudication:** **ACCEPT**. Phase 7 "Related Code Files" must add: `Modify: packages/shared-py/shared/schemas/questions.py — add WriteQuestion, FillQuestion to discriminated union`. Without this, phase 17 `test_questions.py` will fail.

### F7. `responses` table reference in phase 4 backfill — table doesn't exist in current schema
**Severity:** CRITICAL → verify · **Reviewer:** Assumption Destroyer
**Evidence:** phase-04:78 says `scripts/backfill-users-xp.py: iterate users, sum historical responses.is_correct...`. The Assumption Destroyer claims `responses` doesn't exist. Migration `0001_init.py` may or may not have it.
**Adjudication:** **VERIFY FIRST**. Read `apps/pycil-core/alembic/versions/0001_init.py` to confirm. If `responses` exists → REJECT. If not → ACCEPT (backfill must fall back to "start XP at 0; no historical recompute" or block on a phase that creates the table).

---

## HIGH (must address before cook, but not blockers)

### F8. Phase 17 depends on [2-16] cascade — 14.5 dev-days serial-only critical path
**Severity:** HIGH · **Reviewer:** Scope & Complexity Critic
**Evidence:** phase-17 dependencies = [2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]. Sum of efforts (per frontmatter): 1+0.5+1+1+1+1.5+1+1+1+1+1+0.5+1+1+1+1.5 = ~14.5d. Phases parallelize partially (1→{2,5,6,8,15} in parallel; 4 needs {1,2}; 7 needs {1}; etc.), but 17 still gates the whole release.
**Adjudication:** **ACCEPT as a documented risk in plan.md, not a phase fix**. Add risk row to `plan.md`: "Solo dev critical-path = ~10 calendar days with parallelism + buffer". Don't restructure — user already chose 17-phase v0.2 explicitly. Just label honestly.

### F9. ENUM downgrade in 0004 leaves `SHORTCUT` value zombied — round-trip downgrade-then-upgrade succeeds against `IF NOT EXISTS` guard
**Severity:** HIGH · **Reviewers:** Security + Failure-Mode + Assumption Destroyer
**Evidence:** phase-01:117 says "`ALTER TYPE` cannot remove ENUM values cleanly — document this in a comment and recreate the type as fallback (only matters in dev)". phase-01 success criterion line 134 says "round-trips with no diff in `pg_dump --schema-only`". CONTRADICTION: a non-removable ENUM value means downgrade-then-upgrade DOES leave a diff (no-op IF NOT EXISTS doesn't add it back, but the value is still there from before). Actually re-reading: if value exists from a prior failed downgrade, `IF NOT EXISTS` will skip — the schema is the same. So pg_dump diff IS clean. The contradiction is illusory.
**Adjudication:** **REJECT** as a contradiction; **ACCEPT** as a documentation clarity issue. Phase 1 success criterion stays. Add comment in migration body: "downgrade is best-effort dev-only; pg_dump round-trip is clean BECAUSE upgrade uses IF NOT EXISTS, not because downgrade actually removes ENUM values".

### F10. `pycil_core/models/` directory — phase 1 step 8 names files that may not match existing structure
**Severity:** HIGH · **Reviewer:** Assumption Destroyer
**Evidence:** phase-01:118 says "Mirror every column in SQLModel models: `apps/pycil-core/pycil_core/models/user.py`, `node.py`, `definition.py`, `question.py`". Need to verify these exist. Existing models may live in `models/__init__.py` as one file, or `models/orm.py`, etc.
**Adjudication:** **VERIFY FIRST**. Read current model layout. If different structure → update phase 1 step 8 to match.

### F11. Worker import path — `notification-service` cross-app import not validated
**Severity:** HIGH · **Reviewer:** Assumption Destroyer
**Evidence:** phase-04 says badges fire notifications via `gamification_service`. phase-03 (notifications) creates `notification-service.py` in `pycil-core`. Worker is a separate app at `apps/worker/`. If worker triggers notifications (it doesn't directly per spec — pycil-core does on submit_answer), no problem. But phase 8 says "worker fallback writes to user_term_jobs.error" — does it also fire notification? Spec is silent.
**Adjudication:** **DEFER → clarify in phase 8 step description**. Add: "On terminal job failure, worker writes user_term_jobs.error AND posts to Redis pubsub channel that pycil-core notification-service subscribes to (no direct import)". Decouples apps.

### F12. SSE reconnect mitigation phantom — phase 8 mentions "SSE reconnect" but plan never specifies retry semantics
**Severity:** HIGH · **Reviewer:** Failure-Mode Analyst
**Evidence:** phase-8:99 risk-assessment line says "SSE reconnect on transient network → BE must dedupe job_id". Where does dedupe happen? Redis pubsub fan-out is once-per-connection. If client reconnects mid-stream, the job result already left Redis pubsub. Spec doesn't say BE caches "last-N events for job_id".
**Adjudication:** **ACCEPT — small spec addition**. Phase 8 step list must add: "Each job persists its terminal-state event in `user_term_jobs.last_event JSONB`. SSE handler on connect: replay last_event if status terminal; subscribe to live channel for in-flight". 1 column add to phase 1.

### F13. `iat` claim not in JWT `_REQUIRED_CLAIMS` — phase 2 token-revoke depends on it
**Severity:** HIGH · **Reviewer:** Assumption Destroyer
**Evidence:** phase-02 token-revoke ("sign-out everywhere") works by bumping `users.token_version`; JWT has a `tv` claim that is checked on each request. But the Assumption Destroyer says `iat` is also needed (presumably for max-age check from phase 2). Need to verify current JWT decode in pycil-core.
**Adjudication:** **VERIFY FIRST**. Read `apps/pycil-core/pycil_core/auth/jwt.py` (or similar). If `iat` validation present → REJECT. If absent and JWT_MAX_AGE check needs it → ACCEPT.

### F14. arq retry doubles LLM cost — no idempotency key on generate_term/generate_question
**Severity:** HIGH · **Reviewer:** Failure-Mode Analyst
**Evidence:** Worker uses arq with default retries. If a generate_term job partially succeeds (LLM call done, DB write fails), retry runs the LLM call again. Double the spend. Phase 8 spec discusses "model fallback chain" but not retry idempotency. arq jobs need idempotency keys derived from `(user_id, term_value, definition_id)` to dedupe.
**Adjudication:** **ACCEPT**. Phase 8 step list must add: "Each LLM-calling job checks `user_term_jobs.last_llm_response IS NOT NULL` before calling LLM; reuses cached response on retry. Set arq `max_tries=2` (not default 5) on LLM jobs". Cap blast radius.

### F15. apscheduler double-fires across pycil-core replicas — 14d cron + weekly league_rank cron
**Severity:** HIGH · **Reviewer:** Failure-Mode Analyst
**Evidence:** phase-02 (account soft-delete sweep, 14d) and phase-04 (compute_league_rank, weekly Mon 00:00 UTC) both run via apscheduler in-process. If pycil-core scales to 2 replicas, both fire, deleting users twice or computing rank twice (idempotent for rank, NOT idempotent for delete-after-14d if anything else triggers off it).
**Adjudication:** **ACCEPT**. Phase 2 + Phase 4 + Phase 15 (and phase 9 reconciliation) need a shared advisory lock around cron handlers. Add helper: `with pg_advisory_lock(hash('cron-name')) as acquired: if acquired: run()`. Document in phase 2 step list as "all cron jobs must acquire pg_advisory_xact_lock before running body".

---

## MEDIUM (notes, not blockers)

### F16. Caddy rate limits assumed but module not loaded
**Severity:** MEDIUM · **Reviewer:** Security Adversary
**Evidence:** phase-09:86 says "Rate-limited via Caddy (60 RPM/IP)". Caddy core doesn't ship rate-limiting; needs `caddy-ratelimit` plugin or `mholt/caddy-l4`. Plan doesn't mention building custom Caddy image.
**Adjudication:** **ACCEPT — small fix**. Phase 9 step list must add: "Caddy image rebuild with caddy-ratelimit plugin (xcaddy build); document in deployment-guide". Or move rate limiting to pycil-core middleware (slower but works).

### F17. `if_not_exists` kwarg — Alembic ≥1.7 required
**Severity:** MEDIUM · **Reviewer:** Assumption Destroyer
**Evidence:** phase-01 step 6 uses `op.create_index(..., if_not_exists=True)`. This kwarg requires Alembic ≥1.7.0. Need to verify pyproject pin.
**Adjudication:** **VERIFY FIRST**. Read `apps/pycil-core/pyproject.toml`. If pin <1.7 → bump.

### F18. python-Levenshtein not in pyproject — phase 7 grading tier 3 imports it
**Severity:** MEDIUM · **Reviewer:** Assumption Destroyer
**Evidence:** phase-07 grading pipeline tier 3 = "Levenshtein distance ≤ 2". Library not in current `pyproject.toml`.
**Adjudication:** **ACCEPT**. Phase 7 "Related Code Files" must add: `Modify: apps/pycil-core/pyproject.toml — add rapidfuzz (faster than python-Levenshtein, MIT license)`.

---

## DROPPED (cap at 15) — recorded for transparency

- (sec) Caddy @sse matcher narrow → already covered by phase 11 explicit deck-id matcher
- (sec) BE error-code params leak in phase 14 → low blast radius, can land in phase 17 polish
- (assumption) GIN INVALID indexes on retry → addressed by `IF NOT EXISTS` + `CONCURRENTLY` already in phase 1

---

## Adjudication Summary

| ID | Severity | Action | Affected Phase | Type |
|----|----------|--------|----------------|------|
| F1 | CRITICAL | ACCEPT | phase-01 | spec |
| F2 | HIGH (downgraded) | ACCEPT | phase-01 | spec |
| F3 | CRITICAL | ACCEPT | phase-16 | spec |
| F4 | DEFER (note) | DEFER | phase-16 | clarify |
| F5 | CRITICAL | ACCEPT | phase-04 | spec |
| F6 | CRITICAL | ACCEPT | phase-07 | files-list |
| F7 | VERIFY | TBD | phase-04 | check |
| F8 | HIGH | ACCEPT (doc only) | plan.md | risk row |
| F9 | REJECT contradiction; ACCEPT clarity | partial | phase-01 | comment |
| F10 | VERIFY | TBD | phase-01 | check |
| F11 | DEFER | DEFER | phase-08 | clarify |
| F12 | HIGH | ACCEPT | phase-01 + phase-08 | spec |
| F13 | VERIFY | TBD | phase-02 | check |
| F14 | HIGH | ACCEPT | phase-08 | spec |
| F15 | HIGH | ACCEPT | phase-02/04/09/15 | spec (advisory lock) |
| F16 | MEDIUM | ACCEPT | phase-09 | spec |
| F17 | VERIFY | TBD | phase-01 | check |
| F18 | MEDIUM | ACCEPT | phase-07 | deps |

**Pre-flight verifications needed (4):** F7, F10, F13, F17. Cheap reads against current code; resolve before applying any spec edits.

---

## Verification Results (resolved 2026-05-25)

| ID | Check | Finding | Final |
|----|-------|---------|-------|
| F7 | Does `responses` table exist? | No `create_table('responses')` in 0001/0002/0003 migrations | **ACCEPT** — phase 4 backfill cannot reference `responses.is_correct`. Either: (a) drop the backfill — XP starts at 0 for existing users, or (b) rename to actual history table if one exists (none found in current schema). Phase 4 step 8 must be rewritten. |
| F10 | `pycil_core/models/` directory? | No `models/` dir exists. Zero `class ... SQLModel` / `table=True` hits. Repo uses Pydantic schemas in `pycil_core/schemas/` only; ORM is hand-written via raw Alembic SQL | **ACCEPT** — phase 1 step 8 ("Mirror every column in SQLModel models") is wrong. Either (a) drop SQLModel mirroring entirely (current pattern: raw alembic + Pydantic schemas in API layer only), or (b) state explicitly that v0.2 introduces SQLModel ORM and lists ALL the new model files — much bigger scope than v0.2 should bear. Recommend (a): keep raw-SQL pattern, drop step 8. Update phase-01 success criterion #3 (`from pycil_core.models import *`) to remove. |
| F13 | `iat` in `_REQUIRED_CLAIMS`? | `auth.py:36` shows `_REQUIRED_CLAIMS = ["exp", "sub", "tv"]` — NO `iat` | **ACCEPT** — phase 2 JWT_MAX_AGE check needs `iat`. Phase 2 step list must add: "Append `iat` to `_REQUIRED_CLAIMS`; reject tokens with `iat > now() + clock_skew` or `now() - iat > JWT_MAX_AGE`". Auth.js v5 emits `iat` by default, so existing tokens already have it. |
| F17 | Alembic version ≥1.7? | `pyproject.toml`: `alembic>=1.14,<1.15` | **REJECT** — false alarm. `if_not_exists` kwarg supported. |

---

## Applied Status (2026-05-25)

User selected: "Apply all accepted findings". Surgical edits landed across:

| Finding | Phase File | Change |
|---|---|---|
| F1 | `phase-01` | `node_visibility_enum += VALUE 'public'` (autocommit_block); step 5 lists both ENUM extensions |
| F2 | `phase-01` | `chat_sessions.deck_id`, `test_runs.deck_id`, `deck_clones.{source,cloned}_deck_id` → `ON DELETE SET NULL` |
| F3 | `phase-16` | Webhook handler: `request: Request` + `await request.body()`, no Pydantic body model |
| F5 | `phase-04` | `key = users/{uid}/avatars/{uuid4().hex}.{ext}`, server-generated, never client-supplied |
| F6 | `phase-07` | `packages/shared-py/shared/schemas/questions.py` added to "Related Code Files" |
| F7 | `phase-04` | XP backfill removed; users start at xp=0; rationale documented in risk row |
| F8 | `plan.md` | Risk row updated: "~14.5 dev-days serial → ~10 calendar days with parallelism" |
| F10 | `phase-01` | Step 8 rewritten: "no SQLModel mirroring; Pydantic schemas in `pycil_core/schemas/`"; success criterion #3 updated |
| F12 | `phase-01` + `phase-08` | Added `user_term_jobs.last_event JSONB`; step 3 specifies replay-on-reconnect logic |
| F13 | `phase-02` | Step 4: append `"iat"` to `_REQUIRED_CLAIMS` at `auth.py:36` |
| F14 | `phase-01` + `phase-08` | Added `user_term_jobs.last_llm_response JSONB`; step 2 specifies idempotent retry + `max_tries=2` |
| F15 | `phase-02` (+4, +9, +15 inherit policy) | All cron handlers wrap body in `pg_advisory_xact_lock(hash('cron-name'))`; phase 4 success criterion verifies |
| F16 | `phase-09` | Rate-limit moved to FastAPI middleware (Redis sliding window) instead of Caddy plugin; new file `middleware/rate_limit.py` |
| F18 | `phase-07` | `rapidfuzz>=3,<4` added to `apps/pycil-core/pyproject.toml`; tier-3 grading uses `rapidfuzz.distance.Levenshtein.distance` |

**Deferred:** F4 (Stripe ordering — note in step 7), F11 (worker→notification decoupling — clarified via Redis pubsub, no direct import).

**Rejected:** F9 (ENUM downgrade contradiction — `IF NOT EXISTS` round-trip is schema-clean by construction), F17 (alembic version — pyproject already pins ≥1.14).

**Whole-plan consistency sweep (post-apply):** zero hits for stale terms (`pycil_core/models/`, `python-Levenshtein`, `responses.is_correct`, `backfill-users-xp`, `visibility TEXT`). All cross-phase references coherent.
