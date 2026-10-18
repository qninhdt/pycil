# Pycil Comprehensive Testing Suite Audit & Verification Report

**Date:** October 18, 2026\
**Auditors:** 6 Specialist Scouts + 3 Verification Reviewers\
**Target Repository:** `/home/qninh/projects/pycil` (`apps/api`, `apps/web`, `e2e`)\
**Scope:** 832+ tests across Unit, Integration, Component Browser, and Full-Stack E2E\

---

## Executive Summary & Test Pyramid Analysis

An exhaustive audit was conducted across all test directories, source code modules, CI/CD configurations, and runtime performance profiles in the Pycil project. 6 specialist subagents audited the codebase and 3 reviewer subagents rigorously verified all findings through direct code inspection, symbol resolution, AST traversal, and timing benchmarks.

```
                              [E2E Suite]
                           93 Tests (107 runs)
                         Full Stack + Live Clerk
                        =========================
                       [Web Browser Integration]
                        101 Tests (Playwright)
                      Mock Data Mode (Chromium)
                    ===============================
                     [Web Integration / Services]
                       31 Tests (Vitest / Node)
                  ===================================
                   [API Integration & Benchmarks]
                       232 Tests (Pytest / DB)
                =======================================
                            [Web Unit Tests]
                         53 Tests (Vitest / Node)  <-- SEVERE DEFICIT
             =============================================
                           [API Unit Tests]
                       325 Tests (Pytest / Pure)
```

### Key Statistical Insights:
- **Total Test Count**: 832 distinct test functions (expanding to 854+ executions with browser/platform matrices).
- **The Inverted Frontend Ice Cream Cone**: In `apps/web`, there are only **53 unit tests** compared to **101 browser integration tests** and **93 E2E tests**. The frontend heavily relies on slow Chromium launches for tests that should execute in 5ms in Node.
- **The Duplicate Browser Tier**: The project maintains two parallel Playwright suites (101 mock browser tests in `apps/web` + 93 full-stack E2E tests in `e2e`), testing virtually identical form submissions, dialog selections, navigation flows, and responsive layouts twice.
- **API ASGI Blindspot**: Out of 41 FastAPI endpoints, **only 12 endpoints (29.3%)** are ever tested through ASGI HTTP (`AsyncClient`) in `apps/api/tests/`. The other **29 endpoints (70.7%)** are tested only through direct Python service function calls directly against the database, completely bypassing route decorators, validation schemas, query parameters (`strict_query`), and HTTP error translation.

---

## 1. Redundant & Unnecessary Tests (Testing Thừa, Không Cần Thiết)

### 1.1 Duplicate Cross-Layer Browser Journeys (E2E vs Web Browser)
* **Landing Page Navigation**:
  - `apps/web/tests/integration/browser/landing.test.ts:38-49` navigates to `/`, asserts headers, clicks 'Build your vocabulary' -> `/signup`, 'Sign in' -> `/login`, and 'Open the app' -> `/app`.
  - `e2e/tests/public/landing.test.ts:3-13` tests the exact same navigation flow.
  - In addition, `e2e/playwright.config.ts:15` classifies `landing.test.ts` as critical, forcing it to run **3 times** per E2E run (default, mobile Pixel 7, webkit) to test static anchor link `href` attributes.
* **Dictionary Meaning to Deck Creation**:
  - `apps/web/tests/integration/browser/dictionary.test.ts:5-24` searches a word, opens destination dialog, navigates to Personal, adds to deck, creates deck.
  - `e2e/tests/vocabulary/dictionary.test.ts:3-18` and lines 46-64 execute the exact same flow step-by-step.
* **Profile Settings & Handle Conflicts**:
  - `apps/web/tests/integration/browser/profile-settings.test.ts:20-45` edits display name, handle, bio, and asserts `"That handle is already taken. Choose another one."`
  - `e2e/tests/account/profile.test.ts:4-75` executes the identical DOM interactions and asserts the exact same error string.

### 1.2 Zero-Value "Visual Matrix" Tests Without Screenshots
* **`apps/web/tests/integration/browser/app-shell.test.ts:381-403`**:
  - Loops over 2 viewports (`1440, 390`) x 2 themes (`light, dark`) x 3 routes (`/app, /login, /signup`).
  - Performs **16 full `page.goto` calls** in a single test case.
  - Captures **zero screenshots (`toHaveScreenshot`)** and does zero visual diffing; only asserts `heading.toBeVisible()`. Wastes ~15 seconds of browser execution time.
* **`apps/web/tests/integration/browser/showcase.test.ts:113-142`**:
  - Loops over 2 viewports and 2 themes across 5 showcase tabs, only asserting `overflowCheck(page)` (`scrollWidth <= innerWidth`).
* **`apps/web/tests/integration/browser/assistant.test.ts:480-507`**:
  - Loops over 2 viewports and 2 themes purely to verify bounding box widths.

### 1.3 8-Fold Parameterized Clerk Spawns in E2E
* **`e2e/tests/study/question-types.test.ts:5-25`**:
  - Parameterized across 8 question types (`definition_to_word`, `word_to_definition`, `cloze_to_word`, `context_to_word`, `meaning_in_context`, `word_to_usage`, `dialogue_completion`, `sentence_rewrite`).
  - Because each test requests `{ user }`, it provisions **8 separate live Clerk user accounts over the WAN**, each taking 4–8s to create, log in, and tear down.
  - All 8 tests execute the exact same UI interaction (`page.getByRole('button').filter({ hasText: answer }).click()`) and assert `studied: 1`. 1 recognition test + 1 production test in E2E would provide identical regression confidence.

---

## 2. Missing Critical Tests (Testing Thiếu, Quan Trọng)

### 2.1 Backend Critical Gaps
1. **`POST /v1/nodes/{id}:modifySenses` has ZERO tests anywhere**:
   - `apps/api/pycil/library/api.py:107` exposes this endpoint, and `apps/web/src/lib/api/services/http.ts:104` calls it in production.
   - It has **zero tests across unit and integration suites**. Neither the route nor `nodes.patch_senses()` is verified.
2. **`generate_handle` has ZERO tests in the entire repository**:
   - `apps/api/pycil/account/handles.py:8` generates user handles from emails or display names. It has 0 unit tests and 0 integration tests.
3. **Entire `pycil.library` subsystem has 0 pure unit tests**:
   - `nodes.py` (859 LOC), `scope.py` (260 LOC), and `schemas.py` are only tested via PostgreSQL container integration tests. DAG cycle detection, path reconciliation, and scope budgets lack unit validation.
4. **Entire `pycil.jobs` subsystem has 0 pure unit tests**:
   - `singleflight.py` (concurrency serialization, Redis lock release safety) and `schemas.py` have zero unit test coverage.
5. **Core diagnostic grading algorithm lacks unit tests**:
   - `pycil/study/grading.py` (296 LOC) contains choice resolution, word matching, rubrics, and spelling vs grammatical thresholds. Tested only through heavy database integration fixtures.
6. **HTTP Route Layer Coverage Deficit**:
   - 25 to 29 out of 41 FastAPI endpoints are never tested with `AsyncClient`. Query parameter validations (`strict_query`), path decoding, and RFC 9457 error serialization are unverified at the HTTP boundary.

### 2.2 Frontend Critical Gaps
1. **0 Unit Tests for Critical Custom Hooks**:
   - `useStudyRuntime` (`src/features/study/use-study-runtime.client.ts`, 317 LOC): Multi-tab storage conflict detection, background job recovery (`resumeJob`), submission retry idempotency, and abort controller cleanup.
   - `useHomeOverview` (`src/features/home/use-home.client.ts`, 45 LOC): Polling clock intervals, focus event listeners, and TanStack query orchestration.
   - `useAiPanelState`, `useNavigationState`, `useTheme`, `useAccount`, `useCopyToClipboard`.
2. **Untested Complex Settings Validation**:
   - `src/features/account/settings-page.client.tsx:47-52`: Complex rules combining IANA timezone validation, format-type pair compatibility, upper/lower bounds, and max question preparation product limits (`questions_per_sense * max_sense_count <= limits.max_questions_per_prepare`) are inlined and untested.
3. **`ApiError` Code-to-Message Mappings**:
   - ~19 domain error codes in `src/lib/api/error.ts:28-68` map to localized messages. 0 tests assert the resulting error messages.
4. **Missing Browser Accessibility Tests**:
   - Dialog focus trapping (`Tab` / `Shift+Tab` cycling within modals) and background document inertness (`aria-hidden="true"`).
   - WAI-ARIA tab navigation (`ArrowLeft` / `ArrowRight` on Tablists).

### 2.3 E2E Critical Gaps
1. **Taskiq Background Vocabulary Generation via Worker Never Clicked**:
   - In `e2e/tests/vocabulary/dictionary.test.ts:20-26`, the test searches for an unprepared word (`jetty`), verifies that the "Prepare entry" button is visible, and **stops without clicking it**.
   - The entire asynchronous lifecycle (click button -> `202 Accepted` -> Taskiq worker job -> Redis polling -> dynamic entry reveal) has **zero E2E test coverage**.
2. **FSRS Spaced Repetition Updates & Home Dashboard Streak Counter**:
   - Tests verify that study sessions complete (`studied: 1`), but never verify that the FSRS algorithm advances `due_after` intervals, or that the Home dashboard streak counter (`#home-streak-title`) increments to 1 day.
3. **Multi-Device / Cross-Context State Synchronization**:
   - Zero tests run two concurrent browser contexts for the same authenticated user to verify cross-device cache invalidation.

---

## 3. Duplicated, Zero-Value, or Junk Tests (Testing Lặp, Rác, Không Giá Trị)

### 3.1 Testing Python Language & Library Primitives
* **Dataclass Slots & Immutability**:
  - `apps/api/tests/unit/vocabulary/test_schemas.py:70-80`: Asserts `not hasattr(value, "__dict__")`, catches `FrozenInstanceError` when attempting mutation, and tests `dataclasses.replace()`.
  - `test_schemas.py:115-124`: Asserts that `Sense(id=1, ...)` has default tuple fields `((), (), (), (), ())`.
  - Testing Python standard library dataclass semantics rather than business logic.
* **Pydantic Empty Model Dump**:
  - `apps/api/tests/unit/account/test_preferences.py:71`: `assert ProfilePatch().model_dump(exclude_unset=True) == {}`.
* **Static Class Inheritance**:
  - `apps/api/tests/unit/app/test_configuration.py:168-173`: Asserts `issubclass(ApiSettings, ProcessSettings)` and checks keys on `model_fields`.
* **Ad-hoc Synthetic Schema Test**:
  - `apps/api/tests/unit/utils/test_utils.py:128-140`: Constructs an inline dummy class `Item(Strict)` to test that Pydantic enforces `PositiveID`.

### 3.2 Tautological & Dummy Assertions
* **Tautological Redis Key Tests**:
  - `apps/api/tests/unit/vocabulary/test_kv_store.py:130-175`: 45 lines asserting `TASK_STREAM_KEY == "pycil:jobs:tasks"`, `owner_key(job_id) == f"pycil:jobs:owner:{job_id}"`, etc., mirroring the f-string templates.
* **Testing Arithmetic Through Concurrency Shield**:
  - `apps/api/tests/unit/utils/test_utils.py:142-147`: Tests `await shielded_to_thread(lambda: compute(21)) == 42`. Does not test cancellation shielding or thread task cleanup.
* **Ghost Assertions on Untouched Mocks**:
  - `apps/web/tests/unit/ui-preferences.test.ts:16-30`: Asserts `expect(root.lang).toBe('en')` and `expect(root.classes.has('dark')).toBe(false)` on a mock object after running a function that never touches `lang` or `classList`.
* **Non-Assertive `rejects.toBeDefined()`**:
  - `apps/web/tests/integration/services/preview-services.test.ts:215-218`: Passes on any thrown error (including runtime syntax errors).

---

## 4. Dead Tests & Tests of Dead Features (Dead / Legacy Tests)

### 4.1 Dead API Endpoints in Backend
Confirmed by Reviewers 1 & 3 to have **0 callers in frontend and 0 callers in tests**:
1. `POST /v1/study:batchSummarize` (`apps/api/pycil/study/api.py:142`)
2. `POST /v1/me/senses:batchReadContext` (`apps/api/pycil/vocabulary/api.py:81`)
3. `GET /v1/me/senses/{sense_id}/decks` (`apps/api/pycil/vocabulary/api.py:95`)

### 4.2 Dead Code in Backend Utility Modules
* `date_range`, `resolve_date_window`, `utc_now` in `apps/api/pycil/utils/dates.py`: Zero callers across `apps/api/pycil/`. Only imported by `tests/unit/utils/test_utils.py`.
* `UsageRecorder` in `apps/api/pycil/infrastructure/llm.py:139`: Test-only context manager residing in production code; 0 production callers.

### 4.3 Dead & Legacy Frontend Assertions
* **Dead CSS Class `.shell-nav-rule`**:
  - `artwork.test.ts:39`, `app-shell.test.ts:41, 48`: Asserts `toHaveCount(0)` on `.shell-nav-rule`. The CSS class does not exist anywhere in `apps/web/src`.
* **Dead Component Extended Demos in Showcase**:
  - `showcase.test.ts:154-187, 213-234`: Tests `InputOTP`, `Menubar`, `Calendar`, `DirectionProvider`, and multi-step questionnaire. None of these components are used anywhere in the application.
* **Duplicate 99KB Mock Database**:
  - `apps/web/src/lib/api/services/mock/database.json` (99KB) and `database.ts` (99KB) contain identical data.

### 4.4 Brittle & Dead E2E Routes
* **Quarantined Google OAuth Automation**:
  - `e2e/tests/external-auth/providers.test.ts:24-38`: Directly automates `accounts.google.com`. Throws an error when credentials are missing and is blocked by Google anti-bot detection in CI.
* **Untested Next.js Routes**:
  - `/auth/continue` (`apps/web/src/app/(auth)/auth/continue/[[...rest]]/page.tsx`): 0 tests.
  - `/auth/signup` (`apps/web/src/app/(auth)/auth/signup/[[...rest]]/page.tsx`): 0 tests.
  - `not-found.tsx` (`apps/web/src/app/not-found.tsx`): 0 tests.

---

## 5. Slow or Unoptimized Tests (Chạy Chậm, Không Tối Ưu)

### 5.1 Backend Performance Bottlenecks
1. **Unconfigured Retry Backoff in `test_decision.py` (~2.57s Delay)**:
   - `apps/api/tests/unit/infrastructure/test_decision.py:30-36`: Uses default configuration backoff (0.5s per retry). 5 tests spend 0.51s each in `asyncio.sleep`. Overriding `retry_min_seconds=0.001` shaves **~2.5s** off unit tests.
2. **Hardcoded Sleeps in Integration Tests (~2.7s Delay)**:
   - `tests/integration/assistant/test_leases.py:69`: `await sleep(1.2)` (1.2s).
   - `tests/integration/jobs/test_jobs.py:718`: `await asyncio.sleep(1)` (1.0s).
   - `tests/integration/infrastructure/test_telemetry.py:221`: `await asyncio.sleep(0.5)` (0.5s).

### 5.2 Frontend Performance Bottlenecks
1. **Monolithic 2-Minute Test in `library-navigation.test.ts:176-246`**:
   - Declares `test.setTimeout(120_000)`.
   - Loops 4 viewports x 5 routes = **20 page loads** in a single test case, with 40 theme toggles and canvas luminance math.
2. **Global State Mutation Without Cleanup in `jobs.test.ts:7`**:
   - `vi.hoisted(() => { Object.assign(globalThis, { window: {} }) })`.
   - Not cleaned up by `vi.unstubAllGlobals()`, permanently defining `window = {}` on the Node worker thread.
3. **Implicit Style Harvesting Navigation in `render-fixture.ts:33-39`**:
   - Triggers an implicit `page.goto('/app')` on the first fixture render in every worker process.
4. **Hardcoded Sleep in `home-dashboard.test.ts:164`**:
   - `await page.waitForTimeout(200)` to wait for scrollbars.

### 5.3 E2E Performance Bottlenecks
1. **Clerk WAN Overhead Across 72+ Tests (5 to 9+ Minutes)**:
   - 72 tests create and delete real Clerk identities over WAN. Each setup/teardown cycle costs 4–8 seconds.
2. **100-Step Sequential Click Loop in `flashcards.test.ts:29-48`**:
   - 100 individual clicks and assertions in a loop across a page boundary, taking 20–30s.
3. **Sequential API Seeding Loops**:
   - `references.test.ts` (22 calls), `conversations.test.ts` (26 calls), and `public-library.test.ts` (26 calls) seed data in serial loops rather than using `Promise.all`.

---

## 6. Taxonomy Misplacements (Sai Level Trong Taxonomy)

| Test File & Line | Current Level | Correct Level | Rationale |
| :--- | :--- | :--- | :--- |
| `tests/unit/vocabulary/test_kv_store.py` | Unit (Vocabulary) | **Unit (Infrastructure)** | Tests `InMemoryStore` and multi-domain Redis key formats. Has zero vocabulary logic. |
| `tests/integration/infrastructure/test_telemetry.py:36` | Integration | **Unit (Infrastructure)** | Pure mock test with zero DB or Redis calls. |
| `apps/web/tests/integration/services/*.ts` | Web Integration | **Web Unit (API Services)** | Uses `globalThis.fetch` mocks and in-memory mock databases. No real network boundary. |
| `apps/web/tests/integration/assets/design-system.test.ts` | Web Integration | **Repository Linter / Script** | Static filesystem check asserting `toHaveLength(61)` on UI components. |
| `grade-details.test.tsx`, `assistant-tool-renderers.test.tsx` | Web Unit (Node SSR) | **Web Component (DOM)** | Uses `renderToStaticMarkup` with regex substring matches on interactive client components. |
| `e2e/tests/assistant/access-and-usage.test.ts:16` | E2E Playwright | **API Integration** | Calling `secondary.api.call(..., [403, 404])` tests raw HTTP status codes, not user journeys. |
| `e2e/tests/study/recovery.test.ts:33, 87` | E2E Playwright | **Web Unit / API Unit** | Intercepts HTTP headers (`idempotency-key`) and injects prototype `QuotaExceededError`. |
| `apps/api/tests/integration/jobs/test_jobs.py:282` | Integration | **E2E / System** | Spawns external CLI worker processes with `SIGTERM`/`SIGKILL` signals. |

---

## Actionable Remediation Roadmap

```
+-----------------------------------------------------------------------------------+
| PHASE 1: IMMEDIATE PERFORMANCE WINS & CRITICAL SAFETY (P0)                        |
| 1. Add tests for POST /v1/nodes/{id}:modifySenses and generate_handle()          |
| 2. Add retry_min_seconds: 0.001 in test_decision.py (saves ~2.5s instantly)      |
| 3. Fix jobs.test.ts globalThis.window pollution via vi.stubGlobal                 |
| 4. Delete zero-value visual loops (app-shell.test.ts:381, showcase.test.ts:113)  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| PHASE 2: MISSING CRITICAL JOURNEYS & TAXONOMY CLEANUP (P1)                        |
| 1. Wire up E2E click for "Prepare entry" button to test Taskiq worker generation   |
| 2. Verify FSRS interval progression and #home-streak-title in E2E study test     |
| 3. Collapse 8-step question-types.test.ts Clerk loop into 2 representative tests  |
| 4. Move tests/integration/services/*.ts to tests/unit/services/                   |
| 5. Remove dead code: date utilities, UsageRecorder, dead API routes              |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| PHASE 3: PYRAMID REBALANCING & E2E SPEEDUP (P2)                                   |
| 1. Add @testing-library/react and write unit tests for custom hooks               |
| 2. Replace live Clerk WAN calls in PR CI with a local mock JWT session token      |
| 3. Build a consolidated HTTP route integration test suite covering 29 endpoints   |
| 4. Break up 120s library-navigation.test.ts and optimize sequential click loops    |
+-----------------------------------------------------------------------------------+
```
