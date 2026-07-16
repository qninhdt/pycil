---
title: "Phase 1 — System Design Alignment and Hardening"
date: "2026-07-16"
plan: "260716-1321-system-design-alignment-hardening"
phase: 1
status: complete
---

# Phase 1 — System Design Alignment and Hardening

## Context

Phase 1 froze the current Python/FSRS/sense/two-database contracts before
runtime hardening. Its purpose was a reproducible regression baseline, not
feature delivery.

## What happened

- API tests now provision disposable PostgreSQL through Testcontainers when
  `TEST_DB_URL` is absent; CI still supplies `TEST_DB_URL` unchanged.
- Added 19 strict expected-failure contract tests for verified hierarchy,
  session, grading, and statistics gaps owned by later phases.
- Updated FSRS and hierarchy design notes, plus architecture, roadmap, and
  codebase documentation, to reflect the canonical current stack.
- Baseline: shared package 13 passed; API 64 passed and 19 xfailed; no failures
  or errors.

## Reflection

The phase turned ambiguity into executable, visible debt. Strict xfails keep
known defects from being mistaken for accepted behavior while avoiding premature
runtime fixes. The Testcontainers fallback removes a local fixed-database
prerequisite without changing CI's configured database path.

## Decisions

- Preserve CI `TEST_DB_URL` as the preferred explicit override; use
  Testcontainers only as the local fallback.
- Treat the 19 strict xfails as future implementation gates, not passing
  behavior or waived defects.
- Keep runtime feature fixes out of Phase 1; only test infrastructure,
  contracts, baseline evidence, and documentation changed.

## Next

Proceed with Phase 2 hierarchy and cache integrity, then remove contract xfails
only in their owning hardening phases. Migration smoke remains deferred because
the available command mutates the configured database; JWT/Pydantic warning
noise is non-blocking.
