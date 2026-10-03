# Application startup never migrates. Invoke migrate against an explicit target.
.PHONY: api-dev worker migrate docker-build docker-up docker-down lint test test-api \
	test-unit test-integration test-system

api-dev:
	cd apps/api && uv run --locked uvicorn pycil.main:app --reload

worker:
	cd apps/api && uv run --locked python -m pycil.worker

migrate:
	cd apps/api && uv run --locked python -m pycil.migrate

docker-build:
	docker build -f apps/api/Dockerfile -t pycil-api:local .

docker-up:
	python scripts/compose.py up --build

docker-down:
	python scripts/compose.py down

lint:
	cd apps/api && uv run --locked ruff check pycil tests migrations
	cd apps/api && uv run --locked ruff format --check pycil tests migrations

test: test-api

test-api:
	cd apps/api && uv run --locked pytest tests -q

test-unit:
	cd apps/api && uv run --locked pytest tests/unit -q

test-integration:
	cd apps/api && uv run --locked pytest tests/integration -q

test-system:
	cd apps/api && uv run --locked pytest tests/system -q
