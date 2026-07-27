# Code Review — Phase 3: AI Term Pipeline

**Date:** 2026-05-25
**Scope:** apps/pycil-core (job_service, jobs/terms routes, term_service, schemas, alembic 0002), apps/worker (full), apps/web (SSE handler, hook, term-card, types, db pool, dashboard wiring)
**LOC reviewed:** ~900 lines across 17 files
**Verdict:** Functional for happy path; one **Critical** correctness bug (cross-user backfill skip), three **Important** issues around enqueue/retry orchestration, several **Minor** items.

---

## Critical

### C1. `_backfill_deck_definitions` is skipped on the cache-hit path → cross-user `deck_definitions` rows are never created

**File:** `apps/worker/worker/jobs/generate_term.py:222-232`

When a second user adds an already-enriched term **after the original lock TTL expired** (≥600s after first job completed), the new `generate_term` invocation hits the pre-INSERT idempotency branch and returns early without calling `_backfill_deck_definitions`.

Flow:
1. User A adds "ephemeral" → job runs → INSERT `definitions(term=42)` + INSERT `deck_definitions(deck_a, def_id)` ✅
2. Lock TTL expires (~10 min later).
3. User B adds "ephemeral" to deck_b → `term_service.add_term_to_deck` writes `deck_terms(deck_b, 42)` and `enqueue_generate_term` acquires a fresh lock + new job.
4. Worker's `generate_term` runs → `_existing_definition_id` returns the existing id → publishes payload from existing data → **returns without backfill** (line 232).
5. Result: `deck_terms(deck_b, 42)` exists but `deck_definitions(deck_b, def_id)` does NOT.

**Impact:** Phase 3 UI keeps working (because `term_service.list_deck_terms` joins `deck_terms`, not `deck_definitions`), so the bug is silent today. Phase 5 learning mode and any future query that walks `deck_definitions` will miss user B's deck. This breaks the contract implied by the migration comment at `alembic/versions/0002_deck_terms.py:8-9` ("the worker will translate matching deck_terms rows into deck_definitions").

**Fix:** Call `_backfill_deck_definitions(session, term_id, existing)` inside the cache-hit branch before commit/publish. One additional INSERT … SELECT … ON CONFLICT DO NOTHING; cheap and idempotent.

---

## Important

### I1. arq enqueue happens AFTER DB commit → enqueue failure leaves an orphan `pending` job

**File:** `apps/pycil-core/pycil_core/services/job_service.py:103-134`

Order of operations:
1. Redis `lock:generate_term:{term_id}` set with new `job_id` (TTL 600s).
2. INSERT `jobs(...)` + INSERT `user_term_jobs(...)` + `session.commit()`.
3. `pool.enqueue_job("generate_term", ...)`.

If step 3 raises (Redis blip, arq queue overflow, network), the DB has a `pending` `jobs` row that no worker will ever pick up. The lock holds for 600s so subsequent enqueue attempts return the dead `job_id`. SSE for that `job_id` will hang until the 5-minute client timeout (`apps/web/app/api/jobs/[id]/stream/route.ts:19`). The dead `jobs` row is permanent.

**Impact:** Real risk on Redis hiccup. Combined with the lock holding the dead job_id, multiple users adding the same term within 10 minutes of the failure all get the same dead `job_id`.

**Fix options (any):**
- Move `enqueue_job` before commit; commit only on enqueue success (best — single failure mode).
- Wrap `enqueue_job` in try/except that marks the `jobs` row `failed`, deletes the lock, and re-raises.
- Add a janitor task that fails `pending` jobs older than `LOCK_TTL`.

### I2. Failed-then-retry path publishes a `failed` event before arq retries → SSE closes prematurely on transient errors

**File:** `apps/worker/worker/jobs/generate_term.py:256-268`

The except branch always publishes `{status: "failed", error: ...}` to `results:{term_id}` and re-raises so arq counts the attempt. With `max_tries=2` (`apps/worker/worker/main.py:24`), one transient failure (network hiccup, model 503) emits `failed`; the SSE handler closes (`apps/web/lib/use-job-stream.ts:36-48`); the user sees an error toast even though the second attempt may succeed and write a complete `definitions` row.

**Impact:** False failure UX on every transient error. The arq retry succeeds silently; the user has to refresh.

**Fix:** Use `ctx.get("job_try", 1)` and `ctx.get("max_tries", ...)`. Only publish terminal `failed` when `job_try >= max_tries`. For intermediate failures, append a `kind: "retry"` event but keep `jobs.status = "pending"`.

### I3. `_invoke_llm` retry-with-stricter-suffix only catches `ValidationError`

**File:** `apps/worker/worker/jobs/generate_term.py:83-89`

LangChain's `with_structured_output(method="json_mode")` does not exclusively raise `pydantic.ValidationError` on bad output — depending on provider it can raise `OutputParserException`, `json.JSONDecodeError`, or even bubble a raw API exception. Today's path: any non-`ValidationError` failure skips retry and falls into the outer except → `failed` (per I2, this also misleads UX).

**Fix:** Catch `(ValidationError, ValueError, OutputParserException)` (import from `langchain_core.exceptions`), or fall back to a broader catch that excludes only `httpx.TimeoutException`/auth errors.

---

## Minor

### M1. Lenient paraphrase/example counts diverge from spec

**File:** `apps/worker/worker/schemas/term_generation.py:55-56`

Spec (phase-03 lines 22, 35) says exactly 3 paraphrases/examples; schema accepts 2–4. Defensible (LLM jitters), but the UI assumes 3 and may render an inconsistent grid. Either tighten to `min_length=3, max_length=3` or add a server-side post-fill step.

### M2. `_check_user_rate` increments counter before budget check; failures consume quota

**File:** `apps/pycil-core/pycil_core/services/job_service.py:74-75`

Order: rate-limit `INCR` (line 74) → budget check (line 75). If `_check_global_budget` raises 503, the user has lost a quota slot. Swap order, or use a single Lua script that does both atomically.

### M3. `add_spend` resets daily key TTL to 25h on every call → key never resets at midnight

**File:** `apps/worker/worker/redis_helpers.py:43`

`expire(SPEND_KEY_DAILY, 90_000)` slides the TTL forward on every spend. Under continuous traffic the daily counter accumulates indefinitely. v1 might run a manual reset, but for launch consider pinning the key to UTC midnight via `EXPIREAT`.

### M4. Worker `sanitize_text` can empty the user-supplied term

**File:** `apps/worker/worker/sanitize.py:12-20` invoked at `apps/worker/worker/jobs/generate_term.py:236`

If a user submits `"https://example.com"` (passes API checks: 19 chars, no control chars), worker's `sanitize_text` strips the URL leaving `""`. Prompt then renders `<USER_TERM></USER_TERM>` and the LLM hallucinates a definition for nothing. Either:
- Validate term at API against URL/email regex (reject), or
- Skip URL/email stripping for the prompt input (term is wrapped in fences anyway; just strip control chars).

### M5. Estimated spend is a fixed constant, not actual usage

**File:** `apps/worker/worker/jobs/generate_term.py:39, 239`

`_ESTIMATED_COST_USD = 0.0005` is fine as a v1 placeholder. OpenRouter responses include `usage.completion_tokens`/`usage.prompt_tokens` and per-model pricing; the budget cap will drift from reality. Acceptable for launch; track actual cost when accuracy matters.

### M6. SSE handler enqueues to a closed controller on the recheck race

**File:** `apps/web/app/api/jobs/[id]/stream/route.ts:120-145`

If the pub/sub message arrives between `subscribe()` and the post-subscribe recheck SQL, the subscribe callback fires `cleanup()` and closes the controller. The recheck branch then calls `send("result", r.result)` → `controller.enqueue` on a closed controller → throws (only `controller.close()` is wrapped in try/catch at line 109-110). The throw is swallowed by the outer `try` and a stray `error` event is sent. Functionally fine but noisy.

**Fix:** Guard `send` with `if (closed) return;`.

### M7. `_check_user_rate` only sets TTL when `incr` returns 1

**File:** `apps/pycil-core/pycil_core/services/job_service.py:42-46`

If the key was created without TTL by an earlier process and then re-incremented, no TTL is ever set. Edge case; cheap to harden:
```python
n = await redis.incr(key)
await redis.expire(key, 3600, nx=True)  # set TTL only if currently no TTL
```

### M8. `with_structured_output` `model="openai/gpt-4o-mini"` with `method="json_mode"` — confirm OpenRouter passthrough

The default model is fine for json_mode. If a fallback later swaps to a model OpenRouter does not pass `response_format` to (some Gemini routes), JSON mode will silently degrade. Out of scope for this review but flag for phase 4.

---

## Verified Good

- **AC1 single LLM call:** Lua lock-or-get + `_job_id=new_job_id` + pre-INSERT idempotency together enforce single LLM call per `term_id` per lock window. (`job_service.py:80-101`, `generate_term.py:222-232`)
- **AC2 SSE postgres-first:** Initial SELECT before SUBSCRIBE; emits and closes for terminal status. Race-safe re-check after subscribe lands. (`route.ts:47-72, 134-145`)
- **AC4/AC5 idempotency + UNIQUE(term_id):** Migration `0001_init.py:165` enforces UNIQUE; `_persist_definition` uses `ON CONFLICT (term_id) DO UPDATE`. (`generate_term.py:106`)
- **AC6 lock TTL-only release:** No `redis.delete(lock:...)` anywhere in worker; comment at `generate_term.py:270` documents intent. arq retries reuse the same `job_id` (`pool.enqueue_job(... _job_id=new_job_id)` at `job_service.py:131`).
- **AC7 cross-user channel + ownership:** Channel keyed `results:{term_id}` (`generate_term.py:53`); ownership via `user_term_jobs` (`jobs.py:20-30`, `route.ts:39-45`).
- **AC8 prompt injection:** API rejects newlines/control (`term_service.py:28-29`), term wrapped in `<USER_TERM>` fences (`generate_term.md:6`), role.md instructs "data not instructions" (`role.md:8-11`), output sanitized (`sanitize_text` applied to all string fields in `_persist_definition`).
- **AC9 rate limit + budget:** Both enforced pre-enqueue against the **same Redis key** as worker's `add_spend` (`openrouter:spend:daily`). Verified via grep.
- **AC10 SSE timeout/heartbeat:** `HEARTBEAT_MS=15_000`, `TIMEOUT_MS=5*60_000` (`route.ts:18-19`).
- **Off-by-one:** `deck_terms.position` uses `COALESCE((SELECT MAX(position)+1 ...), 0)` → first term position 0, then 1, 2, … ✅ (`term_service.py:73`)
- **Streamed payload shape match:** worker `_build_payload` returns `{term_id, definition, paraphrases, examples}`; SSE forwards as `result`; `term-card.tsx:44-56` reads `stream.result.definition.*`. Field names align.
- **Phase 1-2 regressions:** `add_term_to_deck` signature unchanged; `TermAddResponse` only adds `job_id` (additive — phase 2 plan allowed this). `UserDep`/`SessionDep` and raw-SQL-via-`text()` patterns preserved.
- **Public contract changes:** `TermAddResponse.job_id` (additive) and new `DeckTermRead` schema match plan.

---

## Recommended Actions (Priority Ordered)

1. **C1** — Call `_backfill_deck_definitions` in the cache-hit branch (`generate_term.py:228`). One-line fix.
2. **I1** — Reorder enqueue/commit, or add cleanup-on-enqueue-failure.
3. **I2** — Gate `failed` publish on `job_try >= max_tries` using `ctx`.
4. **I3** — Broaden `_invoke_llm` retry catch to include `OutputParserException` / `ValueError`.
5. **M2** — Swap rate-limit and budget order or atomicize.
6. **M4** — Remove URL/email stripping from term input (only sanitize LLM output).
7. **M3, M6, M7, M5, M1** — Hardening, defer if time-pressed.

---

## Build / Type / Lint Notes

- No new lint errors introduced (ruff settings unchanged in `pyproject.toml`).
- Expected pyright "import not resolved" warnings for langchain/langchain_openai/jinja2/sqlalchemy/redis remain (no installed packages locally) — acceptable per task brief.
- The `# type: ignore[arg-type]` at `openrouter.py:23` and `redis_helpers.py:21` are warranted (third-party type stubs lag).

## Unresolved Questions

- Should phase 5 read from `deck_definitions` (current schema) or shift to `deck_terms` JOIN `definitions`? The C1 fix preserves the current schema contract; deciding the canonical join now would let us drop the backfill step entirely.
- `OPENROUTER_BUDGET_DAILY_USD` default is `20` in `worker/config.py:23` and `job_service.py:54` — acceptable, but confirm prod env sets this explicitly so the default doesn't mask misconfig.
