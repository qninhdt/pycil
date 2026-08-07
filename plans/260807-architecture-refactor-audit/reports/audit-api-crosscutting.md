# Audit — API cross-cutting / infrastructure layers

Scope: `apps/api/pycil/{tasks,assistant,realtime,ports,policy,auth,common,db,account_lifecycle}`, `config.py`, `main.py`.
Read-only. Every claim cited `path:line`. Paths relative to `/home/qninh/projects/pycil`.

Headline: this is **not** typical AI patchwork. The cross-cutting layers are unusually
deliberate — error taxonomy is generated and typechecked against the frontend
(`scripts/extract-error-codes.py`, `apps/web/lib/api/error-taxonomy.ts:52`), architecture
rules are machine-enforced (8 import-linter contracts, `apps/api/pyproject.toml:93-245`),
and the session-scope bypasses are on an allowlist test with written reasons
(`apps/api/tests/test_session_scope_allowlist.py:40-47`). The real defects are narrower and
mostly about **transaction boundaries** and **one leaky port**.

---

## 1. Dependency injection & wiring

Five distinct mechanisms in use.

| # | Mechanism | Sites |
|---|---|---|
| 1 | FastAPI `Depends` for request session | `apps/api/pycil/db/session.py:14`; used in every router |
| 2 | FastAPI `Depends` for the Lexi port | `apps/api/pycil/content/router.py:131,190,207`; `apps/api/pycil/hierarchy/router.py:190,203,216,291,301`; `apps/api/pycil/learning/router.py:215,245` |
| 3 | Module-level mutable singleton + `global` | `apps/api/pycil/ports/lexi_provider.py:8-9,24,31`; `apps/api/pycil/db/redis.py:9-10,14,21` |
| 4 | `app.state` set in lifespan, pulled off `Request` in handler | `apps/api/pycil/main.py:50-52`; read at `apps/api/pycil/assistant/router.py:119,347` |
| 5 | Explicit parameter injection (a real inversion) | `TokenVersionLookup` at `apps/api/pycil/realtime/application/subscriptions.py:24,48`, supplied by `apps/api/pycil/realtime/router.py:24-31,60` |

Plus a sixth, worker-side: an arq `ctx` dict service-locator
(`apps/worker/pycil_worker/main.py:80-88`) — `ctx["lexi_reader"]`, `ctx["session_factory"]`,
`ctx["lexi_engine"]`, `ctx["redis"]`.

Judgement — **one convention is NOT viable, and unifying is not worth it.**

- `Depends(get_lexi_client)` (#2) and direct `get_lexi_client()` (#3) coexist, and the
  direct calls are in code with no request scope: `apps/api/pycil/assistant/application/tools.py:179`
  and `apps/api/pycil/assistant/application/content_facade.py:37` run inside a LangGraph
  run, not a request. `Depends` cannot reach there. Verified: the whole
  `assistant/application/tools.py` module is allowlisted for exactly this reason
  (`apps/api/tests/test_session_scope_allowlist.py:42`).
- #4 is genuinely lifespan-scoped state (a psycopg pool + compiled graph);
  `app.state` is the FastAPI-idiomatic home for it.
- #5 exists to break an import cycle and is pinned by a contract
  (`apps/api/pyproject.toml:138-142`). Do not touch.

The one **real inconsistency worth fixing**: `_graph(request)` at
`apps/api/pycil/assistant/router.py:118-122` is a hand-rolled dependency —
`getattr(app.state, ...)` + raise — invoked manually inside three handlers
(`:245`, `:300`) rather than declared as `Depends`. It is invisible to OpenAPI and to
the route-auth-coverage introspection (`apps/api/tests/contracts/test_route_auth_coverage.py:37-44`,
which walks `route.dependant.dependencies`). Same for the checkpointer at `:347`.
Cost of unifying: ~15 lines. Size S.

Cost of unifying #3 into #2 wholesale: high and negative. It would mean threading a
reader through `ToolRuntime` for every LangChain tool. Reject.

---

## 2. The ports layer

`apps/api/pycil/ports/lexi.py` — **a real port, and a good one.** `LexiReader` /
`LexiWorkerEngine` are `Protocol`s owned by our side (`:85-128`), with structural view
protocols (`SearchResultView`, `SenseView`, `EntryView`, `:15-83`) instead of vendor
classes. The adapter is a one-line `cast` (`apps/api/pycil/ports/lexi_embedded.py:10-12`),
which is honest: Lexi's reader already satisfies the protocol structurally.

The boundary is **enforced twice, by tests that read source rather than trusting
convention**:
- `apps/api/tests/test_lexi_boundary.py:41-46` — only `from lexi_ai.contracts` or
  `from lexi_ai import Lexicon` are legal static imports, across both deployed packages.
- `apps/api/tests/content/test_lexi_contract_parity.py:17-50` — also catches
  `importlib.import_module` escapes and `Lexicon`-typed parameters.

**Leak, real and admitted:** `lexi_ai.contracts` types cross the port into application
code — `PresentedQuestion`, `AnswerSubmission`, `Evaluation`, `PrepareDemand`,
`Reveal`, `TextResponse`, `Flashcard`/`FreeText`/`SingleChoice`/`TextSpan` — at
`apps/api/pycil/learning/application/question_delivery.py:9`,
`.../answering.py:29`, `.../planning.py:24`, `.../service.py:27`,
`apps/api/pycil/learning/domain/grading.py:5`, `.../domain/resolver.py:8`. The port itself
imports them (`apps/api/pycil/ports/lexi.py:6-12`), so this is a *declared* leak, not an
accidental one: the question/answer/evaluation shapes are shared vocabulary rather than
adapted. Defensible (re-mapping five question render kinds through a parallel hierarchy
buys nothing), but note it lands in `learning/domain/`, which the import-linter otherwise
keeps free of infrastructure (`apps/api/pyproject.toml:199-223` forbids `fastapi`/`sqlalchemy`
there but says nothing about `lexi_ai`).

**Fakes: yes.** `apps/api/tests/learning/fakes.py:85` (`FakeLexiReader`), `:175`
(`FakeLexiWorkerEngine`), plus per-test fakes at `tests/content/test_deck_membership.py:18`,
`tests/content/test_sense_detail.py:37`, `tests/hierarchy/test_subtree_stats.py:16`,
`tests/hierarchy/test_global_analytics.py:33`, `tests/content/test_word_search_auth_boundary.py:29`.
Injected via `app.dependency_overrides[get_lexi_client]`
(`tests/learning/test_submit_answer_pending.py:111`, `tests/content/test_word_search_auth_boundary.py:80`,
`tests/contracts/test_learning_contract_gaps.py:81`). Production depends on the
`LexiReader` annotation, not the concrete class.

`apps/api/pycil/ports/centrifugo.py` — **NOT a port. A concrete vendor client in a ports
package.**

- No Protocol, no interface. Four module-level `async def`s wrapping `httpx` +
  `jwt` against Centrifugo's HTTP API (`:15-89`).
- Callers import the module or the function directly:
  `apps/api/pycil/realtime/router.py:17`, `apps/api/pycil/auth/router.py:20`,
  `apps/api/pycil/account_lifecycle/router.py:15`, `apps/api/pycil/main.py:34`.
  Nothing depends on an abstraction.
- No fake. Tests monkeypatch `httpx.AsyncClient` itself
  (`tests/realtime/test_channels_tokens.py:149,168,194,225,241`) or the module attribute
  (`tests/realtime/test_subscribe_proxy.py:229`) — vendor-shape stubbing, which is exactly
  what a port is supposed to make unnecessary.
- Config is read from the global `settings` inside each function (`:19,42,57,84`), so it is
  not constructible with alternate config either.

It sits in `ports/` because the import-linter contract "shared ports and policy import no
domain" (`apps/api/pyproject.toml:102-117`) is the mechanism that broke the
`auth <-> realtime` cycle. So the *placement* is load-bearing; the *shape* is not a port.

**Dead surface in the "port":**
- `sign_subscription_token` (`apps/api/pycil/ports/centrifugo.py:25-27`) — a one-line
  forwarder to `mint_connection_token`. Zero production callers; only
  `tests/realtime/test_channels_tokens.py:62,73`.
- `unsubscribe_channel` (`:66-89`) — 24 lines including a version-verified docstring. Zero
  production callers. Its absence is *deliberately pinned* by
  `tests/realtime/test_subscribe_proxy.py:207-246`, which asserts the terminal transition
  does **not** call it. So this is a documented decision, not rot — but the function is
  live code kept solely to be not-called.

---

## 3. Error handling

The full path is coherent. Domain raises `AppError` subclass → Starlette dispatches by
exception class → `app_error_handler` → `ErrorEnvelope`
(`apps/api/pycil/common/errors.py:49-141`; wired at `apps/api/pycil/main.py:65-73`). Five
handlers registered, broadest last, with the ordering rationale written down
(`main.py:69-72`).

The clever bit is `AppError.__init__` (`errors.py:67-73`): a snake_case message is
*promoted* to `code`, so `ConflictError("session_scope_changed")` reaches the wire as
`code=session_scope_changed` instead of the class default `conflict`. 31 `ConflictError`
raises and 25 `NotFoundError` raises across the API rely on this.

**Frontend contract: hard-coupled, and correctly so.**
`scripts/extract-error-codes.py` walks the API AST for all three code sources (explicit
raises, class defaults, `code=` literals) and generates
`apps/web/lib/api/error-codes.generated.ts`. `apps/web/lib/api/error-taxonomy.ts:52` is
typed `Record<ApiErrorCode, ErrorTaxonomyEntry>`, so a new API code fails the web
typecheck until a category + message is written. CI regenerates and fails on a dirty tree.
This is the strongest single piece of engineering in the audited scope.

**Bypasses — every one found, and most are justified:**

1. `apps/api/pycil/realtime/application/subscriptions.py:14` — `_DENIED = {"error":
   {"code": 103, "message": "permission denied"}}`, returned at `:57,59,63,80,89`. **Not a
   bug**: this is Centrifugo's subscribe-proxy protocol, not the public API. Code 103 is
   Centrifugo's, not ours. Correct to bypass.
2. `apps/api/pycil/common/middleware.py:33-49` and `:112-133` — the envelope is
   hand-built as a dict (`:37-44`) and hand-serialized (`:115-124`). Necessary: middleware
   runs before/outside exception handlers, and `BodySizeLimitMiddleware` is raw ASGI so it
   has no `Request`. Mitigated — `:116` uses the real `ErrorEnvelope`/`ErrorDetail` models,
   and `apps/api/tests/test_middleware_error_contract.py` (121 LOC) pins the shape. Only
   `_middleware_error` at `:37-44` duplicates the JSON literally.
3. **Zero raw `HTTPException` raises in the whole API.** The only mentions are the handler
   registrations (`main.py:5,9,67,68`) and the import in `errors.py:11`. Genuinely clean.
4. Duplicated status-code mapping: `http_error_handler` (`errors.py:157`) carries its own
   `{401,403,404,405} -> code` dict, independent of the class attributes on lines 76-98.
   Small, but it is a second source of truth for the same four mappings.
5. Nine `raise ValueError` in `apps/api/pycil/auth/oauth.py:39,75,80,97,109,113,122,124,126`
   are caught and re-raised as typed errors at `apps/api/pycil/auth/router.py:31-32,44-48`.
   Deliberate: `oauth.py` is HTTP-transport-free. Fine.
6. Nine `raise RuntimeError` with code-shaped messages that reach the client as
   `internal_error`. Three are startup/config guards and correct (`main.py:113`,
   `config.py:164`, `apps/api/pycil/assistant/application/graph.py:23`,
   `apps/api/pycil/assistant/infra/checkpointer.py:29`). But three are *runtime request-path*
   raises: `apps/api/pycil/assistant/application/tools.py:48` (`assistant_action_not_found`)
   and `:52` (`assistant_action_not_executing`), and
   `apps/api/pycil/tasks/application/service.py:196` (`async_command_receipt_missing_task`).
   These look like codes, are named like codes, and are **not** codes — they land as
   `code=internal_error`, so the frontend taxonomy cannot branch on them and the generator
   never sees them. `tools.py:48/52` are the notable ones: `assistant_action_not_found`
   *does* exist as a real 404 code (raised properly at `assistant/router.py:299,320`), so the
   same logical condition reaches the client two different ways depending on which path
   hit it.

**Taxonomy coherence:** seven `AppError` subclasses, one status each, no overlaps
(`errors.py:76-115`). `TooManyRequestsError` carries `retry_after` and the handler emits
the header (`:133-134`). Coherent.

**Redundant-argument noise:** 13 sites pass `code=X` where the message is already `X`, so
the promotion at `errors.py:71` would produce the identical code. E.g.
`assistant/router.py:121`, `assistant/application/persistence.py:91`, `auth/router.py:32`,
`auth/deps.py:36`, `content/router.py:86`, `assistant/application/tools.py:211,218`. Harmless,
but it means two conventions for the same outcome and a reader cannot tell which is
intended. One genuine use: `hierarchy/application/access.py:38` —
`ForbiddenError("not_node_owner", code="forbidden")` deliberately *widens* the wire code.

---

## 4. Models + transaction boundaries

**Model split is coherent.** `apps/api/pycil/db/models.py` (35 LOC) is an aggregator only —
imports every `infra/models.py` so Alembic sees one metadata (`:6-33`), sets
`target_metadata = SQLModel.metadata` (`:35`). No table is defined there. No duplication
found: each table has exactly one definition.

Two deliberate placements worth noting:
- `UserSenseStats` lives in `apps/api/pycil/policy/sense_state.py:43`, not in `learning/`,
  because `content` and `hierarchy` both read it and that one import was the whole
  `content <-> hierarchy <-> learning` cycle. Rationale documented at `sense_state.py:1-22`;
  re-exported for compatibility at `apps/api/pycil/learning/infra/models.py:29`.
- Task enums are in `apps/api/pycil/tasks/domain/vocabulary.py:15,31`, separate from the
  tables, so a consumer wanting only the vocabulary need not import SQLModel
  (`vocabulary.py:1-10`). Both pinned by the domain-layer contract
  (`apps/api/pyproject.toml:199-223`).

**Unit of Work: none. Ad-hoc commits, 48 sites.** Zero uses of `session.begin()` /
`begin_nested()` anywhere in `pycil/`. Every boundary is a bare `await session.commit()`
inside whichever service function felt responsible.

In-scope commit sites: `apps/api/pycil/tasks/application/service.py:206,262,311,413,445,463,487`;
`apps/api/pycil/assistant/application/hitl.py:53,74,86,106,116,137,173`;
`.../run_service.py:117,128`; `.../persistence.py:68`; `.../tools.py:65`;
`.../hierarchy_facade.py:109`; `apps/api/pycil/assistant/router.py:167,192,248,305,362`;
`apps/api/pycil/auth/router.py:69,74,98,130`; `apps/api/pycil/auth/refresh_sessions.py:97,103,115`;
`apps/api/pycil/auth/dev_identity.py:64,68`; `apps/api/pycil/account_lifecycle/service.py:146`.
Out of scope but same pattern: `content/application/service.py:38,61,76`,
`hierarchy/application/service.py:52,75,94,122,146`, `learning/**` (6 sites).

Where the boundary is **right**:
- `tasks/application/service.py` — every commit is one atomic state transition +
  its event + its outbox row (`:243,262` submit; `:310-311` claim; `:412-413` transition).
  This is the correct grain and it is the whole point of the module.
- `account_lifecycle/service.py:72-146` — ~25 DELETEs, one commit at `:146`. Correct: it
  must be all-or-nothing.
- `auth/refresh_sessions.py:79-117` (`rotate`) — row lock + revoke + successor in one
  transaction (`:88,105,113-115`). Correct.

Where the boundary is **wrong** — three findings:

**(a) `auth/router.py:69` + `:74` — double commit in one request.**
`callback` commits the user upsert at `:69`, then commits the refresh session at `:74`.
Two transactions. If the second fails, the user row is already created with no credential.
It also contradicts the function's own comment at `:61` ("Upsert user in the same
transaction, then issue the JWT"). `refresh_sessions.issue` (`:47-61`) deliberately does
*not* commit — it only `session.add`s — so the `:74` commit is the caller's, and `:69`
should be a `flush()`. Same shape at `dev_identity.py:64,68`.
The exact failure mode `tests/test_session_scope_allowlist.py:96-99` warns about
("two sessions in one request means two transactions, so a later failure leaves the earlier
write committed") — except here it is two commits on one session, which the test cannot see.

**(b) `assistant/router.py:192` and `:248` — a commit for a retention touch.**
Both handlers write `thread.retention_deadline = retention_deadline()` then immediately
commit, *before* doing the actual work. At `:248` this means `send_message` commits a
bookkeeping timestamp, and only then calls `create_or_load_run` (which commits again at
`persistence.py:68`). Three transactions in one request path, for one logical operation.

**(c) The `commit: bool = True` parameter — a transaction boundary passed as an
argument, through 6 functions.**
`hierarchy/application/service.py:59,84,107`; `content/application/service.py:68`;
`assistant/application/hierarchy_facade.py:120,134,145`; `content_facade.py:58`; consumed at
`assistant/application/tools.py:148,159,169,270`. Each site branches:

```
if commit:  await session.commit();  await cache.delete_prior_defsets_quietly(prior)
else:       await session.flush();   cache.defer_invalidation(session, prior)
```
(`hierarchy/application/service.py:74-80`, `:93-98`, `:121-127`; `content/application/service.py:75-82`)

That branch is duplicated four times verbatim. It exists because HITL tools must commit the
domain write and the action result together (`tools.py:37-70`), so the domain service must
not commit. The mechanism works and is regression-tested
(`tests/assistant/test_deferred_cache_invalidation.py`, 182 LOC) — but it is textbook
"boolean behaviour flag", and it forced a whole deferred-invalidation subsystem into the
cache module (`hierarchy/application/cache.py:118-146`, using `session.info` as a side
channel) purely to compensate for the caller not owning the transaction.

---

## 5. tasks + realtime + assistant coupling

**The actual flow** (traced, three producers, one path):

```
producer (HTTP route | assistant tool | learning service)
  └─ generation_quota.reserve_quota(redis)              content/application/generation_quota.py:50
  └─ task_service.submit_or_join(session, ...)          tasks/application/service.py:121
        ├─ AsyncTask + AsyncCommandReceipt + AsyncTaskInterest
        ├─ _record_event_and_outbox()                   :91-106
        │     ├─ AsyncTaskEvent(snapshot)
        │     ├─ AsyncTaskOutbox(channel=channels.async_task(id), payload=snapshot)
        │     └─ pg_notify('async_task_outbox')         :105
        └─ ONE commit                                   :262
  └─ arq enqueue_job(...)  in try/except: pass          content/router.py:112-116
                                                        assistant/application/tools.py:243-248
                                                        learning/application/answering.py:393-399
                                                        learning/application/session_flow.py:274-280
worker:
  LISTEN async_task_outbox → _drain_task_outbox         apps/worker/pycil_worker/main.py:69-76
  └─ dispatch_task_outbox: claim → POST /api/publish → ack | retry
                                                        apps/worker/pycil_worker/jobs/dispatch_task_outbox.py:17-47
  job (generate_word_task | grade_answer_task | prepare_questions_task):
     claim_task → work → transition_task → new event+outbox → publish
browser:
  Centrifugo → subscribe proxy → authorize_subscription  realtime/application/subscriptions.py:45
     └─ verifies live interest + token_version, returns latest snapshot as `data`
```

**Architecture: transactional outbox + `LISTEN/NOTIFY` push + cron sweep.** Correctly built.
The event and the outbox row are written in the same transaction as the state change
(`tasks/application/service.py:243,310-311,412-413`), `pg_notify` fires only on commit
(`:103-105`), the outbox row is leased before publish and acked only after Centrifugo
accepts (`dispatch_task_outbox.py:21,30-46`), and republish-on-crash is deliberate
(same event id / version, so the client's `reduceAsyncTaskSnapshot` dedupes by version —
`apps/web/lib/realtime/task-snapshot.ts:14-30`).

Assistant→realtime is **not** coupled through this path at all. Assistant SSE is a
*direct* FastAPI `StreamingResponse` off persisted `AssistantRunEvent` rows
(`assistant/router.py:143-147`, `:265-275`; events persisted before yield at
`run_service.py:100-119`). Two independent realtime transports — Centrifugo for tasks,
raw SSE for assistant runs. That is a real duplication of "recoverable event stream"
machinery (sequence cursor, `Last-Event-ID` at `assistant/router.py:150-154` vs Redis
history + snapshot at `subscriptions.py:96-99`) but they solve different problems
(token-by-token streaming vs. fan-out to a reconnecting tab) and merging them is not
obviously better.

The assistant *does* couple to `tasks` for one thing: `request_word_generation`
(`tools.py:202-249`) goes through `submit_or_join` exactly like the HTTP route, sharing
work key, quota and receipt. Verified by a dedicated test whose docstring records why
(`tests/assistant/test_word_generation_tool_uses_durable_tasks.py:1-11`). That is
correct convergence, not coupling.

### The reconcilers — verdict: legitimate, with one exception

Four reconcilers + the outbox dispatcher (`apps/worker/pycil_worker/main.py:128-135`).

**`dispatch_task_outbox` cron (`main.py:134`) — legitimate, and not a reconciler.** It is
the outbox relay's recovery sweep, needed because `LISTEN` is best-effort: a notification
lost during a worker restart or connection drop would otherwise strand a committed event.
The startup ordering is deliberate and correct — listener registered *before* the initial
drain (`main.py:90-93`) so nothing slips between them.

**`reconcile_async_tasks` (`main.py:130`, every minute) — legitimate, and the root cause is
architectural, not a bug.** The primary write path *is* transactional; what is not
transactional is the **arq enqueue**, which cannot be, because it targets Redis while the
task row is in Postgres. All four producers therefore swallow enqueue failures
(`content/router.py:115-116`, `tools.py:246-248`, `answering.py:399`, `session_flow.py:280`),
each with a comment saying the reconciler owns recovery. This is the correct resolution of
a genuine dual-write: commit the durable row first, treat the queue as a latency
optimization, sweep for lost enqueues. The alternative (enqueue inside the transaction) is
impossible; the other alternative (drive worker dispatch off the outbox too) would be a
larger redesign for the same guarantee.

Two smells inside it, though:
- `list_reenqueueable_tasks` (`tasks/application/service.py:334-351`) filters
  `isinstance(task.dispatch, dict)` **in Python after loading every claimable row**. Not
  bounded by a `LIMIT`. Every minute. On a backlog this loads the whole set.
- The `kind` dispatch is a 3-branch `if/elif` chain (`reconcile_async_tasks.py:18-49`) that
  must be edited in lockstep with every new task kind, plus an `else` that logs unknowns
  (`:43-49`). The comment at `:47-48` records that `question_pool` was such a silently-dead
  kind. This is the growing-conditional-chain smell, and it is the one place a new task
  kind can be forgotten.

**`reconcile_pending_grades` (`main.py:129`) — legitimate, but it is *two* mechanisms in
one job.** Passes 1 and 2 (`reconcile_pending_grades.py:34-70`) are a data-retention purge
of `raw_answer` after 24h/48h, with a documented lease/starvation interaction
(`:8-16`, `:53-56`). Pass 3 (`:72-95`) is the lost-enqueue requeue, bounded at
`REQUEUE_BATCH = 100` (`:18`) — note `reconcile_async_tasks` has no such bound. Retention
purge and enqueue recovery are unrelated concerns sharing a cron slot.

**`reconcile_expired_assistant_actions` (`main.py:131`) — legitimate.** Actions have a TTL
(`config.py:71`) and nothing else can expire them; the query uses
`with_for_update(skip_locked=True)` so it cannot race a user confirmation
(`assistant/application/hitl.py:99`). A time-based expiry sweep is not a patch for
anything.

**`reconcile_assistant_retention` (`main.py:132`, daily 03:15) — legitimate.** A GDPR-style
retention job. It also has to hand-delete LangGraph's checkpoint tables because LangGraph
keys them by a `thread_id` *string* with no FK, so no cascade reaches them
(`reconcile_assistant_retention.py:12-19`). That is vendor-imposed, not a design flaw.

**The one that IS a patch: `grade_answer._converge_task_snapshot`**
(`apps/worker/pycil_worker/jobs/grade_answer.py:59-98`). Its own docstring is the
diagnosis: `reconcile_pending_grades` re-enqueues `grade_answer_v1` **by response id, not
by task id** (`reconcile_pending_grades.py:93-95`), so that path has no task id, published
to a channel the subscribe proxy denies, and left the `AsyncTask` in QUEUED forever while a
verdict had already been applied. The fix re-finds the task through `find_live_task`
(`tasks/application/service.py:316-331` — a function that exists *only* for this) and
claims + transitions it. So there are two grading job entry points (`grade_answer_v1` at
`grade_answer.py:124` and `grade_answer_task` at `:129`) with two different task-settling
strategies, and `find_live_task` + `_converge_task_snapshot` + `grade_answer_v1` are all
scaffolding around the reconciler having the wrong identifier. Root cause: the reconciler
should re-enqueue by task id. That would delete three functions.

---

## 6. AI-patchwork smells

**`assistant/application/hierarchy_facade.py` — a genuine Facade, not a shim.** 149 LOC.
Every function adds a real ownership check the underlying service does not do: `_owned_node`
(`:17-22`) verifies `author_id == actor_id` and not-soft-deleted, and it is applied to
*every* prompt-supplied ID including cursors (`:50-52`) and target parents (`:79`, `:95`,
`:124`). It also projects ORM rows to LLM-safe dicts (`node_payload`, `:24-32` — no
`author_id`, no timestamps). The reason is in the module docstring (`:1-5`) and it is
correct: node-ID-only services are IDOR-prone when the IDs come from a language model.
Two of eleven functions are thin (`get_node` `:71-72`, `set_private` `:128-130`), but even
those add the check. Verdict: keep. Same for `content_facade.py` (61 LOC).

Real smells found:

1. **`content_facade.py:8` imports `_owned_node` — a private name — from
   `hierarchy_facade`.** Cross-module private access. It is the shared authorization
   primitive, so it should not be underscore-prefixed (or should live in one place both
   import from).
2. **`content_facade.py:19` — function-local `from pycil.common.errors import ConflictError`
   inside an `if`.** No cycle justifies it: the module already imports `NotFoundError` from
   the same module at `:9`. Same pattern, same file, at
   `content/application/service.py:144,148`. Pure leftover.
3. **Function-local imports elsewhere, 8 sites**, mostly unjustified:
   `assistant/application/persistence.py:86-87` (`User`, `ForbiddenError`),
   `hitl.py:121` (`async_session_factory`), `hitl.py:148` and
   `run_service.py:220` (both `from pycil.hierarchy.infra.models import Node`, inside a
   loop body at `run_service.py:220`), `generation_quota.py:52` (`settings`).
4. **`stream_run` is doing too much** (`run_service.py:175-274`, 100 LOC). Inside the
   `updates` branch it opens its own session, imports `Node` (`:220`), loops three argument
   keys resolving names and generations (`:222-236`), mutates the argument dict (`:237`),
   creates the pending action, sets status, and appends an event. The name-resolution block
   (`:210-237`) is a distinct concern (building a human-readable approval prompt) inlined
   into the streaming loop.
5. **Dead code — `AsyncTaskSnapshot`** (`apps/api/pycil/tasks/domain/schemas.py:10-20`). A
   Pydantic model of the task snapshot wire shape, with aliases. **Zero importers** in
   Python. The actual snapshot is built as a hand-written dict in
   `tasks/application/service.py:75-88`, and the frontend has its own independent
   `AsyncTaskSnapshot` interface (`apps/web/lib/realtime/task-snapshot.ts:3`). So the one
   Python definition that *should* be the contract is unused, and the wire shape lives in
   an untyped dict literal. Compare `shared/realtime/payloads.py:11-33`, where
   `GradingResult` is the single definition and both the SSE payload and the task snapshot
   go through it — that is the pattern this should follow.
6. **Single-use dead forwarders in the "port"** — `sign_subscription_token`
   (`ports/centrifugo.py:25`), `unsubscribe_channel` (`:66`). See §2.
7. **`lexi_provider.py` wraps `lexi_embedded.py` in a second layer of the same names.**
   `create_embedded_lexi_reader` (`lexi_provider.py:12-14`) is a one-line forward to
   `create_embedded_lexicon_reader` (`lexi_embedded.py:15`); `close_embedded_lexicon`
   (`lexi_provider.py:17-19`) is a one-line forward to `lexicon.close()`, and is duplicated
   verbatim in `apps/worker/pycil_worker/main.py:52-54`. Two files, ~15 lines, three
   forwarders, for one singleton.
8. **`error_responses()` used by 2 of 7 routers.** Declared at `errors.py:41-46`; applied
   only in `assistant/router.py` (3 routes) and `realtime/router.py` (2 routes). Zero uses
   in `auth/`, `content/`, `hierarchy/`, `learning/`, `account_lifecycle/`. So the OpenAPI
   error contract is documented for 5 routes out of ~40.
9. **Defensive re-validation (correct, but worth naming):** `token_version` is re-read from
   the DB on every request (`auth/deps.py:46-49`), *again* before every assistant mutation
   (`persistence.py:84-91`, called from `tools.py:34,42`), and *again* in the subscribe
   proxy (`subscriptions.py:61-63`). Three reads of the same integer per assistant tool
   call. Justified — it is the revocation mechanism and the assistant run outlives the
   request — but it is the reason `revalidate_actor` is called twice in `_run_sensitive`
   paths (once via `_mutate`, once inside).
10. **Redundant `code=` on 13 raises** (§3) — two conventions, one outcome.
11. **`config.py:167-171` — `get_settings()` factory plus a module-level `settings`
    singleton.** `get_settings` has one caller: line 171. Everything else imports
    `settings` directly (~20 modules). The factory is a DI seam nothing uses.
12. **Stale import-linter entries:** `apps/api/pyproject.toml:112` and `:156` both forbid
    `pycil.jobs`, a package deleted in the working tree (`git status` shows
    `D apps/api/pycil/jobs/*`). Exactly the rot the repo's own comment warns about
    (`pyproject.toml:90-91`: "a contract nobody has seen fail is a comment").

---

## 7. Pattern opportunities — with skepticism

### P1. Unit of Work / explicit transaction scope — **recommend, narrowly**

(a) Problem: 48 scattered `session.commit()`; three request paths commit two or three
times (`auth/router.py:69,74`; `assistant/router.py:192,248` + `persistence.py:68`); the
transaction boundary is a `bool` parameter on 6 functions with a 4×-duplicated
commit/flush branch.
(b) Bad because: `auth/router.py:69` can leave a user row with no refresh credential, and
it contradicts its own comment at `:61`. And the boolean flag is a *caller-supplied*
transaction boundary, which is why `cache.defer_invalidation` had to be invented
(`hierarchy/application/cache.py:118-146`) — a `session.info` side channel compensating for
services not owning their commit.
(c) Pattern: services never commit; the caller opens `async with session.begin():`. A
post-commit hook (SQLAlchemy `after_commit` event, or a small UoW object holding a
callback list) replaces `defer_invalidation`/`flush_deferred_invalidations`.
(d) Trade-off: touches 48 sites across all domains. High regression risk in
`tasks/application/service.py`, which has intricate `IntegrityError` + rollback +
re-read logic depending on exact commit placement (`:226-241`, `:261-268`).
(e) Beats the simpler fix? **Only partly.** The simpler fix for (a) — change
`auth/router.py:69` to `flush()`, drop `assistant/router.py:192,248` into the following
commit — is 4 lines and captures most of the value. Recommend doing *that* first,
independently. Full UoW only if the `commit: bool` flag is being removed anyway, and
explicitly **exclude `tasks/application/service.py`** from the refactor: its commits are
already exactly one atomic transition each and are the most-tested code in scope.

### P2. Make `ports/centrifugo.py` an actual port — **recommend**

(a) Problem: concrete `httpx`+`jwt` client in `ports/`, no interface, no fake; tests
monkeypatch `httpx.AsyncClient` in 6 places
(`tests/realtime/test_channels_tokens.py:149,168,194,225,241`,
`tests/test_readiness.py`), plus `dispatch_task_outbox.py:22-29` builds its own `httpx`
client against the same vendor API with the same "command errors arrive inside a 200"
handling duplicated at `:31-32` vs `ports/centrifugo.py:63,89`.
(b) Bad because: every test that touches realtime must know Centrifugo's HTTP shape; the
"200 with an error body" quirk is implemented three times; and swapping transport means
editing four call sites plus the worker.
(c) Pattern: a `RealtimePort` Protocol (`publish`, `disconnect_user`, `mint_token`,
`readiness`) beside `LexiReader` in `ports/`, one `CentrifugoAdapter`, one
`InMemoryRealtime` fake for tests. Include the worker's publish so the quirk lives once.
(d) Trade-off: crosses the api/worker package boundary — the adapter would need to live in
`packages/shared-py` or be duplicated. Token minting is HMAC-local, not HTTP, so it may not
belong on the same interface.
(e) Beats the simpler fix? Yes for the *fake* (it deletes 6 monkeypatches of a vendor
class and makes realtime testable without knowing Centrifugo). The Protocol itself is
marginal at one implementation — see R2 below. Suggest: add the fake + consolidate the
"error inside 200" check; add the Protocol only if a second transport is ever plausible.

### P3. Registry/Strategy for task kinds — **recommend, small**

(a) Problem: adding a task kind requires edits in 3+ unrelated places: the `if/elif` in
`reconcile_async_tasks.py:18-49`, a work-key builder in `tasks/domain/work_keys.py`, the
producer, and the worker registration list (`apps/worker/pycil_worker/main.py:114-127`).
Nothing links them.
(b) Bad because: the `else` branch at `reconcile_async_tasks.py:43-49` exists *because this
already failed* — `question_pool` was a kind with no handler, silently unrecoverable, rows
queued forever. The logging is a workaround for a missing registry.
(c) Pattern: `TASK_KINDS: dict[str, TaskKind]` where `TaskKind` carries the arq job name
and a `dispatch -> args` mapper. `reconcile_async_tasks` becomes a lookup; a kind with no
entry fails at import, not at 3am.
(d) Trade-off: the registry must live where both api (producers) and worker (reconciler)
see it — so `packages/shared-py`, or api-side and imported by the worker (which already
imports `pycil.tasks.application.service`).
(e) Beats the simpler fix? Yes. The simpler fix is "remember to add the branch", which
demonstrably did not work. 3 kinds today, and the failure is silent.

### P4. Fix `_converge_task_snapshot` at the source — **recommend**

(a) Problem: `reconcile_pending_grades.py:93-95` re-enqueues by `response_id`, so
`grade_answer_v1` cannot settle the task; `_converge_task_snapshot`
(`grade_answer.py:59-98`) + `find_live_task` (`tasks/application/service.py:316-331`) +
`grade_answer_v1` (`:124-126`) exist to compensate.
(b) Bad because: two grading entry points with two task-settling strategies; a
work-key-based task *re-lookup* API exists solely for a caller that lost the id it had.
(c) Pattern: none needed — pass the task id. Have the reconciler resolve
`AsyncTask` by `grading_work_key(response_id)` **once**, then enqueue `grade_answer_task`
with the task id, and delete the other path.
(d) Trade-off: `grade_answer_v1` is a versioned target kept "while old jobs drain"
(`grade_answer.py:125`) — needs a deploy-window check before removal.
(e) Beats the simpler fix? It *is* the simpler fix; the current code is the complicated one.

### P5. Bound + type the task snapshot — **recommend, trivial**

`tasks/domain/schemas.py:10-20` (`AsyncTaskSnapshot`) is unused; the wire shape is a dict
literal at `tasks/application/service.py:75-88`. Make `task_snapshot` return
`AsyncTaskSnapshot(...).model_dump(by_alias=True)`, mirroring how
`shared/realtime/payloads.py:22-33` already does it for `GradingResult`. Either that or
delete the model. Leaving an unused Pydantic definition of a live wire contract is the
worst of the three options.

### P6. Declare `_graph` / checkpointer as dependencies — **recommend, trivial**

`assistant/router.py:118-122` + `:347`. Makes them visible to OpenAPI and to
`tests/contracts/test_route_auth_coverage.py`'s dependency introspection, and removes
manual invocation from three handlers.

### Rejected — considered and deliberately staying simple

**R1. Repository pattern over SQLModel.** Services query via `session.scalar`/`select`
directly (~everywhere). Adding repositories would mean ~15 new classes wrapping SQLAlchemy
in a codebase where the query *is* the domain logic — `submit_or_join`'s partial-unique-index
race handling (`tasks/application/service.py:226-241`), `claim_outbox_batch`'s
`with_for_update(skip_locked=True)` (`:436`), `_clamp_interests_to_grace`'s conditional
`UPDATE` (`:367-378`). None of that survives an ORM-agnostic interface. Reject.

**R2. Protocol/ABC for the Centrifugo port.** One implementation, and no second transport
is plausible (Centrifugo is in `docker-compose.yml` and the subscribe-proxy protocol is
baked into `realtime/application/subscriptions.py`). An interface with one impl is the smell,
not the fix. Take the fake from P2, skip the Protocol.

**R3. Merge assistant SSE into the Centrifugo/outbox path.** Superficially attractive —
two recoverable-event-stream implementations. But assistant streaming is token-by-token to
*one* connection with LangGraph interrupt semantics; the outbox is durable fan-out to
reconnecting tabs. Routing tokens through Postgres→outbox→cron→Centrifugo would add
seconds of latency to a typing indicator. Reject.

**R4. Extract an `ErrorCode` enum.** Codes are currently strings promoted from raise-site
messages (`errors.py:67-73`) and extracted by AST (`scripts/extract-error-codes.py`). An
enum looks tidier, but the generator + `Record<ApiErrorCode,…>` typecheck already gives
compile-time coverage on the *consuming* side, which is where it matters. An enum would add
an import to ~60 raise sites and a second place to edit. Reject — the existing mechanism is
verified working (CI fails on a stale generated file).

**R5. Replace the `ctx` dict service locator in the worker.** It is arq's own idiom
(`apps/worker/pycil_worker/main.py:79-95`); fighting the framework buys typing only.
Reject.

**R6. Collapse `ports/lexi_provider.py` into `ports/lexi_embedded.py`.** Tempting (§6.7,
three forwarders). But `tests/content/test_embedded_lexi_construction.py:17,29,31`
monkeypatches those exact names to test singleton behaviour, and the two-file split
separates "how to build one" from "the process's one". Low value, non-zero test churn.
Reject — or fold in only as part of P2.

**R7. Deduplicate the middleware error envelope** (`common/middleware.py:37-44`). It is a
dict literal because `BodySizeLimitMiddleware` is raw ASGI with no `Request` object, and
`_send_too_large` at `:115-124` *already* uses the real models. Only `_middleware_error`
duplicates the JSON, and it is 8 lines pinned by
`tests/test_middleware_error_contract.py`. Reject.

---

## 8. Effort / risk

| # | Proposal | Size | Regression risk | Existing coverage | Independent? |
|---|---|---|---|---|---|
| P1a | `auth/router.py:69` → `flush()`; drop `assistant/router.py:192,248` extra commits | S | Low | `tests/auth/` (~590 LOC over 6 files); `tests/assistant/test_threads_runs_and_actions.py` | Yes |
| P1b | Full UoW / remove `commit: bool` from 6 functions | L | **High** | `tests/assistant/test_deferred_cache_invalidation.py` (182) pins the deferred path; `tests/hierarchy/`, `tests/content/` | No — blocks on P1a; do not touch `tasks/application/service.py` |
| P2a | `InMemoryRealtime` fake + one "error inside 200" helper | M | Low | `tests/realtime/` (525); `apps/worker/tests/test_dispatch_task_outbox.py` (124) | Yes |
| P2b | `RealtimePort` Protocol + adapter | M | Low-Med | same | No — after P2a |
| P3 | `TASK_KINDS` registry | S-M | Low | `apps/worker/tests/test_reconcile_async_tasks.py` (166); `tests/tasks/` (339) | Yes |
| P4 | Reconciler enqueues by task id; delete `_converge_task_snapshot`, `find_live_task`, `grade_answer_v1` | M | Med (deploy window for `grade_answer_v1`) | `apps/worker/tests/test_grade_answer_job.py` (251) incl. `test_reconciled_grade_converges_the_task_snapshot:54`; `test_reconcile_pending_grades.py` (223) | Yes |
| P5 | Route `task_snapshot` through `AsyncTaskSnapshot` (or delete it) | S | Low | `tests/tasks/test_task_registry.py` (235); `apps/web/tests/unit/task-snapshot.test.ts` | Yes |
| P6 | `_graph`/checkpointer as `Depends` | S | Low | `tests/assistant/test_configuration_and_tools.py` (117); `tests/contracts/test_route_auth_coverage.py` | Yes |
| C1 | `tools.py:48,52` + `tasks/service.py:196` `RuntimeError` → typed `AppError` | S | Low | `tests/test_error_code_specificity.py` (106) — will need new cases; regenerate `error-codes.generated.ts` | Yes |
| C2 | Delete `sign_subscription_token`, `unsubscribe_channel` | S | Low | `tests/realtime/test_channels_tokens.py:62,73,173-242` would need deleting; **but** `test_subscribe_proxy.py:207-246` asserts `unsubscribe_channel` is *not* called — that test needs rewriting or the function kept | Yes |
| C3 | Drop `pycil.jobs` from `pyproject.toml:112,156` | XS | None | `lint-imports` in CI | Yes |
| C4 | Remove 8 function-local imports; un-privatize `_owned_node` | S | None | existing | Yes |
| C5 | `LIMIT` on `list_reenqueueable_tasks` (`tasks/service.py:334-351`) | XS | Low | `apps/worker/tests/test_reconcile_async_tasks.py` | Yes |
| C6 | Drop redundant `code=` on the 13 sites where message == code | S | Low | `tests/test_error_code_specificity.py`; regenerate codes | Yes |
| C7 | `error_responses()` on the 5 undocumented routers | M (mechanical) | None | `tests/test_v1_contract.py` | Yes |
| C8 | Split retention purge out of `reconcile_pending_grades` | S | Low | `apps/worker/tests/test_reconcile_pending_grades.py` (223) | Yes |
| C9 | Extract the approval-target resolution block from `stream_run` (`run_service.py:210-237`) | S | Low | `tests/assistant/test_confirmation_targets.py` (156) | Yes |

Suggested order: C3, C5, P5, P6, C1 → P1a, P3, P4 → P2a, C2, C7 → (P1b only if committing
to remove `commit: bool`).

Overall coverage is good: 3,779 LOC of API tests in the audited areas plus 1,471 worker,
with architectural rules enforced by 8 import-linter contracts and four source-reading
tests (`test_lexi_boundary`, `test_lexi_contract_parity`, `test_session_scope_allowlist`,
`test_route_auth_coverage`).

---

## Unresolved questions

1. `unsubscribe_channel` — keep as documented-not-called (with
   `test_subscribe_proxy.py:207-246` guarding it), or delete the function and keep only the
   test's rationale as a comment? The decision at `test_subscribe_proxy.py:208-221` is
   verified; only the dead function's fate is open.
2. `grade_answer_v1` (`grade_answer.py:124-126`) — is the drain window past? P4's cleanup
   depends on it.
3. `ports/centrifugo.py` mints HMAC tokens (`:30-42`) *and* makes HTTP calls (`:45-89`). One
   port with both, or split token-minting out (it has no I/O)?
4. If P2 lands, where does the adapter live so both api and worker share it —
   `packages/shared-py`, or worker imports from `pycil.ports` (it already imports
   `pycil.tasks.application.service` and `pycil.ports.lexi_embedded`)?
5. `learning/domain/` imports `lexi_ai.contracts` (`grading.py:5`, `resolver.py:8`) while the
   import-linter keeps that layer free of `fastapi`/`sqlalchemy` (`pyproject.toml:199-223`).
   Intended (shared vocabulary) or an omission in the contract?
6. `assistant/router.py:242` raises `ServiceUnavailableError` (503) for
   `assistant_message_too_long`. 413 or 422 seems right; is the 503 deliberate? It is on the
   wire today (`error-codes.generated.ts`: `"assistant_message_too_long": [503]`), so
   changing it is a frontend-visible contract change.
