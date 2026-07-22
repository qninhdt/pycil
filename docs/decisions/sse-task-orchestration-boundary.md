# ADR: SSE task orchestration and embedded Lexi boundary

**Status:** accepted — Phase 2 foundation deployed; migration target remains in progress

**Date:** 2026-07-22

## Context

The deployed system has owner-scoped `word_generations`, a separate Lexi HTTP
service, best-effort Centrifugo publications, and browser polling. That model
cannot safely share provider work, guarantee delivery after a publish failure,
or remove status polling. This decision is the contract for the staged
migration; it does not claim that the target is already deployed.

Phase 2 deploys the generic registry/outbox schema and relay only. It does not
move legacy producers, browser delivery, or Lexi execution to the new path;
those remain later-phase cutovers.

## Decision

Pycil will own one durable async-task lifecycle. `lexi_ai` will become an
embedded, transport-free domain library with tables in the PostgreSQL `lexi`
schema. Pycil application tables remain in `public`.

### Identity and privacy

| Term | Meaning | Visibility |
|---|---|---|
| `taskId` | Opaque UUID identifying one durable execution lifecycle. | Authorized interests only. |
| `workKey` | Server-derived identity of shareable work. | Never exposed. |
| interest | Revocable, expiring authorization for a user to observe a task result. | Owner/authorized reader. |
| `deliveryId` | Opaque UUID for a private session projection of a shared question task. | Session owner only. |
| `eventId` | Opaque UUID for a persisted, at-least-once task event. | Subscribers deduplicate it. |
| `version` | Monotonic per-resource snapshot version. | Subscribers ignore lower versions. |

Shared work keys exclude a user and session:

- Word: `word:{match_key}:{dataset_fingerprint}`
- Question pool: `question-pool:{sense_id}:{format}:{generator_revision}:{pool_generation}`
- Translation: `translation:{source_identity}:{content_hmac}:{locale}:{revision}`
- TTS: `tts:{source_identity}:{content_hmac}:{voice}:{format}:{revision}`
- Grading: `grading:{response_id}`

`content_hmac` is an HMAC derived with a server secret. Raw translation text,
plain hashes, and work keys never occur in channel names, logs, or browser
responses. A session selects a persisted question variant through its private
delivery; `sessionId` is correlation data, never shared question identity.
Assistant SSE/HITL remains outside this decision.

### Artifact and execution lifecycle

An artifact's canonical identity is independent from its generator revision.
Normal cache hits return the stable artifact without silently rewriting it.
Regeneration is an explicit authorized mutation and records a new execution
revision.

Retries retain one `taskId` and advance its fenced execution attempt. A
terminal failed or expired task permits a new task for the same `workKey`.
Successful artifacts outlive task-event retention and may seed a terminal
snapshot without another provider call. Effects use unique keys and fenced
leases, so a replay converges rather than duplicates a provider/domain effect.

### Commands and delivery

Every mutating async command accepts a client-generated `Idempotency-Key`
(`commandId` in JSON when headers are unavailable). Pycil persists a command
receipt before responding. A retry with the same principal and command ID
returns the original task and delivery IDs, never a second submission.

Each task state transition writes its event and an outbox row in the same
transaction. The outbox relay publishes full snapshots at least once;
subscribers deduplicate `(eventId, version)`. Centrifugo SSE subscription
authorization loads live interests or private delivery/response access and
returns a durable current snapshot. Browser task/response/session polling and
WebSocket delivery are migration targets for removal; backend outbox sweeping
remains mandatory crash recovery.

### Retention and migration safety

Task snapshots retain DTOs only. Interests are revocable and expire; published
history contains no raw private source text. Retention/deletion windows will
be specified with the Phase 2 schema migration.

All Lexi word, sense, question, and asset primary keys are preserved during
the schema copy. Before embedded writes: rollback may restore the old stack.
After the first embedded write: the old service is read-only, and remediation
is forward-fix or a verified database restore—never a return to dual writers.

## Non-goals

- No rewrite of assistant SSE/HITL.
- No best-effort-only terminal delivery.
- No user/session-scoped identity for globally shareable content.
- No raw-text task identities or browser status-polling fallback.

## Baseline procedure

Run [`scripts/verify-sse-task-migration-baseline.sh`](../../scripts/verify-sse-task-migration-baseline.sh)
against each source database before a rehearsal. Archive its JSON output with
the backup manifest. The command fails if the Pycil migration head differs
from `0013_word_generation_leases`; Lexi verification is intentionally an
explicit second invocation so this repository never needs Lexi credentials.
