# Pycil — backend test runner targets
.PHONY: test test-api test-worker test-shared test-cov

test: test-api test-shared test-worker

test-api:
	cd apps/api && uv run pytest \
		--cov=pycil --cov-fail-under=70 -q --maxfail=5

# Pure-logic tests (FSRS math) — no DB, no I/O.
test-shared:
	cd packages/shared-py && uv run pytest shared/fsrs/tests -q

test-worker:
	cd apps/worker && uv run pytest -q

test-cov:
	cd apps/api && uv run pytest --cov=pycil --cov-report=term-missing
