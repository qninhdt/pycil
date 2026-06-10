# Testing Strategy

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
