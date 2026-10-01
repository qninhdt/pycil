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
POST   /v1/assistant                                      turn or resume, SSE
```

`POST /v1/assistant` is the browser's transport: it accepts a `RunAgentInput` and handles both
a fresh turn and a resume, because a resume carries a `resume` entry on the same
input shape.

**There are no `/runs/{runId}` routes.** Earlier revisions listed a canonical run
read, a resume endpoint and a cancel endpoint. The `assistant_runs` table was
dropped (migration `0007`), the resume decision rides `POST /v1/assistant`, and the run status
a client needs is derived from the checkpoint rather than stored. See §4.

What is dropped from the reference server and why (`G18`):

| Theirs | Dropped because |
|---|---|
| `/assistants`, versions, `/latest`, `/graph`, `/schemas`, `/subgraphs` | one graph. `assistant_id` would be a column with one value |
| `/runs` (stateless), `/runs/batch`, `/runs/wait` | every turn belongs to a Thread; there is no batch caller |
| `/runs/{id}`, `/runs/{id}/resume`, `/runs/{id}/cancel` | no run row to address. The checkpoint holds the pause and `POST /v1/assistant` carries the decision |
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
POST /v1/assistant
  check 10 starts/minute and plan concurrency
  acquire one per-thread execution lease    -> 409 if the thread/account is full
  require remaining usage allowance for new turns/Approve; allow all-Reject at zero
  -> 200 text/event-stream
       graph.astream(...)  ← in this request's task
         message.delta · tool.started · tool.completed  → SSE frames
         interrupt()  → checkpoint and record usage, END STREAM, release the lease
       completion → checkpoint and record usage before RUN_FINISHED
       disconnect → cancel, checkpoint safe state, record completed calls usage, release
```

**There is no Run row, and no second source of truth for turn state.** A turn
either completes in this request, errors, or its connection drops. That is what
makes `G2`'s "the row exists so a background queue is a later config change"
unnecessary: there is nothing to keep in sync, and the checkpoint already holds
everything a resumed turn needs.

The Redis lease is an execution resource bound, not a durable run or usage
record. Free accounts can execute one turn at a time; Pro accounts can execute
five, and each thread can execute only one. A HITL pause releases its slot. The
checkpoint holds the pending approval and the selected model/effort. A later
resume acquires a fresh execution slot.

`usage_events` is the metered usage event record. Each admitted execution gets a
server-generated event key that remains stable for settlement retries within that
request. It never decides whether a client-supplied AG-UI `run_id` already ran;
replaying that ID may repeat a tool effect and is not an exactly-once guarantee.

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
| Provider request timeout | the provider call fails, the graph exits, and the stream emits `RunErrorEvent` |
| Client disconnects | cancel the active model/graph call, shield checkpoint and settlement cleanup for up to 10 seconds, bill completed calls, ignore the incomplete call |
| API process killed mid-turn | best effort: execution may be lost, completed tool effects may not match the last checkpoint, and unsettled usage may be free |
| Concurrent turns | Free allows one and Pro allows five active turns per learner; a thread allows one. HITL pauses hold no slot |
| Start/cancel spam | ten graph starts per learner per minute returns 429 |

The crash window is accepted. Tool effects are not exactly-once and no per-node
checkpoint or execution ledger is added to close it.

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
  → settle completed calls and end the request; release its execution slot
  → the panel renders every action in action_requests, resolving node IDs to names
       approve/reject each action
       submit one decision per action, in action_requests order
  → Command(resume={"decisions":[…]}) on a NEW request, streaming again
```

The product exposes Approve and Reject. It does not expose edited arguments or
free-text responses.

A waiting decision occupies **nothing** (`G9`): no connection or account
concurrency slot. The first request has already returned.

`POST /v1/assistant` accepts a batch `decisions` list, including a one-item list. It is
validated against the number of pending action requests before translation to
LangGraph's `{"decisions":[{"type": ...}]}` shape. Model and
reasoning selection are stored in graph state so resume does not depend on Redis
or a billing event.

**The AG-UI resume shape is translated.** AG-UI sends a `ResumeEntry`
(`interrupt_id`, `status`, `payload`); `HumanInTheLoopMiddleware` reads
`{"decisions": [{"type": "approve"}]}`. `_with_graph_resume` in the router
converts one into the other, and `POST /v1/assistant` refuses a request carrying more than one
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

`durability="exit"` checkpoints when execution exits successfully, with an error,
or at a HITL interrupt. On disconnect, the server cancels the active model/graph
call and waits for exit checkpointing inside a bounded shielded cleanup. It does
not checkpoint every tool/node for crash recovery; a hard process crash remains
best effort.

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
| Create a folder or deck, rename, make private, add a sense | none — reversible and owner-scoped |
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
| **Context window** | Trim with `trim_messages`, reserving the selected model's output budget and estimated system prompt/tool schema tokens; preserve complete tool-call/result pairs |
| **Untrusted content** (`G13`) | Parse JSON tool results and recursively wrap external string values so names, dictionary text and results are treated as data |
| **Stop reasons** | Truncation mid-tool-call drops the block and tells the model. Truncation mid-text keeps the text and marks it truncated. A content refusal is a **result**, not an error, and triggers no fallback |
| **Token budget** | Estimate the selected model's context use before the call; record usage from reported tokens of completed calls |
| **Model allow-list** | An override outside the list is a clean client error — never a silent downgrade, never a server error |
| **Admission** (`G5`) | New turns and Approve resumes require remaining usage allowance. All-Reject resume may close an approval at zero remaining allowance. Disconnect records completed calls; failed calls remain free. Raw remaining units may go negative on overshoot, while available units clamp to zero |

## 10. Prompt

The system prompt is rendered from code-owned Jinja templates. The application
does not serialize a separate cache prefix; provider-side prompt caching is
provider behavior. Usage is accumulated for each completed model call and settled
at graph exit, HITL, or client disconnect. The incomplete invocation contributes
no usage.

## 11. Capabilities that may not be cut

Per R4:

- Free: one active turn per learner; Pro: five. One active turn per thread. A
  pending HITL interrupt holds no slot.
- Ten graph starts per minute per learner.
- Resume from the checkpoint, never a rerun from input.
- Approval before any destructive tool executes.
- Ownership re-checked inside every tool, independent of approval.
- Untrusted content wrapped.
- A pending interrupt readable over HTTP, so a reload rebuilds the popup.

## 12. Invariants for the checklist

```text
a second turn on a running thread → 409
Free with one active turn or Pro with five → another thread gets 409
pending HITL → execution slot released; only resume or delete is accepted on that thread
eleventh start in one minute → 429 with Retry-After
a destructive tool cannot execute before approval
reject → the agent receives a refusal and continues
a paused turn holds no connection and no worker slot
a reload during approval rebuilds the popup from GET /threads/{id}/state
a node deleted during approval → the tool raises; the agent handles it
a provider failure emits a terminal RunErrorEvent instead of truncating the stream
durability="exit" still checkpoints at an interrupt
resume continues from the checkpoint, not from the original input
untrusted content is wrapped
a tool refusal does not change the tool list
the execution lease expires on its own, so a killed process cannot lock a learner out
disconnect → checkpoint safe state and bill completed calls, not the incomplete call
process crash → no exactly-once tool effect or settlement recovery guarantee
```

## 13. To verify at implementation time

Not assumed here, because provider behaviour differs:

- how reasoning tokens arrive on a given endpoint — a dedicated delta field,
  inline markers, or not at all. The `thinking.delta` contract hides this from
  clients;
- tool-call streaming: index-based accumulation of a JSON-string argument field;
- whether the provider offers a parallel-tool-call control and honours it.
