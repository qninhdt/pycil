# Frontend Integration Guide

Pycil is a bearer-token API. The Next.js BFF in `apps/web` stores tokens in
encrypted, `HttpOnly` `iron-session` cookies and forwards `Authorization: Bearer`
only from the server; a bearer token never reaches the browser.

All product routes are under `/v1`.

## Route map

| Flow | Routes |
| --- | --- |
| Dictionary | `GET /words/search?q=...`, `GET /senses/{senseId}`, `POST /word-generations` |
| Hierarchy | `GET/POST /nodes`, `GET/PATCH/DELETE /nodes/{id}`, `POST /nodes/{id}/move`, `PATCH /nodes/{id}/visibility`, deck item add/remove |
| Study | `POST /sessions`, `GET /sessions/{sessionId}`, `GET /sessions/{sessionId}/next`, `POST /answers` |
| Progress | `GET /me`, `GET /capabilities`, `GET /me/history`, `GET /me/cefr`, `GET /me/weakest` |
| Settings | `GET/PUT /me/learning-settings` |
| Realtime | `GET /realtime/token` |
| Assistant | `POST /assistant/threads`, `GET /assistant/threads/{id}/messages`, `POST .../messages` (SSE), `POST .../actions/{id}/confirm` |

## The study delivery model

Study is not a cacheable read loop. Two contracts matter.

**`GET /sessions/{id}/next` mutates session state.** It is not idempotent and
must never be cached or prefetched: each call advances the round store, consuming
a delivery claim. It returns one of **five** states:

- `ready` — a question to render, discriminated by `renderFormat` (below) and
  carrying `questionId`, `senseId`, `requestedLevel`, `servedLevel`, and
  `isFallback`. A `null` `questionId` is an **exposure** card: it is not
  answerable, so there is no submit control, only "next".
- `break` — the round is full; `roundIndex` names the round being **entered**.
  Continuing calls `/next` again (a mutation, so the control disables in flight).
- `preparing` — questions are still being generated; poll again with backoff, do
  not resubmit anything.
- `waiting` — a grade is outstanding and must settle before the next question;
  poll again.
- `exhausted` — nothing left to study; show the recap.

The client polls `preparing`/`waiting` on a bounded, growing backoff and stalls
(offering to keep waiting) once the budget is spent, rather than hammering a
mutating endpoint.

**`POST /answers` takes only a question id and an answer string.** It carries no
correctness signal because the server refetches the authoritative question from
Lexi and grades against it — the answer key never enters the client. The four
render formats are:

- `flashcard` — exposure only, no answer.
- `single_choice` — MCQ; payload options carry no correct-answer marker.
- `text_span` — cloze answered from a fixed word bank.
- `free_text` — open answer, the only format graded asynchronously.

## Grading, in two modes

- **Synchronous.** Rule-graded formats (`single_choice`, `text_span`) settle in
  the `/answers` response with the verdict, the reveal, and the mastery
  transition inline.
- **Asynchronous.** `free_text` returns `gradeStatus: "pending"` and a `taskId`.
  The verdict arrives later as a task snapshot over SSE. The task id is durable,
  so a reload re-subscribes and the replayed snapshot rebuilds the same verdict.

## Task settlement is SSE-plus-recovery, not polling

Async word generation, question preparation, and free-text grades all identify
their work with an opaque `taskId`. Connect to the `GET /realtime/token`
response (`{ token, expiresAt, sseUrl }`) using **Centrifugo SSE only**, then
subscribe to the authorized task IDs. Snapshots are versioned and carry `taskId`,
`kind`, `status`, `result`, and `errorCode`; reconciliation is monotonic
(a lower version or a repeated event id never regresses state).

Recovery is built in and does **not** require polling: the subscribe proxy
replays the latest persisted snapshot on every subscribe, and the server's
outbox relay plus `force_recovery` settle a task even if the original enqueue was
dropped or the socket blipped. A disconnect with work outstanding is stated to
the learner but is not treated as a lost update. `stale` is reserved for a
re-subscribe that was actually **denied**, not for an ordinary disconnect.

## Assistant streaming

The assistant is FastAPI SSE (not Centrifugo). Posting a message opens a stream
of run events; a durable human-approval pause (`confirmation_required`) gates the
sensitive tools (`move_node`, `publish_node`, `delete_node`,
`remove_sense_from_deck`), and posting the decision opens a **new** stream that
continues the same run.

There is no live-run resume. The API cannot reattach to an interrupted generator:
`GET .../messages` and the run query endpoint both replay *persisted* rows and
then close, and a mid-stream disconnect raises `GeneratorExit` (a
`BaseException`) that escapes the run's `except Exception` handlers, leaving the
run `RUNNING` with its work abandoned. So a dropped stream offers exactly two
truthful choices — re-read what the server persisted, or send the turn again as a
new run. There is no `Last-Event-ID` resume; that criterion was removed as
unimplementable against this transport.
