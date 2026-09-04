# Pycil Architecture Decisions

> Status: confirmed decisions
>
> Updated: 2026-08-29
>
> Detailed agent target: [`agent.md`](agent.md)

For the agent runtime, [`agent.md`](agent.md) is normative and supersedes this
file wherever the two disagree. This file keeps the cross-cutting topology, auth,
and realtime decisions; `agent.md` owns the agent resource model, schema, DTOs,
event envelope, attachment plane, and acceptance criteria. The current assistant
implementation will be migrated onto `agent.md` rather than evolved in place: the
request-bound path is accepted as something to be replaced, not a base to extend.

The target vocabulary is **agent**, not assistant. Database tables, columns, wire
fields, channels, routes, Python modules, and frontend types all use `agent`; the
word "assistant" survives only when quoting LangChain's own `Assistant` resource or
naming code that still exists today.

**Deployment constraint: pre-production, breaking changes allowed.** Nothing has
launched, so no compatibility shim, dual-read, or expand/contract sequence is
required for any rename. Renames may be atomic and total. This voids the
deploy-window, data-migration, and client-compat classes of hazard — but not the
correctness classes, which still have to be done by hand. The rename-hazard list in
§4 marks which is which.

## 1. Target Topology

```text
Browser
  |-- HTTPS commands/queries ----------------------> FastAPI replicas
  `-- one Centrifugo connection ------------------> Centrifugo replicas
      |-- WebSocket primary
      `-- bidirectional SSE fallback
                                                        |
FastAPI replicas <------ Postgres + Redis ------------+
Agent workers <-------- Postgres + Redis ------------+
Domain workers <-------- Postgres + Redis ------------+
Agent/domain workers ------ private publish ---------> Centrifugo
```

Confirmed:

- Caddy remains the shared public edge.
- FastAPI is the public application API and owns application authorization.
- Centrifugo is the **only realtime gateway**.
- Postgres is canonical state.
- Redis is coordination, lease, rate-limit, and Centrifugo-engine infrastructure;
  it is not canonical business storage.
- API, worker, and Centrifugo replicas must scale horizontally without sticky sessions.
- No new microservice is required for the agent runtime. A dedicated agent worker
  process/pool may share repository and image with the existing worker while using
  separate queues and concurrency limits.

Final realtime recap:

- Browser-to-server commands stay on HTTPS/FastAPI.
- Server-to-browser realtime stays on Centrifugo, with WebSocket primary and
  bidirectional SSE only as fallback.
- No `uni_sse`, no client publish, and no default client RPC.
- Default channel set is `personal:#userId`, `agent:<runId>`, and `job:<jobId>`;
  future `workspace:` and `chat:` channels stay backend-authorized.

## 2. Authentication and BFF

### Decision

Remove the universal Next.js BFF. The browser calls FastAPI directly through the
same public origin routed by Caddy. Next.js becomes UI only.

FastAPI owns browser credentials:

- short-lived access JWT in an `HttpOnly`, `Secure` cookie;
- opaque, rotating refresh credential in an `HttpOnly`, `Secure` cookie;
- explicit SameSite policy;
- CSRF protection for unsafe cookie-authenticated methods;
- transactional refresh rotation and family-reuse detection in Postgres;
- Redis coordination for overlapping refresh attempts without storing bearer tokens.

Bearer authentication remains only for explicit non-browser clients if required.
Requests presenting both Cookie and Bearer credentials are rejected as ambiguous.

JWT validation must include:

- signature and approved algorithm;
- `iss` and `aud`;
- token type/purpose;
- `sub`, expiry, issued/not-before time;
- existing user/token-version revocation checks.

OAuth callback and refresh endpoints belong to FastAPI. Production cookies and
redirect URIs use exact origins. Unsafe browser methods require an origin check
plus CSRF token; SameSite alone is not the CSRF boundary.

### Frontend migration consequence

- Remove `iron-session` token custody and forwarding routes.
- Remove server-side Bearer forwarding from Next.js.
- Move authenticated RSC/server-action data access to browser-safe calls unless a
  narrowly justified server-rendered route is designed separately.
- Generate TypeScript DTOs/client from FastAPI `/v1/openapi.json`.
- Keep one shared frontend transport wrapper for credentials, CSRF, error envelope,
  idempotency keys, and request IDs.

## 3. Realtime with Centrifugo

### Transport decision

Use Centrifugo's full bidirectional protocol with this transport order:

1. WebSocket primary at `/connection/websocket`;
2. bidirectional SSE fallback at `/connection/sse` plus `/emulation`;
3. do not use `uni_sse`.

`centrifuge-js` owns connection state, reconnect/backoff, token refresh, command
replies, and dynamic subscriptions across both transports. WebSocket has the full
feature set and lowest protocol overhead. SSE is a compatibility fallback and
uses `/emulation` only for Centrifugo protocol commands.

Business commands remain FastAPI HTTPS commands. This includes agent Run
create/cancel/resume, job creation, grading, uploads, and durable chat messages.
Client publish and RPC remain disabled by default. If durable chat later needs a
WebSocket command path, add an idempotent RPC-proxy adapter that invokes the same
application service and persists message plus outbox; never use raw client publish
as the canonical write path. Ephemeral typing/presence may use a separately
authorized namespace when that feature exists.

### Connection authentication

1. Browser authenticates to `POST /v1/realtime/token` with the FastAPI cookie.
2. FastAPI verifies user status and token version, then signs a short-lived,
   Centrifugo-only JWT containing `sub`, `iss`, `aud`, `exp`, and server-controlled
   connection metadata where needed.
3. Centrifugo validates signature, algorithm, issuer, audience, expiry, and origin
   before accepting WebSocket or fallback SSE.
4. `centrifuge-js` obtains a fresh token from FastAPI when the connection expires.

The Centrifugo JWT is not an API access token. Caddy exposes the realtime transport,
but Centrifugo-to-FastAPI proxy endpoints remain internal and authenticate the
Centrifugo caller with a separate secret.

### One connection, multiple subscriptions

One browser session opens one physical Centrifugo connection and multiplexes:

| Channel | Subscription | Use |
| --- | --- | --- |
| `personal:#<userId>` | automatic server-side at connect | notifications, account/global events, agent/job inbox hints |
| `job:<jobId>` | dynamic, authorized | word generation, question generation, grading and future domain jobs |
| `agent:<runId>` | dynamic, authorized | interactive/background agent tokens, tools, lifecycle and HITL |
| `workspace:<workspaceId>` | future dynamic, authorized | shared workspace events |
| `chat:<conversationId>` | future dynamic, authorized | chat messages and ephemeral collaboration events |

Enable Centrifugo automatic personal subscription with the `personal` namespace.
The authenticated connection `sub` determines `personal:#<sub>`; the client does
not choose this channel. Activity Center and the current screen reuse the same
dynamic subscription object rather than open duplicate connections.

The personal channel is authorized differently from the rest, and this asymmetry is
deliberate rather than an oversight. Centrifugo documents that the subscribe proxy
does **not** proxy subscriptions to user-limited channels, and `personal:#<userId>`
is user-limited. So:

- `personal:` is gated only by the connection JWT. There is no per-subscribe
  revocation check on it; revoking access means disconnecting the connection.
- `agent:`/`job:` are gated by the proxy, which revalidates token version on every
  subscribe.
- the `personal` namespace must set `allow_user_limited_channels: true`, or
  Centrifugo rejects the subscription with `103: permission denied`.
- if `single_connection` is ever wanted, that namespace also needs `presence: true`.

One proxy endpoint serves every proxied namespace: `channel.proxy.subscribe.endpoint`
is global and only `subscribe_proxy_enabled` is per-namespace, with the handler
branching on the `channel` field. So `/internal/realtime/subscribe` stays one route
and grows a namespace dispatcher rather than splitting.

### Dynamic channel authorization

Client-side subscription is a request, not a grant. Centrifugo denies subscription
by default. Every dynamic namespace (`job`, `agent`, and future `workspace`/`chat`)
must have `subscribe_proxy_enabled=true` and must keep these options disabled:

- `allow_subscribe_for_client`;
- `allow_subscribe_for_anonymous`;
- `allow_publish_for_client`;
- `allow_publish_for_subscriber`.

On each subscribe, Centrifugo sends its authenticated connection user and exact
channel to an internal FastAPI subscribe proxy. The proxy parses a strict channel
shape and grants only when:

- `agent:<runId>`: user owns the Run or has explicit future workspace authority;
- `job:<jobId>`: a live owner/job-interest row authorizes the user;
- `workspace:<workspaceId>`: future active workspace membership exists;
- `chat:<conversationId>`: future active conversation membership exists.

The proxy revalidates user/token version, returns an initial canonical snapshot
when useful, and otherwise fails closed. Channel names and UUIDs are identifiers,
not secrets.

Do not accept subscription tokens for proxy-authorized namespaces initially:
Centrifugo treats a valid subscription token as the authorization decision and
does not call subscribe proxy. If scale later requires subscription JWTs, FastAPI
must issue short-lived tokens bound to one exact authorized channel using a
central authorization service shared with the proxy.

Immediate membership/ownership revocation calls Centrifugo's server API to
unsubscribe or disconnect affected connections. Expiring subscriptions plus
`sub_refresh` may provide periodic revalidation as a secondary control.

### Fan-out and ownership

- Shared word/question generation may have multiple authorized users subscribed
  to the same `job:<jobId>`. One publication is fanned out by Centrifugo.
- Grading is owner-specific even though it uses the same channel format.
- Interactive and future background agent Runs use `agent:<runId>`; authorization
  is owner- or future workspace-scoped by backend policy.
- Subscribe proxy validates user, token version/expiry, object ownership or live
  job interest, and returns an initial canonical snapshot when applicable.
- Clients cannot choose an arbitrary private channel and gain access merely by
  knowing its name.

### Reliability and scale

- Centrifugo is a best-effort latency layer; business success never depends on a
  publication succeeding.
- Postgres transaction plus outbox records canonical state and publication intent.
- Outbox dispatchers use locking such as `FOR UPDATE SKIP LOCKED`.
- Payloads carry version/sequence; clients deduplicate and ignore stale snapshots.
- Bounded Centrifugo history handles short gaps. HTTP state/event reads handle long gaps.
- Centrifugo uses the Redis engine for multi-node fan-out and history.
- Existing WebSocket or SSE connections remain attached to one Centrifugo replica;
  reconnects may land on any healthy replica. Sticky sessions are unnecessary.

## 4. Durable Domain Jobs

Keep the current durable async-task implementation principles while migrating its
public realtime vocabulary from `async:<taskId>` to `job:<jobId>`:

- API creates a task receipt and durable work/outbox record before returning.
- Workers may retry; operations and result application are idempotent.
- Database state is the source of truth.
- Centrifugo publishes versioned task snapshots.
- Client reconnect recovers from the current task read model, not from assumed
  delivery of every publication.
- Shared task work keys may deduplicate expensive word/question generation.
- Owner-specific grading retains owner-scoped interest and authorization.

No Kafka, gRPC, STS, TypeSpec, or cross-service token exchange is introduced for
this monorepo. Those Openlet decisions solve service-boundary problems Pycil does
not currently have.

### Delta between the `job` target and current code

Verified against current source. The `async` → `job` rename is **not** the same
shape as `assistant` → `agent`: some `async` strings are persisted wire data, not
just identifiers.

What renames cleanly (identifiers only, no stored value):

- tables `async_tasks`, `async_task_interests`, `async_task_events`,
  `async_task_outbox`, `async_command_receipts` → `job_*`, plus their indexes
  (`ix_async_tasks_claimable`, `uq_async_tasks_active_work`, `uq_task_event_version`,
  `ix_async_task_outbox_claimable`, `uq_async_command_receipt`).
- `AsyncTaskStatus`/`OutboxStatus` enum *classes* (their string values stay).
- module `pycil/tasks/` and `shared/realtime/channels.py:_ASYNC_NS`.
- arq handler names. All three enqueue sites go through contract constants
  (`tasks/application/dispatch.py:66`, `jobs/reconcile_async_tasks.py:55`,
  `jobs/reconcile_pending_grades.py:97`), `main.py:157-165` fails worker import if
  registrations do not cover the contract, and `test_worker_registration.py:38-51`
  pins the set. A half-rename fails at import, not at runtime.

What is persisted data. Because nothing is in production these can simply be
changed, but each one is a value stored in rows or read by equality, so a rename
means updating the definition **and** every reader in the same change — no
compatibility path is needed, but a half-rename still breaks:

- `async_task_events.schema_name` defaults to `"async-task.v1"`
  (`tasks/infra/models.py:93`, written at `tasks/application/service.py:83`) and the
  browser validates it by **equality** (`apps/web/lib/realtime/task-snapshot.ts:35`).
  Change both sides together, or every snapshot is silently dropped.
- `async_task_outbox.channel` stores the fully-built channel string at insert time
  (`tasks/application/service.py:104`), so a dev database can hold rows naming the
  old channel. Truncate or let them dead-letter; nothing re-emits them.
- work-key prefixes `word:`, `grading:`, `supply:` (`tasks/domain/work_keys.py:15,18,32`).
  `grade_answer._converge_task_snapshot` finds in-flight tasks by exact work-key
  match, so the builder and that lookup must move together.
- task `kind` values `"word"`, `"grading"`, `"question_supply"`
  (`shared/tasks/contract.py:22-24`). These do **not** contain the word "async", so
  the table rename does not touch them. If they are renamed anyway, note the
  reconciler's lookup (`jobs/reconcile_async_tasks.py:45`) and the raw SQL literal
  `kind = 'grading'` (`account_lifecycle/service.py:109,112,117`) both key on them.

### Rename hazards shared by both renames

These apply to `assistant_*` → `agent_*` and `async_*` → `job_*` alike. Since
breaking changes are allowed pre-production, the deploy-sequencing items are noted
only so a dev-stack rename is not mistaken for a failure. The first two are real
correctness work regardless.

**Raw SQL is invisible to a model rename.** `account_lifecycle/service.py:49-131`
hardcodes `assistant_threads`, `assistant_actions`, `assistant_action_audit`,
`async_command_receipts`, `async_task_outbox`, `async_task_events`,
`async_task_interests`, `async_tasks`, and `kind = 'grading'` as strings. Renaming
`__tablename__` compiles clean and these fail at runtime on the account-deletion
path only — the path least likely to be exercised by a smoke check. No type checker
or linter will catch it.

**The LangGraph checkpoint prefix gates erasure, not just retention.** Checkpoint
rows are keyed by the string `assistant:{owner}:{thread}`
(`assistant/application/run_service.py:23`), and two separate places rebuild that
prefix to purge them: `jobs/reconcile_assistant_retention.py:40` and
`account_lifecycle/service.py:133`. LangGraph owns those tables with no foreign key,
so no cascade reaches them. If the prefix becomes `agent:`, all three must move
together; leaving one behind means rows that no purge query matches, which survive
both retention and account deletion. On a dev database that is only clutter, but the
same defect ships to production silently because nothing tests it.

**`pg_notify` channel name is duplicated as two literals.** Publisher
`tasks/application/service.py:110` and listener `apps/worker/pycil_worker/main.py:47`
share no constant. Renaming one alone stops notifications; drains fall back to the
1/min cron, so latency goes from milliseconds to ≤60s — silent degradation, not
failure. Extract to a shared constant as part of the rename.

**Enforcement baselines key on the old names.**
`scripts/fk-delete-rules-baseline.json` holds 20 `assistant_` and 16 `async_` keys
of the form `table.constraint_name`; `verify-baseline.sh:172` fails until it is
regenerated. `scripts/extract-realtime-contracts.py:243-255` hard-codes an AST
lookup for the literal `_ASYNC_NS` and exits non-zero if absent, which fails the CI
freshness gate at `.github/workflows/test.yml:89-96`. Both must move in the same
commit.

**Test surface.** 46 API test files mention `assistant`; 19 API/worker files mention
`async_task`/`ASYNC_TASK`. On the frontend only `task-snapshot.ts` has unit
coverage — `subscribe-async-task.ts`, `use-task-snapshot.ts`,
`use-activity-subscriptions.ts`, and `activity-store.ts` have none, so the web half
of the rename is verified by `tsc` and e2e only.

**Client-persisted state.** The browser persists outstanding work to sessionStorage
under `pycil.activity.outstanding`, and `readPersisted` requires `record.taskId` to
be a string (`apps/web/lib/stores/activity-store.ts:91-107`). Renaming the field
makes existing entries parse to `[]`. Pre-production this is a dev-tab annoyance,
not a migration.

**Deploy sequencing (informational).** `scripts/deploy.sh` migrates at `:70` but
swaps the API at `:101`, so the old image briefly runs against the new schema; and
the web app ships to Vercel on its own cadence (`deploy.sh:10-11`) while the
namespace is also codegen'd into
`apps/web/lib/realtime/grading-result.generated.ts:42` and declared in
`centrifugo-config.json:23`. Neither matters before launch. Both would matter after,
so the rename should land now rather than later.

## 5. API Contracts

- FastAPI OpenAPI is the single HTTP contract source.
- Generate TypeScript types/client from `/v1/openapi.json`.
- Use camelCase on the public wire and typed server DTOs internally.
- Mutating asynchronous commands return `202 Accepted` plus durable receipt/Run ID.
- Use idempotency keys for retryable create/command endpoints.
- Keep stable machine-readable error codes and request IDs.
- Do not maintain handwritten duplicate DTOs in web and API.

## 6. Agent Runtime Decision

### Licensing and product choice

- `langgraph` core is MIT-licensed OSS and may be embedded and extended.
- LangGraph Agent Server is a deployable production runtime/service, not a small
  FastAPI library. Standalone production deployment requires a LangGraph license
  key and license verification/usage reporting under LangChain's current terms.
- Pycil will **not deploy or clone the entire Agent Server**.
- Pycil will implement a narrow Agent Runtime with OSS LangGraph, following Agent
  Server's proven Assistant → Thread → Run → Checkpoint/Store resource model and
  queue-worker lifecycle, renaming that first resource to Agent definition.

The complete target is defined in [`agent.md`](agent.md). Any intentional deviation
from LangChain semantics is labelled there as a Pycil adaptation.

### Confirmed runtime model

- Agent definition: versioned configuration of a Graph (Agent Server's Assistant).
- Thread: accumulated conversation/graph state.
- Run: durable invocation against a Thread.
- Checkpoint: LangGraph-owned short-term execution state in Postgres.
- Store: optional cross-Thread memory, added only for an explicit product need.
- FastAPI: auth, authorization, DTOs, commands, queries, recovery, cancel/resume.
- Agent worker pool: graph execution, model/tool loop, checkpointing, retries,
  cancellation checks, and realtime publication.
- Centrifugo: sole realtime delivery path on `agent:<runId>` over WebSocket primary
  with bidirectional SSE fallback.

### Run behavior

- `POST /v1/agent/threads/{threadId}/runs` creates a background Run and returns
  `202` with `runId`, state, version, and channel.
- API handlers never execute the graph and never return an agent `StreamingResponse`.
- Only one Run executes per Thread; default competing-Run strategy is `enqueue`.
- Worker execution is horizontally scalable through durable Postgres claiming,
  bounded leases, fencing tokens, checkpoint recovery, and idempotent side effects.
- Browser or realtime disconnect does not cancel a Run.
- Cancellation is an explicit durable HTTP command.
- A HITL interrupt leaves its invocation Run immutable; resume creates a new
  continuation Run on the same Thread/checkpoint with `Command(resume=...)`.
- Short recovery may use Centrifugo history; durable recovery uses HTTP Run/events/state.
- Do not persist every token. Publish deltas best-effort; persist complete messages,
  lifecycle, sanitized tool milestones, interrupts, and terminal state.

### Tool calling and HITL

- Build the graph with LangChain `create_agent` or native LangGraph Graph API.
- Register a closed set of typed tools with strict Pydantic schemas.
- Inject `user_id`, token version, Run ID, and optional action ID through runtime
  context; the model never supplies identity or authority.
- Tools call deterministic application services and recheck object authorization.
- Bound recursion, tool calls, tokens, result size, time, cost, and concurrency.
- Use LangChain `HumanInTheLoopMiddleware`/LangGraph `interrupt()` for sensitive tools.
- Resume with `Command(resume={"decisions": [...]})`.
- Keep Pycil `agent_actions` and audit data for authorization, argument digest,
  checkpoint/resource freshness, expiry, one-time execution, and compliance.
- Initially allow `approve` and `reject`; do not enable editable tool calls yet.

## 7. Agent Migration from Current Assistant Code

### Current implementation to remove or reshape

Current code already has useful pieces but combines transport, orchestration, and
execution in the HTTP request:

- `POST /v1/assistant/threads/{threadId}/messages` creates a Run and calls
  `graph.astream()` inside the FastAPI request.
- `POST .../actions/{actionId}/confirm` resumes the graph inside another HTTP stream.
- FastAPI owns the graph/checkpointer in application lifespan.
- each token is committed as one `assistant_run_events` row;
- client disconnect/`GeneratorExit` marks an active Run cancelled;
- Redis leases are tied to the live request execution;
- frontend recovery is coupled to that endpoint's direct SSE format.

These behaviors conflict with the target worker-based Agent Server lifecycle.

Keep and evolve:

- existing owner-scoped Threads/Runs/Actions/Audit concepts;
- LangChain `create_agent`, the typed run context (`AssistantContext` becomes
  `AgentContext`), bounded tools;
- `HumanInTheLoopMiddleware` and checkpoint freshness checks;
- Postgres `AsyncPostgresSaver` with Alembic-owned schema;
- current application-service authorization and resource-generation fencing;
- retention and account-deletion coverage.

Primary code migration map. Left-hand paths are the files that exist today; the
target module is `apps/api/pycil/agent/` and `apps/web/lib/stores/agent-store.ts`.

| Current code | Target change |
| --- | --- |
| `apps/api/pycil/assistant/router.py` | Becomes `agent/router.py`; replace message/confirm streams with Run create/read/events/cancel/resume HTTP commands under `/v1/agent` |
| `apps/api/pycil/assistant/application/run_service.py` | Move graph execution to worker; split durable milestones from ephemeral token publishing |
| `apps/api/pycil/assistant/application/message_flow.py` | Replace request-bound execute/replay flow with durable Run admission and resume commands |
| `apps/api/pycil/assistant/application/graph.py` | Move graph build to agent worker startup; keep tools and middleware |
| `apps/api/pycil/assistant/infra/checkpointer.py` | Move pool ownership to worker; retain Alembic-owned official checkpoint schema |
| `apps/api/pycil/assistant/infra/models.py` | Rename tables to `agent_*`; evolve Run/Action schema and add agent version/outbox/lease fencing |
| `apps/api/pycil/assistant/domain/context.py` | `AssistantContext` → `AgentContext` |
| `apps/api/pycil/main.py` | Remove graph/checkpointer lifecycle from API process; mount the renamed router |
| `apps/web/lib/stores/assistant-store.ts` | Becomes `agent-store.ts`; consume generated Run DTOs and recover from HTTP canonical state |
| `apps/web/lib/api/types/assistant.ts` | Deleted; types are generated from OpenAPI as agent types |
| `apps/web/lib/realtime/provider.tsx` | Make WebSocket primary with SSE fallback; add dynamic `agent:<runId>` subscriptions on the existing connection |
| `apps/worker/` | Add dedicated agent worker role, reconciler, and outbox publisher; rename the assistant cron jobs |
| `packages/shared-py/shared/realtime/` | Rename async channel vocabulary to `job`; add the `agent` channel builder and versioned event-envelope builders |
| Alembic | One rename migration for `assistant_*` → `agent_*` tables, indexes, and constraints before target columns are added |

### Delta between `agent.md` and current code

Acknowledged: `agent.md` is not an increment on the current assistant. It changes
naming, schema, transport, and the public contract at the same time. The list below
is the accepted scope of that migration, verified against current source.

Naming and vocabulary:

- every `assistant_*` table becomes `agent_*`: `assistant_threads` → `agent_threads`,
  `assistant_runs` → `agent_runs`, `assistant_run_events` → `agent_run_events`,
  `assistant_actions` → `agent_actions`, `assistant_action_audit` →
  `agent_action_audit`. Indexes and constraints rename with them.
- the module, route prefix, and frontend types follow: `pycil/assistant/` →
  `pycil/agent/`, `/v1/assistant/...` → `/v1/agent/...`, `AssistantContext` →
  `AgentContext`, `assistant-store.ts` → `agent-store.ts`. The web
  `lib/api/types/assistant.ts` is deleted in favor of generated types.
- Agent Server's `Assistant` resource is called an Agent definition here, so its
  wire fields are `agentId`/`agentVersion`, not `assistantId`/`assistantVersion`.
- channel namespace `async:<taskId>` → `job:<jobId>`; add `agent:<runId>`;
  `personal:#<userId>` does not exist yet in either Centrifugo config or client.
- the unit of work moves from "message" to "Run": `POST /threads/{id}/messages`
  disappears, `POST /threads/{id}/runs` replaces it.
- `client_message_id` → `client_request_id` carried by an `Idempotency-Key` header
  instead of a body field.
- `assistant_actions.tool` → `agent_actions.tool_name`; `checkpoint_version` →
  `checkpoint_id`; `resource_generation` (single int) → `resource_generations` (jsonb).
- `assistant_run_events.sanitized_payload` → `agent_run_events.payload`, plus a
  `durable` flag.
- resume is Run-scoped (`/runs/{runId}/resume`) rather than action-scoped
  (`/actions/{actionId}/confirm`); `actionId` becomes a body field.
- HITL wire vocabulary keeps `approve`/`reject`, but the current flat event name
  `confirmation_required` becomes a `lifecycle`/`run.interrupted` envelope event.
- error codes rename with the prefix: `assistant_thread_not_found` →
  `agent_thread_not_found`, and so on across the whole envelope.
- internal `RunStatus` values stay, but the API gains an explicit adapter to Agent
  Server vocabulary; `cancelled` is published as `interrupted` plus
  `terminationReason=cancelled`. The handwritten web `RunStatus` union changes with it.

Schema:

- new tables: `agent_definitions`, `agent_versions`, `agent_run_outbox`,
  `agent_assets`, `agent_run_assets`, `agent_asset_jobs`,
  `agent_asset_derivatives`.
- `agent_runs` gains agent/version pinning, `parent_run_id`, durable
  `input`/`output`, `metadata`, attempt/max_attempts, `lease_owner`,
  `lease_expires_at`, `fence_token`, `checkpoint_id`, `cancel_requested_at`,
  `available_at`, `started_at`, `finished_at`, `error_detail`, `termination_reason`.
- `ix_assistant_runs_active_thread` is not a uniqueness guarantee; the target adds a
  partial unique index on `thread_id WHERE status='running'` plus a claim index,
  both under the `agent_runs` name.
- `agent_threads` gains `agent_id`, `metadata`, `deleted_at`, and a
  constrained status.
- `agent_actions` gains `tool_call_id` with `UNIQUE(run_id, tool_call_id)`,
  `decided_at`, and `executed_at`.
- the LangGraph checkpoint tables keep their official upstream names; only Pycil's
  own tables are renamed.
- `checkpoint_thread_id` keeps deriving from owner plus thread. Its literal prefix
  is `assistant:` today; changing it to `agent:` would orphan every existing
  checkpoint namespace, so either keep the prefix or migrate checkpoint rows
  deliberately. Decide this before Phase B rather than as a side effect of the rename.
- the run lease moves from a Redis key tied to the live request to Postgres
  `lease_owner`/`lease_expires_at`/`fence_token` claimed with
  `FOR UPDATE SKIP LOCKED`. Redis keeps per-user/global concurrency, per-minute
  rate, and reserved monthly spend; those limits are retained, not dropped. Their
  key prefixes (`assistant:run:`, `assistant:concurrent:`, `assistant:rate:`,
  `assistant:spend:`) rename to `agent:` — safe, since they are ephemeral.

Realtime and SSE:

- the current FastAPI agent SSE goes away entirely: `_event_frame`, the 15s
  heartbeat comment stream, `X-Accel-Buffering`, and the `Last-Event-ID` header are
  replaced by an explicit `?after=<sequence>` cursor on an ordinary JSON endpoint.
- Centrifugo transport today is SSE-only: the client is constructed with a single
  `{transport:"sse"}` entry, the config file enables only `sse`, and Caddy routes
  only `/connection/sse*` and `/emulation*`. WebSocket-primary requires a Caddy
  route for `/connection/websocket`, a client transport list, and origin config.
- one flat `event_type` becomes the versioned envelope with `schemaVersion`,
  `stream`, `event`, `sequence`, `durable`, and `emittedAt`.
- every token is currently one committed `assistant_run_events` row via
  `append_event`; deltas become ephemeral publications that are never persisted.
- durable events gain a transactional outbox; today they are published from inside
  the request path with no outbox on this path at all.
- the subscribe proxy parses exactly one namespace and denies when no snapshot row
  exists yet; it must become multi-namespace with per-namespace authorization, and
  an `agent:<runId>` grant is owner-based rather than interest-plus-snapshot based.
- connection tokens carry `sub`/`iat`/`exp`/`meta` only; the target requires `iss`
  and `aud`. `GET /v1/realtime/token` becomes `POST`.

Attachments:

- entirely new. There is no upload path, no object storage service in the compose
  stack, and no attachment field anywhere in the API or web client today. This
  brings a private S3-compatible backend, presigned direct upload, staging→immutable
  promotion, scan/extract job workers, and a `wrap_model_call` resolver that keeps
  resolved URLs and bytes out of checkpointed state.

Execution and contract ownership:

- graph and checkpointer move out of the FastAPI lifespan; `apps/worker` has no
  Run-executing role yet, only the retention/expiry cron jobs
  (`reconcile_assistant_retention`, `reconcile_expired_assistant_actions`), which
  rename to `agent` too.
- the web types are handwritten; the target generates them from `/v1/openapi.json`.
- settings keys (`assistant_api_key`, `assistant_model`, `assistant_max_tool_calls`,
  …) and their environment variables rename to `agent_*` / `AGENT_*`.

### Migration phases

#### Phase A — rename to `agent`, freeze contracts, add target schema

1. Rename `assistant_*` tables, indexes, and constraints to `agent_*` in one
   Alembic migration, and rename the Python module, settings, router prefix,
   worker jobs, and frontend store/types to match. No behavior changes here.
2. Add internal Agent definition/version and pin each Run to a version.
3. Extend Run with durable input/output, attempt, lease expiry, fence token,
   checkpoint reference, cancellation request, and queue timestamps.
4. Add durable Run outbox and indexes for claiming/recovery.
5. Keep current endpoints temporarily; add new Run create/read/events/cancel/resume DTOs.
6. Generate and adopt the new TypeScript client.

Completion gate: new schema and endpoints exist without changing current user flow,
and no `assistant_` identifier remains outside LangGraph's own checkpoint tables.

#### Phase B — extract execution to agent workers

1. Move graph/checkpointer initialization from FastAPI lifespan to agent worker startup.
2. Create a dedicated agent queue/worker role with separate concurrency limits. It
   MUST set its own arq `WorkerSettings.queue_name` and every agent producer MUST
   pass the matching `_queue_name=`. arq pops job IDs from one sorted set (default
   `arq:queue`) *before* it looks at the function name, so a second worker sharing
   the default queue claims existing domain jobs and hard-fails them with
   `function not found` — and a failed job is not requeued. Recovery would fall to
   `reconcile_async_tasks`, turning every deploy into a stream of failed jobs.
3. Give the agent role a heartbeat key distinct from `worker:heartbeat`. Both roles
   writing the same key makes `/health/ready` (`apps/api/pycil/main.py:112`) report
   ready while one role is entirely down.
4. Claim pending Runs with Postgres locking, lease heartbeat, and fencing token.
   Reuse the existing task vocabulary rather than inventing a parallel one: the
   durable-task tables already carry `lease_owner`, `lease_token`, `lease_fence`,
   `lease_expires_at`, `attempt`, `max_attempts`, `next_attempt_at`. `agent.md`
   calls the same concept `fence_token`; pick one spelling for both before copying
   the pattern.
5. Invoke LangGraph from the worker using the Run's pinned Agent version and Thread ID.
6. Reconcile expired leases and resume from the latest checkpoint.
7. Make side-effect tools idempotent by `action_id`/`tool_call_id` before retrying Runs.

Completion gate: killing any worker does not strand or duplicate an authorized side
effect, and neither worker role can claim the other's jobs.

#### Phase C — move agent realtime to Centrifugo

1. Configure WebSocket primary, bidirectional SSE fallback, automatic
   `personal:#<userId>`, exact origins, and internal proxy authentication.
2. Add `agent:<runId>` channel builder and owner/future-workspace-scoped subscribe
   proxy policy; migrate `async:<taskId>` to `job:<jobId>`.
3. Keep dynamic namespaces default-deny; do not enable client subscribe/publish flags.
4. Map LangGraph stream modes to the event envelope in `agent.md`.
5. Publish token deltas directly as ephemeral events.
6. Persist complete messages and durable milestones plus outbox rows.
7. Publish durable lifecycle snapshots through the outbox dispatcher.
8. Add HTTP event/state recovery by durable sequence.

Completion gate: the client uses one WebSocket-primary Centrifugo connection with
SSE fallback and can recover a completed message after losing every token delta.

#### Phase D — migrate HITL, cancellation, and frontend

1. Change confirm endpoint to durable `POST .../runs/{runId}/resume` returning a
   new continuation Run ID and channel with `202`.
2. Worker executes the continuation with native LangGraph `Command` after all
   existing freshness checks; the interrupted Run remains immutable history.
3. Add durable cancel endpoint and worker cancellation checks.
4. Remove cancel-on-disconnect semantics.
5. Replace the frontend EventSource/direct SSE parsing with Run channel subscription.
6. Rehydrate UI from Run/events/Thread state after reconnect or page reload.

Completion gate: tab close, API restart, and Centrifugo reconnect do not terminate a Run.

#### Phase E — remove legacy path and per-token persistence

1. Remove `/threads/{threadId}/messages` streaming behavior.
2. Remove streaming confirmation endpoint.
3. Remove FastAPI-owned graph/checkpointer lifecycle.
4. Remove per-token `append_event` DB commits and direct SSE framing/heartbeat code.
5. Remove request-bound Redis lease logic after worker leases fully replace it.
6. Update architecture, frontend integration, deployment, retention, and runbook docs.

Completion gate: all acceptance criteria in `agent.md` pass; no second realtime path remains.

#### Phase F — attachment/asset plane

1. Add a private S3-compatible object-storage backend to the deployment stack.
2. Add the asset registry, run bindings, asset jobs, and derivative tables.
3. Add upload-intent/finalize/read/delete endpoints with allow-listed type/size checks.
4. Add scan/extract/index job workers with the same lease/fence rules as Runs, and
   promote verified bytes to an immutable final key before an asset becomes `ready`.
5. Resolve bound assets into LangChain content blocks or retrieval calls inside a
   transient `wrap_model_call` view; never checkpoint URLs, bytes, or provider file IDs.

Completion gate: an unexpired upload credential cannot change the bytes a `ready`
asset resolves, and no resolved URL or payload appears in checkpointed state.

This phase is independent of Phases A–E and may run after them; it is listed last
because nothing in the current codebase supports it yet.

### Recommended implementation order with auth migration

1. Introduce FastAPI cookie auth and generated client while retaining compatibility.
2. Migrate browser API calls away from BFF.
3. Deploy target agent schema/API and worker behind feature flags.
4. Migrate agent realtime to Centrifugo.
5. Remove the direct agent SSE endpoint.
6. Remove BFF/token forwarding and obsolete compatibility paths.
7. Add the object-storage backend and the attachment/asset plane.

This order avoids changing auth custody and agent execution/realtime in one
unrecoverable cutover.

## 8. Hierarchy, Visibility, and Session Scope

Current source anchors:

- [`docs/designs/vocabulary-hierarchy-stats-architecture.md`](docs/designs/vocabulary-hierarchy-stats-architecture.md)
- [`apps/api/pycil/learning/application/session_queue.py`](apps/api/pycil/learning/application/session_queue.py)
- [`apps/api/pycil/learning/application/planning.py`](apps/api/pycil/learning/application/planning.py)
- [`packages/shared-py/shared/fsrs/recall.py`](packages/shared-py/shared/fsrs/recall.py)

Node model:

- One `nodes` table only.
- `FOLDER` is the only type allowed to be a parent/container.
- `DECK` is a leaf and owns opaque Lexi `sense_id` membership.
- `REFERENCE` is a leaf that points live to a readable `DECK`; it is the only cross-owner edge.
- If a referenced target becomes private or deleted, the `REFERENCE` remains but contributes no content; containing-folder publication never overrides target authorization.
- Parent edges are same-owner only.
- The parent tree is acyclic; write paths reject cycles, and read-side ancestor traversal stops on repeats or other degradation paths instead of raising 500.
- Progress identity is global per `(user_id, sense_id)`; a node is path, not identity.

Read, write, and publication:

- A node is readable if the viewer is the owner, the node itself is `PUBLIC`, or it sits under a `PUBLIC` `FOLDER` through an uninterrupted same-owner ancestor chain.
- Writes are owner-only.
- A deleted ancestor hides the subtree below it.
- Publishing a folder is an explicit confirmed action and applies to current and future descendants.
- `PUBLIC` means link readability, not discovery.
- Private and missing both return 404.

Canonical authorization and scope:

- One set-based `_NODE_ACCESS_SQL` serves single-node authorization, batch deck authorization, and breadcrumbs.
- Breadcrumb traversal stops at the first unreadable hop.
- HTTP and agent hierarchy reads use the same gate.
- Agent hierarchy reads intentionally use the owner-only `write=True` path.
- `_mutate` handles `create`, `rename`, and `set-private`.
- `_run_sensitive` handles `move`, `publish`, `delete`, and `add/remove sense` with HITL and an atomic domain mutation/action result.
- Publishing requires approval; making private does not.

Canonical subtree relation:

- The canonical node scope is the recursive same-owner subtree plus distinct sense IDs from direct `DECK`s and independently authorized live `REFERENCE` targets.
- One canonical relation/cache feeds sessions, stats, items, weakest, CEFR, and history.

Structural generation and cache:

- `structural_generation` is subtree version.
- Structural changes are create, move, soft-delete, visibility/publication,
  add/remove sense, and reference creation/removal or target-access changes;
  learning activity is not structural.
- Structural writes bump every structurally affected node, all of their ancestors,
  and ancestors of `REFERENCE`s targeting those affected nodes; learning never
  bumps it.
- Use one set-based recursive CTE plus one `UPDATE`, not per-descendant ancestor loops.
- Postgres is canonical.
- Redis is a generation-fenced cache with a 1 hour TTL.
- Redis failure may increase latency but never changes the result of a committed or rolled-back PostgreSQL mutation.
- Cache keys are `node:{id}:defset:v{generation}[:viewer:{uuid}]`; old generations
  become unreachable without relying on Redis deletion.
- Re-read generation after resolution.
- Publish cached results only if generation is unchanged.
- Evict only after commit.
- Structural mutation and generation bump happen in the same transaction.
- Concurrency uses stable-order advisory locks followed by `FOR UPDATE` re-read; the locks only reduce contention. Correctness rests on constraints.

Complexity envelope:

- Optimize round trips to constants via recursive CTEs and pipelining, while rows touched remain `H/D/N`.
- Enforce a maximum hierarchy depth.
- Do not replace the adjacency list or hard-cap senses merely to hide `O(N)`.
- Answer/FSRS write remains about five primary-key statements in one transaction,
  with FSRS computed in pure Python; it is `O(1)` per question and independent
  of folder size.

Target query budget:

| Operation | Target |
| --- | --- |
| Owner-scoped one-level listing | one keyset query |
| Breadcrumb | one `_NODE_ACCESS_SQL` query |
| Single-node authorization | one `_NODE_ACCESS_SQL` query |
| Batch deck authorization | one `_NODE_ACCESS_SQL` query |
| Subtree to distinct sense set | zero DB queries on cache hit; one canonical query on miss |
| Structural mutation and generation invalidation | one affected-set CTE plus one `UPDATE` |
| Learner aggregate | one indexed range scan |

Exact session top-K:

- Hard eligibility and quota policy stays separate from rank.
- Query top `K` due and top `K` new in PostgreSQL, returning at most `2K` rows.
- PostgreSQL filters the exact eligible set and applies `ORDER BY ... LIMIT K`
  with bounded top-N selection; the application never loads and fully sorts all
  `N` candidates.
- Existing `_slot_split` / `_admit` then applies `NEW_WORD_FLOOR` and backfill.
- Due rank is exactly lowest FSRS recall, then most overdue, represented as `elapsed_days/stability DESC, next_review_date ASC, sense_id ASC`; preserve `stability <= 0` and null-date parity.
- This order-preserving key avoids duplicating the full FSRS recall formula in SQL.
- New rank remains `sense_id ASC`.
- No fixed top-500 approximation, no hard `N` cap, and no extra ranking index before benchmark.
- Exact arbitrary dynamic score without an order-compatible index or precomputed bound still requires evaluating all eligible candidates.
- Target one DB round trip, `O(N_scope + N_eligible log K)` work, and `O(K)` output.
- Verify empty, `2k`, and `100k` with `EXPLAIN ANALYZE` and randomized SQL-vs-Python property tests.
- If the measured SLO fails, the first escalation is flattened `node_senses` materialization, not closure tables, score cache, or approximate retrieval.

Required implementation corrections:

- Add the `(user_id, next_review_date)` and `(user_id, mastery)` indexes.
- Make `load_candidates` use `cached_sense_ids`.
- Pipeline `session_store.create`.
- Set-based generation bump.
- Authorize session start once.
- Unify the three readability implementations.
- Enforce the depth cap.
- No schema migration beyond the two confirmed indexes.
- Implementation order: indexes → cached candidate loading → Redis pipeline →
  set-based generation bump → single session authorization → canonical access
  SQL → depth cap.

## 9. Product Position Against Quizlet

Recorded because it is the premise every learning decision below rests on, and it
is not derivable from code.

Quizlet is a general memorisation tool where the user supplies content. Pycil is a
specialised English-vocabulary tutor where the system supplies content. Nearly
every Quizlet feature maps onto a Pycil feature, one tier deeper, because Pycil
trades generality for depth: Quizlet must treat a card as an opaque string pair
since it also serves anatomy and kanji learners. Pycil does not.

| Quizlet | Pycil | Substantive difference |
|---|---|---|
| Folder → Set, folders do not nest | one `nodes` table, `FOLDER`/`DECK`/`REFERENCE`, arbitrary nesting | real tree with a depth cap |
| "Copy set" — forks a dead snapshot | `REFERENCE` — live pointer to another owner's deck | target edits propagate; a revoked target stays in the tree and says so rather than rendering as an empty deck |
| card = user-typed `term / definition` | learning unit = **`sense`** | `bank` (finance) and `bank` (river) are separate learning units with separate memory state |
| content per user, duplicated without limit | normalised `lexi` dictionary shared system-wide | generated once, reused by everyone; each sense carries IPA UK/US, POS, CEFR, guideword, grammar patterns, register, connotation, collocations, domain, usage note, inflected forms, examples, and syn/ant relations WSD-resolved to the target **sense** |
| 6 parallel modes, user picks | one 5-level retrieval-demand ladder | Quizlet: 6 silos, separate progress each, learner guesses readiness. Pycil: one scale, engine picks |
| Learn-mode heuristic, progress owned by the set | FSRS-4.5, state global per `(user, sense)` | same word in 3 decks = one memory. Node is path, not identity |
| Write mode = string match | level 4 graded by LLM against a server-side rubric, durable job + reconcile | grades "used the sense appropriately", which string match cannot |
| per-set progress bar | mastery distribution, CEFR mix, review history, forecast, weakest — at any scope | real analytics |

Two things with no Quizlet equivalent: the conversational agent with tools over
the learner's own library (destructive actions gated by durable HITL approval —
Q-Chat tutors but cannot restructure a library), and on-demand word generation
with no card-authoring step.

Deliberately absent, not missing: match/gamification, printable tests, native
mobile, spreadsheet import, image cards, i18n, public discovery (`PUBLIC` is
link-readability only), classroom/teacher features, and every subject except
English vocabulary. That last one is the price paid for the table above.

## 10. Learning Engine: Two Independent Axes

Supersedes the checkpoint/retry model in
[`learning-system.md`](learning-system.md) §"Score and State Are Separate".
Full rationale:
[`plans/reports/brainstorm-260829-0831-learning-engine-two-axis-simplification.md`](plans/reports/brainstorm-260829-0831-learning-engine-two-axis-simplification.md).

### Root defect

Depth (retrieval demand: recognition → production) had **no durable home**, so
depth evidence was smuggled into the strength axis. `user_sense_stats` and
`review_log` carry no level column; only `responses` does, and that is a
per-answer transaction table, not a learner model. Four symptoms, one cause:

| Symptom | What it smuggled |
|---|---|
| `is_fallback → Again` (`learning/application/service.py:123`) | a supply shortfall recorded as learner failure |
| five stage names `New..Fluent` computed from `mastery_band()` | depth vocabulary rendered from a strength value |
| `expected_count` ignored → 1 row per `(sense, level, type)` | depth not treated as needing its own evidence |
| 2 checkpoints collapsing to 1 FSRS update via `uq_session_sense_attempt` | two signals forced through one channel |

`components/study/calibration-note.tsx` exists solely to apologise to the learner
for the first row.

### Rejected: copying Quizlet or Duolingo

Quizlet's Memory Score and Duolingo's Half-Life Regression
(`half_life = 2^(θ·x)`, Settles & Meeder 2016) are the same model family as FSRS.
The formula is published; **θ is not**, and θ is fitted on millions of sessions.
With zero review logs the model is uncopyable regardless of source access — the
model *is* the data.

FSRS-4.5 is that model with weights already fitted on public Anki data. It works
from review #1 and is already integrated at 90 LOC. Abandoning it for a
hand-tuned Quizlet-like heuristic means tuning forever with no ground truth:
strictly more work for a worse result. Rejected.

Also rejected: `Hard(2)` for a correct-but-fallback answer. It inverts FSRS
semantics (`Hard` means the learner struggled — subjective) to encode a supply
fact, which is the same category error as `is_fallback → Again` at smaller
amplitude. It is also not free: `update()`
(`packages/shared-py/shared/fsrs/engine.py:65`) branches on `correct: bool` only,
and FSRS-4.5's Hard penalty needs `w15` while `weights.py` stops at `W[14]`.

### Confirmed model

**One question = one grade = one FSRS update.** Each answer emits two independent
signals.

```text
answer
  ├─► WHEN axis — FSRS, 90 LOC, frozen
  │     wrong → Again(1) ; correct → Good(3)
  │     → stability, difficulty, next_review_date
  │
  └─► WHAT axis — depth ladder, ~20 LOC new
        wrong                    → depth--, streak = 0
        correct, served == depth → streak++ ; at 2 → depth++, streak = 0
        correct, served <  depth → unchanged  (no penalty, no credit)
```

The third row is the fix, and it applies to **every** below-depth serve — whether
Lexi ran out of supply or the sampler chose a lower level deliberately (below).
Correct recall at any level *is* successful retrieval, so stability is earned and
`Good` is correct. It is *not* evidence at the requested depth, so depth does not
advance. Nobody is punished and nobody is wrongly rewarded.

The asymmetry in those rules is deliberate: passing below depth is neutral, but
**failing** below depth still retreats. Evidence is asymmetric — failing an easier
item *disproves* the deeper claim, while passing one does not *prove* it.

FSRS therefore stays binary Again/Good — for correctness, not simplicity.
Hard/Easy need a signal that does not exist yet (subjective effort, or calibrated
latency); they stay dead constants as `engine.py` already documents. Latency-based
grading is deferred until telemetry exists to calibrate a threshold.

Depth ladder rule: **streak of 2 to advance, one wrong to retreat**,
deterministic, one extra variable. A serve below `depth_level` is neutral on the
depth axis, so only the at-depth serves in the sampling table below can advance it.
Probe (occasionally serving `depth + 1` to find the ceiling) is deferred —
`probe_rate` has no calibration data, and it can be added later as a flag with no
schema change.

### Schema delta

Add to `user_sense_stats` (`apps/api/pycil/policy/sense_state.py`):

| Column | Type | Meaning |
|---|---|---|
| `depth_level` | int 0..4 | deepest demand the learner sustains; 0 means never assessed |
| `depth_streak` | int | consecutive clean passes at the current depth |

`status` (`new` / `scheduled`) already exists and carries the entry state, so no
third column is needed.

Drop table `session_sense_attempts`. Breaking change, permitted pre-production.
Existing rows reset `depth_level` to 0 rather than being backfilled from the mastery
band — nothing has launched, and a reset cannot encode a wrong claim about depth.

### Delete

The overengineering is **not** the scheduler. The `learning` module is 3861 LOC;
the FSRS engine inside it is 90 (pure, tested, ported verbatim from spec) and is
closed. The bulk is a self-invented session state machine — `session_store.py`
706, `session_flow.py` 493, `service.py` 454, `answering.py` 395,
`round_scheduler.py` 195 — which is neither Quizlet, Anki, FSRS, nor a selling
point. Quizlet is *simpler* than what exists here today.

Remove: `REQUIRED_CHECKPOINTS`, `MAX_RETRIES_PER_CHECKPOINT`, the four-tier
priority order in `round_scheduler.py`, `disqualifier`, `open_checkpoint`,
`open_failed_round`, `retries_used`, table `session_sense_attempts`, and
`components/study/calibration-note.tsx`. Most of the work is deletion.

What replaces the retry machinery is the ungraded re-ask below — the learner-visible
behaviour survives; the state machine does not.

### Keep untouched

FSRS engine and its tests (the diff there must be empty) · Redis-ephemeral /
Postgres-durable split · answer key server-side, `/answers` accepting only
`question_id` · grade lease and reconcile for LLM-graded items · due-first
planning with `NEW_WORD_FLOOR` and the exact top-K design in §8 · the exclusion
set, so a re-ask is always a different question · `restore_delivered` on an
abort/desync, which returns an unanswered question rather than counting it.

Rounds survive, demoted to UI pagination ("8 items, take a break"). They carry no
scheduling semantics.

### Serving: one probability table, keyed by depth instead of mastery

`serve_level` is **not** `depth_level`. Two different questions were collapsed into
one variable in an earlier draft, and the collapse was wrong.

- `depth_level` answers "how deep has this learner proven they can go" — an
  achievement: durable, remembered, monotonic apart from lapses.
- `serve_level` answers "how deep does *this* review ask" — a tactic, and it does
  not have to equal the achievement.

Sample `serve_level` from a window around `depth_level`:

| `depth_level` | L1 | L2 | L3 | L4 |
|---:|---:|---:|---:|---:|
| 1 | 1.00 | — | — | — |
| 2 | 0.40 | 0.60 | — | — |
| 3 | 0.10 | 0.30 | 0.60 | — |
| 4 | — | 0.30 | 0.45 | **0.25** |

Two rules, no more. Only a serve **at** `depth_level` counts toward the streak that
advances depth — so depth climbs more slowly but on real evidence. `depth_level = 0`
is a sense never yet assessed; it takes the exposure path in acquisition and is not
in the table.

The `p(L4) = 0.25` row *is* the level-4 rate limit. Folding it into the table leaves
one mechanism instead of two.

**Correction to an earlier claim in this file's drafting: `policy.py` does not
become dead code.** `LEVEL_PROFILES` is already exactly this shape — five rows of
`{level: probability}`, `_Band`, a sum-to-1.0 assert at import, and
`sample_requested_level`. All of that machinery is kept. What changes is the lookup
key (`mastery_band(mastery)` → index by `depth_level`) and the numbers in the table.
The mechanism was never the bug; keying it to `mastery` — a strength proxy with no
memory of depth — was. `STAGE_NAMES` re-keys to `depth_level`; `mastery` stays a
displayed number and stops being an input to difficulty selection.

The numbers above are **an uncalibrated shape**, chosen not measured — the same
charge levelled at the old `LEVEL_PROFILES`. The defensible difference: the old
table sampled from a memoryless function of strength, this one samples from a window
around a remembered achievement. Wrong parameters here are recoverable; the old
keying was wrong in kind. First thing to measure before tuning: **the false-negative
rate of the level-4 rubric grader**, since that governs how rare L4 should be.

The resolver keeps its descending fallback
(`learning/domain/resolver.py:35`) when Lexi has no supply at the sampled level.
Changing **type** at the same level is normal resolution and is not a fallback; only
dropping a level is, and `served_level` is recorded either way.

### Why the window, and not a monotonic ladder

A strictly monotonic `serve_level = depth_level` was considered and rejected. Cross
the type-coverage table with it:

| Level | Types available |
|---:|---|
| 1 | `definition_mcq`, `contextual_mcq` |
| 2 | `contextual_mcq`, `cloze` |
| 3 | `cloze`, `use_in_sentence` |
| 4 | `use_in_sentence` |

At `depth_level` 3 the learner never sees a multiple choice again, ever. At 4 there
is exactly one type — `use_in_sentence` — forever, so every review of a
well-known word becomes "write a sentence using this word". Three consequences:

1. **LLM grading cost never amortises.** `use_in_sentence` grades via
   `grade_rubric(judge=...)` against the learner's own text, so unlike the shared
   question pool it cannot be reused across learners. In a mature SRS most reviews
   are of mature items, so most reviews would be an LLM call, permanently.
2. **Level-4 supply is one row with no variation source.** Prompt and rubric are
   templates; the learner meets a single prompt for the rest of that word's life.
3. **False negatives concentrate on the learner's best-known words.** MCQ and cloze
   grade deterministically — zero false-grade rate. A rubric grader has a real one.
   Each false negative is a genuine lapse: `min(S, ...)`, `lapse_count++`, interval
   near the floor. This is the same shape as the `is_fallback → Again` defect just
   removed — "the highest-mastery learner is punished most" — with the cause moved
   from a thin pool to a mis-grade.

The window improves all four axes at once, so it is not a cost-for-quality trade:
varied retrieval practice beats repeating one format for retention (contextual
interference, desirable difficulties); LLM grading drops to a fraction of reviews;
most reviews return to deterministic grading; and "diverse questions" keeps meaning
something for the most engaged learners — under the monotonic rule, the longer
someone used Pycil the *less* variety they would see, inverting the selling point.

The argument for monotonic is real and worth recording: for a vocabulary app,
production *is* the actual goal, so asking at production level forever is asking the
right thing. The false-negative accumulation outweighs it, and the window still
keeps the majority weight at or near `depth_level`, so the real goal is still what
is mostly asked.

### Session walkthrough

One session, start to finish, with `target_words_per_session = 10` and
`max_questions_per_round = 8`. This is the normative example; the rules above and
below are all visible in it.

Plan runs once — top-K in Postgres, due-first, backfilled with new, reserving
`NEW_WORD_FLOOR`:

| Sense | status | depth | streak |
|---|---|---:|---:|
| A | scheduled | 4 | 0 |
| B | scheduled | 3 | 1 |
| C | scheduled | 2 | 0 |
| D | scheduled | 4 | 1 |
| E | scheduled | 1 | 1 |
| F | scheduled | 3 | 0 |
| G | scheduled | 2 | 1 |
| H | scheduled | 1 | 0 |
| I | new | 0 | 0 |
| J | new | 0 | 0 |

Prepare demand goes to Lexi asynchronously; nothing waits on it.

Round 1, capped at 8 items:

| # | Sense | Sampled | Served | Answer | FSRS | Depth |
|---:|---|---|---|---|---|---|
| 1 | A | row 4 → L3 | cloze L3 | right | Good | 4 → 4 (below depth, neutral) |
| 2 | C | row 2 → L2 | mcq L2 | **wrong** | Again, `lapse++` | 2 → **1**, streak 0 |
| 3 | I | — | flashcard L0 | ungraded | — | — |
| 4 | B | row 3 → L3 | cloze L3 | right | Good | streak 1→2 → **depth 4**, streak 0 |
| 5 | E | row 1 → L1 | mcq L1 | right | Good | streak 1→2 → **depth 2**, streak 0 |
| 6 | D | row 4 → L4 | use_in_sentence | free text | **pending** (async) | deferred |
| 7 | J | — | flashcard L0 | ungraded | — | — |
| 8 | F | row 3 → L3 | **no L3 supply** → L2 cloze | right | Good | 3 → 3, logged depth-capped-by-supply |

Cap reached → the API returns a `break` state naming round 2.

Round 2:

| # | Sense | Served | Answer | FSRS | Depth |
|---:|---|---|---|---|---|
| 9 | I | mcq L1 (entry, not sampled) | right | Good | `new`→`scheduled`, **depth 1**, streak 1 |
| 10 | G | row 2 → L1 | right | Good | 2 → 2 (below depth) |
| 11 | H | L1 | **wrong** | Again | 1 → 1 (floor), streak 0 |
| 12 | J | mcq L1 (entry) | **wrong** | Again | `scheduled`, **depth 1**, streak 0 |
| 13 | C | mcq L2, different question | right | **nothing written** | unchanged |
| 14 | H | mcq L1, different question | wrong | **nothing written** | unchanged |
| 15 | J | mcq L1, different question | right | **nothing written** | unchanged |

Totals: 15 items — 10 graded (exactly one per admitted sense), 2 exposures, 3
ungraded re-asks. Then a durable `SessionSummary` and the recap.

D's grade is still pending and **the session still completes**. The recap shows one
answer as being graded and SSE updates it; if it settles `Again`, D's depth moves
4 → 3 at that point. This relaxes today's `has_pending_grade` completion block:
the grade is durable, leased, reconciled, and pushed, so blocking a session on an
LLM call buys no safety.

### Session length is derived, not configured

A learner configures exactly two things — `target_words_per_session` (default 10)
and `max_questions_per_round` (default 8), the two columns
`UserLearningSettings` already has. **Round count is not a setting**; it falls out.

Graded answers per sense is invariably **one** (that is the §10 rule). Total *items*
varies because exposures and re-asks are ungraded:

| Sense | Outcome | Items |
|---|---|---:|
| scheduled | right | 1 |
| scheduled | wrong | 2 (graded + re-ask) |
| new | right | 2 (exposure + graded) |
| new | wrong | 3 (exposure + graded + re-ask) |

```text
items  = N + E + W
         N = admitted senses      = target_words_per_session
         E = new senses among them, >= NEW_WORD_FLOOR
         W = senses failed on the graded answer, 0 <= W <= N

rounds = ceil(items / max_questions_per_round)
```

At the defaults, `items` lies in `[N + NEW_WORD_FLOOR, 3N]` = `[12, 30]`, so rounds
lie in **[2, 4]**. A hard upper bound, no long tail.

This is the concrete difference from the deleted machinery. Under
`REQUIRED_CHECKPOINTS = 2` with `MAX_RETRIES_PER_CHECKPOINT = 2` a sense could take
six graded attempts plus an exposure, and a retry had to *wait out a round*, so
round count depended on how many answers were wrong **and how they were spread**.
Two learners with identical settings could see three rounds or nine.

Now `items` is a function of three numbers known before the first round opens, which
is what makes `/next` able to name the round being entered and the client able to
show real session progress rather than a guessed percentage.

### Same-session re-ask: teaching without a second grade

Deleting checkpoints must not delete the re-ask. `learning-system.md`'s principle —
*same-session retries teach and repair; they do not create repeated FSRS updates* —
is correct; what was wrong was the machinery implementing it (checkpoints, tiers,
round-waiting, and the two-checkpoints-collapse-to-one-grade via
`session_sense_attempts`).

A wrong answer therefore does two separate things: it grades once (`Again` + depth
retreat, immediately, durably), and it puts the sense back in a later round as an
**ungraded** item. That re-ask shows a different question (the exclusion set still
applies), gives the learner right/wrong feedback, and writes **nothing** — no
`review_log`, no stability, no depth. Exactly like an exposure.

Three rules complete it:

- Serve the re-ask at the level that was **failed**, not at the new (lower) depth.
  The point is repairing what just broke. No depth rule applies to an ungraded item,
  so there is no inconsistency in serving above the current depth.
- **One ungraded re-ask per sense per session.** Bounds the loop with no retry-budget
  parameter (item 14 above fails its re-ask and gets no second one).
- Enforced by a `graded` set in Redis session state: once a sense is graded this
  session, every later encounter is ungraded. No durable table needed — `responses`
  already carries `idempotency_key = f"{session_id}:{question_id}"` under a unique
  index, and if Redis is gone the session has ended anyway.

### New-sense entry

A never-assessed sense has `depth_level = 0` and `status = new`, and 0 is not a row
in the sampling table. So its first assessment is **L1 by definition, not sampled**.
That first graded answer sets `status = scheduled` and `depth_level = 1` whichever
way it goes; correct additionally sets `streak = 1`, wrong fires `Again` with
`streak = 0`. Exposure alone changes nothing durable — it only marks the sense
exposed in Redis. `depth_level = 0` therefore never coexists with
`status = scheduled`, consistent with level 0 being ungraded exposure.

The lapse floor is `depth_level = 1`, never 0, because 0 now means "not yet in
assessment" rather than "weakest".

### Ordering inside a round

Two hard constraints: a sense's exposure precedes its graded question, and a re-ask
lands in a later round than the failure it repairs. Otherwise **shuffle** — the same
reason the sampling window beat a monotonic ladder: interleaving beats homogeneous
blocks. Cheap, and it needs no priority tiers.

### Why depth is not overhead

`(sense_id, depth_level + 1)` **is** the prepare demand sent to Lexi. The ladder
is what turns "many question formats" into a pedagogical progression — the actual
selling point. Without depth, "diverse" degrades to a random pick among four
formats, i.e. Quizlet's six modes reshuffled. The two columns serve the selling
point, not the scheduler.

The five stage names become truthful: rendered from `depth_level`, while `mastery`
stays strength and is displayed separately. `apps/web/lib/design/mastery.generated.ts`
carries the same five bands keyed to mastery ranges, so its generator re-keys with
the server or the UI will render a stage name from strength while the server
computes it from depth.

### Named consequence

A sense whose supply never reaches level 3+ climbs in stability, reaches
`mastery` 100, and sits at `depth_level` 2. Both facts are true, the UI shows
`Familiar` rather than `Fluent`, and the situation becomes an actionable
operational metric ("N senses depth-capped by supply") instead of today's silent
mis-grading.

The path to a fitted model stays open for free: `review_log` already records
`stability_before/after`, `grade`, and `reviewed_at` — enough to run the FSRS
optimiser for own weights at roughly 50k reviews.

## 11. Question Supply and the Lexi Boundary

### Two generation events, not one

"AI generates the questions" is mostly false, and the expensive event is the other
one.

| | Generate **word** | Generate **questions** |
|---|---|---|
| Entry point | `generate_word_task` → `generate_fenced` | `prepare_questions_task` → `prepare_questions` |
| LLM | **one call synthesising the whole entry** — senses, definitions, examples, IPA, CEFR, aliases, relations, forms, topics | almost never (below) |
| Frequency | once per word, forever | once per session round |
| Nature | synthesising new content | **assembling** from an existing entry |

All LLM spend is in the left column. Questions are mostly mechanical transforms of
an already-generated entry: definition → MCQ stem, example → cloze, forms →
accepted answers.

Across all five plugins, LLM use is exactly three sites: `contextual_mcq` at
**level 2** (`_generate_context` — the only AI-generated question type),
`use_in_sentence.grade` via `grade_rubric` (LLM at *grading* time, not
generation), and nothing else. `flashcard` has no `prepare` at all and is built
on demand without persisting. **No `retrieve` path ever generates**, and that is
the dividing line of the whole design: the question read path never waits on a
model call. Supply is always async, always through a durable task, always ahead of
need.

Generation is requested at session start (demand aggregated per
`(sense_id, level)`, keyed to round 0) and again on each `/next` that advances a
round (keyed separately). When supply is empty the client gets
`preparing`/`waiting`/`exhausted` — never a synchronously generated question.

`prepare_questions` opens with `del owner_uid  # supply is per-word, not per-user`.
The `questions` table is keyed by `(sense_id, difficulty_level, type_id)` plus a
`content_hash`, so **the pool per sense grows and is shared across all learners**:
the second learner to study a sense gets questions the first learner's session
paid to generate. Combined with "only level 2 calls an LLM", question LLM cost per
learner declines toward zero as the user base grows.

Idempotency has two layers: the task claims a fenced lease before doing work (arq
retry and the reconciler both funnel here; the loser returns `duplicate` without
re-running the expensive part), and `QuestionRepository.insert` hashes the
canonical payload with a double-check before and after insert.

### Why lexi-ai is a separate library

It is a **lazily-generating dictionary library**, not a layer of Pycil. It
synthesises an entry by LLM on first lookup, anchors against Cambridge + WordNet
against hallucination, then caches, so later lookups cost zero tokens.

It owns words, senses, examples, collocations, forms, references, relations, tags,
themes/overlays, the asset cache (translation/TTS), and the question engine — 16
tables in schema `lexi`. It owns none of: users, learning progress, FSRS,
hierarchy, sessions, durable tasks, realtime.

The one invariant it declares load-bearing is `normalize.match_key`, used on both
the write path (indexing generated words plus aliases) and the read path
(resolving user input); divergence means permanent lookup misses.

It is separate because it can serve another application: own README, runnable
examples, hermetic tests needing no network, schema portable SQLite↔Postgres,
semantic search as an opt-in extra. So a leak here means **Pycil knowing how Lexi
is implemented**, or **Lexi knowing Pycil exists**.

Structurally both directions are clean. All 11 Pycil→Lexi imports go through
`lexi_ai.contracts` or `lexi_ai.Lexicon`; Pycil SQL touching a Lexi table: zero
hits. Lexi→Pycil: zero files mention `user_id`, `fsrs`, `mastery`, `stability`,
`deck`, `session_id`, or `node_id` as data concepts; the single place Lexi knows
Pycil exists is a docstring in `entry_repo.py:56`. Worth noting, not yet a leak.

### The leaks are in the contract, not the imports

Four confirmed, all the same shape: the published contract under-specifies, so the
consumer rebuilds what Lexi already knows.

1. **Id types are not pinned.** The same logical id is `str` on
   `PresentedQuestion.question_id/.sense_id/.word_id` and `PrepareDemand.sense_id`,
   `int` on `LexiReader.evaluate_answer`/`retrieve_question`, and
   `tuple[int, int]` as a `PrepareReport.produced` key. Pycil casts at 6+ sites and,
   worse, wraps casts in try/except to raise
   `ServiceUnavailableError("lexi_question_presentation_invalid")` — defending at
   runtime against its own dependency's looseness. Pinning identity is the
   contract's job.
2. **The render discriminator is rebuilt as an `isinstance` ladder.**
   `QuestionTypeInfo.render_kind` already exists, but `PresentedQuestion` does not
   carry it, so `question_delivery.render_format()` walks four `isinstance` checks
   and raises at runtime on an unknown kind instead of failing type-check. Keeping
   the wire name separate from the internal type is **deliberate and correct**; the
   fix is for `PresentedQuestion` to carry `render_kind`, after which
   `render_format()` collapses to a field read. `presentation_payload()` genuinely
   is Pycil's job and stays.
3. **`retrieve_exposure` is being used as `word_id_for`.** Pycil's demand is keyed
   by `sense_id` but `prepare_questions` takes a `word_id`, so the worker builds an
   entire flashcard to read one foreign key. Lexi has
   `uow.senses.word_id_for(sense_id)` internally and does not publish it. Fix:
   publish it on `LexiReader`.
4. **Capability isolation is correct but unenforced.** `QuestionEngine._ctx()`
   passes `llm` and `judge` down every path including `retrieve`, so "retrieve never
   generates" rests on plugin discipline rather than structure. Audited: only three
   sites touch a provider and none are on a retrieve path — but nothing prevents a
   future plugin from doing so.

### `expected_count` is ignored, and it was masking the P0

Every plugin treats `expected_count` as a gate (`<= 0` → skip), builds exactly one
question, and reports `produced[key] = 1`. `expected_count=3` yields one row. And
because payloads are deterministic (`distractors.for_word` has no randomness;
shuffles are seeded with a fixed string), a second prepare produces the same
`content_hash` and therefore **zero new rows** — except for level-2
`contextual_mcq`, whose stem comes from an LLM.

So the pool is fixed at one row per `(sense, level, type)`:

| Level | Types available | Rows |
|---:|---|---:|
| 1 | `definition_mcq`, `contextual_mcq` | 2 |
| 2 | `contextual_mcq` (LLM), `cloze` | 2+ |
| 3 | `cloze`, `use_in_sentence` | 2 |
| 4 | `use_in_sentence` | **1** |

Two things broke under the old two-checkpoint model, both derived from source and
not proven by a test run:

- **New words got the same question twice.** `definition_mcq` and
  `contextual_mcq` at level 1 build a stem from the identical template
  `f"Which word means: {sense.definition}"`, differing only by shuffle seed. Two
  rows, one question, options reordered.
- **Level 4's second checkpoint always dropped a level**, since L4 has one row and
  `excluded_ids` removes it.

Under the §10 model — one question, one grade — both stop being correctness bugs
and become quality issues. Variation sources exist where it matters:
`sense.examples` holds several candidates for `cloze` (only the first blankable one
is used today) and the distractor pool reaches 50 (`_TAG_FETCH_LIMIT`) where only 3
are taken. `use_in_sentence` has no variation source short of an LLM call.

`produced` also counts "ensured present" rather than "newly created" — dedup still
sets `= 1` — so the worker over-reports new work.

### Architecture-enforcement tests removed

Deleted as patchwork nobody maintains: `apps/api/tests/test_lexi_boundary.py`,
`apps/api/tests/architecture/`, `apps/api/tests/contracts/`, the 9 import-linter
contracts in `apps/api/pyproject.toml`, the 5 in Lexi's `pyproject.toml`, and
Lexi's `test_contract_imports.py`, `test_facades.py`, `test_no_service_artifacts.py`.

Kept: **`test_contract_answer_safety.py`**. It is not an architecture test — it is
a per-variant field allowlist proving the correct answer can never be reached
through a presentation type. Without it, adding one field to `SingleChoice` is
enough to leak `correct_index` to the browser with nothing reporting it. Also kept:
`test_llm_spend_bounds.py` and `test_guard.py`, which are spend guards rather than
boundary checks.

## 12. Agent Execution Model

`agent.md` §8 already fixes the realtime contract and §14 already rejects native
FastAPI agent SSE. What was never stated is where the run executes, and the current
code answers it the one way no reference design does.

### Current state is inline, and that is the defect

`assistant/router.py:187` calls `stream_run(...)` inside the HTTP handler and
returns a `StreamingResponse`. The LangGraph loop runs in the request coroutine.
Consequences, all verified against current code:

| | Today |
|---|---|
| Run outliving the request | `ASSISTANT_RUN_DEADLINE_SECONDS = 120`, the request is held open for all of it |
| Client disconnect | severs generation |
| HITL approval | `confirm_action` must open a **new** stream; the original run died with its request |
| Deploy | `docker compose up -d api` kills every in-flight run |
| Retry / budget / rate limit | has to be done inside the request path |

### Confirmed: a run is a durable queued row

This is the part that matters, and both reference designs agree on it. Openlet §7
and LangGraph Agent Server both make a run a **durable queued row claimed by a
worker**, never work performed inline in the request:

```text
POST /v1/agent/threads/{id}/messages
  BEGIN
    INSERT runs (status='queued', ...)
    NOTIFY                       -- wake hint, not a work list
  COMMIT
  -> 202 { runId }

worker   claims the run, streams tokens to agent:<runId>,
         persists accumulated text periodically, writes terminal state

client   subscribes agent:<runId> on the connection it already has
```

Mechanics, matching what `tasks` already does for jobs: claim with
`FOR UPDATE SKIP LOCKED`, hold a lease with a heartbeat, fence stale writers, and
let a reaper return expired leases to `queued`. Cancellation is **a column on the
run row** that the worker observes at its next yield point — not a signal, and not
a killed process. LangGraph does the same recovery with a heartbeat window and a
sweeper on a ~2-minute cadence.

### Executor placement: the existing worker deployment, with its own queue

Agent runs execute in a worker, as in openlet's `leti-api` / `leti-worker` split.
`leti-api` is separate because its scaling signal is request rate and its rollout
must be fast, while a worker must drain claims in flight — and Pycil's `worker`
container already has that drain (`deploy.sh`: `docker compose stop -t 30 worker`),
whereas `api` does not.

Agent runs take a **separate arq queue** rather than sharing the learning worker's:
`WorkerSettings` sets no `max_jobs`, so arq's default of 10 is shared across
`generate_word_task`, `prepare_questions_task`, `grade_answer_v1`,
`grade_answer_task`, four reconcilers, `heartbeat`, and `dispatch_task_outbox`.
Three concurrent agent runs at a 120s deadline would occupy 30% of those slots and
put `grade_answer` behind them — a learner waiting for a grade blocked by someone
else's chat. Same image, same codebase, different `queue_name`, one more compose
service.

This is not a premature split: the two cost profiles are measured, not guessed.
A grade is one short LLM call; an agent run is up to `ASSISTANT_MAX_TOOL_CALLS = 12`
tool calls inside a 120s deadline.

`ASSISTANT_PER_USER_CONCURRENCY = 2` and `ASSISTANT_GLOBAL_CONCURRENCY = 50` (the
Redis lease in `run_service.py:36`) become the worker's **admission gate** — the
local semaphore openlet places next to its autoscaler target, and the same role
`N_JOBS_PER_WORKER` plays in Agent Server. The claim loop takes no row while local
slots are full.

Split the agent worker further only on measured evidence. Openlet applies the same
rule to its own worker.

### Tokens go over Centrifugo; no second streaming path

Because the run executes in a worker, the worker holds no HTTP connection to the
client — so the delivery path is the one already in the stack. This is what §14
means by rejecting native FastAPI agent SSE, and no new infrastructure is needed:
Centrifugo, its Redis engine, the subscribe proxy, and the connection-token flow
all exist and already carry `job:` snapshots.

The client subscribes `agent:<runId>` **on the connection it already has** — one
more subscription, not another connection. What has to change is namespace policy,
which is configuration:

| Namespace | History | Recovery | Why |
|---|---|---|---|
| `job` | `size: 1`, ttl 5m | on | snapshot-shaped; only the last frame means anything |
| `agent` | bounded, **ttl ~60s** | on | a disconnect mid-generation must not lose produced tokens |
| `personal` | on, bounded | on | a missed user-scoped control frame must be recoverable |

`centrifugo-config.json` currently declares exactly one namespace — `async`, with
`history_size: 1`. That is right for a task snapshot and wrong for a token stream:
reconnecting mid-generation would recover nothing. Per-namespace policy is the
reason the namespaces are split rather than merged; one shared namespace would let
a long agent reply evict `job` frames a client still needs.

Three layers cover a dropped connection and all three are required:

1. the run surviving the disconnect — true once it executes in a worker;
2. replay of the gap — Centrifugo history plus recovery, free with the config above;
3. a canonical HTTP fallback when the buffer is outrun.

Layer 3 needs the one piece that must be **built rather than configured**: the
worker persists accumulated text periodically, every N tokens or M milliseconds.
The graph checkpointer persists at node boundaries, so a reconnect in the middle of
a single model call would otherwise find nothing to refetch and leave a blank pane.
`recovered: false` is **expected, not exceptional** — a bounded buffer is
sometimes outrun, and the client must refetch canonical state.

## 13. Frontend Consequences

`apps/web` is roughly 11k LOC and had no coverage in this file. Four blocks change,
each because of a decision already confirmed above. `components/ui` (3881 LOC,
shadcn primitives) is untouched by all of them.

### The whole server-action layer disappears

11 files carry `"use server"` under `lib/actions/` — `library-reads.ts`, `nodes.ts`,
`study.ts`, `progress-reads.ts`, `words.ts`, `dashboard.ts`, `settings-reads.ts`,
`learning-settings.ts`, `account.ts`, `assistant.ts`, `realtime.ts`. They exist
**only** because the BFF held the token server-side, so the browser could not call
the API directly. With the BFF removed (§2) they become direct client calls. Also
removed: `proxy.ts`, `lib/auth/session.ts`, `lib/api/upstream.ts`, and both routes
under `app/api/assistant/**`.

Consequence to decide per route, not globally: every page under `app/(app)/` is
currently an RSC reading through a server action. §2 allows "a narrowly justified
server-rendered route designed separately" — which routes those are is still open.

### `lib/api` is largely replaced by a generated client

§2 confirms generating TS DTOs from `/v1/openapi.json`. `lib/api/types/*` is
hand-written types mirroring server DTOs — exactly what the generator emits. Kept
by hand: `request.ts` (the shared transport wrapper: credentials, CSRF, error
envelope, idempotency keys, request IDs) and `error-taxonomy.ts`.

### `lib/study/session-machine.ts` shrinks with the server model

12.1K mirroring the server's session state machine: `roundIndex`, `roundServed`,
break state, exclusion set, "supply ran out of retries", checkpoint reopen. §10
deletes checkpoints, retries, and tiers server-side, so this contracts with them.

Same group: delete `components/study/calibration-note.tsx`; re-source the stage name
in `verdict-panel.tsx` from `depth_level` (its docstring is right that
"Familiar to Applied" is the thing worth showing — the value just has to come from
the depth axis); keep `round-indicator.tsx` with rounds demoted to pagination.

### `lib/stores/assistant-store.ts` is rewritten against `agent.md`

8.1K covering event envelope, channel identity, and HITL recovery. Both the
vocabulary (`assistant` → `agent`) and the shape change.

## 14. Reliability Invariants


- A committed business mutation remains visible through HTTP even if publication fails.
- Retried API requests do not duplicate Runs/tasks/actions.
- Retried worker execution does not duplicate side effects.
- Stale workers cannot write after lease loss.
- Stale task snapshots/events cannot overwrite newer client state.
- One user may reconnect to any API/Centrifugo replica.
- One shared generation may fan out to multiple authorized users.
- One Thread has at most one executing agent Run.
- A waiting HITL Run consumes no worker slot.
- A client disconnect never implies cancellation.
- Personal subscription identity is derived from the authenticated connection `sub`.
- No `agent`, `job`, future `workspace`, or `chat` subscription succeeds without
  an explicit backend authorization decision.
- Knowing or guessing a channel identifier grants no authority.
- Revoking membership/ownership revokes active subscriptions; it is not deferred
  indefinitely until the next browser reconnect.
- No LLM-selected argument grants identity, ownership, or authority.

## 15. Explicitly Rejected for Current Scope

- universal Next.js BFF;
- native FastAPI agent SSE alongside Centrifugo;
- Centrifugo `uni_sse`;
- raw client publish as a canonical business write path;
- client RPC before a concrete chat requirement and an idempotent persistence/outbox adapter;
- licensed LangGraph Agent Server deployment;
- full reimplementation of Agent Server's cron, webhook, A2A, MCP, Store, and
  deployment-control surfaces;
- persistence of every model token;
- Kafka, gRPC, STS, TypeSpec, or premature service decomposition;
- treating Redis or Centrifugo as canonical business state.

## 16. References

- [`agent.md`](agent.md) — normative agent technical design and official sources.
- [LangGraph MIT license](https://github.com/langchain-ai/langgraph/blob/main/LICENSE)
- [Agent Server](https://docs.langchain.com/langsmith/agent-server)
- [Standalone Agent Server](https://docs.langchain.com/langsmith/deploy-standalone-server)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [Centrifugo transport overview](https://centrifugal.dev/docs/transports/overview)
- [Centrifugo WebSocket with SSE fallback](https://centrifugal.dev/docs/transports/sse)
- [Centrifugo channel permission model](https://centrifugal.dev/docs/server/channel_permissions)
- [Centrifugo server-side subscriptions](https://centrifugal.dev/docs/server/server_subs)
- [Centrifugo subscribe proxy](https://centrifugal.dev/docs/server/proxy#subscribe-proxy)

## 17. Remaining Design Order

Covered: auth/BFF (§2), realtime decisions (§3), durable jobs (§4), agent (§6-7 plus
normative `agent.md`), hierarchy scope and query budget (§8), learning engine and
question supply (§10-11), agent execution model (§12), frontend consequences (§13).

Order is by dependency, not by size:

1. **`realtime`** (152 LOC) — the blocking gap. `subscriptions.py:35` hard-codes one
   namespace (`if not channel.startswith(ASYNC_TASK_PREFIX): return None`) while §3
   specifies four (`job`, `agent`, `workspace`, `chat`) each with its own
   authorization rule. Needs a per-namespace dispatcher. Both the agent Run
   subscription and the `job:` rename wait on it.
2. **`account_lifecycle`** (212 LOC) — small, with one known defect: `service.py:88`
   deletes `session_sense_attempts`, the table §10 drops. Its flat `DELETE FROM`
   chain also has not been reconciled against `agent.md` §17's eight-step deletion
   order (cancel non-terminal Runs, preserve audit rows, asset purge, revoke channel
   interests).
3. **`tasks`** (867 LOC) — execution of the §4 delta, not new design. Decide whether
   the `async_*` → `job_*` rename lands in one migration with `assistant_*` →
   `agent_*` or two.
4. **`hierarchy`** (1792 LOC, 16 endpoints) and **`content`** (701 LOC) — §8 covers
   query complexity only. Open: `folders/{id}/{stats,weakest,cefr,items,history}`
   and the parallel `/me/*` set are near-duplicate pairs, and `SenseContent` already
   carries eight learning-state fields its own docstring calls an exception to
   staying lean — `depthLevel` joins them under §10, which is the moment to decide
   whether it stays one DTO or splits.
5. **Frontend** (§13) — depends on everything above.

## 18. Unresolved Questions

- `depth_level` floor on a lapse — resolved: hold at 1, never 0, since 0 now means
  "not yet in assessment" rather than "weakest". Existing rows reset to 0 rather
  than being backfilled from the mastery band.
- The `serve_level` sampling table in §10 is an uncalibrated shape. Measure the
  level-4 rubric grader's false-negative rate first; it governs whether `p(L4)` at
  `depth_level` 4 stays 0.25 or drops.
- Whether a learner may meet the same question again across sessions.
  `excluded_ids` is keyed per session with a 24h TTL, so a new session starts empty
  and the same rows recur. For spaced repetition re-recognition is still review, but
  it means an assessment can be memorised. Product decision, and it gates whether
  `expected_count` should be honoured (§11) or dropped from the contract.
- No blocker. Optional long-term Store, HITL `edit`, provider/model selection, and
  a future durable-chat HTTP-versus-WS-RPC adapter remain product decisions rather
  than architecture gaps.
- The concrete S3-compatible object-storage backend for the asset plane is still
  unchosen; nothing in the current deployment stack provides one.
- Is `job:<jobId>` one namespace for every async task including asset processing, or
  does asset work get its own? `agent.md` currently puts asset jobs on `job:`, but
  the namespace is configured `history_size: 1` — snapshot-shaped. An asset pipeline
  that wants to stream multi-frame progress would lose all but the last frame.
- `lease_fence` or `fence_token`? Resolved: **`lease_fence`**, the spelling the
  durable-task tables already use (`tasks/infra/models.py:44`). `agent.md` §5 changes
  to match, since the agent Run schema copies that pattern rather than defining it.
- Should `agent.md` and `notes.md` be added to `scripts/check-doc-paths.py`? It
  currently scans `docs/*.md` only. Running it against these two by hand reports 4
  "broken" citations in `notes.md`, and 3 of them are correct as written: they name
  the post-rename target paths (`apps/api/pycil/agent/`, `agent-store.ts`) that do
  not exist yet, plus the URL `/v1/openapi.json` which is not a repo path at all. So
  the checker as built cannot validate a forward-looking design doc — adopting it
  here would need either a way to mark target paths or a convention of not
  code-quoting them. Left out for now; revisit after the rename lands, when those
  paths become real.
