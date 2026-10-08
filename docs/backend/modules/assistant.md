# Assistant conversations, streaming, approvals, and usage

## Responsibility

The assistant exposes owned conversations and native AG-UI streaming on top of a
LangChain agent with PostgreSQL LangGraph checkpoints. It shares Library services and
account usage policy. It does not implement learning-session persistence or a separate
authorization model for content tools.

## Current API

| Operation | Purpose |
| --- | --- |
| `GET /v1/assistant/models` | Configured model/effort/vision choices |
| `POST /v1/assistant/conversations` | Create owned metadata, optional title; 201 |
| `GET /v1/assistant/conversations` | Owner page ordered by updated time/ID descending |
| `GET /v1/assistant/conversations/{identifier}` | Messages and pending persisted approvals |
| `DELETE /v1/assistant/conversations/{identifier}` | Lease-guarded native-thread and metadata cleanup; 204 |
| `POST /v1/assistant:run` | A new turn or approval resolution over SSE |

All routes require authentication. Conversation IDs are UUIDs and ownership is checked
before exposing state. State reads reconstruct the native graph but do not invoke a
model/tool or debit usage. Metadata and native checkpoint records have different owners.

Conversation listing uses opaque viewer-bound `cursor`/`next_cursor` and bounded `limit`;
old timestamp/ID cursor pairs are rejected. The list-node tool accepts the same cursor,
limit and optional inline summary as HTTP. Progress tools return lightweight exact
counts, not mastery/history. Existing mutation approval guards remain unchanged.
Read-only `search_nodes` and `sense_context` tools call the same bounded authorized
services as HTTP; they do not submit reviews, edit profiles or introduce deferred features.

## Input boundary

Use the installed AG-UI `RunAgentInput` shape from OpenAPI, not a custom conversational
JSON protocol. The important local restrictions are:

- `thread_id` is an existing owned conversation UUID.
- A normal turn has exactly one user message.
- `forwarded_props` accepts only `model_id` and `effort`, checked against policy.
- Clients cannot inject `state`, `tools`, `context`, or `parent_run_id`.
- An approval resume contains exactly one resume entry and no new messages.
- Content is supported text or inline base64 images; arbitrary external attachment
  fetching is not offered by this boundary.
- Image models must support vision; allowed MIME types are PNG, JPEG, and WebP.
- Text is at most 8,000 characters; at most 4 images, each up to 10,000,000 decoded bytes.
  The whole encoded request must also fit the 15,000,000-byte HTTP cap.

Effort/model selection is an allowlist, not permission to route to an arbitrary paid
provider. Policy rates and choices are not freshly verified provider billing/catalog data.

## Turn lifecycle and leases

1. Validate input and initial ownership.
2. Construct the configured native model/agent.
3. Acquire a nonblocking renewable Redis conversation lease, then recheck ownership.
4. Load checkpoint state; validate pending interrupts or reject new input while approval is pending.
5. Unless rejecting all pending actions, admit the turn using current plan/allowance
   and increment the per-user/minute start counter.
6. Stream native agent events with 32-tool/33-model-call guards and the SDK request timeout; no whole-turn deadline.
7. In cancellation-shielded cleanup, settle reported usage and update conversation time.
8. Close the event iterator and release the lease even after disconnect/send failure.

FastAPI's request-scoped yield dependency owns this lifecycle through the native
StreamingResponse, including failed header/body sends.

The lease TTL is 30 seconds and renewed every 10 seconds. Busy conversation returns
409 `conversation_busy`. Redis acquisition/loss errors are 503, not a fallback to
uncoordinated concurrent turns. No DB row transaction is held for the duration of model work.

Default admitted start limit is 20/user/minute. A rejected-only resume avoids new
model work, start admission, and the model-cost path; rejecting remains possible when
no fresh allowance is available. There is no universal assistant-turn replay guarantee
equivalent to review Idempotency-Key.

## Tool surface and approval

| Tool | Behavior | Approval |
| --- | --- | --- |
| `search_words` | Native search with available reference entries | No |
| `list_nodes` | Readable immediate children / Library roots | No |
| `get_node` | Authorized metadata and breadcrumbs | No |
| `get_node_editor` | Owned complete membership for Save | No |
| `search_nodes` | Authorized Library or public Discovery search | No |
| `sense_context` | Personal learning state and readable decks for selected senses | No |
| `learning_progress` | Current authenticated user's scoped progress | No |
| `create_node` | Shared create service | Yes |
| `update_node` | Shared atomic Save/move service | Yes |
| `delete_node` | Shared normal-subtree delete service | Yes |

The human-in-the-loop middleware protects the three mutation names explicitly. Change
tool names and that guard together. The packaged prompt is `system_prompt.txt`; ignored
legacy `prompt.md` is not the runtime prompt or packaged fallback. It defines the vocabulary
assistant persona, constructivist single-question active recall, anti-sycophantic calibrated
feedback, multimodal in-situ OCR, and direct tool execution without conversational confirmation
(relying on runtime HITL middleware for mutations).

Approval resume must match the persisted interrupt ID. The entry is resolved, with no
extra metadata, and its payload contains one approve/reject decision per pending action.
No arbitrary modified tool arguments are accepted through approval. If pending approval
exists, a new user-message turn returns `approval_pending`; a mismatched resume returns
`approval_not_pending` or `invalid_approval`.

Rejecting all actions resumes native HITL, which writes the rejection ToolMessages.
A native middleware routing hook then ends the run without invoking the model again. Approval allows the original tools to run, but shared services
still enforce live ownership, quotas, complete deck membership, and publication consent.
Approval is not a privilege override or a guarantee that later execution succeeds.
Typed native tool schemas validate UUIDs, `NodeCreate`, `NodeSave` and `SenseIDs` before
calling the shared business services.

## Streaming and recovery

Response type is `text/event-stream`, with `Cache-Control: no-cache, no-transform`
and `X-Accel-Buffering: no`. `no-transform` prevents Next.js compression from buffering
small events. The frontend rewrite proxy has a 210-second socket inactivity timeout,
longer than the 180-second SDK request timeout; activity resets this proxy timer. Caddy excludes
this route from compression and forwards streaming without introducing full-response
buffering. The server can return safe JSON failures before stream headers start.
During a run, failure is conveyed by native run-error events or an interrupted stream;
the client must not equate status 200 with successful tool completion.

The native `ChatOpenRouter` integration streams provider reasoning and text into AG-UI
events. Standard content blocks preserve reasoning in checkpoint snapshots and reopened
conversations; outbound history uses OpenRouter's reasoning fields. The UI opens reasoning
while it streams and uses the same native Markdown renderer as answer text.
Reasoning is displayed only when the selected provider returns it.
The adapter owns its SDK client inside the SDK async context manager, which closes
connections on completion, cancellation or failure. No custom SDK subclass, stream parser
or history flattening is used. `llm_timeout_seconds: 180` configures the SDK network timeout
for each request (including read inactivity); it is not a total response/turn deadline.
Provider failures and SDK timeouts produce sanitized `assistant_failed` events.

On reload/disconnect, fetch conversation state to see messages and pending approvals.
Do not replay an unknown turn blindly or resolve an old interrupt against a new one.
Persisted native state supports reopening approval, but this is not a promise of exact
replay for every network failure or a backend learning-session resume feature.

## Metering and cleanup

The callback meters completed calls with valid nonnegative input/output token reports.
It distinguishes ordinary input, cached reads, output, and cache writes under configured
Decimal rates, then rounds once to integer units. Missing/incomplete metadata increments
unmetered-call tracking rather than fabricating a token estimate. Unknown cache-write
rates are explicitly represented.

Settlement is idempotent by a new execution key for that accepted turn and is attempted
even after cancellation. Allowance admission is not a prepaid reservation. The system
does not promise that every provider cost report is available or that the configured
rates equal a live invoice.

Deletion acquires the lease, removes the native checkpoint thread, then deletes owned
metadata. Worker retention selects up to 100 conversations older than 30 days, obtains
the same lease, rechecks the cutoff, and cleans them. Busy conversations are skipped.
This cleanup spans native/application transactions, not a single all-or-nothing DB unit.

## Sources and tests

- [Router](../../../apps/api/pycil/assistant/api.py), [turn boundary](../../../apps/api/pycil/assistant/stream.py), [graph/guard](../../../apps/api/pycil/assistant/graph.py)
- [System prompt](../../../apps/api/pycil/assistant/system_prompt.txt), [Prompt research synthesis](../../../tmp/assistant-system-prompt-research.md)
- [Tools](../../../apps/api/pycil/assistant/tools.py), [conversation leases/retention](../../../apps/api/pycil/assistant/conversations.py), [meter](../../../apps/api/pycil/assistant/metering.py), [checkpoint storage](../../../apps/api/pycil/assistant/checkpoints.py)
- [Assistant integration](../../../apps/api/tests/integration/test_assistant.py), [process restart](../../../apps/api/tests/system/test_process_restart.py)
