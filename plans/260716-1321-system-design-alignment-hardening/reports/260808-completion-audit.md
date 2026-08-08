# Completion Audit — 2026-08-08

## Outcome

The System Design Alignment and Hardening plan is implemented and its six phase
checklists are synchronized with the current Python/FSRS runtime. The only
environment-owned exception is a broker-level Centrifugo cross-user denial
rehearsal; the application subscribe proxy, static v6 configuration, and live
recovery journey are covered.

## Evidence

- API full suite: 527 passed, 1 skipped.
- Worker: 39 passed, 6 skipped.
- Shared Python: 26 passed.
- Web Vitest: 114 passed; typecheck and lint passed.
- Opt-in hierarchy benchmark: 2k = 19.61 ms; 100k = 104.35 ms; the 2k target
  is below the 50 ms representative-environment budget.
- Generated error, mastery, and grading contracts regenerated twice with no
  byte drift. Documentation path validation checked 37 citations successfully.
- Fresh-schema Compose rehearsal completed in an isolated Compose project with
  temporary ports/configuration; its containers and volumes were removed after
  the smoke run. Migration compatibility is also covered by the API migration
  tests and CI's dedicated Lexi/Pycil head job.
- The quick baseline run passes API, shared, Lexi, import-boundary, cycle, FK,
  and documentation tiers. The FK detector checked 30 foreign keys against the
  recorded baseline; the worker floor was reconciled from the pre-cleanup 50 to
  the current 45-test canonical suite with the reason recorded in
  `scripts/verify-baseline.sh`.

## Implementation deltas closed

- Added owner-scoped durable `GET /v1/responses/{response_id}` recovery and
  pending-response omission of unresolved verdict fields.
- Made `gradeStatus` a closed wire union and aligned the server-owned mastery
  floor to 80; generated frontend contracts now derive the floor, grading keys,
  and realtime namespace from Python/shared sources.
- Corrected the generated error-code taxonomy for
  `word_generation_query_invalid`; the historical API script now delegates to
  the repository-level generator.
- Updated architecture, integration, roadmap, and decision docs to describe
  embedded Lexi, SSE plus durable response recovery, and current route paths.
- Aligned host backup/restore wrappers and the disaster-recovery runbook with the
  single shared PostgreSQL dump covering `public` and isolated `lexi` schemas;
  shell syntax and Compose validation pass.

## Unresolved questions

The broker-level Centrifugo denial rehearsal remains an environment-owned
deployment check; it is not an unanswered code contract. The local stack was
left running and untouched.
