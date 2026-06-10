#!/usr/bin/env bash
# One-command local staging: full backend stack in compose (Postgres, Redis,
# pycil-core, worker, Dex, MinIO) + web on the host via `next dev`.
#
#   make staging        # bring it all up, stream web logs in the foreground
#   make staging-down    # tear the stack down + stop the host web
#
# Open http://localhost:3100 → redirected to Dex → log in
# e2e-test@pycil.local / password123 → land on the dashboard. Real LLM via
# OpenRouter (stub flags forced off here).
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

ENV_FILE=".env"
WEB_PORT=3100
WEB_DIR="apps/web"
WEB_PIDFILE=".staging-web.pid"
PLACEHOLDER="changeme-base64-32-bytes"
DEX_CONFIG="infra/dex/config.yaml"
# Explicit -f (NOT the magic docker-compose.override.yml name): the staging
# file must never auto-merge into a bare `docker compose` on the prod host
# (deploy.yml runs bare `up -d`), which would swap prod to a --reload dev server
# with LLM stubs on. Every staging invocation names both files explicitly.
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.staging.yml"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
die() { red "staging-up: $*"; exit 1; }

# --- 1. Load + validate env --------------------------------------------------
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found — run: cp .env.example .env, then fill secrets."
set -a; . "./$ENV_FILE"; set +a

for v in OIDC_ISSUER_URL INTERNAL_API_SECRET AUTH_JWT_SECRET POSTGRES_USER POSTGRES_DB; do
  [ -n "${!v:-}" ] || die "$v is unset in $ENV_FILE (add the OIDC block from .env.example?)."
done
[ -n "${OPENROUTER_API_KEY:-}" ] || red "warning: OPENROUTER_API_KEY empty — real-LLM features will fail (stubs are forced off in staging)."

# --- 2. Guard placeholder secrets (cheap, before standing the stack up) -------
[ "$INTERNAL_API_SECRET" != "$PLACEHOLDER" ] || die "INTERNAL_API_SECRET is still the .env.example placeholder — generate one: openssl rand -base64 32"
[ "$AUTH_JWT_SECRET" != "$PLACEHOLDER" ] || die "AUTH_JWT_SECRET is still the .env.example placeholder — generate one: openssl rand -base64 32"

# --- 3. Assert issuer byte-match (fail fast vs cryptic Auth.js discovery err) -
dex_issuer="$(sed -n 's/^issuer:[[:space:]]*//p' "$DEX_CONFIG" | head -n1 | tr -d '[:space:]')"
[ -n "$dex_issuer" ] || die "could not read issuer: from $DEX_CONFIG."
# Strip both sides: a trailing space/CR on the env value must not fail the match.
oidc_issuer="$(printf '%s' "$OIDC_ISSUER_URL" | tr -d '[:space:]')"
if [ "$dex_issuer" != "$oidc_issuer" ]; then
  die "issuer mismatch: $DEX_CONFIG has '$dex_issuer' but OIDC_ISSUER_URL='$oidc_issuer' — they must byte-match."
fi
grn "✓ issuer byte-match: $dex_issuer"

# --- 4. Bring up the backend stack (stub flags OFF for real LLM) -------------
grn "→ building + starting backend services…"
LLM_STUB_MODE=false WORKER_LLM_STUB=false \
  $COMPOSE up -d --build postgres redis pycil-core worker dex minio

# --- 5. Wait for health ------------------------------------------------------
wait_healthy() {
  local svc="$1" cid status tries=0 max=60
  while :; do
    cid="$($COMPOSE ps -q "$svc" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      status="$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)"
      [ "$status" = "healthy" ] && { grn "✓ $svc healthy"; return 0; }
      [ "$status" = "unhealthy" ] && die "$svc reported unhealthy — check: $COMPOSE logs $svc"
    fi
    tries=$((tries + 1)); [ "$tries" -ge "$max" ] && die "$svc not healthy after $((max * 2))s — check: $COMPOSE logs $svc"
    sleep 2
  done
}
for svc in postgres redis pycil-core worker dex minio; do wait_healthy "$svc"; done

# --- 6. Create the MinIO bucket (idempotent) ---------------------------------
grn "→ ensuring MinIO bucket…"
bash scripts/mc-mkbucket.sh

# --- 7. Migrate (idempotent) -------------------------------------------------
grn "→ applying migrations…"
$COMPOSE run --rm pycil-core alembic upgrade head

# --- 8. Seed the canonical test identity as a plain user (NOT admin) ----------
# The Dex static user and this seed MUST share one email so login resolves to a
# real row. role='user' keeps E2E off admin surfaces (require_admin reads live
# DB role; local Caddy does not gate /admin/*).
grn "→ seeding canonical test user (role=user)…"
$COMPOSE exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "INSERT INTO users (email, role) VALUES ('e2e-test@pycil.local','user') ON CONFLICT (email) DO UPDATE SET role='user';"

# --- 9. Launch host web ------------------------------------------------------
# Shell env beats apps/web/.env.local, which pins NEXT_PUBLIC_USE_MOCK=true (that
# renders the demo-bypass button instead of the Dex flow). Force it false here.
grn "→ starting host web on :$WEB_PORT (real OIDC via Dex)…"
# setsid runs web in its own process group so teardown can kill the whole tree
# (npm → next → node); killing just the subshell PID would orphan next on :3100.
cleanup() {
  if [ -f "$WEB_PIDFILE" ]; then
    kill -- "-$(cat "$WEB_PIDFILE")" 2>/dev/null || true
    rm -f "$WEB_PIDFILE"
  fi
}
trap cleanup INT TERM EXIT

setsid bash -c "
  cd '$WEB_DIR'
  AUTH_URL='http://localhost:$WEB_PORT' \
  PORT='$WEB_PORT' \
  NEXT_PUBLIC_USE_MOCK=false \
  NEXT_DEV_PROXY_TARGET='${NEXT_DEV_PROXY_TARGET:-http://localhost:8000}' \
  exec npm run dev
" &
WEB_PID=$!
echo "$WEB_PID" > "$WEB_PIDFILE"

grn ""
grn "════════════════════════════════════════════════════════════════"
grn " staging up. open http://localhost:$WEB_PORT"
grn " login: e2e-test@pycil.local / password123"
grn " Ctrl-C stops web; backend stays up. 'make staging-down' tears all down."
grn "════════════════════════════════════════════════════════════════"

wait "$WEB_PID"
