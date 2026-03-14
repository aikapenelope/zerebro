#!/usr/bin/env bash
# Docker entrypoint: run Alembic migrations BEFORE starting uvicorn.
#
# Running migrations here (outside the Python event loop) avoids the
# asyncio.run() conflict that occurs when Alembic runs inside FastAPI's
# async lifespan.  If migrations fail the container exits immediately
# instead of starting a half-broken server.
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

exec "$@"
