# Focus entry and project E2E review — 2026-10-12

Status: completed. Collection is not execution evidence.

## Repaired behavior and diagnosis

Home and Library Practice/Learn new/Review links enter focus mode directly. The
standalone Learn authentication/restoration/error gates and Home preparation panel
are removed. Focus chrome remains available while preparation runs; errors show an
accessible popup with retry/return actions. Exiting cancels preparation, preventing
a late response from creating a session after navigation.

The application Docker logs showed preparation HTTP 500s. A bounded diagnostic
against the actual native pipeline reproduced an OpenAI `BadRequestError` escaping
the adapter's `LexiconError` handler. Existing fixtures had prefilled every question
artifact, so ordinary E2E never exercised this cold-bank provider branch. Provider
400/connection/timeout failures now retain the retryable 503 contract. The patch
does not claim to repair the external provider's rejected payload or availability.

The new backend regression failed **3/3 with HTTP 500 before the fix**, then passed
**3/3 with HTTP 503**, no personal learning writes and successful native retry.
The browser regression removes real native artifacts, rejects the inference call
once, checks the popup/503 and retries through native generation and real completion.
No synthetic preparation response replaces the API.

Other repaired boundaries: session readiness checks wait for an answer control,
invalid saved preparation is rejected, storage errors prevent silent advancement,
Clerk hydration gates editable account state, and mobile study actions have stable
descriptive accessible names. The live suite fails on unexpected browser exceptions.
Restarting after a stale grading error clears that error so automatic preparation
can actually start. Restored AI panels are tested after hydration rather than
clicking a transient server-rendered launcher while the panel is already opening.

## Whole-project coverage map

Scouted all 23 App Router page files, domain API routers, service adapters and both
browser suites. `/showcase` has separate mock visual/interaction coverage; it does
not establish authenticated backend behavior.

| Surface / owning tests | Assertions and added gaps |
| --- | --- |
| Landing, unknown routes — `product-journeys`, mock `landing` | Guest CTA, private API rejection, missing-page recovery; mock example, responsive/theme interactions |
| Login/signup/reset/callback/continuation — `authentication`, mock `services` | Real Clerk custom forms, incorrect credentials/codes, resend, reset, safe return routes, expired/refreshed JWTs, account switch and session revocation; external limitations below |
| Profile/settings — `account`, mock `account-pages` | Public privacy/XSS, handle conflict and draft retention, timezone/language persistence, Free/Pro entitlement, failed saves; added delayed Clerk hydration regression |
| Home — `reporting`, `focus-entry`, mock `home` | Deduplicated native counts, accepted activity/timezone/schedule, outage/retry, no writes on browsing; added direct focus navigation |
| Personal folders/decks/words — `library`, `integration`, `product-journeys` | Real create/edit/move/copy/delete, concurrent atomic membership, pagination/search/filter/sort, quotas, duplicate/lost writes; added failed metadata edit retry and Create reference UI live updates |
| Published/Discovery/public profile aliases — `integration`, `library`, `product-journeys` | Publication consent/cancel, private-ID isolation, references and revocation, catalog paging; added guest folder/deck reading and direct public learning with no personal Library membership |
| Dictionary/generation — `dictionary`, `product-journeys` | Public search/misses, stale-query cancellation, picker batching, nested destination, job failure/retry/completion, markup; added real alias/inflection/POS/form/pattern/collocation/related-word fixtures |
| Focus study — `study`, `focus-entry` | All 8 choice types and 6 typed pairs, retries/initial diagnostics, independent node sessions, competing tabs, frozen review replay, stale grading; added cold generation, failure popup, mobile entry, empty/missing scope, late-response cancellation, invalid cache, unavailable storage, pause/partial finish and lost grading response |
| Flashcards — `library`, `integration`, mock `focus` | Real paging/position, meaning details, account scope, no review writes |
| PycilAI — `assistant`, `product-journeys`, mock `assistant` | Native SSE/checkpoints/reasoning, approval/rejection, reauthorization/privacy, pagination/deletion, failure recovery, vision validation, usage/rate limits; added persisted auto-approval and failed settings write |

Backend integration/system tests cover atomic rollback, strict schemas, native
provider errors, Memory/Mastery rubrics, concurrent review replay, query deadlines,
resource ownership and migrations on disposable stores. They supplement browser
journeys; they are not counted as E2E.

## Inventory and test repairs

Original collection: **81 tests / 10 files**. Current collection: **108 / 12 files**
(including Clerk setup and five separately gated provider scenarios): account 5,
Assistant 13, authentication 11, Dictionary 9, focus entry 12, integration 9,
Library 11, product journeys 8, provider 5, reporting 3, study 21, setup 1.

The first expanded live run produced **75 passed, 23 failed, 7 skipped**. It exposed
real hydration/state failures and stale test assumptions. Test repairs include the
removed `Start session`/`Save to Personal` controls, retired `study:submitReviews`
endpoint, localized error labels and asynchronous generation completion. NEW tests
use an unstudied Sense rather than reusing one already learned earlier in the suite.

A subsequent full run produced **85 passed, 14 failed, 7 skipped** before the final
assertion fixes. A focused recheck passed **21/25**, including account hydration,
Assistant reopening/approval/history/privacy, stale-session restart and lost grading
response. The subsequent five-case final check passed, including image sending, guest
Published reads, direct public learning and reporting. The latest result for each
named case across the full run and focused rechecks is **101 passed, 7 skipped,
zero remaining failures**. This is cumulative execution evidence, not a claim that
a single full run passed on the final revision. The failed full runs are retained.

Private Library read tools return a handled `node_not_found` ToolMessage, not a
terminal `RUN_ERROR`: verified by the native backend test and Assistant contract.
The browser assertion checks persisted tool-error content, no private deck name,
and normal run completion. It continues to assert cross-account HTTP 404s.

Image sending exposed an assistant-ui message attachment lookup during the pending
composer submission, when the persisted message attachment list was still empty.
The UI now renders the pending submission attachments directly. This regression
failed before the fix and passed in two subsequent native browser runs.

Guest Published links previously reached an account-only Library gate. Public
folder/deck reads now use the existing anonymous service contracts and the shared
Library header, with public meanings and cursor navigation. Guest profile folders wait for
identity hydration, use a distinct anonymous query key and omit personal study
summary enrichment (the native public contract returns null learning fields).
Mock and native browser
regressions verify reading while signed out and rejection of private nodes.

## Executed validation

- Backend default suite: **340 passed, 2 skipped** on disposable PostgreSQL/Redis.
- Cold generation error regression: **3 passed** after proving its failing baseline.
- Native typed grading decision-boundary transport regression: **2 passed**.
- TypeScript and Ruff lint/format passed; Oxlint has warnings and no errors.
- Production build passed on the final source and current Next configuration.
- Final native browser group: **5 passed** (including Clerk setup).
- All four mock account/public-profile tests passed after the guest-read repair.
- Mock suite baseline: **132 passed, 5 failed, 10 not run**. The full final run
  returned **146 passed, 1 failed**; its sole navigation was aborted by the logged
  Fast Refresh when the HTTP adapter changed during that run. The unchanged
  desktop/mobile/theme matrix then passed on a fresh server (**1 passed**).
  Latest execution per mock case: **147 passed**, cumulative rather than one
  uninterrupted full run. Four account and fifteen adapter cases were rechecked
  after the final anonymous-read fix.

The managed profile owns Next.js 3000 and API 8100 and disposes its exact resources
and temporary Clerk users. Its frontend uses a disposable source snapshot to avoid
hot reload interrupting a long SSE test. Tests do not use application API 8000 or
application stores. Stop ordinary `pnpm dev` while running this profile. A frontend CI job
adds mock Chromium, TypeScript, lint and build gates; it does not silently supply
Clerk credentials or claim live coverage.

## Limits and findings outside the focus repair

- Five paid external-provider scenarios are separate opt-in tests; the full live
  provider profile was not run. Bounded diagnostics are not full provider acceptance.
- Google OAuth completion lacks dedicated Google credentials. TOTP is disabled in
  the development Clerk instance. These are explicit skips, not passing coverage.
- Pending account tasks need a configured Clerk instance. Ordinary sign-in does
  not prove continuation completion. Callback rejection is covered separately.
- Only Chromium runs here. Firefox/WebKit, full accessibility auditing and prolonged
  load/production acceptance are not established.
- Interface language is saved in account settings, but a fresh browser uses its
  local language preference until a settings save. Cross-session tests verify the
  saved preference separately; they do not claim automatic account-locale application.
- Settings currently omits the Sentence rewrite checkbox despite native support.
  Typed/runtime behavior is covered through real saved preferences; the control gap
  remains outside the requested focus entry repair.

The local API image was rebuilt and its existing container recreated with
`python scripts/compose.py up -d --no-deps api`; readiness and installed exception
handling were checked. No migration, dependency restart, production deployment,
credential publication or commit was performed.

## Design hook review

Two rounded-border findings were false positives for underlines on child marked
text inside chat bubbles. The three-dot typing motion is appropriate to the existing
Dialogue question UI. Narrow local detector exceptions are saved for this file.
The two side-accent borders predate this session (verified against HEAD) and were
left standing; this task does not change their design. No visual finding required
a design change. Temporary React internals/stack diagnostics were removed.

## Connected code review

Reviewed study entry callers, save/load conflict handling, cancellation and native
SDK error boundaries; reviewed the submission attachment lifecycle and guest
Library readers against the backend access contract. Existing authenticated
Library requests retain bearer authentication. Anonymous readers cannot edit or
learn, and private node reads remain HTTP 404. Native root-profile navigation and
mock account/adapter contracts cover the final shared-reader change. No known
failing case is concealed or disabled. The final source passes build/type checking
and lint with existing warnings; all owned test processes/stores are cleaned up.
