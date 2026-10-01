---
phase: 2
title: "Messaging and Durable Jobs"
status: pending
priority: P1
effort: "2-3d"
dependencies: [1]
---

# Phase 2: Messaging and Durable Jobs

## Outcome

Replace the previous queue with Taskiq over Redis Streams for domain jobs only.
Make Postgres rows canonical and recover a lost enqueue through a separate
scheduler process.

## Requirements

- One `jobs` queue and one `domain-worker` process.
- Broker payload contains only `job_id`.
- Conditional durable claim commits and increments `attempt` before acknowledgement.
- `attempt` is the only retry counter; terminal failure is readable in Postgres.
- Commands create or join a job, commit, enqueue best-effort, and return a receipt.
- Scheduler heartbeat, dispatch reconciliation, and retention run outside worker
  slots.
- Shared work keys are server-derived; requester interests authorize job reads.
- No outbox, publication event, relay, assistant queue, or grading queue.

## Implementation

1. Configure Taskiq `RedisStreamBroker` and the single domain worker entrypoint.
2. Implement job create/join, interest creation, conditional claim, transitions,
   bounded retry, and terminal reads.
3. Enqueue the id after commit; make the scheduler redispatch pending rows.
4. Move periodic heartbeat and retention work into the scheduler entrypoint.
5. Implement owner-authorized job reads for Phase 4.
6. Remove the old queue library, outbox/event/receipt publication machinery, and
   assistant or grade tasks.

## Success criteria

- [ ] Duplicate delivery produces one claim and no duplicate effect.
- [ ] Broker loss after commit leaves a readable receipt and scheduler recovery.
- [ ] Payload carries only the id.
- [ ] A client cannot choose a work key.
- [ ] Two word requests join one job and both requesters may read it.
- [ ] One round's supply is generated once.
- [ ] Bounded attempts end in a readable terminal row.
- [ ] Periodic work runs while domain-worker slots are saturated.
- [ ] No outbox, relay, assistant queue, or pending-grade queue remains.
