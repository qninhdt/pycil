# syntax=docker/dockerfile:1

# ─────────────────────────────
# Builder
# ─────────────────────────────
FROM python:3.14.8-slim-trixie AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

WORKDIR /app/apps/api

# Instructor is locked to a Git source; native builds stay in this stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer
COPY apps/api/pyproject.toml apps/api/uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    --locked \
    --no-dev \
    --no-install-project

# Application layer
COPY apps/api ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    --locked \
    --no-dev


# ─────────────────────────────
# Runtime
# ─────────────────────────────
FROM python:3.14.8-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/apps/api/.venv/bin:$PATH" \
    CONFIG_PATH=/app/config/config.yaml

WORKDIR /app/apps/api

# Editable package and migration paths require source beside the venv.
COPY --from=builder /app/apps/api/.venv ./.venv
COPY --from=builder /app/apps/api/pycil ./pycil
COPY --from=builder /app/apps/api/migrations ./migrations
COPY --from=builder /app/apps/api/alembic.ini ./alembic.ini

COPY config/config.yaml /app/config/config.yaml

# Dependencies are installed in the builder; runtime does not need pip's vendored packages.
RUN /usr/local/bin/python -m pip uninstall --yes pip \
    && useradd --create-home --uid 10001 appuser \
    && install -d -o appuser -g appuser /var/lib/pycil/search

USER appuser

CMD ["uvicorn", "pycil.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "75", "--timeout-keep-alive", "5", "--limit-concurrency", "64", "--no-access-log"]
