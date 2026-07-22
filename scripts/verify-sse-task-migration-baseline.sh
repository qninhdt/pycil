#!/usr/bin/env bash
# Capture a reproducible, read-only Pycil migration/job baseline before the
# SSE task migration. Requires DATABASE_URL or PYCIL_DATABASE_URL for psql.
set -euo pipefail

DATABASE_DSN="${PYCIL_DATABASE_URL:-${DATABASE_URL:-}}"
if [[ -z "$DATABASE_DSN" ]]; then
  echo "Set PYCIL_DATABASE_URL (or DATABASE_URL) to a PostgreSQL DSN." >&2
  exit 2
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPECTED_HEAD="0015_async_task_deliveries"
ACTUAL_HEAD="$(cd "$PROJECT_DIR/apps/api" && uv run alembic heads | awk 'NR == 1 { print $1 }')"
if [[ "$ACTUAL_HEAD" != "$EXPECTED_HEAD" ]]; then
  echo "Expected Pycil migration head $EXPECTED_HEAD; found $ACTUAL_HEAD." >&2
  exit 3
fi

psql "$DATABASE_DSN" -X -v ON_ERROR_STOP=1 -Atc "
WITH generations AS (
  SELECT
    count(*) AS total,
    count(*) FILTER (WHERE status IN ('queued', 'running')) AS active,
    count(*) FILTER (WHERE status IN ('succeeded', 'failed')) AS terminal,
    coalesce(md5(string_agg(id::text || ':' || status || ':' || coalesce(result::text, ''), ',' ORDER BY id)), md5('')) AS checksum
  FROM word_generations
), sequences AS (
  SELECT coalesce(jsonb_object_agg(sequence_name, last_value), '{}'::jsonb) AS values
  FROM information_schema.sequences s
  CROSS JOIN LATERAL pg_sequence_last_value(format('%I.%I', s.sequence_schema, s.sequence_name)::regclass) AS last_value
  WHERE s.sequence_schema = 'public'
)
SELECT json_build_object(
  'capturedAt', now(),
  'migrationHead', '$EXPECTED_HEAD',
  'wordGenerations', json_build_object('total', total, 'active', active, 'terminal', terminal, 'checksum', checksum),
  'sequences', values
)::text
FROM generations CROSS JOIN sequences;"
