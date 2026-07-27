# Phase 5 - Worker Adversarial Bug Hunt Report

Scope: apps/worker/worker (jobs, db.py, lifecycle, sanitize, llm, schemas) + tests.
Method: domain agent sweep + controller adjudication; every CONFIRMED bug proven
by empirical probe or failing test, then fixed and re-verified green.

## Baseline

Before fixes: worker suite = 6 failed + 7 errors (all collection/setup errors).
Root: stale tests patched a symbol the job no longer imports, masking that the
suite NEVER ran green -> the SQLModel conversion shipped unverified.

After fixes: 41 passed, coverage 73.5% (gate 70%), ruff clean.

## CONFIRMED bugs fixed

### W1 (P1) - is_terminal() always False; idempotency gate defeated
- File: worker/jobs/lifecycle.py:58-63
- Cause: `from sqlalchemy import select` passed to SQLModel `session.exec()`.
  SQLModel only auto-scalarizes a `sqlmodel.select`. A `sqlalchemy.select(col)`
  returns a Row, so `select(Job.status).first()` returns `('completed',)`, and
  `Row in ("completed","failed")` is ALWAYS False.
- Empirical probe (live PG, this SQLModel version):
  - sqlalchemy.select(col).first() -> Row ('completed',), in-tuple test False
  - sqlmodel.select(col).first()   -> scalar 'completed', in-tuple test True
  - both multi-col selects -> Row with attr access working
- Pre-conversion used `row.status in (...)` (raw Row attr) which worked.
  Conversion regression.
- Impact: generate_question / translate_definition / tts_render retry-dedup
  gate never short-circuits -> re-runs paid side effects on every arq retry.
- Fix: import `select` from sqlmodel in lifecycle.py.
- verified by test test_terminal_job_returns_duplicate + translate/tts duplicate tests.

### W3/W4 (P2) - generate_question single-col selects return Row not scalar
- File: worker/jobs/generate_question.py:93-106, 65-72/88-89
- Same root cause as W1. `_existing_question_id` returned a Row (cache-hit
  result dict carried a Row question_id); paraphrase/example samples were Rows
  not strings -> garbage in MCQ prompt + JSONB-serialize problems.
- Fix: import `select` from sqlmodel in generate_question.py.
- verified by test test_generate_question_happy_inserts_row, _cache_hit, _sanitize.

### W7 (P1) - ON CONFLICT (term_id) references a dropped constraint
- Files: worker/jobs/generate_term.py:150, pycil-core onboarding_service.py:129
- Migration 0012_multi_sense_definitions DROPS UNIQUE(term_id) on definitions
  and replaces it with UNIQUE(term_id, sense_index). Both code sites still do
  `ON CONFLICT (term_id) DO UPDATE` -> at schema head this raises
  InvalidColumnReferenceError "no unique or exclusion constraint matching the
  ON CONFLICT specification". Crashes core term-enrichment AND new-user
  onboarding on EVERY new term. Pre-existing (raw SQL, not conversion), masked
  because the worker suite never ran green.
- Fix: ON CONFLICT (term_id, sense_index) (both inserts default sense_index=0,
  behavior-preserving for the single-sense case).
- verified by test test_generate_term_happy_path + onboarding still green.

### W8 (P1) - to_jsonb(:param::text) bind param silently dropped
- Files: worker/jobs/translate_definition.py:100, tts_render.py:113
- SQLAlchemy text() bind-param parser treats `:val` immediately followed by
  `::` as NOT a parameter (reads `::` as a cast op) -> param never bound ->
  PostgresSyntaxError "syntax error at or near :". The translate and TTS JSONB
  write-back paths crash 100% of the time. Caught by NEW tests I added.
- Repo sweep for `:param::type` pattern -> only these 2 sites.
- Fix: to_jsonb(CAST(:val AS text)) / CAST(:url AS text).
- verified by test test_translate_happy_writes_jsonb, test_tts_happy_persists_url.

### W9 (P2) - UUID not JSON serializable on job result write
- File: worker/db.py (engine), surfaced via lifecycle.mark_job
- Old mark_job used json.dumps(result, default=str). The converted ORM
  `.values(result=result)` relies on the engine default JSON serializer which
  raises TypeError on a UUID question_id.
- Fix: create_async_engine(..., json_serializer=partial(json.dumps, default=str))
  in worker/db.py (runtime) + test engine in conftest. Matches old default=str.
- verified by test test_generate_question_happy_inserts_row.

### W10 (P1, test harness) - test session lacked .exec()
- File: apps/worker/tests/conftest.py:_bind_worker_session
- Same class as core F9: the SessionLocal factory built plain SQLAlchemy
  AsyncSession (no .exec), while runtime worker/db.py uses SQLModel AsyncSession.
  This is WHY the worker conversion shipped unverified.
- Fix: factory now builds sqlmodel.ext.asyncio.session.AsyncSession.

## Stale-test drift fixed (pre-existing, not conversion)
- 3 test files patched `worker.jobs.<mod>.generate_with_schema` (no longer
  imported; jobs call invoke_with_fallback since commit 53cf204). Updated all
  monkeypatch sites to patch invoke_with_fallback and return FallbackResult.

## New tests added
- tests/jobs/test_translate_tts_pipeline.py - 9 tests covering the two
  previously-untested (40%/25% cov) conversion-touched job files: happy,
  not-found, is_terminal duplicate, not-configured, synth/upload failure.

## REFUTED / no-action
- "never release lock in finally" (TTL-only) - intentional user-locked design;
  not a bug. Not touched.
- Publish-before-commit - all success paths publish strictly after commit.
- Sanitization weakening - sanitize.py untouched by conversion; fence strips
  HTML before prompt build. (Pre-existing non-greedy <[^>]+> regex + http(s)-only
  URL match are SUSPECTED-low pre-existing gaps, NOT conversion-introduced.)
- W2/W5/W6 spend double-count on retry - SUSPECTED (depends on arq retry vs
  crash-retry semantics); generate_term has last_llm_response cache that skips
  re-spend on retry. Logged as residual risk; not a CONFIRMED defect.
