FROM python:3.14.8-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api /app/apps/api

# Product policy lives at one fixed path in the image rather than being resolved
# from a working directory, so the API reads the same revision
# regardless of where their process was started. It holds no secrets; those
# arrive through the environment.
COPY config/config.yaml /app/config/config.yaml
ENV CONFIG_PATH=/app/config/config.yaml

WORKDIR /app/apps/api

RUN uv sync --locked --no-dev

ENV PATH="/app/apps/api/.venv/bin:$PATH"

# Runtime reads packaged application/policy only; no reason to recursively chown
# the entire dependency environment (or make installed code runtime-writable).
RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["uvicorn", "pycil.main:app", "--host", "0.0.0.0", "--port", "8000"]
