# Web Frontend Rebuild onto the Shipped API Contract

**Date**: 2026-07-28
**Severity**: High (14-phase cross-cutting rebuild: contract, frontend, tests, docs)
**Component**: `apps/web` (presentation + data layer), `apps/api` (contract additions), docs
**Status**: Resolved for every stack-independent gate — unit + design-system audit +
Storybook + build + CI green. The live-stack E2E layer was subsequently stood up
against `docker compose`: auth, library, and the study loop pass (17 specs), and
they found four real defects the stack-independent gates could not — see
"Defects the browser found" below. Screenshot capture and the remaining
accessibility, quota, and bundle-hygiene specs are still outstanding.

## What Happened

Executed the 14-phase plan to rebuild the tracked web app on the shipped Pycil
API. The backend contract was completed and corrected (phases 2–4), the frontend
torn down to its retained BFF/auth/realtime layer and rebuilt screen by screen
(phases 5–12), and the verification harness plus docs brought into line (phases
13–14).

Final gate on the stack-independent slice: web `typecheck` / `lint` / `build`
clean, 86 Vitest unit tests passing, the ten-check design-system audit clean
across 162 files, `build-storybook` green with 86 stories, and a `test-web` CI job
wired alongside `uv sync --locked` on every Python job. Backend 292 pytest
passing.

## The Brutal Truth

Five plan or scouting assumptions were wrong, each in a way a typecheck could not
see:

1. **`GET /v1/me` and `/v1/capabilities` were reported missing during scouting.**
   They existed. Building replacements would have forked the viewer contract.

2. **The deck-settings endpoint had been a no-op since it was written.** Session
   shape belongs to the learner, not the deck, so a folder session ignored the
   deck value entirely and a per-deck write applied about half the time. Fixed by
   moving settings onto a `UserLearningSettings` row (migration
   `0019`) — a behaviour fix, not a frontend one.

3. **`components.json` lacks a `base` key.** A naive shadcn regeneration would have
   silently swapped Base UI for Radix, because the registry defaults to Radix when
   `base` is absent. Caught before regenerating.

4. **`restore_delivered` permanently wedged a sense after any aborted answer.** The
   reopen path never restored the delivery claim, so an abandoned question could
   never be re-served. Fixed in the session store.

5. **"The API always emits camelCase" was false.** `RunEventRead` and the study
   reveal payloads pass the dictionary's own snake_case through verbatim. The
   assistant token payload is `{content}`, not a bare string, so an early revision
   rendered `[object Object]` on every streamed token; and `RunEventRead` 500'd
   until `AliasChoices` + `from_attributes` were added. Typecheck was green
   throughout because `lib/api/types` is hand-authored, not generated.

## Technical Details

- **Assistant transport** is SSE, not Centrifugo, and the API cannot resume a live
  `RUNNING` run: `GET .../messages` and the run query endpoint both replay
  persisted rows and close. The `Last-Event-ID` resume the plan assumed does not
  exist, so recovery re-reads the thread and offers a resend. A mid-stream
  disconnect raises `GeneratorExit` (a `BaseException`), which escapes the run's
  `except Exception` handlers — so an interrupted run stays `RUNNING` with its work
  abandoned and is never reaped. Recorded as a backend follow-up.

- **Per-run sequence collision.** The event `sequence` is per-run, so every turn
  restarts at 1; keying dedupe on `sequence` alone dropped later runs' events as
  duplicates. Fixed by keying on `(runId, sequence)`, with a regression test.

- **The design-system audit script had a bug that made it pass vacuously.** The
  first comment-stripper blanked string *contents*, but Tailwind classes and hex
  colours live inside strings, so every class/colour rule matched nothing. Rewrote
  it to strip comments (block-aware, file-wide) while keeping strings. Running the
  corrected gate surfaced three real drifts: a serif `Assistant` panel heading
  (chrome, not lexical content), an undefined `--radius-xs` token silently falling
  back to Tailwind's 2px, and the previously-hidden hex in the error boundary and
  `themeColor` meta (both legitimate, now narrowly exempted).

- **A phase-7 file had to be restructured with approval.** The desktop assistant
  needed an in-flow sticky sidebar, which meant editing `app-shell.tsx` — a file the
  plan placed in a completed phase. Escalated and approved rather than patched
  around.

## Verification

- `pnpm --filter web typecheck | lint | build | test:unit` all clean; 86 unit
  tests over the session reducer, error taxonomy, snapshot reconciliation, mastery
  mapping, the assistant transcript fold, and the SSE frame parser.
- `pnpm --filter web audit:design` — 10/10 clean; `build-storybook` green.
- Backend: 292 pytest passing (289 baseline + 3 new contract tests); the new tests
  were confirmed red at `HEAD` before the fixes landed.
- `node .claude/scripts/validate-docs.cjs docs/` and `wc -l docs/*.md` checked in
  the phase-14 close.
- Live stack: 17 Playwright specs green against `docker compose` on
  `https://localhost` — auth (7), library (5), study (5), the last of which walks a
  real session to its recap and settles a free-text grade over SSE.

## What the Live Stack Found

Every gate above was green while three defects sat in the product, because none of
them is reachable without a browser against a real stack.

1. **No async verdict could reach any client.** `channel.proxy.subscribe` needs
   `include_connection_meta`, which defaults to off, so Centrifugo never forwarded
   the JWT `meta` that `authorize_subscription` reads — every subscribe was denied
   with code 103. Free-text grading, word generation, and the activity centre were
   all inert. Now asserted in `test_channels_tokens.py`.
2. **Level-3 cloze was unanswerable.** The generator fills `word_bank` only at
   level 2 (free recall is the point at level 3), but `TextSpanQuestion` rendered
   nothing but that bank, so a high-mastery learner met an empty toggle group and a
   permanently disabled Submit. It now falls back to a typed input.
3. **The dashboard shipped without an `h1`.** Caught by the accessible-name
   assertion, invisible to the design audit.

Two further findings were mine, not the product's, and both were disproven by
evidence rather than argued: a suspected missing proxy header (the secrets hashed
identically) and a suspected write-order race (task, interest, and event share one
transaction and one millisecond).

## Unresolved

- Spec coverage is not complete. Specified in phase 13 but **not written**: quota
  exhaustion, the add-word warning, deck settings, the generation tier, the axe and
  keyboard a11y runs, the mobile/desktop screenshot set, the bundle-hygiene
  secret-leak check, and the Centrifugo-restart recovery case. What exists is auth
  (7), library (5), and the study loop (5).
- E2E stays off the PR gate — it needs the full compose stack plus an LLM
  credential — and belongs on a nightly job. That job is not wired yet.
- Only Chromium has been run. The WebKit project is configured but unexercised.
- `fixtures/schedule.ts` reaches into the database through `docker compose exec`
  because no endpoint sets `next_review_date` or `mastery`. It is the suite's one
  documented exception to API-only seeding; an internal test-only endpoint would
  remove it.
- The abandoned-`RUNNING`-run reaper is a recorded backend follow-up, not done.
