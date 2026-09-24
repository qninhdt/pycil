#!/usr/bin/env bash
# Rehearse deploy.sh's failure behaviour against a sandbox stack.
#
# The point is the two paths a deploy must not get wrong: a failed migration has
# to abort before anything is swapped, and a health failure after a successful
# migration has to roll the images back and say so. Neither can be tested against
# a real deployment, which is why the sandbox exists.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX="${SANDBOX:-$(mktemp -d -t pycil-deploy-rehearsal-XXXXXX)}"
mkdir -p "$SANDBOX/scripts" "$SANDBOX/backups"
# The sandbox gets a copy of the real deploy script and its own stand-in stack, so
# nothing here can reach a running deployment.
cp "$REPO/scripts/deploy.sh" "$SANDBOX/scripts/deploy.sh"
cp "$REPO/infra/deploy-rehearsal/docker-compose.yml" "$SANDBOX/docker-compose.yml"
cp "$REPO/infra/deploy-rehearsal/Caddyfile" "$SANDBOX/Caddyfile"
cd "$SANDBOX"
trap 'docker compose down -v >/dev/null 2>&1 || true; rm -rf "$SANDBOX"' EXIT

export POSTGRES_USER=pycil POSTGRES_PASSWORD=rehearsal POSTGRES_DB=pycil
export COMPOSE_PROJECT_NAME=pycil-deploy-rehearsal
mkdir -p backups
printf 'reference artifact\n' > reference.db
REF_SHA="$(sha256sum reference.db | cut -d ' ' -f 1)"

cat > .env <<ENV
POSTGRES_USER=pycil
POSTGRES_PASSWORD=rehearsal
POSTGRES_DB=pycil
LEXI_REFERENCE_DATASET_PATH=${SANDBOX}/reference.db
LEXI_REFERENCE_DATASET_SHA256=${REF_SHA}
ENV

# The stand-in services need a tiny image, referenced by digest because deploy.sh
# refuses anything else. Pulled and resolved here rather than hardcoded, so this
# does not silently depend on the image happening to be cached.
docker pull -q alpine:3.19 >/dev/null 2>&1 || { echo "could not pull alpine:3.19"; exit 1; }
IMG="alpine@sha256:$(docker image inspect alpine:3.19 --format '{{index .RepoDigests 0}}' | sed 's/.*@sha256://')"
[ -n "${IMG#alpine@sha256:}" ] || { echo "could not resolve the alpine digest"; exit 1; }
pass=0; fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail+1)); }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

compose() { docker compose "$@"; }

# The deployed project must be untouched by all of this.
step "Guard: the sandbox project is not the deployed one"
if [ "$COMPOSE_PROJECT_NAME" = "pycil" ]; then bad "sandbox project name collides"; exit 1; fi
ok "project ${COMPOSE_PROJECT_NAME} differs from the deployed 'pycil'"

step "Case 1: a failed migration aborts before anything is swapped"
compose up -d postgres >/dev/null 2>&1
# Wait for readiness rather than sleeping: a previous case's cluster may still be
# shutting down, and a pg_dump into that window fails for a reason that has
# nothing to do with what this case is testing.
for _ in $(seq 1 30); do
  if compose exec -T postgres pg_isready -U pycil -d pycil >/dev/null 2>&1; then break; fi
  sleep 2
done
compose exec -T postgres pg_isready -U pycil -d pycil >/dev/null 2>&1 || { bad "postgres never became ready"; exit 1; }
ok "postgres ready"
BEFORE_WORKER="$(compose ps -q worker 2>/dev/null | head -1)"
MIGRATE_COMMAND="echo 'migration failed' >&2; exit 1" \
  API_IMAGE="$IMG" WORKER_IMAGE="$IMG" WEB_IMAGE="$IMG" \
  BACKUP_DIR="$SANDBOX/backups" bash scripts/deploy.sh > case1.log 2>&1
rc=$?
if [ $rc -ne 0 ]; then ok "deploy exited non-zero on migration failure"; else bad "deploy exited 0 despite a failed migration"; fi
if grep -q "old containers untouched" case1.log; then ok "it aborts before swapping"; else bad "no abort message"; fi
AFTER_WORKER="$(compose ps -q worker 2>/dev/null | head -1)"
if [ "$BEFORE_WORKER" = "$AFTER_WORKER" ]; then ok "the running worker container was not replaced"; else bad "worker changed despite the abort"; fi
if grep -q "no previous image recorded" case1.log; then ok "it reports that nothing was running to roll back to"; fi

step "Case 2: a health failure after a successful migration rolls back"
# The worker must already be running a *recorded* image, because that is what a
# rollback restores. A first-ever deploy has nothing to go back to, which Case 1
# covers separately.
WORKER_HEALTHCHECK="exit 0" compose up -d --force-recreate worker >/dev/null 2>&1
sleep 3
if compose ps -q worker | head -1 | grep -q .; then
  ok "a worker is running with a recorded image to roll back to"
else
  bad "no worker running; the rollback case cannot be set up"
fi
WORKER_COMMAND="sleep 3600" WORKER_HEALTHCHECK="exit 1" \
  API_IMAGE="$IMG" WORKER_IMAGE="$IMG" WEB_IMAGE="$IMG" \
  BACKUP_DIR="$SANDBOX/backups" bash scripts/deploy.sh > case2.log 2>&1
rc=$?
if [ $rc -ne 0 ]; then ok "deploy exited non-zero on a health failure"; else bad "deploy exited 0 despite an unhealthy worker"; fi
if grep -q "rolling back: worker" case2.log; then ok "it rolled the images back"; else bad "no rollback attempt"; fi
if grep -q "The schema was NOT reverted" case2.log; then ok "it does not silently downgrade the schema"; else bad "schema handling is not stated"; fi
if grep -q "rollback values recorded in" case2.log; then ok "it names the rollback record"; else bad "no rollback record named"; fi

step "Case 3: the rollback record is written before the swap"
if ls backups/*.rollback >/dev/null 2>&1; then
  ok "a rollback file exists: $(ls backups/*.rollback | head -1)"
  if grep -q "PREVIOUS_HEAD=" backups/*.rollback; then ok "it records the previous migration head"; else bad "no previous head recorded"; fi
  if grep -q "DB_SNAPSHOT=" backups/*.rollback; then ok "it names the pre-deploy snapshot"; else bad "no snapshot path recorded"; fi
else
  bad "no rollback file was written"
fi

compose down -v >/dev/null 2>&1
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
