---
phase: 10
title: "Web"
status: pending
priority: P1
effort: "4-5d"
dependencies: [9]
---

# Phase 10: Web

## Overview

Rebuild the client against the settled API: a generated client instead of
hand-written mirrors, one realtime connection, the session machine shrunk to what the
server still owns, and stage names sourced from depth. Last before deploy, precisely
so a route shape can still change cheaply.

The BFF is already gone from phase 1, so nothing here is a deletion of scale — it is
reconstruction of the data layer that replaced it.

## Requirements

**Functional**

- Client and DTOs **generated** from the OpenAPI document (`I2`); the error enum comes
  from the same generator (`H14`).
- One hand-written transport wrapper (`I3`): credentials, CSRF, the Problem Details
  envelope, an idempotency key, a request id, and **refresh serialised across tabs**.
- The session machine mirrors only what the server has (`I5`) — no checkpoint index,
  no retry counter, no client round arithmetic.
- A break is a **state the server names**; a pending grade is a **state**, and the
  session completes with one still pending.
- Stage names render from `depth_level` (`I4`); the band table has one owner, and the
  client's copy is generated from it.
- One realtime connection multiplexing personal, job, and thread; reconcile by
  **version**, treat `recovered: false` as normal, bound the subscription set.
- Agent panel: tokens from `thread:<threadId>`, `runId` in the payload, and a
  **popup** for approval that survives a reload.
- Credit surface in two places only: a balance with a human estimate, and an honest
  exhaustion state that is not an error.

**Non-functional**

- No credential reachable from JavaScript.
- Keyboard operability and visible focus on the study loop.

## Architecture

```text
generated                          hand-written
  request/response types             transport wrapper
  endpoint functions                 query keys and cache policy
  error code enum                    error presentation (code → message)
                                     session state machine
                                     realtime subscription lifecycle
```

**Why the wrapper is not generated.** It is cross-cutting rather than per-endpoint.
Refresh serialisation belongs there and nowhere else: the server rotates atomically
under a row lock regardless, but a client firing five refreshes from five tabs turns
a correct server into five replay classifications — and a replay outside the grace
window revokes the family.

**Two numbers, two meanings** (`I4`):

| | Source | Rendered as |
|---|---|---|
| Strength | FSRS stability | a percentage, and the next review time |
| Depth | `depth_level` | the stage name |

This is the correctness half of `B13`. Five names in the language of depth, computed
from a strength value, promised a depth model and delivered a strength model wearing
depth labels.

**Approval is a popup, not a message.** The decision is a control interaction. A run
interrupted for approval holds no worker slot, so the panel may sit on an open popup
indefinitely; reopening the app mid-approval reads the run state and re-renders it —
the state is in the checkpoint, not in the client.

## Related Code Files

**Create**

- `apps/web/lib/api/generated/` — from the OpenAPI document; committed, not built at
  install
- `apps/web/lib/api/request.ts` — the surviving wrapper, rewritten for cookies
- `apps/web/components/agent/approval-popup.tsx`
- `apps/web/lib/realtime/connection.ts` — one connection, three subscription kinds

**Modify**

- every page under `app/(app)/` — direct client fetches; per-route decision on whether
  any genuinely needs server rendering (`H1` permits a narrowly justified one)
- `apps/web/lib/study/session-machine.ts` — shrink with the server model
- `apps/web/lib/design/mastery.generated.ts` — re-keyed to `depth_level`, generated
  from the server constant
- `apps/web/lib/stores/` — the agent store rewritten against the event contract
- `apps/web/components/study/` — remove the fallback warning component; re-source the
  stage name
- `apps/web/components/settings/` — the credit surface

**Delete**

- `apps/web/lib/api/types/` — hand-written mirrors
- `apps/web/lib/api/error-codes.generated.ts` — the second generator's output
- `apps/web/lib/api/handle-api-error.ts`, `errors.ts` — superseded by the envelope

## Implementation Steps

1. Generate the client from `/v1/openapi.json`. Commit the output so a build needs
   neither the generator nor the running API.
2. Rewrite `request.ts` for cookies: `credentials: include`, the CSRF header on unsafe
   methods, Problem Details parsed once, an idempotency key on every command, and
   refresh serialised with a single in-flight promise shared across tabs.
3. Convert each page from a server action to a client fetch. Decide per route whether
   any needs server rendering, and record the justification where it does.
4. Shrink the session machine: drop the checkpoint index, the retry counter, and the
   round arithmetic. Keep the current item, the round indicator, the break state, the
   submitted-once guard, and the pending panel.
5. Re-source the stage name from `depth_level`, and regenerate the band table from the
   server constant. Delete the hand copy.
6. Write `connection.ts`: one connection, subscribe personal at connect, job when
   waiting, thread when a conversation opens. Reconcile by version; on
   `recovered: false`, refetch canonical state.
7. Rewrite the agent store against the event contract, with `runId` from the payload
   rather than from the channel.
8. Write the approval popup, reading its content from the interrupt payload and
   reconstructible after a reload from the run state.
9. Add the credit surface: a balance with a human estimate, and an exhaustion state
   that reads as paused rather than failed.
10. Delete the hand-written mirrors and the second generator's output.
11. Rewrite the surviving browser spec as the golden journey.

## Todo

- [ ] Client generated from the OpenAPI document, committed
- [ ] `request.ts` for cookies, with refresh serialisation
- [ ] Every page converted; server-rendered exceptions justified
- [ ] Session machine shrunk
- [ ] Stage name from depth; band table generated from one owner
- [ ] One realtime connection, three subscription kinds
- [ ] Version reconciliation; `recovered: false` refetches
- [ ] Agent store on the event contract
- [ ] Approval popup, reload-safe
- [ ] Credit surface
- [ ] Hand-written mirrors and the second generator deleted
- [ ] Golden journey written
- [ ] `web.md` §10 covered by named tests

## Success Criteria

- [ ] No token reachable from client JavaScript
- [ ] An unsafe request without a CSRF token is rejected by the API
- [ ] Five tabs refreshing produce one rotation
- [ ] An out-of-order snapshot does not move state backwards
- [ ] `recovered: false` triggers a canonical refetch
- [ ] One connection serves personal, job, and thread
- [ ] A delivered item cannot be submitted twice
- [ ] A break renders as a state the server named
- [ ] A session completes with a grade pending; the recap updates in place
- [ ] An approval popup survives a reload mid-approval
- [ ] Reject continues the run; the agent receives the refusal
- [ ] The stage name changes with depth, not with strength
- [ ] Exhausted credit shows a paused state, not an error
- [ ] The study loop is operable by keyboard with visible focus
- [ ] `web.md` §10 fully covered by named tests

## Risk Assessment

**A generated client can drift from a hand-written call site quietly.** Signal: a
type error at build. Response: that is the improvement — the failure moves from
runtime to build. The real risk is committing generated output that was produced from
a stale document, so regeneration belongs in the same commit as any API change.

**Refresh serialisation is easy to get almost right.** A per-tab lock is not enough;
tabs do not share memory. Signal: unexplained forced re-authentication under multi-tab
use. Response: the mechanism must be shared across tabs, and "five tabs, one rotation"
is a success criterion rather than a note.

**Approval reconstruction after a reload is the piece most likely to be skipped.**
Signal: a reload during approval loses the popup and the run appears stuck. Response:
the state is in the checkpoint, so reconstruction is a read — but only if the run read
returns the interrupt payload, which is a phase-9 dependency worth verifying here.

**Converting every page at once is a large surface.** Signal: pages that authenticate
but render nothing. Response: the golden journey covers the path that matters, and it
is written in this phase rather than assumed from the previous suite.

**The client cannot be finished before the API settles.** That is why this phase is
tenth. Signal: needing an API change while converting. Response: change it — a route
shape is still cheap here, and this ordering exists to make that true.
