# Frontend integration guide

Pycil is a bearer-token API. The browser must not retain that token. Use a
Next.js BFF with `iron-session`: the BFF stores the bearer token in its
encrypted, `HttpOnly`, `Secure`, `SameSite=Lax` session cookie and adds
`Authorization: Bearer <token>` only on server-to-server calls to Pycil.

## Required production configuration

Set `OAUTH_REDIRECT_URIS` to the exact Next.js callback URL, for example
`https://app.example.com/api/auth/callback`, and include the Next.js origin in
`ALLOWED_ORIGINS`. Production startup rejects localhost `DOMAIN`, an empty
redirect allowlist, wildcard/localhost origins, and placeholder secrets.

## Authentication flow

1. BFF calls `GET /v1/auth/login?redirect_uri=<its exact callback URL>`.
2. Redirect the browser to returned `authorizeUrl`.
3. Google redirects to the BFF callback with `code` and `state`.
4. BFF calls `GET /v1/auth/callback?code=…&state=…`, receives
   `access_token` and `expires_in`, then seals the token in `iron-session`.
5. On each server render/action, BFF calls `GET /v1/me`. A 401 means clear the
   BFF session and restart login. `POST /v1/auth/refresh` can rotate a valid
   token before expiry; `POST /v1/auth/logout` revokes every token for that
   user and BFF must clear its cookie.

Pycil never accepts a browser cookie and never implements Auth.js/session-table
semantics.

For local development only, opt in with `DEV_IDENTITY_ENABLED=true` and run
`uv run python -m pycil.auth.dev_identity`. It creates/reuses a deterministic
development user and prints a normal bearer token. The command fails closed in
production and is never an HTTP endpoint.

## Core routes

All routes below are `/v1` routes. Mutations require bearer auth.

| Flow | Routes |
|---|---|
| Identity | `GET /me`, `GET /capabilities` |
| Tree | `GET /nodes`, `POST /nodes`, `GET/PATCH/DELETE /nodes/{id}`, move/visibility routes, `PATCH /decks/{id}/settings` |
| Dictionary | `GET /words/search?q=…`; `POST /word-generations`; `GET /jobs/{jobId}` |
| Deck membership | `POST/DELETE /decks/{nodeId}/senses/{senseId}`; `GET /decks/{nodeId}/items` |
| Study | `POST /sessions`, `GET /sessions/{sessionId}/next`, `POST /answers`, `GET /responses/{responseId}` |
| Realtime | `GET /realtime/token` |

Public nodes/content may be read anonymously through their direct URL. There is
no anonymous discovery/listing endpoint. Private nodes return 404 to everyone
but their author; writes are always author-only.

## Word generation and polling

`POST /word-generations` body is `{ "query": "example" }`. Send a fresh UUID
as `Idempotency-Key` per user action and reuse it only when retrying that same
action. Response is `{ "jobId", "status" }` with status `queued`.

Poll `GET /jobs/{jobId}` until `status` is `succeeded` or `failed`. A terminal
success result contains opaque Lexi `wordId` and `senseIds`; attach selected
sense IDs with `POST /decks/{nodeId}/senses`. Polling is authoritative;
Centrifugo is only an acceleration path. Jobs are owner-scoped and another
user receives 404.

## Study question union

`GET /sessions/{sessionId}/next` returns one of:

- `{ state: "pending", senseId, recommendedType }`: retry after a short delay.
- `{ state: "exhausted" }`: end the session.
- `{ state: "ready", questionId, senseId, recommendedType, format, payload }`.

For `ready`, switch on `format`:

| `format` | `payload` | Client answer |
|---|---|---|
| `definition_mcq`, `contextual_mcq` | `{ stem, options }` | selected option index as a string |
| `cloze` | `{ stemWithBlank }` | entered text |
| `use_in_sentence` | `{ prompt }` | entered sentence |

No ready payload contains correct indices, normalized answers, accepted forms,
or grading rubric. Submit only `{ sessionId, questionId, answer }` to
`POST /answers`; never echo question payload back. `GET /responses/{responseId}`
is the recovery/polling source for an async verdict.

## Errors and realtime

Errors use one envelope:

```json
{"error":{"code":"…","message":"…","details":{},"requestId":"…"}}
```

Log the `requestId` for support. Do not branch on English messages. The BFF can
obtain a Centrifugo connection token from `/realtime/token`; subscribe only to
the owner-scoped channels provided by the API contract. On reconnect or missed
events, refetch jobs/responses/runs: durable HTTP state wins over push events.
Job updates use `{ jobId, status, detail }`; grading updates use camelCase
response/sense/verdict/mastery fields matching `GET /responses/{responseId}`.

Assistant SSE runs are recoverable via
`GET /assistant/threads/{threadId}/runs/{runId}?after=<sequence>`; do not treat
an interrupted stream as a failed run.
