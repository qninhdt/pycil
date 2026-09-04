---
phase: 4
title: "Realtime"
status: pending
priority: P1
effort: "2-3d"
dependencies: [1]
---

# Phase 4: Realtime

## Overview

Three channel families with independent history policy, and a subscribe proxy that
authorizes each namespace against the fact that owns it. Today one namespace is
hard-coded and the gateway config declares one snapshot-shaped policy — which is
right for a job snapshot and wrong for a token stream.

Independent of phase 3: disjoint modules, either order.

## Requirements

**Functional**

- Three namespaces (`E2`): `personal:#<userId>` server-subscribed at connect,
  `job:<jobId>`, `thread:<threadId>`.
- Per-namespace history (`E4`): `job` size 1 short TTL; `thread` bounded short TTL;
  `personal` bounded and recoverable.
- A subscribe proxy dispatching **per namespace** (`E8`), authenticating the gateway
  itself, parsing a strict channel format, revalidating the token version, and
  failing closed.
- Subscription expiry **clamped to the shorter** of the token expiry and the
  authorizing fact's expiry.
- The authorizing fact and its expiry read **in one row** — selecting the expiry
  alone makes "no interest" and "an interest with no deadline" indistinguishable.
- Revocation calls the gateway's server API and logs a failure (`E9`).
- A realtime token separate from the API token, with its own secret and audience
  (`H13`).

**Non-functional**

- Publication is best-effort; the gateway being down never fails a mutation.
- The edge excludes the realtime path from compression and disables buffering
  (`O2`).

## Architecture

```text
POST /v1/realtime/token       cookie auth → a short-lived realtime-only token
                              subject, fixed algorithm, iss, aud, exp

gateway validates signature, algorithm, issuer, audience, expiry, exact origin

on each subscribe → internal proxy
  authenticate the gateway itself (shared secret, not reachable from the edge)
  parse a strict channel format
  revalidate the user and token version
  dispatch:
    personal:#<id>   → the connection subject IS the check
    job:<id>         → a live unexpired interest for this requester
    thread:<id>      → thread ownership
  return the current snapshot where one exists
  clamp expire_at to min(token, authorizing fact)
  otherwise fail closed
```

**Why the namespaces are split rather than merged.** With one shared namespace a
long agent reply evicts job frames a client still needs. That is also why the
`thread` policy cannot be the `job` policy: reconnecting mid-generation against a
size-1 buffer recovers nothing.

**Why no subscription tokens.** A valid subscription token *is* an authorization
decision and short-circuits the proxy entirely.

## Related Code Files

**Create**

- `apps/api/pycil/realtime/channels.py` — strict parse and build per namespace
- `apps/api/pycil/realtime/authorizers.py` — one authorizer per namespace, dispatched

**Modify**

- `apps/api/pycil/realtime/subscriptions.py` — replace the single hard-coded prefix
  with dispatch; keep the expiry clamp and the one-row read, both of which are
  already correct and both of which have a recorded reason
- `apps/api/pycil/realtime/router.py` — the token endpoint under cookie auth
- `centrifugo-config.json` — three namespaces with distinct history policy
- `Caddyfile` — keep the non-compression carve-out and unbuffered proxy; verify the
  path set still matches after the namespace change
- `packages/shared-py/shared/realtime/channels.py` — the builders for three families

## Implementation Steps

1. Write `channels.py`: build and **strict** parse for each family. A name that does
   not match exactly is a rejection, not a loose parse.
2. Write one authorizer per namespace and dispatch on the parsed family.
3. Rewrite `subscriptions.py` around the dispatch, preserving the expiry clamp and
   the single-row read of the fact and its deadline.
4. Add the three namespace blocks to the gateway config with their history policy.
5. Move the token endpoint to cookie auth and confirm the audience the gateway
   expects matches what is signed.
6. Wire revocation into logout and account deletion, logging failure.
7. Verify the edge configuration with the gateway's and the edge's own validators —
   both are mounted files that fail at runtime rather than at parse time.
8. **Read the gateway's startup log** for unknown-variable warnings. It warns rather
   than failing on a misspelt configuration name, so a rename is silently inert
   until something downstream breaks with no explanation.

## Todo

- [ ] `channels.py`: build and strict parse, three families
- [ ] One authorizer per namespace
- [ ] Dispatch replaces the hard-coded prefix
- [ ] Preserve the expiry clamp and the one-row read
- [ ] Three namespace blocks with distinct history
- [ ] Token endpoint under cookie auth
- [ ] Revocation wired into logout and deletion, logged
- [ ] Edge and gateway configuration validated
- [ ] Startup log read for unknown-variable warnings
- [ ] `realtime.md` §12 covered by named tests

## Success Criteria

- [ ] Subscribing to another learner's thread → denied
- [ ] Subscribing to a job with no live interest → denied
- [ ] A stale token version → denied
- [ ] The internal endpoint without its shared secret → rejected
- [ ] A malformed channel name → denied, not loosely parsed
- [ ] Subscription expiry never exceeds the authorizing fact's expiry
- [ ] An interest with no deadline is not treated as absent
- [ ] Revocation closes an established subscription
- [ ] The gateway down: the mutation commits and is readable over HTTP
- [ ] A job snapshot replays on subscribe
- [ ] Three namespaces carry three distinct history policies
- [ ] The startup log shows no unknown-variable warning
- [ ] `realtime.md` §12 fully covered by named tests

## Risk Assessment

**The gateway warns instead of failing on a misspelt configuration name.** This has
already cost real time once: four variables were silently inert, and the expensive
one was the proxy secret — without that header the API rejects every authorization
call and **no channel can be subscribed at all**, with nothing in the failure path
saying why. Signal: subscribes fail with a generic denial while the API looks
healthy. Response: read the startup log after any rename, and treat step 8 as a gate
rather than a courtesy.

**Splitting namespaces without revocation is a security regression.** A revoked
reader keeps receiving frames on an already-established subscription. Signal: only
visible by testing revocation explicitly. Response: the revocation test is not
optional in this phase's criteria.

**The `thread` history TTL is a guess.** It must cover a reconnect of a few seconds,
not an hour offline. Signal: `recovered: false` arriving routinely rather than
occasionally. Response: the canonical HTTP read is the backstop by design, so a
too-short buffer degrades rather than breaks — tune after phase 9 gives real token
volume.

**Nothing subscribes to `thread` until phase 9.** Signal: none — expected. Response:
the namespace and its authorizer are testable without a producer, and that is what
this phase asserts.
