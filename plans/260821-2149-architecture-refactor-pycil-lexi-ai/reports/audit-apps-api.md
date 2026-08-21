# Audit Report — apps/api (FastAPI)

Auditor: Explore agent, 2026-08-21. Scope: `apps/api/src/pycil/` (110 files / ~11.9K LOC src; rest is tests).

## Verdict

Genuine, import-linter-enforced layered architecture (`router → application → infra`, plus leaf packages `ports`/`policy`/`common`). Learning/hierarchy/tasks/common subsystems are exemplary. Degradation is concentrated at three boundaries: assistant router, word-generation dispatch duplication, and divergent ownership gates.

## Module Map (LOC)

| Package | LOC | Notes |
|---|---|---|
| learning | 3,879 | router 303 + application 9 modules + domain + infra (`session_store.py` 706 Redis state machine) |
| assistant | 1,843 | router 362 + application (run_service 340, tools 307, hitl, persistence, graph, facades) + infra |
| hierarchy | 1,780 | router 306 + application (service 224, reads 215, stats 299, subtree 191, cache 164, access 80) |
| auth | 1,019 | flat: router 163, deps 76, tokens, oauth, refresh_sessions 169 |
| tasks | 741 | application/service.py 489: registry+outbox+leases |
| content | 668 | router 279 + application service 137 + generation_quota 83 |
| common | 432 | errors.py envelope+handlers, middleware, retry |
| ports | 375 | lexi.py Protocols, lexi_embedded, lexi_provider, centrifugo |
| policy | 254 | pure constants/bands/sampler |
| account_lifecycle | 212 | raw-SQL bulk ops (deliberate) |
| realtime | 165 | token minting + subscribe proxy |
| db | 76 | engine/session factory, redis/arq globals |

## Layering Reality

Router (auth+wire mapping) → application free-functions taking explicit `AsyncSession`/`Redis`. No repository pattern anywhere; "infra" = ORM models + function-store modules. Routers never build SQL except assistant/auth.

Traced paths:
- Learning question flow: textbook. router:118 → session_flow.start():97 → planning + session_store.create + task_service.submit_or_join + arq enqueue. `/answers` → answering.submit:119 with consume-once bind, compensation reopen.
- Folder CRUD: routes do access check then one application call; read routes compose 2–3 calls inline.
- Word generation dispatch: whole use case runs in route `content/router.py:75-120`; identical flow reimplemented in `assistant/application/tools.py:~210-249`.

## DI Reality

Three coexisting styles: FastAPI Depends (sessions/Lexi/current_user — consistent), module-global lazy singletons called imperatively (`db/redis.py get_redis()/get_arq_pool()` at 17 sites), `app.state` for assistant graph/checkpointer. Global `settings` singleton.

## Keep List (do not pattern-ify)

- `common/errors.py` + handlers — best subsystem.
- `policy/` pure constants with import-time assertions.
- `ports/lexi.py` Protocol port; import-linter forbids domain→lexi_ai.
- `tasks/application/service.py` fenced leases/outbox (heavily reasoned).
- hierarchy application split + its AST router-hygiene test.
- Learning one-concern-per-module layout + dataclass outcomes.
- Free-function services with explicit session args — no repositories, no DI container.
- `get_redis()` imperative global (patchable seam works).
- Raw-SQL bulk ops in account_lifecycle.
- `commit:` flags until a third deferred-commit caller appears.

## Patchwork Smells → Refactor Targets

1. **Routers doing business logic** — worst: `assistant/router.py` (362 lines: raw selects :177, cascade delete :339-362, run lifecycle :234-275, 5 in-route commits, opens `async_session_factory()` inline at :108/:317 while importing `get_session` on same line). Also `content/router.py:75-120` (whole dispatch use case in route), `auth/router.py:69-90` (user upsert choreography in route).
2. **Duplicated word-generation dispatch** — `content/router.py:82-118` vs `assistant/application/tools.py:~200-250`.
3. **Three ownership gates** — `require_node_access` (`hierarchy/application/access.py:18`, canonical) vs `_owned_node` (`assistant/application/hierarchy_facade.py:17-21`) vs `_owned_deck` (`assistant/application/content_facade.py:16`). Facade copies bypass inherited-visibility/ancestry rules.
4. **Submit-and-dispatch choreography ×4** — reserve quota → submit_or_join → release on failure/not-created → best-effort enqueue (`except Exception: pass`) at `content/router.py:83-117`, `tools.py:215-248`, `answering.py:331-400`, `session_flow.py:242-277`. Already drifting in error-handling shape.
5. **Architecture contract test covers only hierarchy** — `tests/hierarchy/test_router_is_routes_only.py`; content and assistant routers fail every clause today.
6. **Pagination ×3 schemes** — id-keyset `reads.owned_children_page` (`reads.py:187-215`) vs created_at+id cursor `hierarchy_facade.list_nodes` (`hierarchy_facade.py:44-68`) vs bounded offset slicing `folder_items` (`hierarchy/router.py:211-217`, allowed to stay).
7. **Error taxonomy outliers** — `ServiceUnavailableError` (503) for oversized user message (`assistant/router.py:241-244`, should be 4xx); double-specified code `TooManyRequestsError("word_generation_quota_exceeded", code=...)` (`content/router.py:85-89`).
8. **God files** — session_store.py 706, session_flow.py 500, tasks/service.py 489, learning/application/service.py 454, answering.py 406, assistant/router.py 362.
9. Minor: stale `pycil.jobs` in import-linter forbidden lists (`pyproject.toml:112`); acknowledged N+1 in search_words (`content/router.py:137-140`); SQLAlchemyError catch around Lexi-port call (:150).

## Assistant/Auth Boundary Notes

Assistant internally layered but router is a third application layer beside the real ones. Out-of-request context justifies self-managed sessions in tools/run_service (documented `ports/lexi_provider.py:15-25`) — does NOT extend to the router. Auth: upsert choreography in callback route; raw RefreshSession query in logout; dev_identity must stay env-gated.

## Refactor Plan Mapping

| Audit finding | Phase |
|---|---|
| #2+#4 dispatch duplication/choreography | 03 |
| #3 ownership gates | 04 |
| #1 assistant router + #7 error outliers | 05 |
| #5 contract test parametrization | 06 |
| #6 pagination unification | 07 |
| God-file splits beyond approved | tech debt (not scheduled) |
