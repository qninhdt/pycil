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

# Build context = repo root (see docker-compose.yml). The worker reuses the API
# package for learning services and embeds the Lexi domain library.
COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker

# Same fixed policy path as the API image, so one release has one catalog and a
# worker can never bill or bound a turn against a different revision than the
# process that admitted it.
COPY config/config.yaml /app/config/config.yaml
ENV PYCIL_CONFIG_PATH=/app/config/config.yaml

WORKDIR /app/apps/worker

RUN uv sync --locked --no-dev

ENV PATH="/app/apps/worker/.venv/bin:$PATH"

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

# Domain jobs need no privileged ports.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["taskiq", "worker", "pycil_worker.main:broker", "--workers", "1"]
