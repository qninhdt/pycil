#!/bin/sh
# Validate WAL-G configuration, then hand off to the stock PostgreSQL entrypoint.
#
# A cluster with `archive_mode = on` and a broken `archive_command` starts
# normally and reports healthy while accumulating WAL it will never ship. The
# failure is invisible until a restore, which is the worst time to find it. So the
# two things that must be true are checked before PostgreSQL is allowed to start,
# and a missing one is fatal rather than a warning.
set -eu

if [ -z "${WALG_S3_PREFIX:-}" ]; then
  echo "[walg] WALG_S3_PREFIX is not set; refusing to start an unarchived cluster" >&2
  exit 1
fi

# WAL-G reads libpq's own PG* variables. Without these it defaults to the OS user
# (usually root) and fails with `role "root" does not exist`, which surfaces as a
# failing archive_command rather than as a startup error.
export PGUSER="${PGUSER:-${POSTGRES_USER:-postgres}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-postgres}}"
export PGHOST="${PGHOST:-/var/run/postgresql}"

wal-g --version

# Cheap reachability check: a prefix that cannot be listed cannot be written to,
# and finding that out now beats finding it out on the first WAL switch.
if ! wal-g backup-list >/dev/null 2>&1; then
  echo "[walg] cannot reach ${WALG_S3_PREFIX}; refusing to start" >&2
  exit 1
fi

echo "[walg] archiving to ${WALG_S3_PREFIX} as ${PGUSER}"
exec /usr/local/bin/docker-entrypoint.sh "$@"
