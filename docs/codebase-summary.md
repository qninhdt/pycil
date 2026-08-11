# Pycil Codebase Summary

**Stack:** FastAPI + SQLModel + Alembic (`apps/api`), arq (`apps/worker`),
Next.js 16 App Router + React 19 + Tailwind v4 (`apps/web`), shared Python
(`packages/shared-py`), and GitHub-pinned `lexi-ai` domain library (immutable
commit SHA).

`lexi_ai` is embedded, transport-free, and owns its `lexi` PostgreSQL schema.
Pycil application code uses the `ports/lexi_embedded.py` adapter and never
imports Lexi ORM models directly.

## Backend (`apps/api`)

| Area | Responsibility |
| --- | --- |
| `content/` | Search, opaque deck sense membership, embedded Lexi adapter. |
| `tasks/` | Durable task identity, interests, snapshots, and outbox delivery. |
| `learning/` | Session planning, round delivery, Lexi grading, and FSRS persistence. |
| `hierarchy/` | Folder/deck/reference tree, ownership scoping, visibility. |
| `realtime/` | Centrifugo SSE connection tokens and subscription authorization. |
| `assistant/` | Optional assistant with independent FastAPI SSE and HITL actions. |

`POST /v1/word-generations` returns an opaque `taskId`. Pending study grades and
question generation also return task IDs. Clients subscribe through SSE; the
owner-scoped `GET /v1/responses/{responseId}` read is the durable fallback for a
missed grading event, while generic task status has no REST endpoint.

## Frontend (`apps/web`)

A Next.js BFF: the browser never holds a bearer token. `proxy.ts`, `lib/auth/*`,
and the `app/api/*` route handlers seal tokens in an encrypted `HttpOnly`
iron-session cookie and forward `Authorization: Bearer` only from the server.

| Area | Responsibility |
| --- | --- |
| `app/(app)/` | Authenticated screens: Today, `library`, `library/[nodeId]`, `w/[senseId]`, `progress`, `settings`. |
| `app/(auth)/`, `app/study/` | Sign-in, and the chromeless study loop at `study/[sessionId]`. |
| `app/api/` | BFF route handlers (auth callback/login/logout, assistant message/confirm proxies). |
| `lib/api/` | Typed API client, generated error codes, and the wire error taxonomy. |
| `lib/actions/` | Server actions — the only place a bearer token is attached. |
| `lib/study/` | The pure session reducer, backoff schedule, and grade-snapshot projection. |
| `lib/assistant/` | The SSE frame reader and the event→turn transcript fold. |
| `lib/realtime/`, `lib/stores/` | Centrifugo provider, task-snapshot reconciliation, Zustand stores. |
| `lib/design/` | Mastery band→stage mapping, shared with the API's learning policy. |
| `components/` | Feature components by domain (study, vocabulary, library, progress, assistant, activity, command, dashboard, settings, shell) plus the `ui/` primitive registry. |

Design tokens are generated from the root `DESIGN.md` into
`app/tokens.generated.css` (`scripts/build-design-tokens.mjs`); both are
committed so `next build` needs no network. `scripts/design-system-audit.mjs`
gates ten mechanical design rules. Tests are three-layered: Vitest for pure
logic (`tests/unit/`), Storybook for component review, Playwright for E2E — see
[`testing-strategy.md`](./testing-strategy.md).

## Operations

Compose runs a one-shot migration gate that upgrades Lexi's `lexi` schema before
Pycil's public schema. `scripts/rehearse-fresh-schema.sh` verifies this against
empty Compose volumes. `scripts/deploy.sh` snapshots the shared Postgres
database, applies migrations, starts the worker before the API, and gates
readiness.
