FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libmagic1 \
    file \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for caching
COPY app/pyproject.toml app/uv.lock .
RUN uv sync --frozen

# Copy app code
COPY app/ .

# Expose Uvicorn's port
EXPOSE 8000

# Run Uvicorn via uv
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
