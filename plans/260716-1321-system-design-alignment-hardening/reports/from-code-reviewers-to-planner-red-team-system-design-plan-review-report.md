---
title: "Red-Team System Design Plan Review"
status: complete
created: 2026-07-16
---

# Red-Team System Design Plan Review

## Summary

Two hostile reviewers plus controller scope review produced 18 evidence-backed findings. Three duplicates were merged. Fifteen were provisionally accepted into the draft because interactive approval was unavailable; user validation remains required before implementation.

## Accepted Findings

| # | Severity | Finding | Applied |
|---|---|---|---|
| 1 | Critical | Same Alembic revision edited across phases | Immutable `0002`, `0003`, `0004` |
| 2 | Critical | DB commit can lose Redis enqueue | Pending row as outbox + reconciler |
| 3 | Critical | Terminal idempotency does not stop duplicate LLM calls | Lease, fencing, provider idempotency caveat |
| 4 | Critical | Redis-only generation cannot guarantee revocation | PostgreSQL structural versions |
| 5 | Critical | Concurrent moves can create a cycle | Stable advisory locks + recheck |
| 6 | High | Response uniqueness conflicts with repeated drills | Separate session-sense claim table |
| 7 | High | Destructive next cursor loses items on retry | Current-issue lease/state machine |
| 8 | High | API/worker rollout lacks queue/version protocol | Version, pause/drain, worker-first rollout |
| 9 | High | History lacks pre-window baseline/index | Baseline query + composite index |
| 10 | High | Centrifugo owner scope is not enforced | Subscribe ACL + live denial test |
| 11 | High | Migration omits cross-owner parent edges | Preflight + defensive ownership traversal |
| 12 | High | Raw answers lack bounds/retention | Limits, quota, transient retention, encryption |
| 13 | Medium | Response lifecycle contradictory | Response created only by answer submission |
| 14 | Medium | Invalid reference remediation ambiguous | Preserve row; dynamic unavailable resolution |
| 15 | Medium | History/generation endpoints unbounded | Window/page/job/rate limits |

## Whole-Plan Consistency Sweep

- Files reread: `plan.md` and six phase files.
- Decision deltas checked: 15.
- Reconciled stale references: 12.
- Unresolved contradictions: 0.

## Unresolved Questions

- User must confirm the six scope defaults in `plan.md` before implementation.
