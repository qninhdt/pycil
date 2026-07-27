# Learning System Redesign onto the Shipped Lexi Contract

**Date**: 2026-07-24
**Severity**: High (10-phase cross-cutting redesign)
**Component**: learning domain (API + worker + schema)
**Status**: Resolved — full test gate green

## What Happened

Executed the 10-phase plan to rebuild pycil's learning domain on lexi-ai's
level-based contract (SHA `7d6b571`). All phases landed in one cook run so the
tree never merged half-migrated: port/DTOs → policy+resolver → schema → Redis
state → planning → round scheduler → score/state engine → API router → worker →
tests. Final gate: API 191 passed/1 skipped, worker 22, shared 13; ruff +
compileall clean; single alembic head `0016`.

## The Brutal Truth

Two plan assumptions were stale and would have wasted hours if trusted blindly:

1. **The installed lexi was the WRONG SHA.** `pyproject`/`uv.lock` pinned
   `7d6b571` (new contract) but both venvs still had `3bbd70e` installed (old
   `format`/`answer_kind`/`Score` contract). The worker `pyproject` still pinned
   the old SHA outright. Writing Phase 1 DTOs against the "shipped" contract would
   have failed against the actually-installed package. Caught it before writing a
   line by diffing `direct_url.json` against the lock, then `uv sync`-ing both
   venvs (and re-adding the `dev` extra that the first sync silently dropped).

2. **The alembic chain view was stale.** The plan said add revision `0007` on
   head `0006`; the real head was `0015` and `0007` was already taken. Adapted to
   `0016_learning_lifecycle_v2` on `0015` — the confirmed D-A decision (forward
   revision, no squash) held; only the id was wrong.

## Technical Details

- Correctness core (`service.apply_checkpoint_result`) validated against real
  Postgres: acquisition enters FSRS only after N passed checkpoints; a clean due
  review is exactly one `Good`; a first wrong locks `Again` and repair adds no
  second FSRS (the Postgres first-attempt claim is consumed by the `Again`, so the
  later completion `Good` loses the claim); a served-below-requested fallback
  locks `Again`; repeated wrong answers terminate at the retry cap.
- Concurrency: two parallel disqualifying submits on the same (session, sense)
  produce exactly one `review_log` row (advisory xact lock + unique claim).
- F1 ordering enforced: Postgres commit precedes all best-effort Redis advisory
  writes, so a crash in the gap can never lock Redis while Postgres rolled back.

## Root Cause Analysis

Plan artifacts drift from the codebase between planning and execution. The
lexi-pin and alembic-head assumptions were both correct at plan time and stale at
cook time. Scout-first on every "given" (grep the lock, `alembic heads`) caught
both before they cost anything.

## Lessons Learned

- Never trust a plan's "already installed / already pinned" claim — verify the
  installed artifact, not the manifest.
- `uv sync` without `--extra dev` silently removes test/lint tooling; always
  re-sync the dev extra after a dependency change.
- A passing test suite hides post-commit reliability bugs: the code review caught
  that the `/answers` graded path re-armed the consume-once bind after the durable
  commit (a duplicate-`idempotency_key` 500 loop under a post-commit Redis
  hiccup). Fixed by gating the restore on a pre-commit flag.

## Next Steps

- `docs/system-architecture.md` and `docs/codebase-summary.md` still describe the
  old single-issue delivery model; a follow-up doc pass should rewrite the
  learning sections to the round/level model (flagged as major docs impact).
- Run the opt-in lexi PG release gate in CI alongside pycil's suite.

## Unresolved Questions

- None blocking. The reconcile path for pending grades re-enqueues
  `grade_answer_v1` (realtime publish) rather than the task-registry SSE variant —
  pre-existing behavior, worth confirming FE observability expectations later.
