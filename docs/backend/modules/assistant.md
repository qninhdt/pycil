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
old timestamp/ID cursor pairs are rejected. Assistant tools use bounded task-oriented
inputs and compact batched projections over the same authorized services as HTTP.
They do not persist learning sessions or submit reviews.

## Input boundary

Use the installed AG-UI `RunAgentInput` shape from OpenAPI, not a custom conversational
JSON protocol. The important local restrictions are:

- `thread_id` is an existing owned conversation UUID.
- A normal turn has exactly one user message.
- `forwarded_props` accepts `model_id`, `effort`, and optional `current_view`.
  Model/effort choices are checked against policy; view accepts a page `path` and
  either a `node_id` or `word_id`, never client-supplied names.
- Clients cannot inject `state`, `tools`, `context`, or `parent_run_id`.
- An approval resume contains exactly one resume entry and no new messages.
- Content is supported text or inline base64 images; arbitrary external attachment
  fetching is not offered by this boundary.
- Image models must support vision; allowed MIME types are PNG, JPEG, and WebP.
- Text is at most 8,000 characters; at most 4 images, each up to 10,000,000 decoded bytes.
  The whole encoded request must also fit the 15,000,000-byte HTTP cap.

Effort/model selection is an allowlist, not permission to route to an arbitrary paid
provider. Policy rates and choices are not freshly verified provider billing/catalog data.

## Per-turn application context

For each new request (including an approval resume), the server reads fresh profile
settings and resolves the current view with live authorization. The frontend publishes
IDs from the active Library page or selected dictionary Word and sends the current path
on every turn; it does not recreate the conversation when the view changes.

The model receives one transient HumanMessage immediately after the current user message:
`<context>{compact JSON}</context>`. Its only fields are `now` (ISO date/time in the user's
zone), `timezone`, `current_view`, `name`, and `username`. `name` and `username` use the
current user display name, handle and settings read from PostgreSQL for this turn. View names/types
come from server reads; an unavailable/private node yields only path + unavailable status.
The path remains an untrusted UI hint. JSON escapes tag delimiters, and the teaching prompt
instructs the model to treat context/tool strings as data, not instructions.

This block is inserted only into the outbound model request. It is not persisted in
checkpoints, streamed as a user message, or accumulated in history. Tool-call/result
pairs remain adjacent. The current turn's tool chain is retained while older turns are
trimmed. There is no reminder block.

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
| `search_words` | Up to 10 queries; per-query limit 1–10 (default 3); one deduplicated list of existing WORDs with matched/unmatched queries and sense IDs/definitions; no lexical references | No |
| `read_vocabulary` | Up to 30 Word IDs / 100 sense IDs; deduplicated senses, optional examples, lexical details, personal learning or containing decks | No |
| `search_nodes` | Multiple names in Library or published Discovery; per-query limit; merged nodes with safe paths, roles, editability, reference availability and summaries | No |
| `read_library` | Default Library or a known node: content reads distinct senses with examples/learning; structure lists children; bounded cursor pages | No |
| `learning_overview` | Batch exact scope summaries; optional account-wide activity and scoped future schedules with separate date windows | No |
| `generate_words` | Accept `words`, up to 10 word/expression strings; the vocabulary module selects exact source matches internally and reuses or generates Words; wait up to 30 seconds, then return completed senses or pending task IDs | Yes |
| `get_generations` | Batch task statuses, with a bounded wait and completed Word/senses | No |
| `create_node` | Create metadata and initial deck sense IDs in one transaction | Yes |
| `update_node` | Atomically update metadata and/or membership; null name/description preserves values; `clear_description=true` explicitly clears description; actual added/removed counts | Yes |
| `move_nodes` | Bounded batch; per-item transaction, explicit publication consent and optional retained personal reference | Yes |
| `copy_nodes` | Bounded batch; per-item atomic subtree copy, remapped internal references and batch membership/path writes | Yes |
| `delete_nodes` | Bounded batch; per-item subtree deletion result, protected system roots | Yes |
| `get_preferences` | Saved settings, effective learning choices and plan restrictions | No |
| `update_preferences` | Update only supplied settings, preserve the rest; cannot change plan | Yes |

`include` is optional enrichment, not a second retrieval step. Word reads have a combined
sense hydration cap from configuration; they fail explicitly rather than silently omitting
senses. Search results are merged only after each query's limit is applied.

content supports query, new/due/not_yet_due filters and SQL/keyset ordering, including
mastery_asc (lowest Elo first; unstudied senses use configured initial Elo). A cursor binds
viewer, scope, filters and sort. A page is incomplete while next_cursor is present.
structure never represents a deck's membership. Summary/schedule scope counts must not be
summed when scopes overlap; activity is account-wide. Lifetime streaks are aggregated in
SQL, while only the requested activity date window is loaded into the application.

Batch writes report each item's success/failure; success enrichment is batched after the
writes. Each item is atomic, but the whole batch is not one transaction. In `update_node`,
null and omitted name/description preserve metadata; `clear_description=true` clears the
description and cannot accompany a non-null description. Preference patches keep their
JSON-schema omission semantics. HTTP metadata PATCH retains its separate null-clears contract.
Tools normalize UUID/date/enum output to JSON-safe values before native serialization.
Validation failures return error ToolMessages with safe field locations/messages; rejected
inputs and exception context are not echoed. Business error codes remain distinct.

the vocabulary modulecal reference IDs are private to the generation flow used by the Assistant. It sends
word strings, never reference/target pairs. The Dictionary HTTP API still supports explicit
reference selection. Missing exact matches fail generation rather than generating a fuzzy
suggestion. Finished jobs retain their task IDs and can be read through `get_generations`.

The human-in-the-loop middleware protects all mutation names explicitly by default. Change
tool names and that guard together. The packaged prompt is `system_prompt.txt`; it defines the vocabulary
assistant persona, constructivist single-question active recall, anti-sycophantic calibrated
feedback, multimodal in-situ OCR, and direct tool execution without conversational confirmation
(relying on runtime HITL middleware for mutations).

Account setting `assistant.auto_approve` defaults to false. The existing Assistant-panel
toggle persists it through `PATCH /v1/me/settings`. Each new turn reads the current saved
setting and skips mutation interruptions when enabled. It does not bypass service
authorization, quotas or publication consent. Approvals already pending keep their
explicit approve/reject flow; changing the toggle does not execute old pending actions.

Approval resume must match the persisted interrupt ID. The entry is resolved, with no
extra metadata, and its payload contains one approve/reject decision per pending action.
No arbitrary modified tool arguments are accepted through approval. If pending approval
exists, a new user-message turn returns `approval_pending`; a mismatched resume returns
`approval_not_pending` or `invalid_approval`.

Rejecting all actions resumes native HITL, which writes the rejection ToolMessages.
A native middleware routing hook then ends the run without invoking the model again. Approval allows the original tools to run, but shared services
still enforce live ownership, quotas, membership validation, and publication consent.
Approval is not a privilege override or a guarantee that later execution succeeds.
Typed schemas validate bounded query/ID batches, node changes and preferences before
calling the shared business services. The old API-shaped Assistant tools have been removed;
HTTP resource routes retain their existing contracts.

## Streaming and recovery

Response type is `text/event-stream`, with `Cache-Control: no-cache, no-transform`
and `X-Accel-Buffering: no`. `no-transform` prevents Next.js compression from buffering
small events. The frontend rewrite proxy has a 210-second socket inactivity timeout,
longer than the 180-second SDK request timeout; activity resets this proxy timer. Caddy excludes
this route from compression and forwards streaming without introducing full-response
buffering. The server can return safe JSON failures before stream headers start.
Expected business errors from tools, such as `sense_not_found` or revoked Library
access, return error ToolMessages with safe codes so the model can respond or correct
its request. Authorization and mutation approval remain enforced. Unexpected tool
failures still fail the run. When history contains an unfinished tool call, outbound
model history labels its missing result `tool_result_unavailable`; it never replays
an old mutation or changes saved history.

During a run, failure is conveyed by native run-error events or an interrupted stream;
the client must not equate status 200 with successful tool completion.

The native `ChatOpenRouter` integration streams provider reasoning and text into AG-UI
events. Standard content blocks preserve reasoning in checkpoint snapshots and reopened
conversations; outbound history uses OpenRouter's reasoning fields. The UI opens reasoning
while it streams and uses the same native Markdown renderer as answer text.
Reasoning is displayed only when the selected provider returns it.
The frontend groups reasoning and tool calls into one Thought collapse per user turn,
using the same display projection for streaming and reopened history. Native message
IDs, tool results and approval state stay in the live runtime; the composer and approval
controls use that runtime. Completed message content uses the native message snapshot
when available, so the final run update cannot hide reasoning that appears on reload.
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
metadata. Conversations are retained until explicitly deleted; there is no scheduled purge.
This cleanup spans native/application transactions, not a single all-or-nothing DB unit.

## Sources and tests

- [Router](../../../apps/api/pycil/assistant/api.py), [turn boundary](../../../apps/api/pycil/assistant/stream.py), [graph/guard](../../../apps/api/pycil/assistant/graph.py)
- [System prompt](../../../apps/api/pycil/assistant/prompts/system_prompt.txt)
- [Tools](../../../apps/api/pycil/assistant/tools.py), [conversation leases/deletion](../../../apps/api/pycil/assistant/conversations.py), [meter](../../../apps/api/pycil/assistant/metering.py), [checkpoint storage](../../../apps/api/pycil/assistant/checkpoints.py)
- [Checkpoint restart, lease and owned deletion](../../../apps/api/tests/integration/assistant/test_checkpoints.py)
