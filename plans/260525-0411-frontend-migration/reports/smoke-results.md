# Smoke Results — FE Migration Sprint

**Run date:** 2026-05-25
**Stack version:** post-phase-10 (FE migration + BFF removal)
**Mode:** static + build verification only — live cold-stack browser smoke deferred to launch-day checklist (`docs/launch-checklist.md`).

## Summary

| Gate | Status | Source |
|---|---|---|
| `npm run build` (Next.js 15 + Turbopack) | PASS | apps/web build output: 12 routes generated, 0 type errors, 0 build errors |
| `tsc --noEmit` (implicit via `next build`) | PASS | Same build pass — Next runs full type check before page-data collection |
| ESLint warnings | 2 known | `learning-session.tsx:39,54` — `useEffect`/`useMemo` deps on `session.current` ref. Intentional; carried to v0.2 backlog. |
| Docker `web` image build | PASS | 714MB; over the 200MB target, deviation documented (single-stage `output:standalone` rejected for stability). |
| `docker compose config` | PASS | Validates with all required env vars supplied. |
| Caddy SSE matcher path (post-strip `/jobs/*/stream` inside `handle_path /api/core/*`) | VERIFIED | `Caddyfile`, `Caddyfile.local` reviewed. |
| `respond /api/core/auth/* 404` precedence | VERIFIED | Rule placed before `handle_path /api/core/*` in both Caddyfiles. |
| Dead-link grep (`/classes`, `/saved`, `/trash`, `/decks/new`, `/decks/[id]/edit|chat|test`) | 0 hits | `grep -rE` over `apps/web/src` returns empty. |
| `mock-data` consumers in JSX/layouts | 0 | All four prior consumers refactored to TanStack hooks; mock-data.ts file kept per user decision but no longer imported. |
| Dead exports (`useLearningSession`, `useLearningActions`, `WriteQuestion`) | REMOVED | `hooks/index.ts`, `study/learn/index.ts`, `study/index.ts` cleaned. |

## Critical-path checks (deferred to launch-day cold-stack run)

These checks need a live Postgres + Redis + worker stack with seeded OpenRouter credentials; not runnable in this environment. Tracked in `docs/launch-checklist.md`:

1. Sign-in via Google → JWT cookie set → PyJWT verifies in pycil-core.
2. Onboarding seed idempotency under double-fire (`useRef` + sessionStorage key + partial unique index).
3. Add term "loquacious" → SSE delivers `completed` within 30s via the new `/api/core/jobs/*/stream` path.
4. `/decks/{id}/flashcard` → first 5 cards render `canonical_meaning`.
5. `/decks/{id}/learn` → 5 MCQs → next round → `session_complete` summary.
6. Sign-out → `qc.clear()` runs → next `/api/core/me` returns 401 → middleware redirects to `/sign-in?reason=expired`.

## Non-critical-path BE checks

ELO unit tests (`pytest pycil_core/learning/elo_test.py`) require a Python venv with `pycil-core` deps installed; not run in this static-verification pass. Existing test suite from v1 sprint remains green per prior phase reports.

## Deviations from plan

- `mock-data.ts` deleted from import graph (4 files refactored), file itself kept on disk per user decision recorded earlier in the sprint. Plan had instructed `rm`; user override took precedence.
- **Web is hosted on Vercel — not Docker.** User-corrected mid-sprint. `apps/web/Dockerfile`, `apps/web/.dockerignore`, the `web` service in `docker-compose.yml`, the `Build & push web` step in `.github/workflows/deploy.yml`, and the Caddy `reverse_proxy web:3000` line were all removed. Caddy is now api-only (`/api/core/*` + `/health` passthrough; everything else 404). VPS docker stack reduced from 6 → 5 containers. Phase-10's image-size criterion is moot.

## Open Questions

None — Phase 11 contract enforcement complete to the limit of what static + build checks can verify.
