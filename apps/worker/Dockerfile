FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Build context = repo root (see docker-compose.yml). The worker reuses the API
# package for learning services and embeds the Lexi domain library.
COPY packages/shared-py /app/packages/shared-py
COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

RUN pip install --upgrade pip \
    && pip install -e /app/packages/shared-py \
    && pip install -e /app/apps/api \
    && pip install -e /app/apps/worker

WORKDIR /app/apps/worker

# Drop root: arq needs no privileged ports or writes outside the venv.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["arq", "pycil_worker.main.WorkerSettings"]
