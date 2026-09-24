# cross-cutting/messaging

Redis Streams transports content jobs. The receipt is Redis, not a Postgres row.
Decisions `F1`–`F9`.

## 1. What belongs on the broker

Only work that may outlive an HTTP request is queued:

| Flow | Durable state | Consumer |
|---|---|---|
| Word generation | Redis receipt, 24h TTL | `domain-worker` |
| Question supply | Redis receipt, 24h TTL | `domain-worker` |

Free-text grading is synchronous under a hard timeout. Assistant turns execute
inline in the authenticated API request and stream SSE. Neither uses Taskiq.

## 2. Taskiq over Redis Streams

`F1`. Taskiq's `RedisStreamBroker` provides consumer groups and explicit
acknowledgement, which is what makes a crashed worker's job recoverable without a
starting worker stealing work a live worker is running.

Two brokers, one Stream. The API's broker publishes and registers no tasks; the
worker's broker registers handlers and consumes. They are separate objects
because the API must not import worker code and the worker must not be able to
serve an API request, but they share `STREAM_NAME` and `CONSUMER_GROUP_NAME` so
both ends address the same Stream.

```text
worker idle_timeout            300_000 ms
worker unacknowledged_batch    10
stream maxlen                  10_000
```

`idle_timeout` must exceed the longest real job or a slow provider call gets
duplicated and paid for twice. `maxlen` is deliberately generous: trimming an
unconsumed message loses that content job.

## 3. Delivery, acknowledgement and the at-least-once boundary

Both handlers use Taskiq's default executed-or-failed acknowledgement, **not**
`when_received`. Acknowledging on receipt would ACK before the effect exists and
lose the job on a crash; instead the Stream's pending-entry reclaim owns recovery,
and a message unacknowledged past `idle_timeout` is redelivered to another worker.

Delivery is therefore at-least-once, and nothing here promises exactly-once. The
effect is made idempotent at the content boundary — Lexi's uniqueness rule — so a
redelivery after a committed write returns the existing row instead of paying for
a second generation. Word generation additionally passes through a Redis
singleflight (`pycil/queue/singleflight.py`) so concurrent identical queries in
flight share one provider call.

The payload is the job id and its dispatch arguments (`F3`); the worker executes
from those arguments rather than reloading a row, because there is no row to
reload. See §5.

## 4. Receipt, not a job row

**This is where the implementation departs from the earlier design, and the
departure is load-bearing.**

There is no `job_tasks` table, no durable job row, no conditional claim, no
`attempt` counter, no interest row and no reconciler. What exists is a Redis
record per job:

```text
pycil:job:{job_id}
  id, kind, owner_id, status, createdAt, updatedAt,
  result, errorCode, finishedAt
TASK TTL 24h
status: queued -> running -> done | failed | expired
```

`enqueue_job` writes the receipt **before** publishing. If publication then
fails, the receipt is marked `failed` rather than left `queued`:

```text
API:    SET pycil:job:{id} status=queued
API:    broker.kick(message)
        on publish failure -> status=failed, errorCode=job_publish_failed
worker: status=running -> effect -> status=done | failed
client: GET /v1/jobs/{id} until terminal
```

The failure branch is the reason the ordering is what it is. A permanent `queued`
with nothing on the Stream is the state a polling client cannot escape — it would
wait forever for work that was never sent. Writing the receipt first and
correcting it on failure means the client always reaches a terminal state.

**What this costs.** `F5`'s "no transactional outbox, a reconciler re-enqueues
what the queue lost" no longer holds, because there is no reconciler and no row to
reconcile from. Redis loss loses in-flight content work outright. That is the
accepted trade rather than an oversight: a lost generation is retryable from the
UI, and graded learning never depends on a job. It is stated here rather than
left implied, because the older invariant list claimed the opposite.

The session's own retry bound re-requests a failed supply job, and the learner
re-requests a failed word generation. Neither is automatic.

## 5. Ownership and authorization

The receipt carries `owner_id`, written once at creation and **never restated by
a later update**. That is a security property, not tidiness: the status route
authorizes against that field, so letting a worker rewrite it would let a bug in
a handler hand one learner's job to another.

`GET /v1/jobs/{job_id}` returns the same 404 for an unknown id and for another
learner's id, so the route never confirms that someone else's job exists. It
requires authentication rather than accepting an anonymous read.

A receipt that expired mid-flight is still updatable: `update_job_status` creates
a minimal record with `owner_id: None`, which the route treats as "not yours". The
client sees a terminal state instead of polling a key that will never come back.

## 6. Where periodic work went

Earlier revisions of this folder specified a scheduler process (`F9`) owning
worker heartbeat, dispatch reconciliation and retention sweeps. **There is no
scheduler process.** The implemented worker owns its own liveness: `_heartbeat_loop`
runs as an in-process task inside `pycil_worker/main.py` and refreshes
`worker:heartbeat` (TTL 90s, interval 10s), which is the key API readiness reads.
Readiness therefore distinguishes "API is up" from "a worker is alive" without a
third process.

Nothing else periodic runs. Assistant thread retention has a deadline column and
`reconcile_assistant_retention` exists and is tested, but **it is not registered
in the worker's handler registry and nothing calls it** — the registry holds
exactly the two content kinds, and a startup assertion fails the process if the
registry and the handler map disagree. A retention sweep is therefore an operator
action, not a scheduled one. Phase 15 owns deciding whether an actual privacy
policy requires wiring it up.

## 7. Capabilities that may not be cut

- Payloads carry a job id and its dispatch arguments, never credentials.
- A failed publication is recorded as failed, never left queued.
- The receipt's owner is written once and never restated by a worker.
- One learner cannot read another's receipt.
- Every consumer names and tests its idempotency mechanism.
- Word generation is not charged and not duplicated by concurrent identical calls.
- The worker's handler registry must equal the shared contract's kind registry.

## 8. Invariants for the checklist

```text
a publish failure leaves a failed receipt, not a permanent queued one
a receipt expires after 24h and an expired receipt is not readable as someone's
another learner's job id returns 404, indistinguishable from an unknown id
duplicate delivery of a word job pays for one generation
two concurrent identical word requests share one provider call
supply for one round is not generated twice
the worker refuses to start if a contract kind has no handler
the worker heartbeat is what API readiness reads
```

The older list's `Redis loss does not erase job state` and `periodic work runs
while the domain worker pool is saturated` are **withdrawn**: neither is true of
the implemented system, and §4 and §6 say why.
