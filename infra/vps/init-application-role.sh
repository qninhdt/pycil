#!/bin/sh
set -eu

# The image runs this only when initializing an empty PostgreSQL data directory.
psql -X -h /var/run/postgresql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_user="$APP_DB_USER" --set=app_password="$APP_DB_PASSWORD" \
    --set=app_database="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'app_password';
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
ALTER DATABASE :"app_database" OWNER TO :"app_user";
SQL
