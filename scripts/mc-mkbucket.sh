#!/usr/bin/env bash
# Create the MinIO bucket for avatars + TTS audio (idempotent).
#
# The minio/minio server image has no `mc`; the `mc` client ships in a separate
# image. Run it as a one-shot container joined to the compose network so it can
# reach the minio service at its in-cluster name.
#
# Invoked by staging-up.sh after MinIO is healthy. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

# Load env for S3_* (staging-up already exports these, but allow standalone use).
[ -f .env ] && { set -a; . ./.env; set +a; }

BUCKET="${S3_BUCKET:-pycil-media}"
KEY_ID="${S3_KEY_ID:-minioadmin}"
SECRET="${S3_APPLICATION_KEY:-minioadmin}"
MC_IMAGE="minio/mc:RELEASE.2025-04-08T15-39-49Z"

# Compose project name is `pycil` (docker-compose.yml `name:`), so the default
# network is pycil_default. mc reaches the server at http://minio:9000.
NETWORK="${COMPOSE_PROJECT_NAME:-pycil}_default"

# Creds go through MC_HOST_local (mc reads it for the `local` alias) instead of
# being interpolated into the command string — a secret containing a quote can't
# break the shell, and it never shows in the container's `ps`/args. BUCKET is a
# tame slug; pass it through the environment too for symmetry.
docker run --rm --network "$NETWORK" \
  -e MC_HOST_local="http://${KEY_ID}:${SECRET}@minio:9000" \
  -e BUCKET="$BUCKET" \
  --entrypoint sh "$MC_IMAGE" -c '
  set -e
  mc mb --ignore-existing "local/$BUCKET"
  # Public-read on the media prefix so presigned GETs (and the public URL
  # prefix) serve avatars/audio without per-object ACLs.
  mc anonymous set download "local/$BUCKET" >/dev/null || true
'
printf '\033[32m✓ MinIO bucket ready: %s\033[0m\n' "$BUCKET"
