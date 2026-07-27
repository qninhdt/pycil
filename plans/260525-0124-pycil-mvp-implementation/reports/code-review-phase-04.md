# Code Review — Phase 4 (Question Generation, MCQ-only v1)

Reviewer: code-reviewer agent
Date: 2026-05-25
Scope: shared-py package, worker MCQ job, pycil-core question routes/service, web MCQ UI, docker context changes

## Overall Assessment

Architecture mostly clean and consistent with phase-3 patterns (Lua lock-or-get, sanitize-before-INSERT, terminal-attempt-only failure publish, role.md include + USER_TERM fences, vanilla Jinja2). Pydantic schema shape matches LLM contract; uniqueness validator wired correctly via `with_structured_output`.

However, there is a **load-bearing type mismatch** that breaks both the fetch and check endpoints at runtime: `questions.id` is `UUID` in the DB schema but the Python and TS layers all type it as `int`. Two `redis.publish` calls also crash on `uuid.UUID` because they omit `default=str`. Combined effect: the success path for MCQ generation is non-functional end-to-end despite the row being persisted correctly.

Acceptance criteria status:
- (1) Pydantic-conformant JSON: PASS (`MCQData` validators wired)
- (2) Cache hit on second fetch: PARTIAL (works at service layer; fails on serialization in worker on first success)
- (3) Exactly 4 options / one correct: PASS (schema enforces, prompt enforces)
- (4) UI renders MCQ + post-submit explanation: PASS (component logic correct, but the network round-trip is blocked by Critical-2)
- (5) BaseQuestion swap test: NOT VERIFIED (no test included)
- (6) Non-MCQ returns 400: PARTIAL — `check_answer` returns 400 for non-MCQ; the fetch endpoint has no `type` query param so cannot be exercised

---

## Critical Issues

### C1. `questions.id` type mismatch — UUID DB column vs `int` Python/TS

DB schema is authoritative:

- `apps/pycil-core/alembic/versions/0001_init.py:208` — `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`

But every consumer types it as `int`:

- `apps/pycil-core/pycil_core/schemas/question.py:11` — `class QuestionRead(BaseModel): id: int`
- `apps/pycil-core/pycil_core/api/routes/questions.py:37` — `question_id: int` path param on POST `/questions/{question_id}/check`
- `apps/pycil-core/pycil_core/services/question_service.py:65` — `QuestionRead(id=row.id, ...)` where `row.id` is `uuid.UUID`
- `apps/pycil-core/pycil_core/services/question_service.py:157` — `check_answer(... question_id: int, ...)`
- `apps/web/lib/types.ts:82` — `QuestionRead.id: number`
- `apps/web/components/multiple-choice-card.tsx:16` — `questionId: number`
- `apps/worker/worker/jobs/generate_question.py:88` — `_existing_question_id(...) -> int | None`
- `apps/worker/worker/jobs/generate_question.py:99` — return value is a `uuid.UUID` cast to the int type hint

Concrete failure modes:
- `GET /definitions/{id}/question` → cache hit → `_existing_question` builds `QuestionRead(id=<uuid.UUID>, ...)` → Pydantic `id: int` validation raises `ValidationError`. The route 500s on every cache hit. Acceptance criterion (2) fails.
- `POST /questions/{question_id}/check` with a real UUID → FastAPI path validation rejects with 422 because the param is `int`. The endpoint is unreachable.
- `apps/web` types pretend `id` is a number; `JSON.stringify` will pass through the UUID string, but every place that does `String(question.id)` or numeric ops gets the wrong shape.

Fix:
- Schema: `id: UUID` (`from uuid import UUID`) or `id: str`
- Routes: `question_id: UUID`
- Service signatures: `question_id: UUID`
- Worker: `_existing_question_id(...) -> UUID | None`; serialize via `str(...)` before JSON writes
- Web: `id: string` (and update prop types in `multiple-choice-card.tsx` / `question-renderer.tsx`)

### C2. `redis.publish` payloads contain `uuid.UUID` without `default=str` — success publish raises `TypeError`

`apps/worker/worker/jobs/generate_question.py:174-178` (cache-hit branch):
```python
await redis.publish(
    f"results:job_{job_id}",
    json.dumps({"status": "completed", "question_id": existing}),  # existing is uuid.UUID
)
```

`apps/worker/worker/jobs/generate_question.py:226-229` (success branch):
```python
await redis.publish(
    f"results:job_{job_id}",
    json.dumps({"status": "completed", **result}),  # result["question_id"] is uuid.UUID
)
```

Both omit `default=str`. With asyncpg the `RETURNING id` from a `UUID` column comes back as `uuid.UUID`, which is not JSON-serializable. Phase-3 `generate_term._publish_event` correctly uses `json.dumps(payload, default=str)` — phase 4 dropped that.

Failure mode after the success branch raises:
1. INSERT into `questions` already committed (line 225 `session.commit()`)
2. Publish raises `TypeError`
3. Caught by `except Exception`; rollback is a no-op; appends error event; flips `jobs.status='failed'` and commits
4. End state: a valid question row exists, but its job is stuck on `failed`. Subsequent requests cache-hit on the question row, but the cache-hit branch (line 174) ALSO crashes the same way → `jobs.status='failed'` again, nothing is published.

Fix: add `default=str` to both `json.dumps` calls (or stringify `question_id` before composing the dict).

### C3. `GET /jobs/{job_id}` rejects question generation jobs (403) — no polling path for the pending response

`apps/pycil-core/pycil_core/api/routes/jobs.py:21-30` enforces ownership through `user_term_jobs`. `question_service.get_or_generate` does not insert into `user_term_jobs` (it has no `term_id` to record), so the user that just received `{job_id, status: "pending"}` cannot poll that job.

Net effect on the polling flow: the only working signal is re-calling `GET /definitions/{id}/question` until it returns `status: "ready"`. The `job_id` field is dead weight.

Two acceptable fixes; either is fine:
1. Drop `job_id` from `QuestionFetchResponse` and document that callers re-poll the fetch endpoint.
2. Open a question-job ownership mechanism — e.g. a generic `user_jobs` ownership check that passes when the job's payload references a definition the user can access.

User explicitly flagged this as an item to audit; flagging as Critical because the contract advertised by the response body cannot be honored.

---

## Important

### I1. Stale lock returning a job in terminal state

`apps/pycil-core/pycil_core/services/question_service.py:96-103` — the lock TTL is 600s. If the original holder finished (success or fail) inside that window, the lock still holds the old `job_id`. A new caller hits `lock-or-get`, gets back the terminal job_id, returns `{job_id, status: "pending"}`. The caller's polling will never see a transition because nothing is going to run.

Mitigation that matches phase-3 semantics: after the eval, when `owner_job_id != new_job_id`, fetch `jobs.status` for that id and:
- if `pending`/`in_progress` → return as-is
- if `completed` and a question now exists → return cached question
- if `failed` → invalidate the lock (`SET` over it with the new id, conditional on still holding the old value) and re-enter the enqueue path

Note the same rescue applies on the cache-hit guard inside the worker (`generate_question.py:163`). Both layers should agree.

### I2. Cache-hit fallback when the worker job runs after the question was inserted

`apps/worker/worker/jobs/generate_question.py:163-179` checks `_existing_question_id` and if it returns non-`None`, marks job completed. Good. But the `result` it writes to `jobs.result` is `{"question_id": existing, "cached": True}` (line 172). `_mark_job` uses `json.dumps(result, default=str)` so the JSON write itself is fine. But the publish below it is the C2 bug.

Once C2 is fixed this whole branch is correct. Calling out only because it is the only place currently relying on `default=str` for the result write but not the publish.

### I3. `from typing import Any` unused in `question_service.py`

`apps/pycil-core/pycil_core/services/question_service.py:10` — imported, not referenced. Ruff `F401` will flag.

### I4. Redis pool churn on every fetch

`apps/pycil-core/pycil_core/services/question_service.py:126-149` — `create_pool` + `pool.close()` per request when the lock is acquired. This is consistent with phase-3 (`term_service` does the same on enqueue), so leaving as-is is defensible for v1; flagging because it inherits the same characteristic.

### I5. `MCQAnswerInput` is unused

`packages/shared-py/shared/questions/multiple_choice.py:35-38` defines `MCQAnswerInput` but the API uses `pycil_core.schemas.question.QuestionCheckRequest` (effectively the same shape). Either drop `MCQAnswerInput` or have the route reuse it. Currently it is dead code, easy to confuse future readers about which is canonical.

### I6. `notes[0]` as canonical_meaning is implicit

`apps/worker/worker/jobs/generate_question.py:76-77` — `notes = row.notes or []; canonical = notes[0] if notes else None`. Phase-3 `_persist_definition` writes canonical meaning at `notes[0]` deliberately, but neither file documents the convention. A schema migration that ever rewrites this ordering will silently drop the canonical meaning out of MCQ prompts. Add a code comment cross-referencing the producer.

---

## Minor

### M1. `data` JSONB read fallback is dead code in practice

`apps/pycil-core/pycil_core/services/question_service.py:58-63` and `:176-181` both branch on `isinstance(data, str)`. With asyncpg + SQLAlchemy `text()`, JSONB comes back as `dict`. Defensive fallback is fine; matches phase-3 jobs.py pattern.

### M2. `MCQData.options` uniqueness check is case- and whitespace-insensitive — by design

`packages/shared-py/shared/questions/multiple_choice.py:26-32` — normalizes via `strip().lower()` before set comparison. This is the right call for human-readable distractors but means LLM-generated `"Bank"` vs `"bank"` would be rejected. Worth a one-line comment so future contributors do not "fix" it.

### M3. Question fetch endpoint advertises a `type` parameter in the plan but the route ignores it

Phase doc step 4 mentions `type=MCQ` in the URL; the route at `apps/pycil-core/pycil_core/api/routes/questions.py:21-29` accepts only `difficulty`. Acceptance (6) ("Non-MCQ returns 400") cannot be exercised through this surface since the input space already excludes non-MCQ. Document the v1 narrowing in the route docstring or accept a `type` query and 400 for anything that isn't `MULTIPLE_CHOICE`.

### M4. Worker cost estimate hardcoded

`apps/worker/worker/jobs/generate_question.py:34` — `_ESTIMATED_COST_USD = 0.0003`. Different from phase-3's `0.0005`. Probably intentional (MCQ prompt is shorter). Consider centralizing both in `worker/config.py` so the daily budget caps remain meaningful when models change.

### M5. Acceptance test for `BaseQuestion` swap (criterion 5) not present

No `test_*.py` in the diff sets up a stub MCQ subclass and runs through the route. The ABC contract is narrow enough that this would be a 30-line test. Recommend adding before phase-5 starts depending on it.

---

## Regressions vs Phase 3

- jobs router (`jobs.py`): unchanged. Question generation jobs cannot be polled through it (see C3) — that's a contract gap, not a regression.
- terms route + `term-card`: unchanged.
- `generate_term`: unchanged.
- `generate_with_schema` is purely additive on `worker/llm/openrouter.py:46-52`. Existing `generate_term_payload` untouched.
- Public `jobs.payload` shape now also includes `{definition_id, difficulty, type}`. JSONB column has no schema, so this is forward-compatible.
- `questions` table columns used by INSERT (`definition_id`, `type`, `data`) match the alembic 0001_init definition; defaults supply `id`, `created_at`, `updated_at`. No DDL regression.

---

## Docker / Build Context

The compose context flip from `./apps/pycil-core` and `./apps/worker` to `.` is required to mount the `packages/shared-py` package, and matches the `COPY packages/shared-py /app/packages/shared-py` in both Dockerfiles. I did not find any path that referenced the old contexts (no `apps/pycil-core/Dockerfile.dev`, no GitHub Actions referencing the old paths inside this diff). Watch for:

- Build caches that previously layered on top of `apps/pycil-core` contents are invalidated. First build will be slower; that is expected.
- `.dockerignore` at the repo root is now load-bearing. If one does not exist, the build context will pull `plans/`, `.git/`, etc. into the daemon. Worth confirming a repo-root `.dockerignore` is present (out of diff scope).

`apps/web` build context remained `./apps/web` — correct, no shared-py dep there.

---

## Shared-py packaging

- `packages/shared-py/pyproject.toml` declares `pycil-shared` (project name) but the namespace is `shared`. The two consumers depend by project name `pycil-shared` and import via `shared.questions...` which is correct but worth a one-line note in `__init__.py` to spare future readers a grep.
- `[tool.uv.sources]` editable path entries are local-dev only; pip running inside the Dockerfile resolves the package from `pip install -e /app/packages/shared-py`. Both paths agree.

Lazy import of `MultipleChoiceQuestion` inside `check_answer` (`question_service.py:161`) works because the package is installed editable into the same site-packages as `pycil_core`. Confirmed via Dockerfile lines 22-23.

---

## MCQData details (user audit prompts)

- `distractor_rationale` length 3 vs `options` length 4: correct invariant — 4 options minus 1 correct = 3 wrongs; prompt at `apps/worker/prompts/mcq.md:13-14` instructs "in the same order as `options`, skipping the correct index". Schema enforces both bounds.
- Uniqueness validator on `options`: runs as a Pydantic `field_validator`. `with_structured_output(MCQData, method="json_mode")` runs Pydantic validation on the parsed JSON, so the validator fires on the LLM output — not just on hand-built instances. Verified via the LangChain `_runnable_to_pydantic` path.

---

## Edge cases worth a follow-up (not blocking)

- `generate_question` swallows any LLM error into the retry suffix once. If the second call also fails, the error reaches the outer `except` and follows the terminal-attempt logic. No infinite loop. Aligns with phase-3.
- `question_service.get_or_generate` does not check whether the user has access to the parent deck/term. Phase 3 jobs router enforces ownership via `user_term_jobs`. Question fetches are not gated. For v1 with no deck-sharing UI this may be acceptable, but flag for phase 5/6 because once a definition can be reached by URL, anyone authenticated can request its MCQ.
- `_load_inputs` always picks `paraphrase id ASC LIMIT 1` and `example id ASC LIMIT 1`. If phase-3's enrichment writes multiple paraphrases at varying CEFR, MCQ always sees the first inserted one — fine for v1, but the "difficulty" hint in the prompt becomes weaker.

---

## Recommended Actions (in order)

1. C1: change `questions.id` typing to UUID/`str` everywhere (schema, route, service signatures, worker return types, web types).
2. C2: add `default=str` (or pre-stringify `question_id`) to both `redis.publish` calls in `generate_question.py`.
3. C3: either drop `job_id` from `QuestionFetchResponse` (poll-only via the fetch endpoint) or extend the jobs route to allow ownership for question jobs.
4. I1: handle stale-lock-with-terminal-job in `get_or_generate`.
5. I3: remove unused `from typing import Any` import in `question_service.py`.
6. I5: drop or wire up `MCQAnswerInput`.
7. M5: add the BaseQuestion stub-swap test (acceptance criterion 5).

Items 1-3 are blocking for "phase 4 works end-to-end". Items 4-7 can land alongside phase 5 prep.

---

## Positive Observations

- Strict JSON prompt with role.md include + USER_TERM fences carries the phase-3 prompt-injection posture forward. `mcq.md` correctly warns that USER_TERM contents are data only.
- `MCQData` Pydantic validators enforce option count, index range, uniqueness, and rationale array length all at validation time, so a malformed LLM output never reaches the DB.
- `_invoke_llm` retry-with-stricter-suffix mirrors `generate_term._invoke_llm` exactly. Good consistency.
- Sanitization step (`_sanitize_mcq`) runs before INSERT, matching phase-3 `_persist_definition`.
- Terminal-attempt-only failure publish in `generate_question` correctly mirrors `generate_term` behavior.
- BaseQuestion ABC scope is narrow (`template_name`, `prompt_inputs`, `check_answer`) — easy v0.2 plug-in path is preserved without speculative generalization.

---

## Unresolved Questions

1. Is the question-fetch flow actually expected to surface `job_id` to the client (per the response schema), or is the field vestigial for future SSE wiring? If vestigial, drop it per C3 option 1; if not, the polling endpoint needs to accept question jobs.
2. Should `get_or_generate` enforce deck/visibility access on the parent definition before enqueuing? Phase plan does not specify; phase 5 may need it once decks can be shared.
3. Are MCQ option strings required to remain in original casing in the DB but uniqueness-checked in normalized form? The current implementation says yes (returns `v` not `normalized`), but no comment documents the intent.
