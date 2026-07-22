#!/usr/bin/env bash
# Coordinated Pycil + Lexi backup. Run on the host only, never from CI.
set -euo pipefail

PYCIL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LEXI_PROJECT_DIR="${LEXI_PROJECT_DIR:-/opt/lexi-ai}"
BACKUP_ID="${BACKUP_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"

test -f "$LEXI_PROJECT_DIR/deploy/docker-compose.yml" || {
  echo "LEXI_PROJECT_DIR must contain deploy/docker-compose.yml" >&2
  exit 1
}

restore_services() {
  (cd "$LEXI_PROJECT_DIR" && docker compose -f deploy/docker-compose.yml up -d api worker)
  (cd "$PYCIL_DIR" && docker compose up -d worker api caddy)
}
trap restore_services EXIT

# A stopped write path gives both PostgreSQL dumps one consistent product point.
(cd "$PYCIL_DIR" && docker compose stop api worker)
(cd "$LEXI_PROJECT_DIR" && docker compose -f deploy/docker-compose.yml stop api worker)
(cd "$LEXI_PROJECT_DIR" && BACKUP_ID="$BACKUP_ID" docker compose -f deploy/docker-compose.yml --profile backup run --rm backup)
(cd "$PYCIL_DIR" && BACKUP_ID="$BACKUP_ID" docker compose --profile backup run --rm backup)

printf '{"backupId":"%s","createdAt":"%s"}\n' "$BACKUP_ID" "$(date -u +%FT%TZ)" \
  > "$PYCIL_DIR/backup-manifest-${BACKUP_ID}.json"
echo "coordinated backup complete: $BACKUP_ID"
