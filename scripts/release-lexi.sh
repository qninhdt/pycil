#!/usr/bin/env bash
# The cross-repo release, as one reviewable command.
#
# NOT run automatically, and it takes an explicit --confirm. The push to Lexi's
# public `main` is the one irreversible step in this plan: Pycil pins Lexi by SHA,
# so a branch SHA proves Pycil green before anything lands on a public OSS main.
# Pushing first makes the redesign unrollbackable.
#
# This exists so the release is a command rather than seven remembered steps. Every
# one of them is checkable, and the order matters:
#
#   1. Lexi green on its own, including its Postgres tier — nothing downstream can
#      recover from a broken dictionary.
#   2. Push the branch to `main`.
#   3. Re-pin the SHA in apps/api/pyproject.toml.
#   4. Relock BOTH apps/api/uv.lock and apps/worker/uv.lock. The worker embeds Lexi
#      too, and a half-relocked pair means the api and the worker disagree about
#      which dictionary they are running.
#   5. Bump LEXI_DOMAIN_MIGRATION_HEAD wherever it appears. This release adds
#      revision 20260806_01; skipping the bump aborts the `migrate` one-shot after
#      Lexi's schema migrates and before Pycil's, leaving a half-migrated database
#      and a stack that will not boot.
#   6. Rebuild the api and worker images.
#   7. Full baseline, then E2E.
#
# Usage:
#   scripts/release-lexi.sh            # dry run: prints what it would do
#   scripts/release-lexi.sh --confirm  # actually does it

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEXI_ROOT="${LEXI_ROOT:-$(cd "$REPO_ROOT/../lexi-ai" && pwd)}"
LEXI_BRANCH="${LEXI_BRANCH:-redesign/defect-repair-and-ports}"
CONFIRMED=0
[[ "${1:-}" == "--confirm" ]] && CONFIRMED=1

say() { printf '\n\033[1m── %s ──\033[0m\n' "$1"; }
run() {
  if (( CONFIRMED )); then
    printf '  $ %s\n' "$*"
    "$@"
  else
    printf '  would run: %s\n' "$*"
  fi
}

say "preflight"
cd "$LEXI_ROOT"
[[ -z "$(git status --porcelain)" ]] || { echo "lexi-ai has uncommitted changes"; exit 1; }
on="$(git branch --show-current)"
[[ "$on" == "$LEXI_BRANCH" ]] || { echo "lexi-ai is on '$on', expected '$LEXI_BRANCH'"; exit 1; }
NEW_SHA="$(git rev-parse HEAD)"
OLD_SHA="$(grep -oE 'lexi-ai\.git@[0-9a-f]{40}' "$REPO_ROOT/apps/api/pyproject.toml" | cut -d@ -f2)"
printf '  pin %s -> %s\n' "${OLD_SHA:0:12}" "${NEW_SHA:0:12}"
printf '  %s commits ahead of origin/main\n' "$(git log --oneline origin/main..HEAD | wc -l)"

# The migration head this release lands on, read rather than assumed.
NEW_HEAD="$(cd "$LEXI_ROOT" && uv run alembic -c lexi_ai/migrations/alembic.ini heads 2>/dev/null | awk '{print $1}' | head -1)"
OLD_HEAD="$(grep -m1 -oE 'LEXI_DOMAIN_MIGRATION_HEAD=[A-Za-z0-9_]+' "$REPO_ROOT/.env.example" | cut -d= -f2 || true)"
printf '  migration head %s -> %s\n' "${OLD_HEAD:-unset}" "${NEW_HEAD:-unknown}"

say "1. lexi green, including its Postgres tier"
if (( CONFIRMED )); then
  ( cd "$LEXI_ROOT" && uv run pytest -q && uv run lint-imports )
else
  printf '  would run: uv run pytest -q && uv run lint-imports (in %s)\n' "$LEXI_ROOT"
fi

say "2. push to lexi main"
run git -C "$LEXI_ROOT" push origin "HEAD:main"

say "3. re-pin the SHA"
if (( CONFIRMED )); then
  sed -i "s|lexi-ai\.git@${OLD_SHA}|lexi-ai.git@${NEW_SHA}|" "$REPO_ROOT/apps/api/pyproject.toml"
  grep -n "lexi-ai.git@" "$REPO_ROOT/apps/api/pyproject.toml"
else
  printf '  would re-pin apps/api/pyproject.toml to %s\n' "${NEW_SHA:0:12}"
fi

say "4. relock both packages"
run bash -c "cd '$REPO_ROOT/apps/api' && uv lock"
run bash -c "cd '$REPO_ROOT/apps/worker' && uv lock"

say "5. bump LEXI_DOMAIN_MIGRATION_HEAD"
if [[ -n "${NEW_HEAD:-}" && -n "${OLD_HEAD:-}" && "$NEW_HEAD" != "$OLD_HEAD" ]]; then
  for target in "$REPO_ROOT/docker-compose.yml" "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"; do
    [[ -f "$target" ]] || continue
    grep -q "LEXI_DOMAIN_MIGRATION_HEAD" "$target" || continue
    if (( CONFIRMED )); then
      sed -i "s|LEXI_DOMAIN_MIGRATION_HEAD=${OLD_HEAD}|LEXI_DOMAIN_MIGRATION_HEAD=${NEW_HEAD}|" "$target"
      printf '  bumped %s\n' "$(basename "$target")"
    else
      printf '  would bump %s\n' "$target"
    fi
  done
else
  printf '  head unchanged or unreadable — check by hand before continuing\n'
fi

say "6. rebuild the images"
run docker compose -f "$REPO_ROOT/docker-compose.yml" up -d --build api worker

say "7. verify"
run bash "$REPO_ROOT/scripts/verify-baseline.sh"
run bash -c "cd '$REPO_ROOT/apps/web' && npx playwright test --project=chromium"

if (( CONFIRMED )); then
  printf '\n\033[1mReleased.\033[0m Commit the pin and the lockfiles.\n'
else
  printf '\n\033[1mDry run.\033[0m Re-run with --confirm to execute.\n'
fi
