# Full-Project Audit & Refactor — Consolidated Summary

Plan: `plans/260529-0615-full-project-audit-refactor/` (8 phases).
Completed: 2026-05-29. Branch: `main`.

Goal: stabilize + verify the in-flight raw-SQL→SQLModel conversion (checkpoint
`9f07149`), then full adversarial bug hunt across `pycil-core`, `worker`,
`shared-py`, and the Next.js web app. Behavior-preserving; every CONFIRMED bug
proven by source + failing repro, fixed, re-verified green.

## Outcome

| Suite | Baseline | After audit |
|-------|----------|-------------|
| pycil-core (DB-backed) | 12+ failures (conftest `.exec` + model defaults) | 159 pass, 1 xfail (F7), 9 skip, 0 fail |
| worker (DB-backed) | 6 fail + 7 err (never green) | 41 pass, cov 73.5% (gate 70%) |
| web tsc / eslint / build | all FAIL | all green (eslint 0 err) |
| web tests | orphan, no runner | `tsx --test`, 9 pass |
| ruff (core + worker pkgs) | — | clean |

## Bugs fixed by severity

### P1 (data/money/authz/runtime-break)
- **W1** worker `lifecycle.is_terminal()` always False (`sqlalchemy.select`
  scalarization) → idempotency gate defeated, re-runs paid LLM on every retry.
- **W7** `ON CONFLICT (term_id)` references constraint dropped by migration 0012
  → term enrichment + onboarding crash on every new term (`generate_term` +
  `onboarding_service`).
- **W8** `to_jsonb(:param::text)` bind-param parse bug → translate + TTS JSONB
  write-back crash 100%.
- **W10 / F9-class** worker `conftest` SessionLocal built plain SQLAlchemy
  `AsyncSession` (no `.exec`) → why the conversion shipped unverified.

### P2 (correctness)
- **W3/W4** `generate_question` single-col selects return Row not scalar.
- **W9** UUID not JSON-serializable on job `result` write (engine serializer).
- **C-scalar-1** `claim_username` false 409 when re-saving your own username.
- **C-scalar-2** `reverse_card` distractor pool held Rows not strings.
- **C-scalar-3** `me_extras` follow-by-username bound a Row as UUID.
- **C1** `job_service` lock leak on commit failure (term un-enrichable for TTL).
- **FE3** dead study-mode links (`chat`/`test`) → 404.
- **FE6** Next 15 `searchParams` Promise read synchronously → callbackUrl/banners undefined.

### P3 (robustness)
- **D2** `upsert_subscription` dropped `updated_at = NOW()` on conflict-update.
- **PWA1** never-installed `next-pwa` broke tsc/build (custom `sw.js` is the real PWA).
- **FE4** legal pages behind auth middleware.
- 13 `no-explicit-any` lint errors replaced with proper types.

## Parity verdict (Phase 2)
- IDOR/tenancy-predicate parity CLEAN (30 mutations, 0 dropped predicates).
- `isinstance(row, tuple)` RETURNING hack FIXED (F14).
- The `select` import-source → scalarization defect was the conversion's single
  systemic regression class; fixed at every scalar-consumed site, multi-col
  sites left as-is (Row access safe). Full report: `conversion-parity-audit-report.md`.

## Refactor (Phase 7)
- Disciplined no-churn pass. No file modularized: every >200-LOC file is either a
  schema/data file (`models.py`), just-verified this session (re-touch invalidates
  locks), or only modestly over with no behavioral reason. No dead code deleted
  (arq jobs all registered; "unwired" services are deferred-feature scaffold,
  escalated not deleted). SQLModel query idiom deliberately NOT extracted.

## Residual risks / escalations (out of behavior-preserving scope)

1. **Core test coverage 48.57% < CI gate 70%** — PRE-EXISTING. ~30 unwired
   P4–P12 deferred-feature scaffold services have zero tests (committed in prior
   plans `b0f900f`, `bbac893`). Not introduced by this audit. CI on this branch
   was already red on core coverage. Decision (user-confirmed 2026-05-29):
   document + escalate, do NOT change the gate or game it with omits. Follow-up:
   either author tests for the scaffold services or scope the coverage target.
2. **Unwired services with latent gaps if routed** — `deck_search_service`
   (binds user_id, never uses it in WHERE), `classroom_service.assign_deck` (no
   deck-ownership check), `user_spend_service` (per-user cap non-functional:
   global-vs-per-user key mismatch + zero callers), `admin_audit_service.record()`
   (unwired → privileged ops unaudited). Verify before routing.
3. **Learning ELO** — `elo_at_start` snapshot not re-read at commit (concurrent
   same-definition lost-update); user-ELO computed vs constant 1000, not
   `Question.elo`; realized_score always 1.0 from submit path (monotonic ELO).
   Likely deliberate v1 simplifications — product decision, not silently changed.
4. **Web** — `useBroadcastSync` cross-tab sync is dead code (never wired);
   FE1 expired-session-on-/api/core may return sign-in HTML vs 401 (prod-proxy
   dependent, needs prod-like verification).
5. **npm audit** — pre-existing next/swiper/postcss advisories need breaking
   major bumps. Out of scope.
6. **F7 fuzzy-grading** — pre-existing rapidfuzz drift (`definishun`→`definition`
   returns no_match not fuzzy); quarantined `xfail`, threshold re-tune is a
   separate grading-quality task.

## Test-infra note
Running the core + worker pytest suites in PARALLEL against one Postgres
container collides on the session-scoped `postgresql_proc` fixture (transient
errors). Run them sequentially (CI matrix already isolates them per-job).

## Reports
- `findings-ledger.md` — every finding, terminal status.
- `conversion-parity-audit-report.md` (Phase 2)
- `pycil-core-bug-hunt-report.md` (Phase 4)
- `worker-bug-hunt-report.md` (Phase 5)
- `web-frontend-bug-hunt-report.md` (Phase 6)
- `refactor-code-health-report.md` (Phase 7)
- `from-explore-to-controller-phase2-idor-parity-audit.md`,
  `from-agent-phase4-auth-middleware-bughunt.md`
