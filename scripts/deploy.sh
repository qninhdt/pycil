#!/usr/bin/env bash
# Host-side production deploy: migration-then-swap via docker compose.
#
# CI (deploy.yml) builds and pushes the backend application images. Deployment
# happens HERE, on the VPS — no SSH from CI. Run after pulling the latest repo:
#
#   cd /opt/pycil && git pull \
#     API_IMAGE=ghcr.io/qninhdt/pycil-api@sha256:<digest> \
#     bash scripts/deploy.sh
#
# The backend stack is deployed here: API and Caddy. Web is on Vercel.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root (expected: /opt/pycil)

ENV_FILE="${ENV_FILE:-.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pycil}"

red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
die() { red "deploy: $*"; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE not found in $(pwd)."
# Source .env so $POSTGRES_USER / $POSTGRES_DB are available to pg_dump.
set -a; . "./$ENV_FILE"; set +a

: "${LEXI_REFERENCE_DATASET_PATH:?LEXI_REFERENCE_DATASET_PATH is required}"
: "${LEXI_REFERENCE_DATASET_SHA256:?LEXI_REFERENCE_DATASET_SHA256 is required}"
: "${API_IMAGE:?API_IMAGE must be an immutable registry digest}"
for image in "$API_IMAGE"; do
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
grn "→ deploying immutable API image"

# --- 1. Pre-deploy DB snapshot (keep last 5) ---------------------------------
mkdir -p "$BACKUP_DIR"
ts=$(date +%s)
grn "→ pg_dump snapshot…"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "$BACKUP_DIR/pre-deploy-${ts}.sql"
ls -1t "$BACKUP_DIR"/pre-deploy-*.sql | tail -n +6 | xargs -r rm

# --- 1b. Record what is running now, so a failed swap can be undone ----------
# Read from the live containers rather than from the environment: the variables
# this script was invoked with are the images being deployed, so they say nothing
# about what is currently serving. `com.docker.compose.image` is the image ID the
# running container was created from, which is what a rollback has to restore.
running_image() {
  local service="$1" id
  id="$(docker compose ps -q "$service" 2>/dev/null | head -1)"
  [ -n "$id" ] || return 1
  docker inspect "$id" --format '{{index .Config.Labels "com.docker.compose.image"}}'
}
PREVIOUS_API="$(running_image api || true)"
PREVIOUS_HEAD="$(docker compose exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'SELECT version_num FROM alembic_version' \
  2>/dev/null | tr -d '[:space:]' || true)"
grn "→ previous: api=${PREVIOUS_API:-none} head=${PREVIOUS_HEAD:-unknown}"

# Written before anything changes, so a deploy that dies mid-swap still leaves the
# rollback values on disk for whoever picks it up.
ROLLBACK_FILE="${BACKUP_DIR}/last-deploy-${ts}.rollback"
{
  printf 'PREVIOUS_API=%s\n' "$PREVIOUS_API"
  printf 'PREVIOUS_HEAD=%s\n' "$PREVIOUS_HEAD"
  printf 'NEW_API=%s\n' "$API_IMAGE"
  printf 'DB_SNAPSHOT=%s\n' "$BACKUP_DIR/pre-deploy-${ts}.sql"
} > "$ROLLBACK_FILE"
ls -1t "$BACKUP_DIR"/*.rollback | tail -n +6 | xargs -r rm

# Undoes the image swap only. It deliberately does NOT downgrade the schema: a
# migration that already ran is not reversed by starting an older image, and
# `alembic downgrade` on a live database is a destructive act that needs a human
# decision and the snapshot above. So this reports what a rollback would need
# rather than performing an unreviewed schema change.
rollback_images() {
  local why="$1"
  red "deploy: ${why}"
  red "deploy: schema is at $(docker compose exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '[:space:]'), was ${PREVIOUS_HEAD:-unknown}"
  red "deploy: rollback values recorded in ${ROLLBACK_FILE}"
  if [ "${legacy_removed:-0}" -eq 1 ]; then
    red "deploy: old API needs its worker: restore the previous Compose revision and worker image manually"
    exit 1
  fi

  if [ -z "$PREVIOUS_API" ]; then
    red "deploy: no previous image recorded for any service; nothing to roll back"
    red "deploy: restore from ${BACKUP_DIR}/pre-deploy-${ts}.sql under the runbook"
    exit 1
  fi

  red "deploy: rolling back: api"
  API_IMAGE="$PREVIOUS_API" \
    docker compose up -d --no-deps api || red "deploy: rollback itself failed"
  red "deploy: rolled back: api. The schema was NOT reverted; if the new"
  red "deploy: revision migrated destructively, restore the snapshot instead."
  exit 1
}

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

# --- 4. Remove the obsolete Compose worker on the first cutover --------------
# Use the current project's labels; never touch other projects or Redis data.
project="$(docker compose config --format json | python -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
legacy_workers="$(docker ps -aq --filter "label=com.docker.compose.project=$project" --filter label=com.docker.compose.service=worker)"
if [ -n "$legacy_workers" ]; then
  for legacy_worker in $legacy_workers; do
    grn "→ stopping obsolete worker $legacy_worker (pending Stream jobs will not replay)…"
    docker stop "$legacy_worker" || die "cannot stop old worker"
    docker rm "$legacy_worker" || die "cannot remove old worker"
  done
  legacy_removed=1
fi
# Rollback across this cutover requires the former Compose revision and worker
# image; simply reverting the API image is not sufficient.

grn "→ starting API and TLS/SSE ingress…"
docker compose up -d api caddy
grn "→ waiting for api health…"
healthy=0
for _ in $(seq 1 30); do
  status="$(docker compose ps --format '{{.Health}}' api 2>/dev/null || true)"
  state="$(docker compose ps --format '{{.State}}' api 2>/dev/null || true)"
  if [ "$status" = "unhealthy" ] || [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
    docker compose logs --tail=50 api || true
    rollback_images "api is ${status:-$state} — deploy unhealthy"
  fi
  if docker compose exec -T api \
       python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready').read()" \
       >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 2
done
[ "$healthy" -eq 1 ] || { docker compose logs --tail=50 api || true; rollback_images "api failed health check after 60s"; }
grn "✓ api healthy"

grn "✓ deploy complete (immutable image digests)"
grn "  previous: api=${PREVIOUS_API:-none} head=${PREVIOUS_HEAD:-unknown}"
grn "  rollback values: ${ROLLBACK_FILE}"
grn "  db snapshot:     ${BACKUP_DIR}/pre-deploy-${ts}.sql"
