# Shelly Exporter Dockerfile
# Uses uv for dependency management

FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock* README.md ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies (frozen if lock file exists)
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-dev; \
    else \
        uv sync --no-dev; \
    fi

# Copy application code
COPY src/ ./src/

# Install the application
RUN uv pip install --no-deps .

# Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/config/config.yml

# Create config directory
RUN mkdir -p /config

# Create non-root user first
RUN useradd -r -s /bin/false shelly

# Create data directory for discovered devices (writable by shelly user)
RUN mkdir -p /app/data && chown -R shelly:shelly /app/data

# Expose metrics port
EXPOSE 10037

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:10037/health')" || exit 1

# Switch to non-root user
USER shelly

# Start application
ENTRYPOINT ["shelly-exporter"]
CMD ["--config", "/config/config.yml"]
