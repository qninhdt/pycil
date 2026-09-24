# modules/assistant

Owns Threads, Runs, tools, prompts, and approval. Decisions `G1`–`G18`.

Top of the dependency chain — nothing calls it. It reaches product behaviour
through module facades, never around them.

## 1. This is not a special problem

An LLM agent, a handful of tools over the learner's own library, and human
approval on the destructive ones. That is what LangGraph's Agent Server exists to
run, so its shape is adopted and every deviation is named with a reason (`G18`).

```text
GET    /v1/assistant/models                               model catalog
POST   /v1/assistant/threads                              create
GET    /v1/assistant/threads                              list
GET    /v1/assistant/threads/{threadId}                   read
DELETE /v1/assistant/threads/{threadId}                   delete
GET    /v1/assistant/threads/{threadId}/state             messages + interrupts
POST   /v1/assistant/ag-ui                                AG-UI turn or resume
POST   /v1/assistant/threads/{threadId}/runs/stream       new turn, SSE
```

`/ag-ui` is the browser's transport: it accepts a `RunAgentInput` and handles both
a fresh turn and a resume, because a resume carries a `resume` entry on the same
input shape. `/runs/stream` starts a turn from a plain message for a client that
does not drive AG-UI itself; both funnel through the same `_streamed_events`.

**There are no `/runs/{runId}` routes.** Earlier revisions listed a canonical run
read, a resume endpoint and a cancel endpoint. The `assistant_runs` table was
dropped (migration `0007`), the resume decision rides `/ag-ui`, and the run status
a client needs is derived from the checkpoint rather than stored. See §4.

What is dropped from the reference server and why (`G18`):

| Theirs | Dropped because |
|---|---|
| `/assistants`, versions, `/latest`, `/graph`, `/schemas`, `/subgraphs` | one graph. `assistant_id` would be a column with one value |
| `/runs` (stateless), `/runs/batch`, `/runs/wait` | every turn belongs to a Thread; there is no batch caller |
| `/runs/{id}`, `/runs/{id}/resume`, `/runs/{id}/cancel` | no run row to address. The checkpoint holds the pause and `/ag-ui` carries the decision |
| `/store/*` | long-term memory is the learner's library (`Q7`) |
| `/runs/crons/*` | no periodic work exists to schedule (`F9` is withdrawn; see [../cross-cutting/messaging.md](../cross-cutting/messaging.md) §6) |
| `/a2a/*`, `/mcp/` | no second agent and no external tool host |
| `/threads/{id}/copy`, `/history`, `/state/checkpoint` | time travel is a platform feature, not a product one |

Kept from their shape, verbatim where it fits: `text/event-stream` on the turn
route, `resume` carrying a decision, and a state read a reload rebuilds from.

## 2. A turn executes inline in its request

`G1`. Their default self-hosted runtime is one process managing its own queue
`[R40]`, and their image executes runs in-process until told not to `[R43]`. A
Pycil turn is one to three model calls and a few tool calls.

```text
POST /v1/assistant/ag-ui  (or /threads/{id}/runs/stream)
  acquire the per-learner turn lease        -> 409 if one is active
  require a positive credit balance
  -> 200 text/event-stream
       graph.astream(...)  ← in this request's task
         message.delta · tool.started · tool.completed  → SSE frames
         interrupt()  → emit approval frame, END STREAM
       release the lease (or extend it when a pause is pending)
```

**There is no Run row, and no second source of truth for turn state.** A turn
either completes in this request, errors, or its connection drops. That is what
makes `G2`'s "the row exists so a background queue is a later config change"
unnecessary: there is nothing to keep in sync, and the checkpoint already holds
everything a resumed turn needs.

The one durable per-turn record is the **turn lease**, and it is Redis, not
Postgres. It is a resource bound rather than a billing record: PostgreSQL's unique
`(kind, reference_id)` ledger key stays the correctness boundary, so a Redis
outage costs at most a little parallel overspend rather than a wrong balance. It is
keyed **per learner**, not per thread — two tabs on two threads are the same
overspend risk as two tabs on one.

A paused turn extends the lease to the thread retention window rather than
releasing it, so an approval that arrives later still has an owner.

## 3. No reaper

`G3`. Verified against both published references: **no environment variable
containing HEARTBEAT or SWEEP exists** `[R44]`, `[R45]`. Their recovery is
`BG_JOB_MAX_RETRIES` (default 3), requeueing so a run *"resumes from the last
checkpointed step"*.

Inline execution removes the failure a reaper exists for. There is no worker that
can stall while holding a claim; the request completes, errors, or its connection
drops, and all three are observable in the same process.

| Failure | Handling |
|---|---|
| Provider error mid-turn | the stream carries a terminal `RunErrorEvent`; the checkpoint holds the thread to the last completed message |
| Deadline exceeded | the same, with a deadline error code |
| Client disconnects | the ASGI task is cancelled (`E5`) |
| API process killed mid-turn | the turn is simply gone; the lease expires on its own TTL. The checkpoint holds everything up to the last completed message, and re-asking is the recovery |
| Two tabs | the second turn is refused with `409 assistant_turn_in_progress` |

The last row is the honest cost of inline, and it is bounded: one turn, one
learner, recoverable by re-asking.

**A stream error does not truncate the response.** `_streamed_events` catches a
provider or graph exception, logs it, and emits a terminal `RunErrorEvent` frame
rather than letting the exception propagate. A propagated exception closes the SSE
body with no terminal frame, which a client cannot distinguish from a dropped
connection.

## 4. Status is derived, not stored

`G7`. There is no status column. What a client needs is computed from the
checkpoint:

```text
interrupted  the checkpoint holds a pending interrupt — awaiting a human decision
idle         no pending interrupt; the turn either finished or never started
```

`GET /threads/{id}/state` sets that field from `state.interrupts`. The older
vocabulary (`pending · running · interrupted · success · error · cancelled`) was
the reference server's run-row status set; with no row, five of those six describe
something no longer recorded anywhere, and inventing columns to hold them would
be a second counter wearing a name.

## 5. Approval

`G8`–`G10`. Kept, because four tools write to the learner's library. The pause
state is `ThreadState.interrupts` read from the checkpoint — in the reference API
interrupts live on the **thread state**, not on the run row `[R42]`.

```text
tool call needs approval
  → interrupt() pauses inside the node; the checkpointer writes
  → the request ENDS
  → the panel renders a popup from the interrupt payload
       approve → POST /v1/assistant/ag-ui {resume:[{interrupt_id, status, payload}]}
       edit    → …decision:"edit", editedAction:{name, args}
       reject  → …decision:"reject", message?   agent receives a refusal, CONTINUES
       respond → …decision:"respond", message}  answer without calling the tool
  → Command(resume={"decisions":[…]}) on a NEW request, streaming again
```

The four decisions are the installed middleware's `approve · edit · reject ·
respond` `[R26]`; `edit` is the one that matters for a destructive tool —
correcting a target beats rejecting and re-asking.

A waiting decision occupies **nothing** (`G9`): no worker slot, and no open
connection either. The first request has already returned.

**The AG-UI resume shape is translated.** AG-UI sends a `ResumeEntry`
(`interrupt_id`, `status`, `payload`); `HumanInTheLoopMiddleware` reads
`{"decisions": [{"type": "approve"}]}`. `_with_graph_resume` in the router
converts one into the other, and `/ag-ui` refuses a request carrying more than one
resume entry.

What this does not need (`Q5`):

| Removed | Why |
|---|---|
| An action table as a state machine | `ThreadState.interrupts` *is* the state |
| A TTL and an expiry reconciler | A pause holds no resource, so nothing needs expiring |
| A freshness check before resume | The tool re-checks ownership when it runs. A node deleted meanwhile raises, and the agent handles it — correct behaviour, not a gap |
| An audit row | Postgres holds the state; the popup is the mechanism. An audit row blocks nothing |

## 6. Checkpointing

`G11`, `E7`. The checkpointer owns its own schema through `setup()`: ten
migrations, versioned by the library. Copying that DDL into a Pycil migration
means a library upgrade silently disagrees with the tables it is handed.

`durability="exit"` — checkpoint at the message boundary, not at every node.
Verified against `langgraph` 1.2.9: `durability="exit"` writes **one** checkpoint
where `"async"` writes three, and it still checkpoints at an `interrupt()` so
`Command(resume=…)` continues from it. HITL is unaffected; only mid-turn node
granularity is given up, which is `E6`'s accepted loss.

## 7. Streaming

One contract, normalised from the provider's stream so a client never sees
provider shapes:

```text
run.started         { runId }
message.delta       { text }
thinking.delta      { text }
tool.started        { toolCallId, name }
tool.args_delta     { toolCallId, partial }
tool.completed      { toolCallId, ok, summary }
approval.required   { toolCallId, action }      ← terminal for this request
message.completed
run.completed | run.failed | run.cancelled
```

Four constraints from how provider streams actually behave `[R28]`:

| | |
|---|---|
| Tool input arrives as JSON fragments | Show the name when the block opens, fill arguments progressively. Do not wait for the block to close |
| Usage figures are cumulative | Record the latest value. Summing double-counts |
| Thinking is a separate stream | The client may collapse it. Never merge it into text |
| Keepalive frames carry no content | Ignore rather than emitting an empty event |

Recovery is one layer: `GET /v1/assistant/threads/{threadId}/state` returns the
thread's completed messages and its pending interrupts, read from the checkpoint.
There is no event table (`Q4`) and no partial buffer (`E6`).

The browser-facing route emits AG-UI `RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`,
`CUSTOM` approval, and `RUN_FINISHED` or `RUN_ERROR` events. The assistant-ui
runtime parses that stream. A resume entry carries the interrupt id and the
approval decision.

## 8. Tools

Bounded, and the boundary is the point. No sandbox (`G17`) — the agent executes no
code; its tools are library operations and dictionary reads.

| Tool group | Approval |
|---|---|
| List and read nodes, list deck contents, read statistics, search the dictionary | none |
| Create a folder or deck, rename, make private, request a word generation, add a sense | none — reversible and owner-scoped |
| **Move, publish, delete, remove a sense** | **required** |

The split is by reversibility and reach. Publishing exposes a subtree to other
people; deleting removes one; moving restructures; removing a sense drops
membership the learner curated. None of those should happen because a model chose
a tool call.

Every tool re-checks ownership when it executes. That is what makes approval a
gate on **intent** rather than on authorization — the authorization check is not
optional and does not depend on the approval having happened.

## 9. Required behaviour

| | |
|---|---|
| **Compaction** (`G12`) | Mandatory. Triggered by a ratio of the context window, never by a message count. Summarise the oldest safe range, keep recent messages, and **never split a tool call from its result**. A per-message cap bounds one message; nothing else bounds a thread |
| **Untrusted content** (`G13`) | Every string from outside is wrapped so the model treats it as data: node names, deck names, dictionary text, tool results. A folder named like an instruction, beside a delete tool, is a real injection path `[R37]` |
| **Stop reasons** | Truncation mid-tool-call drops the block and tells the model. Truncation mid-text keeps the text and marks it truncated. A content refusal is a **result**, not an error, and triggers no fallback |
| **Token budget** | Estimated before the call, actual from the response. Feeds compaction, the per-turn limit, and the credit debit |
| **Model allow-list** | An override outside the list is a clean client error — never a silent downgrade, never a server error |
| **Title generation** | Scheduled only *after* the run row is committed, so a rejected turn neither bills a model call nor titles a conversation from a message that never ran |
| **Admission** (`G5`) | Bounded per learner at run creation. With no worker pool there is no `N_JOBS_PER_WORKER`; a per-learner bound is what stops one learner occupying the API. `uncalibrated` |

## 10. Prompt

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
- the tool list never changes mid-session — an unavailable tool returns a typed
  refusal rather than disappearing from the list;
- deterministic JSON serialisation with a fixed key order;
- thinking blocks are passed back with tool results, never stripped;
- compaction is a deliberate invalidation point.

Log the cache-read token count on every call (`G15`). Always zero means nothing is
cached, and that is a cost bug nothing else surfaces.

## 11. Capabilities that may not be cut

Per R4:

- One active turn per learner, enforced by a Redis lease rather than by
  convention. Tested as a lock, not as a safety net.
- Resume from the checkpoint, never a rerun from input.
- Approval before any destructive tool executes.
- Ownership re-checked inside every tool, independent of approval.
- Untrusted content wrapped.
- A pending interrupt readable over HTTP, so a reload rebuilds the popup.

## 12. Invariants for the checklist

```text
a second turn for the same learner while one is active → 409
a destructive tool cannot execute before approval
reject → the agent receives a refusal and continues
edit → the tool executes with the edited arguments, never the original
a paused turn holds no connection and no worker slot
a reload during approval rebuilds the popup from GET /threads/{id}/state
a node deleted during approval → the tool raises; the agent handles it
a provider failure emits a terminal RunErrorEvent instead of truncating the stream
durability="exit" still checkpoints at an interrupt
resume continues from the checkpoint, not from the original input
compaction never splits a tool call from its result
untrusted content is wrapped
a tool refusal does not change the tool list
the turn lease expires on its own, so a killed process cannot lock a learner out
```

## 13. To verify at implementation time

Not assumed here, because provider behaviour differs:

- how reasoning tokens arrive on a given endpoint — a dedicated delta field,
  inline markers, or not at all. The `thinking.delta` contract hides this from
  clients;
- tool-call streaming: index-based accumulation of a JSON-string argument field;
- whether the provider offers a parallel-tool-call control and honours it.
