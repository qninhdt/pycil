#!/usr/bin/env bash
# Host-side production deploy: migration-then-swap via docker compose.
#
# CI (deploy.yml) builds and pushes the three application images. Deployment
# happens HERE, on the VPS — no SSH from CI. Run after pulling the latest repo:
#
#   cd /opt/pycil && git pull \
#     API_IMAGE=ghcr.io/qninhdt/pycil-api@sha256:<digest> \
#     WORKER_IMAGE=ghcr.io/qninhdt/pycil-worker@sha256:<digest> \
#     WEB_IMAGE=ghcr.io/qninhdt/pycil-web@sha256:<digest> \
#     bash scripts/deploy.sh
#
# The complete stack is deployed here: API, worker, web, and Caddy.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root (expected: /opt/pycil)

ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pycil}"
WORKER_DRAIN_SECONDS="${WORKER_DRAIN_SECONDS:-30}"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
die() { red "deploy: $*"; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found in $(pwd)."
# Source .env so $POSTGRES_USER / $POSTGRES_DB are available to pg_dump.
set -a; . "./$ENV_FILE"; set +a

: "${LEXI_REFERENCE_DATASET_PATH:?LEXI_REFERENCE_DATASET_PATH is required}"
: "${LEXI_REFERENCE_DATASET_SHA256:?LEXI_REFERENCE_DATASET_SHA256 is required}"
: "${API_IMAGE:?API_IMAGE must be an immutable registry digest}"
: "${WORKER_IMAGE:?WORKER_IMAGE must be an immutable registry digest}"
: "${WEB_IMAGE:?WEB_IMAGE must be an immutable registry digest}"
for image in "$API_IMAGE" "$WORKER_IMAGE" "$WEB_IMAGE"; do
  case "$image" in
    *@sha256:*) ;;
    *) die "application images must use @sha256 digests: $image" ;;
  esac
done
[ -f "$LEXI_REFERENCE_DATASET_PATH" ] || die "Lexi reference artifact not found: $LEXI_REFERENCE_DATASET_PATH"
reference_sha="$(sha256sum "$LEXI_REFERENCE_DATASET_PATH" | cut -d ' ' -f 1)"
[ "$reference_sha" = "$LEXI_REFERENCE_DATASET_SHA256" ] \
  || die "Lexi reference artifact SHA-256 does not match LEXI_REFERENCE_DATASET_SHA256"

# A VPS deploy is always production even when an operator copied a development
# template and forgot this knob. The API then validates all production guards.
export ENVIRONMENT=production
grn "→ deploying immutable API, worker, and web images"

# --- 1. Pre-deploy DB snapshot (keep last 5) ---------------------------------
mkdir -p "$BACKUP_DIR"
ts=$(date +%s)
grn "→ pg_dump snapshot…"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$BACKUP_DIR/pre-deploy-${ts}.sql"
ls -1t "$BACKUP_DIR"/pre-deploy-*.sql | tail -n +6 | xargs -r rm

# --- 2. Pull new images ------------------------------------------------------
grn "→ docker compose pull…"
docker compose pull

grn "→ validating Caddy TLS/SSE ingress configuration…"
docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
  >/dev/null || die "Caddy ingress configuration is invalid"

# --- 3. Migration-then-swap: migrate in the NEW image BEFORE swapping --------
# `migrate` applies Lexi's isolated schema first, then Pycil's public schema.
# Running it here mirrors the compose gate while letting us abort before
# workloads are swapped. The fresh-schema baseline has no copy-and-stamp path.
grn "→ Lexi domain then Pycil alembic upgrades (new image)…"
if ! docker compose run --rm migrate; then
  die "migration failed; aborting deploy. old containers untouched."
fi

# --- 4. Drain old jobs, then start worker before API --------------------------
# Pending jobs are written by the API but consumed by the worker, so starting
# the worker first prevents an API/worker schema-version window. This pre-release
# deployment starts from a fresh schema; after the first embedded write use a
# forward fix or verified database restore, never a destructive downgrade.
grn "→ draining previous worker (up to ${WORKER_DRAIN_SECONDS}s)…"
docker compose stop -t "$WORKER_DRAIN_SECONDS" worker || true
grn "→ starting domain worker before API…"
docker compose up -d worker
grn "→ waiting for worker health…"
worker_ok=0
for _ in $(seq 1 30); do
  status="$(docker compose ps --format '{{.Health}}' worker 2>/dev/null || true)"
  [ "$status" = "healthy" ] && { worker_ok=1; break; }
  state="$(docker compose ps --format '{{.State}}' worker 2>/dev/null || true)"
  if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
    docker compose logs --tail=50 worker || true
    die "worker container is $state — deploy unhealthy"
  fi
  sleep 2
done
[ "$worker_ok" -eq 1 ] || { docker compose logs --tail=50 worker || true; die "worker failed health check after 60s"; }
grn "✓ worker healthy"

grn "→ starting API, web, and TLS/SSE ingress…"
docker compose up -d api web caddy
grn "→ waiting for api health…"
healthy=0
for _ in $(seq 1 30); do
  if docker compose exec -T api \
       python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready').read()" \
       >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ] || die "api failed health check after 60s"
grn "✓ api healthy"

grn "✓ deploy complete (immutable image digests)"
