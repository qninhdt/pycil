---
title: "Current Test Baseline"
status: complete
created: 2026-07-16
---

# Phase 1 Test Baseline

## Environment

- `TEST_DB_URL` unset: API tests provisioned `postgres:16-alpine` through
  Testcontainers with the asyncpg driver.
- Redis remained a fakeredis boundary fake.
- CI continues to inject `TEST_DB_URL`, bypassing Testcontainers.

## Results — 2026-07-16

- `packages/shared-py`: 13 passed in 0.01s.
- API contract-gap suite: 19 expected strict xfails; 0 passed, failed, or errored
  in 5.67s.
- Full API suite: 64 passed, 19 expected strict xfails; 0 failed or errored in
  18.76s (83 collected).
- Worker: no suite yet; Phase 6 owns hermetic worker fixtures and coverage.
- Migration smoke: not run. The only discovered command is the Docker Compose
  one-shot `alembic upgrade head`, which mutates the configured database and is
  outside this read-only baseline gate.

## Warnings

- 19 JWT insecure-HMAC-key warnings from test secrets.
- 3 Pydantic unsupported-field-attribute warnings in the contract suite.

## Recommendation

Keep the Testcontainers fallback and CI `TEST_DB_URL` override. Resolve warning
noise and add worker/migration coverage in their planned phases; do not treat the
strict xfails as passing behavior until their markers are removed with the
corresponding implementation.

## Unresolved Questions

- None.
