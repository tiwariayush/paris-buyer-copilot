# Paris Buyer Copilot — backend image
# Single-stage Python 3.12 build using uv for reproducible deps.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# System deps: minimal — DuckDB ships its own native libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first (cache-friendly).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source + pre-built DuckDB (data/paris.duckdb). The .dockerignore
# excludes the raw DVF gz files but keeps the parquet-style DuckDB asset.
COPY app ./app
COPY scripts ./scripts
COPY data ./data

# Pre-warm DuckDB spatial extension so first request is fast.
RUN uv run --no-dev python -c "import duckdb; c = duckdb.connect('/tmp/_warm.duckdb'); c.execute('INSTALL spatial; LOAD spatial;'); c.close()" || true

ENV DUCKDB_PATH=/app/data/paris.duckdb \
    HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080

# Single worker keeps the DuckDB connection cleanly shared.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
