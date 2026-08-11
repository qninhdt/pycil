FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/shared-py /app/packages/shared-py
COPY apps/api /app/apps/api

WORKDIR /app/apps/api

RUN uv sync --locked --no-dev

ENV PATH="/app/apps/api/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "pycil.main:app", "--host", "0.0.0.0", "--port", "8000"]
