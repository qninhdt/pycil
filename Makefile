# Pycil — backend test runner targets
.PHONY: test test-api test-worker test-shared test-cov staging staging-down

test: test-api test-shared test-worker

# One-command local staging: compose backend (Postgres, Redis, pycil-core,
# worker, Dex, MinIO) + host `next dev` on :3100. Open http://localhost:3100,
# log in via Dex (e2e-test@pycil.local / password123). Real LLM via OpenRouter.
# STALE: staging-up.sh + docker-compose.staging.yml still target the retired
# pycil-core/Dex/MinIO stack, not apps/api (Google-PKCE auth, no S3/media).
# Needs a rework tied to Phase 10 (frontend auth/Centrifugo) completion.
staging:
	bash scripts/staging-up.sh

# Tear the stack down + stop the host web started by `make staging`.
# Negative PID kills the whole web process group (npm → next → node), matching
# the setsid launch in staging-up.sh; killing just the PID would orphan next.
staging-down:
	@[ -f .staging-web.pid ] && kill -- "-$$(cat .staging-web.pid)" 2>/dev/null || true
	@rm -f .staging-web.pid
	docker compose -f docker-compose.yml -f docker-compose.staging.yml down

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
