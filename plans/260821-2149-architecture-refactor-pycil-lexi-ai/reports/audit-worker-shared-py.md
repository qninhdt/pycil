# Audit Report — apps/worker + packages/shared-py

Auditor: Explore agent, 2026-08-21. Worker read in full (23 files / 2.4K LOC); shared-py read in full.

## Verdict

Worker is a disciplined thin shell correctly sharing code via declared `pycil-api` dependency + zero-dep shared-py. Real debt: stringly-typed api↔worker job contract scattered across 7+ files, duplicated Centrifugo/channel/heartbeat literals, 4× copy-pasted submit-and-enqueue choreography.

## Module Map

Worker jobs (`apps/worker/pycil_worker/jobs/`): generate_word.py (fenced claim, quota refund on won transitions), generate_question.py (best-effort warm-up wrapped in durable task), grade_answer.py (`grade_answer_v1` by response id + durable `grade_answer_task`; `GradingResult` consolidation :25-58 collapsed three hand-written copies), dispatch_task_outbox.py (ACK-aware at-least-once relay, dead-letter after budget), reconcile_pending_grades.py (24h lease-aware purge + 48h ceiling + requeue), reconcile_async_tasks.py (re-enqueue lost tasks by kind/dispatch dict), reconcile_assistant_retention.py (thread purge + raw-psycopg checkpoint deletes), reconcile_expired_assistant_actions.py (pure forwarder), heartbeat.py (`SETEX worker:heartbeat 90`).

shared-py: `fsrs/` pure FSRS-4.5 math zero-dep; `realtime/channels.py` `async_task(task_id)` → `"async:{id}"`; `realtime/payloads.py` `GradingResult` dataclass camelCase to_dict.

## Current Patterns

Job handlers = plain async functions `(ctx, ...args)` registered via `WorkerSettings.functions` (main.py:116-128). Durability layered: (1) durable AsyncTask table with fenced leases (`claim_task` service.py:275-313) + fence-checked `transition_task` (:381-415), attempt cap 4 w/ backoff; (2) transactional outbox + pg_notify + ACK-aware relay; (3) response-row grading lease inside apply_verdict. Idempotency claim-first. Lost-enqueue recovery: producers wrap enqueue in try/except pass relying on reconciler cron.

## Keep List

- shared-py FSRS (both services consume properly; no third copy anywhere).
- GradingResult consolidation — the model for consolidation work.
- worker→pycil-api whole-package dep (documented single-pin policy).
- Thin forwarder jobs; fenced-lease discipline; registration tests pinning handler sets.
- import-linter contracts both services.

## Smells → Refactor Targets

| # | Finding | Evidence |
|---|---|--- auditor mapping |
| W1 | Job-name/task-kind/dispatch contract stringly-typed across 7+ files | literals at content/router.py:114, tools.py:244, answering.py:394, session_flow.py:271; reconciler re-spells names+arg order reconcile_async_tasks.py:21-40; kinds "word"/"grading"/"question_supply" written by producers and switched by worker |
| W2 | Centrifugo HTTP logic ×2; worker copy violates api's one-client rule | api ports/centrifugo.py docstring condemns per-call clients; worker dispatch_task_outbox.py:24 fresh httpx.AsyncClient per invocation |
| W4a | Dead `owner_uid` param in grade_answer_v1 | grade_answer.py:97-128 never uses it; reconcile_pending_grades.py:95 must keep passing positionally |
| W4b | Bare `prepare_questions` registered but never produced | main.py:118; only prepare_questions_task is enqueued |
| W4c | Heartbeat key + channel prefix literals duplicated | heartbeat.py:5 vs api main.py:39; channels.py vs subscriptions.py:13 `_CHANNEL_PREFIX="async:"` |
| W3 | Submit-and-dispatch choreography ×4 | same as api audit #4 |

## Refactor Plan Mapping

W1+W4 → Phase 02 (contract registry in shared-py)
W3 → Phase 03
W2 → Phase 08
