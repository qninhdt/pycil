# references

Cited as `[R##]` throughout. Tier per R5 in [README.md](./README.md).

## Tier 1 — specification, RFC, peer-reviewed

| # | Source |
|---|---|
| R01 | [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749) — authorization code grant |
| R02 | [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — S256 code challenge |
| R03 | [RFC 8252 — OAuth for Native Apps](https://www.rfc-editor.org/rfc/rfc8252) — system browser, never an embedded WebView; claimed HTTPS redirect preferred |
| R04 | [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — rotating or sender-constrained refresh tokens for public clients |
| R05 | [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519) |
| R06 | [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) — algorithm allow-list; never trust the token's own `alg` |
| R07 | [RFC 9068 — JWT Profile for Access Tokens](https://www.rfc-editor.org/rfc/rfc9068) — `typ=at+jwt`, required claims |
| R08 | [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457) — `application/problem+json`; obsoletes RFC 7807 |
| R09 | [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) |
| R10 | Settles & Meeder (2016), *A Trainable Spaced Repetition Model for Language Learning*, ACL — half-life regression; `half_life = 2^(θ·x)` with θ fitted on ~12M sessions |

## Tier 2 — official documentation

| # | Source |
|---|---|
| R11 | [FSRS algorithm walkthrough](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/Spaced-Repetition-Algorithm:-A-Three%E2%80%90Day-Journey-from-Novice-to-Expert) — FSRS-4.5 power-law forgetting, stability/difficulty update, published default weights |
| R12 | [FSRS optimizer](https://github.com/open-spaced-repetition/fsrs-optimizer) — refitting weights from a review log |
| R13 | [Google — OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) — `sub` is the stable identifier; email can change |
| R14 | [Centrifugo — transports overview](https://centrifugal.dev/docs/transports/overview) — WebSocket is the primary bidirectional transport |
| R15 | [Centrifugo — SSE fallback](https://centrifugal.dev/docs/transports/sse) — bidirectional SSE plus `/emulation`; `uni_sse` cannot subscribe after connect |
| R16 | [Centrifugo — channel permissions](https://centrifugal.dev/docs/server/channel_permissions) — subscribe is denied by default; `#` user-limited channel form |
| R17 | [Centrifugo — subscribe proxy](https://centrifugal.dev/docs/server/proxy#subscribe-proxy) — backend consulted on every subscribe |
| R18 | [Centrifugo — history and recovery](https://centrifugal.dev/docs/server/history_and_recovery) — history "is a cache, not your source of truth"; "can be empty, truncated, or lost at any moment"; **always keep a backend fallback**; offset + epoch semantics |
| R19 | [Centrifugo — Redis engine](https://centrifugal.dev/docs/server/engines) — cross-node fan-out, history, presence; no sticky sessions required |
| R20 | [Centrifugo — server-side subscriptions](https://centrifugal.dev/docs/server/server_subs) — automatic personal subscription |
| R21 | [Taskiq — CLI](https://taskiq-python.github.io/guide/cli.html) — `--ack-type when_received\|when_executed\|when_saved`, `--max-async-tasks`, `--wait-tasks-timeout`, `--hardkill-count` |
| R22 | [Taskiq — middlewares](https://taskiq-python.github.io/available-components/middlewares.html) — `SimpleRetryMiddleware`; retry is opt-in per task via `retry_on_error` |
| R23 | [Taskiq — scheduling](https://taskiq-python.github.io/guide/scheduling-tasks.html) — `TaskiqScheduler` + `LabelScheduleSource`, run as a separate process |
| R24 | [taskiq-redis — brokers](https://github.com/taskiq-python/taskiq-redis) — three brokers; only `RedisStreamBroker` (Redis Streams + consumer groups) supports acknowledgement and durability |
| R25 | [arq — maintenance-only mode](https://github.com/python-arq/arq/issues/510) — critical security fixes only, no new work |
| R26 | [LangGraph — interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — `interrupt()` pauses inside a node; `Command(resume=…)` continues |
| R27 | [LangGraph — persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — checkpointer writes at node boundaries; resume, not rerun |
| R28 | [LangGraph — streaming](https://docs.langchain.com/oss/python/langgraph/streaming) — event stream shapes |
| R29 | [LangGraph Platform — scalability and resilience](https://docs.langchain.com/langgraph-platform/scalability-and-resilience) — stateless instances, heartbeat window plus sweeper requeue, `N_JOBS_PER_WORKER` |
| R30 | [Anthropic — prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — prefix order `tools → system → messages`, invalidation table, `cache_read_input_tokens` |
| R31 | [PostgreSQL — `SELECT … FOR UPDATE SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) — the claim primitive for a queue in a table |
| R32 | [PostgreSQL — `NOTIFY`](https://www.postgresql.org/docs/current/sql-notify.html) — transactional: delivered only on commit |
| R33 | [Testcontainers](https://testcontainers.com/) — a test brings up its own dependency |
| R34 | [Caddy — reverse proxy streaming](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming) — `flush_interval -1` for SSE |

## Tier 3 — engineering guidance from organisations operating at scale

| # | Source |
|---|---|
| R35 | [AWS — transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) — commit state and message atomically; at-least-once, so consumers must be idempotent |
| R36 | [Microsoft — Transactional Outbox](https://learn.microsoft.com/en-us/azure/architecture/best-practices/transactional-outbox-cosmos) — relay claims, publishes, marks |
| R37 | [OWASP — Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) — LLM01 prompt injection; treat every external string as data, not instruction |
| R38 | [Quizlet — spaced repetition and Memory Score](https://quizlet.com/blog/spaced-repetition-for-all-cognitive-science-meets-big-data-in-a-procrastinating-world) — a trained model over their own review data; the parameters are not published |
| R39 | [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) — **implement-time reference.** Consult when writing the agent system prompt: shape, length, how tools and boundaries are described. Do not hand-write a short prompt from scratch |

## Labelled `judgment`

Decisions with no tier 1–3 source carry `judgment` in
[decisions.md](./decisions.md) and state their reasoning inline. Every
`uncalibrated` value carries the measurement that would settle it.
