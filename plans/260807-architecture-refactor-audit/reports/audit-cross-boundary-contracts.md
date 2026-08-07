# Audit: Cross-Boundary Contracts

**Date:** 2026-08-07  
**Scope:** api↔worker, shared-py, pycil↔lexi-ai, realtime contract, in-flight git changes

---

## A. api ↔ worker

### Job contract: typed vs dict

All 4 `enqueue_job` call sites pass positional args, not typed payloads:

```
apps/api/pycil/learning/application/answering.py:393     pool.enqueue_job("grade_answer_task", task_id, owner_uid, response_id)
apps/api/pycil/learning/application/session_flow.py:274  pool.enqueue_job("generate_word_task", task_id, query, owner_id)
apps/api/pycil/content/router.py:112                     pool.enqueue_job("generate_word_task", ...)
apps/api/pycil/assistant/application/tools.py:243        pool.enqueue_job("generate_word_task", ...)
```

Handlers receive `ctx: dict` — no typed envelope. Signature on the handler side:

```
apps/worker/pycil_worker/jobs/grade_answer.py:124   async def grade_answer_task(ctx: dict, task_id: str, owner_uid: str, response_id: str)
apps/worker/pycil_worker/jobs/generate_word.py:18   async def generate_word_task(ctx: dict, task_id: str, query: str, owner_id: str | None)
```

Drift risk: positional order. Rename or reorder on one side → silent wrong-argument call at runtime. No test covers the API-side enqueue payload matching the worker-side signature. `reconcile_async_tasks` re-enqueues from the `dispatch` JSON stored in the task row (`dispatch["query"]`, `dispatch.get("owner_id")`) — so a field rename also silently breaks the reconciler path.

**Rating:** Medium risk. The task row stores the dispatch dict, so as long as both sides stay in sync with the dict keys, it survives a restart. But there is no compile-time check.

### Reconciler legitimacy

`reconcile_async_tasks` (apps/worker/pycil_worker/jobs/reconcile_async_tasks.py): repairs ARQ enqueue failures (the `except Exception: pass` on 4 call sites after a committed task row). Correct design — ARQ-in-Redis cannot join a Postgres transaction. Every committed task row without a matching ARQ key is safe to re-enqueue because jobs are idempotent.

`reconcile_pending_grades` (apps/worker/pycil_worker/jobs/reconcile_pending_grades.py): sweeps `Response` rows in `PENDING` grade status older than a lease window, re-enqueues `grade_answer_task` by `response_id`. This re-enqueue goes through `_converge_task_snapshot` on the worker (`grade_answer.py:59-99`) to re-find the task row by `work_key`. Two-step lookup is a seam — it exists because the reconciler enqueues by a different ID than the primary path. Root cause: the pending-grade reconciler was written before `grade_answer_task` (the task-aware version) existed; it still re-enqueues the legacy handler path `grade_answer_v1` (`grade_answer.py:119`) which then delegates. That delegation adds one DB round-trip per reconciled grade.

**Both reconcilers are legitimate safety nets, not patches over a broken primary path.** The `reconcile_pending_grades` seam is a cleanup opportunity, not a correctness issue.

### lexi schema writer invariant

README claims worker is "single writer to the lexi schema." Verified in pycil api code:

```
grep -r "lexi\." apps/api/pycil --include="*.py"
```

No api-side SQL writes to the `lexi` schema found. API only reads through `ports/lexi.py` (the Protocol port) or indirectly via `lexi_ai.contracts`. The invariant holds in code.

### Duplicated business logic

No FSRS/scheduling/scoring logic found in both api and worker. FSRS math lives exclusively in `packages/shared-py/shared/fsrs/`. Grading logic lives in `lexi_ai/questions/scoring.py` (called by the worker via `ctx["lexi_engine"]`). Clean.

---

## B. Shared code (packages/shared-py)

### Channel construction: NOT used by all consumers

`shared/realtime/channels.py` exports one function: `async_task(task_id) -> str` returning `f"async:{task_id}"`.

Web side constructs the channel string **inline, hardcoded**:

```
apps/web/lib/realtime/task-subscription.ts:  const channel = `async:${taskId}`
```

This is the only consumer that matters for the realtime path. The shared-py function is only imported by the api side (`ports/centrifugo.py` or realtime module). Result: the channel name format is defined twice — once in Python, once in TypeScript — with no test asserting they match.

**Risk:** Low today (single string `async:`), but a namespace change (e.g. adding a tenant prefix) must be made in two places. There is no codegen or contract test bridging them.

### FSRS/mastery: NOT duplicated in web

Web has its own mastery display logic in `lib/progress/` but it is presentation only — threshold display, color mapping. The scheduling math (interval computation, stability, retrievability) lives exclusively in `shared/fsrs/engine.py`. Web never re-implements FSRS. **This seam is fine as-is.**

### shared-py boundary assessment

Two unrelated concerns in one package: FSRS engine (domain math) + realtime wire format (infrastructure). They have no dependency on each other. Combining them in `pycil_shared` is a grab-bag. Not a problem today given the small size (315 LOC), but if either grows significantly they should be split into `pycil-fsrs` and `pycil-realtime`.

---

## C. pycil ↔ lexi-ai

### Actual consumed surface

Every `lexi_ai` import in pycil api + worker:

```
apps/api/pycil/ports/lexi.py                           lexi_ai.contracts (EntryView, SenseView, etc.)
apps/api/pycil/ports/lexi_embedded.py                  lexi_ai.Lexicon
apps/api/pycil/ports/lexi_provider.py                  lexi_ai.Lexicon
apps/api/pycil/learning/application/answering.py        lexi_ai.contracts.PresentedQuestion
apps/api/pycil/learning/application/question_delivery.py  lexi_ai.contracts.*
apps/api/pycil/learning/application/planning.py         lexi_ai.contracts.PrepareDemand
apps/api/pycil/learning/application/service.py          lexi_ai.contracts.*
apps/api/pycil/learning/domain/resolver.py              lexi_ai.contracts.PresentedQuestion
apps/api/pycil/learning/domain/grading.py               lexi_ai.contracts.*
apps/worker/pycil_worker/main.py                        lexi_ai.Lexicon
apps/worker/pycil_worker/lexi_library.py                lexi_ai.Lexicon
apps/worker/pycil_worker/jobs/generate_question.py      lexi_ai.contracts.PrepareDemand
```

**Port boundary violation:** `learning/domain/grading.py` and `learning/domain/resolver.py` import `lexi_ai.contracts` directly, bypassing `ports/lexi.py`. The learning *domain* depends on lexi-ai types. This ties the domain layer to an external library version — the whole reason `ports/lexi.py` exists.

**Correct path:** all lexi-ai types entering pycil should be imported via `pycil.ports.lexi` re-exports or via `lexi_ai.contracts` only in the application layer and outward. Domain importing an external package directly is a layering violation.

### Port completeness

`ports/lexi.py` defines a `Protocol` for read operations and has a boundary test + fake. This is good. The issue is that `lexi_ai.contracts` (the lexi-ai public data-transfer types — `PresentedQuestion`, `PrepareDemand`, etc.) are imported directly across 9 files without going through the port. The port controls *operations*; the *types* flow freely. This is partly acceptable (types are stable contracts), but `domain/grading.py` importing a lexi-ai type means any breaking lexi-ai contract change requires touching the pycil domain layer.

### Pin management

Pinned via git revision in pyproject.toml. A lexi-ai change requires: bump revision + run lexi-ai migration head + re-run pycil migrations that depend on the lexi schema. No automated check that the pinned revision's migration head matches what pycil expects. This is an operational risk, not a code smell.

### Schema isolation

`lexi` schema is owned by lexi-ai migrations (`lexi_ai/migrations/`). Pycil api schema is `public`. No cross-schema FK found in pycil's alembic versions. Isolation holds structurally.

---

## D. Realtime contract

### End-to-end trace (one async task event)

1. **Publish site (api):** `tasks/application/service.py:91-106` writes event row + outbox row in same transaction, calls `pg_notify("task_outbox", task_id)`. This is the only publish path.
2. **Worker LISTEN:** `pycil_worker/main.py:69-76` subscribes to `pg_notify("task_outbox")` on startup. Outbox dispatch job reads and sends to Centrifugo.
3. **Channel naming (api):** `ports/centrifugo.py` constructs channel via `shared.realtime.channels.async_task(task_id)` → `"async:{task_id}"`.
4. **Channel naming (web):** `lib/realtime/task-subscription.ts` hardcodes `` `async:${taskId}` ``. **Duplicate, unguarded.**
5. **Token/authz:** Centrifugo subscribe proxy validates token (HMAC). The api generates subscription tokens via `ports/centrifugo.py:sign_subscription_token` — but this function has **zero production callers** (only test callers). How tokens are actually issued to the browser is unclear from ports/centrifugo.py alone.
6. **Frame parsing (web):** `lib/realtime/task-snapshot.ts` defines `AsyncTaskSnapshot` interface + `isAsyncTaskSnapshot` guard. Fully typed but **hand-mirrored** from the Python `shared/realtime/payloads.py` definition. No codegen. If a field is added on the Python side, the TypeScript side silently ignores it.
7. **Store update:** `lib/stores/activity-store.ts:applySnapshot` updates task status from snapshot. Monotonic version guard prevents out-of-order updates.

### Wire format: Python vs TypeScript mirror

Python (`shared/realtime/payloads.py`):
```python
class AsyncTaskPayload:
    schema: str  # "async-task.v1"
    event_id: str
    task_id: str
    status: str
    ...
```

TypeScript (`lib/realtime/task-snapshot.ts`):
```typescript
interface AsyncTaskSnapshot {
  schema: "async-task.v1";
  eventId: string;
  taskId: string;
  status: ...;
}
```

The Python fields use `snake_case` and TypeScript uses `camelCase` — the api serialises with `by_alias=True`, so Pydantic aliases do the mapping. The aliases must match the TS field names exactly. No test covers the mapping end-to-end. A Pydantic alias rename silently breaks the web subscription.

### `unsubscribe_channel` dead function

`ports/centrifugo.py:unsubscribe_channel` — confirmed zero production callers. Test-only. Delete.

---

## In-flight git changes (41 dirty files)

Running `git diff --stat HEAD` shows 1121 deletions / 274 insertions, primarily:

- **`apps/api/pycil/jobs/`** (4 files deleted: `__init__.py`, `models.py`, `schemas.py`, `service.py` — 370 LOC deleted). Old jobs module replaced by `tasks/`. Migration to tasks/ appears complete on the api side.
- **`apps/worker/pycil_worker/jobs/reconcile_queued_word_generations.py`** deleted. The reconciler that repaired the old `word_generations` table (now dropped per migration `0025_drop_word_generations.py`).
- **`apps/worker/pycil_worker/realtime.py`** deleted (23 LOC). Replaced by shared-py `channels.py`.
- **`apps/api/pycil/ports/centrifugo.py`** modified (-28 lines). Likely removing `unsubscribe_channel` and the old sign function.
- **`packages/shared-py/shared/realtime/channels.py`** modified (-10 lines). Trimmed.
- **`apps/worker/pycil_worker/jobs/generate_word.py`** heavily simplified (-115 of original LOC): quota logic moved out into `apps/api/pycil/content/application/generation_quota.py` (new untracked file).

**Half-migrated item:** `apps/api/tests/jobs/test_word_generation_jobs.py` deleted but `apps/api/tests/content/test_word_search_auth_boundary.py` (new, untracked) exists. The test migration appears complete but not committed — both old and new tests are absent from git HEAD simultaneously, meaning the test suite is currently weaker than either state.

**Action required before any refactor phase:** commit or squash the in-flight changes. A refactor on top of an uncommitted half-migration creates merge conflicts that obscure which change caused a regression.

---

## Prioritized findings & proposals

| # | Finding | Severity | Proposed fix | Size | Risk | Cross-repo? |
|---|---------|----------|-------------|------|------|-------------|
| C1 | `learning/domain` imports `lexi_ai.contracts` directly | High | Move lexi-ai type re-exports to `ports/lexi.py`; domain uses port types only | S | Low | No |
| D1 | Channel name duplicated: Python vs TS | Medium | Codegen `shared/realtime/channels.py` to `lib/realtime/channels.generated.ts` at build time | S | Low | No |
| D2 | Realtime wire format not tested end-to-end | Medium | Contract test: Python serialise → TS deserialise for `AsyncTaskPayload` | S | Low | No |
| A1 | Job payloads untyped positional args | Medium | Define typed `@dataclass` payload per job, store in `dispatch` field of task row | M | Low | No |
| A2 | `reconcile_pending_grades` → two-path re-enqueue | Low | Unify: reconciler enqueues `grade_answer_task` (task-id path) only | S | Low | No |
| D3 | `unsubscribe_channel` dead code | Low | Delete `ports/centrifugo.py:unsubscribe_channel` | XS | None | No |
| B1 | `shared-py` two unrelated concerns | Low | Split `pycil-fsrs` / `pycil-realtime` when either exceeds 500 LOC | - | Low | No |
| GIT | In-flight changes uncommitted | Blocker | Commit working tree before any refactor phase begins | - | - | No |

---

## Unresolved questions

1. How are Centrifugo subscription tokens actually issued to the browser? `sign_subscription_token` has zero production callers — is there a separate path not visible in these files?
2. The `dispatch` JSON field in `AsyncTask` stores job args for reconciler re-enqueue. If job args evolve (new field added), old task rows have the old shape. Is there a migration strategy for the dispatch field, or is it considered ephemeral?
3. Should `lexi_ai.contracts` types be re-exported from `ports/lexi.py` (making the port the single import point for everything lexi-related), or is a direct import of a stable public contracts package acceptable in the application layer?
