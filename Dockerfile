# Multi-stage production container for AI Reliability & Evaluation Platform
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies from locked specification
COPY requirements-lock.txt requirements.txt pyproject.toml ./
RUN pip install -r requirements-lock.txt

# Copy application source and configuration
COPY src/ ./src/
COPY configs/ ./configs/
COPY data/benchmarks/ ./data/benchmarks/
COPY data/evaluation_sets/ ./data/evaluation_sets/
COPY frontend/ ./frontend/
COPY main.py ./

# Install local package
RUN pip install --no-deps -e .

# Create unprivileged application user and data directory
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    mkdir -p /app/data/results && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000 8501

# Default entrypoint starts the FastAPI service
CMD ["uvicorn", "ai_reliability.api:app", "--host", "0.0.0.0", "--port", "8000"]
