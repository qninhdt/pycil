---
phase: 2
title: "Messaging"
status: pending
priority: P1
effort: "3-4d"
dependencies: [1]
---

# Phase 2: Messaging

## Overview

Replace arq with Taskiq over Redis Streams, move periodic work into its own
process, and make the outbox the only path from a committed mutation to a
published message. Every asynchronous path in the product runs on this.

## Requirements

**Functional**

- Taskiq with `RedisStreamBroker` (`F1`) — the only Redis broker with consumer
  groups and acknowledgement.
- Two worker processes, two queues, different configuration (`G3`): domain jobs and
  agent runs.
- The four configuration rules: acknowledge after the durable claim (`F2`), retry
  **off** for runs (`F3`), payload is the id alone (`F3`), one authoritative attempt
  counter (`F4`).
- A scheduler process (`F9`) owning every periodic task.
- Outbox with an in-process relay in every replica, claiming with `SKIP LOCKED`
  (`F5`, `F6`).
- Each consumer declares its idempotency mechanism and has a test proving duplicate
  delivery causes no double effect (`F8`).
- Server-derived work keys; a client-supplied key is rejected (`C2`, messaging §8).

**Non-functional**

- Periodic work runs while the worker pool is saturated — this is the failure the
  scheduler split exists to prevent.
- Redis persistence on: a broker queue is durable work in flight.

## Architecture

```text
api ──┬─ BEGIN mutate + INSERT outbox COMMIT ──► 202 {id}
      └─ relay (in-process, every replica)
           claim FOR UPDATE SKIP LOCKED → publish → await ack → mark

redis streams
  queue "jobs"  ──► domain-worker   ack when_executed · retry on  · concurrency high
  queue "runs"  ──► agent-worker    ack when_received · retry OFF · bounded by admission

scheduler (own process)
  outbox relay tick · worker heartbeat · reconcile stuck jobs
  reconcile pending grades · run reaper · retention sweep
```

**Why acknowledgement timing differs.** An agent run acknowledges after its durable
claim so the broker holds nothing in flight for minutes; recovery is the reaper, not
redelivery. A domain job is short and idempotent, so acknowledging after execution
plus redelivery is the cleanest handling of a native crash.

**Why retry is off for runs.** Library retry restarts a task from its arguments,
which is a rerun from input — and the task is "resume this Run", not "run this
turn". Retry is opt-in per task in Taskiq, so "off" means not labelling it, and the
domain jobs that want it opt in explicitly.

**Why the scheduler is separate.** The heartbeat that gates readiness and the relay
that delivers realtime frames are periodic. Starved of a slot they fail silently:
readiness reports a failure that is not happening, and realtime delivery stops with
nothing saying so.

## Related Code Files

**Create**

- `apps/worker/pycil_worker/broker.py` — the Taskiq broker and both queue names
- `apps/worker/pycil_worker/scheduler.py` — `TaskiqScheduler` with its label source
- `apps/api/pycil/jobs/` — the module, renamed from `tasks` (flat, per `A2`)

**Modify**

- `apps/worker/pycil_worker/main.py` — registration replaces `WorkerSettings`
- every job under `apps/worker/pycil_worker/jobs/` — decorator and signature
- `packages/shared-py/shared/tasks/contract.py` → `shared/jobs/contract.py`, and
  **delete** the two re-export layers (removed #18: the outer has zero importers,
  the inner is bypassed by five modules)
- `apps/api/pycil/jobs/service.py` — claim, lease, fence, transition
- `docker-compose.yml` — add `scheduler` and `agent-worker`; `stop_grace_period` per
  worker, the agent one exceeding the run deadline (`O9`)

**Delete**

- `apps/worker/pycil_worker/context.py` — one `TypedDict` with optional keys
  replaces two bridged by a cast (removed #19)
- the cron registration block in `main.py` — the scheduler owns it now

## Implementation Steps

1. Add `taskiq`, `taskiq-redis`; remove `arq`.
2. Write `broker.py`: `RedisStreamBroker` with `queue_name` per class, consumer
   group, and the reclaim timeout that returns an unacknowledged message.
3. Convert each job: `@broker.task`, and **only** the ones that want retry get the
   label. Domain jobs opt in; the run task does not.
4. Write `scheduler.py` and move every periodic task to a schedule label.
5. Rename `tasks` → `jobs` across the API, and collapse the two re-export layers to
   a direct import of the contract.
6. Rewrite the claim path for the `attempt` counter as the single authority — remove
   any second counter, including the broker's own where it is consulted.
7. Rework the relay to claim with `SKIP LOCKED` and mark only after the broker
   acknowledges.
8. Add the compose services, with a drain window per worker.
9. Write the idempotency test per consumer: deliver twice, assert one effect.

## Todo

- [ ] Swap the dependency
- [ ] `broker.py` with two queues
- [ ] Convert every job; retry opt-in only where wanted
- [ ] `scheduler.py` owning all periodic work
- [ ] Rename `tasks` → `jobs`; collapse the re-export layers
- [ ] `attempt` on the row as the only counter
- [ ] Relay: `SKIP LOCKED`, mark after ack
- [ ] Compose: `scheduler`, `agent-worker`, per-worker drain
- [ ] One idempotency test per consumer
- [ ] Reject a client-supplied work key
- [ ] Suites green

## Success Criteria

- [ ] No `arq` import remains
- [ ] Two queues, two worker processes, distinct acknowledgement and retry settings
- [ ] The run task carries no retry label
- [ ] A run payload contains the id and nothing else
- [ ] Periodic work fires while every worker slot is occupied
- [ ] Two relays on one outbox: no row published twice
- [ ] A rolled-back transaction publishes nothing
- [ ] Broker unreachable: the outbox accumulates and the API still commits
- [ ] Each consumer has a named duplicate-delivery test
- [ ] A client-supplied work key is rejected
- [ ] Two requests for one word join a single job; both are authorized to read it
- [ ] `messaging.md` §11 fully covered by named tests

## Risk Assessment

**Stream semantics differ from a list queue in ways a test suite may not cover.**
Signal: a message is processed twice, or a consumer-group message is stranded
unacknowledged. Response: the reclaim timeout and the conditional claim are the two
controls; a stranded message must be observable in the runbook query before it is
trusted.

**Acknowledging on receipt means a crash between claim and completion loses the
broker's copy.** This is intended — the reaper is the recovery path — but it is only
true if the reaper exists. Signal: a run stuck `running` with an expired lease and
nothing requeuing it. Response: the reaper is a phase-9 deliverable, so until then
treat a stuck run as expected rather than as a defect, and do not add broker-level
retry to compensate.

**The scheduler is a new single point of failure for periodic work.** Signal: the
heartbeat goes stale while workers are healthy. Response: readiness already fails on
a stale heartbeat, which makes it visible; a scheduler that cannot start is a boot
failure, not a silent one.

**The rename touches persisted values, not only identifiers.** A channel string
stored at insert time, a schema-name field validated by equality on the client. A
half-rename passes type checks and drops every message. Response: rename definition
and reader in one commit; truncate any dev rows holding an old channel string.
