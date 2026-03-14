"""Async SQLAlchemy engine and session factory.

The engine is created lazily on first access so that tests can call
``set_engine()`` before any database connection is attempted.

Usage::

    from zerebro.db.engine import async_session, init_db

    # At startup
    await init_db()

    # In request handlers
    async with async_session() as session:
        ...
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine & session factory (lazy singletons)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _default_engine() -> AsyncEngine:
    """Create the default engine from settings (deferred import)."""
    from zerebro.config import settings

    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


def _get_engine() -> AsyncEngine:
    """Return the current engine, creating the default one if needed."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = _default_engine()
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory, creating it if needed."""
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


def set_engine(new_engine: AsyncEngine) -> None:
    """Replace the module-level engine and session factory.

    Used by tests to swap in an in-memory SQLite engine.
    Must be called **before** any code accesses ``async_session()``.
    """
    global _engine, _session_factory  # noqa: PLW0603
    _engine = new_engine
    _session_factory = async_sessionmaker(
        new_engine,
        expire_on_commit=False,
    )


@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session.

    Usage::

        async with async_session() as session:
            repo = AgentRepository(session)
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables directly via ``CREATE TABLE IF NOT EXISTS``.

    Used by **tests only** (with in-memory SQLite).  The production app
    uses ``run_migrations()`` instead so that Alembic tracks schema state.
    """
    from zerebro.db.models import Base

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized (create_all)")


def run_migrations() -> None:
    """Run Alembic migrations to ``head``.

    Called during application startup so the database schema is always
    up-to-date.  This is a **synchronous** function because Alembic's
    command API is synchronous (it manages its own async engine internally
    via the async env.py template).
    """
    import pathlib

    from alembic import command
    from alembic.config import Config

    # Locate alembic.ini: in Docker it lives at /app/alembic.ini (WORKDIR),
    # locally it's at the backend root.  We try the working directory first
    # (Docker), then fall back to resolving from this file's location (local dev).
    cwd_ini = pathlib.Path.cwd() / "alembic.ini"
    if cwd_ini.is_file():
        alembic_cfg = Config(str(cwd_ini))
    else:
        backend_root = pathlib.Path(__file__).resolve().parents[3]
        alembic_cfg = Config(str(backend_root / "alembic.ini"))

    from zerebro.config import settings

    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url_sync)

    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied to head")
