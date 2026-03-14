"""Alembic environment configuration.

Reads the database URL from ``zerebro.config.settings`` so there is a
single source of truth for connection strings.

Uses the **sync** database URL (``database_url_sync``) so that migrations
can run inside an already-running async event loop (e.g., uvicorn's
lifespan) without ``asyncio.run()`` conflicts.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from zerebro.config import settings
from zerebro.db.models import Base

# ---------------------------------------------------------------------------
# Alembic Config object -- provides access to alembic.ini values
# ---------------------------------------------------------------------------

config = context.config

# Use the sync URL so we don't need asyncio.run() inside uvicorn's loop.
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Set up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our ORM metadata for autogenerate support
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a sync engine."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url", ""),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
