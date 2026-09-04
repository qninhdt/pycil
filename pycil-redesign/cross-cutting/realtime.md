# cross-cutting/realtime

One connection per client, three channel families, authorization per namespace.
Decisions `E1`–`E9`.

## 1. Transport

HTTPS for every command and query. **One** Centrifugo bidirectional connection
for server-to-client realtime: WebSocket primary, bidirectional SSE fallback
(`E1`).

Clients never send business commands over the realtime connection. Client publish
and client RPC stay disabled, so the emulation endpoint that bidirectional SSE
requires never becomes a command path.

`uni_sse` is not used: it cannot subscribe or unsubscribe after connect, and the
channel model below requires dynamic subscription `[R15]`.

SSE fallback and its emulation endpoint are **server features enabled by
configuration**. There is no Pycil code behind them.

## 2. Channels

`E2`. Three families, one connection:

```text
personal:#<userId>      connection lifetime      account events, control frames
job:<jobId>             job lifetime             word generation, supply, grading
thread:<threadId>       conversation lifetime    agent tokens, tools, lifecycle
```

`personal:#<userId>` uses the **user-limited channel form**: the separator binds
the channel to the authenticated connection's subject, so a client cannot widen it
by supplying a different name `[R16]`. It is the one family that cannot be
mis-scoped, and it is subscribed server-side at connect `[R20]`.

`thread:<threadId>` rather than a run-scoped channel (`E3`). A run-scoped channel
forces a fresh subscribe every turn, and each subscribe is an authorization
round-trip through the proxy. The run id travels in the payload instead. Isolation
is unchanged: a Thread belongs to one learner.

`job:<jobId>` may have **several authorized subscribers** — word generation is
shared work, so two learners waiting on the same word both receive it. Grading is
owner-scoped even though the channel shape is identical; the difference is in
authorization, not in the name.

## 3. Namespace policy

Each namespace needs its own history policy, and separate namespaces are what
make that possible (`E4`). With one shared namespace a long agent reply evicts job
frames a client still needs.

| Namespace | History | Recovery | Why |
|---|---|---|---|
| `personal` | on, bounded | on | A missed control frame must be recoverable |
| `job` | **size 1**, short TTL | on | Snapshot-shaped: only the latest state means anything |
| `thread` | bounded, **short TTL** | on | A dropped connection mid-generation must not lose produced tokens |

`job` at size 1 is deliberate and is the contract the client's reconciliation
depends on: replay the latest snapshot on subscribe, monotonic version, ignore
anything older.

`thread` is where the difference bites. A token stream needs more than one frame
of replay, and the buffer only has to cover a reconnect of a few seconds — not a
whole run. Bounded and short-lived on purpose.

All three enable the subscribe proxy and none enable client subscribe without it,
anonymous subscribe, client publish, or publish-by-subscriber (`E8`).

If token volume ever crowds the other namespaces, the response is a separate
Centrifugo deployment for `thread` — a scaling lever, not a redesign.

## 4. Recovery — two layers

```text
Layer 1   Centrifugo history + recovery
          bounded window, short TTL
          replays the gap in order, deduplicated, in the subscribe reply

Layer 2   a canonical HTTP read
          job:     GET /v1/jobs/{jobId}        or the owning resource
          thread:  GET /v1/agent/runs/{runId}  status + partial_output
          grading: GET /v1/responses/{id}      verdict + FSRS effect
```

Both are required (`E5`). Centrifugo's own documentation is unambiguous `[R18]`:

> "History is a cache, not your source of truth."
>
> It "can be empty, truncated, or lost at any moment."

The stated guidance is: keep streams small and short, **always keep a backend
fallback**, tolerate duplicates.

Layer 2 *is* that fallback. This is why there is no third layer (`Q4`) — a durable
event table with a cursor covers nothing Layer 2 misses and costs a table, an
endpoint, and sequence discipline. And it is why `partial_output` is **mandatory**
(`E6`): without it a reconnect mid-generation returns a running Run with an empty
body and the learner sees a blank pane.

The grading fallback follows the same rule and for the same reason. A learner who
loses their connection while free text is being graded must be able to read the
verdict over HTTP; the realtime snapshot is Layer 1 for that flow, not the answer.

### Three flags to handle correctly

| Flag | Meaning |
|---|---|
| `wasRecovering: true` | The client *attempted* recovery with a stored position. **Says nothing about success** |
| `recovered: true` | Continuity preserved. May arrive with zero replayed frames if the client was already at the top |
| `wasRecovering: true` + `recovered: false` | **Fetch canonical state.** Expected, not exceptional (`E7`) |

Recovery is never partial: rather than hand back a stream with a silent hole,
Centrifugo reports failure and replays nothing.

The **epoch** names one stream instance. If a stream is lost and recreated,
offsets restart — so a changed epoch tells the client its stored offset is
meaningless rather than letting it be trusted.

## 5. Connection authentication

```text
1  the browser calls POST /v1/realtime/token with its cookie
2  the API revalidates the user and the token version, then signs a
   short-lived realtime-only token: subject, fixed algorithm, issuer,
   audience, expiry
3  Centrifugo validates signature, algorithm, issuer, audience, expiry,
   and exact origin before accepting either transport
4  the client library refreshes the token through the API before it expires
```

The realtime token is **not** the API access token (`H13`). A realtime-token
compromise must not be an API compromise, so it is signed with a separate secret
and Centrifugo is configured with its own expected audience — it does not validate
audience or issuer by default.

Its TTL is short, and that TTL **is** the blast radius of a leaked connection
token: the token carries no revocation list, so revocation is the server API call
in §7, and expiry is the bound if that call is missed.

## 6. Subscribe authorization

Client subscribes are **denied by default** `[R16]`. Authorization goes through the
subscribe proxy, which makes Centrifugo consult the backend on every attempt
`[R17]`.

Centrifugo sends the authenticated subject, the exact channel, and connection
metadata. The proxy:

- authenticates **Centrifugo itself** with a shared secret — the endpoint is
  internal and must not be reachable from outside;
- parses a **strict** channel format, rejecting anything that does not match
  exactly;
- revalidates the user and token version, so a subscribe cannot outlive a
  revocation that has already happened;
- authorizes against the fact it owns;
- **fails closed.** Knowing an identifier grants no authority.

| Channel | Authorized by |
|---|---|
| `personal:#<userId>` | The connection subject. Not a lookup — the channel form is the check |
| `job:<jobId>` | A live, unexpired interest row for this requester |
| `thread:<threadId>` | Thread ownership |

The proxy returns the **current canonical snapshot** where one exists, which is
what closes the narrow race between a job's state changing and the client
subscribing.

Two details that are easy to get wrong and are load-bearing:

- The reply's expiry is **clamped to the shorter of** the token's expiry and the
  authorizing fact's expiry. Centrifugo enforces expiry on its own clock, so
  returning the token's value lets a subscription authorized one second before its
  interest lapsed run on for the token's full remaining life.
- Authorization reads the fact and its expiry **in one row**. Selecting the expiry
  alone makes "no interest" and "an interest with no deadline" indistinguishable,
  and treating the second as the first denies a valid reader.

**No subscription tokens** (`E8`). A valid subscription token *is* an
authorization decision and short-circuits the proxy entirely. If proxy load ever
demands them, they must be short-lived, bound to exactly one channel, and issued
through the same authorization path.

## 7. Revocation

Mandatory (`E9`). The personal channel cannot be mis-scoped, but thread ownership
and job interest change over time.

```text
access revoked
  → call the server unsubscribe/disconnect API for that user and channel
```

Without it, a revoked reader keeps receiving frames on an **already established**
subscription — which would make channel splitting a security regression rather
than an improvement. Expiring subscriptions with periodic revalidation may be
added on top.

The call is **best-effort and logged when it fails**, because that log is the only
signal that a socket outlived a revocation. Two callers need it: logout and
account deletion.

Bound the subscription set per connection: the jobs currently in flight and the
Thread currently open, not everything the learner has ever touched.

## 8. Publisher ownership

| Channel | Published by |
|---|---|
| `personal:` | The API, through the outbox relay |
| `job:` | The domain worker, through the outbox relay |
| `thread:` | The agent worker, directly |

Publication is **best-effort everywhere** (`E9`). Centrifugo being unavailable must
never fail a durable mutation — a committed business change stays visible over
HTTP even when its publication was lost, which is what makes Layer 2 the design's
backbone rather than its fallback.

Token deltas are the one flow with **no outbox** (`F5` applies only where the
message carries durable work): they are ephemeral, accompany no state change, and
`partial_output` plus the checkpoint is what makes them recoverable.

## 9. Engine and scale

Redis engine `[R19]`. Connections live in each node's memory; Redis carries
cross-node publication and history.

```text
client A  ──►  centrifugo node 1
publisher ──►  centrifugo node 2
                     │
                   redis
                     │
               node 1 delivers to client A
```

Adding nodes is configuration: they share one Redis and a client does not need to
know which node holds a connection. **Sticky sessions are not required** — though
an established connection stays attached to its node for that connection's
lifetime, and a reconnect may land anywhere healthy.

## 10. Edge configuration

Caddy is the only public ingress (`O2`), and two settings on the realtime path are
not optional:

- **exclude the realtime paths from compression.** Compression buffers, and a
  buffered publication is a publication that has not arrived.
- **disable proxy response buffering** for the same reason at the proxy layer
  `[R34]`.

The internal proxy endpoint is **not** exposed at the edge. Only the transport
paths are.

One-origin is load-bearing beyond tidiness (`H1`): the API hands the browser its
realtime URL verbatim, so a separate frontend origin makes every subscribe
cross-origin, requires an allowed-origin list to be maintained in lockstep, and
stops the session cookie being first-party.

## 11. Capabilities that may not be cut

Per R4:

- Subscribe denied by default, authorized per namespace, failing closed.
- The internal proxy endpoint authenticates Centrifugo itself.
- Subscription expiry clamped to the authorizing fact.
- Revocation calls the server API, and a failure is logged.
- Per-namespace history policy — one shared namespace is not equivalent.
- A canonical HTTP read behind every realtime flow.
- The realtime token is separate from the API token, with its own secret and
  audience.
- No compression and no buffering on the realtime path.

## 12. Invariants for the checklist

```text
subscribe to another user's thread → denied
subscribe to a job with no live interest → denied
subscribe with a stale token version → denied
the internal proxy endpoint without its shared secret → rejected
a malformed channel name → denied, not parsed loosely
subscription expiry never exceeds the authorizing fact's expiry
an interest with no deadline is not treated as absent
revocation closes an established subscription
Centrifugo unavailable → the mutation still commits and is readable over HTTP
recovered:false → the client refetches canonical state
a job snapshot replays on subscribe
```

## 13. To verify at implementation time

- The exact configuration keys for per-namespace history and for mapping a
  namespace to its proxy endpoint in the deployed version. Not assumed here.
- History size and TTL per namespace: they must cover a reconnect, not an hour
  offline `[R18]`.
- The realtime gateway **warns rather than fails** on an unrecognised
  configuration variable, so a misspelt key is silently inert. Any rename must be
  followed by reading the startup log — see [../ops/devops.md](../ops/devops.md).
