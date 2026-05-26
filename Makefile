# Pycil — backend test runner targets
.PHONY: test test-core test-worker test-cov

test: test-core test-worker

test-core:
	cd apps/pycil-core && uv run pytest \
		--cov=pycil_core --cov-fail-under=70 -q --maxfail=5

test-worker:
	cd apps/worker && uv run pytest \
		--cov=worker --cov-fail-under=70 -q --maxfail=5

test-cov:
	cd apps/pycil-core && uv run pytest --cov=pycil_core --cov-report=term-missing
	cd apps/worker && uv run pytest --cov=worker --cov-report=term-missing
