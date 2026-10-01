# modules/web

The browser client. UI only. Decisions `I1`–`I5`, `H1`.

It proxies nothing and owns no business rule.

## 1. Direct API client

The browser calls FastAPI directly, attaching Clerk's session token as an
`Authorization: Bearer` header. Server actions, proxy routes, sealed web sessions
and credential forwarding are deleted.

**Status: the types are hand-written, not generated.** `I2` specifies generation
from the OpenAPI document. Nothing generates a client: the earlier
`scripts/generate-web-openapi.sh` emitted into `apps/web/lib/api/generated/`, which
no longer exists, and nothing imported its output, so it was removed rather than
left as a script that appears to maintain a contract it does not. `apps/web/lib/api/types/`
and `apps/web/lib/api/resources/` are hand-written, derived by reading an archived
`GET /v1/openapi.json` snapshot rather than by running a generator. So most of the
drift `I2` exists to prevent is not prevented: a server DTO can change and `tsc` will
still pass against a stale mirror.

| Generated from OpenAPI | Hand-written |
|---|---|
| — *(nothing, currently)* | Request and response types |
| — | Endpoint functions |
| — | Transport wrapper, query keys, cache policy |
| — | Human error presentation |
| — | Study state machine |
| — | assistant-ui AG-UI runtime and thread recovery UI |
| — | Durable-job polling |

Wiring generation in — importing a generated client instead of the mirrors, and
failing CI when regeneration produces a diff — is the work `I2` describes. It is not
done, and this document said otherwise until it was checked against the code.

**Two contracts are checked instead, because both had already drifted.** Neither is
a substitute for generation; each covers the one thing a stale mirror silently
breaks, and both read the server as the authority:

- `apps/api/tests/unit/architecture/test_web_client_paths_are_served.py` — every
  path a resource fetches exists in the app's own OpenAPI. Written after the
  analytics routes were consolidated onto `/v1/me/*?nodeId=` and four folder-scoped
  paths the client still called had stopped existing.
- `apps/api/tests/unit/architecture/test_web_error_codes_match_api.py` — the
  client's error-code map equals the set the API can emit, in both directions and
  with matching statuses. Written after that map drifted both ways at once: 27 codes
  the API raises were absent, 16 entries named codes nothing raises any more, one
  status was wrong, and the client branched in two places on a code no version of
  this API emits. An unlisted code falls through to a generic message with no retry,
  so each missing one was a recoverable failure rendering as a broken product.

Both are static checks over the sources, so they cover the wire contract and nothing
else: a changed response *shape* still passes both.

`lib/api/request.ts` is the whole hand-written wrapper. It reads
`window.Clerk.session.getToken()` and sets the bearer header, adds an
`X-Request-ID`, parses RFC 9457 errors, and sends `credentials: "include"`.

**There is no CSRF header and no cross-tab refresh serialization.** Both were in
earlier revisions and both are withdrawn with the cookie design: a bearer header
is attached explicitly by application code, so a cross-site request carries no
credential, and Clerk's SDK owns session lifetime and refresh.

## 2. Study

The server chooses every sense, level, item, and round boundary. The client keeps
the current item, round indicator, break state, and submitted-once guard. It has
no checkpoint, retry, priority, scheduling, or pending-grade state.

Free-text submission waits for the synchronous grade. A timeout leaves the item
answerable and shows a retryable error. A successful response already contains
the verdict and updated strength/depth projection.

Strength renders as a percentage and next-review time. Stage names render only
from `depth_level`; their band table has one server owner and is generated into
the client contract.

## 3. Delivery

Durable jobs return `202` with a receipt. The client polls the owner-authorized
job endpoint with bounded backoff until a terminal snapshot. Reloading resumes
polling from route state or the canonical resource read.

Assistant turns and resumes use `POST /v1/assistant`. FastAPI streams
standard AG-UI events over SSE; `@assistant-ui/react-ag-ui` renders incremental
text and tool calls. A dropped connection does not imply completion: the panel
reads the Run and Thread state and renders the durable result or interruption.

## 4. Assistant panel

An approval interrupt closes the first stream and renders a popup from durable
checkpoint state. Reloading reconstructs the same popup. A decision starts a new
AG-UI request with a resume entry:

```text
approve -> execute the proposed tool call
edit    -> execute the corrected tool call
reject  -> give the refusal to the assistant and continue
respond -> give the user's response to the assistant and continue
```

Reject is distinct from cancellation. An interrupted Run holds no API request,
connection, worker slot, or lease while waiting.

## 5. Usage allowance surface

The UI shows remaining monthly usage allowance and an honest exhaustion state.
When the usage allowance is exhausted, depth-4 grading and assistant turns pause while ordinary
study and scheduling continue.

## 6. Capabilities that may not be cut

- A delivered item cannot be submitted twice.
- Job polling treats the receipt as the state, and a missing receipt means retry.
- An assistant stream failure renders a terminal error rather than hanging.
- Approval is reconstructible after reload and supports all four decisions.
- Stage name derives from depth; strength is shown separately.
- The study loop remains keyboard-operable with visible focus.

## 7. Invariants for the checklist

```text
a delivered item cannot be submitted twice
a break renders as a server-named state
free-text success returns a verdict with no pending state
free-text timeout leaves the item answerable
a durable job reaches terminal UI state through polling
a failed assistant turn renders a terminal error, not an indefinite spinner
an approval popup survives reload and offers approve/edit/reject/respond
reject continues the turn and the assistant receives the refusal
stage name changes with depth and not with strength
the study loop is keyboard-operable with visible focus
```

The older list's `no token is reachable from client JavaScript`,
`an unsafe request without CSRF is rejected` and `five tabs refreshing produce one
rotation` are **withdrawn**. Clerk's SDK holds the session in the browser and
attaches it explicitly, so there is no cookie to protect from JavaScript, no CSRF
surface, and no refresh for this app to coordinate.

## 8. Golden journey

```text
sign in
  -> create a folder and a deck
  -> add a word and poll its generation job to completion
  -> study exposure, graded recall, wrong answer, ungraded re-ask, break,
     and a synchronously graded free-text answer
  -> recap with every submitted answer settled
  -> open the assistant, stream a turn, reload at approval,
     approve the destructive action, and see the resumed result
```

The browser half of this journey is **not yet automated**: Phase 14 is blocked on a
Clerk test instance. See
[the phase file](../../plans/260924-0608-pycil-complete-redesign/phase-14-browser-journeys.md).
