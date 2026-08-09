#!/usr/bin/env bash
# Rehearse the pre-release, empty-volume cutover locally. This never copies
# prior Lexi service data; it proves the new images can create both schemas,
# start the embedded worker, and satisfy API readiness.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
PROJECT_NAME="${PROJECT_NAME:-pycil-rehearsal}"

[ -f "$ENV_FILE" ] || { echo "rehearsal: $ENV_FILE not found" >&2; exit 2; }
set -a; . "./$ENV_FILE"; set +a

: "${LEXI_REFERENCE_DATASET_PATH:?rehearsal requires LEXI_REFERENCE_DATASET_PATH}"
: "${LEXI_REFERENCE_DATASET_SHA256:?rehearsal requires LEXI_REFERENCE_DATASET_SHA256}"
[ -f "$LEXI_REFERENCE_DATASET_PATH" ] || {
  echo "rehearsal: reference artifact not found: $LEXI_REFERENCE_DATASET_PATH" >&2
  exit 2
}
actual_sha="$(sha256sum "$LEXI_REFERENCE_DATASET_PATH" | cut -d ' ' -f 1)"
[ "$actual_sha" = "$LEXI_REFERENCE_DATASET_SHA256" ] || {
  echo "rehearsal: reference artifact SHA-256 mismatch" >&2
  exit 2
}

compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE")
cleanup() { "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

cleanup
"${compose[@]}" config -q
"${compose[@]}" up -d --build postgres redis centrifugo
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d worker api

for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready').read()" \
    >/dev/null 2>&1; then
    echo "rehearsal: fresh-schema deployment is ready"
    exit 0
  fi
  sleep 2
done

"${compose[@]}" logs --tail=100 api worker migrate >&2 || true
echo "rehearsal: API readiness did not succeed" >&2
exit 1
