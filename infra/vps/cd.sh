#!/usr/bin/env bash
# Invoked over SSH as root; the scoped registry token is provided on stdin.
set -euo pipefail
cd "$(dirname "$0")/../.."
export ENV_FILE=/etc/pycil/runtime.env
export COMPOSE_FILE="$PWD/infra/vps/compose.yaml"
export DEPLOY_STATE_DIR=/srv/pycil/deploy
export SMOKE_SESSION_FILE=/etc/pycil/smoke-session
export PROMETHEUS_URL=http://prometheus:9090
export VERIFIED_BACKUP_FILE=/srv/pycil/backup/verification.json
export VERIFIED_BACKUP_SHA256
VERIFIED_BACKUP_SHA256=$(cat /srv/pycil/backup/verification.sha256)
umask 077
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d /run/pycil-registry.XXXXXX)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
docker login ghcr.io --username "${1:?registry username required}" --password-stdin
timeout --foreground --kill-after=30s 1800s bash infra/vps/deploy.sh deploy release.json
