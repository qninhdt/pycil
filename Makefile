# Pycil — development and test targets
.PHONY: api-dev web-dev docker-up docker-down test test-api \
	test-unit test-integration test-system test-e2e

api-dev:
	cd apps/api && uv run alembic upgrade head && uv run uvicorn pycil.main:app --reload

web-dev:
	cd apps/web && pnpm dev

docker-up:
	docker compose up --build

docker-down:
	docker compose down

test: test-api

test-api:
	cd apps/api && uv run pytest -q --maxfail=5

# Pure rules only: no PostgreSQL, no Redis, no Docker, no browser. Runs in about a
# second, so it is the level to reach for while editing FSRS arithmetic, pricing or
# config validation.
test-unit:
	cd apps/api && uv run pytest tests/unit -q
	cd apps/api && uv run pytest tests/worker/unit -q
	cd apps/web && pnpm test:unit

# Real disposable PostgreSQL and Redis, plus rendered components over controlled
# HTTP. No browser and no running application process.
test-integration:
	cd apps/api && uv run pytest tests/integration -q
	cd apps/api && uv run pytest tests/worker/integration -q
	cd apps/web && pnpm test:integration

# The whole product: a real API and worker process over HTTP/SSE, against real
# stores. Needs Docker (or TEST_STACK_DB_URL/TEST_STACK_REDIS_URL) and the
# Cambridge reference artifact named by LEXI_REFERENCE_DATASET_PATH.
test-system:
	cd apps/api && uv run pytest tests/system -q

# The learner's own screens, driven through a browser against the running stack.
test-e2e:
	cd apps/web && pnpm test:e2e
