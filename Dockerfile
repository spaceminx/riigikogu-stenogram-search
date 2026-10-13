# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build tools in builder stage for packages compiling from source (e.g. estnltk on arm64)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.13-slim

WORKDIR /app

# Only runtime curl needed for healthcheck (no build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application files
COPY config.py .
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create data directories for SQLite database and state files
RUN mkdir -p /app/database /app/data/processed

# Run container as non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
