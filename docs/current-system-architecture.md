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
delivery; the owner-scoped response read is a durable fallback for missed grading
pushes, while clients do not poll generic task status.

Assistant FastAPI SSE and its HITL/recovery contract are independent and
unchanged.

## Learning

Redis holds ephemeral study state. PostgreSQL holds response, attempt, and FSRS
effects. Lexi is authoritative for question content and grading. Ready question
payloads expose presentation only; answer indexes, accepted forms, and rubrics
remain inside Lexi. First-attempt claims and worker grade leases prevent
duplicate FSRS mutation.

### Session shape: planning, rounds, levels

A session is **planned once** at creation and then delivered a round at a time.
Planning admits a bounded set of senses; delivery walks them through per-sense
checkpoints inside variable-length rounds.

- **Planning admits senses, due-first.** `plan_session`
  (`learning/application/planning.py:147`) fills the learner's `target_words_per_session`
  budget from due candidates first, then backfills with new senses, always
  reserving a `NEW_WORD_FLOOR` of new words even under a large due backlog
  (`_slot_split`, `learning/application/planning.py:82`). Session shape is the **learner's**,
  not the deck's: `settings_for_user` (`learning/application/planning.py:58`) reads their
  `UserLearningSettings` row and falls back to `DEFAULT_TARGET_WORDS_PER_SESSION`
  / `DEFAULT_MAX_QUESTIONS_PER_ROUND` (`policy/policy.py:25-26`) when absent.

- **Requirements are per-sense checkpoints.** A sense must pass
  `REQUIRED_CHECKPOINTS` clean checkpoints (`policy/policy.py:17`) to earn its
  Good this session, with `MAX_RETRIES_PER_CHECKPOINT` retries after a wrong
  first attempt (`policy/policy.py:19`). Progress is tracked per sense, not per
  session, so the same sense recurs across rounds until satisfied.

- **Rounds bound the per-round question count; breaks are first-class.** The
  round scheduler (`learning/application/round_scheduler.py`) caps a round at
  `max_per_round` and closes it, and the API returns a `break` state naming the
  round being **entered** (`learning/router.py:431`) rather than counting client
  side. A break is a real `/next` state the client renders, not a toast.

- **Difficulty is sampled from the mastery band.** `sample_requested_level`
  draws an assessment level (1..4) from the mastery band's probability profile
  (`LEVEL_PROFILES`, `policy/policy.py:50`); level 0 is exposure. These bands
  are the single source the UI mastery ramp must mirror.

- **A served-below-requested fallback is surfaced, not hidden.** When supply
  cannot serve the requested level, the delivered question carries
  `isFallback: true` with the level actually served, so the client can say the
  difficulty was lowered rather than silently downgrading.

- **An aborted answer reopens its checkpoint.** Delivery claims are consumed on
  answer; a desync (`question_not_issued_for_session`, `question_not_available`,
  `question_not_assessable`) reopens the bound delivery
  (`session_store.reopen_bound_delivery`, `learning/router.py:533`) so the sense
  returns in a later round rather than being lost. Recovery is re-polling
  `/next`, never resubmitting the consumed claim.

The recap reads a **durable** `SessionSummary` (`learning/infra/models.py:185`), so it
survives a reload after the ephemeral Redis state is gone: a `session_not_found`
on `/next` after completion is treated as finished, not as an error.
