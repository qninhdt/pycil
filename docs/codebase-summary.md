# Pycil — Codebase Summary

**Stack:** FastAPI + SQLModel + Alembic backend (`apps/api`, `apps/worker`),
Next.js 15 frontend (`apps/web`), shared Python package (`packages/shared-py`).
**Migration:** `plans/260705-0032-python-greenfield-migration/plan.md` — see
[project-roadmap.md](./project-roadmap.md) for phase status.

This describes the codebase as it exists on `python-migration` today. The
prior Go/ent/chi backend was never completed and is gone; the prior
single-DB Python MVP (`apps/pycil-core`) is kept on disk as a historical
reference, not part of the running stack.

## Repository Layout

```
pycil/
├── apps/
│   ├── web/           # Next.js 15 (App Router) — frontend, partially migrated (see Known Gaps)
│   ├── api/            # FastAPI + SQLModel + Alembic — current backend
│   ├── worker/          # arq consumer — current worker (3 jobs)
│   └── pycil-core/     # Pre-migration Python backend — kept as historical reference, not run
├── packages/
│   └── shared-py/      # Cross-service package (pycil-shared): FSRS engine, realtime payloads,
│                        # plus legacy question-plugin/redis-lock/logging modules still used by pycil-core
├── vendor/
│   └── lexi-ai/         # Editable path dep — dictionary/question/grading authority (own DB); gitignored
├── docs/                # This folder
├── plans/               # Migration + feature plans
├── docker-compose.yml         # Current stack: postgres, redis, centrifugo, migrate, api, worker, backup
├── docker-compose.staging.yml # Stale — still wires an old `dex` OIDC service (see Known Gaps)
└── scripts/deploy.sh          # Stale — references a `pycil-core` container name the current compose file doesn't have
```

## Service: `apps/api` (FastAPI)

```
apps/api/
├── pycil/
│   ├── main.py                     # App factory: mounts routers, wires lifespan (lexicon.init())
│   ├── config.py                   # Pydantic Settings — DB/Redis/JWT/Google/Centrifugo/lexi vars
│   ├── auth/
│   │   ├── router.py                # /auth/login, /callback, /refresh, /logout
│   │   ├── oauth.py                 # Google OAuth2.1+PKCE, Redis-backed single-use state
│   │   ├── tokens.py                # sign_access/verify — HS256-pinned, secret-rotation fallback
│   │   ├── deps.py                  # current_user — Bearer-only, re-reads token_version/banned_at
│   │   ├── models.py, schemas.py
│   ├── content/
│   │   ├── router.py                # POST /words, deck-sense CRUD, GET /decks/{id}/items
│   │   ├── service.py                # request_word, create/rename/delete_deck, add/remove_sense
│   │   ├── lexi_port.py              # LexiClient Protocol (the port)
│   │   ├── lexi_inprocess.py         # InProcessLexiClient — the ONLY Lexicon(...) construction site
│   │   ├── deps.py                   # get_lexi_client singleton provider
│   │   ├── models.py                 # DeckSense (no FK on sense_id — cross-DB boundary)
│   │   ├── schemas.py
│   ├── hierarchy/
│   │   ├── router.py                # /nodes CRUD+move, /folders/{id}/stats|weakest|cefr
│   │   ├── service.py                 # create/move/soft_delete_node, REFERENCE-target validation
│   │   ├── access.py                  # require_node_access — the single IDOR gate
│   │   ├── subtree.py                 # Recursive CTE: resolve_deck_ids / resolve_sense_ids
│   │   ├── stats.py                   # folder_stats, weakest_senses, cefr_distribution
│   │   ├── cache.py                   # L1 Redis cache of resolved sense-id sets, ancestor-chain busted
│   │   ├── models.py                  # Node, FolderAttributes, DeckAttributes, UserNode
│   │   ├── schemas.py
│   ├── learning/
│   │   ├── router.py                 # POST /sessions, POST /answers
│   │   ├── router_question.py        # choose_format — mastery-gated, hash-seeded weighted pick
│   │   ├── service.py                 # answer() / apply_verdict() — FSRS update + persist-back
│   │   ├── session_queue.py           # build_queue — retrievability-ranked, new/due interleave
│   │   ├── grading.py                 # fsrs_grade / grade_status_for (Score → FSRS grade)
│   │   ├── fsrs_wrapper.py            # Thin wrapper over shared.fsrs (no new math)
│   │   ├── models.py                  # UserSenseStats, ReviewLog, Response
│   │   ├── schemas.py
│   ├── realtime/
│   │   ├── router.py                 # GET /realtime/token
│   │   ├── client.py                  # sign_subscription_token, publish (best-effort)
│   ├── worker_bridge/
│   │   └── __init__.py               # Empty — present but unmounted, not part of the live path
│   ├── common/
│   │   ├── errors.py                  # Domain error → HTTP mapping (NotFoundError, ConflictError, ...)
│   │   ├── middleware.py               # Body-size limit, CORS
│   │   ├── pagination.py               # PageParams / Page[T]
│   ├── db/
│   │   ├── models.py                   # target_metadata — aggregates every domain's SQLModel metadata
│   │   ├── base.py, session.py, redis.py
├── alembic/
│   └── versions/0001_baseline_baseline.py   # Single baseline migration (clean-slate greenfield schema)
├── tests/
│   ├── conftest.py                    # Real Postgres (pytest-postgresql) + fakeredis fixtures
│   ├── test_boundary.py               # Two-DB boundary structural assertions
│   ├── auth/, content/, hierarchy/, learning/, realtime/   # Per-domain unit tests
│   └── integration/test_session_flow.py   # Full session→answer→FSRS→persist-back flow
├── pyproject.toml                     # uv-managed; path deps on pycil-shared + lexi-ai
└── Dockerfile                          # Build context = repo root (needs vendor/lexi-ai + shared-py)
```

**Route inventory** (complete): `GET /health` (inline in `main.py`), auth
(`GET /auth/login`, `GET /auth/callback`, `POST /auth/refresh`,
`POST /auth/logout`), content (`POST /words`, `POST /decks/{node_id}/senses`,
`DELETE /decks/{node_id}/senses/{sense_id}`, `GET /decks/{node_id}/items`),
hierarchy (`POST /nodes`, `PATCH /nodes/{node_id}/move`,
`DELETE /nodes/{node_id}`, `GET /folders/{node_id}/stats`,
`GET /folders/{node_id}/weakest`, `GET /folders/{node_id}/cefr`), learning
(`POST /sessions`, `POST /answers`), realtime (`GET /realtime/token`).

**Wire format**: request/response schemas use Pydantic `Field(alias=...,
serialization_alias=...)` throughout to expose camelCase JSON
(`parent_node_id` ↔ `parentNodeId`, `sense_id` ↔ `senseId`) while keeping
snake_case Python internally.

**`worker_bridge`** is an empty package — not mounted in `main.py`, not
imported anywhere else. Jobs are enqueued directly against the arq Redis pool
from `content/service.py`; this package is a placeholder for a future
API-side job-status surface, not currently load-bearing.

## Service: `apps/worker` (arq)

```
apps/worker/
├── pycil_worker/
│   ├── main.py               # WorkerSettings — 3 functions, max_tries=2, on_startup/on_shutdown
│   ├── config.py              # Pydantic Settings (redis_url, db_url passthrough from pycil.config)
│   ├── realtime.py             # publish_job / publish_grading — reuses api's realtime.client.publish
│   └── jobs/
│       ├── generate_word.py     # search → (fallback) generate; single writer to lexi's DB
│       ├── generate_question.py # delegates to client.generate_questions
│       └── grade_answer.py      # resolves pending async verdicts; idempotent on grade_status
├── pyproject.toml              # Path dep on apps/api (reuses pycil.* for LexiClient/service/models)
└── Dockerfile                   # Build context = repo root; installs shared-py, lexi-ai, api, then worker
```

`apps/worker` currently has **no test directory** — the prior LLM-pipeline
test suite (jobs/llm/llm_live/unit subpackages) was removed as part of the
worker redesign and has not been replaced.

`generate_question.py` has a fallback branch: if the injected `LexiClient`
port has no `get(word_id)` method, it reaches into `ctx["lexicon"]` directly
(bypassing the port) to fetch the entry. `InProcessLexiClient` doesn't define
`get`, so this fallback is the path actually taken today — worth knowing if
touching this file, since it's a live port-bypass, not dead code.

## Package: `packages/shared-py` (pycil-shared)

```
packages/shared-py/
├── pyproject.toml
└── shared/
    ├── fsrs/
    │   ├── engine.py            # initial_state, update — FSRS-4.5 stability/difficulty math
    │   ├── recall.py             # recall(t, S) — retrievability
    │   ├── mastery.py             # mastery(S) — 0-100 display value
    │   ├── weights.py              # 17 hardcoded fsrs4anki v4.5 weights
    │   └── tests/test_fsrs_engine.py
    ├── realtime/
    │   ├── channels.py            # users:{uid}[:jobs:{id}|:grading:{id}] channel builders
    │   └── payloads.py             # JobUpdate, GradingResult, Notification dataclasses
    ├── db/
    │   ├── models.py, enums.py    # Legacy SQLModel models — consumed by apps/pycil-core only
    ├── questions/                  # Legacy question-type ABC + plugins (MCQ/write/fill-in-blank)
    ├── logging_config.py            # Legacy JSON logging setup
    └── redis_lock.py                 # Legacy Lua lock-or-get helper
```

Only `shared.fsrs` and `shared.realtime` are imported by the current
`apps/api`/`apps/worker` stack (`fsrs_wrapper.py`, `grading.py`,
`session_queue.py`, `service.py`, `learning/router.py`, worker's
`realtime.py`/`jobs/grade_answer.py`). `shared/db`, `shared/questions`,
`shared/logging_config.py`, and `shared/redis_lock.py` are **not dead code**
— they're still imported by the retained `apps/pycil-core` reference app
(e.g. `pycil_core/services/question_service.py`,
`pycil_core/observability/telemetry.py`). Don't delete them without also
retiring `apps/pycil-core`.

## Postgres Schema (`apps/api/alembic/versions/0001_baseline_baseline.py`)

Single baseline migration, greenfield (no data-migration step — clean
slate per the migration plan's validation log). 9 tables, all owned by
pycil; see [system-architecture.md](./system-architecture.md#two-database-boundary)
for the full table-to-domain mapping and the two-DB boundary rationale.

## Where Things Live (Quick Reference)

| Concern | Path |
|---|---|
| Two-DB boundary structural tests | `apps/api/tests/test_boundary.py` |
| LexiClient port | `apps/api/pycil/content/lexi_port.py` |
| Only Lexicon(...) construction site | `apps/api/pycil/content/lexi_inprocess.py` |
| FSRS math | `packages/shared-py/shared/fsrs/engine.py`, `recall.py`, `mastery.py`, `weights.py` |
| FSRS domain wrapper | `apps/api/pycil/learning/fsrs_wrapper.py` |
| Session queue | `apps/api/pycil/learning/session_queue.py` |
| Question format routing | `apps/api/pycil/learning/router_question.py` |
| Answer flow + verdict persist-back | `apps/api/pycil/learning/service.py` |
| IDOR gate | `apps/api/pycil/hierarchy/access.py` |
| Subtree resolution (recursive CTE) | `apps/api/pycil/hierarchy/subtree.py` |
| Folder/deck stats | `apps/api/pycil/hierarchy/stats.py` |
| Google OAuth2.1+PKCE | `apps/api/pycil/auth/oauth.py` |
| JWT sign/verify | `apps/api/pycil/auth/tokens.py` |
| Centrifugo channel builders | `packages/shared-py/shared/realtime/channels.py` |
| Centrifugo publish (best-effort) | `apps/api/pycil/realtime/client.py` |
| Worker jobs | `apps/worker/pycil_worker/jobs/` |
| Migration gate | `docker-compose.yml`'s `migrate` service |

## Known Gaps (see also system-architecture.md § Known Gaps)

- `apps/worker` has zero tests currently.
- `apps/api/pycil/worker_bridge/` is present but empty/unmounted.
- CI (`.github/workflows/*.yml`), `scripts/deploy.sh`, and the root
  `Makefile` all still target `apps/pycil-core` and/or a `dex` OIDC
  container, not the current `apps/api`/`apps/worker` stack.
- `apps/web` frontend auth/realtime integration is partial — see
  [project-roadmap.md](./project-roadmap.md).

## See Also

- [system-architecture.md](./system-architecture.md) — architecture, data
  flow, and the full Known Gaps list.
- [project-roadmap.md](./project-roadmap.md) — phase status.
- [project-changelog.md](./project-changelog.md) — dated change history.
