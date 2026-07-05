FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Build context = repo root (see docker-compose.yml). lexi-ai is an editable
# path dep; its source must be copied into the context too (interim until it
# publishes to an index). The compose build mounts it under /app/vendor/lexi-ai.
COPY packages/shared-py /app/packages/shared-py
COPY vendor/lexi-ai /app/vendor/lexi-ai
COPY apps/api /app/apps/api

RUN pip install --upgrade pip \
    && pip install -e /app/packages/shared-py \
    && pip install -e /app/vendor/lexi-ai \
    && pip install -e /app/apps/api

WORKDIR /app/apps/api

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "pycil.main:app", "--host", "0.0.0.0", "--port", "8000"]
