#!/usr/bin/env bash
# Reproducible E2E runner against the REAL stack (real Dex login, no minted cookie).
#
# With real OIDC login the host web now does three things the old minted-cookie
# fixture never did, and all three need secrets that match the running core:
#   1. SIGNS the session JWT with AUTH_JWT_SECRET (core then VERIFIES with its own
#      AUTH_JWT_SECRET — mismatch → every API call 401s).
#   2. Calls core's /auth/upsert-user on first login with x-internal-secret
#      (must equal core's INTERNAL_API_SECRET — mismatch → login 500s, no row).
#   3. Runs the OIDC discovery + token exchange against Dex, then reaches core at
#      PYCIL_CORE_INTERNAL_URL (defaults to the docker name `pycil-core:8000`,
#      which the HOST cannot resolve → must point at the published loopback port).
# This script derives the two secrets from the running container so the recipe is
# captured, not tribal knowledge; the OIDC_* + PYCIL_CORE_INTERNAL_URL defaults
# live in playwright.config.ts (webEnv) and match the staging compose.
#
# Usage:
#   apps/web/scripts/run-e2e.sh                 # run whole suite
#   apps/web/scripts/run-e2e.sh 03-learn        # grep-filter specs
#   E2E_WEB_PORT=3100 apps/web/scripts/run-e2e.sh   # avoid port clash
#
# Prereqs (publishes host ports + sets stub flags the fixtures need; pass with -f
# since the staging file is no longer an auto-merged `override`):
#   docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d \
#     postgres redis pycil-core worker dex minio
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WEB="$ROOT/apps/web"

core_env() { docker compose -f "$ROOT/docker-compose.yml" exec -T pycil-core printenv "$1" 2>/dev/null | tr -d '\r'; }

# Core's secrets — web MUST use these exact values or core 401s (JWT) / 500s (upsert).
AUTH_JWT_SECRET="$(core_env AUTH_JWT_SECRET)"
INTERNAL_API_SECRET="$(core_env INTERNAL_API_SECRET)"
# Real DB password (DATABASE_URL=postgresql+asyncpg://pycil:PW@postgres:5432/pycil).
DB_URL="$(core_env DATABASE_URL)"
POSTGRES_PASSWORD="$(printf '%s' "$DB_URL" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')"
COOKIE="$(core_env SESSION_COOKIE_NAME)"; COOKIE="${COOKIE:-pycil-session}"

if [ -z "$AUTH_JWT_SECRET" ] || [ -z "$POSTGRES_PASSWORD" ] || [ -z "$INTERNAL_API_SECRET" ]; then
  echo "ERROR: could not derive secrets from pycil-core container. Is the stack up?" >&2
  exit 1
fi
# NextAuth needs a stable AUTH_SECRET to encrypt the PKCE/state cookies across the
# OIDC round-trip. It is a web-only secret (core has none), so reuse the JWT secret
# — any stable value works within a single run; reusing one keeps the recipe simple.
AUTH_SECRET="${AUTH_SECRET:-$AUTH_JWT_SECRET}"
echo "derived: jwt_len=${#AUTH_JWT_SECRET} internal_len=${#INTERNAL_API_SECRET} pgpw_len=${#POSTGRES_PASSWORD} cookie=$COOKIE"

# --- Live-LLM precondition (silently-mocked-green guard) ----------------------
# The generation path is gated SOLELY by the worker's WORKER_LLM_STUB; core's
# LLM_STUB_MODE only affects chat streaming. A "zero-mock" run with a leftover
# WORKER_LLM_STUB=true still passes the structural asserts while having tested
# ZERO real LLM. So when the caller asks for a live run (E2E_LIVE_LLM truthy),
# read the flag back from the WORKER container and abort loudly if it is truthy.
# This is the one check that makes "live" mean live; do not soften it.
worker_env() { docker compose -f "$ROOT/docker-compose.yml" exec -T worker printenv "$1" 2>/dev/null | tr -d '\r'; }
case "${E2E_LIVE_LLM:-}" in
  1|true|yes|TRUE|YES)
    stub="$(worker_env WORKER_LLM_STUB)"
    case "$(printf '%s' "$stub" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes)
        echo "ERROR: E2E_LIVE_LLM set but worker WORKER_LLM_STUB='$stub' (truthy)." >&2
        echo "  A live run with the stub on tests ZERO real LLM yet still passes." >&2
        echo "  Restart the stack with stubs off, e.g.:" >&2
        echo "    LLM_STUB_MODE=false WORKER_LLM_STUB=false docker compose \\" >&2
        echo "      -f docker-compose.yml -f docker-compose.staging.yml up -d worker pycil-core" >&2
        exit 1
        ;;
    esac
    echo "live-LLM precondition ok: worker WORKER_LLM_STUB='${stub:-<unset>}' (falsy)"
    ;;
esac

FILTER="${1:-}"
GREP_ARG=()
[ -n "$FILTER" ] && GREP_ARG=(--grep "$FILTER")

# CRITICAL: do NOT reuse a foreign next dev. Other projects (e.g. pandora-code)
# commonly squat :3000; with reuseExistingServer the suite silently runs against
# the WRONG app and "passes" on generic assertions (false green). Force CI=true
# so playwright.config sets reuseExistingServer=false and boots OUR app, and pick
# a dedicated port that other local stacks don't use. Override with E2E_WEB_PORT.
PORT="${E2E_WEB_PORT:-3210}"
if curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/" 2>/dev/null | grep -qv '^000$'; then
  echo "ERROR: port ${PORT} is already in use — pick a free E2E_WEB_PORT." >&2
  exit 1
fi

cd "$WEB"
# Do NOT pin NODE_ENV: the default webServer runs `next build && next start`,
# and a forced NODE_ENV=development corrupts the production build (Next warns,
# then the /404 prerender fails). Let each next subcommand set its own NODE_ENV.
# For an interactive dev loop, pass E2E_WEB_COMMAND="npx next dev -p $PORT".
#
# AUTH_URL must match the port the browser actually hits so Auth.js builds the
# right callback/redirect URLs. OIDC_*/PYCIL_CORE_INTERNAL_URL defaults live in
# playwright.config webEnv; export here only what is derived per-run.
exec env \
  NEXT_PUBLIC_USE_MOCK=false \
  E2E_PROXY=true \
  AUTH_JWT_SECRET="$AUTH_JWT_SECRET" \
  AUTH_SECRET="$AUTH_SECRET" \
  INTERNAL_API_SECRET="$INTERNAL_API_SECRET" \
  SESSION_COOKIE_NAME="$COOKIE" \
  AUTH_URL="http://localhost:$PORT" \
  POSTGRES_USER=pycil POSTGRES_DB=pycil PG_HOST=localhost PG_PORT=5432 \
  POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  E2E_WEB_PORT="$PORT" \
  E2E_WORKER_SPECS="${E2E_WORKER_SPECS:-true}" \
  CI=true \
  pnpm exec playwright test --config=playwright.config.ts "${GREP_ARG[@]}"
