#!/usr/bin/env bash
# Coordinated Pycil backup. The dump contains both the public application schema
# and the isolated embedded-Lexi schema in the shared PostgreSQL database. Run on
# the host only, never from CI.
set -euo pipefail

PYCIL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_ID="${BACKUP_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"

restore_services() {
  (cd "$PYCIL_DIR" && docker compose up -d worker api web caddy)
}
trap restore_services EXIT

# A stopped write path gives the shared PostgreSQL dump one consistent product point.
(cd "$PYCIL_DIR" && docker compose stop api worker)
(cd "$PYCIL_DIR" && BACKUP_ID="$BACKUP_ID" docker compose --profile backup run --rm backup)

printf '{"backupId":"%s","createdAt":"%s"}\n' "$BACKUP_ID" "$(date -u +%FT%TZ)" \
  > "$PYCIL_DIR/backup-manifest-${BACKUP_ID}.json"
echo "coordinated backup complete: $BACKUP_ID"
