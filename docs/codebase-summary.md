# Pycil — Codebase Summary

**Stack:** FastAPI + SQLModel + Alembic backend (`apps/api`, `apps/worker`),
shared Python package (`packages/shared-py`). Backend-only repo — no frontend;
clients consume the API over REST + bearer JWT.
**Migration:** `plans/260705-0032-python-greenfield-migration/plan.md` — see
[project-roadmap.md](./project-roadmap.md) for phase status.

This describes the codebase as it exists on `python-migration` today. The
prior Go/ent/chi backend was never completed and is gone; the prior
single-DB Python MVP (`apps/pycil-core`) was fully superseded by `apps/api`
and has been removed (2026-07-06) — nothing in the running stack referenced
it (see git history if you need to recover it).

## Repository Layout

```
pycil/
├── apps/
│   ├── api/            # FastAPI + SQLModel + Alembic — current backend
│   └── worker/          # arq consumer — current worker (4 jobs)
├── packages/
│   └── shared-py/      # Cross-service package (pycil-shared): FSRS engine, realtime channel/payload builders
├── vendor/
│   └── lexi-ai/         # Editable path dep — dictionary/question/grading authority (own DB); gitignored
├── docs/                # This folder
├── plans/               # Migration + feature plans
├── docker-compose.yml         # Current stack: postgres, redis, centrifugo, migrate, api, worker, backup
├── centrifugo-config.json     # Enables native user-limited channel ACL in the users namespace
└── scripts/deploy.sh          # Migration-then-swap prod deploy against the current compose topology
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
│   │   ├── router.py                # hierarchy routes, folder stats/items/history, global stats
│   │   ├── service.py               # Locked tree mutations, reference/publication validation, generation bumps
│   │   ├── access.py                # Owner-only writes; direct/inherited public read gate
│   │   ├── subtree.py               # Same-owner recursive CTE + live reference visibility filtering
│   │   ├── stats.py                   # folder_stats, weakest_senses, cefr_distribution
│   │   ├── cache.py                 # DB-generation, viewer-scoped Redis cache + reverse-reference invalidation
│   │   ├── models.py                  # Node, FolderAttributes, DeckAttributes, UserNode
│   │   ├── schemas.py
│   ├── learning/
│   │   ├── router.py                 # POST /sessions, POST /answers, GET /responses/{id}
│   │   ├── router_question.py        # choose_format — mastery-gated, hash-seeded weighted pick
│   │   ├── service.py                 # answer() / apply_verdict() — FSRS update + persist-back
│   │   ├── session_store.py           # Redis session issue/cursor state and answer binding
│   │   ├── question_delivery.py       # canonical question lookup and payload sanitisation
│   │   ├── session_queue.py           # build_queue — retrievability-ranked, new/due interleave
│   │   ├── grading.py                 # fsrs_grade / grade_status_for (Score → FSRS grade)
│   │   ├── fsrs_wrapper.py            # Thin wrapper over shared.fsrs (no new math)
│   │   ├── models.py                  # stats/logs, durable session attempts, leased pending responses
│   │   ├── schemas.py
│   ├── realtime/
│   │   ├── router.py                 # Centrifugo connection-token endpoint
│   │   ├── client.py                  # connection JWT signing, publish (best-effort)
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
│   └── versions/
│       ├── 0001_baseline_baseline.py         # Clean-slate greenfield schema
│       ├── 0002_hierarchy_integrity.py       # Hierarchy integrity preflight + cache generation schema
│       ├── 0003_learning_grading_expand.py   # Durable attempts and pending-grade lease fields
│       ├── 0004_review_history_index.py      # Bounded history access path
│       └── 0005_learning_grading_validate.py # Pending-grade data validation constraint
│       ├── 0006_learning_grading_expiry_status.py # Terminal expiry state for raw-answer retention
│       └── 0007_response_mastery_snapshots.py  # Poll/realtime mastery parity
├── tests/
│   ├── conftest.py                    # `TEST_DB_URL` or disposable Testcontainers PostgreSQL + fakeredis fixtures
│   ├── test_boundary.py               # Two-DB boundary structural assertions
│   ├── auth/, content/, hierarchy/, learning/, realtime/   # Per-domain unit tests
│   ├── contracts/                     # Strict xfails for accepted hardening gaps, removed by owning phases
│   └── integration/test_session_flow.py   # Full session→answer→FSRS→persist-back flow
├── pyproject.toml                     # uv-managed; path deps on pycil-shared + lexi-ai
└── Dockerfile                          # Build context = repo root (needs vendor/lexi-ai + shared-py)
```

**Route inventory** (complete): `GET /health` (inline in `main.py`), auth
(`GET /auth/login`, `GET /auth/callback`, `POST /auth/refresh`,
`POST /auth/logout`), content (`POST /words`, `POST /decks/{node_id}/senses`,
`DELETE /decks/{node_id}/senses/{sense_id}`, `GET /decks/{node_id}/items`),
hierarchy (`POST /nodes`, `PATCH /nodes/{node_id}/move`,
`PATCH /nodes/{node_id}/visibility`, `DELETE /nodes/{node_id}`, `GET /folders/{node_id}/stats`,
`GET /folders/{node_id}/weakest`, `GET /folders/{node_id}/cefr`,
`GET /folders/{node_id}/items`, `GET /folders/{node_id}/history`, `GET /me/stats`),
learning (`POST /sessions`, `POST /answers`, `GET /responses/{response_id}`),
realtime (`GET /realtime/token`).

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
│   ├── main.py               # WorkerSettings — 4 functions plus reconciliation cron, max_tries=2
│   ├── config.py              # Pydantic Settings (redis_url, db_url passthrough from pycil.config)
│   ├── realtime.py             # publish_job / publish_grading — reuses api's realtime.client.publish
│   └── jobs/
│       ├── generate_word.py     # search → (fallback) generate; single writer to lexi's DB
│       ├── generate_question.py # delegates to client.generate_questions
│       ├── grade_answer.py      # resolves pending async verdicts; idempotent on grade_status
│       └── reconcile_pending_grades.py # bounded sweep for unleased pending grades; purges stale raw answers
├── tests/
│   └── test_worker_registration.py # asserts reconciliation job + cron registration
├── pyproject.toml              # Path dep on apps/api (reuses pycil.* for LexiClient/service/models)
└── Dockerfile                   # Build context = repo root; installs shared-py, lexi-ai, api, then worker
```

`apps/worker/tests/test_worker_registration.py` protects the registration of
the durable-grade reconciler and its cron schedule. It is intentionally a
narrow smoke test, not job-behaviour coverage.

### Test Baseline

API tests use `TEST_DB_URL` when supplied (as in CI); otherwise `conftest.py`
starts a disposable `postgres:16-alpine` container through Testcontainers.
Redis remains a fakeredis boundary fake. The Phase 1 hardening baseline
(2026-07-16) recorded 64 API tests passing and 19 expected strict xfails.
Phase 2 turns the eight hierarchy/cache cases into passing regression tests;
later phases implement their session, grading, and statistics contracts.
Shared FSRS tests recorded 13 passing. See the
[baseline report](../plans/260716-1321-system-design-alignment-hardening/reports/current-test-baseline.md).

Question generation and session delivery resolve lexical content through the
`LexiClient` port; workers do not use a direct `ctx["lexicon"]` fallback.

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
    └── realtime/
        ├── channels.py            # users:{uid}:...#{uid} channel builders
        └── payloads.py             # JobUpdate, GradingResult, Notification dataclasses
```

Both `shared.fsrs` and `shared.realtime` are imported by the current
`apps/api`/`apps/worker` stack (`fsrs_wrapper.py`, `grading.py`,
`session_queue.py`, `service.py`, `learning/router.py`, worker's
`realtime.py`/`jobs/grade_answer.py`). The legacy `shared/db`,
`shared/questions`, `shared/logging_config.py`, and `shared/redis_lock.py`
modules (SQLModel models, question-type ABC/plugins, JSON logging, Lua
lock-or-get helper) were removed alongside `apps/pycil-core` (2026-07-06) —
that reference app was their only consumer.

## Postgres Schema (`apps/api/alembic/versions/`)

The greenfield `0001` baseline is followed by additive migrations `0002`–`0007`.
`0002` preflights legacy cycles, cross-owner/non-folder edges, invalid
memberships, and invalid reference targets before adding
`nodes.structural_generation`, the reference-target shape constraint, and a
target lookup index. `0003` adds durable first-attempt and pending-grade
state; `0004` adds the review-history access path; `0005` validates pending
rows; `0006` adds the terminal expired state used by retention; `0007` persists
response mastery snapshots so polling and realtime expose the same verdict. See
[system-architecture.md](./system-architecture.md#two-database-boundary) for
the table-to-domain mapping and two-DB boundary rationale.

## Where Things Live (Quick Reference)

| Concern | Path |
|---|---|
| Two-DB boundary structural tests | `apps/api/tests/test_boundary.py` |
| LexiClient port | `apps/api/pycil/content/lexi_port.py` |
| Only Lexicon(...) construction site | `apps/api/pycil/content/lexi_inprocess.py` |
| FSRS math | `packages/shared-py/shared/fsrs/engine.py`, `recall.py`, `mastery.py`, `weights.py` |
| FSRS domain wrapper | `apps/api/pycil/learning/fsrs_wrapper.py` |
| Session delivery and binding | `apps/api/pycil/learning/session_store.py`, `question_delivery.py` |
| Session queue | `apps/api/pycil/learning/session_queue.py` |
| Question format routing | `apps/api/pycil/learning/router_question.py` |
| Answer flow + verdict persist-back | `apps/api/pycil/learning/service.py` |
| IDOR gate | `apps/api/pycil/hierarchy/access.py` |
| Subtree resolution (recursive CTE) | `apps/api/pycil/hierarchy/subtree.py` |
| Generation-safe subtree cache | `apps/api/pycil/hierarchy/cache.py` |
| Folder/deck stats | `apps/api/pycil/hierarchy/stats.py` |
| Google OAuth2.1+PKCE | `apps/api/pycil/auth/oauth.py` |
| JWT sign/verify | `apps/api/pycil/auth/tokens.py` |
| Centrifugo channel builders | `packages/shared-py/shared/realtime/channels.py` |
| Centrifugo connection JWT + publish | `apps/api/pycil/realtime/client.py` |
| Worker jobs | `apps/worker/pycil_worker/jobs/` |
| Migration gate | `docker-compose.yml`'s `migrate` service |

## Known Gaps (see also system-architecture.md § Known Gaps)

- Worker coverage is currently limited to the reconciliation registration test.
- `apps/api/pycil/worker_bridge/` is present but empty/unmounted.

## See Also

- [system-architecture.md](./system-architecture.md) — architecture, data
  flow, and the full Known Gaps list.
- [project-roadmap.md](./project-roadmap.md) — phase status.
- [project-changelog.md](./project-changelog.md) — dated change history.
