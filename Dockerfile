# Self-contained image for the pharma research agent.
# Build:  docker build -t agent .
# Run:    docker run -p 8000:8000 --env-file .env agent
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# 1) Dependencies first — this layer is cached unless requirements.txt changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# 2) Application code + data (corpus baked in -> self-contained).
COPY app ./app
COPY corpus ./corpus
COPY frontend ./frontend
COPY eval ./eval

# Run as a non-root user; give it a writable cache dir for the embedding index.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/.cache \
    && chown appuser:appuser /app/.cache
USER appuser

EXPOSE 8000

# Healthy only once the retriever is actually ready (status == "ok").
HEALTHCHECK --interval=15s --timeout=5s --start-period=300s --retries=10 \
    CMD python -c "import json,urllib.request,sys; r=urllib.request.urlopen('http://localhost:8000/health'); sys.exit(0 if json.load(r).get('status')=='ok' else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "32", "--backlog", "64", "--timeout-keep-alive", "5"]
