# Phase 6 - Web Frontend Bug Hunt Report

Scope: apps/web (Next.js 15 App Router, Auth.js v5, TanStack Query, Shadcn,
TS strict). Gates: tsc --noEmit, eslint, next build, plus adversarial reasoning
over auth/SSE/cache/render flows. Method: 1 domain agent + controller verify.

## Static gate baseline (all were FAILING)

- tsc: exit 1 - blocked by `next-pwa` import (declared in package.json, never
  installed; absent from lockfile).
- eslint: exit 1 - 13 no-explicit-any errors across 4 files + 3 hook-dep warnings.
- next build: exit 1 - lint errors treated as build failures.

## After fixes: all gates green

- tsc --noEmit: 0 errors.
- eslint: 0 errors (3 pre-existing react-hooks/exhaustive-deps warnings left -
  non-blocking, and the session.current mutable-ref pattern is intentional).
- next build: succeeds, 15 routes.
- npm test: 9 pass (orphan test now wired, see below).

## CONFIRMED bugs fixed

### PWA1 (P1-build) - next-pwa breaks tsc + build
- File: next.config.ts:2, package.json:35
- `next-pwa@^5.6.0` declared but never installed (not in lockfile), incompatible
  with Next 15 + Turbopack, AND generates a competing sw.js that would clobber
  the app's hand-written public/sw.js (the real, wired PWA via pwa-register.ts).
- Fix: removed next-pwa wrapper from next.config.ts + dropped the dep. The
  custom service worker is unaffected (next-pwa never ran). Behavior-preserving.

### FE-lint (P2) - 13 no-explicit-any
- Files: lib/pwa-register.ts, lib/offline-answer-queue.ts, profile/page.tsx,
  profile/edit-profile-dialog.tsx + types/domain/user.ts, api-client/auth.ts.
- Replaced `any` with proper minimal interfaces for non-standard browser APIs
  (BeforeInstallPromptEvent, Background Sync Registration). Made CurrentUser
  type accurate (optional gamification fields - deferred feature, API does not
  return them yet; page already defaults them). Typed UpdateMeBody to match the
  backend so the image_url mutation needs no cast.

### FE3 (P2) - dead study-mode links (chat/test) 404
- File: components/study/study-modes.tsx (rendered in every deck layout)
- StudyModes rendered live <Link> to /decks/[id]/chat and /decks/[id]/test, but
  those routes do not exist (build confirms only flashcard/learn). docs/codebase
  -summary.md claims these were removed + "grep -> 0 hits", but the component
  still shipped them - the doc claim was stale.
- Fix: dropped chat + test options (matches v1 scope); grid 4-col -> 2-col.

### FE4 (P3) - legal pages behind auth
- File: middleware.ts:5
- Matcher excluded only api/auth, _next, favicon, sign-in. /legal/privacy and
  /legal/terms were auth-gated -> signed-out users (and OAuth consent links)
  redirected to sign-in. Privacy/ToS must be public.
- Fix: added `legal` to the matcher negative-lookahead.

### FE6 (P2) - Next 15 searchParams Promise read synchronously
- File: app/sign-in/page.tsx
- Next 15 makes searchParams a Promise. The page typed it as a plain object and
  read it synchronously -> callbackUrl + reason/error banners ALWAYS undefined
  -> deep-link callbackUrl ignored after OAuth, banners never show.
- Fix: page is now async, awaits searchParams. Verified by build (PageProps
  validator passes).

## Orphaned test decision (phase-mandated)
- src/lib/quizlet-parser.test.ts used node:test, no runner configured (no test
  script, no vitest/jest dep). DECISION: wire a runner, not delete.
- Added tsx devDep + `"test": "tsx --test src/**/*.test.ts"`. `npm test` -> 9 pass.
- Node built-in --experimental-strip-types could not resolve the extensionless
  .ts import; tsx handles it. tsx pulled only clean esbuild@0.28.0 (no new vulns).

## SUSPECTED / not fixed (need browser/runtime verification or out of scope)
- FE1 (P2): expired session on /api/core/* XHR may return sign-in HTML (307
  followed by fetch) instead of 401 -> garbage cached. Depends on prod proxy
  topology (next.config rewrites only in dev; prod assumes external proxy strips
  /api/core). SUSPECTED, needs prod-like env. ESCALATE.
- FE2 (P2): useBroadcastSync / broadcastInvalidate are DEAD CODE (zero call
  sites) -> cross-tab cache sync non-functional despite infra. Not a regression;
  flag for Phase 7 dead-code pass or wire it. ESCALATE.
- FE5 (P3): non-MCQ payload -> [...undefined] throw in be-question-to-fe adapter;
  caught by error boundary (error screen, not white screen). v1 is MCQ-only.
- FE7 (P3): job-stream-watcher unstable effect deps -> possible double
  invalidate/toast on terminal status. Small window. Needs browser verify.
- FE8 (P3): safeHref permits external http(s) from notification payload; <a>
  lacks rel=noopener. Reverse-tabnabbing risk only (javascript:/data: blocked).

## REFUTED
- Sign-out cache leak: qc.clear() runs BEFORE signOut(). Correct.
- Open-redirect via callbackUrl: safeCallbackUrl rejects non-/ , // , /\. Safe.
- Protected /dashboard /learn reachable unauthenticated: matcher covers them.
- EventSource leak on unmount: use-jobs cleanup closes source. No leak.
- SameSite: config is "lax" (required for OAuth callback), not a bug.

## Residual: pre-existing npm audit findings (NOT introduced here, out of scope)
- next (RCE/DoS advisories), swiper (prototype pollution), postcss (XSS) -
  fixes require breaking major bumps (npm audit fix --force). Out of this
  behavior-preserving audit's scope. ESCALATE as a dependency-upgrade task.
