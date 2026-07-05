#!/usr/bin/env bash
# Host-side production deploy: migration-then-swap via docker compose.
#
# CI (deploy.yml) only builds + pushes api/worker images to ghcr. Deployment
# happens HERE, on the VPS — no SSH from CI. Run after pulling the latest repo:
#
#   cd /opt/pycil && git pull && IMAGE_TAG=<sha12> bash scripts/deploy.sh
#
# IMAGE_TAG defaults to "latest"; pass the 12-char commit SHA CI printed to pin
# an exact build. The web frontend is NOT deployed here — it ships to Vercel /
# Next.js hosting separately; this stack is API-only (api + worker + centrifugo).
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root (expected: /opt/pycil)

REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_PREFIX="${IMAGE_PREFIX:-qninhdt/pycil}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pycil}"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
die() { red "deploy: $*"; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found in $(pwd)."
# Source .env so $POSTGRES_USER / $POSTGRES_DB are available to pg_dump.
set -a; . "./$ENV_FILE"; set +a

export API_IMAGE="${REGISTRY}/${IMAGE_PREFIX}-api:${IMAGE_TAG}"
export WORKER_IMAGE="${REGISTRY}/${IMAGE_PREFIX}-worker:${IMAGE_TAG}"
grn "→ deploying api=${API_IMAGE} worker=${WORKER_IMAGE}"

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

# --- 3. Migration-then-swap: migrate in the NEW image BEFORE swapping --------
# `migrate` is the one-shot compose service (command: alembic upgrade head,
# built from the same API_IMAGE) — running it here mirrors what api/worker's
# own `depends_on: migrate: service_completed_successfully` gate does on `up`,
# but lets us abort the deploy BEFORE swapping if migration fails.
grn "→ alembic upgrade head (new image, via the migrate service)…"
if ! docker compose run --rm migrate; then
  die "migration failed; aborting deploy. old containers untouched."
fi

grn "→ docker compose up -d…"
docker compose up -d

# --- 4. Health gate: api HTTP, then worker compose healthcheck ---------------
grn "→ waiting for api health…"
healthy=0
for _ in $(seq 1 30); do
  if docker compose exec -T api \
       python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" \
       >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ] || die "api failed health check after 60s"
grn "✓ api healthy"

# Worker shares the schema + runs generation/grading jobs: a migration that
# breaks it must fail the deploy, not silently crash-loop.
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

grn "✓ deploy complete (tag ${IMAGE_TAG})"

