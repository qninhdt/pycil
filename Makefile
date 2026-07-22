# Pycil — development and test targets
.PHONY: api-dev worker-dev web-dev docker-up docker-down test test-api test-worker test-shared test-cov

api-dev:
	cd apps/api && uv run alembic upgrade head && uv run uvicorn pycil.main:app --reload

worker-dev:
	cd apps/worker && uv run arq pycil_worker.main.WorkerSettings

web-dev:
	pnpm web:dev

docker-up:
	docker compose up --build

docker-down:
	docker compose down

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
