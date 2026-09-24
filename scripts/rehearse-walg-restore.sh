#!/usr/bin/env bash
# Rehearse a WAL-G base backup and a point-in-time restore against an isolated
# cluster. Never touches a deployed database.
#
# Why this exists: `wal-g backup-list` succeeding proves a backup was *written*,
# not that it can boot a cluster. Only a fetch into empty PGDATA and a replay to a
# chosen time proves recoverability, and that is the claim the runbook makes.
#
# The three things this asserts, in order:
#   1. archiving is live and WAL segments reach the bucket;
#   2. a base backup can be fetched into fresh PGDATA;
#   3. replay reaches a chosen target and the rows written *before* it are present
#      while rows written *after* it are absent — which is what makes it a
#      point-in-time restore rather than a restore of whatever was latest.
#
# Usage: ./scripts/rehearse-walg-restore.sh
set -euo pipefail

COMPOSE_FILE="docker-compose.walg-rehearsal.yml"
SOURCE="postgres"
TARGET="postgres-restore"
REHEARSAL_PORT=5499
# The port the deployed stack uses. Refusing to run against it is the guard that
# turns "I aimed this at the wrong database" from a silent disaster into a stop.
DEPLOYED_PORT=5434

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
psql_src() { compose exec -T -e PGPASSWORD=rehearsal-only "$SOURCE" psql -U pycil -d pycil "$@"; }
psql_tgt() { compose exec -T -e PGPASSWORD=rehearsal-only "$TARGET" psql -U pycil -d pycil "$@"; }
walg_src() { compose exec -T "$SOURCE" wal-g "$@"; }

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
die() { printf '  \033[31mFAIL\033[0m %s\n' "$1" >&2; exit 1; }

step "Guard: the rehearsal must not be aimed at the deployed database"
if ss -ltn 2>/dev/null | grep -q ":${REHEARSAL_PORT} " ; then
  ok "rehearsal cluster listening on ${REHEARSAL_PORT}"
else
  die "nothing is listening on ${REHEARSAL_PORT}; start the rehearsal stack first"
fi
if [ "$REHEARSAL_PORT" = "$DEPLOYED_PORT" ]; then
  die "the rehearsal port equals the deployed port"
fi
ok "rehearsal port ${REHEARSAL_PORT} differs from the deployed ${DEPLOYED_PORT}"

step "1. Archiving is live"
psql_src -tAc "SHOW archive_mode" | grep -qx "on" || die "archive_mode is not on"
psql_src -tAc "SHOW archive_command" | grep -q "wal-g wal-push" || die "archive_command does not use wal-g"
ok "archive_mode=on with the wal-g archive_command"

# The real schema, not a stand-in. Restoring probe tables would prove that
# PostgreSQL can be restored; restoring Pycil's own migrations proves the product
# can be. `DB_URL` is the override that works — Alembic reads `settings.db_url`,
# and `alembic/env.py` sets it from the settings object, so a `DATABASE_URL`
# variable is silently ignored and the migration lands on whatever the settings
# resolve to. That is how a rehearsal once aimed itself at the deployed database.
step "1b. Apply Pycil's own migration chain to the source cluster"
API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/api" && pwd)"
TARGET_DB_URL="postgresql+asyncpg://pycil:rehearsal-only@127.0.0.1:${REHEARSAL_PORT}/pycil"
RESOLVED=$(cd "$API_DIR" && DB_URL="$TARGET_DB_URL" python -c "
from pycil.config import settings
import re
print(re.sub(r'://[^@]+@', '://***@', settings.db_url))
")
case "$RESOLVED" in
  *":${REHEARSAL_PORT}/"*) ok "alembic resolves to ${RESOLVED}" ;;
  *) die "alembic would target ${RESOLVED}, not the rehearsal cluster" ;;
esac
(cd "$API_DIR" && DB_URL="$TARGET_DB_URL" uv run alembic upgrade head >/dev/null 2>&1) \
  || die "the migration chain failed against the rehearsal cluster"
HEAD=$(psql_src -tAc "SELECT version_num FROM alembic_version")
ok "migrations applied; head is ${HEAD}"

# The three schemas a restore has to prove: Pycil's own tables, the embedded Lexi
# schema, and LangGraph's checkpointer tables. The product tables exist from the
# migrations; Lexi and the checkpointer are created by their own owners, so they
# are stood up here.
step "2. Seed a known state across all three schemas"
psql_src -v ON_ERROR_STOP=1 -q <<'SQL'
CREATE SCHEMA IF NOT EXISTS lexi;
CREATE TABLE IF NOT EXISTS lexi.dictionary_probe(id int PRIMARY KEY, headword text);
CREATE TABLE IF NOT EXISTS public.checkpoints(thread_id text PRIMARY KEY, payload jsonb);
INSERT INTO public.users (id, clerk_id, email)
  VALUES ('00000000-0000-4000-8000-000000000001', 'clerk_rehearsal', 'rehearsal@example.test')
  ON CONFLICT DO NOTHING;
INSERT INTO lexi.dictionary_probe VALUES (1, 'before-the-backup') ON CONFLICT DO NOTHING;
INSERT INTO public.checkpoints VALUES ('t-before', '{"step":1}'::jsonb) ON CONFLICT DO NOTHING;
SQL
ok "a product row, a lexi row and a checkpoint row all hold a 'before' value"

step "3. Take a base backup and archive it"
walg_src backup-push /var/lib/postgresql/data >/dev/null 2>&1 || die "backup-push failed"
BACKUP_NAME=$(walg_src backup-list 2>/dev/null | awk 'NR==2{print $1}')
[ -n "$BACKUP_NAME" ] || die "backup-list returned no backup"
ok "base backup written: ${BACKUP_NAME}"

# The recovery target: a row written after the backup but before the cut, and a
# second row written after it. A correct point-in-time restore keeps the first and
# drops the second.
step "4. Write a post-backup row, then force a WAL switch"
psql_src -v ON_ERROR_STOP=1 -q -c "INSERT INTO lexi.dictionary_probe VALUES (2, 'after-backup') ON CONFLICT DO NOTHING;"
TARGET_TIME=$(psql_src -tAc "SELECT now()")
psql_src -tAc "SELECT pg_switch_wal()" >/dev/null
ok "recovery target recorded at ${TARGET_TIME}"

sleep 3
psql_src -tAc "INSERT INTO lexi.dictionary_probe VALUES (3, 'after-target') ON CONFLICT DO NOTHING;" >/dev/null
psql_src -tAc "SELECT pg_switch_wal()" >/dev/null
ARCHIVED=$(psql_src -tAc "SELECT archived_count FROM pg_stat_archiver")
FAILED=$(psql_src -tAc "SELECT failed_count FROM pg_stat_archiver")
[ "$FAILED" = "0" ] || die "archiver reported ${FAILED} failures"
ok "archived_count=${ARCHIVED}, failed_count=0"

walg_src wal-verify integrity 2>/dev/null | grep -q "OK" || die "wal-verify integrity did not report OK"
ok "wal-verify integrity: OK"

step "5. Fetch the base backup into fresh PGDATA"
compose --profile restore up -d "$TARGET" >/dev/null 2>&1
# The stock entrypoint initialises an empty cluster; that has to be cleared so the
# fetch lands in genuinely empty PGDATA rather than on top of a template database.
compose exec -T "$TARGET" sh -c 'rm -rf /var/lib/postgresql/data/* /var/lib/postgresql/data/.[!.]* 2>/dev/null || true'
compose exec -T "$TARGET" sh -c 'wal-g backup-fetch /var/lib/postgresql/data "$0"' "$BACKUP_NAME" >/dev/null 2>&1 \
  || die "backup-fetch failed"
ok "fetched ${BACKUP_NAME} into fresh PGDATA"

step "6. Replay to the target time"
compose exec -T "$TARGET" sh -c "
  cat > /var/lib/postgresql/data/postgresql.auto.conf <<EOF
restore_command = 'wal-g wal-fetch %f %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
EOF
  touch /var/lib/postgresql/data/recovery.signal
  chown -R postgres:postgres /var/lib/postgresql/data
  chmod 700 /var/lib/postgresql/data
"
compose exec -T -u postgres "$TARGET" postgres -D /var/lib/postgresql/data -c config_file=/var/lib/postgresql/data/postgresql.conf >/tmp/walg-restore.log 2>&1 &
RESTORE_PID=$!
for _ in $(seq 1 60); do
  if psql_tgt -tAc "SELECT 1" >/dev/null 2>&1; then break; fi
  sleep 2
done
psql_tgt -tAc "SELECT 1" >/dev/null 2>&1 || { tail -20 /tmp/walg-restore.log; die "restored cluster did not accept connections"; }
ok "restored cluster is accepting connections"

step "7. Assert the point-in-time boundary and all three schemas"
BEFORE=$(psql_tgt -tAc "SELECT headword FROM lexi.dictionary_probe WHERE id=1")
AFTER_BACKUP=$(psql_tgt -tAc "SELECT headword FROM lexi.dictionary_probe WHERE id=2")
AFTER_TARGET=$(psql_tgt -tAc "SELECT count(*) FROM lexi.dictionary_probe WHERE id=3")
USER_ROW=$(psql_tgt -tAc "SELECT email FROM public.users WHERE clerk_id='clerk_rehearsal'")
TABLES=$(psql_tgt -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")
CHECKPOINT=$(psql_tgt -tAc "SELECT payload->>'step' FROM public.checkpoints WHERE thread_id='t-before'")
HEAD_AFTER=$(psql_tgt -tAc "SELECT version_num FROM alembic_version")

[ "$BEFORE" = "before-the-backup" ] || die "the pre-backup row is missing"
[ "$AFTER_BACKUP" = "after-backup" ] || die "the post-backup pre-target row is missing"
[ "$AFTER_TARGET" = "0" ] || die "the post-target row is present; replay overshot the target"
[ "$USER_ROW" = "rehearsal@example.test" ] || die "the product users row did not restore"
[ "$CHECKPOINT" = "1" ] || die "the checkpoint table did not restore"
[ "$HEAD_AFTER" = "$HEAD" ] || die "the restored schema is at ${HEAD_AFTER}, not the backed-up ${HEAD}"
[ "$TABLES" -ge 5 ] || die "only ${TABLES} public tables restored; the product schema is missing"
ok "lexi: pre-backup and pre-target rows present, post-target row absent"
ok "public: ${TABLES} tables restored, alembic head ${HEAD_AFTER}, users row intact"
ok "checkpoints: restored (step ${CHECKPOINT})"

step "8. Measured RPO"
LAG=$(psql_src -tAc "SELECT COALESCE(EXTRACT(EPOCH FROM now() - last_archived_time)::int, -1) FROM pg_stat_archiver")
ok "archive lag at the end of the rehearsal: ${LAG}s (RPO is bounded by archive_timeout=60s)"

kill "$RESTORE_PID" 2>/dev/null || true
printf '\n\033[1;32mRehearsal passed.\033[0m\n'
printf 'Tear down with (the profile flag matters — the restore container is behind it):\n'
printf '  docker compose -f %s --profile restore down -v\n' "$COMPOSE_FILE"
