# Pycil canonical system architecture

## Boundaries

Pycil and Lexi are separate services with separate PostgreSQL databases.

| Owner | Data and responsibility |
|---|---|
| Pycil | users, node hierarchy, deck-to-sense membership, FSRS/review history, assistant state, durable word jobs, realtime token issuance |
| Lexi | Cambridge reference cache, entries, senses, questions, answer keys, grading and generation |

Pycil references Lexi data only through opaque IDs (`wordId`, `senseId`,
`questionId`). It must never import Lexi ORM models, mount Cambridge data, or
write Lexi's database directly. The boundary is enforced by
`apps/api/tests/test_boundary.py`.

## Deployment

One VPS runs two Docker Compose projects. Each project has its own stores and
they join the pre-created internal network `pycil-backend`:

```
Internet ─ TLS ingress ─► Pycil API ─► Pycil Postgres / Redis / Centrifugo
                              │
                              └── internal pycil-backend ─► lexi-service ─► Lexi Postgres
```

Pycil exposes API and Centrifugo ports; Lexi has no public API port. The API
and worker authenticate to Lexi using the shared service token and verify the
configured Cambridge reference fingerprint through Lexi readiness.

`/health/live` means the API process is running. `/health/ready` requires
Pycil Postgres, Redis, a recent worker heartbeat, Lexi, and Centrifugo. The
assistant is optional and only appears as a capability.

## API and identity

All product routes use `/v1`. Pycil accepts only `Authorization: Bearer` JWTs;
token-version checks make logout/revocation immediate. Google OAuth 2.1 uses
PKCE and exact configured redirect URLs.

The frontend is a separate Next.js BFF. It keeps the bearer token inside
`iron-session` and does not expose it to browser JavaScript. See
[frontend integration guide](./frontend-integration-guide.md).

Public nodes are readable anonymously only by direct URL. Private nodes are
invisible (404) to anyone except their author. All writes are author-only.

## Durable orchestration

Word generation creates a Pycil `word_generations` row before enqueueing arq.
The worker atomically changes it from `queued` to `running`, asks Lexi to
search/generate, stores only opaque result IDs, and publishes status. An
`Idempotency-Key` deduplicates browser retries. A worker cron reenqueues rows
left queued after an API-to-Redis outage; a duplicate arq message is harmless
because the database claim fences it.

HTTP polling (`GET /v1/jobs/{jobId}` and `GET /v1/responses/{responseId}`) is
authoritative. Centrifugo push is a latency optimisation and uses the same
camelCase event fields.

## Learning

Redis holds ephemeral study session queue/cursor/issue state. PostgreSQL holds
durable response, attempt and FSRS effects. Lexi is authoritative for question
content and grades. Ready question payloads are an OpenAPI-discriminated union:

- `definition_mcq` / `contextual_mcq`: `{ stem, options }`
- `cloze`: `{ stemWithBlank }`
- `use_in_sentence`: `{ prompt }`

Correct answers, answer indexes, accepted forms and rubrics never leave Lexi.
First-attempt claims and worker grade leases prevent duplicate FSRS mutation.

## Removed surface

No roles/bans/admin panel, social counters, pins/stars, notifications, billing,
gamification, TTS/translation, local Cambridge storage, or in-process Lexi
adapter is part of the canonical runtime.
