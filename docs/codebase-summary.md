> Current architecture authority: [`./design/`](./design/README.md).

# Pycil Codebase Summary

| Area | Responsibility |
|---|---|
| `apps/api` | FastAPI composition plus account, billing, library, lexicon, study, assistant, and job contexts |
| `apps/api/pycil/worker` | Taskiq content jobs and the worker heartbeat; runs as a separate process from the API |
| `apps/web` | Next.js UI, generated API client, bearer transport, job polling, and assistant-ui chat |
| `docs/design` | Product and technical design authority; each document records where it diverges from the code |
| `scripts` | Deployment, backup/restore, schema rehearsal, OpenAPI generation |
| `infra` | Infrastructure configurations, Postgres WAL-G, deploy rehearsal, Caddy edge |

`packages/` holds only `zod`; the former `shared-py` package is retired and the
worker imports its contract from `apps/api/pycil/jobs/contracts.py`.

## API contexts

| Package | Owns |
|---|---|
| `platform` | Environment settings, product configuration, database, Redis, HTTP errors/middleware, and telemetry |
| `account` | Clerk identity mapping, authenticated profile, export, and deletion |
| `billing` | Plans, periods, allowance admission, and idempotent usage settlement |
| `library` | Folders, decks, references, access, deck membership, cache, and scoped analytics |
| `lexicon` | Lexi contracts/adapters, word search, sense detail, and word generation |
| `study` | Durable learning engine and disposable study-session workflow |
| `assistant` | Threads, agent runtime, turn streaming, approval, metering, and settlement |
| `jobs` | Task contracts, receipts, broker configuration, deduplication, and owner-scoped status |

The folders follow business ownership. HTTP files compose focused use cases;
there are no `domain/application/infra` layers or catch-all `service.py` modules.

## Runtime boundaries

- PostgreSQL is canonical and contains the public, isolated Lexi, and assistant
  checkpointer schemas. `apps/api/pycil/metadata.py` is the composition-only aggregator Alembic
  reads.
- Redis holds disposable study-session state, caches, coordination, the worker
  heartbeat, and the content-job receipts. A receipt has a 24-hour TTL and **is**
  the only record of an in-flight content job, so a Redis loss loses that work —
  the learner's retry recovers it, and graded learning never depends on a job.
- Lexi is accessed through `apps/api/pycil/lexicon/contracts.py`; Pycil stores opaque
  sense IDs and never queries Lexi tables directly.
- Caddy is the only public edge. The web app calls FastAPI directly with a Clerk
  bearer token; no BFF, realtime gateway, or token-custody layer remains.

Use the execution plan under `plans/260924-0608-pycil-complete-redesign/` for
stateful delivery evidence; do not copy its phase status into evergreen docs.
