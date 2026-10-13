# Application startup never migrates. Invoke migrate against an explicit target.
.PHONY: api-dev migrate docker-build docker-up docker-down lint test test-api \
	test-unit test-integration openapi storybook storybook-build

storybook:
	cd apps/web && pnpm run storybook

storybook-build:
	cd apps/web && pnpm run build-storybook

api-dev:
	cd apps/api && uv run --locked uvicorn pycil.main:app --reload

migrate:
	cd apps/api && uv run --locked python -m pycil.app.migrate

docker-build:
	docker build -f apps/api/Dockerfile -t pycil-api:local .

docker-up:
	python scripts/compose.py up --build --remove-orphans

docker-down:
	python scripts/compose.py down

lint:
	cd apps/api && uv run --locked ruff check pycil tests migrations ../../scripts/export_openapi.py
	cd apps/api && uv run --locked ruff format --check pycil tests migrations ../../scripts/export_openapi.py

openapi:
	python scripts/export_openapi.py docs/backend/openapi.json

test: test-api

test-api:
	cd apps/api && uv run --locked pytest tests -q

test-unit:
	cd apps/api && uv run --locked pytest tests/unit -q

test-integration:
	cd apps/api && uv run --locked pytest tests/integration -q
