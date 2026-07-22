#!/usr/bin/env bash
# Restore a coordinated product backup. This intentionally stops both stacks.
set -euo pipefail

PYCIL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LEXI_PROJECT_DIR="${LEXI_PROJECT_DIR:-/opt/lexi-ai}"
BACKUP_ID="${BACKUP_ID:?set BACKUP_ID to the coordinated backup identifier}"

test -f "$LEXI_PROJECT_DIR/deploy/docker-compose.yml" || {
  echo "LEXI_PROJECT_DIR must contain deploy/docker-compose.yml" >&2
  exit 1
}

(cd "$PYCIL_DIR" && docker compose stop caddy api worker)
(cd "$LEXI_PROJECT_DIR" && docker compose -f deploy/docker-compose.yml stop api worker)

# Lexi must restore first: Pycil persists opaque Lexi IDs.
(cd "$LEXI_PROJECT_DIR" && BACKUP_ID="$BACKUP_ID" docker compose -f deploy/docker-compose.yml --profile backup run --rm --entrypoint /restore.sh backup)
(cd "$LEXI_PROJECT_DIR" && docker compose -f deploy/docker-compose.yml up -d migrate api worker)
(cd "$PYCIL_DIR" && BACKUP_ID="$BACKUP_ID" docker compose --profile backup run --rm --entrypoint /restore.sh backup)
(cd "$PYCIL_DIR" && docker compose up -d migrate worker api caddy)

echo "restore submitted; verify both /readyz and /health/ready before traffic is resumed"
