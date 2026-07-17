---
date: 2026-07-18
topic: assistant-agent-mvp
status: implementation-complete-pending-external-smoke
---

# Assistant Agent MVP implementation journal

## Context

Implemented `plans/260716-1729-assistant-agent-system/plan.md`: an owner-scoped
assistant for hierarchy/content tasks. Existing generic SSE remained removed;
this bounded assistant is the explicit exception.

## What happened

- Added `/assistant` threads, idempotent runs, sanitized persisted SSE events,
  recovery via `Last-Event-ID`, heartbeats, and Redis run/rate/spend limits.
- Added LangGraph Postgres checkpoint storage, owner/action persistence,
  `0008_assistant_agent_foundation`, expiry and retention worker jobs.
- Exposed a bounded tool set for hierarchy, deck content, dictionary search,
  generation requests, and folder stats. Sensitive move/publish/delete/remove
  operations pause for a durable approval.
- Added focused assistant tests plus API boundary and worker registration
  coverage. Documentation, compose, and sample environment now describe the
  feature and its lifecycle.

## Decisions

- Replaced OpenRouter-specific integration with `ChatOpenAI` against a dedicated
  **OpenAI-compatible** `ASSISTANT_BASE_URL` and `ASSISTANT_API_KEY`. Lexi and
  assistant credentials remain separate.
- Bound approval to canonical arguments, a LangGraph checkpoint version, and
  resource generations; confirmation revalidates all three before resuming.
- Made sensitive domain writes and `AssistantAction.result` part of one DB
  transaction. The action ID is supplied to resumed tool calls, so a committed
  result is replayed instead of attempting the write again after an SSE/process
  interruption.
- Delete checkpoint state before deleting thread rows, retaining a retryable
  DB record if checkpoint cleanup fails. Detached minimized audit records retain
  only decision metadata for 90 days.

## Verification

- Focused assistant API suite: `12 passed` (recorded in
  `plans/reports/260718-0100-assistant-phase-06-tests.md`).
- API regression debugging fixed migration enum creation and the boundary-table
  inventory; worker registration suite recorded `3 passed`
  (`plans/reports/260718-assistant-api-worker-test-report.md`).
- Static checks/formatting and final full-suite validation remain part of the
  release handoff after the final atomic-action refinements.

## Reflection

The difficult invariant was not token streaming but making an approved mutation
safe across disconnects. The durable action result must be the idempotency key;
an SSE completion signal is only a delivery mechanism.

## Next

- Configure a real OpenAI-compatible endpoint, key, and model in a non-local
  environment; run the opt-in assistant smoke test (normal tool run, approval,
  reconnect/replay, and retention cleanup).
- Complete final full-suite/lint gate before release or commit.

## Unresolved questions

- Which production OpenAI-compatible provider/model, timeout, and monthly spend
  ceiling should be used for the first rollout?
