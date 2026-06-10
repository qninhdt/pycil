# Playwright E2E Tests

Browser-level end-to-end tests for critical user paths in Pycil.

## Prerequisites

- Docker 24+ (for Postgres + Redis backend services)
- Node.js 20+, pnpm
- Backend services running: `docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d postgres redis pycil-core dex`
- Database migrated: `docker compose -f docker-compose.yml -f docker-compose.staging.yml run --rm pycil-core alembic upgrade head`
- Dex reachable at `http://localhost:5556/dex`
- The `docker-compose.staging.yml` overlay is **not** auto-merged (it is no longer named `*.override.yml`); pass both `-f` flags so host ports, CSRF origins, and stub flags apply. Bare `docker compose` uses prod config only.

## Quick start

```bash
# Install Playwright browsers (once)
pnpm exec playwright install chromium --with-deps

# Set required env vars
export AUTH_JWT_SECRET="your-dev-jwt-secret"
export INTERNAL_API_SECRET="your-dev-internal-secret"
export AUTH_URL="http://localhost:3000"
export PYCIL_CORE_INTERNAL_URL="http://localhost:8000"
export OIDC_ISSUER_URL="http://localhost:5556/dex"
export OIDC_CLIENT_ID="pycil-web"
export OIDC_CLIENT_SECRET="pycil-dex-secret-local-only"
export OIDC_PROVIDER_ID="oidc"
export OIDC_PROVIDER_NAME="Dex"

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
│   ├── auth.ts          # Real browser login through Dex OIDC
│   └── db-seed.ts       # Idempotent psql seed: user + pre-enriched deck
├── pages/
│   ├── dex-login-page.ts
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
1. Navigates to `/sign-in`
2. Clicks the OIDC provider button
3. Fills the Dex password form with `e2e-test@pycil.local` / `password123`
4. Saves Playwright `storageState` from the real Auth.js callback

No Google client ID is needed for testing. Dex is the local OIDC provider and production swaps to Google by changing OIDC env vars.

## DB seeding

The `db-seed.ts` fixture inserts a pre-enriched test user and deck using `psql`:
- **User**: `e2e-test@pycil.local`, role `user`
- **Deck**: "E2E Starter Deck" with one term (`ephemeral`) fully enriched (definition, paraphrases, examples)
- **Stats**: Pre-seeded `user_term_stats` row so Learn/Flashcard modes see ready terms

All INSERTs use `ON CONFLICT DO NOTHING` so repeated runs are safe.

## Run profiles

Per-PR CI runs the deterministic profile:

- Real Dex login.
- Pre-seeded definitions/questions for the normal specs.
- `E2E_WORKER_SPECS=false`, so worker-backed specs 07/08 are skipped.

Worker-backed local/nightly runs use:

- `E2E_WORKER_SPECS=true` to enable specs 07/08.
- `WORKER_LLM_STUB=true` for deterministic worker-path testing.
- `E2E_LIVE_LLM=true` plus `WORKER_LLM_STUB=false` for real OpenRouter runs via `apps/web/scripts/run-e2e.sh`.

## Test specs

| # | Spec | Description |
|---|------|-------------|
| 01 | auth-flow | Sign-in page renders; auth user redirected to dashboard |
| 02 | create-deck-and-term | Pre-seeded deck loads; terms page shows "ephemeral" |
| 03 | learn-session | Learn mode loads with pre-seeded enriched terms |
| 04 | flashcard-mode | Flashcard mode loads with pre-seeded enriched terms |
| 05 | explore-page | Explore public decks page loads for auth user |
| 06 | sign-out | Log out clears session → redirects to sign-in |
| 07 | term-enrichment-live | Worker-backed term enrichment path; skipped unless `E2E_WORKER_SPECS=true` |
| 08 | mcq-live-elo | Worker-backed MCQ generation + ELO mutation; skipped unless `E2E_WORKER_SPECS=true` |
| 10 | learn-loop-elo-mutation | Seeded MCQ answer proves DB ELO mutation |

## CI

The `.github/workflows/test.yml` `e2e` job:
1. Spins up Postgres + Redis services
2. Runs Alembic migrations
3. Starts Dex from `infra/dex/config.yaml`
4. Starts `pycil-core` on `localhost:8000`
5. Builds/starts Next through Playwright and runs `pnpm e2e` targeting `http://localhost:3000`
6. Uploads `playwright-report/` on failure

## Divergences from plan

- **Test mode (spec 04)**: Replaced with flashcard mode — the `/decks/[id]/test` route was cut from v1 scope (see `study-modes.tsx:12`).
- **Chat mode (spec 05)**: Replaced with explore page — the `/decks/[id]/chat` route was also cut from v1. The chat components and API exist in pycil-core but have no Next.js page route.
- **LLM chokepoint**: The plan referenced `worker/llm/__init__.py` (empty file). Actual interception points are `invoke_with_fallback` (worker) and `stream_chat` (core).
- **Web in docker compose**: The `web` service is not in docker-compose (runs on Vercel in prod, `next dev` locally). Playwright's `webServer` config boots it separately.
