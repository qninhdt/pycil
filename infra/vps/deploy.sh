#!/usr/bin/env bash
# One operator at a time; Docker, Caddy and Taskiq own their native lifecycles.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${ENV_FILE:?private production env required}"
: "${DEPLOY_STATE_DIR:?existing private deployment-state directory required}"
: "${SMOKE_SESSION_FILE:?existing dedicated Clerk smoke-session ID file required}"
: "${PROMETHEUS_URL:?private Prometheus query URL required}"
: "${VERIFIED_BACKUP_FILE:?independently verified recovery evidence required}"
: "${VERIFIED_BACKUP_SHA256:?recovery evidence checksum required}"
case "${1:-}" in deploy|rollback) action=$1 ;; *) echo 'usage: deploy.sh deploy release.json | rollback' >&2; exit 2 ;; esac
[[ -d "$DEPLOY_STATE_DIR" && -s "$SMOKE_SESSION_FILE" && -f "$VERIFIED_BACKUP_FILE" ]] || exit 2
[[ "$DEPLOY_STATE_DIR" = /* && "$ENV_FILE" = /* ]] || exit 2
actual=$(sha256sum "$VERIFIED_BACKUP_FILE")
[[ "${actual%% *}" = "$VERIFIED_BACKUP_SHA256" ]] || exit 2
umask 077
exec 9>"$DEPLOY_STATE_DIR/deploy.lock"
flock -n 9 || { echo 'deploy: another deployment is running' >&2; exit 1; }
# Native Compose file selection allows isolated drills without another config parser.
export COMPOSE_FILE="${COMPOSE_FILE:-$PWD/infra/vps/compose.yaml}"
compose=(python3 scripts/compose.py --env-file "$ENV_FILE" --project-name "${COMPOSE_PROJECT_NAME:-pycil-production}")
run() { timeout --foreground --kill-after=15s 480s "${compose[@]}" "$@"; }
start_worker() {
  local service id started listening
  for service in worker worker-2; do
    run up -d --no-build --no-deps --wait --wait-timeout 120 "$service" || return 1
    id=$(run ps -q "$service")
    started=$(docker inspect --format '{{.State.StartedAt}}' "$id")
    listening=no
    for _ in $(seq 1 60); do
      if docker logs --since "$started" "$id" 2>&1 | grep -F 'Listening started.' >/dev/null; then
        listening=yes
        break
      fi
      sleep 1
    done
    [[ "$listening" = yes && "$(docker inspect --format '{{.State.Running}} {{.State.StartedAt}}' "$id")" = "true $started" ]] || return 1
  done
}

manifest() {
  jq -er --arg repository "${IMAGE_REPOSITORY:-ghcr.io/qninhdt/pycil-api}" 'select(.platform == "linux/amd64") | select(.source_sha | test("^[0-9a-f]{40}$")) |
    select(.ghcr == ($repository + "@" + .manifest_digest)) |
    .ghcr | select(startswith($repository + "@sha256:")) | select(test("@sha256:[0-9a-f]{64}$"))' "$1"
}
old=$(cat "$DEPLOY_STATE_DIR/active")
[[ "$old" = blue || "$old" = green ]] || exit 2
if [[ "$old" = blue ]]; then next=green; else next=blue; fi
export BLUE_API_IMAGE GREEN_API_IMAGE RELEASE_IMAGE DEPLOY_STATE_DIR
BLUE_API_IMAGE=$(manifest "$DEPLOY_STATE_DIR/blue.json")
GREEN_API_IMAGE=$(manifest "$DEPLOY_STATE_DIR/green.json")
old_image=$(manifest "$DEPLOY_STATE_DIR/$old.json")
[[ ! -e "$DEPLOY_STATE_DIR/pending" ]] || { echo 'deploy: interrupted switch; follow the manual recovery runbook' >&2; exit 1; }
if [[ "$action" = deploy ]]; then
  release=${2:?release.json required}
else
  next=$(cat "$DEPLOY_STATE_DIR/previous")
  [[ "$next" = blue || "$next" = green ]] || exit 2
  [[ "$next" != "$old" ]] || exit 2
  release="$DEPLOY_STATE_DIR/$next.json"
fi
image=$(manifest "$release")
sha=$(jq -er .source_sha "$release")
if [[ "$next" = blue ]]; then BLUE_API_IMAGE=$image; else GREEN_API_IMAGE=$image; fi
RELEASE_IMAGE=$old_image
old_services=("api-$old")
next_services=("api-$next")
for index in {2..6}; do
  old_services+=("api-$old-$index")
  next_services+=("api-$next-$index")
done
run config -q
available_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
[[ "$available_kb" -ge 2097152 ]] || { echo 'deploy: less than 2 GiB available for overlap/headroom' >&2; exit 1; }
available_kb=$(df -Pk "$DEPLOY_STATE_DIR" | awk 'NR==2 {print $4}')
[[ "$available_kb" -ge 5242880 ]] || { echo 'deploy: less than 5 GiB free deployment storage' >&2; exit 1; }
for service in "${old_services[@]}"; do
  id=$(run ps -q "$service")
  [[ "$(docker inspect --format '{{.Image}}' "$id")" = "$(docker image inspect --format '{{.Id}}' "$old_image")" ]] || { echo 'deploy: active container differs from recorded release' >&2; exit 1; }
done
for service in "${old_services[@]}"; do
  run exec -T caddy wget -qO- http://127.0.0.1:2019/config/ | grep -F "$service:8000" >/dev/null
done
run exec -T caddy cat /etc/caddy/Caddyfile | cmp -s - infra/vps/Caddyfile || { echo 'deploy: ingress configuration changes require a separate validated reload' >&2; exit 1; }
run exec -T "api-$old" python -c 'import sys,urllib.request; urllib.request.urlopen(sys.argv[1]+"/-/ready",timeout=5).read()' "$PROMETHEUS_URL"
run pull "api-$next"
[[ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")" = linux/amd64 ]] || { echo 'deploy: candidate image platform differs from release manifest' >&2; exit 1; }
actual_sha=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
[[ "$actual_sha" = "$sha" ]] || { echo 'deploy: image revision differs from release manifest' >&2; exit 1; }
# Exact-head startup validation makes cross-head restart unsafe even for additive DDL.
head_code='from alembic.script import ScriptDirectory; from pycil.app.schema import migration_config; print(ScriptDirectory.from_config(migration_config("postgresql+asyncpg://")).get_current_head())'
old_head=$(timeout 60s docker run --rm --network none --memory 256m --cpus 0.25 --entrypoint python "$old_image" -c "$head_code")
new_head=$(timeout 60s docker run --rm --network none --memory 256m --cpus 0.25 --entrypoint python "$image" -c "$head_code")
[[ "$old_head" = "$new_head" ]] || { echo 'deploy: schema head changes require a separately planned maintenance release' >&2; exit 1; }
# Keep the last accepted routing on disk; a reload failure must remain reversible.
cp "$DEPLOY_STATE_DIR/upstream.caddy" "$DEPLOY_STATE_DIR/previous.caddy"
switched=no
migration="${COMPOSE_PROJECT_NAME:-pycil-production}-release-migration"
restore() {
  local status=$?
  trap - EXIT INT TERM
  docker rm -f "$migration" >/dev/null 2>&1 || true
  restored=yes
  if [[ "$status" != 0 && "$switched" = yes ]]; then
    restored=no
    echo 'deploy: restoring previous routing and worker' >&2
    cp "$DEPLOY_STATE_DIR/previous.caddy" "$DEPLOY_STATE_DIR/upstream.restore"
    mv "$DEPLOY_STATE_DIR/upstream.restore" "$DEPLOY_STATE_DIR/upstream.caddy"
    if run exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
      RELEASE_IMAGE=$old_image
      if start_worker; then
        rm -f "$DEPLOY_STATE_DIR/pending"
        restored=yes
      else
        echo 'deploy: worker restore failed; retained pending state for operator recovery' >&2
      fi
    else
      echo 'deploy: ROUTING RESTORE FAILED; keep both API slots running' >&2
    fi
  fi
  if [[ "$status" != 0 && "$restored" = yes ]]; then run stop "${next_services[@]}" || true; fi
  exit "$status"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
RELEASE_IMAGE=$image
if [[ "$action" = deploy ]]; then
  run run --rm --no-deps --name "$migration" migrate
fi
run up -d --no-build --no-deps --wait --wait-timeout 180 "${next_services[@]}"
probe='import json,urllib.request; assert json.load(urllib.request.urlopen("http://127.0.0.1:8000/readyz",timeout=3))["status"]=="ready"'
for _ in 1 2 3 4 5; do
  for service in "${next_services[@]}"; do
    run exec -T "$service" python -c "$probe"
  done
  sleep 2
done
for service in "${next_services[@]}"; do
  python3 infra/vps/session-token.py "$ENV_FILE" "$SMOKE_SESSION_FILE" |
    run exec -T "$service" python -c "$(cat infra/vps/smoke.py)" http://127.0.0.1:8000 authenticated
done
sed "s/api-blue/api-$next/g" infra/vps/upstream.caddy > "$DEPLOY_STATE_DIR/candidate.caddy"
sed 's#/routing/upstream.caddy#/routing/candidate.caddy#g' infra/vps/Caddyfile > "$DEPLOY_STATE_DIR/candidate.Caddyfile"
run exec -T caddy caddy validate --config /etc/caddy/routing/candidate.Caddyfile --adapter caddyfile
# Record intent before reload: after a host/process crash, automatic deploy refuses to guess.
printf '%s\n' "$next" > "$DEPLOY_STATE_DIR/pending"
switched=yes
mv "$DEPLOY_STATE_DIR/candidate.caddy" "$DEPLOY_STATE_DIR/upstream.caddy"
run exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
start_worker
# Session tokens are short-lived: authenticate before switching, observe public reads after it.
for sample in $(seq 1 30); do
  run exec -T "api-$next" python -c "$(cat infra/vps/smoke.py)" https://api-pycil.qninhdt.com public < /dev/null
  sleep 10
  if (( sample >= 12 && sample % 6 == 0 )); then
    run exec -T "api-$next" python -c "$(cat infra/vps/observe.py)" "$PROMETHEUS_URL" "$image"
  fi
done
if [[ "$action" = deploy ]]; then
  cp "$release" "$DEPLOY_STATE_DIR/$next.next.json"
  mv "$DEPLOY_STATE_DIR/$next.next.json" "$DEPLOY_STATE_DIR/$next.json"
fi
printf '%s\n' "$old" > "$DEPLOY_STATE_DIR/previous"
printf '%s\n' "$next" > "$DEPLOY_STATE_DIR/active.next"
mv "$DEPLOY_STATE_DIR/active.next" "$DEPLOY_STATE_DIR/active"
rm -f "$DEPLOY_STATE_DIR/pending"
switched=no
# The new release is committed; failure to stop the retired slot must not stop it.
trap - EXIT INT TERM
# Caddy's stream-close delay has elapsed; native Uvicorn/Taskiq stop budgets apply.
run stop "${old_services[@]}"
echo "deploy: $action completed; active=$next source=$sha"
