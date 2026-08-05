---
title: "Python Greenfield Migration — lexi-ai + FSRS + Hierarchy"
description: ""
status: completed
priority: P2
branch: "go-migration"
tags: []
blockedBy: []
blocks: []
created: "2026-07-04T17:33:58.638Z"
createdBy: "ck:plan"
source: skill
---

# Python Greenfield Migration — lexi-ai + FSRS + Hierarchy

## Overview

Rebuild the pycil backend as a **greenfield Python service** (FastAPI + SQLModel + Alembic), replacing the mid-flight Go/ent/chi stack on `go-migration`. Internalizes `~/projects/lexi-ai` as the dictionary + question + grading authority, implements the FSRS-4.5 learning engine and the folder/deck/REFERENCE hierarchy + stats designs, redesigns auth (OAuth 2.1 + backend JWT + iron-session), and adds Centrifugo for realtime. Removes billing/gamification/social/admin. Renames pycil terminology to match lexi-ai (`Term`→`Word`, `Definition`→`Sense`, `user_term_stats`→`user_sense_stats`, ELO→FSRS).

**Source design:** `plans/reports/260705-0001-python-greenfield-migration-brainstorm.md` (approved).

**Branch:** work happens on a NEW branch off `main` (retains old `apps/pycil-core` as reference), NOT on `go-migration`.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Scaffold & Infrastructure](./phase-01-scaffold-infrastructure.md) | Complete |
| 2 | [Baseline Schema & Migration](./phase-02-baseline-schema-migration.md) | Complete |
| 3 | [Auth Domain](./phase-03-auth-domain.md) | Complete |
| 4 | [FSRS Engine](./phase-04-fsrs-engine.md) | Complete |
| 5 | [Content & Lexi-AI](./phase-05-content-lexi-ai.md) | Complete |
| 6 | [Learning Domain](./phase-06-learning-domain.md) | Complete |
| 7 | [Hierarchy & Stats](./phase-07-hierarchy-stats.md) | Complete |
| 8 | [Realtime Centrifugo](./phase-08-realtime-centrifugo.md) | Complete |
| 9 | [Worker Redesign](./phase-09-worker-redesign.md) | Complete |
| 10 | [Frontend Auth & Rename](./phase-10-frontend-auth-rename.md) | Complete (closed 2026-08-05: the browser-pending auth/Centrifugo remainder shipped in `260727-1332-web-frontend-rebuild` — `apps/web/lib/auth/session.ts`, `apps/web/lib/realtime/provider.tsx`, covered by `auth.spec.ts` + `realtime-recovery.spec.ts` in the green E2E suite) |
| 11 | [Integration Wiring](./phase-11-integration-wiring.md) | Complete |
| 12 | [Tests & Docs](./phase-12-tests-docs.md) | Complete |

## Dependencies

**Supersedes direction of:** `260612-2302-full-project-refactoring` (status: in-progress, branch `go-migration`). That plan completes the Go/ent/chi migration; THIS plan pivots the backend back to Python, abandoning the Go direction. The Go plan should be marked `superseded` once the user confirms the pivot (not done automatically — it's a business decision).

**Branch:** work happens on a NEW branch off `main` (not `go-migration`). The `branch:` frontmatter above reflects the creation context, not the target branch.

## Red Team Review

### Session — 2026-07-05
**Findings:** 22 surviving (after dedup + evidence filter) — 20 accepted, 2 rejected/mooted.
**Severity breakdown:** 5 Critical, 8 High, 7 Medium (+2 Low folded in).

| # | Finding | Severity | Disposition | Applied To |
|---|---------|----------|-------------|------------|
| A1 | `get_senses(ids)` not in lexi-ai; `get()` takes word_id | Critical | Accept | Phase 5 (add to lexi), 2, 7 |
| A2 | `generate`/`grade` on `Lexicon.questions`, not `Lexicon` | High | Accept | Phase 5, 9 |
| A3 | Invalid format taxonomy (mcq/fill/write vs 4 real ids) | High | Accept | Phase 6, 9 |
| A4 | Cambridge SQLite dependency never provisioned | Critical | Accept | Phase 5, 1 |
| A5 | `lexi.init()` never called → no schema | High | Accept | Phase 9, 11 |
| A6 | Two processes construct client → dedup guard defeated | Medium | Accept | Phase 9 (worker single-writer) |
| A7 | py-fsrs dead path (FSRS-5/6, scheduler-shaped) | Medium | Accept | Phase 4 (verbatim port) |
| A9 | `Score`→`GradeResponse` mapping missing | Medium | Accept | Phase 6, 9, 10 |
| C1 | Systemic IDOR — no ownership checks | Critical | Accept | Phase 7 (require_node_access), 5 |
| C2 | banned-user lockout dropped | High | Accept | Phase 3 |
| C3 | internal-secret no constant-time/empty-reject | High | Accept | Phase 3 |
| C4 | JWT alg not pinned (alg-confusion/none) | High | Accept | Phase 3 |
| C5 | grade trusts client question payload (answer-key tamper) | High | Accept | Phase 6, 9 |
| C6 | Centrifugo channels not user-scoped | High | Accept | Phase 8, 10 |
| C7 | CSRF/cookie-vs-bearer contradiction | Medium | Accept | Phase 3, 10 (bearer-only) |
| C8 | rate-limit not fail-closed on auth | Medium | Accept | Phase 3 |
| B3 | grade job not idempotent (arq retry → LLM double-bill) | Critical | Accept | Phase 9 |
| B5 | WRITE verdict lost if push missed (no persist-back) | High | Accept | Phase 2, 6, 9 |
| B6 | no migration step in boot/deploy sequence | High | Accept | Phase 11 |
| B7 | deferred WRITE FSRS races first-attempt bookkeeping | Medium | Accept | Phase 6 (per-(user,sense) lock) |
| D1 | partitioning/BRIN/snapshot/2 crons premature at MVP | High | Accept | Phase 2, 11 (plain table) |
| D2 | prewarm_questions/lifecycle jobs (brainstorm said 3) | High | Accept | Phase 9 (cut) |
| D3 | L1+L2 cache premature (uncached <50ms) | Medium | Accept | Phase 7 (L1-only) |
| D4 | sessions table contradicts stateless JWT | Medium | Accept | Phase 2, 3 (drop) |
| D7 | deck_words has no reader | Low | Accept | Phase 2 (drop) |
| B4 | backup covers only one DB | High | Accept | (ops note — see below) |
| D5 | drop responses table | Medium | Reject | Has consumer (B5 verdict persist-back) |

**Mooted by acceptance:** two Critical failure-mode findings — "missing review_log partition halts all answers" and "arq cron not durable" — dissolve because D1 removes partitioning entirely (plain table).

**Ops note (B4):** backup/restore must cover BOTH pycil and lexi databases to a consistent point; deferred to deployment phase (not in the 12 code phases). Tracked here so it isn't lost.

### Whole-Plan Consistency Sweep
Ran after applying findings — see conversation. All phase files re-read; stale `deck_words`/`sessions`/`user_daily_snapshot`/partition/L2/`mcq`/`fill`/`write`/ELO references reconciled. Two-DB boundary + LexiClient port consistent across phases 2/5/6/7/9/11.

## Validation Log

### Session — 2026-07-05
**Questions:** 3 asked, 3 confirmed. Verification pass skipped — Red Team Review above already carries `file:line` evidence.

| # | Question | Decision | Propagated to |
|---|----------|----------|---------------|
| V1 | Migrate old pycil-core data (25 migrations on main) or clean slate? | **Clean slate** — no real users/data (never verified per prompt.md). No data-migration phase. | Phase 2 (confirmed greenfield, no migrate step) |
| V2 | Source of Cambridge SQLite (~142MB, gitignored) for deployment? | **Copy from `~/projects/lexi-ai/data`** — mount/copy into build context, set `LEXI_CAMBRIDGE_DB_PATH`. | Phase 1 (compose provisioning), Phase 5 (already noted) |
| V3 | How are decks/senses populated (lexi starts empty)? | **Lazy 100%** — words generated on-demand via `POST /words` → `lexi.generate`. No pre-seed. | Phase 5 (already lazy) |

**Recommendation:** proceed. No `[UNVERIFIED]` tags remain; all three decisions confirm the greenfield/lazy design already in the plan.

### Whole-Plan Consistency Sweep (validation)
Re-swept after propagating V1–V3. No data-migration/backfill/pre-seed refs (clean slate + lazy honored); Cambridge provisioning present in phase-01 + phase-05; only `prewarm` hits are the phase-09 "NO prewarm job" negations. Zero unresolved contradictions.
