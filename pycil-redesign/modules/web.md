# modules/web

The browser client. UI only. Decisions `I1`–`I5`, `H1`.

It holds no credential reachable from JavaScript, proxies nothing, and owns no
business rule.

## 1. Direct API client

The API sets first-party `HttpOnly` cookies and the browser calls FastAPI on the
same public origin. Server actions, proxy routes, sealed web sessions, credential
forwarding, and handwritten DTO mirrors are deleted.

| Generated from OpenAPI | Hand-written |
|---|---|
| Request and response types | Transport wrapper |
| Endpoint functions | Query keys and cache policy |
| Error code enum | Human error presentation |
| — | Study state machine |
| — | Assistant SSE parser and reconnect UI |
| — | Durable-job polling |

The wrapper includes credentials, adds CSRF and idempotency headers to unsafe
requests, parses RFC 9457 errors, propagates request ids, and serializes refresh
across tabs.

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

Assistant creation and resume requests return SSE directly from FastAPI. The
parser handles lifecycle, message, thinking, tool, approval, error, and terminal
frames. A dropped connection does not imply completion: the panel reads the Run
and Thread state and renders the durable result or interruption.

## 4. Assistant panel

An approval interrupt closes the first stream and renders a popup from durable
checkpoint state. Reloading reconstructs the same popup. A decision starts a new
resume request:

```text
approve -> execute the proposed tool call
edit    -> execute the corrected tool call
reject  -> give the refusal to the assistant and continue
respond -> give the user's response to the assistant and continue
```

Reject is distinct from cancellation. An interrupted Run holds no API request,
connection, worker slot, or lease while waiting.

## 5. Credit surface

The UI shows a balance with a human estimate and an honest exhaustion state.
When credit runs out, depth-4 grading and assistant turns pause while ordinary
study and scheduling continue.

## 6. Capabilities that may not be cut

- No credential is reachable from JavaScript.
- CSRF is attached to every unsafe method.
- One refresh is in flight across tabs.
- A delivered item cannot be submitted twice.
- Job polling treats Postgres snapshots as canonical.
- SSE interruption is repaired by Run and Thread reads.
- Approval is reconstructible after reload and supports all four decisions.
- Stage name derives from depth; strength is shown separately.
- The study loop remains keyboard-operable with visible focus.

## 7. Invariants for the checklist

```text
no token is reachable from client JavaScript
an unsafe request without CSRF is rejected
five tabs refreshing produce one rotation
a delivered item cannot be submitted twice
a break renders as a server-named state
free-text success returns a verdict with no pending state
free-text timeout leaves the item answerable
a durable job reaches terminal UI state through polling
a dropped assistant stream reconciles from canonical Run and Thread state
an approval popup survives reload and offers approve/edit/reject/respond
reject continues the Run and the assistant receives the refusal
stage name changes with depth and not with strength
the study loop is keyboard-operable with visible focus
```

## 8. Golden journey

```text
sign in
  -> create a folder and a deck
  -> add a word and poll its generation job to completion
  -> study exposure, graded recall, wrong answer, ungraded re-ask, break,
     and a synchronously graded free-text answer
  -> recap with every submitted answer settled
  -> open the assistant, stream a turn, reload at approval,
     edit or approve the destructive action, and see the resumed result
```
