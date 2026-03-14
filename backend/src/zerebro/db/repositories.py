"""Repository layer -- async CRUD over SQLAlchemy models.

Each repository class owns the mapping between ORM rows and the Pydantic
models used by the rest of the application.  API routes never touch
SQLAlchemy directly; they call repository methods instead.

Usage::

    async with async_session() as session:
        repo = AgentRepository(session)
        agent = await repo.get("some-id")
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zerebro.db.models import AgentRecord, BuilderSessionRecord, RunRecord
from zerebro.models.agent import (
    AgentConfig,
    AgentUpdate,
    ModelRole,
    RunResult,
    RunStatus,
    SubAgentConfig,
    TriggerConfig,
)
from zerebro.models.conversation import (
    BuilderSession,
    ConversationMessage,
    SessionStatus,
)

# ---------------------------------------------------------------------------
# Helpers -- Pydantic <-> ORM conversion
# ---------------------------------------------------------------------------


def _agent_to_row(config: AgentConfig) -> AgentRecord:
    """Convert a Pydantic AgentConfig to an ORM AgentRecord."""
    return AgentRecord(
        id=config.id,
        name=config.name,
        description=config.description,
        system_prompt=config.system_prompt,
        model_role=config.model_role.value,
        model_override=config.model_override,
        tools=config.tools,
        subagents=[sa.model_dump(mode="json") for sa in config.subagents],
        triggers=[t.model_dump(mode="json") for t in config.triggers],
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _row_to_agent(row: AgentRecord) -> AgentConfig:
    """Convert an ORM AgentRecord to a Pydantic AgentConfig."""
    return AgentConfig(
        id=row.id,
        name=row.name,
        description=row.description,
        system_prompt=row.system_prompt,
        model_role=ModelRole(row.model_role),
        model_override=row.model_override,
        tools=row.tools,
        subagents=[SubAgentConfig.model_validate(sa) for sa in row.subagents],
        triggers=[TriggerConfig.model_validate(t) for t in row.triggers],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _session_to_row(session: BuilderSession) -> BuilderSessionRecord:
    """Convert a Pydantic BuilderSession to an ORM BuilderSessionRecord."""
    return BuilderSessionRecord(
        id=session.id,
        status=session.status.value,
        messages=[m.model_dump(mode="json") for m in session.messages],
        proposed_config=(
            session.proposed_config.model_dump(mode="json")
            if session.proposed_config
            else None
        ),
        confirmed_agent_id=session.confirmed_agent_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _row_to_session(row: BuilderSessionRecord) -> BuilderSession:
    """Convert an ORM BuilderSessionRecord to a Pydantic BuilderSession."""
    return BuilderSession(
        id=row.id,
        status=SessionStatus(row.status),
        messages=[ConversationMessage.model_validate(m) for m in row.messages],
        proposed_config=(
            AgentConfig.model_validate(row.proposed_config)
            if row.proposed_config
            else None
        ),
        confirmed_agent_id=row.confirmed_agent_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_result_to_row(result: RunResult, input_message: str) -> RunRecord:
    """Convert a Pydantic RunResult to an ORM RunRecord."""
    return RunRecord(
        run_id=result.run_id,
        agent_id=result.agent_id,
        status=result.status.value,
        input_message=input_message,
        output=result.output,
        structured_output=result.structured_output,
        error=result.error,
        token_usage=result.token_usage,
        duration_ms=result.duration_ms,
        created_at=result.created_at,
    )


def _row_to_run_result(row: RunRecord) -> RunResult:
    """Convert an ORM RunRecord to a Pydantic RunResult."""
    return RunResult(
        run_id=row.run_id,
        agent_id=row.agent_id,
        status=RunStatus(row.status),
        output=row.output,
        structured_output=row.structured_output,
        error=row.error,
        token_usage=row.token_usage,
        duration_ms=row.duration_ms,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# AgentRepository
# ---------------------------------------------------------------------------


class AgentRepository:
    """Async CRUD for agent configurations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[AgentConfig]:
        """Return all agents ordered by creation date (newest first)."""
        result = await self._session.execute(
            select(AgentRecord).order_by(AgentRecord.created_at.desc())
        )
        return [_row_to_agent(row) for row in result.scalars().all()]

    async def get(self, agent_id: str) -> AgentConfig | None:
        """Return a single agent by ID, or None if not found."""
        row = await self._session.get(AgentRecord, agent_id)
        return _row_to_agent(row) if row else None

    async def create(self, config: AgentConfig) -> AgentConfig:
        """Insert a new agent and return it."""
        row = _agent_to_row(config)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_agent(row)

    async def update(self, agent_id: str, update: AgentUpdate) -> AgentConfig | None:
        """Apply a partial update to an agent. Returns None if not found."""
        row = await self._session.get(AgentRecord, agent_id)
        if not row:
            return None

        update_data = update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "model_role" and value is not None:
                setattr(row, key, value.value if isinstance(value, ModelRole) else value)
            elif key == "subagents" and value is not None:
                setattr(row, key, [sa.model_dump(mode="json") for sa in value])
            elif key == "triggers" and value is not None:
                setattr(row, key, [t.model_dump(mode="json") for t in value])
            else:
                setattr(row, key, value)

        row.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_agent(row)

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent. Returns True if deleted, False if not found."""
        row = await self._session.get(AgentRecord, agent_id)
        if not row:
            return False
        await self._session.delete(row)
        await self._session.commit()
        return True

    async def exists(self, agent_id: str) -> bool:
        """Check if an agent exists without loading the full row."""
        row = await self._session.get(AgentRecord, agent_id)
        return row is not None


# ---------------------------------------------------------------------------
# SessionRepository
# ---------------------------------------------------------------------------


class SessionRepository:
    """Async CRUD for builder conversation sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[BuilderSession]:
        """Return all sessions ordered by creation date (newest first)."""
        result = await self._session.execute(
            select(BuilderSessionRecord).order_by(
                BuilderSessionRecord.created_at.desc()
            )
        )
        return [_row_to_session(row) for row in result.scalars().all()]

    async def get(self, session_id: str) -> BuilderSession | None:
        """Return a single session by ID, or None if not found."""
        row = await self._session.get(BuilderSessionRecord, session_id)
        return _row_to_session(row) if row else None

    async def create(self, bs: BuilderSession) -> BuilderSession:
        """Insert a new session and return it."""
        row = _session_to_row(bs)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_session(row)

    async def save(self, bs: BuilderSession) -> BuilderSession:
        """Upsert a session -- update if exists, insert if not.

        This is the primary method used by builder_routes to persist
        session state after each chat turn.
        """
        row = await self._session.get(BuilderSessionRecord, bs.id)
        if row:
            row.status = bs.status.value
            row.messages = [m.model_dump(mode="json") for m in bs.messages]
            row.proposed_config = (
                bs.proposed_config.model_dump(mode="json")
                if bs.proposed_config
                else None
            )
            row.confirmed_agent_id = bs.confirmed_agent_id
            row.updated_at = datetime.now(UTC)
        else:
            row = _session_to_row(bs)
            self._session.add(row)

        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_session(row)


# ---------------------------------------------------------------------------
# RunRepository
# ---------------------------------------------------------------------------


class RunRepository:
    """Async CRUD for agent run history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, result: RunResult, input_message: str) -> RunResult:
        """Persist a run result."""
        row = _run_result_to_row(result, input_message)
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_run_result(row)

    async def list_by_agent(
        self, agent_id: str, limit: int = 50
    ) -> list[RunResult]:
        """Return runs for a given agent, newest first."""
        result = await self._session.execute(
            select(RunRecord)
            .where(RunRecord.agent_id == agent_id)
            .order_by(RunRecord.created_at.desc())
            .limit(limit)
        )
        return [_row_to_run_result(row) for row in result.scalars().all()]
