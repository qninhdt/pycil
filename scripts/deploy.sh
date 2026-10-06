#!/usr/bin/env bash
# Operator-only migration-then-swap; never run automatically or reset a database.
# A deployment needs separate approval and a independently verified backup.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ENV_FILE:?explicit deployment environment file required}"
: "${API_IMAGE:?immutable tested image required}"
: "${DEPLOY_APPROVED:?set to yes only after separate deployment approval}"
: "${VERIFIED_BACKUP_FILE:?explicit verified database backup required}"
: "${VERIFIED_BACKUP_SHA256:?verified backup checksum required}"
[ "$DEPLOY_APPROVED" = yes ] || exit 2
case "$API_IMAGE" in *@sha256:*) ;; *) echo "deploy: image must use a digest" >&2; exit 2 ;; esac
[ -f "$VERIFIED_BACKUP_FILE" ] || exit 2
actual="$(sha256sum "$VERIFIED_BACKUP_FILE")"
[ "${actual%% *}" = "$VERIFIED_BACKUP_SHA256" ] || exit 2
export API_IMAGE
compose=(python scripts/compose.py --env-file "$ENV_FILE")
"${compose[@]}" config -q
"${compose[@]}" pull api worker migrate
# Stop both writers before the explicit migration. A failed migration leaves
# them stopped; never pretend swapping an old image reverses schema changes.
"${compose[@]}" stop api worker
"${compose[@]}" run --rm --no-deps migrate
"${compose[@]}" up -d --no-deps --wait api worker
"${compose[@]}" run --rm --no-deps worker python -m pycil.worker --check
echo "deploy: API and worker replaced after explicit schema verification"
