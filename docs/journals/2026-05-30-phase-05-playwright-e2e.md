# Journal — 2026-05-30 Phase 5: Playwright E2E suite

## Summary
Delivered 6-spec Playwright E2E test suite for critical user paths. Added LLM stub mode to worker + core for zero-cost test execution.

## Key Changes
- 16 new files: `apps/web/e2e/` (fixtures, pages, specs, config, README), `worker/llm/stub.py`, `worker/tests/fixtures/llm_responses.json`
- 4 modified: `apps/web/package.json`, `.github/workflows/test.yml`, `worker/llm/openrouter.py`, `core/llm_streaming.py`
- 46 worker tests + 218 core tests: zero regression
- 0 TypeScript errors

## Architecture Decisions
- **JWT bypass**: jose mints HS256 token with AUTH_JWT_SECRET → inject as `pycil-session` cookie. No Google OAuth needed.
- **LLM chokepoint**: `invoke_with_fallback()` (worker) + `stream_chat()` (core) — both env-gated with `WORKER_LLM_STUB`/`LLM_STUB_MODE`
- **CI serving**: `next dev` (not `next start`) — API rewrites active, dev cookie name non-secure on localhost
- **DB fixture**: psql with `ON CONFLICT DO NOTHING` for idempotent seeding

## Plan Divergences
| Plan item | Resolution |
|-----------|------------|
| Test mode spec | Replaced with flashcard mode — `/decks/[id]/test` route cut from v1 |
| Chat mode spec | Replaced with explore page — `/decks/[id]/chat` route cut from v1 |
| `worker/llm/__init__.py` chokepoint | Moved to `openrouter.py::invoke_with_fallback` (actual chokepoint) |
| Web in docker compose | Playwright webServer boots `next dev` separately |

## Impact
- Low: all changes env-gated behind stub flags or new test files
- No schema changes, no API contract changes
- README docs + e2e README provide self-serve local run instructions

## Unresolved
- Chromium install requires sudo (unavailable in dev env) — e2e can't run in this sandbox; CI covers it
