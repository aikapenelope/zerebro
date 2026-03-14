"""Persistent memory layer using LangGraph Postgres backends.

Solves the "memory siloed" problem: without this, every agent invocation
starts from zero because the default ``MemorySaver`` is in-process only.

This module provides:
- **Checkpointer** (``AsyncPostgresSaver``): persists LangGraph graph state
  (message history, tool call results) across invocations for the same
  ``thread_id``.  This gives agents conversational memory.
- **Store** (``AsyncPostgresStore``): a key-value store for cross-thread
  persistent data (e.g., user preferences, learned facts).  Agents access
  it via the ``/memories/`` path when using ``CompositeBackend``.

Both use the *sync* Postgres URL (``database_url_sync``) because
``langgraph-checkpoint-postgres`` is built on **psycopg3** (not asyncpg).

Usage::

    from zerebro.core.memory import memory_lifespan, get_checkpointer, get_store

    # In the FastAPI lifespan, enter the context:
    async with memory_lifespan():
        yield  # app runs here

    # Then pass to create_deep_agent:
    create_deep_agent(
        ...,
        checkpointer=get_checkpointer(),
        store=get_store(),
    )
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from zerebro.config import settings

logger = logging.getLogger(__name__)

# Module-level singletons, managed by ``memory_lifespan()``.
_checkpointer: AsyncPostgresSaver | None = None
_store: AsyncPostgresStore | None = None


@asynccontextmanager
async def memory_lifespan() -> AsyncIterator[None]:
    """Async context manager that owns the Postgres connections for memory.

    Enter this in the FastAPI lifespan so connections are properly closed
    on shutdown.  Runs DDL (``setup()``) on first entry.
    """
    global _checkpointer, _store  # noqa: PLW0603

    conn_str = settings.database_url_sync
    logger.info(
        "Initialising LangGraph Postgres memory (%s)",
        conn_str.split("@")[-1],
    )

    async with (
        AsyncPostgresSaver.from_conn_string(conn_str) as checkpointer,
        AsyncPostgresStore.from_conn_string(conn_str) as store,
    ):
        await checkpointer.setup()
        await store.setup()

        _checkpointer = checkpointer
        _store = store
        logger.info("LangGraph Postgres memory ready")

        try:
            yield
        finally:
            _checkpointer = None
            _store = None
            logger.info("LangGraph Postgres memory shut down")


def get_checkpointer() -> AsyncPostgresSaver | None:
    """Return the initialised checkpointer, or ``None`` before setup."""
    return _checkpointer


def get_store() -> AsyncPostgresStore | None:
    """Return the initialised store, or ``None`` before setup."""
    return _store
