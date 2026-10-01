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
| R21 | [Taskiq — CLI](https://taskiq-python.github.io/guide/cli.html) — `--ack-type when_received\|when_executed\|when_saved`, `--max-async-tasks`, `--wait-tasks-timeout`, `--hardkill-count` |
| R22 | [Taskiq — middlewares](https://taskiq-python.github.io/available-components/middlewares.html) — `SimpleRetryMiddleware`; retry is opt-in per task via `retry_on_error` |
| R23 | [Taskiq — scheduling](https://taskiq-python.github.io/guide/scheduling-tasks.html) — `TaskiqScheduler` + `LabelScheduleSource`, run as a separate process |
| R24 | [taskiq-redis — brokers](https://github.com/taskiq-python/taskiq-redis) — three brokers; only `RedisStreamBroker` (Redis Streams + consumer groups) supports acknowledgement and durability |
| R25 | [arq — maintenance-only mode](https://github.com/python-arq/arq/issues/510) — critical security fixes only, no new work |
| R26 | [LangGraph — interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — `interrupt()` pauses inside a node; `Command(resume=…)` continues; the middleware's four decisions are `approve · edit · reject · respond` |
| R27 | [LangGraph — persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — checkpointer writes at node boundaries; resume, not rerun. `AsyncPostgresSaver.setup()` owns its ten migrations |
| R28 | [LangGraph — streaming](https://docs.langchain.com/oss/python/langgraph/streaming) — event stream shapes |
| R30 | [Anthropic — prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — prefix order `tools → system → messages`, invalidation table, `cache_read_input_tokens` |
| R31 | [PostgreSQL — `SELECT … FOR UPDATE SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) — the claim primitive for a queue in a table |
| R32 | [PostgreSQL — `NOTIFY`](https://www.postgresql.org/docs/current/sql-notify.html) — transactional: delivered only on commit |
| R33 | [Testcontainers](https://testcontainers.com/) — a test brings up its own dependency |
| R34 | [Caddy — reverse proxy streaming](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming) — `flush_interval -1` for SSE |
| R40 | [Agent Server — runtime architecture](https://docs.langchain.com/langsmith/langgraph-server) — three runtime modes; **single host** is the self-hosted default and "the API server manages the task queue directly with no separate queue workers"; Postgres is the system of record, Redis carries "wake signals, cancellation, and streaming pub/sub" and "stores only ephemeral data" |
| R41 | [Agent Server — self-host standalone](https://docs.langchain.com/langsmith/deploy-standalone-server) — Postgres "manage[s] the state of the background task queue with 'exactly once' semantics"; Redis is "a pub-sub broker to enable streaming real time output from background runs". No dedicated message broker |
| R42 | [Agent Server — OpenAPI document](https://docs.langchain.com/langsmith/agent-server-openapi.json) — 49 paths. `Run` is 8 fields with no lease, fence, or attempt column; `RunStatus`, `ThreadStatus`, `MultitaskStrategy`, `Durability` enums; `stream_resumable` defaults `false`; `cancel_on_disconnect`; `POST .../cancel?action=interrupt\|rollback`; `GET .../runs/{id}/stream` with `Last-Event-ID`; interrupts live on `ThreadState`, not on the run |
| R43 | [Splitting API and queue workers](https://forum.langchain.com/t/free-self-hosted-langgraph-agent-server-how-to-separate-api-and-queue-workers-using-docker/3409) — one image serves API **and** executes runs by default; splitting requires `N_JOBS_PER_WORKER=0` "so it stops claiming runs" plus a `langgraph_api.queue_entrypoint` container |
| R44 | [Agent Server — background runs](https://docs.langchain.com/langsmith/background-run) — poll `GET /threads/{tid}/runs/{rid}` and read `status`; `/join` blocks until done |
| R45 | [Agent Server — environment variables](https://docs.langchain.com/langgraph-platform/env-var) — `N_JOBS_PER_WORKER` 10, `BG_JOB_MAX_RETRIES` 3 (requeue "resumes from the last checkpointed step"), `BG_JOB_SHUTDOWN_GRACE_PERIOD_SECS` 180, `BG_JOB_TIMEOUT_SECS` 86400, `RESUMABLE_STREAM_TTL_SECONDS` 120. **No variable containing HEARTBEAT or SWEEP exists** |

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
