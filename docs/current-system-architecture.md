# Pycil Canonical System Architecture

Pycil embeds the GitHub-pinned `lexi_ai` as a domain library. Lexi owns dictionary
content, questions, and grading in the isolated `lexi` PostgreSQL schema; Pycil
owns users, hierarchy, learning state, task orchestration, and delivery.

```
client / Next.js BFF -- bearer REST --> FastAPI API
                                         |-- Postgres (public + lexi schemas)
                                         |-- Redis / arq worker
                                         |-- Centrifugo SSE
                                         `-- embedded lexi_ai
```

The API and worker construct separate Lexi pools. Lexi's domain Alembic chain
creates the `lexi` schema before Pycil's application migrations. Runtime
processes never perform Lexi DDL and no Lexi HTTP, gRPC, WebSocket, service
credential, or service deployment exists.

## Async delivery

Pycil's `async_tasks` registry, interests, command receipts, event stream, and
transactional outbox provide durable task identity and delivery. Every
non-assistant asynchronous client state change arrives through authorized,
versioned Centrifugo SSE task snapshots. The outbox relay recovers missed
delivery; clients do not poll task or response status.

Assistant FastAPI SSE and its HITL/recovery contract are independent and
unchanged.

## Learning

Redis holds ephemeral study state. PostgreSQL holds response, attempt, and FSRS
effects. Lexi is authoritative for question content and grading. Ready question
payloads expose presentation only; answer indexes, accepted forms, and rubrics
remain inside Lexi. First-attempt claims and worker grade leases prevent
duplicate FSRS mutation.
