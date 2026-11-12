FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install . \
    && useradd --system --uid 10001 --create-home app \
    && mkdir -p /app/incoming \
    && chown -R app:app /app

USER app

CMD ["transaction-pipeline", "--help"]
