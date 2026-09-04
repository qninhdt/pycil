# cross-cutting/messaging

PostgreSQL is the source of truth. The broker is transport. Decisions `F1`–`F9`.

## 1. A broker, not an event log

Four questions decide which primitive a flow needs:

1. Is this **work to be done once**, or a **fact several parties may care about**?
2. Is historical **replay** needed to rebuild something?
3. Is **per-message retry** needed? Must concurrency exceed a partition count?
4. Is **strict per-key ordering with retained history** needed?

1 and 3 point at a broker; 2 and 4 point at a log.

What Pycil actually has:

| Flow | Nature | Replay needed? | Consumers |
|---|---|---|---|
| Word generation | Job, shared, minutes | No | 1 |
| Question supply | Job, shared | No | 1 |
| Free-text grading | Job, owner-scoped | No | 1 |
| Agent Run execution | Command, **not idempotent** | **Replay would be harmful** | 1 |
| Reconciliation sweeps | Periodic | No | 1 |

No flow needs replay. No flow has two independent consumers. This is entirely
command and job traffic, so the answer is a **message broker**.

A Run is not idempotent: replay is a *feature* of an event log and here it is a
defect — rerunning a Run that already produced half an answer bills twice and
emits garbage.

## 2. Taskiq over Redis Streams

`F1`. Redis is already in the stack for cache, coordination, and the realtime
engine, so a broker there costs no new component.

Of the three Redis brokers available, only one is usable `[R24]`:

| Broker | Mechanism | Acknowledgement |
|---|---|---|
| Pub/Sub | Broadcast — every worker receives it | **no** |
| List queue | Work queue, one worker receives it | **no** |
| **Streams** | Redis Streams with consumer groups | **yes, durable** |

The list broker is what the previous library already was, so moving to it would
change nothing. Streams adds consumer groups, explicit acknowledgement, and
automatic reclaim of messages left unacknowledged past a timeout.

The previous library is in **maintenance-only mode** — critical security fixes
only, no new work `[R25]`. That is the reason to move; the capability gap is the
reason to move *here*.

Redis serves four roles on one instance (cache, coordination, broker, realtime
engine). Their requirements differ — a broker wants no eviction, a cache is
deliberately evictable — and separating them into two Redis deployments is the
**seam** if a backlog ever competes with token streaming. On one VPS, one instance
with append-only persistence enabled.

## 3. Two workers, one library, different configuration

| | `domain-worker` | `agent-worker` |
|---|---|---|
| Queue | `jobs` | `runs` |
| Acknowledge | after execution | **after the durable claim** |
| Retry | on, bounded | **off** |
| Concurrency | high — all work is I/O-bound | bounded by admission (`G4`) |
| Payload | content-keyed job arguments | `{runId}` **only** |
| Recovery | redelivery, idempotent by key | reaper → requeue → resume from checkpoint |

**Acknowledgement timing differs for a reason** (`F2`). An agent Run acknowledges
after its durable claim so the broker holds nothing in flight for minutes;
recovery is the reaper, not redelivery. Domain jobs are shorter and idempotent, so
acknowledging after execution plus redelivery is the cleanest handling of a native
crash.

**Retry is off for Runs** (`F3`). Library retry restarts a task **from its
arguments**, which is a rerun from input — and the task function is "resume this
Run", not "run this turn". Retry is opt-in per task in this library `[R22]`, so
"off" means simply not labelling the task, and the domain jobs that do want it opt
in explicitly.

**Exactly one retry counter is authoritative**: `attempt` on the domain row
(`F4`). Three counters for one concept — a broker delivery count, a library retry
count, and a database column — with two of them unaware of checkpoints, is how a
Run gets rerun when it should have failed.

## 4. The scheduler is a separate process

`F9`. Periodic work does not share a worker's slots.

The reason is concrete: the worker heartbeat that gates readiness, and the outbox
relay that delivers realtime frames, are both periodic. If the pool is full of long
work they cannot get a slot — readiness fails while the system is healthy, and
realtime delivery stops **silently**. Neither failure mode announces itself.

Periodic work in this design:

```text
outbox relay              deliver pending publications
worker heartbeat          feed the readiness probe
reconcile stuck jobs      re-enqueue a job whose dispatch was lost
reconcile pending grades  settle a grade whose worker died
run reaper               requeue a Run whose lease expired
retention sweep          expire what policy says expires
```

## 5. Transactional outbox

`F5`. The pattern `[R35]`, `[R36]`:

```text
BEGIN
  mutate domain state
  INSERT outbox(subject, payload, available_at, …)
COMMIT
      │
      ▼
relay   claim: WHERE published_at IS NULL AND available_at <= now()
                ORDER BY id FOR UPDATE SKIP LOCKED LIMIT N
        publish → await acknowledgement
        UPDATE published_at
        on error: attempts++, back off via available_at, record the error
      │
      ▼
broker  competing consumers · ack · bounded redelivery
      │
      ▼
consumer  apply idempotently, then ack
```

It solves exactly **one** problem: dual write. A committed state change and the
message that must accompany it cannot diverge.

It does **not** give exactly-once. It gives "no lost message". Duplicates remain,
which is why consumers must be idempotent (`F7`).

The relay runs **in-process in every API replica** (`F6`); no leader election.
`SKIP LOCKED` guarantees two relays never claim the same row `[R31]`. An external
relay service is impossible by construction — it cannot join the producer's
transaction, which recreates the dual write it exists to prevent.

The wake hint is a database notification, which is **transactional**: it fires
only on commit `[R32]`, so there is no window where a notification precedes the
row it announces. A periodic sweep is the backstop; the notification is latency.

Four things that are not optional:

| | |
|---|---|
| **Retention** | Keep published rows for a recovery window before archiving. Deleting immediately removes the ability to republish |
| **Ordering** | Rows are claimed by id, but parallel publishing can reorder within one aggregate. Pycil's messages are order-insensitive; a flow that ever needs order serialises on a key |
| **Backoff** | A failing publication must not spin. The delay lives on the row |
| **No outbox service** | See above |

Observability of the relay is the one place `O7` (no metrics stack) genuinely
costs something: a dead relay is otherwise invisible until a client notices
missing updates. Mitigation is a runbook entry — [../ops/devops.md](../ops/devops.md)
names the query that shows the oldest unpublished row — not a metric.

## 6. When an outbox is required

Three questions:

```text
1. Does this operation write database state?
   No → nothing to make atomic → no outbox

2. If the message is lost, does the system self-heal?
   A reconciler, sweeper, or the next write covers it → outbox optional
   Nothing covers it                                 → outbox REQUIRED

3. Is the message the only carrier of work another party must perform?
   Yes → outbox REQUIRED
```

Question 2 is the one usually skipped.

| Flow | Outbox? | Why |
|---|---|---|
| Word generation | **Yes** | The message is the only thing that schedules the work |
| Question supply | **Yes** | Same |
| Free-text grading | **Yes** | A lost dispatch means a learner's answer is never graded |
| Agent Run execution | **Yes** | The Run row and its dispatch commit together; the reaper is the backstop, not the primary path |
| Job state snapshots to clients | **Yes** | Publication intent belongs in the same transaction as the state change |
| Agent token deltas | **No** | Ephemeral, no state change; `partial_output` plus the checkpoint is the recovery |
| Any synchronous read | **No** | A caller that needs an answer waits for one |

One sentence:

> **Use an outbox when the message is the only carrier of durable work. Do not
> when the message announces state already durable elsewhere and a repair path
> exists.**

## 7. Idempotency

At-least-once delivery means duplicates are normal, not a bug:

```text
relay    publishes → crashes before marking → publishes again
consumer commits   → crashes before ack     → receives again
```

The rule (`F7`) `[R35]`:

> **A dedup store is needed when the effect is APPEND or INCREMENT. It is not
> needed when the effect is a conditional UPDATE, a unique-key INSERT, or an
> absolute OVERWRITE.**

Mechanisms, in order of preference:

| # | Mechanism | Where it applies |
|---|---|---|
| 1 | Naturally idempotent — no side effect | A pure read |
| 2 | **Conditional update** — a state-machine guard | `UPDATE … WHERE id=$1 AND status='queued'` → a duplicate matches zero rows |
| 3 | **Unique constraint** on a natural key | Shared work deduplication by work key |
| 4 | **Absolute write** instead of a delta | Writing a computed total, not an increment |
| 5 | Claim + fence | A non-repeatable external effect |
| 6 | **Dedup by unique index on the domain table** | Last resort, and it belongs beside the data |

Broker-level deduplication is a noise reducer, never the correctness boundary.

Applied:

| Consumer | Effect | Mechanism |
|---|---|---|
| Run claim | Conditional update | 2 |
| Job claim | Conditional update + lease | 2 + 5 |
| Shared work joining | Unique index on an active work key | 3 |
| Question supply insert | Content hash | 3 |
| FSRS effect for one answer | Unique index on a per-session answer key | 3 |
| Grade settle | Conditional update on a pending status | 2 |
| **Credit debit** | **INCREMENT** | **Unique index on `(kind, reference)`** (`P8`) |

The credit debit is the only consumer in this design whose effect is an increment,
and it is therefore the only one needing an explicit dedup key. The index sits on
the domain table, not in a separate inbox: one write instead of two, and the
constraint lives beside the data it protects.

A unique index only holds if the insert is in the **same transaction** as every
related mutation. Where publication is separate, a duplicate publish is possible
while the row stays single — acceptable, because publication is best-effort.

There is no generic inbox library. Each consumer **declares** its mechanism and
has a test proving duplicate delivery produces no double effect (`F8`).

## 8. Work keys: shared work joins instead of duplicating

Two learners asking for the same word must join one job, not start two. The
mechanism is a **server-derived work key** plus a unique index over active jobs.

```text
word:<normalised form>:<dictionary artefact identity>
supply:<sessionId>:<roundIndex>
grade:<responseId>
```

Three properties that matter:

- The key is **never accepted from a client.** A caller able to choose it could
  join someone else's job and read its result.
- The word key includes the **dictionary artefact identity** (`O5`), so a job
  generated against one reference dataset is not joined by a request expecting
  another.
- The supply key is `(session, round)`, **not** the demand list. The demand is
  derived from what the round still needs, so two calls in one round compute
  *different* lists; keying on the list would make them two jobs and generate the
  same round's supply twice.

Joining is per-requester: each joiner gets its own **interest** row, which is what
`realtime` authorizes a subscription against, and what makes one publication fan
out to several authorized readers.

## 9. Three layers that do not substitute for each other

| Layer | Purpose | Required where |
|---|---|---|
| Outbox | No lost message on the producer side | Wherever the message is the only carrier of work |
| Broker retry / bounded redelivery / terminal state | A message delivered but not processable | Every job consumer |
| Idempotency | A duplicate must not double-apply | Every consumer, mechanism varying |

A message exceeding bounded redelivery is **terminal state in Postgres**, not a
broker feature. That row is the operator-visible quarantine and the replay source.

## 10. Capabilities that may not be cut

Per R4:

- State and message commit in one transaction.
- The relay claims with `SKIP LOCKED` and marks after acknowledgement.
- Every job carries a lease and a fence; a stale worker cannot write.
- Exactly one authoritative attempt counter, on the domain row.
- Shared work joins by a server-derived key, never a client-supplied one.
- Terminal failure is durable and readable.
- Retry is off for Runs.
- Periodic work runs outside the worker pool.

## 11. Invariants for the checklist

```text
mutation and outbox row commit in ONE transaction
a rolled-back transaction publishes nothing
relay crash after publish, before marking → duplicate delivered, no double effect
two relays on one outbox → no row published twice
broker unavailable → the outbox accumulates and the API still commits
each consumer: duplicate delivery produces no double effect   ← one test per mechanism
a client-supplied work key is rejected
two requests for the same word join one job; both are authorized to read it
supply for one round is not generated twice
credit debit is charged once under retried settlement
a job exceeding redelivery lands in terminal state, readable
periodic work runs while the worker pool is saturated
```
