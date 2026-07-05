---
phase: 11
title: "Integration Wiring"
status: complete
priority: P1
effort: "1d"
dependencies: [3, 5, 6, 7, 8, 9]
---

# Phase 11: Integration Wiring

## Overview
Wire all domains into the FastAPI app + worker: mount routers, inject the `LexiClient` port, connect the review→Centrifugo chain, add an explicit migration gate before services start, run `lexi.init()` at startup, and remove the retired Go/dead surfaces.

## Requirements
- Functional: full request path works end-to-end (auth → deck → generate → session → answer → live update); migrations applied before api/worker consume.
- Non-functional: single app factory; dependency injection for session/redis/lexi/centrifugo; no dead Go artifacts left.

## Architecture
`main.py` mounts routers from every domain, builds shared singletons (DB session factory, Redis/arq pool, `InProcessLexiClient`, Centrifugo client) and injects them via FastAPI dependencies. **An explicit migrate step (`alembic upgrade head`) runs as a one-shot compose service / init step that api + worker `depends_on` — a healthy Postgres is not a migrated Postgres.** `await lexicon.init()` runs once at startup (idempotent) so lexi's own DB schema exists. The review flow (Phase 6) publishes to Centrifugo after commit; no L2 cache to bust (L1-only, Phase 7). No partition/snapshot cron (plain `review_log`, Phase 2).

## Related Code Files
- Modify: `apps/api/pycil/main.py` (mount routers, wire deps, `lexi.init()` on startup), `apps/api/pycil/config.py`
- Modify: `docker-compose.yml` (add `migrate` one-shot service; api+worker `depends_on: migrate: service_completed_successfully`)
- Modify: `apps/api/pycil/learning/service.py` (publish on answer — no cache bust)
- Delete: `apps/api/cmd/`, `apps/api/internal/`, `apps/api/ent/`, Go Dockerfile/atlas, `packages/shared-py/shared/questions/*`, retired worker modules
- Reference (read-only): all prior phase files; `docker-compose.yml:124` (current `depends_on` healthcheck pattern)

## Implementation Steps
1. `main.py`: mount auth, content, hierarchy, learning, realtime, worker_bridge routers; wire dependencies (get_session, get_redis, get_lexi, get_centrifugo); call `await lexicon.init()` at startup.
2. Dependency providers: construct singletons at startup; `get_lexi` returns `InProcessLexiClient` (swap point for gRPC later). API is read/enqueue only — generation runs in worker (single writer).
3. Migration gate: add a `migrate` one-shot service to compose running `alembic upgrade head`; api + worker `depends_on: migrate: condition: service_completed_successfully`. No worker job runs against an unmigrated DB.
4. Learning answer flow: after FSRS update + review_log insert + verdict persist (Phase 6), publish `users:{uid}:grading:{response_id}` / `users:{uid}`. NO cache bust (L1-only). NO partition/snapshot cron.
5. Remove retired Go dirs + dead Python (questions plugins, tts/translate jobs, prompts/llm/schemas in worker).
6. End-to-end manual run: sign in → create deck → generate word → add sense → start session → answer → mastery updates + live push.
7. Verify no import of removed modules; `ruff` clean; app boots after migrate gate.

## Success Criteria
- [ ] App factory mounts all domain routers with injected deps
- [ ] `get_lexi` dependency returns the port impl (single swap point); `lexi.init()` runs at startup
- [ ] `migrate` step runs `alembic upgrade head` before api+worker start (they `depends_on` it)
- [ ] Answer flow updates stats + publishes realtime (no cache bust, no cron)
- [ ] Retired Go dirs + dead Python modules deleted
- [ ] End-to-end path works in a manual run

## Risk Assessment
- Deleting Go dirs may break lingering references. Mitigation: grep for imports before delete; delete after Python path proven.
- Migrate gate must complete before consumers start. Mitigation: `service_completed_successfully` condition on api+worker; migrate is idempotent (`upgrade head`).
