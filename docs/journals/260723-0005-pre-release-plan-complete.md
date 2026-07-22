# Pre-release async task and Lexi consolidation

The prototype now uses one Pycil async-task lifecycle, embedded Lexi execution,
transactional outbox delivery, and Centrifugo SSE-only client delivery. Lexi is
installed from GitHub at immutable commit `3bbd70e96679f8baa179424228d7f32b9342732d`.

Legacy Lexi HTTP/gRPC/service code, browser polling, WebSocket paths, and status
fallback routes were removed. Fresh PostgreSQL setup is managed by Lexi's
immutable domain Alembic baseline in the `lexi` schema; SQLite remains a local
bootstrap option.

Verification completed: API `177 passed, 1 skipped`, worker `20 passed`, shared
`13 passed`, Lexi `446 passed, 9 skipped`, frontend typecheck/build, both Docker
image builds, Compose config, and migration/config validation.

Production canary, backup/restore, and observation are deferred until a real
deployment exists; the plan is closed under the pre-release acceptance scope.
