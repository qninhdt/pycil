# cross-cutting/delivery

How a result reaches the client. Decisions `E1`–`E7`.

Three mechanisms, one per shape of work. No gateway, no broker between the
producer and the reader.

## 1. The reference implementation

LangGraph's Agent Server is the same problem: an LLM agent with a tool set, a
conversation thread, and human approval on some tool calls. Its **default
self-hosted runtime is one process** — *"single host: the API server manages the
task queue directly with no separate queue workers"* `[R40]`. The published image
serves the API **and** executes runs in-process; splitting them requires
`N_JOBS_PER_WORKER=0` on the API container *"so it stops claiming runs"* plus a
second container on `langgraph_api.queue_entrypoint` `[R43]`.

Read their stack bottom-up and the reason for each part is legible:

| | Theirs | Why | Pycil |
|---|---|---|---|
| Postgres | queue state with *"'exactly once' semantics"*, threads, runs, checkpoints `[R41]` | system of record | same |
| Redis | *"a pub-sub broker to enable streaming real time output from background runs"*; *"stores only ephemeral data"* `[R40]`, `[R41]` | a **worker** holds no client connection, so events must cross a process boundary | cache and coordination only |
| Message broker | none | Postgres is the queue | same |

Redis pub-sub is a bridge from worker to API. Run inline and both ends of the
bridge are the same process, so the bridge is not simplified — it is absent. That
is `E1`, and it is why deleting the gateway is convergence with the reference
design rather than divergence from it.

## 2. Three mechanisms

```text
assistant turn      SSE on the request that created the run          E2
durable job         202 + a handle, then polling                     E3
free-text grade     synchronous under a hard timeout                 E4
```

### Assistant turn — SSE

```text
POST /v1/assistant/threads/{threadId}/runs/stream
  → 200 text/event-stream
    event: run.started        data: {"runId": …}
    event: message.delta      data: {"text": …}
    event: tool.started       data: {"toolCallId": …, "name": …}
    event: approval.required  data: {"toolCallId": …, "action": …}   ← stream ENDS
    event: run.completed      data: {"runId": …}
```

`text/event-stream` is their transport too (`GET .../runs/{runId}/stream`,
`GET /threads/{threadId}/stream`) `[R42]`. Pycil streams on the **creating**
request rather than offering a separate join, because a background run is what a
join exists for and there is no background run.

The connection carries the same bearer header as any other route (`H13`). No
second token: a scoped short-lived token is the right answer when a *third party*
validates the signature itself, and dead weight when the API serves the stream.

### Durable job — polling

```text
POST /v1/content/words          → 202 { "jobId": … }
GET  /v1/jobs/{jobId}           → { "status": "queued"|"running"|"done"|"failed"|"expired", … }
```

Their own background-run guide does exactly this: poll
`GET /threads/{tid}/runs/{rid}` and read `status` `[R44]`. Word generation and
question supply are not interactive — a learner asked for a word and will read it
when it exists. The receipt's `owner_id` authorizes the read, so a job is never
readable by anyone but the learner who asked for it.

**Each request gets its own receipt.** There is no shared-work join: two learners
asking for the same word produce two receipts, and the duplicate provider call is
prevented one layer down, by the worker's Redis singleflight. That is a real
difference from the earlier design, which had the API join both callers onto one
job through a server-derived work key. The cost is a second receipt for the same
work; the benefit is that no cross-learner record exists to authorize.

### Free-text grade — synchronous

One request, one answer, a hard timeout, and a typed refusal on expiry (`E4`).
What this replaces: a pending row, a grading lease, a fence, a reconciler, an
outbox row, and a push — to save the learner a few seconds. The timeout is
`uncalibrated`; the measurement that settles it is the p99 of the rubric call.

## 3. What a reload loses, stated plainly

| Interrupted | Lost | Recovered by |
|---|---|---|
| Mid-turn, before the reply completes | that turn | re-ask. The checkpoint holds the thread up to the last completed message (`E7`) |
| While a job runs | nothing | the next poll |
| Mid-grade | that submission | resubmit |
| While an approval is pending | nothing | `GET /v1/assistant/threads/{id}/state` returns the interrupt payload; the popup re-renders |

The reference server loses the same thing in its default configuration:
`stream_resumable` defaults to **`false`**, and joining a run mid-flight states
*"output is not buffered, so any output produced before joining will not be
received"* `[R42]`. When resumability is enabled the buffer is **Redis** with
`RESUMABLE_STREAM_TTL_SECONDS` default 120 `[R45]` — not a database column. Their
advice when a rejoin fails is to fetch thread history, which is the checkpoint.

So `E6` drops `partial_output`, and the seam is theirs: a short-TTL Redis buffer
keyed by run id. A column was the wrong shape for a 120-second concern.

## 4. Disconnect

`E5`. A dropped connection cancels the run, which is `cancel_on_disconnect` in
their API `[R42]`. Inline makes it the only coherent option — the ASGI task *is*
the run, so the alternative is a run nothing is reading and nobody will pay for.

`on_disconnect: continue` is the behaviour that needs a worker, and that is
`E1`'s seam rather than a gap.

## 5. What the edge must do

Unchanged in requirement, changed in target: the non-compression carve-out and
`flush_interval -1` now name Pycil's own SSE paths instead of a gateway's
`/connection/sse*` (`O2`, `[R34]`). A proxy that buffers defeats streaming
entirely, and compression buffers by construction.

## 6. Capabilities that may not be cut

Per R4:

- A committed mutation is readable over HTTP without any push having succeeded.
- A job result is reachable by polling alone.
- An approval survives a reload: the interrupt payload is readable from the run.
- The SSE path is neither compressed nor buffered at the edge.
- Tokens reach the client incrementally, not batched at the end of a turn.

## 7. Invariants for the checklist

```text
a committed mutation is readable over HTTP with no push involved
a job's terminal state is reachable by polling alone
two learners waiting on one word both read that job's result
a client disconnect cancels the run it was reading
a reload during an approval re-renders the popup from the run read
the SSE route is not compressed and not buffered at the edge
a grade that exceeds its timeout returns a typed refusal, not a 500
no credential is reachable from client JavaScript on the SSE path
```
