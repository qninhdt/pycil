---
title: "Pycil Redesign Implementation"
description: "Implement two-axis learning, inline assistant turns, durable polled jobs, Clerk identity, plans and credit."
status: superseded
priority: P1
effort: ""
tags: [redesign, breaking-change, pre-production]
created: 2026-09-04
---

# Pycil Redesign Implementation

> **Superseded as the execution record.** The redesign was executed as
> [`plans/260924-0608-pycil-complete-redesign/`](../../plans/260924-0608-pycil-complete-redesign/plan.md),
> an 18-phase plan that supersedes the eleven-phase sequence below. This file is
> kept because the per-phase detail under `implementation/` is still the reasoning
> behind several modules, but its phase table and status are **not** the current
> state — read the execution plan for that.

## Contract

- **Outcome** — the codebase matches `pycil-redesign/` and deploys to the VPS.
- **Constraints** — one developer, direct commits to `main`; this design folder
  governs; `lexi-ai` is edited and pinned as an embedded subproject; intermediate
  gates may be red but each phase's focused checks must pass.
- **Non-goals** — mobile, an observability stack, an assistant sandbox, a third
  plan tier, and a realtime gateway.
- **Acceptance** — the browser journeys pass on a real stack, every named
  invariant has a test, the migration baseline creates the final schema, and
  deployment plus restore rehearsal complete.

## Sequence

```text
1  foundation   delete retired surface + one final schema baseline
2  messaging    Taskiq content jobs + receipt
3  auth         Clerk verification + subject→UUID mapping
4  delivery     assistant SSE + durable-job polling
5  learning     independent strength/depth + synchronous grading
6  content      Lexi contract + ahead-of-read supply
7  hierarchy    one readability query + bounded tree
8  account      plans, credit, export, deletion order
9  assistant    inline turns, checkpoint HITL, tools, compaction
10 web          generated client, study and assistant panels
11 deploy       invariant gate, browser journeys, backup/restore, ship
```

Foundation fixes the schema and deletion boundary first. Messaging and auth then
establish the shared contracts used by delivery. Learning, content, hierarchy,
and account settle the facades the assistant calls. Web follows stable APIs;
deployment follows a green gate.

## Phases

| # | Phase | Status |
|---|---|---|
| 1 | [Foundation](./phase-01-foundation.md) | Superseded by execution phase 01 |
| 2 | [Messaging](./phase-02-messaging.md) | Superseded — no scheduler was built |
| 3 | [Auth](./phase-03-auth.md) | Superseded — Clerk replaced the local issuer |
| 4 | [Direct Delivery](./phase-04-delivery.md) | Delivered |
| 5 | [Learning](./phase-05-learning.md) | Delivered |
| 6 | [Content](./phase-06-content.md) | Delivered |
| 7 | [Hierarchy](./phase-07-hierarchy.md) | Delivered |
| 8 | [Account](./phase-08-account.md) | Delivered |
| 9 | [Assistant](./phase-09-assistant.md) | Delivered, minus the Run row |
| 10 | [Web](./phase-10-web.md) | Delivered |
| 11 | [Deploy](./phase-11-deploy.md) | Not executed here — see execution phases 15–18 |

Read the table as history, not as state. The authoritative status is in
[the execution plan](../../plans/260924-0608-pycil-complete-redesign/plan.md).

## Dependencies

```text
1 -> 2 -> 3 -> 4 -------------------+
|         |                         |
+-> 5 -> 6 -------------------------+-> 9 -> 10 -> 11
+-> 7 -> 8 -------------------------+
```

## Success criteria

- [x] One Pycil migration baseline creates the final schema on empty Postgres.
- [x] Taskiq uses Redis Streams for content jobs; Postgres is canonical for learner
  state. **No scheduler exists**; a failed publish is recorded failed and the
  learner retries.
- [x] Clerk bearer verification rejects ambiguity and validates issuer, audience,
  algorithm and expiry; authorization uses the internal UUID.
- [x] Jobs use owner-authorized polling; assistant turns and resumes use direct SSE.
- [x] No Centrifugo, transactional outbox, publication relay, or assistant worker
  remains.
- [x] Strength and depth persist independently; free-text grading is synchronous.
- [x] Assistant approval supports approve/edit/reject/respond and waits without
  holding a request or execution slot.
- [x] Credit debits once and exhaustion degrades learning rather than blocking it.
- [ ] Every invariant has a named test and the browser journeys pass.
- [ ] The tested image digest deploys and the complete Postgres restore is rehearsed.

## Resolved decisions

Phase 6 uses one public `PrepareDemand` per `(sense, level)`; any remaining count
is an internal worker round-budget field. Item exclusion is session-scoped, so
cross-session repetition remains a deliberate later policy decision.
