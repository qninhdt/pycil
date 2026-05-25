FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Build context = repo root (see docker-compose.yml).
COPY packages/shared-py /app/packages/shared-py
COPY apps/worker /app/apps/worker

RUN pip install --upgrade pip \
    && pip install -e /app/packages/shared-py \
    && pip install -e /app/apps/worker

WORKDIR /app/apps/worker

CMD ["arq", "worker.main.WorkerSettings"]
