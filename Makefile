# Pycil — backend test runner targets
.PHONY: test test-api test-worker test-shared test-cov

test: test-api test-shared test-worker

test-api:
	cd apps/api && uv run pytest \
		--cov=pycil --cov-fail-under=70 -q --maxfail=5

# Pure-logic tests (FSRS math) — no DB, no I/O.
test-shared:
	cd packages/shared-py && uv run pytest shared/fsrs/tests -q

# apps/worker has no dedicated tests yet: its 3 jobs are thin wrappers around
# apps/api's tested service layer (see apps/api/tests/learning/test_apply_verdict.py).
# Ruff-only until that changes.
test-worker:
	cd apps/worker && uv run ruff check .

test-cov:
	cd apps/api && uv run pytest --cov=pycil --cov-report=term-missing
