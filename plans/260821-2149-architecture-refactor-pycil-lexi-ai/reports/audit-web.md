# Audit Report — apps/web (Next.js BFF)

Auditor: Explore agent, 202 unparsed... (condensed from Explore agent report, 2026-08-21)

## Verdict

Disciplined BFF: one enforced API-client convention, pure session machine, well-factored realtime, CI-gated design/type/secret checks. Real debts: copy-pasted auth/assistant route handlers with formatting drift, hand-maintained API types with no CI regeneration, dead boolean props, ~40 duplicated lines in assistant transport hook.

## Module Map (approx)

- `app/` 28 files: `(app)/` Server Component pages + `app/api/*` route handlers (auth ×3 + assistant ×2, SSE proxy). `app/study/*` outside chrome group.
- `components/` 125 files (~11.8K LOC): feature dirs (study 18, library 1... etc.) + `ui/` 35-file shadcn-style registry.
- `lib/` 59 files (~5.3K LOC): `api/` (fetcher/resources/types/error taxonomy), `actions/` (server actions + server-only read modules), `auth/`, `realtime/`, `stores/` (3 vanilla zustand stores behind single provider), `study/session-machine.ts` pure reducer, `assistant/` (SSE frame fold), `design/`, `format/`.
- `hooks/` 5: use-assistant-run 370 (worst), others small.
- `tests/` 36: unit 12, e2e 14 specs + 9 fixtures.

## Data Flow

Three justified fetch patterns: (A) server-only typed fetcher via `lib/actions/*-reads.ts` for Server Components; (B) server actions with `withClient` preamble → `ActionResult` union; (A') route handlers only where browser must be HTTP peer (OAuth, assistant SSE proxy). Study flow: StartSessionPanel → startSession action → redirect → SessionRunner drives pure reducer `lib/study/session-machine.ts`; grading via `useTaskSnapshot` Centrifugo channel; recap via readSession.

## Keep List (do not "improve")

- `lib/api/request.ts` fetcher + double single-flight token refresh.
- error taxonomy + generated codes + CI staleness check.
- session-machine reducer + 493-line unit suite.
- realtime provider + subscribe-async-task manager.
- `ActionResult` union; vanilla zustand + single provider; URL-as-state.
- design-system-audit.mjs (10 mechanical CI-gated rules); bundle-hygiene e2e.
- No react-query (deliberate, documented); hand-rolled SSE frame reader.

## Smells → Refactor Targets

| # | Finding | Evidence |
|---|---| semicolon-styled |
| B1 | BFF route-handler plumbing copy-paste: 5 files duplicate env fallback + auth preamble + proxy loop; 2 assistant routes ~90% identical; formatting drift (semicolons) in auth/assistant routes | `app/api/auth/{login,callback,logout}/route.ts`, `app/api/assistant/threads/[threadId]/{messages,confirm}/route.ts`; `process.env.PYCIL_API_URL \|\| "http://localhost:8000"` ×5 |
| B2 | Hand-written API response types, no CI regen | `lib/api/types/index.ts:1-14` header admits prior drift; snapshot lives under `plans/` |
| B2b | e2e fixtures redeclare wire types | `tests/e2e/fixtures/api.ts` redeclares Node/SenseContent etc. |
| B3 | use-assistant-run send/decide duplicate ~40 lines (abort wiring, phase set, readErrorCode, consume, turn-key) | `hooks/use-assistant-run.ts:170-221` vs `:230-27 subtle |
| B4 | Dead boolean props `advancing`/`retrying` always false at every call site | round-break-panel.tsx:29, exposure-card.tsx, polling-panel.tsx:113; call sites session-runner.tsx:375,386,412 |
B5 | Repeated toast-on-error 3-liner ×~7 files | rename-node-dialog.tsx:61-64, delete-node-dialog.tsx:57, move-node-dialog tables |
| B6 | session-runner.tsx 487 lines, phase switch ~125 lines | weakest candidate; measure before cutting |
B7 | Stale comment "query cache" | app/(app)/layout.tsx:6 |
| B8 | No import-boundary lint | nothing pins components→lib/api internals / feature-to-feature coupling |
| — | Per-render capability probes cost 3-4 upstream calls per node page | documented trade-off, leave |

## Refactor Plan Mapping

B1 → Phase 09; B3/B4/B5/B7/B8 → Phase 09; B2/B2b → tech debt (OpenAPI typegen CI step, post-refactor); B6 optional in Phase 09 if clean.
