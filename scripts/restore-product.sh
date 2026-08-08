#!/usr/bin/env bash
# Restore a coordinated Pycil backup. The dump contains the public application
# and isolated embedded-Lexi schemas in one PostgreSQL database.
set -euo pipefail

PYCIL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_ID="${BACKUP_ID:?set BACKUP_ID to the coordinated backup identifier}"

(cd "$PYCIL_DIR" && docker compose stop caddy api worker)

# The one dump restores both schemas; the migration gate then verifies the
# installed Lexi head before the API/worker processes start.
(cd "$PYCIL_DIR" && BACKUP_ID="$BACKUP_ID" docker compose --profile backup run --rm --entrypoint /restore.sh backup)
(cd "$PYCIL_DIR" && docker compose up -d migrate worker api caddy)

echo "restore submitted; verify /health/ready before traffic is resumed"
