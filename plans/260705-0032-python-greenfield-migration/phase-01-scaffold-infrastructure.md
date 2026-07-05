---
phase: 1
title: "Scaffold & Infrastructure"
status: complete
priority: P1
effort: "1d"
dependencies: []
---

# Phase 1: Scaffold & Infrastructure

## Overview
Create the new branch off `main`, scaffold the domain-modular Python package, wire `pyproject.toml` (uv), lexi-ai path dep, and the docker-compose stack (Postgres, Redis, Centrifugo, api, worker) with Caddy removed.

## Requirements
- Functional: `uvicorn pycil.main:app` boots with a `/health` endpoint; `docker compose up` brings up all services.
- Non-functional: domain-split layout (no flat `services/`); files ≤ ~200 lines; env-driven config via pydantic-settings.

## Architecture
New branch `python-migration` off `main` (retains `apps/pycil-core` as read-only reference). Fresh `apps/api/pycil/` package with domain subpackages (`auth`, `content`, `hierarchy`, `learning`, `realtime`, `worker_bridge`, `common`, `db`). `packages/shared-py/shared/{db,fsrs,realtime}` shared between api + worker. lexi-ai wired as editable path dep on `~/projects/lexi-ai` (mirrors `pycil-shared`).

## Related Code Files
- Create: `apps/api/pyproject.toml`, `apps/api/pycil/main.py`, `apps/api/pycil/config.py`, `apps/api/pycil/db/{session,base,redis}.py`, `apps/api/pycil/common/{middleware,errors,pagination}.py`, `apps/api/Dockerfile`
- Create: `packages/shared-py/shared/fsrs/__init__.py` (placeholder), `packages/shared-py/shared/realtime/` (placeholder)
- Modify: `docker-compose.yml` (add centrifugo, drop caddy), `.env.example`
- Delete: Go-only files staged for removal in later phases (not yet)

## Implementation Steps
1. `git checkout main && git checkout -b python-migration`.
2. Scaffold `apps/api/pycil/` domain package tree + empty `__init__.py` per domain.
3. Write `pyproject.toml`: fastapi, uvicorn[standard], sqlmodel, alembic, asyncpg, redis, arq, pydantic-settings, pyjwt, httpx, pycil-shared (path), lexi-ai (path `~/projects/lexi-ai`, editable). Dev: pytest, pytest-asyncio, pytest-postgresql, fakeredis, ruff, httpx.
4. `config.py`: pydantic-settings `Settings` (DB_URL for pycil, REDIS_URL, JWT_SECRET, GOOGLE_CLIENT_ID/SECRET, CENTRIFUGO_*, INTERNAL_SECRET, and LEXI_* for lexi-ai: `LEXI_DB_URL` (separate pycil-lexi database on the same node), `LEXI_LLM_*`, `LEXI_CAMBRIDGE_DB_PATH`).
4b. Cambridge data provisioning: copy/mount the read-only Cambridge SQLite file from `~/projects/lexi-ai/data` (~142MB, gitignored) into the api+worker containers; set `LEXI_CAMBRIDGE_DB_PATH` to its path. Document in `.env.example`. Without it lexi `search()` returns empty and generation cannot resolve refs.
5. `db/session.py`: async engine + `get_session` dependency. `db/redis.py`: async Redis + arq pool.
6. `main.py`: FastAPI app factory, mount `/health`, wire middleware from `common/middleware.py`.
7. `common/middleware.py`: body-size, CORS, rate-limit, security-headers, `X-Internal-Secret` guard.
8. `docker-compose.yml`: services postgres, redis, centrifugo, api, worker; remove caddy service + Caddyfiles usage. Expose api `8000:8000`.
9. Verify: `docker compose up --build` → all healthy; `curl localhost:8000/health` → 200.

## Success Criteria
- [ ] New branch `python-migration` created off `main`
- [ ] `uvicorn pycil.main:app` boots, `/health` returns 200
- [ ] `docker compose up` starts postgres + redis + centrifugo + api + worker, all healthy
- [ ] No flat `services/` dir; each domain package is self-contained
- [ ] lexi-ai importable from api + worker venvs

## Risk Assessment
- Docker build must make lexi-ai source available (path dep) — copy/mount into build context or extend context root. Mitigation: document the interim build step; removed when lexi-ai publishes to PyPI.
- Centrifugo config drift. Mitigation: pin image version + minimal config in compose.
