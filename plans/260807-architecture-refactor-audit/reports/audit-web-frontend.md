# Audit: Web Frontend Architecture (apps/web)

**Date:** 2026-08-07
**Stack:** Next.js 16 App Router BFF, 216 TS/TSX files, 18,944 LOC
**Scope:** data-fetching, BFF token boundary, type contracts, state machines, component architecture, cross-language drift, AI-patchwork smells

---

## 1. Data-fetching & mutation mechanisms

Four mechanisms, all justified:

| Mechanism | Location | Role |
|-----------|----------|------|
| **Server-only read functions** (`import "server-only"`, not actions) | `lib/actions/dashboard.ts:20`, `lib/actions/library-reads.ts:42`, `lib/actions/progress-reads.ts:46`, `lib/actions/settings-reads.ts:20` | Awaited at render time by page/layout server components |
| **Server actions** (`"use server"`) | `lib/actions/nodes.ts`, `study.ts`, `words.ts`, `learning-settings.ts`, `account.ts`, `assistant.ts` | All mutations. Funnel through `withClient()` (`lib/actions/authorized-action.ts:31`) |
| **Route handlers** | 5 files under `app/api/` | 3 OAuth (login/callback/logout) + 2 assistant SSE proxies |
| **Client `fetch()`** | `hooks/use-assistant-run.ts:190`, `:243` | Only to the two SSE route handlers — server actions cannot return a streaming body (stated at `lib/actions/assistant.ts:14`) |

Both server paths share one exit: `createApiClient(session)` → `createFetcher(session)` → `apiFetch` (`lib/api/request.ts:117-164`). No SWR, no TanStack Query, no client-side cache to reason about.

Client state is three Zustand stores created once per `StoreProvider` mount (`lib/stores/store-provider.tsx:23-29`): `assistant-store.ts` (195 LOC), `activity-store.ts` (180), `ui-store.ts` (63).

Cache invalidation is `revalidatePath` at 15 sites in `lib/actions/nodes.ts`, `words.ts`, `learning-settings.ts` — always guarded on `result.success`. Consistent.

**Verdict: coherent, no standardisation needed.**

---

## 2. BFF token boundary — holds

Enforcement is structural, not conventional:

- `lib/api/request.ts:1` and `lib/api/client.ts:1` — `import "server-only"`. A client component importing either is a **build error**.
- `lib/auth/session.ts:52-56` — JSDoc: the session object carries both tokens and "must never be passed to a client component or returned from a server action: either would serialise both tokens into the RSC payload as plaintext."
- `lib/auth/viewer.ts:14-19` — `ViewerSummary` strips the token fields; `app/(app)/layout.tsx:20` calls `toViewerSummary(session)` before handing anything to `AppShell`.
- `tests/e2e/specs/bundle-hygiene.spec.ts:87-187` — scans built JS bundles **and** rendered HTML of authenticated pages for `PYCIL_API_URL`, secrets, and `"Bearer "`.

The SSE route handlers read `session.accessToken` from the sealed cookie server-side and set the header themselves (`app/api/assistant/threads/[threadId]/messages/route.ts:19-23`). The token value never crosses to the client.

One documented trade-off, not a gap: `ensureAccessToken` (`lib/api/request.ts:51-94`) swallows a re-seal failure during RSC render, because Next.js forbids cookie writes there. The fresh token still serves the current request; the next action or route handler seals it (`persistSession`, `request.ts:104-115`).

### Finding W1 — `PYCIL_API_URL` fallback duplicated 5×

`apiBaseUrl()` (`lib/api/request.ts:27-29`) is module-private. The identical expression is re-typed at:

- `app/api/auth/callback/route.ts:12`
- `app/api/auth/login/route.ts:11`
- `app/api/auth/logout/route.ts:5`
- `app/api/assistant/threads/[threadId]/messages/route.ts:19`
- `app/api/assistant/threads/[threadId]/actions/[actionId]/confirm/route.ts:19`

`NEXT_PUBLIC_APP_URL || "http://localhost:3000"` is duplicated 3× the same way (`callback/route.ts:13`, `login/route.ts:12`, `logout/route.ts:6`).

All five call sites are server-side, so exporting `apiBaseUrl` from `request.ts` (already `server-only`) and importing it is safe. Six copies of a fallback host is how a staging deploy ends up pointing one route at localhost.

### Finding W2 — auth guard duplicated in the two SSE handlers

`messages/route.ts:9-13` and `confirm/route.ts:9-13` each hand-roll the same 5-line "no session → 401 JSON" block. The server-action path centralises this in `withClient` (`lib/actions/authorized-action.ts:25-30`, returning `{success:false, code:"not_authenticated"}`), and `lib/api/handle-api-error.ts:13-14` redirects on a 401 `ApiError`. Three shapes of the same decision. Low priority at two handlers, but it is the place a third streaming endpoint will copy from.

---

## 3. Type contracts: what is generated, what is not

**Error codes ARE generated and CI-enforced.** `lib/api/error-codes.generated.ts:1-4` — "Generated from apps/api by scripts/extract-error-codes.py. Do not edit. Source revision: 8b0178a." CI runs the extractor and diffs (`.github/workflows/test.yml:72-74`); a stale file fails the build.

`ERROR_TAXONOMY: Record<ApiErrorCode, ErrorTaxonomyEntry>` (`lib/api/error-taxonomy.ts:50`) is keyed by the generated union, so a new backend error code without a taxonomy entry is a **compile error**. `tests/unit/error-taxonomy.test.ts:36-43` adds a runtime check on top. This is the right pattern; 13 components consume the taxonomy.

**Response shapes are NOT generated.** `lib/api/types/index.ts:7-14` — every type was hand-written against a fetched `GET /v1/openapi.json`, archived at `plans/…/v1-openapi-snapshot.json`. The snapshot is an archive, not a pipeline input; `scripts/` has `extract-error-codes.py` but no type generator. Two known schema inaccuracies are documented and hand-corrected at `lib/api/types/learning.ts:1-15`; `Reveal` (`learning.ts:241-249`) and the SSE payloads (`types/assistant.ts:60-82`) are flagged as cases where the document lies.

**Residual risk:** TypeScript catches shape mismatches that reach a call site. It cannot catch a backend field that became optional or was removed while the TS type still declares it present — that compiles clean and reads `undefined` at runtime. Severity medium-low: the snapshot plus documented corrections plus strict TS catch most of it. Fix the OpenAPI document's accuracy *before* introducing codegen, or codegen will just enshrine the two known lies.

---

## 4. Cross-language drift — the real exposure

Three contracts are defined in Python and re-declared in TypeScript. None has a test that fails when the Python side changes.

### Finding W3 — async-task envelope mirrored by hand (highest risk)

Python defines the envelope in `task_snapshot()` at `apps/api/pycil/tasks/application/service.py:75-88`. TypeScript mirrors it at `lib/realtime/task-snapshot.ts:3-12` with a genuine runtime validator (`isAsyncTaskSnapshot`, `:31-46`) checking `schema === "async-task.v1"` and every field's type.

The validator is good — and it stops at `result: Record<string, unknown> | null`. The inner grading payload comes from `packages/shared-py/shared/realtime/payloads.py` `GradingResult.to_dict()`, and TypeScript reads it by string key in `lib/study/grade-snapshot.ts:68-74`: `result?.isCorrect`, `result?.gradeScore`, `result?.gradeFeedback`, `result?.reveal`, `result?.masteryBefore`, `result?.masteryAfter`.

Every read is defensive (`asBoolean`, `asNumber`, `asString` → `null` on mismatch). So renaming `gradeScore` on the Python side produces **a silently null verdict**, not an error: no exception, no TS error, and `tests/unit/task-snapshot.test.ts` keeps passing because it asserts against hand-written fixtures in the same repo. The learner sees a blank score after answering.

There is also a **dead duplicate** of the envelope: the Pydantic `AsyncTaskSnapshot` at `apps/api/pycil/tasks/domain/schemas.py:10` has no importers — the wire envelope is built by the dict-returning `task_snapshot()` instead.

### Finding W4 — channel name built in both languages

`packages/shared-py/shared/realtime/channels.py:12` returns `f"async:{task_id}"`; `lib/realtime/subscribe-async-task.ts:35` builds `` `async:${taskId}` `` as a TS template literal. Unavoidable across the language boundary. Mitigated on the Python side: authorization never parses ownership out of the channel name — it is opaque, and `apps/api/pycil/realtime/application/subscriptions.py:45-98` authorizes purely by `AsyncTaskInterest` row lookup, failing closed on any parse error. Correct design; the string itself is still two copies.

### Finding W5 — mastery bands mirrored, and the test cannot catch drift

`lib/design/mastery.ts:24-30` declares five bands with names and inclusive bounds. `apps/api/pycil/policy/policy.py:50-56` (`LEVEL_PROFILES`) and `:86` (`STAGE_NAMES`) declare the same five. Both files carry comments acknowledging the mirror (`mastery.ts:1-11`, `policy.py:78-85`).

Python guards itself well — `MASTERED_FLOOR = LEVEL_PROFILES[-1].lo` (`policy.py:95`) is derived, never a literal, and a stage-name/band count mismatch raises at import (`policy.py:88-91`).

`tests/unit/mastery.test.ts` is thorough about *TypeScript-side* correctness: contiguity, every inclusive edge, the classic boundaries (10/11, 30/31, 55/56, 80/81), rounding, clamping, NaN. But every expectation is a literal in the same repo. If the API moves a band edge, this test still passes.

This matters because **both sources render on the same screens**: a deck row shows the server's `masteryStageName` while the dashboard and study verdict resolve the name locally through `masteryBand()` (7 callers, `components/vocabulary/mastery-stage.tsx:33`, `components/progress/mastery-distribution.tsx`). Divergence shows one learner two labels for one score — exactly what the comment at `mastery.ts:6-10` warns about.

---

## 5. Session machine — a real state machine

`lib/study/session-machine.ts:37-64` — `Phase` is an explicit discriminated union: `advancing | asking | break | preparing | settling | stalled | finished | stopped`.

Exhaustiveness is compile-enforced twice: `sessionReducer` (`:136-175`) ends `default: return assertNever(event)`, and `applyNext` (`:178-219`) ends `assertNever(next)` over all five `NextQuestionState` values (`assertNever` at `lib/api/types/learning.ts:279`). A new event or supply state without a handler does not compile.

`tests/unit/session-machine.test.ts` — 493 LOC, 25+ cases: all five `next_received` states, `poll_again` vs `advance` counter distinction, `supply_settled`, answer lifecycle (graded/pending/failed), `next_failed`, `answer_failed`, `canSubmit`, backoff, a full session walk.

`components/study/session-runner.tsx` (487 LOC) is the effect layer and respects the boundary — `:50-55`: "Every decision lives in the reducer. The effects here do I/O and dispatch the result." Effects at `:129-132`, `:153-163`, `:167-173` each guard on `phase.kind` first. No phase logic duplicated.

**487 LOC is earned**, not bloat: it is a dispatch table over ~12 render cases, each delegating to a different component.

### Finding W6 — three hardcoded `false` props

- `session-runner.tsx:375` → `retrying={false}` on `StalledPanel`
- `session-runner.tsx:386` → `advancing={false}` on `RoundBreakPanel`
- `session-runner.tsx:412` → `advancing={false}` on `ExposureCard`

The props are real and wired to `disabled` on the child's action button: `components/study/polling-panel.tsx:99,104,109,112` (`retrying`), `components/study/round-break-panel.tsx:21,26,47` and `components/study/exposure-card.tsx:24,28,52` (`advancing`). The only caller passes a literal `false`, so the disable can never fire.

Two readings, and the audit cannot pick between them from the code alone: either the reducer already covers the in-flight case (making the props dead and removable) or the button genuinely lacks a pending state and a fast double-click double-submits. `session-runner.tsx:112-125` does hold an `advancing` ref for the advance path, which suggests the first — the ref guards re-entry, so the prop is redundant. Confirm against the reducer before removing.

---

## 6. Assistant architecture — the split is earned

| File | LOC | Job |
|------|-----|-----|
| `lib/stores/assistant-store.ts` | 195 | Conversation state across the viewport breakpoint |
| `hooks/use-assistant-run.ts` | 368 | Transport: POST a turn, read the SSE body, fold frames |
| `lib/assistant/transcript.ts` | 326 | Pure fold of `RunEvent[]` → displayable transcript |
| `components/assistant/assistant-surface.tsx` | 289 | Renderer |

The store exists for a concrete reason (`assistant-store.ts:1-16`): drawer and sidebar are mutually exclusive by viewport, so `useState` in either is lost when the breakpoint crosses. `transcript.ts` is shared by the streamed and the replayed paths, which is why it is pure.

`AssistantTransport` (`assistant-store.ts:65-69`) holds `abort`, `turnKey`, `loadedThreadId`, `listLoaded` as **deliberately mutable, non-reactive** fields — mutated directly (`:94-101`) rather than through a setter. That is correct for an abort controller (a re-render on every abort swap would be noise) but it is the one place in the store where the "state is immutable" assumption does not hold. Worth a comment if one is not already there.

The no-unmount-cleanup decision is documented and correct (`use-assistant-run.ts:52-56`): the open stream is cancelled when the *provider* unmounts, not when a surface does, because a surface unmounting **is** the breakpoint crossing the store exists to survive. `loadedThreadId` (`:64-68`) makes the thread-change abort fire once per thread rather than once per mount, so a remount mid-turn cannot abort the live stream and overwrite its events with the server's copy. The cleanup that does exist (`:110-112`) only flips a local `active` flag. There is a `resetTurn` escape hatch at `:334-339`.

**Leave as-is.**

---

## 7. Container/presentational — consistent

Components do not fetch. Data arrives as props from server components or is read from a store. Server actions invoked from client components (`session-runner.tsx` calling `advanceSession`/`submitAnswer`) is the idiomatic Next.js 16 pattern, not a leak.

Date formatting is genuinely centralised — `lib/format/` holds one file, `date.ts`. The four remaining inline calls are not date formatting: three are `Number.toLocaleString()` on character counts (`components/assistant/assistant-composer.tsx:82,99`) and a chart value (`components/ui/chart.tsx:258`); the fourth is a comment in `components/dashboard/forecast-strip.tsx:6`. That comment documents a deliberate choice worth preserving: weekday initials are a hardcoded `WEEKDAY_INITIALS` table (`:18`) precisely *because* server-side ICU locale and browser locale disagree for non-en-US visitors, producing a post-hydration text flash that CI cannot catch (both sides run the same locale). Two tests defend this: `tests/unit/date-format-locale-stability.test.ts`, `tests/unit/forecast-weekday-locale-stability.test.ts`.

---

## 8. Other smells

**W7 — `lib/api/error-taxonomy.ts` (360 LOC) mixes data and logic.** `ERROR_TAXONOMY` (`:50`) is ~300 lines of hand-written declarations (categories and messages need human judgment — correctly not generated). `classifyErrorCode` and `isRetryable` (`:357`) are the logic. Splitting into `error-taxonomy-data.ts` + `error-classifier.ts` brings both under 200 LOC per the repo's own rule. Purely mechanical.

**W8 — `components/ui/chart.tsx` (373 LOC)** is the vendored shadcn Recharts wrapper. Verify it is unmodified from upstream before any refactor touches it; if it is unmodified it is not this codebase's debt.

**W9 — `unsubscribe_channel` (`apps/api/pycil/ports/centrifugo.py:66`) has no non-test callers.** The terminal-task path uses `_clamp_interests_to_grace` instead. Dead port method (backend-side, noted here because it surfaced tracing the realtime contract).

### Checked and clean

- No prop-drilling chain that wants a context.
- No two components doing the same job.
- No `any`/`as` casts hiding domain gaps in the study or assistant paths.
- 35 `components/ui/*` files, 12 feature directories — flat, no speculative nesting.
- Design system: `lib/design/` (layers, mastery, motion) + `tokens.generated.css` + `scripts/design-system-audit.mjs` enforcing 10 mechanical rules at build time. Correct pattern.
- Test coverage: 10 unit suites, 13 Playwright specs including `bundle-hygiene`, `realtime-recovery`, `a11y`, `quota`.

---

## 9. Effort / risk

| # | Finding | Size | Risk | Covered by | Independent |
|---|---------|------|------|-----------|-------------|
| W3 | Contract test: Python `GradingResult.to_dict()` keys ↔ `grade-snapshot.ts` reads. Delete dead `AsyncTaskSnapshot` at `tasks/domain/schemas.py:10` | S | Low | nothing today | Yes |
| W5 | Contract test: API-served band edges ↔ `MASTERY_BANDS`, or serve the table from the API | S | Low | TS-side only | Yes |
| W1 | Export `apiBaseUrl` from `request.ts`; replace 5 copies (+3 `NEXT_PUBLIC_APP_URL`) | XS | Low | e2e auth + bundle-hygiene | Yes |
| W7 | Split `error-taxonomy.ts` into data + classifier | S | Low | `error-taxonomy.test.ts` | Yes |
| W6 | Resolve the three `={false}` props — remove, or wire the pending state | XS | Low | `session-machine.test.ts`, `study.spec.ts` | Yes |
| W2 | Extract the SSE-handler auth guard into one helper | XS | Low | `assistant-breakpoint.spec.ts` | Yes |
| W9 | Delete `unsubscribe_channel` | XS | None | n/a | Yes |
| W4 | Keep the two channel builders; add a parity assertion | XS | Low | partial | Yes |
| W8 | Verify `chart.tsx` matches shadcn upstream | XS | None | n/a | Yes |
| — | Codegen `lib/api/types/*` from OpenAPI | L | **Med** | vitest + Playwright | **No** — blocked on fixing the OpenAPI document's two known inaccuracies first |

All items except the last are independent and touch disjoint files. W3 and W5 are the two that buy real safety; everything else is hygiene.

---

## 10. Fine as-is — do not touch

- Data-fetching architecture: one `Fetcher`, server-only reads, server actions, 5 justified route handlers.
- BFF token boundary: `server-only` compile enforcement + `toViewerSummary` stripping + bundle-hygiene e2e scanning both bundles and rendered HTML.
- Error-code pipeline: generated, CI-diffed, compile-enforced against the taxonomy.
- Session reducer: discriminated union with `assertNever` on both switches, 493 LOC of tests.
- `session-runner.tsx` at 487 LOC: a dispatch table, not a god component.
- Assistant 4-file split, including the mutable `AssistantTransport` and the no-unmount-cleanup decision.
- Locale-stable date formatting and its two regression tests.
- Design-token codegen + audit script.
- Realtime authorization: opaque channel names, single DB-backed enforcement point, fails closed.

---

## Unresolved questions

1. **W6** — do the three `={false}` props reflect a reducer that already prevents the in-flight case (making them dead code), or a genuinely missing pending state? The `advancing` ref at `session-runner.tsx:112-125` suggests the former, but confirming needs a reducer read that this audit did not complete.
2. **Who owns `plans/…/v1-openapi-snapshot.json`?** It has two known inaccuracies (`lib/api/types/learning.ts:1-15`). Nothing refreshes it, and codegen cannot start until it is accurate.
3. **W5 direction** — should the API serve the mastery band table (one source, runtime cost) or should a contract test assert the two tables match (two sources, CI cost)? Product call: the bands are stable enough that a test may be the cheaper answer.
4. **W8** — is `components/ui/chart.tsx` unmodified from shadcn upstream? Not verified; a diff against the registry version would settle it.
