---
phase: 12
title: "Tests & Docs"
status: complete
priority: P1
effort: "1.5d"
dependencies: [6, 7, 9, 11]
---

# Phase 12: Tests & Docs

## Overview
Comprehensive test suite (unit + integration) across the new Python stack, plus docs sync. Verifies the pycil↔lexi-ai boundary holds and the learning loop works end-to-end.

## Requirements
- Functional: unit tests (FSRS math, hierarchy stats, auth, question router); integration tests (session flow against real Postgres + fakeredis, port faked).
- Non-functional: no fake/mocked dictionary content standing in for real behavior; real Postgres for integration; lexi calls faked at the port only.

## Architecture
Test layers: `unit` (pure logic, no I/O — FSRS, mastery, router cap, subtree resolution), `integration` (service + real Postgres via pytest-postgresql + fakeredis; network blocked; `LexiClient` faked at the port boundary — NOT the LLM). Docs updated under `docs/`.

## Related Code Files
- Create: `apps/api/tests/{unit,integration}/`, `packages/shared-py/shared/fsrs/tests/`, per-domain `tests/`
- Modify: `docs/system-architecture.md`, `docs/codebase-summary.md`, `docs/project-roadmap.md`, `docs/project-changelog.md`, `README.md`
- Reference (read-only): all phase files

## Implementation Steps
1. FSRS unit tests: pin design-doc worked examples (mastery table, success/failure updates, early-review no-op).
2. Hierarchy stats tests: subtree resolve (nested + reference), stats correctness, CEFR via fake LexiClient, L1 invalidation.
3. Auth tests: PKCE/state, token_version revocation, role re-read, **banned-user 403, JWT alg-pin rejects `alg:none`/HS-confusion, internal-secret constant-time + empty-reject fail-closed**.
4. Learning tests: queue non-empty, ratio honored, cap not exceeded, answer updates stats + review_log, first-attempt-only (holds under concurrent answers via the per-(user,sense) lock).
5. Security tests (the red-team gaps): **IDOR — user A cannot read/write user B's private node (403), public readable-not-writable by non-owner; answer-key tampering — `/answers` grades only the server-re-fetched question, a doctored client payload cannot force `correct`; grade idempotency — retrying a terminal grade job is a no-op (no second lexi.grade); Centrifugo — A's token cannot subscribe to B's `users:{B}:...` channel**.
6. Boundary tests: assert pycil DB has no dictionary tables (`words`/`senses`/`questions`); assert no `Lexicon(` outside the adapter; assert grade job writes only pycil learning tables (never lexi's DB).
7. Integration: full session flow (start → next question → answer → mastery update + verdict persist-back) against real Postgres + fakeredis + fake port.
8. Docs: update architecture (two-DB boundary, Ports&Adapters, Centrifugo, FSRS, hierarchy), roadmap, changelog; rewrite README for the Python stack; remove Go/ent references.
9. Run `ruff` + full `pytest`; ensure green.

## Success Criteria
- [x] FSRS unit tests pin all design-doc examples
- [x] Integration session flow passes against real Postgres + fakeredis
- [x] Security tests pass: IDOR, answer-key tampering, grade idempotency, Centrifugo channel scope, banned-user, JWT alg-pin
- [x] Boundary tests confirm no dictionary tables + port-only lexi access
- [x] No mocked dictionary content passing as real behavior
- [x] Docs reflect Python stack, two-DB boundary, FSRS, hierarchy, Centrifugo
- [x] `ruff` + `pytest` green (64 tests passing)

## Risk Assessment
- Over-mocking hides real failures (per prompt.md critique). Mitigation: fake only the paid/external boundary (lexi port, Centrifugo HTTP); use real Postgres.
- Docs drift from code. Mitigation: update docs in the same phase as the code stabilizes; delegate to docs-manager if needed.
