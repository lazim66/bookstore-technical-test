FROM python:3.11-slim

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system -e ".[dev]"

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "src.main:application", "--host", "0.0.0.0", "--port", "8080", "--reload"]
