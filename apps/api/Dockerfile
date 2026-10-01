FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api /app/apps/api

# Product policy lives at one fixed path in the image rather than being resolved
# from a working directory, so the API and the worker read the same revision
# regardless of where their process was started. It holds no secrets; those
# arrive through the environment.
COPY config/config.yaml /app/config/config.yaml
ENV PYCIL_CONFIG_PATH=/app/config/config.yaml

WORKDIR /app/apps/api

RUN uv sync --locked --no-dev

ENV PATH="/app/apps/api/.venv/bin:$PATH"

# Word generation runs in the worker process from this same image and needs the
# WordNet corpus at runtime (the nltk package alone does not include its data).
ENV NLTK_DATA=/usr/local/nltk_data
RUN python -m nltk.downloader -d "$NLTK_DATA" wordnet \
    && python -c "from nltk.corpus import wordnet; assert wordnet.synsets('resilient')"

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "pycil.main:app", "--host", "0.0.0.0", "--port", "8000"]
