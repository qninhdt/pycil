# Pycil — Codebase Summary

**Stack:** FastAPI + SQLModel + Alembic (`apps/api`), arq worker
(`apps/worker`), and `pycil-shared` (`packages/shared-py`). This is a
backend-only repository. A Next.js BFF/frontend is intentionally out of tree.

Pycil owns identities, the vocabulary hierarchy, deck membership, learning
state, realtime events, and durable orchestration jobs. Public
[`lexi-ai`](../../lexi-ai) is a separately deployed HTTP service and owns all
dictionary entries, senses, Cambridge reference data, questions, and grading.
There is no editable Lexi dependency or Cambridge dataset in this repository.
The current architecture reference is
[current-system-architecture.md](./current-system-architecture.md).

## Runtime topology

```
client / Next.js BFF ─ bearer REST ─► Pycil API (:8000)
                                      ├─ Pycil Postgres
                                      ├─ Redis / arq
                                      ├─ Centrifugo
                                      └─ internal pycil-backend network ─► lexi-service
                                                                            └─ Lexi Postgres
```

Both compose projects join the externally created, internal Docker network
`pycil-backend`. The service name `lexi-service` is the only dictionary
endpoint Pycil needs. `LEXI_REFERENCE_DATASET_SHA256` is a deployment contract:
Pycil refuses readiness when the Lexi dataset fingerprint differs.

## Repository layout

```
apps/
  api/                 FastAPI API and Alembic migrations
  worker/              arq worker, using the API package for DTOs/jobs
packages/shared-py/    FSRS math and realtime channel/payload helpers
infra/backup/          Restic/Postgres backup image and scripts
scripts/deploy.sh      VPS migration-then-swap deployment
docker-compose.yml     Pycil API stack (does not run Lexi)
```

## API service (`apps/api/pycil`)

| Area | Responsibility |
|---|---|
| `auth/` | Google OAuth + PKCE; bearer JWT verification with token-version revocation. No roles, bans, or cookie auth. |
| `hierarchy/` | Private-by-default nodes, folders, decks, and references. Anonymous users can read only public content; mutations are author-only. |
| `content/` | `GET /v1/words/search`, deck-to-opaque-sense membership, and `LexiHttpClient`, the only dictionary transport adapter. |
| `jobs/` | Durable `word_generations` records. `POST /v1/word-generations` accepts optional `Idempotency-Key`; `GET /v1/jobs/{id}` is owner scoped. |
| `learning/` | Redis-backed session delivery, authoritative Lexi grading, FSRS persistence, and response polling. |
| `assistant/` | Optional bounded assistant with durable runs/actions; it schedules the same word-generation job instead of bypassing it. |
| `realtime/` | Centrifugo connection tokens and owner-scoped event payloads. |
| `common/` | Standard error envelope, request-id middleware, CORS/body limits. |

All application routes are versioned under `/v1`. Health endpoints are
unversioned: `/health/live` is process liveness; `/health/ready` verifies
Pycil Postgres, Redis, worker heartbeat, Lexi, and Centrifugo readiness.

Study delivery exposes a discriminated `format` union (`definition_mcq`,
`contextual_mcq`, `cloze`, `use_in_sentence`) in OpenAPI. Only the
format-specific presentation fields cross the boundary; answer material stays
inside Lexi.

### Persistence boundary

Pycil tables include `users`, `nodes`, `deck_attributes`, `deck_senses`, FSRS
learning tables, assistant tables, and `word_generations`. Pycil deliberately
does **not** contain Lexi's `words`, `senses`, `questions`, `examples`, or
Cambridge data. `apps/api/tests/test_boundary.py` enforces this structurally.

Alembic is forward-only for removal and durable-job migrations:

- `0009_remove_legacy_product_schema` removes roles/bans, social counters,
  folders, pins/stars, notifications, and their dead tables/columns.
- `0010_durable_word_generations` adds owner-scoped durable Lexi generation
  lifecycle records (`queued → running → succeeded|failed`).
- `0011_word_generation_idempotency` adds a partial owner/idempotency-key
  uniqueness index for browser retries.

## Worker (`apps/worker`)

The worker uses the same `LexiHttpClient` as the API. `generate_word` first
atomically claims a queued `word_generations` row, then asks Lexi to search or
generate, persists only opaque Lexi ids as the result, and publishes status.
Retries observe the existing claim and return `duplicate`; they cannot create a
second Lexi write through this job path.

If the producer commits a job while Redis is unavailable, the worker's queued
generation reconciliation cron submits it later. Thus polling remains correct
even if the first realtime/enqueue attempt is missed.

Other jobs generate questions, apply asynchronous grades, and reconcile
pending grades/assistant state. The worker never opens Lexi's database.

## Verification

- API tests use `TEST_DB_URL` or a disposable PostgreSQL container and
  fakeredis.
- Worker tests cover registration, grade terminal delivery, and durable word
  generation lifecycle/retry behavior.
- `docker compose` has a one-shot migration gate. API and worker wait for it,
  then connect to Lexi only over `pycil-backend`.
- `scripts/deploy.sh` snapshots Pycil Postgres, ensures `pycil-backend` exists,
  migrates the new image, starts worker before API, and gates API on
  `/health/ready`.

## Deliberately absent

There are no admin/role/ban systems, folder-specific attributes, social
counters, pins, stars, notifications, billing, gamification, translation/TTS,
or local Cambridge / Lexi database implementation. These were removed rather
than maintained as legacy compatibility surface.
