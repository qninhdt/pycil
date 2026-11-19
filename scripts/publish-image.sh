#!/usr/bin/env bash
# Promote one tested linux/amd64 artifact; never run code from the image.
set -euo pipefail
: "${RELEASE_DIR:?release artifact directory required}"
: "${TESTED_SHA:?tested full source SHA required}"
[[ "$TESTED_SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
case "${1:-}" in verify|publish) ;; *) exit 2 ;; esac
cd "$RELEASE_DIR"
sha256sum --check SHA256SUMS
config_path=$(tar -xOf api.tar manifest.json | jq -er 'select(length == 1) | .[0].Config')
[[ "$config_path" =~ ^([0-9a-f]{64}\.json|blobs/sha256/[0-9a-f]{64})$ ]] || exit 2
config=$(tar -xOf api.tar -- "$config_path")
jq -e --arg sha "$TESTED_SHA" \
  '.os == "linux" and .architecture == "amd64" and .config.Labels["org.opencontainers.image.revision"] == $sha' \
  <<< "$config" >/dev/null
digest=$(crane digest --tarball api.tar)
[[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
if [ "$1" = verify ]; then exit 0; fi
: "${GHCR_REPOSITORY:?required}"
: "${ECR_REPOSITORY:?required}"
: "${AWS_REGION:?required}"
: "${DOCKER_CONFIG:?temporary registry credential directory required}"
umask 077
mkdir -p "$DOCKER_CONFIG"
aws ecr get-login-password --region "$AWS_REGION" |
  crane auth login "${ECR_REPOSITORY%%/*}" --username AWS --password-stdin
crane push api.tar "$GHCR_REPOSITORY:$TESTED_SHA"
test "$(crane digest "$GHCR_REPOSITORY:$TESTED_SHA")" = "$digest"
crane copy "$GHCR_REPOSITORY@$digest" "$ECR_REPOSITORY:$TESTED_SHA"
test "$(crane digest "$ECR_REPOSITORY:$TESTED_SHA")" = "$digest"
jq -n --arg sha "$TESTED_SHA" --arg digest "$digest" \
  --arg ghcr "$GHCR_REPOSITORY@$digest" --arg ecr "$ECR_REPOSITORY@$digest" \
  --arg published_at "$(date -u +%FT%TZ)" \
  '{source_sha:$sha, platform:"linux/amd64", manifest_digest:$digest,
    ghcr:$ghcr, ecr:$ecr, published_at:$published_at}' > release.json
echo "Published verified artifact $digest for $TESTED_SHA; no runtime deployment performed."
