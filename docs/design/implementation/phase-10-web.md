---
phase: 10
title: "Web"
status: pending
priority: P1
effort: "4-5d"
dependencies: [3, 4, 5, 6, 7, 8, 9]
---

# Phase 10: Web

## Outcome

Replace the BFF and handwritten contracts with a generated direct API client,
durable-job polling, and an assistant panel that consumes direct SSE and rebuilds
approval state after reload.

## Requirements

- API cookies remain unreachable from JavaScript; unsafe calls carry CSRF.
- Request/response/error types and endpoint functions come from OpenAPI.
- One handwritten transport wrapper owns credentials, refresh serialization,
  idempotency, request ids, and Problem Details parsing.
- Study state has no scheduling logic or pending-grade state.
- Jobs poll canonical owner-authorized snapshots with bounded backoff.
- Assistant create/resume parse SSE across arbitrary chunks and reconcile dropped
  streams through Run and Thread reads.
- Approval popup survives reload and supports approve, edit, reject, respond.
- Strength and depth render separately; stage name derives only from depth.

## Implementation

1. Delete web session custody, proxy routes, server-action data access, and DTO mirrors.
2. Generate the API client and error enum from the checked OpenAPI document.
3. Build the transport wrapper and cross-tab refresh coordination.
4. Shrink study state and implement synchronous free-text error/retry behavior.
5. Implement reusable job polling and assistant SSE parsing/reconciliation.
6. Build the four-decision approval popup from canonical checkpoint state.
7. Replace broad browser specs with the one golden journey plus focused pure tests.

## Success criteria

- [ ] No application token is readable by client JavaScript.
- [ ] Generated client matches the current OpenAPI contract.
- [ ] Five tabs produce one refresh rotation.
- [ ] A delivered item submits once; free-text has no pending state.
- [ ] A job completes in the UI through polling with no push service.
- [ ] SSE chunk boundaries do not corrupt frames.
- [ ] Dropped stream and reload recover terminal or approval state.
- [ ] All four approval decisions resume correctly.
- [ ] Stage name follows depth and study remains keyboard-operable.
