FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (gcc + libpq for asyncpg/psycopg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy project metadata first for layer caching
COPY pyproject.toml ./

# Copy source code (needed for pip install with setuptools find_packages)
COPY src/ ./src/

# Copy Alembic config and migrations
COPY alembic.ini ./
COPY migrations/ ./migrations/

# Install the project and all dependencies
RUN pip install --no-cache-dir "."

# Copy entrypoint script (runs migrations before uvicorn)
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

# Use --reload for dev; override CMD in production
CMD ["uvicorn", "zerebro.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
