"""SQLAlchemy ORM models for persistent storage.

Each table mirrors a Pydantic model from ``zerebro.models``.  Complex nested
structures (sub-agents, triggers, messages) are stored as JSON columns --
this keeps the schema simple while PostgreSQL's JSONB gives us indexing
if needed later.

Conversion between ORM rows and Pydantic models happens in the repository
layer (``zerebro.db.repositories``), not here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from zerebro.models.agent import ModelRole, RunStatus
from zerebro.models.conversation import SessionStatus

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# JSON fallback -- use JSONB on PostgreSQL, plain JSON elsewhere (SQLite)
# ---------------------------------------------------------------------------

# SQLAlchemy's JSONB only works on PostgreSQL.  For tests we use SQLite,
# so we fall back to the generic JSON type via ``with_variant``.
JSONColumn = JSONB().with_variant(JSON(), "sqlite")


# ---------------------------------------------------------------------------
# Agent table
# ---------------------------------------------------------------------------


class AgentRecord(Base):
    """Persistent storage for agent configurations."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_role: Mapped[str] = mapped_column(
        Enum(ModelRole, values_callable=lambda e: [m.value for m in e]),
        default=ModelRole.WORKER.value,
    )
    model_override: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Complex nested data stored as JSON
    tools: Mapped[list] = mapped_column(JSONColumn, default=list)  # type: ignore[type-arg]
    subagents: Mapped[list] = mapped_column(JSONColumn, default=list)  # type: ignore[type-arg]
    triggers: Mapped[list] = mapped_column(JSONColumn, default=list)  # type: ignore[type-arg]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Builder session table
# ---------------------------------------------------------------------------


class BuilderSessionRecord(Base):
    """Persistent storage for builder conversation sessions."""

    __tablename__ = "builder_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(
        Enum(SessionStatus, values_callable=lambda e: [s.value for s in e]),
        default=SessionStatus.ACTIVE.value,
    )

    # Full conversation history as JSON array of {role, content, timestamp}
    messages: Mapped[list] = mapped_column(JSONColumn, default=list)  # type: ignore[type-arg]

    # The proposed AgentConfig (full JSON), null until builder produces one
    proposed_config: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONColumn, nullable=True
    )

    confirmed_agent_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Run history table
# ---------------------------------------------------------------------------


class RunRecord(Base):
    """Persistent storage for agent execution history."""

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum(RunStatus, values_callable=lambda e: [s.value for s in e]),
        default=RunStatus.PENDING.value,
    )
    input_message: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    structured_output: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONColumn, nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict] = mapped_column(JSONColumn, default=dict)  # type: ignore[type-arg]
    duration_ms: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
