# API conventions

## Contract discovery

Business routes use `/v1`. The working tree has 39 business operations.
`/livez` and `/readyz` are excluded from OpenAPI; generated `/docs`, `/redoc`,
and `/openapi.json` remain available with FastAPI defaults.

Use the generated schema for required fields and native vocabulary/AG-UI types. The declared
application version remains `1.0.0`; it is not proof that two checked-out revisions have
identical contracts. The node redesign is deliberately breaking under the current namespace.

Route groups and payload examples live in module pages. There is no old
`/v1/library/nodes` alias or raw study-history route. Search and Discovery are separate
from native word search; Star/Pin and sense preference routes remain absent.

## Custom actions

Custom methods follow [Google AIP-136](https://google.aip.dev/136): append `:verb`
to the resource, with camelCase for multiple words. Mutations use POST; simple
reads use GET. Bounded batch reads use POST for their structured request bodies.
Standard resource CRUD keeps its existing paths and methods.

Examples: `POST /v1/nodes/{node_id}:move`,
`POST /v1/nodes/{node_id}:modifySenses`, `GET /v1/words:search`,
and `POST /v1/assistant:run`. Handle lookup is
`GET /v1/users:lookup?handle=...`; the handle is a required query parameter.

This is a breaking URL change, including PATCH-to-POST for sense deltas.
Previous slash-action paths are not aliases. Deploy matching clients and ingress;
payloads, authorization, review idempotency and response formats are unchanged.
The [exported OpenAPI](openapi.json) lists every current path and method.

## Authentication and authorization

Private requests send `Authorization: Bearer <Clerk JWT>`. Verification checks RS256,
issuer, expiry, and subject, with audience verification when configured. Subject is the
identity key, not email. Missing credentials produce `authentication_required`; malformed
or invalid supplied credentials produce `invalid_credentials`.

Public-safe routes use optional authentication:

- `/v1/users/{user_id}` and current-handle lookup.
- Node child listing, metadata, sense/source pages and scoped search; Discovery.
- Dictionary search, word detail and batch previews; explicit card summaries.

Omitting the header permits anonymous public browsing. Supplying a bad token does not
fall back to anonymous. OpenAPI represents the anonymous alternative with an empty
security requirement, alongside the bearer scheme.

Public browsing is not public mutation. Editor/save/delete require current ownership.
Unreadable node identities return `node_not_found`, avoiding private metadata disclosure.
Personal learning fields always belong to the authenticated viewer, never the author.

Anonymous `/v1/nodes` requires an explicit readable `parent_id`; it is not a global
public-node listing. An authenticated omitted parent selects the user's Library roots.

## Request models and mutation semantics

Local request models reject unknown fields. Node requests cannot set owner, role,
space, type changes, or old visibility flags. Positive sense IDs are strict integers
and unique for deck membership. Blank names fail validation.

- Node `POST` creates a final item; omitted parent defaults to Personal.
- Node `PUT` is a full-state save, not a merge patch. Decks require complete `sense_ids`
  even for a rename. Omitted/null parent resolves to Personal, not "keep old parent."
- Settings `PATCH` merges only explicitly supplied known levels. Explicit null is invalid.
- Job acceptance returns 202; read completion through its status URL.
- Deletes return 204 with no response body; creation returns 201.
- There is no universal idempotency middleware for all mutations.

Never retry a create or publish-with-retained-reference blindly after an unknown outcome;
inspect current state first. Review-specific replay is documented in [Study](modules/study.md).

## Asynchronous request/reply

Word generation and study preparation return 202 with `job_id`, `status_url`,
`Location` and `Retry-After`. GET the owner-only `/v1/jobs/{job_id}` until a terminal
status; acceptance is not completion. See [jobs](modules/jobs.md) for expiry,
backoff, safe failures and retry limitations. Old word-status routes are absent.

## Errors and correlation

Error responses follow [RFC 9457 (Problem Details for HTTP APIs)](https://datatracker.ietf.org/doc/html/rfc9457) with media type `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "This material could not be found.",
  "instance": "/v1/nodes/018f2f45-0000-7000-8000-000000000001",
  "code": "node_not_found",
  "request_id": "018f2f45-0000-7000-8000-000000000002",
  "invalid_params": null,
  "error": "node_not_found"
}
```

- Standard RFC 9457 members:
  - `type`: URI identifying problem type (defaults to `"about:blank"`).
  - `title`: Short HTTP status phrase (e.g., `"Not Found"`).
  - `status`: HTTP status code integer matching the status header.
  - `detail`: Safe human-readable explanation (sanitized).
  - `instance`: Request URL path.
- Extension members:
  - `code`: Machine-readable error discriminator (e.g., `node_not_found`).
  - `request_id`: Request correlation ID matching `X-Request-ID`.
  - `invalid_params`: For 422 `invalid_request`, lists field locations and reasons without echoing raw input values.
  - `error`: Backward-compatible alias for `code`.

Raw provider/DB exceptions and secret inputs are never reflected back. The request boundary gives each HTTP response an `X-Request-ID`: a valid incoming UUID is retained, otherwise a fresh UUID is generated. Use it for support and log correlation; it is not an idempotency key.

| Status | Typical meaning |
| --- | --- |
| 400 | Malformed body-length declaration |
| 401 | Missing/invalid identity; domain 401 responses include `WWW-Authenticate: Bearer` |
| 403 | Feature/allowance or grading entitlement denied |
| 404 | Missing/unreadable resource or nonexistent route |
| 405 | Method not allowed |
| 409 | Publication consent required, invalid tree-space state, content changed, replay conflict, busy/pending conversation |
| 413 | Request or attachment exceeds limits |
| 422 | Invalid request/domain selection, quota, cycle, depth, reference rule, or oversized scope |
| 429 | Assistant admitted-start rate exceeded |
| 500 | Redacted unhandled failure |
| 503 | Runtime dependency, scope deadline, SQL cancellation, or provider unavailability |

Application database pool acquisition timeout returns 503 `database_busy`; its
native exception details stay out of the response and logs. This is bounded
overload rejection, not proof that an uncertain mutation can be replayed.

The response error code is the machine-readable discriminator; not every route emits
every declared status. Log messages should not include JWTs, credentials, submitted
answers, or raw provider/DB exceptions. Retry only where the operation's semantics
permit it, not simply because a status is 503.

## Pagination

Paged routes accept `cursor` and `limit` (default 50, maximum 100) and return
`next_cursor`. Opaque versioned tokens bind viewer, route kind, scope and normalized
filters/order to seek values. Wrong/malformed tokens return 422 `invalid_cursor`.
Old `after_id`, `after`, and conversation timestamp pairs are rejected, not ignored.
Tokens are unsigned and confer no access; predicates and live authorization run again.
Deleting an anchor does not require a private anchor lookup or invalidate its seek tuple.

Children order creation time/ID ascending; conversations order updated time/ID descending.
Sources seek canonical deck ID. Discovery without a query orders creation time/ID
descending; FTS orders rank descending then ID ascending. Sense orders are ID, lower
lemma/ID, or applied review time descending with never-reviewed last and ID ties.

Sense pages bind state all/new/due/not_yet_due, literal lemma `q`, and sort. Non-all
state or personal review order requires sign-in. Tokens freeze `as_of` for state
classification, not cross-request membership/progress snapshots. Refresh after edits
or reviews. Anonymous senses have `learning=null`. No exact global search count is
invented. Optional `include` values are validated; unknown/duplicate page query keys fail.

## Bodies and CORS

The application enforces 15,000,000 bytes for JSON and assistant request bodies. It
checks both declared size and streamed chunks before dispatch; chunked transfer does
not bypass the limit. Responses, including SSE, are not fully buffered by this guard.

CORS includes the localhost development origins and configured deployment origins,
allows credentialed requests, and exposes response headers including X-Request-ID.
It surrounds the error boundary. Caddy has a matching request byte cap.

## Assistant streaming

`POST /v1/assistant:run` returns native AG-UI events over `text/event-stream`, not a JSON
assistant transcript or a WebSocket. Pre-stream failures can still return normal JSON
errors. After headers have started, a failed/truncated stream cannot be replaced with
a second HTTP status. Clients must handle run-error events and disconnects explicitly;
HTTP 200 alone is not proof the turn finished.

For requests, messages, attachments, resume approval, and recovery, see [Assistant](modules/assistant.md).
Do not replay an uncertain assistant turn as though it had review idempotency.

## Sources

- [Application router assembly](../../apps/api/pycil/main.py), [HTTP boundary](../../apps/api/pycil/app/http.py)
- [Identity dependencies](../../apps/api/pycil/account/auth.py), [request SQL timeout handling](../../apps/api/pycil/app/dependencies.py)
- [Lifecycle and readiness](../../apps/api/tests/integration/app/test_lifespan.py)
