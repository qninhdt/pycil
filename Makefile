# Application startup never migrates. Invoke migrate against an explicit target.
.PHONY: api-dev migrate docker-build docker-up docker-down lint test test-api \
	test-unit test-integration test-benchmark openapi storybook storybook-build vps-deploy vps-rollback k6-vps k6-check

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

vps-deploy:
	timeout --foreground --kill-after=30s 1800s bash infra/vps/deploy.sh deploy "$(RELEASE)"

vps-rollback:
	timeout --foreground --kill-after=30s 1800s bash infra/vps/deploy.sh rollback

lint:
	cd apps/api && uv run --locked ruff check pycil tests migrations ../../scripts/export_openapi.py ../../scripts/run-k6.py ../../tests/performance/tests
	cd apps/api && uv run --locked ruff format --check pycil tests migrations ../../scripts/export_openapi.py ../../scripts/run-k6.py ../../tests/performance/tests

openapi:
	python scripts/export_openapi.py docs/backend/openapi.json

test: test-api

test-api:
	cd apps/api && uv run --locked pytest -q

test-unit:
	cd apps/api && uv run --locked pytest tests/unit -q

test-integration:
	cd apps/api && uv run --locked pytest tests/integration -q

test-benchmark:
	cd apps/api && uv run --locked pytest tests/benchmarks -v

k6-check:
	node --test tests/performance/tests/*.test.js
	uv run --project apps/api --locked python -m unittest discover -s tests/performance/tests -p 'test_*.py' -v

k6-vps:
	uv run --project apps/api --locked python scripts/run-k6.py $(K6_ARGS)
