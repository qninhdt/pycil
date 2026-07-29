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

# Lexi resolves a candidate's senses against WordNet during generation, so the
# corpus is a runtime requirement of this image rather than an optional extra:
# without it every `generate_word` raises LookupError inside the reference
# lookup, the job reports `failed`, and no dictionary entry is ever produced.
# `nltk` is declared as a dependency but ships no data, so it is fetched here.
#
# The target is one of nltk's own search paths and is written while this layer
# still runs as root, so the unprivileged runtime user only ever reads it. A
# download at startup instead would need a writable home, network egress on
# every boot, and would fail closed in an air-gapped deployment.
ENV NLTK_DATA=/usr/local/nltk_data
RUN python -m nltk.downloader -d "$NLTK_DATA" wordnet \
    && python -c "from nltk.corpus import wordnet; assert wordnet.synsets('resilient')"

WORKDIR /app/apps/worker

# Drop root: arq needs no privileged ports or writes outside the venv.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["arq", "pycil_worker.main.WorkerSettings"]
