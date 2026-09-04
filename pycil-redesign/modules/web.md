# modules/web

The browser client. UI only. Decisions `I1`–`I5`, `H1`.

Holds no credential, proxies nothing, and owns no business rule.

## 1. What changes, and why it is one change

`I1`. The client had a server-side data layer — server actions, a proxy, a sealed
session cookie, forwarded credentials — and **all of it existed for one reason**:
the token lived on the server, so the browser could not call the API.

With the browser holding an `HttpOnly` cookie against the same origin (`H1`), that
reason is gone. So the whole layer goes, not piece by piece but as a consequence:

```text
server-side session custody      →  the API sets cookies (H2)
server actions as a data layer   →  direct client calls
a proxy route per API surface    →  none
credential forwarding            →  none
hand-written DTO mirrors         →  generated from the OpenAPI document (I2)
a second generator for errors    →  the same generated client (H14)
```

One consequence needs a per-route decision rather than a global one: pages that
render on the server today read through that layer. Each becomes a client fetch
unless there is a specific reason to render it on the server — and `H1` allows a
narrowly justified server-rendered route, designed separately, not inherited by
default.

## 2. Generated, hand-written, and the line between

`I2`. The API's OpenAPI document is the contract; the client is generated from it.

| Generated | Hand-written |
|---|---|
| Request and response types | The transport wrapper (`I3`) |
| Endpoint functions | Query keys and cache policy |
| Error code enum | Error **presentation** — code to human message |
| — | The session state machine (`I5`) |
| — | Realtime subscription lifecycle |

A hand-written mirror of a server DTO drifts silently: nothing fails, the two just
stop meaning the same thing. And a second generated artefact for error codes is a
second source for one contract — with a staleness gate whose only job is to notice
they diverged, which is a gate that exists because the design has two answers.

The transport wrapper is the one thing generation cannot own, because it is
cross-cutting rather than per-endpoint (`I3`):

```text
credentials: include            the cookie travels; nothing reads it
CSRF token on unsafe methods    plus the API's origin check (H11)
RFC 9457 error envelope         parsed once, not per call site
idempotency key                 on every command that creates work
request id                      propagated for correlation
refresh serialisation           one refresh in flight across tabs
```

Refresh serialisation belongs here and nowhere else. The server rotates atomically
under a row lock regardless (`H8`), but a client that fires five refreshes from five
tabs turns a correct server into five replay classifications.

## 3. Study

The client renders one question at a time and holds **no** scheduling logic. Every
decision — which sense, which level, which item, whether a round ended — is the
server's, delivered in the response to "next".

`I5`. The state machine mirrors only what the server still has. With checkpoints,
retry budgets, and priority tiers gone (`B9`), the client loses the same state:

| Keeps | Loses |
|---|---|
| Current item, its render shape | checkpoint index, retry counter |
| Round index and items served, for the indicator | tier, priority, open-failure round |
| Break as a real state to render | client-side round arithmetic |
| Submitted-once guard per item | — |
| Pending-grade panel | — |

Two behaviours are worth naming because they look like edge cases and are the
common path:

**A break is a state, not a toast.** The server names the round being entered, so
the client renders a break screen rather than counting items and guessing.

**A pending grade is a state, not a spinner.** Free-text answers return a receipt;
the verdict arrives over the realtime channel, and the session **completes with one
still pending** (`modules/learning.md` §9). The recap shows it as being graded and
updates in place. If the realtime frame is missed, the canonical read is the
fallback (`E5`).

Deleted with the server model: the component whose only job was to warn a learner
that a correct answer would be recorded as a miss. Under `B7` there is nothing left
to apologise for.

## 4. Two numbers, two meanings

`I4`. Strength and depth are independent (`B1`), so the UI shows two things and
must not blur them:

| | Source | Rendered as |
|---|---|---|
| **Strength** | FSRS stability | a percentage, and the next review time |
| **Depth** | `depth_level` | the stage name |

Stage names are **rendered from depth**, not from strength. That is the correctness
half of `B13`: five names in the language of depth, computed from a strength value,
promised a depth model and delivered a strength model wearing depth labels.

The band table has **one owner** — a constant on the server, from which the client's
copy is generated. It previously existed in four places, one of them a hand copy no
generator read and no check verified, which also cited a source path that did not
exist. Four copies of a table is three chances to disagree.

## 5. Realtime

One connection, opened once, multiplexing everything (`E1`). Not a connection per
job and not a connection per screen.

```text
connect            fetch a short-lived realtime token from the API, then connect
personal channel   subscribed server-side at connect
job channel        subscribed when the client starts waiting on a job
thread channel     subscribed when a conversation is open
```

Three client obligations:

- **Reconcile by version, not by arrival.** Snapshots carry a version; an older one
  is ignored. Without this, a replayed frame can move state backwards.
- **Treat `recovered: false` as normal** and refetch canonical state (`E7`). It is
  a bounded buffer; being outrun is expected, not exceptional.
- **Bound the subscription set.** The jobs in flight and the thread that is open —
  not everything ever touched.

## 6. Agent panel

Streams tokens, tool activity, and lifecycle from the thread channel. `runId`
travels in the payload, so a new turn is **not** a new subscription (`E3`).

Approval is a **popup in the panel** (`G10`) — not a message in the transcript, not
a separate page:

```text
approval.required frame
  → render the popup: what will happen, to what
       Approve → resume with approve → the tool executes
       Reject  → resume with reject  → the agent receives it and continues
```

Reject is not cancel. The agent learns it was refused and can propose something
else, which is why the transcript keeps flowing afterwards.

A run interrupted for approval **holds no worker slot** (`G11`), so the panel may
sit on an open popup indefinitely without occupying capacity. Reopening the app
mid-approval reads the run's state and re-renders the popup — the state is in the
checkpoint, not in the client.

## 7. Credit surface

Two places, and only two:

- **A balance with a human estimate** (`P6`) — "≈ 120 writing checks", not a raw
  number alone.
- **An honest exhaustion state.** When credit runs out, the learner is told writing
  checks are paused and that scheduling continues normally (`P10`). Not an error,
  not a modal blocking study.

Depth 4 becoming unavailable is **not** surfaced as a failure. Serving falls to a
lower level, the answer still counts, and the stage simply stops advancing — which
is the same thing the UI already shows when supply is thin.

## 8. What is not here

| Absent | Why |
|---|---|
| A story gallery in the gate (`N11`) | It asserted nothing: no runner installed, its accessibility check set to report-not-fail, no story carrying an assertion. Component behaviour is proven in the golden journey or in unit tests of pure logic |
| A design-system lint | Its own header listed what it could not catch — contrast, anything outside two directories, composed class names, token misuse, dark-mode parity. A green gate reading as "the design system holds" is the failure mode |
| A component library beyond what is used | Registry surface, not authored code. Fresh authoring pulls fewer parts |
| Client-side scheduling logic | The server decides. A second implementation is a second answer |
| Any credential in JavaScript | No local storage, no session storage, no in-memory custody (`H6`) |

## 9. Capabilities that may not be cut

Per R4:

- No credential reachable from JavaScript.
- CSRF token on every unsafe method.
- One refresh in flight across tabs.
- Version-based reconciliation of realtime snapshots.
- `recovered: false` triggers a canonical refetch.
- One realtime connection, bounded subscriptions.
- Submitted-once guard per delivered item.
- Approval rendered before a destructive tool runs, reconstructible after a reload.
- Stage name from depth, strength shown separately.
- Keyboard operability and visible focus on the study loop — it is the surface a
  learner uses hundreds of times.

## 10. Invariants for the checklist

```text
no token is reachable from client JavaScript
an unsafe request without a CSRF token is rejected by the API
five tabs refreshing produce one rotation
an out-of-order snapshot does not move state backwards
recovered:false triggers a canonical refetch
one realtime connection serves personal, job, and thread
a delivered item cannot be submitted twice
a break renders as a state named by the server
a session completes with a grade still pending, and the recap updates in place
an approval popup survives a reload mid-approval
reject continues the run; the agent receives the refusal
the stage name changes with depth and not with strength
exhausted credit shows a paused state, not an error
the study loop is operable by keyboard with visible focus
```

## 11. Golden journey

The one end-to-end path (`N2`), and the client half of it:

```text
sign in
  → create a folder, then a deck inside it
  → add a word: request generation, watch the job frame arrive
  → study the deck: exposure, a graded item, a wrong answer, its ungraded re-ask,
    a break, a free-text answer that returns a receipt
  → recap, with one answer still being graded
  → open the agent, ask it to rename the deck, approve a deletion it proposes
```

Everything else is a unit test of pure logic or an invariant above.
