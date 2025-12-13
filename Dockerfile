FROM python:3.11-slim

# Hugging Face Spaces runs containers as uid 1000; use a matching non-root user.
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (ensure correct ownership without an extra chown layer)
COPY --chown=appuser:appuser src/ ./src/

USER appuser

# Hugging Face Spaces uses README.md `app_port` for the exposed port.
EXPOSE 8000

# Health check (use runtime PORT if provided)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/health')" || exit 1

# Run the application (respect PORT if set by the platform; default 8000)
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
