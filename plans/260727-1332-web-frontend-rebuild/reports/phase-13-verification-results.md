# Phase 13 — Verification and Test Suite: results

Run date: 2026-08-01. Stack: `docker compose` (api, caddy, centrifugo, postgres, redis,
web, worker), single origin `https://localhost`.

## Totals

| Layer | Result |
| --- | --- |
| Vitest (unit) | 86 passed / 86, 6 files |
| Playwright — chromium | 38 passed, 1 skipped |
| Playwright — webkit | 38 passed, 1 skipped |
| Playwright — mobile-safari | 38 passed, 1 skipped |
| Screenshot capture | 6 passed, 36 images |
| Design-system audit | 10/10 clean across 162 files |
| Storybook stories | 13 files |
| API pytest (`tests/learning`) | 75 passed |
| `typecheck` / `lint` / `build` | clean |

The E2E suite runs `fullyParallel: false`, `workers: 1`, `retries: 0`. No retry is
configured on purpose: the async paths here are meant to converge, so a spec that
passed only on a second attempt would be reporting a real defect in recovery.

## Two product defects found by the E2E layer

Both were found because the specs run against the real stack, and both were fixed in
product code rather than worked around in the test.

### The live-session warning could never fire

`SessionRunner` published `liveSession` on mount and cleared it in the effect's
cleanup. But the palette — the only surface that offers an add — is mounted in
`AppShell`, and `/study/[sessionId]` renders no shell by design. So leaving the study
screen to reach an add unmounted the runner, which cleared the store, which meant
`CommandPalette` and `DeckItemList` always saw `liveSession: null`. The warning, its
dialog, and the store seam were unreachable code.

The fix is in the lifecycle, not the mounting. A session does not end when the learner
walks away from the screen: the Redis meta stands until the session completes or
expires, and `/study/{id}` resumes it. So publication now outlives the screen and is
cleared when the session actually reaches `finished` or `stopped`
(`components/study/session-runner.tsx`).

Mounting the palette inside `/study` was tried first and rejected: `POST
/v1/decks/{node_id}/senses` takes a deck, and `liveSession.nodeId` may be a folder, so
a palette opened mid-session has no valid add target.

### A spent grading quota wedged the question it refused

`consume_delivered` clears `current_qid` before the rubric branch is reached, so by the
time `take_grading_slot` refuses, the delivery claim is already spent. The `bind_held`
flag protected nothing: the retry failed `consume_delivered` and came back as
`question_not_issued_for_session` — a session-desync code shown to someone who had
merely hit a rate limit, and one the client recovers from by polling `/next` and
discarding the answer they had typed.

`submit_answer` now re-arms that exact question id before raising
(`apps/api/pycil/learning/router.py`). Not `restore_delivered`, which reopens the whole
delivery and brings the sense back as a *different* question later — correct for a
genuinely aborted answer, wrong when the learner is still looking at this one.

Verified end to end rather than by reading: free-text responses went 7 → 8 across the
quota run and a `grading` async task succeeded, so the rubric path really executed.

## Two test defects

- **`quota.spec.ts`** resubmitted without retyping. `SessionRunner` keys the draft by
  `senseId:questionId` and derives the field's value from that key, so a refused
  submission leaves the box empty and Submit disabled. The spec now refills before the
  retry.
- **`settings.spec.ts`** raced hydration, and only WebKit was slow enough to show it.
  These inputs are controlled, so a `fill` landing pre-hydration leaves the typed text
  in the DOM while React state still holds the server value — and React's value tracker
  then records that text at hydration, so re-filling the *same* number is deduped and
  `onChange` never fires. Each attempt now clears the field first, inside `toPass`.

## Screenshots

36 images in `reports/screenshots/`: 9 screens × 2 themes × 2 viewports (390×844 and
1440×900). Screens: today, library, deck, sense, progress, settings, study-start,
study, login.

Captured through `emulateMedia({colorScheme, reducedMotion: "reduce"})` on the page
rather than `test.use`, because the learner-scoped fixtures build their own context and
would not receive a project-level option. `colorScheme` is the real input: the app runs
`defaultTheme="system"` with `enableSystem`, so seeding the `next-themes` storage key
would exercise a path a first-time visitor never takes.

The capture waits on each screen's own `h1`, not `networkidle`. Every signed-in screen
sits inside the shell, which holds an SSE connection to Centrifugo for as long as it is
mounted, so the network is never idle and that wait could only ever time out — which is
exactly how it first failed.

These are evidence, not assertions. No baseline comparison: a golden-image suite on a
design system this new would fail on every intentional change and tell a reviewer
nothing.

## Skipped, with reasons

- **`a11y.spec.ts` — "answers a study question using only the keyboard"** (1 skip per
  browser, 3 total). The digit shortcuts apply to single-choice, and the round did not
  open on one. Which format is served is the sampler's decision; this test is about the
  keyboard, so it skips rather than fails. The guard is at `a11y.spec.ts:182`.
- **The opt-in generation tier (step 10) is not implemented.** `LEXI_LLM_API_KEY` is
  empty in this environment, so a word-generation spec would have nothing to assert
  against. Question supply and rubric grading both work here — supply warmed on every
  run — so this gap is specific to generating a *new* word, not to the model paths in
  general.

## Unresolved questions

- Step 10's generation-tier spec still needs writing, and needs an environment with a
  populated `LEXI_LLM_*` credential to be meaningful.
- The keyboard-only study spec has never actually executed its assertions in any run
  observed here, because the sampler has not yet served a single-choice question first.
  Seeding a session whose opening question is single-choice would make it real rather
  than conditional.
