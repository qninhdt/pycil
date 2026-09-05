# cross-cutting/messaging

PostgreSQL is the source of truth. Redis Streams transports durable domain jobs.
Decisions `F1`–`F9`.

## 1. What belongs on the broker

Only work that may outlive an HTTP request is queued:

| Flow | Durable row | Consumer |
|---|---|---|
| Word generation | `job_tasks` | `domain-worker` |
| Question supply | `job_tasks` | `domain-worker` |

Free-text grading is synchronous under a hard timeout. Assistant Runs execute
inline in the authenticated API request and stream SSE. Neither uses Taskiq.

## 2. Taskiq over Redis Streams

`F1`. Taskiq's `RedisStreamBroker` provides consumer groups and explicit
acknowledgement. Redis remains transport, cache, and coordination; no user, Run,
or job state is canonical there (`A4`, `F6`). One VPS uses one Redis instance
with append-only persistence. A separate broker instance is the scale seam if
queue traffic begins competing with cache traffic.

The worker receives the job id alone (`F3`). It always reloads current state from
Postgres, so a delivery cannot restart work from stale arguments.

## 3. Durable claim and retry

The domain worker acknowledges after a durable claim (`F2`):

```text
delivery(job_id)
  -> conditional claim + attempt increment in Postgres
  -> acknowledge broker delivery
  -> execute from the durable row
  -> conditional terminal update
```

`attempt` on `job_tasks` is the only retry counter (`F4`). A duplicate delivery
that loses the claim performs no work. Every external or append effect has a
domain unique key; absolute and conditional writes are naturally idempotent
(`F7`, `F8`). Bounded failure becomes a readable terminal row in Postgres.

## 4. Commit, enqueue, reconcile

There is no transactional outbox (`F5`). A command commits the canonical job row,
then attempts to enqueue its id. If Redis is unavailable, the API still returns
the durable receipt and a scheduler reconciliation pass enqueues pending rows
that have no active delivery.

```text
API transaction: create or join job_tasks row -> COMMIT
API best effort: broker.enqueue(job_id)
scheduler:       find dispatchable rows -> broker.enqueue(job_id)
client:          GET /v1/jobs/{job_id} until terminal
```

Repeated enqueue is safe because the durable conditional claim is the execution
boundary. The queue is never the only record that work exists.

## 5. Shared work and authorization

Two callers requesting the same shared work join one active job through a
server-derived work key and a unique partial index:

```text
word:<normalised-form>:<dictionary-artifact-identity>
supply:<session-id>:<round-index>
```

Clients cannot provide work keys. Each requester receives an interest row, and
the job read authorizes through that interest. A poll returns the latest canonical
snapshot; no publication or replay layer is involved.

## 6. Scheduler

The scheduler is a separate process (`F9`) so periodic work cannot be starved by
the domain worker pool. It owns worker heartbeat, reconciliation of undispatched
or interrupted jobs, and retention sweeps.

## 7. Capabilities that may not be cut

- Postgres rows are canonical; Redis contains no durable business state.
- Payloads contain only a job id.
- Claim and attempt increment commit before broker acknowledgement.
- One authoritative attempt counter exists on the domain row.
- Lost dispatch self-heals through reconciliation.
- Shared work joins through a server-derived key.
- Terminal failure is durable and readable.
- Every consumer names and tests its idempotency mechanism.
- Periodic work runs outside the worker pool.

## 8. Invariants for the checklist

```text
broker unavailable after commit -> durable receipt exists and reconciliation dispatches it
duplicate delivery -> one durable claim and no double effect
payload contains a job id and no execution arguments
a client-supplied work key is rejected
two requests for the same word join one job; both may read it
supply for one round is not generated twice
a job exceeding its attempt bound reaches readable terminal state
Redis loss does not erase job state
periodic work runs while the domain worker pool is saturated
```
