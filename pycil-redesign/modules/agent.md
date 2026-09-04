# modules/agent

Owns Threads, Runs, tools, prompts, and approval. Decisions `G1`–`G17`.

Top of the dependency chain — nothing calls it. It reaches product behaviour
through module facades, never around them.

## 1. Shape

```text
api            POST creates a Run, returns a handle · reads · cancel
               + outbox relay (in-process, every replica)

agent-worker   claims Runs from its own queue
               + Run reaper

scheduler      periodic only
```

Same image as the API and the domain worker; a different queue and a different
drain window (`G3`). One codebase because Threads, Runs, and checkpoints have
exactly one owner.

`api` is separate from the worker because its scaling signal is request rate and
its rollout must be fast, while a worker must drain claims in flight.

## 2. The Run is a durable row

Not work performed inside a request (`G1`). The current shape — a graph loop
running in the HTTP handler behind a streaming response — has four consequences,
each fatal on its own:

| | Inline |
|---|---|
| A run outliving its request | Cannot. The request is held for the whole deadline |
| Client disconnect | Severs generation |
| Human approval | Needs a *second* stream, because the first died with its request |
| Deploy | Kills every run in flight |

Target:

```text
POST /v1/agent/threads/{id}/messages
  BEGIN
    INSERT runs(status='queued', thread_id, fence=0)
      ← a unique index rejects a second active Run on the Thread → 409
    INSERT outbox(subject='agent.run.execute', payload={runId})
  COMMIT                                              →  202 { runId }

relay    claim batch FOR UPDATE SKIP LOCKED → publish → mark

worker   UPDATE runs SET status='running', lease_owner=me,
                lease_expires_at=now()+ttl, fence=fence+1
          WHERE id=$1 AND status='queued'
         0 rows  → ack and drop            (duplicate delivery)
         claimed → ack, then execute

execute  load checkpoint → resume, NOT rerun from input
         node boundary         → checkpointer writes
         every N tokens / M ms → partial_output (fenced write)
         token deltas          → thread:<threadId>
         heartbeat             → extend lease
         yield point           → check cancellation

finish   write output or error, clear partial fields, release lease
```

The payload is `{runId}` **only** (`F3`). Anything else lets a redelivery restart
from input.

## 3. Single writer: four motions on one row

Each follows from the previous, and skipping any one breaks the next (`G5`):

```text
create the row      admission   UNIQUE INDEX (thread_id) WHERE status is active
take the row        claim       UPDATE … WHERE status='queued', fence+1
hold the row        lease       heartbeat extends the expiry
prove you hold it   fence       every write matches (runId, fence)
```

Admission alone wedges a Thread forever when a worker dies, so a lease is
required. A lease alone lets a paused worker wake and write over its successor,
so a fence is required.

## 4. Idempotency without a dedup table

Three situations, three mechanisms that already exist (`F7`):

| Situation | What happens |
|---|---|
| The broker delivers a run id twice | The conditional claim matches zero rows → ack, drop |
| A worker crashes, then resumes | Loads the latest checkpoint; a tool that already ran has its result in state |
| A worker stalls, then wakes | The fence rejects its write |

**Single-writer stops concurrency; the checkpoint stops redoing.** That is the
whole of it. The one external effect needing more is the credit debit, which
carries a unique key on `(kind, reference)` (`P8`).

## 5. Recovery

```text
reaper   lease_expires_at < now()
         → status = 'queued'
         → INSERT outbox row (same runId)
         → relay republishes
         → another worker claims, fence+1, resumes from the checkpoint
```

Recovery does not depend on broker redelivery (`G6`). `attempt` on the Run row is
the only authoritative counter (`F4`).

Lease expiry is **not terminal** (`G7`). Terminal is reached when `attempt` is
exhausted, and then it is a failure with a reason. A status meaning "the lease ran
out" would be a second retry counter wearing a different name.

One limit, stated as correct behaviour rather than a gap: if a lease expires after
a non-idempotent provider call with no safe checkpoint after it, the Run fails
rather than restarting from input.

Cancellation is a column, observed at the next yield point (`G8`). Never a broker
operation and never a process kill — terminating a process cannot know whether the
target already moved on.

## 6. Why a separate worker

Three reasons, and the third is the one that is not about latency (`G3`).

**Head-of-line blocking.** Two workload classes with service times an order of
magnitude apart on one FIFO: a grade lands behind every queued run. Raising the
pool size does not fix it — there is no priority inside one queue, so a full pool
still makes a short job wait. Routing long work to a dedicated queue with its own
worker is the documented arrangement for a mixed workload.

**Drain windows differ by the same order.** A deploy wants to wait out a run and
not wait out a grade. One process forces one window for both.

**Periodic work must not compete for slots.** The heartbeat that gates readiness
and the relay that delivers realtime frames are periodic. If they cannot get a
slot, readiness fails and realtime delivery stops silently. That is why the
scheduler is its own process (`F9`) *and* why long runs live away from short jobs.

Concurrency: `--max-async-tasks` on the agent worker **is** the global bound
(`G4`) — one knob enforced by the runtime rather than two places asserting the
same number. Per-learner fairness is checked at enqueue: over the limit, the Run
stays `queued` and is not pushed to the broker, so the queue never holds a deep
backlog. The value is `uncalibrated`; it needs queue depth and wait time per kind.

## 7. Streaming

```text
provider stream
  → graph event stream
  → normalised to one event contract
  → thread:<threadId>, runId in the payload
```

Thread-scoped, not run-scoped (`E3`): a run-scoped channel forces a fresh
subscribe every turn, and each subscribe is an authorization round-trip.

Contract:

```text
run.started
message.delta       { text }
thinking.delta      { text }
tool.started        { toolCallId, name }
tool.args_delta     { toolCallId, partial }
tool.completed      { toolCallId, ok, summary }
approval.required   { toolCallId, action }
message.completed
run.completed | run.failed | run.cancelled
```

Four constraints from how provider streams actually behave `[R28]`:

| | |
|---|---|
| Tool input arrives as JSON fragments | Show the tool name when the block opens and fill arguments progressively. Do not wait for the block to close |
| Usage figures are cumulative | Record the latest value. Summing double-counts |
| Thinking is a separate stream | The client may collapse it. Never merge it into text |
| Keepalive frames carry no content | Ignore rather than publishing an empty event |

### Recovery is two layers, and both are required

```text
Layer 1   Centrifugo history, bounded, short TTL
          replays the gap in order in the subscribe reply

Layer 2   GET /v1/agent/runs/{runId}
          status + partial_output + messages
```

Centrifugo's own documentation is unambiguous: history "is a cache, not your
source of truth", it "can be empty, truncated, or lost at any moment", and the
guidance is to **always keep a backend fallback** `[R18]`.

Layer 2 *is* that fallback, which is why `partial_output` is **mandatory**
(`E6`): the checkpointer writes at node boundaries, so a reconnect in the middle
of one model call would otherwise return a `running` Run with an empty body and
the learner sees a blank pane. This is the one piece of resume machinery that must
be built rather than configured.

There is no third layer (`Q4`). A durable event table with a cursor covers nothing
Layer 2 misses, and costs a table, an endpoint, and sequence discipline.

Three flags to handle correctly:

| Flag | Meaning |
|---|---|
| `wasRecovering: true` | Recovery was *attempted*. Says nothing about success |
| `recovered: true` | Continuity preserved. May arrive with zero replayed frames |
| `wasRecovering` + `recovered: false` | **Fetch canonical state.** Expected, not exceptional |

The **epoch** names one stream instance: if a stream is lost and recreated,
offsets restart, so a changed epoch tells the client its stored offset is
meaningless rather than letting it be trusted.

## 8. Tools

Bounded, and the boundary is the point. No sandbox (`G17`) — the agent executes
no code; its tools are library operations and dictionary reads.

| Tool group | Approval |
|---|---|
| List and read nodes, list deck contents, read statistics, search the dictionary | none |
| Create a folder or deck, rename, make private, request a word generation, add a sense | none — reversible and owner-scoped |
| **Move, publish, delete, remove a sense** | **required** |

The split is by reversibility and reach. Publishing exposes a subtree to other
people; deleting removes a subtree; moving restructures; removing a sense drops
membership the learner curated. None of those should happen because a model chose
a tool call.

Every tool re-checks ownership when it executes. That is what makes approval a
gate on intent rather than a gate on authorization — the authorization check is
not optional and does not depend on the approval having happened.

## 9. Approval

Kept, because this agent can write (`G9`). The reference design that removes
approval entirely has an assistant that *structurally* cannot: no credential, no
write verb, a gate at the boundary. This one has four destructive tools over the
learner's own library.

```text
tool call needs approval
  → interrupt() pauses inside the node; the checkpoint holds the state
  → run status = interrupted, holding NO worker slot
  → the agent panel renders a popup from the interrupt payload
       Approve → POST /v1/agent/runs/{runId}/resume {decision: approve}
                 → Command(resume=approve) → the tool executes
       Reject  → Command(resume=reject)
                 → the agent receives a rejection and continues
                   (not an abort — it can propose something else)
```

A **popup in the panel**, not a question in the transcript. The decision is a
control interaction, not a message.

What this does **not** need (`G10`, `Q5`):

| Removed | Why |
|---|---|
| An action table as a state machine | The checkpoint *is* the state |
| A time-to-live and an expiry reconciler | A paused run holds no slot; the general Run reaper handles a very old interrupt |
| A freshness check before resume | The tool re-checks ownership when it runs. A node deleted meanwhile raises, and the agent handles it — which is correct behaviour |
| An audit row | Postgres holds the state; the popup is the safety mechanism. An audit row blocks nothing |

A waiting decision occupies no capacity (`G11`): the job ends, the checkpoint
persists, approval enqueues a new job. Otherwise a human lunch break holds a
worker slot.

## 10. Required behaviour

| | |
|---|---|
| **Compaction** (`G12`) | Mandatory. Triggered by a ratio of the context window, never by a message count. Summarise the oldest safe range, keep recent messages, and **never split a tool call from its result**. A per-message cap bounds one message; nothing else bounds a thread, and a long enough thread exceeds the window |
| **Untrusted content** (`G13`) | Every string from outside is wrapped so the model treats it as data: node names, deck names, dictionary text, tool results. These are author-controlled and flow into tool results — a folder named like an instruction, beside a delete tool, is a real injection path `[R37]` |
| **Stop reasons** | Truncation mid-tool-call drops the block and tells the model. Truncation mid-text keeps the text and marks it truncated. A content refusal is a **result**, not an error, and triggers no fallback |
| **Token budget** | Estimated before the call, actual from the response. Feeds compaction, the per-turn limit, and the credit debit |
| **Model allow-list** | An override outside the list is a clean client error — never a silent downgrade, never a server error |
| **Title generation** | Scheduled only *after* single-writer is held, so a rejected turn neither bills a model call nor titles a conversation from a message that never ran |

## 11. Prompt

Written **against a corpus of real system prompts** (`G16`, `[R39]`), not
hand-written short. Shape, length, and how tools and boundaries are described are
the hard parts, and there is a reference body of work.

Caching is **prefix stability** (`G14`), because the cache prefix order is
`tools → system → messages` `[R30]` — anything unstable early invalidates
everything after it:

```text
[1] tool definitions     absolutely stable within a session
[2] system prompt        a version, not a template rendered per request
[3] compacted summary    changes only when compaction runs
[4] message history      append-only
[5] current turn
```

Five rules follow:

- no timestamp and no random identifier in the system prompt;
- the tool list never changes mid-session — a tool that is unavailable returns a
  typed refusal rather than disappearing from the list;
- deterministic JSON serialisation with a fixed key order;
- thinking blocks are passed back with tool results, never stripped;
- compaction is a deliberate invalidation point.

Log the cache-read token count on every call (`G15`). Always zero means nothing is
cached, and that is a cost bug nothing else surfaces.

## 12. Capabilities that may not be cut

Per R4:

- One running Run per Thread, enforced by a unique index rather than by
  convention. Tested as a lock, not as a safety net.
- Resume from the checkpoint, never a rerun from input.
- A fence on every write from a leased worker.
- Cancellation observable mid-generation.
- Approval before any destructive tool executes.
- Ownership re-checked inside every tool, independent of approval.
- `partial_output` persisted periodically.
- Untrusted content wrapped.

## 13. Invariants for the checklist

```text
claim: WHERE status='queued' → a duplicate matches zero rows
a second Run on the same Thread → 409
lease expiry → reaper → requeue → resume FROM CHECKPOINT, not from input
fence: a stalled worker's late write is rejected
cancel mid-generation → stops at the next yield point
two workers on one queue → no Run executes twice
a destructive tool cannot execute before approval
reject → the agent receives a rejection and continues
an interrupted Run holds no worker slot
a node deleted during approval → the tool raises; the agent handles it
partial_output is written mid-generation and readable over HTTP
compaction never splits a tool call from its result
untrusted content is wrapped
a tool refusal does not change the tool list
```

## 14. To verify at implementation time

Not assumed here, because provider behaviour differs:

- how reasoning tokens arrive on a given endpoint — a dedicated delta field,
  inline markers, or not at all. The `thinking.delta` contract hides this from
  clients;
- tool-call streaming: index-based accumulation of a JSON-string argument field;
- whether a provider offers a parallel-tool-call control and honours it.
