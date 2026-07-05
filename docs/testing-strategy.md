# Testing Strategy

**Note:** this file originally described `apps/pycil-core` (the pre-migration
backend, kept as a historical reference — see `docs/system-architecture.md`).
That description is still accurate for `apps/pycil-core` itself. It does
**not** describe `apps/api`/`apps/worker` (the current backend) — see
"Current backend (`apps/api`)" below for that.

## Current backend (`apps/api`)

Tests live in `apps/api/tests/`, organized by domain (`auth/`, `content/`,
`hierarchy/`, `learning/`, `realtime/`, `integration/`) plus a top-level
`test_boundary.py` asserting the two-DB structural boundary. There is no
unit/integration pytest-marker split here (unlike `apps/pycil-core` below) —
every test in this suite runs against a **real Postgres**
(`pytest-postgresql`, per-test schema create/drop via
`target_metadata.create_all`/`drop_all` in `conftest.py`) and **fakeredis**
(autouse fixture). `LexiClient` is faked at the port boundary in tests that
need it (e.g. `apps/api/tests/integration/test_session_flow.py`'s
`IntegrationLexiClient`) — never the LLM itself, since the port is the
intended seam.

Run: `cd apps/api && uv run pytest`.

There is no coverage-gate config (`--cov-fail-under`) in `apps/api/pyproject.toml`
today — the 70% gate described below is specific to `apps/pycil-core`.

`packages/shared-py/tests/` covers the FSRS engine and the legacy question
plugins; run with `cd packages/shared-py && uv run pytest`.

`apps/worker` has no test suite yet — the previous LLM-pipeline tests were
removed during the worker redesign and not replaced.

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

### E2E (`apps/web/e2e/`, Playwright)

Full user flows against real Dex + core + worker + migrations, LLM stubbed for
cost. Validates sign-in, deck/term, learn loop, ELO mutation end to end.
Covered in the e2e runner (`apps/web/scripts/run-e2e.sh`), not pytest.

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
