# Frontend Integration Guide

Pycil is a bearer-token API. A Next.js BFF stores tokens in encrypted,
`HttpOnly` `iron-session` cookies and forwards `Authorization: Bearer` only from
the server.

All product routes are under `/v1`. Core async routes return an opaque `taskId`:

| Flow | Routes |
| --- | --- |
| Dictionary | `GET /words/search?q=...`, `POST /word-generations` |
| Study | `POST /sessions`, `GET /sessions/{sessionId}/next`, `POST /answers` |
| Realtime | `GET /realtime/token` |

`POST /word-generations` accepts `{ "query": "example" }` and an optional
idempotency key. Its response is `{ "taskId": "..." }`. Pending question and
grading responses also identify their task. Connect to the returned
`{ token, expiresAt, sseUrl }` using Centrifugo SSE only, then subscribe to the
authorized opaque task IDs. Task snapshots are versioned and include `taskId`,
`kind`, `status`, `result`, and `errorCode`; do not poll task or response status.

Assistant streaming remains FastAPI SSE. Persist the latest event ID and resume
a run with `Last-Event-ID`; use the assistant run query endpoint for recovery.
