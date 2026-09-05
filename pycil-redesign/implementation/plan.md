---
title: "Pycil Redesign Implementation"
description: "Implement two-axis learning, inline assistant SSE, durable polled jobs, cookie auth, plans and credit."
status: pending
priority: P1
effort: ""
tags: [redesign, breaking-change, pre-production]
created: 2026-09-04
---

# Pycil Redesign Implementation

## Contract

- **Outcome** — the codebase matches `pycil-redesign/` and deploys to the VPS.
- **Constraints** — one developer, direct commits to `main`; this design folder
  governs; `lexi-ai` is edited and pinned as an embedded subproject; intermediate
  gates may be red but each phase's focused checks must pass.
- **Non-goals** — mobile, an observability stack, an assistant sandbox, a third
  plan tier, and a realtime gateway.
- **Acceptance** — the golden journey passes on a real stack, every named
  invariant has a test, the migration baseline creates the final schema, and
  deployment plus restore rehearsal complete.

## Sequence

```text
1  foundation   delete retired surface + one final schema baseline
2  messaging    Taskiq domain jobs + scheduler + reconciliation
3  auth         cookies, claims, identity, CSRF
4  delivery     assistant SSE + durable-job polling
5  learning     independent strength/depth + synchronous grading
6  content      Lexi contract + ahead-of-read supply
7  hierarchy    one readability query + bounded tree
8  account      plans, credit, export, deletion order
9  assistant    inline Runs, checkpoint HITL, tools, compaction
10 web          generated client, study and assistant panels
11 deploy       invariant gate, golden journey, backup/restore, ship
```

Foundation fixes the schema and deletion boundary first. Messaging and auth then
establish the shared contracts used by delivery. Learning, content, hierarchy,
and account settle the facades the assistant calls. Web follows stable APIs;
deployment follows a green gate.

## Phases

| # | Phase | Status |
|---|---|---|
| 1 | [Foundation](./phase-01-foundation.md) | Pending |
| 2 | [Messaging](./phase-02-messaging.md) | Pending |
| 3 | [Auth](./phase-03-auth.md) | Pending |
| 4 | [Direct Delivery](./phase-04-delivery.md) | Pending |
| 5 | [Learning](./phase-05-learning.md) | Pending |
| 6 | [Content](./phase-06-content.md) | Pending |
| 7 | [Hierarchy](./phase-07-hierarchy.md) | Pending |
| 8 | [Account](./phase-08-account.md) | Pending |
| 9 | [Assistant](./phase-09-assistant.md) | Pending |
| 10 | [Web](./phase-10-web.md) | Pending |
| 11 | [Deploy](./phase-11-deploy.md) | Pending |

## Dependencies

```text
1 -> 2 -> 3 -> 4 -------------------+
|         |                         |
+-> 5 -> 6 -------------------------+-> 9 -> 10 -> 11
+-> 7 -> 8 -------------------------+
```

## Success criteria

- [ ] One Pycil migration baseline creates the final schema on empty Postgres.
- [ ] Taskiq uses Redis Streams for domain jobs; Postgres is canonical and the
  scheduler recovers lost dispatch.
- [ ] Cookie and bearer auth reject ambiguity and validate required JWT claims.
- [ ] Jobs use owner-authorized polling; assistant create/resume use direct SSE.
- [ ] No Centrifugo, transactional outbox, publication relay, or assistant worker
  remains.
- [ ] Strength and depth persist independently; free-text grading is synchronous.
- [ ] Assistant approval supports approve/edit/reject/respond and waits without
  holding a request or execution slot.
- [ ] Credit debits once and exhaustion degrades learning rather than blocking it.
- [ ] Every invariant has a named test and the golden journey passes.
- [ ] The tested image digest deploys and the complete Postgres restore is rehearsed.

## Open questions

Phase 6 must settle whether per-demand item count remains in the Lexi contract and
whether item exclusion is session-scoped or durable across sessions.
