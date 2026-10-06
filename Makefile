# Application startup never migrates. Invoke migrate against an explicit target.
.PHONY: api-dev worker migrate docker-build docker-up docker-down lint test test-api \
	test-unit test-integration test-system openapi

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
	cd apps/api && uv run --locked ruff check pycil tests migrations ../../scripts/test_api.py ../../scripts/export_openapi.py
	cd apps/api && uv run --locked ruff format --check pycil tests migrations ../../scripts/test_api.py ../../scripts/export_openapi.py

openapi:
	python scripts/export_openapi.py docs/backend/openapi.json

test: test-api

test-api:
	python scripts/test_api.py tests -q

test-unit:
	cd apps/api && uv run --locked pytest tests/unit -q

test-integration:
	python scripts/test_api.py tests/integration -q

test-system:
	python scripts/test_api.py tests/system -q
