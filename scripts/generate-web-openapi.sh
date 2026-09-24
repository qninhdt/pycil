#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_FILE="$(mktemp)"
trap 'rm -f "$SPEC_FILE"' EXIT

(
  cd "$ROOT_DIR/apps/api"
  uv run python -c 'import json; from pathlib import Path; from pycil.main import create_app; Path("'"$SPEC_FILE"'").write_text(json.dumps(create_app().openapi()))'
)

cd "$ROOT_DIR"
pnpm dlx openapi-typescript "$SPEC_FILE" \
  -o apps/web/lib/api/generated/openapi.ts
