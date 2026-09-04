---
title: "Pycil Redesign Implementation"
description: "Bring the codebase in line with pycil-redesign/ — two-axis learning, agent in a worker, Taskiq, cookie auth, three realtime namespaces, plans and credit."
status: pending
priority: P1
effort: ""
tags: [redesign, breaking-change, pre-production]
created: 2026-09-04
---

# Pycil Redesign Implementation

## Overview

Execute the design in [`../`](../) — this plan is the **sequence**, that folder is
the **authority**. Where a phase and the design disagree, the design wins and the
phase is wrong.

Pre-production, so breaking changes are free. Committing directly to `main`, so
the gate is expected to be red while phases are in flight and must be green
before the first deploy (phase 11).

Full contract:

- **Outcome** — the codebase matches `pycil-redesign/`: two-axis learning, the
  agent running in a worker on its own queue, Taskiq over Redis Streams, cookie
  auth with no BFF, three realtime namespaces, plans and credit, and the invariant
  checklist as the gate. Deployable to the VPS.
- **Constraints** — one developer, direct commits to `main`. `pycil-redesign/`
  governs. `lexi-ai` is a sub-project: edit it directly and bump the pin (the gap
  is one commit). A red gate is permitted mid-flight, required green before deploy.
- **Non-goals** — mobile (`Q14`), observability (`Q1`), agent sandbox (`Q6`), a
  third plan tier (`Q8`). The three `uncalibrated` values (`P12`) stay `judgment`.
- **Acceptance** — the golden journey green on a real stack · every invariant line
  in the eleven design files has a named test · `docs/`, `plans/`, and the five
  root design documents deleted with nothing citing them · `deploy.sh` runs to
  completion.

## Strategy

Foundation first, then vertical by dependency. Phase 1 is almost entirely
**deletion plus one squashed schema**, which is why it is cheapest to abandon: if
a later phase proves a design decision wrong, the work already done keeps its
value.

The ordering constraint that shaped everything: `A6` squashes the migration chain
to one baseline, and that baseline must contain the **final** schema — every new
column, every rename, every drop. So schema is decided in phase 1 from the design
rather than discovered incrementally, and later phases build on a chain of one.

```text
1  foundation      delete + one squashed baseline   ── everything depends on it
2  messaging       Taskiq, scheduler, outbox        ── every async path
3  auth            cookies, claims, identity        ─┐ independent of each other
4  realtime        namespaces, subscribe proxy      ─┘
5  learning        two axes, sampling, re-ask
6  content         lexi contract + supply           ── needs 5's demand shape
7  hierarchy       one readability query, analytics
8  account         plan, credit, deletion order     ── needs 7 for deletion order
9  agent           durable Run, interrupt, prompt   ── needs 2,3,4,6,7
10 web             generated client, panels         ── needs every API stable
11 deploy          preconditions, journey, ship
```

## Goals

| # | Goal | Priority |
|---|------|----------|
| 1 | One authority: the design folder, with everything it retires deleted | P1 |
| 2 | One migration baseline holding the final schema | P1 |
| 3 | Two-axis learning: strength and depth, independently stateful | P1 |
| 4 | The agent as a durable Run in a worker, with approval intact | P1 |
| 5 | Cookie auth with no BFF, identity keyed on `(issuer, subject)` | P1 |
| 6 | Taskiq over Redis Streams, with periodic work outside the pool | P1 |
| 7 | Three realtime namespaces with per-namespace history policy | P1 |
| 8 | Plans and credit, degrading rather than blocking | P2 |
| 9 | The invariant checklist as the gate, and it is green | P1 |
| 10 | Deployable: production boots, restore has been rehearsed | P1 |

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Foundation](./phase-01-foundation.md) | Pending |
| 2 | [Messaging](./phase-02-messaging.md) | Pending |
| 3 | [Auth](./phase-03-auth.md) | Pending |
| 4 | [Realtime](./phase-04-realtime.md) | Pending |
| 5 | [Learning](./phase-05-learning.md) | Pending |
| 6 | [Content](./phase-06-content.md) | Pending |
| 7 | [Hierarchy](./phase-07-hierarchy.md) | Pending |
| 8 | [Account](./phase-08-account.md) | Pending |
| 9 | [Agent](./phase-09-agent.md) | Pending |
| 10 | [Web](./phase-10-web.md) | Pending |
| 11 | [Deploy](./phase-11-deploy.md) | Pending |

## Dependencies

```text
1 ──┬─► 2 ──┬─► 3 ──┐
    │       │       ├─► 9 ──► 10 ──► 11
    │       └─► 4 ──┤
    ├─► 5 ──► 6 ────┤
    └─► 7 ──► 8 ────┘
```

Phases 3 and 4 touch disjoint modules and may run in either order. Phase 5 needs
only the schema from phase 1. Phase 9 needs the checkpoint schema, the queue, the
realtime channel, and the facades it calls.

## Superseded plans

Ten plans are tracked and all are `pending`; every one is an execution record for
the design being replaced — including
`260805-1327-pycil-and-lexi-full-hexagonal-redesign`, whose output is the
three-tier module layout that `A2` flattens.

They are **not** `blockedBy` this plan, and they are **not deleted**. Phase 1
closes them: `plans/` stays in the tree as the record of what was built, demoted
from authority rather than erased. Same for `docs/`.

## Risks

| Risk | Signal it broke | Response |
|---|---|---|
| The squashed baseline omits a table a later phase needs | A phase cannot express its schema | Edit the baseline — pre-production, no data. Adding a revision on top of a just-squashed chain is the failure to avoid |
| A red gate for many phases hides a real regression | A phase's own suite cannot be made green | Each phase ends with its own suite green. The gate is red only for what has not been reached yet |
| Nine phases of design decisions turn out wrong at phase 10 | The generated client cannot express a route shape | The web phase is last precisely so the API has settled. A route change at that point is cheap; a schema change is not |
| `lexi-ai` edits break the pin | Its suite fails after the contract change | The gap is one commit. Run its suite before bumping (`N10`) |
| A retired root design document is still cited somewhere | A reader follows a link into a document that no longer describes the system | Phase 1 sweeps citations. `docs/` and `plans/` are kept, so only the five root documents create this risk |

## Success Criteria

- [ ] `pycil-redesign/` is the only design authority; nothing cites a retired document
- [ ] One migration baseline; `alembic upgrade head` on an empty database yields the final schema
- [ ] Taskiq over Redis Streams; periodic work in its own process
- [ ] Cookie auth, no BFF, identity on `(issuer, subject)`, `typ`/`iss`/`aud` validated
- [ ] Three realtime namespaces with distinct history policy; subscribe fails closed
- [ ] `depth_level` and `depth_streak` durable; the sampling table keyed on depth
- [ ] A correct answer never produces `Again` under any supply condition
- [ ] The agent runs in a worker; approval blocks a destructive tool; a paused Run holds no slot
- [ ] Credit debits once per operation; exhaustion degrades to a lower depth
- [ ] Every invariant line in the eleven design files has a named test
- [ ] The golden journey passes on a real stack
- [ ] `deploy.sh` runs to completion; restore has been rehearsed

## Open Questions

Two, both from `modules/content.md` §10, both product decisions that phase 6
must close deliberately rather than by accident:

1. **Is the per-demand item count honoured, or removed from the contract?**
   Honouring it needs a variation source per question type; the productive type
   has none short of a model call. Ignoring it silently is the current state and
   the worst of the three.
2. **May a learner meet the same item across sessions?** A durable exclusion set
   grows without bound; a session-scoped one lets an assessment be memorised.
