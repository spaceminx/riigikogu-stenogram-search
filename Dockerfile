# Stage 1: Build dependencies
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39 AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install /usr/local

# Pre-download NLTK punkt_tab data so it does not require runtime downloading
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -c "import nltk; nltk.download('punkt_tab', download_dir='/usr/local/share/nltk_data', quiet=True, raise_on_error=True)"

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

# urlopen raises on a connection error or an HTTP error status, so no curl (or apt) is needed
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/', timeout=4)"]

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
