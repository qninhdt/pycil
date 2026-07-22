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
2. Redirect the browser to returned `authorize_url`.
3. Google redirects to the BFF callback with `code` and `state`.
4. BFF calls `GET /v1/auth/callback?code=…&state=…`, receives
   `access_token`, `refresh_token`, `expires_in`, and `refresh_expires_in`,
   then seals both tokens and their expiries in `iron-session`.
5. Before forwarding a Pycil call, the BFF refreshes when the access token is
   close to expiry: `POST /v1/auth/refresh` with `{ "refresh_token": "…" }`.
   Replace the stored refresh token atomically with the returned one. Refresh
   tokens are single-use and rotation/replay revokes the session family.
6. On each server render/action, BFF calls `GET /v1/me`. A 401 means clear the
   BFF session and restart login. To sign out, call `POST /v1/auth/logout`
   with the stored refresh token, then clear the BFF cookie.

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
obtain a Centrifugo connection token from `/realtime/token`. The response is
`{ token, expiresAt, websocketUrl }`; connect only to that `websocketUrl` and
renew before `expiresAt`. Subscribe only to the owner-scoped channels provided
by the API contract. On reconnect or missed events, refetch jobs/responses/runs:
durable HTTP state wins over push events.
Job updates use `{ jobId, status, detail }`; grading updates use camelCase
response/sense/verdict/mastery fields matching `GET /responses/{responseId}`.

Assistant SSE frames use `id`, `event`, and JSON `data`; persist the latest
event id and reconnect with `Last-Event-ID`. Runs are recoverable via
`GET /assistant/threads/{threadId}/runs/{runId}?after=<sequence>`; do not treat
an interrupted stream as a failed run. The API enforces a 1 MiB cumulative
request-body limit (including chunked uploads); send compact JSON only.

## Contract and account lifecycle

The canonical, versioned OpenAPI document is `GET /v1/openapi.json` (the
unversioned `/openapi.json` remains a convenience alias). Generate clients from
the versioned document and treat compatible additions as the normal evolution
path. All documented non-success responses use the error envelope above; a
429 also supplies `Retry-After` when a retry time is known.

Authenticated users can download their Pycil-owned export with
`GET /me/export` and permanently delete their Pycil account with `DELETE /me`,
supplying `{ "confirmation": "DELETE", "refresh_token": "…" }` as a
confirmation.
Deletion does not delete Lexi's independently owned dictionary data.
