#!/bin/sh
set -eu
psql -X -h /var/run/postgresql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    --set=backup_password="$(cat /run/secrets/walg/backup-password)" \
    --set=monitor_password="$(cat /run/secrets/walg/monitor-password)" <<'SQL'
CREATE ROLE walg_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'backup_password';
GRANT CONNECT ON DATABASE postgres TO walg_backup;
GRANT pg_read_all_settings TO walg_backup;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_backup_start(text, boolean) TO walg_backup;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_backup_stop(boolean) TO walg_backup;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO walg_backup;
CREATE ROLE walg_monitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'monitor_password';
GRANT pg_monitor TO walg_monitor;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SQL
