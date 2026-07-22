# Pycil Codebase Summary

**Stack:** FastAPI + SQLModel + Alembic (`apps/api`), arq (`apps/worker`),
Next.js BFF/frontend (`apps/web`), shared Python (`packages/shared-py`), and
GitHub-pinned `lexi-ai` domain library (immutable commit SHA).

`lexi_ai` is embedded, transport-free, and owns its `lexi` PostgreSQL schema.
Pycil application code uses the `content/lexi_library.py` adapter and never
imports Lexi ORM models directly.

| Area | Responsibility |
| --- | --- |
| `content/` | Search, opaque deck sense membership, embedded Lexi adapter. |
| `jobs/` | Internal word-generation quota and worker fencing. |
| `tasks/` | Durable task identity, interests, snapshots, and outbox delivery. |
| `learning/` | Session delivery, Lexi grading, and FSRS persistence. |
| `realtime/` | Centrifugo SSE connection tokens and subscription authorization. |
| `assistant/` | Optional assistant with independent FastAPI SSE and HITL actions. |

`POST /v1/word-generations` returns an opaque `taskId`. Pending study grades and
question generation also return task IDs. Clients subscribe through SSE only;
there are no job or response status endpoints.

Compose runs a one-shot migration gate that upgrades Lexi's `lexi` schema before
Pycil's public schema. `scripts/rehearse-fresh-schema.sh` verifies this against
empty Compose volumes. `scripts/deploy.sh` snapshots the shared Postgres
database, applies migrations, starts the worker before the API, and gates
readiness.
