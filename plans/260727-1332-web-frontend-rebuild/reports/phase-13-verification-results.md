# Phase 13 — Verification and Test Suite: results

Run date: 2026-08-01. Stack: `docker compose` (api, caddy, centrifugo, postgres, redis,
web, worker), single origin `https://localhost`.

## Totals

| Layer | Result |
| --- | --- |
| Vitest (unit) | 86 passed / 86, 6 files |
| Playwright — chromium | 51 passed, 1 skipped (whole suite) |
| Playwright — webkit | 8 passed on the study/quota/realtime set |
| Playwright — mobile-safari | 15 passed, 1 skipped (a11y + generation) |
| Screenshot capture | 6 passed, 36 images |
| Design-system audit | 10/10 clean across 162 files |
| Storybook stories | 13 files |
| API pytest (`tests/learning`) | 75 passed |
| Worker pytest | 30 passed |
| `typecheck` / `lint` / `build` | clean |

The E2E suite runs `fullyParallel: false`, `workers: 1`, `retries: 0`. No retry is
configured on purpose: the async paths here are meant to converge, so a spec that
passed only on a second attempt would be reporting a real defect in recovery.

## Four product defects found by the E2E layer

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

### The activity centre could not be opened at all

Found the moment a credential made the generation tier testable, because nothing had
ever clicked that button. `ActivityCenter` passed a custom component to the trigger's
`render` prop — `render={<ActivityTrigger unsettledCount={n} />}` — and that component
declared only `unsettledCount`. Base UI clones the element it is given and injects the
click handler, the ref and `aria-expanded` onto it; a component that does not spread
its props drops all of them. So the button rendered, took focus, and opened nothing.
Repeated clicks over sixty seconds never mounted the popup, and the panel's own text
appears nowhere in the trace.

Every other `render` in the app hands over a primitive that spreads — `<Link>`,
`<a>`, `<Button>` — which is why this was the only surface affected. The fix follows
the idiom already in `user-menu.tsx`: the trigger is a plain `Button`, and the bell
and its badge are children (`components/activity/activity-center.tsx`).

That makes three surfaces the browser layer found unreachable rather than merely
wrong, all of them invisible to typecheck, lint and the design audit.

### A cold worker failed the grades it happened to run first

Surfaced by restarting the worker to pick up the credential: `grade_answer_v1` began
failing with `NoReferencedTableError: review_log.node_id could not find table 'nodes'`
— and succeeding, in the same second, for other jobs.

The interleaving is the tell. A foreign key is not resolved when its own model is
imported but when a flush sorts the tables, so `ReviewLog` needs `nodes` and `users`
to be registered by the time the first grade is written. The worker's entrypoint
imported `pycil.auth.models` alone, with a comment explaining that the API registers
these through its routers and the worker must do it itself — the same reasoning that
never got extended to `nodes` when grading started writing `ReviewLog`. Whether a
grade succeeded therefore depended on which job the process happened to run first.

`pycil_worker/main.py` now imports `pycil.db.models`, the aggregate module that exists
for exactly this, which closes the class rather than adding a second one-off. Pinned by
`tests/test_worker_registration.py`, which fails with the production error when the
import is narrowed back.

## Three test defects

- **`quota.spec.ts`** resubmitted without retyping. `SessionRunner` keys the draft by
  `senseId:questionId` and derives the field's value from that key, so a refused
  submission leaves the box empty and Submit disabled. The spec now refills before the
  retry.
- **`settings.spec.ts`** raced hydration, and only WebKit was slow enough to show it.
  These inputs are controlled, so a `fill` landing pre-hydration leaves the typed text
  in the DOM while React state still holds the server value — and React's value tracker
  then records that text at hydration, so re-filling the *same* number is deduped and
  `onChange` never fires. Each attempt now clears the field first, inside `toPass`.
- **`study.spec.ts` — the double-advance spec proved nothing and then hung.** Two
  `locator.click()` calls in a row do not double-invoke anything: Playwright serialises
  them, so the second waits for actionability and lands on whatever screen the first
  click produced. The first click advanced past the exposure card onto an assessment,
  which has no advance control at all — and because the default action timeout is
  unbounded, the second click waited out the full 900s test budget instead of failing.
  The trace showed it exactly: the last application request at 18:39:44, then fifteen
  minutes of nothing but CDP heartbeats. `.catch(() => {})` could not help, since the
  promise never settled.

  Fixed by firing both calls from inside the page, where they reach the same handler
  before React can re-render, and by applying it to *every* advance the walk touches
  rather than the first four — the exposure card, the verdict's Continue, and the round
  boundary take different paths into the same reservation. Verified as a real
  double-dispatch (a listener counts 2, not 1) rather than assumed. Runtime went from a
  900s hang to 7.8–12s, and it passes on all three browsers.

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
- **The opt-in generation tier now runs.** A `LEXI_LLM_*` credential was supplied
  after the first pass, so `generation.spec.ts` exists and passes: a real word is
  authored end to end in roughly 22s. It still skips, naming the variables to set,
  when no credential is configured.

  The endpoint is an OpenAI-compatible proxy, and `LEXI_LLM_STRUCTURED_METHOD` has to
  be `function_calling` against it. Probed rather than assumed: asked for a strict
  `json_schema` response it answers 200 with prose, silently ignoring the schema,
  which is precisely the failure `lexi_ai/config.py` documents that setting for. A
  forced tool call returns conforming JSON.

  The spec picks its word at run time — the first headword the dataset knows but has
  no senses for — and the pool has to be headwords rather than obscure words. A word
  the dataset has never heard of resolves to its nearest neighbour ("halcyon" becomes
  "halcyon days"), so it never gains senses under its own name, gets picked again on
  every run, and joins the same finished task forever. That is how this first passed
  and then failed.

## Unresolved questions

- The keyboard-only study spec has never actually executed its assertions in any run
  observed here, because the sampler has not yet served a single-choice question first.
  Seeding a session whose opening question is single-choice would make it real rather
  than conditional.
