#!/usr/bin/env bash
# Re-run every test tier and assert a minimum test count, not just exit status.
#
# Exit status alone is not enough. A collection error can yield "0 tests, exit 0"
# in some tiers, which reads as green while asserting nothing. Each tier below
# therefore parses the count out of pytest/vitest output and fails if it falls
# below a floor measured against a known-good tree.
#
# Floors are lower bounds, not equalities: adding tests must never fail the gate.
# A count that *drops* means a test was deleted, and that needs a stated reason.
#
# Usage:
#   scripts/verify-baseline.sh              # python + web unit tiers (~5 min)
#   scripts/verify-baseline.sh --with-web   # adds typecheck/lint/build/storybook
#   scripts/verify-baseline.sh --quick      # python tiers only
#
# E2E is deliberately NOT here: it needs a live stack plus a real LLM, runs for
# ~11 minutes, and is gated by test-ID manifest rather than by count. See
# scripts/verify-e2e-manifest.sh.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEXI_ROOT="${LEXI_ROOT:-$(cd "$REPO_ROOT/../lexi-ai" 2>/dev/null && pwd || true)}"

# Floors measured 2026-08-06 against a green tree. Raise them when a tier grows
# permanently; never lower one without recording why. Overridable by environment
# so CI can tighten a floor, and so the gate itself can be probed for falsifiability.
FLOOR_API="${FLOOR_API:-497}"
FLOOR_WORKER="${FLOOR_WORKER:-50}"
FLOOR_SHARED="${FLOOR_SHARED:-13}"
FLOOR_WEB_UNIT="${FLOOR_WEB_UNIT:-114}"
FLOOR_LEXI="${FLOOR_LEXI:-628}"

# Coverage floors, applied only to a whole-suite run. They live here rather than in
# each package's `addopts` because a threshold there also judges a single-file run,
# which fails with every test passing and trains people to pass `--no-cov`.
# `api` was measured at 83.07% over 4,703 statements; the other two carry the
# values they were already gated at.
COV_API="${COV_API:-82}"
COV_WORKER="${COV_WORKER:-81}"
COV_SHARED="${COV_SHARED:-78}"

WITH_WEB_BUILD=0
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --with-web) WITH_WEB_BUILD=1 ;;
    --quick) QUICK=1 ;;
    -h|--help) sed -n '2,19p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# Two tiers skip themselves when a Postgres DSN is absent, and a skipped tier
# proves nothing while reporting the same green as a passing one.
#
# Lexi's Postgres tier silently shrinks the suite by 10 tests. The worker's
# reconciler tests are worse: those six stand between the 24h purge and a
# learner's answer text, and they had never run locally or in CI.
#
# Both are pointed at the compose database when the caller has not chosen one,
# and Lexi's REQUIRE flag makes a broken connection loud rather than quiet.
if [[ -f "$REPO_ROOT/.env" ]]; then
  _pg_password="$(grep -m1 '^POSTGRES_PASSWORD=' "$REPO_ROOT/.env" | cut -d= -f2- || true)"
  _pg_user="$(grep -m1 '^POSTGRES_USER=' "$REPO_ROOT/.env" | cut -d= -f2- || true)"
  _pg_db="$(grep -m1 '^POSTGRES_DB=' "$REPO_ROOT/.env" | cut -d= -f2- || true)"
  _pg_port="$(docker compose -f "$REPO_ROOT/docker-compose.yml" port postgres 5432 2>/dev/null | sed 's/.*://' || true)"
  if [[ -n "$_pg_password" && -n "$_pg_port" ]]; then
    _pg_dsn="postgresql+asyncpg://${_pg_user:-pycil}:${_pg_password}@127.0.0.1:${_pg_port}"
    if [[ -z "${LEXI_TEST_PG_URL:-}" ]]; then
      export LEXI_TEST_PG_URL="${_pg_dsn}/${_pg_db:-pycil}"
      export LEXI_REQUIRE_PG=1
    fi
    # A database of its own, because these tests `drop_all`/`create_all`: pointing
    # them at the live compose database would erase it.
    if [[ -z "${WORKER_TEST_DB_URL:-}" ]]; then
      _compose=("docker" "compose" "-f" "$REPO_ROOT/docker-compose.yml" "exec" "-T" "postgres")
      "${_compose[@]}" createdb -U "${_pg_user:-pycil}" pycil_worker_test >/dev/null 2>&1 || true
      if [[ "$("${_compose[@]}" psql -U "${_pg_user:-pycil}" -d "${_pg_db:-pycil}" -tAc \
                "SELECT 1 FROM pg_database WHERE datname='pycil_worker_test'" 2>/dev/null | tr -d '[:space:]')" == "1" ]]; then
        export WORKER_TEST_DB_URL="${_pg_dsn}/pycil_worker_test"
      fi
    fi
  fi
fi

RESULTS=()
FAILED=0

record() { # name status detail
  RESULTS+=("$1|$2|$3")
  [[ "$2" == "PASS" ]] || FAILED=1
}

# Pull "431 passed" out of a pytest/vitest tail. Prints 0 when absent, so a
# missing count is a floor failure rather than an accidental pass.
extract_count() {
  local output="$1" pattern="$2"
  grep -oE "$pattern" <<<"$output" | grep -oE '[0-9]+' | head -1 || true
}

run_pytest_tier() { # label dir test_floor coverage_floor extra_args...
  local label="$1" dir="$2" floor="$3" cov_floor="$4"; shift 4
  printf '\n\033[1m── %s ──\033[0m\n' "$label"

  if [[ ! -d "$dir" ]]; then
    record "$label" "SKIP" "directory absent: $dir"
    printf '  skipped (no %s)\n' "$dir"
    return
  fi

  local output status count coverage
  # The coverage threshold is passed here rather than living in the package's
  # `addopts`, because there it also applies to a single-file run: `pytest
  # tests/one_file.py` would report failure with every test passing, which teaches
  # people to pass `--no-cov` and then the gate protects nothing. Each package
  # measures coverage on every run; only the whole-suite run judges it.
  output="$(cd "$dir" && uv run pytest -q --cov-fail-under="$cov_floor" "$@" 2>&1)"
  status=$?
  tail -3 <<<"$output"

  count="$(extract_count "$output" '[0-9]+ passed')"
  count="${count:-0}"
  coverage="$(grep -oE 'Total coverage: [0-9.]+' <<<"$output" | grep -oE '[0-9.]+' | head -1)"

  if (( status != 0 )); then
    record "$label" "FAIL" "pytest exit $status ($count passed, coverage ${coverage:-?}%)"
  elif (( count < floor )); then
    record "$label" "FAIL" "$count passed, floor $floor"
  else
    record "$label" "PASS" "$count passed (floor $floor), coverage ${coverage:-?}% (floor $cov_floor)"
  fi
}

run_pytest_tier "api"       "$REPO_ROOT/apps/api"           "$FLOOR_API"    "$COV_API"
run_pytest_tier "worker"    "$REPO_ROOT/apps/worker"        "$FLOOR_WORKER" "$COV_WORKER"
run_pytest_tier "shared-py" "$REPO_ROOT/packages/shared-py" "$FLOOR_SHARED" "$COV_SHARED"

# ---- Import boundaries (api + worker) ---------------------------------------
# shared-py declares no contracts: one pure-logic package has no internal
# boundary to enforce, and an empty config that always passes is worse than none.
for _pkg in api worker; do
  printf '\n\033[1m── %s boundaries ──\033[0m\n' "$_pkg"
  _out="$(cd "$REPO_ROOT/apps/$_pkg" && uv run lint-imports 2>&1)"
  _status=$?
  tail -3 <<<"$_out"
  if (( _status == 0 )); then
    record "$_pkg boundaries" "PASS" "$(grep -oE '[0-9]+ kept' <<<"$_out" | head -1)"
  else
    record "$_pkg boundaries" "FAIL" "contracts broken"
  fi
done

# ---- Foreign-key delete rules against a migrated schema ---------------------
# The test suite cannot see these: conftest builds its schema from the ORM with
# `create_all`, so a rule that differs between a migration and the model is
# invisible to every test. `NO ACTION` is the deliberate default here — account
# deletion's hand-maintained order depends on a forgotten table aborting the
# delete rather than cascading — so this pins the rules rather than demanding
# cascades.
printf '\n\033[1m── fk delete rules ──\033[0m\n'
if [[ -n "${WORKER_TEST_DB_URL:-}" ]]; then
  # The same compose database, addressed synchronously: psycopg, not asyncpg.
  _fk_dsn="${LEXI_TEST_PG_URL/postgresql+asyncpg/postgresql}"
  _fk_out="$(cd "$REPO_ROOT/apps/api" && uv run --with 'psycopg[binary]' python \
      "$REPO_ROOT/scripts/extract-fk-delete-rules.py" "$_fk_dsn" 2>&1)"
  _fk_status=$?
  tail -4 <<<"$_fk_out"
  if (( _fk_status == 0 )); then
    record "fk delete rules" "PASS" "$(grep -oE '[0-9]+ foreign keys' <<<"$_fk_out" | head -1) unchanged"
  else
    record "fk delete rules" "FAIL" "a delete rule changed, appeared or vanished"
  fi
else
  record "fk delete rules" "SKIP" "no database reachable (is the stack up?)"
  printf '  skipped (no database)\n'
fi

# ---- Documentation truth ----------------------------------------------------
# A doc that names a file is making a checkable claim. This repo had accumulated
# false ones from three superseded eras, and a reader cannot tell a stale path
# from one they should go read.
printf '\n\033[1m── doc paths ──\033[0m\n'
if doc_out="$(python3 "$REPO_ROOT/scripts/check-doc-paths.py" 2>&1)"; then
  record "doc paths" "PASS" "$(tail -1 <<<"$doc_out")"
else
  tail -6 <<<"$doc_out"
  record "doc paths" "FAIL" "a doc cites a path that does not exist"
fi

# ---- Module cycles: assert the committed baseline has not regressed ----------
printf '\n\033[1m── module cycles ──\033[0m\n'
BASELINE="$REPO_ROOT/scripts/module-cycles-baseline.json"
if [[ -f "$BASELINE" ]]; then
  # Run under the api venv: the tree uses PEP 695 generics, which a system
  # Python older than 3.12 cannot parse.
  cycle_out="$(cd "$REPO_ROOT/apps/api" && uv run python "$REPO_ROOT/scripts/check-module-cycles.py" \
      "$REPO_ROOT/apps/api/pycil" "$REPO_ROOT/apps/worker/pycil_worker" \
      --baseline "$BASELINE" 2>&1)"
  cycle_status=$?
  tail -4 <<<"$cycle_out"
  if (( cycle_status == 0 )); then
    record "module cycles" "PASS" "no cycle outside baseline"
  else
    record "module cycles" "FAIL" "a new cycle appeared"
  fi
else
  record "module cycles" "SKIP" "no committed baseline"
fi

# ---- Lexi (sibling repo, pinned by SHA) -------------------------------------
printf '\n\033[1m── lexi ──\033[0m\n'
if [[ -n "$LEXI_ROOT" && -d "$LEXI_ROOT" ]]; then
  lexi_out="$(cd "$LEXI_ROOT" && uv run pytest -q 2>&1)"
  lexi_status=$?
  tail -3 <<<"$lexi_out"
  lexi_count="$(extract_count "$lexi_out" '[0-9]+ passed')"
  lexi_count="${lexi_count:-0}"
  if (( lexi_status != 0 )); then
    record "lexi" "FAIL" "pytest exit $lexi_status ($lexi_count passed)"
  elif (( lexi_count < FLOOR_LEXI )); then
    record "lexi" "FAIL" "$lexi_count passed, floor $FLOOR_LEXI"
  else
    record "lexi" "PASS" "$lexi_count passed (floor $FLOOR_LEXI)"
  fi

  printf '\n\033[1m── lexi boundaries ──\033[0m\n'
  # import-linter exits 0 only when every contract is kept.
  imports_out="$(cd "$LEXI_ROOT" && uv run lint-imports 2>&1)"
  imports_status=$?
  tail -3 <<<"$imports_out"
  if (( imports_status == 0 )); then
    record "lexi boundaries" "PASS" "$(grep -oE '[0-9]+ kept' <<<"$imports_out" | head -1)"
  else
    record "lexi boundaries" "FAIL" "contracts broken"
  fi
else
  record "lexi" "SKIP" "sibling repo not found (set LEXI_ROOT)"
  record "lexi boundaries" "SKIP" "sibling repo not found"
fi

# ---- Web -------------------------------------------------------------------
if (( QUICK == 0 )); then
  printf '\n\033[1m── web unit ──\033[0m\n'
  web_out="$(cd "$REPO_ROOT/apps/web" && pnpm test:unit 2>&1)"
  web_status=$?
  tail -5 <<<"$web_out"
  # vitest prints "Tests  86 passed (86)"
  web_count="$(grep -oE 'Tests +[0-9]+ passed' <<<"$web_out" | grep -oE '[0-9]+' | head -1)"
  web_count="${web_count:-0}"
  if (( web_status != 0 )); then
    record "web unit" "FAIL" "vitest exit $web_status ($web_count passed)"
  elif (( web_count < FLOOR_WEB_UNIT )); then
    record "web unit" "FAIL" "$web_count passed, floor $FLOOR_WEB_UNIT"
  else
    record "web unit" "PASS" "$web_count passed (floor $FLOOR_WEB_UNIT)"
  fi

  printf '\n\033[1m── design audit ──\033[0m\n'
  if (cd "$REPO_ROOT/apps/web" && pnpm audit:design >/dev/null 2>&1); then
    record "design audit" "PASS" "clean"
  else
    record "design audit" "FAIL" "see pnpm audit:design"
  fi
fi

if (( WITH_WEB_BUILD == 1 )); then
  for target in typecheck lint build build-storybook; do
    printf '\n\033[1m── web %s ──\033[0m\n' "$target"
    if (cd "$REPO_ROOT/apps/web" && pnpm "$target" >/dev/null 2>&1); then
      record "web $target" "PASS" "clean"
    else
      record "web $target" "FAIL" "see pnpm $target"
    fi
  done
fi

# ---- Summary ---------------------------------------------------------------
printf '\n\033[1m═══ baseline summary ═══\033[0m\n'
printf '%-20s %-6s %s\n' "TIER" "STATUS" "DETAIL"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r name status detail <<<"$row"
  case "$status" in
    PASS) colour='\033[32m' ;;
    FAIL) colour='\033[31m' ;;
    *)    colour='\033[33m' ;;
  esac
  printf "%-20s ${colour}%-6s\033[0m %s\n" "$name" "$status" "$detail"
done

if (( FAILED == 1 )); then
  printf '\n\033[31mBASELINE RED\033[0m — a tier failed or fell below its floor.\n'
  exit 1
fi
printf '\n\033[32mBASELINE GREEN\033[0m — every tier met its floor.\n'
