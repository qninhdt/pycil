---
title: "System Design Alignment and Hardening"
date: "2026-08-08 16:50"
plan: "260716-1321-system-design-alignment-hardening"
status: "complete"
---

# System Design Alignment and Hardening

## Context

This was the final hardening pass for the FSRS / hierarchy alignment plan. The goal was not another rewrite; it was to close the drift between the Python runtime, the generated web contracts, and the documented behavior without breaking the public/isolated-Lexi schema boundary or the owner-scoped realtime model.

## What Happened

We added an owner-scoped recovery endpoint, `GET /v1/responses/{response_id}`, so the authenticated owner can re-read pending answer state. Pending rows now omit unresolved verdict fields instead of pretending they are settled. We also locked `gradeStatus` to the closed union `pending | graded | expired`.

On the mastery side, the server-owned floor is now explicitly `80`, separate from the visual `Fluent` band at `81`. The web mastery contract was regenerated from the Python source, along with the realtime grading payload and error taxonomy, so the frontend stopped carrying stale copies of the same rules.

The API error contract was synchronized too: `word_generation_query_invalid` now exists in the generated web taxonomy with the correct conflict category. The hierarchy stats path also kept the query-budget regression green after the scheduled-status test fixture change.

## Decisions

We kept the mastery threshold server-owned instead of letting callers redefine it per request. We accepted the environment-owned Centrifugo cross-user denial rehearsal as the only unresolved broker-level exception; the app proxy denial path, static v6 config, and live recovery flow are covered.

## Impact

Validation finished cleanly: API `527 passed, 1 skipped`; the direct worker suite had `39 passed, 6 skipped` and the DB-enabled baseline worker tier had `45 passed`; shared Python had `26 passed`; web had `114 passed`, plus typecheck, lint, and production build. The opt-in hierarchy benchmark landed at `19.61 ms` for 2k and `104.35 ms` for 100k, with the 2k target under the `50 ms` budget.

The repository quick-baseline also passed the API, shared, Lexi, boundary, cycle,
and documentation tiers. Its FK detector checked all 30 recorded foreign keys
against the post-migration baseline, and the worker floor now matches the
canonical 45-test suite.

## Next

No code follow-up is open from this plan. The fresh-schema Compose rehearsal also
completed in an isolated project with temporary ports/configuration and was
cleaned up afterward. Keep the generated contracts in sync whenever the Python
policy or realtime payloads change, because the last bug here was simple drift
and it wasted real time.
