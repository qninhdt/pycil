# Playwright E2E Tests

Browser-level end-to-end tests for critical user paths in Pycil.

## Prerequisites

- Docker 24+ (for Postgres + Redis backend services)
- Node.js 20+, pnpm
- Backend services running: `docker compose up -d postgres redis pycil-core`
- Database migrated: `docker compose run --rm pycil-core alembic upgrade head`

## Quick start

```bash
# Install Playwright browsers (once)
pnpm exec playwright install chromium --with-deps

# Set required env vars
export AUTH_JWT_SECRET="your-dev-jwt-secret"
export INTERNAL_API_SECRET="your-dev-internal-secret"
export SESSION_COOKIE_NAME="pycil-session"  # dev cookie name (non-secure)

# Seed test data
# (see fixtures/db-seed.ts — idempotent ON CONFLICT DO NOTHING)

# Run the suite
pnpm e2e

# Debug mode (headed, step-by-step)
pnpm e2e:debug
```

## Architecture

```
e2e/
├── fixtures/
│   ├── auth.ts          # JWT cookie injection (bypasses Google OAuth via jose)
│   ├── db-seed.ts       # Idempotent psql seed: test_user + pre-enriched deck
│   └── docker-stack.ts  # docker compose health-check waiter
├── pages/
│   ├── sign-in-page.ts
│   ├── dashboard-page.ts
│   ├── deck-page.ts
│   ├── learn-page.ts
│   ├── flashcard-page.ts
│   └── explore-page.ts
├── tests/
│   ├── 01-auth-flow.spec.ts
│   ├── 02-create-deck-and-term.spec.ts
│   ├── 03-learn-session.spec.ts
│   ├── 04-flashcard-mode.spec.ts
│   ├── 05-explore-page.spec.ts
│   └── 06-sign-out.spec.ts
└── playwright.config.ts
```

## Auth strategy

Tests bypass Google OAuth entirely. The `auth.ts` fixture:
1. Mints a JWT with `jose` using `AUTH_JWT_SECRET` (HS256)
2. Sets it as the session cookie (`pycil-session` in dev / `__Secure-pycil-session` in CI)
3. Browser navigates as an already-authenticated user

No real OAuth flow runs — no Google client ID needed for testing.

## DB seeding

The `db-seed.ts` fixture inserts a pre-enriched test user and deck using `psql`:
- **User**: `e2e-test@pycil.local`, role `user`
- **Deck**: "E2E Starter Deck" with one term (`ephemeral`) fully enriched (definition, paraphrases, examples)
- **Stats**: Pre-seeded `user_term_stats` row so Learn/Flashcard modes see ready terms

All INSERTs use `ON CONFLICT DO NOTHING` so repeated runs are safe.

## LLM cost avoidance

Tests must NOT call OpenRouter. Two mechanisms ensure this:

1. **Worker stub**: `WORKER_LLM_STUB=true` causes `invoke_with_fallback` to return canned responses from `apps/worker/tests/fixtures/llm_responses.json` keyed by schema class name.
2. **Core stub**: `LLM_STUB_MODE=true` causes `stream_chat` to yield a canned chat response without calling OpenRouter.
3. **Pre-seeded data**: The `ephemeral` term is fully enriched in the DB seed — no enrichment needed at test time.

## Test specs

| # | Spec | Description |
|---|------|-------------|
| 01 | auth-flow | Sign-in page renders; auth user redirected to dashboard |
| 02 | create-deck-and-term | Pre-seeded deck loads; terms page shows "ephemeral" |
| 03 | learn-session | Learn mode loads with pre-seeded enriched terms |
| 04 | flashcard-mode | Flashcard mode loads with pre-seeded enriched terms |
| 05 | explore-page | Explore public decks page loads for auth user |
| 06 | sign-out | Log out clears session → redirects to sign-in |

## CI

The `.github/workflows/test.yml` `e2e` job:
1. Spins up Postgres + Redis services
2. Runs Alembic migrations
3. Builds Next.js (`pnpm build`)
4. Runs `pnpm e2e` targeting `http://localhost:3000`
5. Uploads `playwright-report/` on failure

## Divergences from plan

- **Test mode (spec 04)**: Replaced with flashcard mode — the `/decks/[id]/test` route was cut from v1 scope (see `study-modes.tsx:12`).
- **Chat mode (spec 05)**: Replaced with explore page — the `/decks/[id]/chat` route was also cut from v1. The chat components and API exist in pycil-core but have no Next.js page route.
- **LLM chokepoint**: The plan referenced `worker/llm/__init__.py` (empty file). Actual interception points are `invoke_with_fallback` (worker) and `stream_chat` (core).
- **Web in docker compose**: The `web` service is not in docker-compose (runs on Vercel in prod, `next dev` locally). Playwright's `webServer` config boots it separately.
