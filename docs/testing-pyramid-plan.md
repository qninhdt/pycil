# Pycil Testing Pyramid Restructuring & Implementation Plan

**Author:** DeepMind Agentic Coding Pair (Antigravity)\
**Target Repository:** `/home/qninh/projects/pycil`\
**Status:** ✅ Completed & Verified (100% of Phases 1–4)\
**Execution Date:** October 18, 2026\

---

## 1. Executive Vision & Architectural Rationale

### 1.1 The Problem Statement
The Pycil testing ecosystem currently comprises **832+ tests** across three decoupled suites (`apps/api`, `apps/web`, `e2e`), but suffers from an acute **inverted pyramid in frontend** and **twin Playwright duplication**:
1. **Frontend Deficit**: Only 53 unit tests in `apps/web` vs 101 browser integration tests and 93 E2E tests. Complex state machines (`useStudyRuntime`, 317 LOC), settings validation, and error translation rely on Chromium runs rather than 5ms Node.js tests.
2. **The "Twin Playwright" Duplication**: Two parallel Playwright suites (`apps/web/tests/integration/browser` running against mock data, and `e2e/tests` running against live Docker/Clerk stack) test identical user flows: Landing, Dictionary additions, Profile updates, Settings, and Flashcard navigation.
3. **Backend ASGI HTTP Blindspot**: 29 out of 41 FastAPI endpoints are only tested via direct Python service functions interacting with the database, completely bypassing FastAPI routing, security dependencies, query validation, and RFC 9457 error serialization.
4. **CI/CD Latency & Flakes**: Live Clerk user provisioning over WAN across 72+ E2E tests consumes 5–9 minutes of external network I/O; unconfigured retry backoff in `test_decision.py` wastes ~2.6s in `asyncio.sleep`; un-cached test runs create high CI runtime.

### 1.2 The Unified Pyramid Model (Target State)

```
                              [ Unified E2E ]
                              ~30 - 35 Tests
                        Critical User Journeys Only
                       (Full Stack + Mock/Live Clerk)
                      =================================
                          [ Web Browser Component ]
                               ~25 - 30 Tests
                        Real Rendering Only: Canvas,
                      Artwork, CSS Overflow, Dialog A11y
                    =====================================
                         [ Backend API Integration ]
                               150 - 180 Tests
                       100% 41 Routes via AsyncClient
                         + Real Postgres/Redis/Taskiq
                  =========================================
                          [ Web Unit & DOM Hooks ]
                               180 - 220 Tests
                        Vitest + JSDOM / Testing-Lib
                       Hooks, Stores, Form Validation
              =============================================
                           [ Backend Domain Unit ]
                               350 - 380 Tests
                         Fast Pytest In-Memory (<2s)
                        Domain Models, Algorithms, FSRS
```

---

## 2. Definitive Scope & Boundary Guidelines

### Should E2E be split into Frontend E2E and Backend E2E?
**NO.** Having separate "Frontend E2E with Mocks" and "Backend E2E" is an anti-pattern that leads to the exact duplicate test maintenance and CI bloat Pycil currently experiences.
- **Backend** does not need E2E; it needs **API Integration Testing** via `httpx.AsyncClient` + PostgreSQL/Redis testcontainers. It verifies routes, auth, middleware, database, and background workers in-process at millisecond speeds.
- **Frontend** does not need mock-based E2E; it needs **Unit & Component Testing** (`vitest` + `@testing-library/react`) for state and interactions, retaining a minimal browser component suite strictly for layout and canvas rendering.
- **E2E is ONE Unified Top Layer (`e2e/tests`)**: Strictly reserved for end-to-end multi-tier business workflows (Happy Paths & Critical Journeys).

---

## 3. Phased Implementation Roadmap

### Phase 1: High-Priority Safety & Immediate Performance Wins (P0)

#### Track A: Backend (`apps/api`)
1. **Add Critical Missing Route Test**:
   - Write integration and schema tests for `POST /v1/nodes/{id}:modifySenses` and `nodes.patch_senses()`.
2. **Add Missing Utility Unit Test**:
   - Write unit test for `generate_handle()` in `apps/api/pycil/account/handles.py`.
3. **Slash Unit Test Sleep Time**:
   - In `apps/api/tests/unit/infrastructure/test_decision.py:30-36`, add `retry_min_seconds=0.001` in the test client fixture to eliminate ~2.57s of unneeded `asyncio.sleep`.
4. **Clean up Dead Utilities & Relocate Fixtures**:
   - Delete dead functions `date_range`, `resolve_date_window`, `utc_now` in `pycil/utils/dates.py`.
   - Move `UsageRecorder` from production `pycil/infrastructure/llm.py` into `tests/support/inference.py`.
   - Relocate `tests/unit/vocabulary/test_kv_store.py` to `tests/unit/infrastructure/test_kv_store.py` and delete tautological f-string assertions.
   - Delete dead API routes: `batchSummarize`, `batchReadContext`, and `me/senses/{sense_id}/decks`.

#### Track B: Frontend (`apps/web`)
1. **Fix Node Worker Pollution**:
   - In `apps/web/tests/unit/jobs.test.ts:7`, replace `Object.assign(globalThis, { window: {} })` with `vi.stubGlobal('window', {})` and ensure clean teardown.
2. **Prune Zero-Value Visual Matrix Loops**:
   - Delete the 16-navigation loop in `apps/web/tests/integration/browser/app-shell.test.ts:381-403`.
   - Delete the viewport/theme loop in `apps/web/tests/integration/browser/showcase.test.ts:113-142`.
   - Delete the redundant viewport loop in `apps/web/tests/integration/browser/assistant.test.ts:480-507`.
3. **Delete Phantom & Duplicate Assets**:
   - Remove dead `.shell-nav-rule` assertions from `artwork.test.ts:39` and `app-shell.test.ts:41, 48`.
   - Delete `apps/web/src/lib/api/services/mock/database.ts` and consolidate references to `database.json`.
   - Remove hardcoded `waitForTimeout(200)` in `home-dashboard.test.ts:164`.
4. **Implement Missing Unit Tests**:
   - Extract and unit-test the complex learning settings validation logic in `settings-page.client.tsx:47-52`.
   - Add unit tests for `ApiError` code-to-message mappings in `src/lib/api/error.ts`.

#### Track C: E2E Suite (`e2e`)
1. **Collapse Question Types Clerk Waste**:
   - In `e2e/tests/study/question-types.test.ts`, consolidate the 8 separate Clerk user setups into 1-2 representative tests or execute within a single user session.
2. **Wire up Taskiq Background Generation in E2E**:
   - In `e2e/tests/vocabulary/dictionary.test.ts:20-26`, click the "Prepare entry" button, await the background worker completion, and verify dynamic reveal of the generated word.
3. **Verify FSRS & Home Streak Progression**:
   - In `e2e/tests/study/session.test.ts` / `home/dashboard.test.ts`, verify that completing study updates `due_after` intervals and increments the `#home-streak-title` streak count to 1 day.
4. **Optimize Sequential Loops**:
   - Replace the 100-step sequential click loop in `e2e/tests/study/flashcards.test.ts:29-48` with a focused boundary assertion.
   - Parallelize serial seeding loops in `references.test.ts`, `conversations.test.ts`, and `public-library.test.ts` using `Promise.all`.
5. **Quarantine / Fix Google OAuth Anti-Pattern**:
   - Replace manual typing into `accounts.google.com` in `e2e/tests/external-auth/providers.test.ts` with mock token verification or skip gracefully in CI.

---

## 4. Verification & Review Protocol

After the 3 implementer subagents finish, 3 reviewer subagents will conduct:
1. **Backend Reviewer**: Verify `pytest -q tests/unit tests/integration` passes 100%, verify speedup in `test_decision.py`, check that deleted dead code has no broken imports.
2. **Frontend Reviewer**: Verify `pnpm test:vitest` and `pnpm test:browser` pass 100%, check that worker pollution in `jobs.test.ts` is resolved, and confirm zero regression in mock server runs.
3. **E2E Reviewer**: Verify `pnpm exec playwright test` passes, check that Clerk rate limiting is avoided, and confirm that Taskiq worker and streak progression are verified.
