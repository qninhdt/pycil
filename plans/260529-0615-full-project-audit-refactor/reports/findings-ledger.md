# Findings Ledger — Full-project audit & refactor

Plan: `plans/260529-0615-full-project-audit-refactor/`
Protocol: a finding is **CONFIRMED** only with a failing repro/test or a source citation proving the defect. Verified decisions locked with `verified by {file:line}` / `verified by test {name}`.

Severity: P1 = data/money/authz/runtime-break · P2 = correctness · P3 = robustness/style

| ID | file:line | sev | claim | repro / evidence | status |
|----|-----------|-----|-------|------------------|--------|
| F1 | services/term_notes_service.py:49,53 | P1 | `async def delete` shadows `from sqlalchemy import delete`; inner `delete(TermNote)` self-recurses → coroutine has no `.where` → runtime AttributeError/TypeError on every note delete | source: l.11 import, l.49 def, l.53 call — verified by read | CONFIRMED → fixing P1 |
| F2 | services/saved_search_service.py:74,90 | P1 | `async def update` shadows imported `update`; `update(SavedSearchRecord)` (l.90) calls the coroutine → `.where` fails at runtime | source read l.16/74/90 | CONFIRMED → fixing P1 |
| F3 | services/saved_search_service.py:97,101 | P1 | `async def delete` shadows imported `delete`; `delete(...)` (l.101) self-recurses | source read l.16/97/101 | CONFIRMED → fixing P1 |
| F4 | services/definition_overrides_service.py:54,58 | P1 | `async def delete` shadows imported `delete`; `delete(...)` (l.58) self-recurses | source read l.13/54/58 | CONFIRMED → fixing P1 |
| F5 | services/share_link_service.py:11 | P3 | unused `delete` import (F401); `update`+`func` used, `delete` not | ruff F401; grep shows no `delete(` in body | CONFIRMED → fixing P3 |
| F6 | api/routes/notifications.py:32, auth.py:76, main.py:93 | P3 | B008 — `Query()`/`Depends()` in arg defaults. FastAPI's intended DI pattern, not a bug | ruff B008 | TRIAGE → suppress (noqa), not fix |
| F7 | tests/test_answer_grading.py (fuzzy tier) | P2 | `definishun`→`definition` expected `fuzzy`, got `no_match`. NOT conversion-caused: test predates checkpoint 9f07149, `answer_grading_service.py` not in diff | `uv run pytest` fail; `git log` single ancestor commit | PRE-EXISTING → quarantine in Phase 8 |
| F8 | pyproject.toml:36,58 | P3 | `fakeredis[lua]` declared twice (optional-deps.dev + dependency-groups.dev) | source read | CONFIRMED → dedup deferred (verify test-invocation first) |
| F9 | tests/conftest.py:122,233,271 | P1 | Test fixtures construct plain `sqlalchemy.ext.asyncio.AsyncSession`, which has NO `.exec()`. Every converted service calls `session.exec(...)` → `AttributeError` under test. Runtime `db.py:4` is correct (SQLModel AsyncSession); the TEST harness was never aligned to the conversion — this is why the conversion shipped "unverified" (full suite never ran green). | `uv run pytest` vs real PG → 12 failures, all `'AsyncSession' object has no attribute 'exec'` at billing_service.py:83 etc. | CONFIRMED → fixing P1 |
| F10 | services/*.py (data_export:79, conftest:196/214) | P2 | residual `session.execute()` (deprecated) not converted to `.exec()` — Pyright deprecation flag | Pyright diag | NOTED → Phase 2 parity scope |
| F11 | services using `select(Model.col, ...)` → `.first()`/`.all()` then `.attr` access (saved_search:65-68, share_link:87-90/117-120, backup_rehearsal:78-81) | P2 | Row-tuple attribute access; works at runtime (Row supports both) but shape-ambiguous — same family as the isinstance hack | Pyright diag | NOTED → Phase 2 parity scope |
| F12 | shared/db/models.py — `_dt_column`, surrogate `id` PKs | **P1** | DDL has `DEFAULT NOW()` / `gen_random_uuid()`; models lacked `server_default`, so INSERT sent `created_at=NULL` → IntegrityError. **Broke share-link/subscription/notification creation in PRODUCTION.** | full-DB suite: `IntegrityError` on `node_share_links` INSERT | FIXED P3 — `_dt_column(nullable=False)` auto `now()`; 14 surrogate `id` PKs get `gen_random_uuid()`; `rehearsed_at` exception. verified by test `test_model_schema_parity` + share_link suite green |
| F13 | shared/db/models.py `_pg_enum` | **P1** | `KeyError: 'private'` — SQLAlchemy Enum maps by member NAME; lowercase-valued enums (profile_visibility/user_term_status/classroom_role) broke on read-back | full-DB suite: elo_commit + auth `KeyError: 'private'` | FIXED P3 — `_pg_enum` now uses `values_callable` (map on `.value`). verified by full suite green |

## Phase 1+3 verification (full-DB run, throwaway Postgres :55432)

- Baseline: 12 failed (all `'AsyncSession' has no .exec'` — F9 conftest).
- After F9 conftest fix: 10 failed. After F12+F13 model fixes: **154 passed, 1 failed, 9 skipped**.
- The 1 remaining failure = F7 (pre-existing fuzzy-grading, NOT conversion-caused) → Phase 8 quarantine.
- Shadow bugs F1-F4: proven fixed by `test_converted_delete_update_no_shadow.py` (4 pass).
- Model-schema parity: `test_model_schema_parity` passes — 0 structural drift (0 add/drop column, 0 add/drop table). Residual autogenerate ops are cosmetic (AutoString↔TEXT, non-load-bearing server_default text).
- `alembic/env.py` wired to `SQLModel.metadata` (was `None`); `--autogenerate` now functional.
- Ruff: 0 errors core + shared + worker.

## Caller trace (Phase 1 step 2)

- `term_notes_service`: caller `api/routes/me_extras.py:52-60` imports `delete as note_delete`, `get as note_get`, `upsert as note_upsert`. Public names used → fix (alias SQLAlchemy import) is caller-safe.
- `saved_search_service`, `definition_overrides_service`: no callers in `pycil_core/api` (wired elsewhere or pending). Public names unchanged → safe.
- `share_link_service`: `update` (l.56), `func` (l.62) used; `delete` dead.

## Fix decision

Alias the SQLAlchemy imports (`delete as sa_delete`, `update as sa_update`); update in-function call sites only. Public service function names (`delete`, `update`) unchanged → zero caller churn.

## Phase 2 — conversion parity audit

### F14 — `isinstance(row, tuple)` shape hack (red-team finding #3) — FIXED
4 sites: `user_service.py:48` (id→JWT sub), `:93` (token_version, auth-critical), `push_notification_service.py:51` (id), `term_status_service.py:62` (lapse_count).
**Empirical probe** (live PG, this SQLModel version) — decisive return-shape facts:
- `insert/update.returning(single_col)` → `.one()`/`.first()` returns a **`Row`** (e.g. `(UUID(...),)`), NOT a Python tuple, NOT a scalar. So `isinstance(row, tuple)` is **always False** → the `row[0]` branch was dead; it resolved via Row attr-access (`row.id`) which happens to work.
- `select(Model)` → `.first()` returns the model instance.
- `select(Model.col)` → `.first()` returns an **unwrapped scalar** (sqlmodel single-column special-case).
**Fix:** `.returning(col)` → use positional `row[0]` (deterministic for single-col Row); drop the always-False isinstance hedge. verified by full suite 154 pass + behavior-identical (probe proved old==new value).

### Verification note (operator error, NOT a code regression)
A transient "10 failed" run was traced to MY inline env export `ALLOWED_ORIGINS=http://t` (truncated from `http://test`). conftest uses `setdefault`, so my truncated export won → `client` fixture's `origin: http://test` failed the CSRF origin allowlist → 403 on all integration tests. Proven by stash-test (same tests fail on committed baseline w/ bad env) + clean-env rerun (`env -u ALLOWED_ORIGINS …` → integration 12 pass, full suite **154 pass / 1 pre-existing fail**). Lesson: do NOT override conftest env vars; let its `setdefault` defaults apply.

### F10 follow-up — residual `session.execute()` (deprecated)
`data_export_service.py:79`, conftest `test_user`/`second_user` fixtures (196/214) still use `session.execute(text(...))`. Works (SQLModel AsyncSession supports `.execute`), deprecation-warned only. Behavior-preserving holdout — acceptable, but audit remaining call sites for authz-clause parity below.

### IDOR / authz-predicate parity (security-critical) — CLEAN
Audited 30 converted `update()`/`delete()` statements old (`9f07149^`) vs new. **0 dropped tenancy predicates.** Every mutation either keeps its `user_id`/`created_by`/`author_id` WHERE or is gated upstream. Controller-verified the highest-risk claim: `node_service.update_node:173` + `delete_node:189` call `_ensure_owner(session, user_id, node_id)` before the id-only mutation → safe. Canonical shared tables (`terms`/`definitions`/`questions`/deck counters) were id-only in BOTH versions (no per-user predicate to lose). Report: `reports/from-explore-to-controller-phase2-idor-parity-audit.md`.

### Phase 4 follow-ups (flagged, not fixed here)
- `definition_comments_service.soft_delete`: old enforced admin via DB subquery; new takes a caller `is_admin` bool (default False, author-scoping intact). The route caller MUST verify admin server-side — unverified client `is_admin=True` would be IDOR. Audit route wiring in Phase 4.
- `set_primary` (definition_sense) + comment `soft_delete` have NO callers in this WIP checkpoint — statement parity verified, route authz not yet testable.

## Phase 4 - pycil-core bug hunt (CONFIRMED + fixed)

Severity: P1 = data/money/authz/runtime-break, P2 = correctness, P3 = robustness.

| ID | file:line | sev | claim | status |
|----|-----------|-----|-------|--------|
| C-scalar-1 | services/social_service.py:37 | P2 | `select(User.id)` from sqlalchemy under exec() returns Row; `existing_id != user_id` (Row != UUID) always True -> false 409 when a user re-saves their own username. FIX: import select from sqlmodel. | FIXED, verified by test test_claim_username_idempotent_for_self |
| C-scalar-2 | services/reverse_card_service.py:82 | P2 | single-col `select(Definition.canonical_meaning)` -> .all() yields Rows; distractor pool holds Rows not strings. FIX: import select from sqlmodel. | FIXED, verified by test test_reverse_prompts_distractors_are_strings |
| C-scalar-3 | api/routes/me_extras.py:99 | P2 | `select(User.id)` Row passed as followee_id UUID to toggle_follow. FIX: import select from sqlmodel. | FIXED |
| D2 | services/billing_service.py:86 | P3 | conversion dropped `updated_at = NOW()` from upsert_subscription DO UPDATE set clause (no ORM onupdate) -> updated_at frozen. FIX: set_ now includes func.now(). | FIXED, verified by test test_updated_at_advances_on_conflict_update |
| C1 | services/job_service.py:100-141 | P2 | fresh-job INSERT+commit sat outside orphan-cleanup except; commit failure leaks lock:generate_term for full 600s TTL -> term un-enrichable. FIX: wrap INSERTs+commit+enqueue in one try; rollback + delete lock on any failure. | FIXED, verified by test test_commit_failure_releases_lock |

Multi-column sqlalchemy.select sites (job_stream_service._load_owned_job, chat.py,
me_extras audit, billing) are SAFE: multi-col Row attr/_mapping access works under
exec() regardless of select import source. Only single-col-as-scalar sites were bugs.

### Phase 4 SUSPECTED / escalated (NOT fixed - behavior-preserving scope)
- D1 (P2): per-user LLM spend cap (user_spend_service) unwired + global-vs-per-user
  key mismatch -> non-functional. Likely v0.x scaffold; docstring misleading. ESCALATE.
- D3 (P3): admin_audit_service.record() zero callers; revoke_tokens writes no audit. ESCALATE.
- D4 (P3): per-user spend key local date.today() vs global UTC; latent until D1 wired.
- E1 (P1-if-routed): deck_search_service.search binds user_id but never uses it in
  WHERE (latent, no caller). ESCALATE before routing.
- E2/E3/E5 (P2-if-routed): classroom_service assign_deck no ownership check;
  list_assigned malformed join; join_with_code TOCTOU. classroom_service unrouted. ESCALATE.
- E4: definition_sense_service.set_primary mutates global primary sense, no authz; unrouted. ESCALATE.
- B1 (P2): learning elo_at_start snapshot not re-read at commit -> concurrent
  same-definition lost-update. Product scope call. ESCALATE.
- B2/B4 (P3): user-ELO vs constant 1000; realized_score always 1.0 from submit
  (monotonic ELO). Likely deliberate v1 simplification. ESCALATE.

## Phase 5 - worker bug hunt (CONFIRMED + fixed)

| ID | file:line | sev | claim | status |
|----|-----------|-----|-------|--------|
| W1 | worker/jobs/lifecycle.py:58-63 | P1 | sqlalchemy.select(Job.status) under exec() returns Row -> `row in (...)` always False -> is_terminal() always False -> retry-dedup gate defeated (re-runs paid side effects). Empirically probed (live PG): sqlalchemy.select(col).first()=Row; sqlmodel.select(col).first()=scalar. FIX: import select from sqlmodel. | FIXED, verified by test test_terminal_job_returns_duplicate |
| W3/W4 | worker/jobs/generate_question.py:93,65 | P2 | same scalarization: _existing_question_id Row, paraphrase/example samples Rows not strings. FIX: import select from sqlmodel. | FIXED, verified by generate_question suite |
| W7 | worker/jobs/generate_term.py:150 + onboarding_service.py:129 | P1 | ON CONFLICT (term_id) references constraint dropped by migration 0012 (replaced with UNIQUE(term_id, sense_index)) -> InvalidColumnReferenceError; crashes core enrichment + onboarding on every new term. Pre-existing, masked by never-green worker suite. FIX: ON CONFLICT (term_id, sense_index). | FIXED, verified by test test_generate_term_happy_path |
| W8 | translate_definition.py:100, tts_render.py:113 | P1 | to_jsonb(:param::text): text() bind parser ignores :param before :: -> PostgresSyntaxError; translate + TTS JSONB write-back crash 100%. Repo sweep: only these 2 sites. FIX: CAST(:param AS text). | FIXED, verified by test test_translate_happy_writes_jsonb + test_tts_happy_persists_url |
| W9 | worker/db.py (engine) | P2 | converted ORM .values(result=...) used default JSON serializer -> TypeError on UUID question_id (old mark_job used default=str). FIX: engine json_serializer=partial(json.dumps, default=str). | FIXED, verified by generate_question happy test |
| W10 | tests/conftest.py _bind_worker_session | P1(harness) | SessionLocal factory built plain SQLAlchemy AsyncSession (no .exec) vs runtime SQLModel AsyncSession -> why worker conversion shipped unverified. FIX: factory uses sqlmodel AsyncSession. | FIXED |

Stale-test drift (pre-existing, commit 53cf204): 3 test files patched
generate_with_schema (no longer imported; jobs call invoke_with_fallback).
Updated all monkeypatch sites to patch invoke_with_fallback + return FallbackResult.
New tests: tests/jobs/test_translate_tts_pipeline.py (9 tests, lifted 2 untested
conversion-touched job files from 40%/25% to gate-passing; suite 41 pass, cov 73.5%).

### Phase 5 SUSPECTED / no-action
- "never release lock in finally" (TTL-only) - intentional user-locked design, NOT a bug.
- W2/W5/W6 spend double-count on retry - SUSPECTED (depends on arq retry vs crash-retry);
  generate_term last_llm_response cache skips re-spend. Residual risk, not CONFIRMED.
- sanitize.py non-greedy <[^>]+> + http(s)-only URL match - pre-existing SUSPECTED-low,
  NOT conversion-introduced, NOT P1.

## Phase 8 - Ledger resolution (terminal status of every finding)

Protocol requires 0 dangling SUSPECTED. Disposition:

CONFIRMED-FIXED (proven by former-failing test, re-verified green):
  F1-F5, F9, F12, F13, F14 (phases 1-3); C-scalar-1/2/3, D2, C1 (phase 4);
  W1, W3/W4, W7, W8, W9, W10 (phase 5); PWA1, FE-lint, FE3, FE4, FE6 (phase 6).

PRE-EXISTING / QUARANTINED:
  F7 fuzzy-grading -> xfail(strict) with rationale; predates conversion;
  threshold re-tune is a separate grading-quality task (NOT this audit's scope).

REFUTED (with rationale, locked):
  auth core (exp/token_version/HS256/CSRF), IDOR parity (30 mutations clean),
  billing replay/out-of-order, redis.aclose pool, rate-limit EXPIRE,
  FE sign-out cache leak / open-redirect / EventSource leak / protected-route bypass.

ESCALATED (real, but out of behavior-preserving scope -> tracked in audit summary,
NOT silently changed):
  - CORE COVERAGE 48.57% < gate 70% (pre-existing; ~30 unwired scaffold services
    zero tests). User-confirmed 2026-05-29: document + escalate, do not change gate.
  - D1 per-user spend cap non-functional (unwired + key mismatch).
  - D3 admin_audit_service.record() unwired.
  - D4 per-user spend key TZ inconsistency (latent until D1 wired).
  - E1 deck_search_service missing user-scope (latent, unrouted).
  - E2/E3/E5 classroom_service ownership/join/TOCTOU (latent, unrouted).
  - E4 definition_sense_service.set_primary global mutate, no authz (unrouted).
  - B1 ELO elo_at_start snapshot lost-update; B2/B4 monotonic ELO / constant-1000
    difficulty (likely deliberate v1 simplification - product call).
  - FE1 expired-session-on-/api/core HTML-vs-401 (prod-proxy dependent).
  - FE2 useBroadcastSync dead code (intentional infra pending wiring).
  - npm audit: next/swiper/postcss advisories (need breaking major bumps).

NO DANGLING SUSPECTED: every finding above has a terminal status.

## Phase 8 - Final verification (DB-backed, throwaway PG :55432)
- core: 159 passed, 1 xfailed (F7), 9 skipped, 0 failed. ruff clean.
- worker: 41 passed, coverage 73.5% (>= 70 gate). ruff clean.
- web: tsc 0 errors, eslint 0 errors (3 hook-dep warnings), next build green, npm test 9 pass.
- Core coverage 48.57% < 70 gate: documented residual (pre-existing scaffold), gate unchanged.
- NOTE: run core + worker suites SEQUENTIALLY (shared session-scoped postgresql_proc
  fixture collides if parallel). CI matrix isolates them per-job.
