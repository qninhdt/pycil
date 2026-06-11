# Pycil Production Rehabilitation — Final Report

**Date:** 2026-06-11
**Plan:** `plans/260610-1157-pycil-production-rehabilitation/`
**Branches:** per-phase `rehab/N-*` → integrated on `rehab/main` (14 phases)
**Status:** all 14 phases complete. App NOT yet deployed; NO production data.

This report is the owner-facing close-out of the 14-phase rehabilitation. It
records what changed, the new testing / infra / CI strategies, the day-to-day
workflows, and — most importantly — the **remaining risks, tech debt, and items
that need an owner decision** before launch.

---

## 1. Executive summary

The rehabilitation took a feature-complete-but-messy codebase and made it
*coherent*: dead features removed at the root (services + schema + tests), the
test suite re-layered into unit/integration/e2e with honest markers, telemetry
made truthful, infra collapsed into a clean base+overlay compose model, and CI
split into a fast PR gate plus a hardened nightly real-LLM suite. Two latent
build/CI bugs that would have broken the first real PR and the first prod deploy
were found by scouting and fixed.

No behavioral feature regressions: the kept feature set (auth, decks, LLM
enrichment, MCQ/Write/Fill questions, ELO sessions, public decks, TTS,
translation, chat, test-mode) still passes its suites. The changes were
subtractive (dead code/schema), structural (layout/markers/compose/CI), and
honesty-restoring (docstrings/docs), not feature-altering.

---

## 2. What changed, phase by phase

Each phase shipped on its own branch and merged to `rehab/main`; each has a
detailed report in `plans/260610-1157-pycil-production-rehabilitation/artifacts/`.

| Phase | Scope | Outcome |
|---|---|---|
| 1 | Baseline & safety net | Captured baseline schema/tables/test state as artifacts; established the per-phase test-gate discipline. |
| 2 | Backend descope | Removed dead services; **kept** `data_retention_service` (GDPR purge) and re-wired it into the existing cron (owner decision). Surfaced me_extras/saved-search keep-vs-delete as owner items. |
| 3 | Schema & migration cleanup | Single forward-only "drop dead-feature tables" migration (0025). No history editing. |
| 4 | Web & worker dead-code removal | Removed unreachable FE/worker code tied to dropped features. |
| 5 | Service defrag & route cleanup | Consolidated fragmented services; `learning_service` split kept its public facade so callers/tests stay bound. (Owner decision: "easy to maintain, no tech debt".) |
| 6 | Dev artifact & comment-noise cleanup | Stripped scratch artifacts and plan-reference comments from code. |
| 7 | Project structure & naming | Standardized layout + kebab-case descriptive filenames. |
| 8 | Config consolidation | Centralized env/config; preserved deployed secret aliases (do NOT rename — they are live secret names). |
| 9 | Test strategy redesign | Three layers + directory-driven markers; coverage gate ≥70%. No padding-deletion that would hide gaps. (Owner decision on approach.) |
| 10 | LLM real-capability testing | Logic unit tests (classify/fallback/structured-output) + gated `llm_live` real-LLM contract suite (opt-in `RUN_LLM_LIVE=1`). Zero production changes. |
| 11 | Telemetry & observability | Central stdlib JSON log config so `extra={}` fields actually serialize; fixed the telemetry docstring (traces-only; metrics deferred). MeterProvider deferred per the plan's own red-team. |
| 12 | Infra & compose redesign | base (=prod) + ONE non-prod overlay; DRY via YAML anchors; killed the `cp Caddyfile` footgun via env-selected mount; non-root Dockerfiles; worker healthcheck in base. |
| 13 | CI/CD redesign | PR gate split lint/unit/integration; hardened nightly `llm_live`; fixed deploy build contexts + added worker readiness gate + compose-sync-to-host. Removed the 9233-line committed `release-manifest.json`. |
| 14 | Docs reconciliation & this report | Scope lists reconciled to shipped reality; this report. |

---

## 3. What was removed (deliberate — not deferred)

So future devs don't "re-add" them thinking they were forgotten:

- `SHORTCUT` node type + `shortcut_attributes`.
- Definition topic/usage tags (`definitions.tags`).
- i18n (next-intl).
- Payments / premium tier (Stripe scaffold may remain inert — see tech debt).
- Mobile native app.
- Loki / Tempo / Grafana log+metrics stack.
- Assorted dead services removed in Phase 2 (see phase-02 report for the table).

## 4. What ships that the original plan called out-of-scope

These were marked "deferred" in the old PDR/README but DO ship and are KEPT:

- Public / cloned decks.
- TTS (server-rendered audio via worker → S3-compatible storage).
- Definition translation.
- Sentry error reporting + OpenTelemetry tracing (both opt-in, no-op when their
  env is unset).
- Backups (opt-in restic compose profile).

Docs (`README.md`, `docs/project-overview-pdr.md`, `docs/system-architecture.md`)
were reconciled in Phase 14 to state this accurately.

---

## 5. New testing strategy

Three layers, markers applied by directory (see `docs/testing-strategy.md`):

- **unit** (`-m unit`): pure logic, NO I/O, NO network. Exception classifiers,
  fallback-chain hops with fake clients, structured-output parse, the JSON log
  formatter. Runs with no Postgres.
- **integration** (`-m "not unit and not llm_live"`): real Postgres
  (pytest-postgresql, self-provisioning) + fakeredis. Carries the coverage gate
  (`--cov-fail-under=70`).
- **e2e**: Playwright against a real stack with the LLM **stubbed** (deterministic,
  no spend). Anti-fake-green guards in `run-e2e.sh` preserved.
- **llm_live** (`-m llm_live`, opt-in `RUN_LLM_LIVE=1`): real OpenRouter contract
  tests (term-gen, MCQ, judge, translate). Skipped everywhere unless explicitly
  enabled; runs only in the hardened nightly.

**Mock policy:** mock at the process boundary (LLM client, external HTTP), never
the database — integration tests hit a real PG. `llm_live` mocks nothing.

Current results (this session, suites run individually):
- core: green (gate met) — see §11 for the recorded numbers.
- worker: **105 passed, 5 skipped, 78.30% coverage** (gate ≥70%).

---

## 6. New infrastructure strategy

- **`docker-compose.yml` = base = production.** Used ALONE in prod (no overlay).
  No DB/Redis host ports; only Caddy binds 80/443.
- **`docker-compose.staging.yml` = the single non-prod overlay** for local dev +
  E2E: loopback-only host ports, `--reload`, LLM stub flags, Dex + MinIO local
  stand-ins, bind-mounted source. Explicitly NOT named `docker-compose.override.yml`
  so it can never auto-merge into a bare prod `docker compose`.
- **No second `local.yml`.** A separate local overlay would duplicate ~90% of the
  staging overlay; one non-prod overlay is the no-debt model for this topology
  (owner-confirmed in Phase 12).
- **DRY via YAML anchors:** `x-backend-env` + `x-depends-stores` in base;
  `x-s3-env` in the overlay.
- **Caddyfile selected by env, not `cp`:** `${CADDYFILE:-./Caddyfile}`. Prod
  (base-only) always gets the prod Caddyfile; the tracked file is never
  overwritten. Local sets `CADDYFILE=./Caddyfile.local`. Both Caddyfiles now
  carry the same `auth` + `admin` 404 defense-in-depth blocks.
- **Both Dockerfiles run non-root** (`appuser`, uid 10001).
- **Worker healthcheck lives in base**, so prod is health-gated too.

## 7. Workflows (day-to-day)

**Local dev:**
```bash
cp .env.example .env        # fill secrets
export CADDYFILE=./Caddyfile.local
docker compose up --build
docker compose run --rm pycil-core alembic upgrade head
```

**One-command local staging (real LLM, host web on :3100):**
```bash
make staging        # backend in compose + host `next dev`, real OpenRouter
make staging-down   # tears down stack + host web (process-group kill)
```

**Testing:**
```bash
make test           # core + worker
make test-core / make test-worker
make test-unit      # -m unit (fast, no DB)
make test-integration
# IMPORTANT: do NOT run test-core and test-worker in parallel against the same
# local :55432 Postgres — they race CREATE DATABASE. Run sequentially, or set
# distinct PYTEST_PG_DBNAME per run (the conftest reads it).
```

**E2E:** `cd apps/web && pnpm e2e` (LLM stubbed; anti-fake-green guards enforced).

**Real-LLM contract tests:** never local-by-default. `RUN_LLM_LIVE=1` +
`OPENROUTER_API_KEY` (real, not `test-fake`). Runs in the nightly only.

## 8. CI/CD workflow

| Trigger | Jobs |
|---|---|
| **PR → main/dev** | lint (ruff) · unit (no DB) · integration (real PG + coverage gate) · caddy-validate · e2e (LLM stub) |
| **push → main** | deploy: caddy-validate → build/push ghcr → validate base-only compose → scp compose to host → SSH migration-then-swap (pg_dump → upgrade head → up -d) → core health gate → **worker health gate** |
| **nightly (cron 03:17 UTC)** | full integration + coverage; gated real-LLM `llm_live` |
| **manual (workflow_dispatch)** | `llm_live` on demand (boolean input) |

- unit/integration are separable; both assert `--collect-only` collects >0 so a
  mis-selected marker fails loudly instead of silently skipping.
- `llm_live` is gated behind a GitHub Environment (`llm-live`, required reviewer
  + low-budget scoped key), runs NEVER on PRs, masks the key, uploads no raw LLM
  output. Cheapest model + `OPENROUTER_BUDGET_DAILY_USD=1`.

---

## 9. Remaining risks

- **No real CI/deploy run has happened yet.** Every rehab phase was validated
  locally; the pipeline is structurally correct and locally simulated, but the
  first real PR to `main` and first push-to-main deploy are the true smoke tests.
  Two latent bugs were already fixed (CI Postgres DSN, deploy build context) —
  there may be others only a live run surfaces.
- **`make staging` not booted live this session** (no Docker stack spun up; the
  compose model was validated via `docker compose config` only). Recommend one
  real `make staging` smoke before launch.
- **0025 is a destructive table-drop migration.** No data-loss risk today (no
  prod data), but deploy.yml still has no automatic restore branch — the safety
  net is the pre-deploy `pg_dump` + the README image-swap-before-downgrade runbook.

## 10. Remaining tech debt

- **Test-DB harness foot-gun:** core + worker conftests default to the SAME local
  Postgres (`:55432`) and DB name; running both suites in parallel races
  `CREATE DATABASE`. Mitigation is documentation (run sequentially or set
  `PYTEST_PG_DBNAME`); a cleaner fix would default the two suites to distinct DB
  names. Low priority.
- **Stripe billing scaffold** may remain inert in the tree though payments are
  out of scope — confirm whether to remove or keep dormant.
- **deploy rollback/restore branch** (Critical-2) deferred as pre-launch hygiene.
- **0025-drop manual-approval gate** intentionally not added while unreleased.

## 11. Final validation (recorded)

Run individually (NOT in parallel — see §10):
- **pycil-core:** `make test-core` → exit 0, **495 passed, 9 skipped, 1 xfailed,
  79.32% coverage** (gate ≥70%).
- **worker:** `make test-worker` → exit 0, **105 passed, 5 skipped, 78.30%
  coverage** (gate ≥70%).
- **compose:** `docker compose -f docker-compose.yml config` (base-only) valid;
  `+ -f docker-compose.staging.yml` valid.
- **caddy:** `caddy validate` passes both Caddyfiles; auth+admin 404 parity asserted.
- **workflows:** test.yml / nightly.yml / deploy.yml all parse as valid YAML.

Note: a first parallel run of both suites produced 5 errors each — root-caused to
orphaned test-DB state from the parallel race (not a code regression), cleaned,
and both suites re-run green individually.

## 12. Items needing owner input (decision required before launch)

1. **Prod 0025 table-drop approval + tested restore runbook** [Critical-2]. Build
   the deploy rollback branch (image-swap → `psql < pre-deploy-*.sql` →
   downgrade in the 0019-0021 window per README) before first real deploy.
2. **GDPR data-retention purge ownership/scheduling** [High-6]. `data_retention_service`
   is wired to the cron (Phase 2) — confirm cadence + that it is the intended
   purge owner.
3. **Env-var alias deprecation windows** [High-13]. Some env names are legacy
   (e.g. S3 on old `B2_*` aliases). Renaming drops the deployed value — decide
   deprecation windows; do NOT rename live secret names without one.
4. **Is `/opt/pycil/docker-compose.yml` version-controlled on the host?** [FMA-6].
   Phase 13 adds an scp-of-compose step making the repo file authoritative; confirm
   no hand-edited host drift you want to keep.
5. **me_extras / saved-search keep-vs-delete** [High-7, Sec-5]. Surfaced in the
   Phase 2 report; left in place pending your call.
6. **GitHub repo settings for nightly:** the `llm-live` Environment (with required
   reviewer + low-budget scoped key) and the `OPENROUTER_API_KEY` secret must
   exist for the nightly real-LLM job to run.

## 13. Plans archive note

The 14-phase rehab plan and its per-phase artifacts live under
`plans/260610-1157-pycil-production-rehabilitation/` (gitignored — on-disk
reference, not version-controlled). Earlier superseded plan dirs (p1-p12 rollout
etc.) are retained on disk for roadmap intent, not deleted. No `/ck:plan archive`
run this session — archival is a housekeeping step the owner can trigger; nothing
depends on it.
