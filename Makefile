# Pycil — backend test runner targets
.PHONY: test test-core test-worker test-cov staging staging-down

test: test-core test-worker

# One-command local staging: compose backend (Postgres, Redis, pycil-core,
# worker, Dex, MinIO) + host `next dev` on :3100. Open http://localhost:3100,
# log in via Dex (e2e-test@pycil.local / password123). Real LLM via OpenRouter.
staging:
	bash scripts/staging-up.sh

# Tear the stack down + stop the host web started by `make staging`.
# Negative PID kills the whole web process group (npm → next → node), matching
# the setsid launch in staging-up.sh; killing just the PID would orphan next.
staging-down:
	@[ -f .staging-web.pid ] && kill -- "-$$(cat .staging-web.pid)" 2>/dev/null || true
	@rm -f .staging-web.pid
	docker compose -f docker-compose.yml -f docker-compose.staging.yml down

test-core:
	cd apps/pycil-core && uv run pytest \
		--cov=pycil_core --cov-fail-under=70 -q --maxfail=5

test-worker:
	cd apps/worker && uv run pytest \
		--cov=worker --cov-fail-under=70 -q --maxfail=5

test-cov:
	cd apps/pycil-core && uv run pytest --cov=pycil_core --cov-report=term-missing
	cd apps/worker && uv run pytest --cov=worker --cov-report=term-missing
