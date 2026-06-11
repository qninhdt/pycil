FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Build context = repo root (see docker-compose.yml).
COPY packages/shared-py /app/packages/shared-py
COPY apps/pycil-core /app/apps/pycil-core

RUN pip install --upgrade pip \
    && pip install -e /app/packages/shared-py \
    && pip install -e /app/apps/pycil-core

WORKDIR /app/apps/pycil-core

EXPOSE 8000

# Drop root: uvicorn binds 8000 (non-privileged), no writes outside the venv.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "pycil_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
