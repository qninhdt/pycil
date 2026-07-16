# FSRS Learning Engine — Current Python Contract

**Status:** Implemented core; workflow hardening in progress

**Updated:** 2026-07-16

**Scope:** FSRS-4.5 scheduling, question selection, session delivery, and hybrid grading.

## 1. Canonical boundaries

- Pycil is Python: FastAPI/SQLModel in `apps/api`, arq in `apps/worker`, and
  shared FSRS/realtime code in `packages/shared-py`.
- The learnable unit is an opaque lexi-ai `sense_id`, not a term or legacy
  definition identifier.
- Pycil owns users, hierarchy, deck membership, scheduling state, attempts,
  responses, and review history in PostgreSQL.
- Lexi-ai owns dictionary content, questions, and grading helpers in its own
  database. All access crosses the `LexiClient` port; Pycil never joins or
  copies lexi tables.
- Redis stores restartable session orchestration only. Durable learning effects
  belong in PostgreSQL.

## 2. FSRS state and grading map

Each `(user_id, sense_id)` row stores stability, difficulty, mastery `0..100`,
review dates, interval, counters, and status. Retrievability is derived at read
time and is never persisted.

Pycil maps authoritative binary verdicts to FSRS grades:

| Verdict | FSRS grade |
|---|---:|
| Incorrect | Again (1) |
| Correct | Good (3) |

Hard and Easy are intentionally unused because clients provide neither
self-rating nor trustworthy response-time evidence. The shared package owns the
FSRS-4.5 formulas and golden vectors; application services must not fork them.

Displayed mastery is derived from stability:

```text
mastery = round(100 * S / (S + 30))
```

Average mastery is computed over learned senses only. The server owns the
mastered threshold, default `80`; clients cannot override it.

## 3. Session contract

Any accessible `FOLDER`, `DECK`, or `REFERENCE` is studyable through one
canonical, distinct subtree sense set. Buried senses are excluded.

`POST /sessions` creates a high-entropy owner-bound session and returns:

- `sessionId`
- `queueSize`
- expiry metadata
- the initial delivery state

Redis holds the immutable scope generation, ordered sense queue, cursor, and
current issued-question state. Repeated `GET /sessions/{id}/next` is retry-safe
and returns one discriminator:

| State | Meaning |
|---|---|
| `ready` | An authoritative, sanitized question is issued. |
| `pending` | Correlated question generation is in progress. |
| `exhausted` | No queue item remains. |

The cursor advances atomically only after a question binding is established.
Expired or evicted sessions fail closed and may be restarted.

The default mix is 2 new senses per 10 reviews. A single-deck session may use
that deck's settings; mixed folder/reference sessions use the server default.

## 4. Question selection and payload safety

Mastery defines a hard format cap: easier formats may be selected, harder ones
may not. `choose_format()` is part of production delivery rather than a DTO-only
helper.

Ready payloads contain `questionId`, `senseId`, `recommendedType`, and a
deny-by-default sanitized `payload`. Answer keys, rubrics, canonical completions,
or other grading material never leave the API.

Missing `contextual_mcq` content creates a deduplicated asynchronous generation
job correlated to the session issue. Generation topology does not determine
grading topology.

## 5. Answer and grading lifecycle

`POST /answers` accepts only an issued session/question binding, a bounded raw
answer, and a client idempotency key. The server verifies owner, live subtree
generation, queued sense, and authoritative question before any learning write.

Grading topology:

| Question format | Grading path |
|---|---|
| `definition_mcq` | synchronous lexi rule helper |
| `cloze` | synchronous lexi rule helper |
| `contextual_mcq` | synchronous lexi rule helper |
| `use_in_sentence` | durable pending response + arq LLM rubric job |

Both paths create a durable response and converge on one atomic verdict
application function. A separate unique `(user, session, sense)` attempt claim
ensures only the first attempt mutates FSRS and appends one review log. Further
responses remain recordable without a second scheduling mutation.

`POST /answers` always returns `responseId` and `gradeStatus`. Pending responses
omit unresolved verdict fields. `GET /responses/{id}` is owner-scoped and is the
recovery path when realtime delivery is missed.

## 6. Async durability and privacy

Pending response rows are the durable outbox. Enqueue is deterministic and
best-effort; a stale-pending reconciler repairs lost enqueue operations. Workers
claim leases with fencing before external grading and apply terminal results
idempotently. No database transaction is held across an LLM request.

Raw free-text answers are size-limited, encrypted at rest through the storage
deployment, redacted from logs, cleared on terminal grading, and purged after 24
hours if abandoned. Per-user quotas and rate limits bound generation/grading
cost.

## 7. Queue ordering

All active learned senses are ordered by increasing FSRS retrievability; overdue
items naturally come first while upcoming items remain eligible. New senses are
mixed using the configured ratio. Early review needs no custom penalty because
FSRS produces little stability growth when retrievability is already high.

## 8. Accepted trade-offs and rejected alternatives

- A correct MCQ guess still maps to Good; binary grading cannot infer guessing.
- Shared FSRS parameters are retained; per-user fitting is out of scope.
- No IRT/3PL, ELO layer, embedding graph, response-time model, or continuous
  score is introduced.
- `review_log` is retained for truthful history and auditability; it is not a
  replay engine for per-user parameter fitting.
- Redis-only durable attempts and all-PostgreSQL session orchestration were
  rejected: the chosen split keeps orchestration cheap and learning effects
  recoverable.

## 9. Validation obligations

- Shared FSRS golden vectors remain green.
- Concurrent first answers produce one scheduling mutation and one review log.
- Sync and async grading yield the same response/verdict contract.
- Unknown, unissued, wrong-owner, expired, stale-scope, and answer-key-leaking
  requests fail without changing learning state.
- Worker retries, lease expiry, lost enqueue, missed realtime, and polling are
  covered by integration tests.

## 10. Deferred work

Per-user FSRS parameter fitting, non-binary grades, L2 analytics infrastructure,
and alternate mastery curves require separate measured evidence and plans.
