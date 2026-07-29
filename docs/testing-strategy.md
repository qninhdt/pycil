# Testing Strategy

**Note:** this file originally described `apps/pycil-core` (the pre-migration
backend). That app was fully superseded by `apps/api` and removed from disk
(2026-07-06) — the "Historical" section below is kept purely as a record of
its testing approach, not a description of anything currently runnable. It
does **not** describe `apps/api`/`apps/worker` (the current backend) — see
"Current backend (`apps/api`)" below for that.

## Current backend (`apps/api`)

Tests live in `apps/api/tests/`, organized by domain (`auth/`, `content/`,
`hierarchy/`, `learning/`, `realtime/`) plus a top-level
`test_lexi_boundary.py` asserting that neither deployed package imports Lexi
internals. There is no
unit/integration pytest-marker split here (unlike `apps/pycil-core` below) —
every test in this suite runs against a **real Postgres** (a disposable
instance pointed at via `TEST_DB_URL`, schema create/drop via
`target_metadata.create_all`/`drop_all` in `conftest.py`) and **fakeredis**
(autouse fixture). Lexi is faked at the port boundary in tests that need it —
`FakeLexiReader` and `FakeLexiWorkerEngine` in `apps/api/tests/learning/fakes.py`
stand in for the `LexiReader` / `LexiWorkerEngine` protocols in
`apps/api/pycil/content/lexi_port.py` — never the LLM itself, since the port is
the intended seam.

Run: `cd apps/api && uv run pytest`.

There is no coverage-gate config (`--cov-fail-under`) in `apps/api/pyproject.toml`
today — the 70% gate described below is specific to `apps/pycil-core`.

`packages/shared-py/shared/fsrs/tests/` covers the FSRS engine; run with
`cd packages/shared-py && uv run pytest`. The legacy question-plugin tests
that used to live in `packages/shared-py/tests/` were removed alongside
`apps/pycil-core`, their only consumer.

`apps/worker` has no test suite yet — the previous LLM-pipeline tests were
removed during the worker redesign and not replaced.

## Current frontend (`apps/web`)

Three layers, distinct jobs, no overlap. Vitest for pure logic (no DOM, no
network); Storybook for component review and a11y in isolation; Playwright for
the real browser against the real stack. There are deliberately **no**
component-level DOM tests in Vitest — the same assertions are cheaper and truer
in Storybook and Playwright.

### Unit (`apps/web/tests/unit/`, Vitest)

Pure functions that take values and return values, where a bug is a logic bug
rather than a render bug. Config in `vitest.config.ts` (`environment: "node"`,
`@/` alias mirroring `tsconfig.json`). Covers the modules that carry real risk:
the study session reducer (`lib/study/session-machine.ts`), the error taxonomy
(`lib/api/error-taxonomy.ts`), async-task snapshot reconciliation
(`lib/realtime/task-snapshot.ts`), mastery-stage mapping (`lib/design/mastery.ts`),
and the assistant transport (`lib/assistant/transcript.ts`, `sse-frames.ts`).
No test asserts against fabricated data to pass — fixtures are built to the real
wire types.

Run: `pnpm --filter web test:unit` (or `test:coverage`).

### Design-system audit (`apps/web/scripts/design-system-audit.mjs`)

Ten mechanical greps that enforce the `DESIGN.md` rules a typecheck cannot:
serif reserved for lexical content, spacing via `gap` not `space-*`, elevation
as a hairline ring not a drop shadow, colour through the semantic token layer
not raw hex or a call-site `dark:` override, icons from `lib/icons`, `size-N`
over `w-N h-N`, `min-h-[100dvh]` over `h-screen`, and every `rounded-*` radius
resolving to a defined token. Comment-aware: it strips line and block comments
but keeps string and JSX-text content, so a class inside `className="…"` is
still checked while an em dash in a JSDoc note is not. The `components/ui/**`
primitive registry is exempt (that layer wires the tokens); the rules keep the
rest of the app off the raw values. Non-zero exit on any violation.

Run: `pnpm --filter web audit:design`.

### Storybook (`apps/web/stories/`)

Component review and axe a11y in isolation, themed light/dark via a preview
decorator, viewports at 390 and 1280. Foundations cover the primitive inventory
and design tokens; feature stories cover the four question formats, the study
feedback surfaces (verdict/pending/round), lexical content (headword,
definition, mastery ramp), library rows and the anonymous-read notice, the
assistant confirmation card and recovery notice, and the progress figures and
activity rows — each with loading, empty, and error variants where they apply.

Run: `pnpm --filter web storybook` (dev) or `build-storybook` (CI).

### E2E (`apps/web/tests/e2e/`, Playwright)

The real browser against `docker compose up`, through Caddy's single
`https://localhost` origin. Nothing is stubbed: no mocked `getSession`, no
dev-login route, no fabricated question payloads. Auth seals a session cookie
from the `dev_identity` CLI one-shot using the app's own `sessionOptions`, so the
cookie under test is the cookie production issues.

Selection is by accessible role and text only. The app ships no `data-testid`
anywhere, which means a spec cannot pass while the accessible name is wrong — a
selector that a screen reader could not follow does not resolve either.

`global-setup.ts` seeds a run-scoped folder, deck, and senses over the API and
warms the question supply, then each spec that studies takes its **own** learner
via the `learner` fixture. Scheduling state is keyed `(user_id, sense_id)`, so a
shared learner would make the study specs order-dependent: the first to run
would pass and the rest would open on "Nothing due right now" — a stale schedule
that reads exactly like a planner bug. Per-spec learners are cheap because senses
and prepared questions are global (the generation job drops the owner
explicitly), so a new identity inherits warm supply and pays no model call.

`fixtures/schedule.ts` is the one documented exception to the API-only rule: no
endpoint sets `next_review_date` or `mastery`, by design, so making a sense due
at a chosen mastery runs SQLAlchemy inside the API container. Without it the
level-3 and level-4 question formats are unreachable, because a new sense is
always requested at the assessment floor.

Covered: the auth seam, library navigation and anonymous read-only access, and
the study loop end to end — exposure cards, all four question formats, round
breaks, the recap and its reload, and a free-text verdict arriving over SSE and
surviving a reload mid-grade.

Run: `pnpm --filter web test:e2e`.

Not on the per-push gate. It needs the full stack (API, worker, Postgres, Redis,
Centrifugo, Caddy) plus an LLM credential for the generation tier, so it belongs
on a nightly workflow against a stood-up stack.

### CI

`test-web` in `.github/workflows/test.yml` runs typecheck, lint, unit, the
design-system audit, build, and build-storybook on Node 22 / pnpm with a frozen
lockfile. E2E placement is explicitly the nightly stack. The Python jobs use
`uv sync --locked` so lockfile drift fails CI.

---

## Historical: `apps/pycil-core` testing strategy

Three test layers, each with a clear contract for what it proves and what it
mocks. CI and `make` can target each layer independently via pytest markers.

## Layers

### Unit (`tests/unit/`, marker `unit`)

Pure logic, no I/O. ELO math, mastery-level mapping, interval ladder,
sanitizers, parsers, the config prod-secret validator. Nothing to mock —
these functions take values and return values.

Run: `make test-unit` (fast, no Postgres/Redis needed).

### Integration (`tests/integration/` + top-level `tests/test_*.py`, marker `integration`)

Service + route behavior against a **real Postgres** (`pytest-postgresql`,
session-scoped, schema migrated once) and **fakeredis**. Network egress is
blocked. This is the bulk of the suite.

Mock ONLY external paid / third-party boundaries:
- OpenRouter (LLM calls)
- Stripe SDK
- S3 / object storage
- arq enqueue (the job is asserted enqueued; the worker side is tested separately)

Everything else runs for real: SQL, ownership scoping, transaction boundaries,
auth/RBAC gating, ELO commits, GDPR purge, advisory locks. A test that only
asserts "a function was called" is not an integration test — assert the
resulting DB/state change instead.

Run: `make test-integration` (requires a reachable Postgres; see conftest env).

### E2E (removed)

Was `apps/web/e2e/` (Playwright): full user flows against real Dex + core +
worker + migrations, LLM stubbed for cost — sign-in, deck/term, learn loop,
ELO mutation end to end via `apps/web/scripts/run-e2e.sh`. Removed 2026-07-06
alongside `apps/pycil-core`: it drove that app's Dex/next-auth login and
asserted ELO fields, both gone from the current stack. `apps/api/pycil/auth/
oauth.py` hardcodes Google's real endpoints (no local IdP swap-in), so
rebuilding e2e coverage needs a new auth-testing strategy, not just a
find-and-replace on service names — tracked in `docs/project-roadmap.md`'s
operational gaps, blocked on Phase 10 (frontend auth/Centrifugo) landing.

## Markers

Markers are applied automatically by location (see `conftest.py`
`pytest_collection_modifyitems`): anything under `tests/unit/` is `unit`,
everything else is `integration`. No need to decorate individual tests.

```
pytest -m unit            # pure logic only
pytest -m integration     # service + DB + fakeredis
```

The partition is total and exclusive: every collected test carries exactly one
of the two markers (CI asserts zero unmarked via `pytest -m "not unit and not
integration" --collect-only`).

## On the `*_coverage.py` suffix

Several integration files are named `test_<area>_coverage.py`. The suffix is
historical — it does NOT mean "coverage padding." These are full behavior
suites (owner-scoping, 404/403 arms, ON CONFLICT flips, guard rejections,
verify-then-delete). They are kept and maintained like any other behavior test.

## Coverage gate

`--cov-fail-under=70` on both core and worker. The threshold is a floor met by
real behavioral tests, not a target hit with tautological calls. Compliance- and
correctness-critical paths (GDPR `hard_delete_expired_users` cron lock, the
learning ELO/lock/concurrency core) carry dedicated behavior tests; do not delete
those even if a global coverage number would still pass without them.
