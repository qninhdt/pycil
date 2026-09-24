> Current architecture authority: [`../pycil-redesign/`](../pycil-redesign/README.md).

# Pycil Codebase Summary

| Area | Responsibility |
|---|---|
| `apps/api` | FastAPI routes, Clerk verification, hierarchy, learning, account, inline AG-UI assistant, and content-job publication |
| `apps/worker` | The two Taskiq content jobs, question supply and word generation, plus the heartbeat loop |
| `apps/web` | Next.js UI, generated API client, bearer transport, job polling, and assistant-ui chat |
| `pycil-redesign` | Product and technical design authority; each document records where it diverges from the code |
| `scripts` | Deployment, backup/restore, schema rehearsal, OpenAPI generation |
| `infra/backup` | The current `pg_dump` + restic backup image |

`packages/` holds only `zod`; the former `shared-py` package is retired and the
worker imports its contract from `apps/api/pycil/queue/contracts.py`.

## Runtime boundaries

- PostgreSQL is canonical and contains the public, isolated Lexi, and assistant
  checkpointer schemas. `apps/api/pycil/db/models.py` is the one aggregator Alembic
  reads.
- Redis holds disposable study-session state, caches, coordination, the worker
  heartbeat, and the content-job receipts. A receipt has a 24-hour TTL and **is**
  the only record of an in-flight content job, so a Redis loss loses that work —
  the learner's retry recovers it, and graded learning never depends on a job.
- Lexi is accessed only through `apps/api/pycil/ports/`; Pycil stores opaque
  sense IDs and never queries Lexi tables directly.
- Caddy is the only public edge. The web app calls FastAPI directly with a Clerk
  bearer token; no BFF, realtime gateway, or token-custody layer remains.

Use the execution plan under `plans/260924-0608-pycil-complete-redesign/` for
stateful delivery evidence; do not copy its phase status into evergreen docs.
