# Lexi refresh and browser E2E review — 2026-10-10

## Dependency and consumer changes

Pycil consumes native Lexi source from `/home/qninh/projects/lexi-ai` as local,
unpublished `0.1.0+pycil.20261010.2`. Source HEAD remains
`f7537590b0cc71be3c730f695a4a1b41ecbd9946`; packaged uncommitted inputs are identified
by [provenance hashes](../../../vendor/lexi-ai/provenance.json), not HEAD alone.
The previous local wheel was replaced; no upstream files were changed.

- Removed `usage_note` from the frontend DTO/parser/rendering and mock fixture;
  regenerated OpenAPI from the installed dependency. Native migration head is
  `20261010_no_notes` and drops stored notes permanently.
- Adapted browser inference fixtures to inventory references grouped by POS.
  Added three real native generation checks for successful generation, failed
  generation with a new retry task, and partial usable content.
- Updated learning checks for fixed-stem question deduplication and compact markup.
  Seeded test row sequences now follow explicit fixture IDs before native inserts.
- Fixed the browser retry assertion to poll the new task, retaining FAILED status
  for the original task; updated the partial-content assertion to native markup.
- Bound web test scripts to `@playwright/test/cli.js` and made the managed runner use
  the project E2E script. Concurrent Storybook dependency changes introduced a
  different `playwright` CLI version; invoking that CLI failed collection while the
  installed `@playwright/test` CLI collected correctly. Existing Storybook work is
  preserved.

## Executed checks

| Check | Result |
| --- | --- |
| Wheel checksum and uv locked installation | Passed |
| Fresh schema plus learning pipeline on managed disposable stores | 42 passed |
| Entire API suite on managed disposable stores | 307 passed, 2 skipped, 17 upstream LangGraph deprecation warnings |
| Dictionary fixture/parser/mock contract/live adapter tests | 5 passed |
| Web TypeScript | Passed after concurrently edited Storybook imports were resolved |
| Backend Ruff lint/format | Passed |
| Web Oxlint | Passed with warnings |
| E2E collection | 74 tests in 10 files, including Clerk setup and 3 live-provider cases |
| Focused full-stack Lexi browser run | 5 passed: Clerk setup, guest Dictionary, harbor success, quay failure/retry, jetty partial content plus completed study |
| Production web build | Failed during prerender of `/_global-error`: Next.js `Invariant: Expected workStore to be initialized`; compilation and TypeScript stages passed |

Collection is only a test inventory; it does not establish that all 74 tests pass.
The ordinary API suite skips the opt-in browser runner and performance tier.
The production-build failure remains unresolved in this working tree; its cause
was not established by an isolated baseline comparison. Do not treat these passing
dependency/browser checks as production-build acceptance.

## Is E2E complete?

**No. Core journeys have broad coverage, but several features and execution gates
remain unverified.** The current product has no payment, audio, import or translation
workflow requiring browser tests; a saved translation-language preference is covered.

| Area | Collected cases | Coverage read from current source |
| --- | ---: | --- |
| Account/settings | 4 | Profile handle/bio, duplicate handles, persisted settings, Free/Pro permissions, failed drafts |
| Authentication | 10 | Signup/verification/resend, invalid login, password reset, JWT refresh/expiry/revocation, account switching; OAuth and TOTP conditional |
| Library/Discovery/integration | 20 | CRUD, move/copy, hierarchy, publication/revocation, references, private ownership, pagination/search/filter/sort, quotas/concurrency, lost responses, flashcard persistence |
| Dictionary | 7 | Guest reads/markup/misses, stale searches, batched picker, nested destination, generation/retry/partial content |
| Study | 15 | All 7 question types with SINGLE_CHOICE; SINGLE_WORD with DEFINITION_TO_WORD; SHORT_ANSWER with WORD_TO_DEFINITION; resume/reload/conflicting tabs, DUE/NEW, stale grading, review replay |
| Reporting/mobile | 3 | Deduplicated counts, activity/practice/streak/schedule, timezone, outages/retry; one 390×844 mobile learning journey |
| Assistant | 11 | SSE/reasoning/timeouts, history/checkpoints, approve/reject, isolation, pagination/deletion, busy/cancel/error, vision validation, allowance/rate limits |
| Real providers | 3 | Separate opt-in generation, typed grading and Assistant smoke profile |
| Clerk setup | 1 | Official testing-token configuration |

## Gaps and priorities

1. **CI does not execute browser tests.** `.github/workflows/test.yml` runs the
   backend and image gates, without web typecheck/build, mock browser tests or the
   opt-in full-stack runner. Backend success therefore does not protect UI journeys.
2. **Typed study coverage omits 3 enabled pairs.** Config enables CONTEXT_TO_WORD
   and CLOZE_TO_WORD with SINGLE_WORD, plus WORD_TO_USAGE with SHORT_ANSWER. E2E
   explicitly exercises the other 2 typed pairs. Backend tests are complementary
   evidence, not browser coverage of the missing pairs.
3. **Clerk account continuation has no E2E case.** `/auth/continue/[[...rest]]`
   exists; successful ordinary login cannot validate pending account tasks.
   Google OAuth requires dedicated credentials; TOTP can skip when disabled.
4. **Lexical detail/search branches lack live browser cases.** Current live fixture
   tests basic noun meanings and generation; aliases, inflected-reference searches,
   POS tabs, forms/patterns/collocations and related-word navigation are not asserted
   as complete journeys against the native API. Mock tests cover some detail UI.
5. **Public direct learning is not explicitly completed.** The API permits learning
   a readable public node without saving it. E2E tests publication/references and
   flashcard revocation, but does not finish that unsaved public study journey.
6. **Mobile and browser coverage is limited.** One mobile viewport/journey; no
   configured Firefox/WebKit projects or full accessibility audit.
7. **Real inference is a separate gate.** Default E2E substitutes only external
   inference, preserving real auth/API/domain/native validation/storage. The three
   live-provider cases skip in the default profile and were not invoked here.

These are an audit of existing coverage, not newly implemented product scope or a
claim of full E2E acceptance. Prioritize the CI gate and missing typed pairs before
using E2E as a release gate.

## Operational boundaries

Only disposable stores were migrated. Native note removal requires a backup before
an operational upgrade; downgrade cannot restore values. No deployment or paid
inference was performed. Browser runs used temporary Clerk development identities
owned and cleaned by the runner. Local runner `.env` lacked `CLERK_PUBLISHABLE_KEY`;
execution supplied the existing frontend key only in the child environment.
Existing cached Chromium was selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`.
All managed store projects completed cleanup. The owned Next dev process was
terminated after browser execution; no API or frontend server was left on 8000/3000.

Sources: [web runner](../../../apps/api/tests/system/test_web_e2e.py),
[E2E suite](../../../apps/web/e2e/), [browser config](../../../apps/web/playwright.e2e.config.ts),
[product policy](../../../config/config.yaml), [CI](../../../.github/workflows/test.yml).
