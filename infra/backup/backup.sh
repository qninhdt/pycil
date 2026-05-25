#!/bin/sh
# Pycil nightly backup: pg_dump | restic backup → B2.
# Run via: docker compose --profile backup run --rm backup
set -eu

: "${DATABASE_URL:?DATABASE_URL not set}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY not set (e.g. b2:bucket/pycil)}"
: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE not set}"

TAG="pycil-pg-$(date -u +%F)"

echo "[backup] starting $TAG"

restic snapshots --tag pycil-pg- >/dev/null 2>&1 || restic init

pg_dump -Fc -d "$DATABASE_URL" \
  | restic backup --tag "$TAG" --stdin --stdin-filename pycil.dump

echo "[backup] applying retention policy (7d/4w/6m)"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune

echo "[backup] done"
