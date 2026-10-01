---
phase: 9
title: "Assistant"
status: pending
priority: P1
effort: "4-5d"
dependencies: [3, 4, 6, 7, 8]
---

# Phase 9: Assistant

## Outcome

Run the LangGraph assistant inline in FastAPI with durable Run rows, direct SSE,
checkpoint-owned approval state, cancellation, compaction, and guarded tools.

## Requirements

- One active Run per Thread, enforced by a unique partial index and `409`.
- Create and resume requests execute the graph inline and stream SSE.
- Durable status is `pending`, `running`, `interrupted`, `success`, `error`, or
  `cancelled`; deadline failures use `error_code`.
- No worker queue, lease, fence, heartbeat, reaper, `partial_output`, action table,
  action audit, or persisted event stream.
- Cancellation is a column checked at yield points.
- Approval uses `interrupt()` and supports approve, edit, reject, and respond.
- Interrupt closes the request; resume is a second request using
  `Command(resume=...)`.
- Compaction is context-ratio based and never splits a tool call from its result.
- External strings are structurally wrapped; tools re-check ownership on execute.
- Prompt prefix is stable and cache-read tokens are logged.

## Implementation

1. Rename the module to `assistant` and reduce persistence to Threads and Runs.
2. Implement admission, status transitions, cancellation, and canonical reads.
3. Execute create/resume inline under per-learner and application deadlines.
4. Stream the shared SSE contract and persist terminal/interrupted state before
   closing.
5. Replace action records with checkpointer interrupts and all four decisions.
6. Add compaction, external-data wrapping, stable prompt construction, and cache
   telemetry.
7. Delete the assistant worker, queue, leases, fences, reaper, partial output,
   action subsystem, and event cursor API.

## Success criteria

- [ ] A second active Run on one Thread returns `409`.
- [ ] Create and resume execute in the API process and stream valid SSE.
- [ ] Cancellation stops at the next yield point and ends `cancelled`.
- [ ] Interrupt persists state, closes the stream, and holds no execution slot.
- [ ] Reload reconstructs approval; all four decisions resume correctly.
- [ ] A destructive tool cannot execute before approval and re-checks ownership.
- [ ] Compaction preserves tool-call/result pairs.
- [ ] Injected external text cannot bypass destructive approval.
- [ ] No assistant queue, worker, lease, fence, reaper, action table, event table,
  or `partial_output` remains.
