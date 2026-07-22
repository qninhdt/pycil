#!/bin/sh
# Pycil DB restore from latest restic snapshot.
# Run via: docker compose --profile backup run --rm --entrypoint /restore.sh backup
set -eu

: "${DATABASE_URL:?DATABASE_URL not set}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY not set}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE not set}"

SNAPSHOT="${SNAPSHOT:-latest}"
: "${BACKUP_ID:?BACKUP_ID is required}"

echo "[restore] streaming snapshot $SNAPSHOT into pg_restore"
restic dump "$SNAPSHOT" "pycil-${BACKUP_ID}.dump" \
  | pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL"

echo "[restore] done"
