#!/usr/bin/env bash
# Regenerate the bcrypt hash for the Dex static-password user.
#
# Dex needs a $2a$/$2b$/$2y$ bcrypt hash for staticPasswords[].hash. Run this
# if you change the local test password, then paste the output into
# infra/dex/config.yaml.
#
# Usage: ./infra/dex/gen-bcrypt.sh [password]   (default: password123)
set -euo pipefail

PASSWORD="${1:-password123}"

if command -v htpasswd >/dev/null 2>&1; then
  htpasswd -bnBC 10 "" "$PASSWORD" | tr -d ':\n'
  echo
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "import bcrypt,sys;print(bcrypt.hashpw(sys.argv[1].encode(),bcrypt.gensalt(10)).decode())" "$PASSWORD"
else
  echo "need htpasswd or python3 (with bcrypt) to generate the hash" >&2
  exit 1
fi
