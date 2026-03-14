"""Builder Agent API routes.

Provides the conversational interface for creating agents:
- ``POST /builder/chat``              -- send a message, get builder response
- ``GET  /builder/sessions``          -- list all builder sessions
- ``GET  /builder/sessions/{id}``     -- get a specific session
- ``POST /builder/sessions/{id}/confirm`` -- confirm and register the proposed agent
- ``POST /builder/sessions/{id}/cancel``  -- cancel a builder session
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from zerebro.core.builder import messages_from_history, run_builder_turn
from zerebro.db.engine import async_session
from zerebro.db.repositories import AgentRepository, SessionRepository
from zerebro.models.agent import AgentConfig
from zerebro.models.conversation import (
    BuilderSession,
    ChatRequest,
    ChatResponse,
    MessageRole,
    SessionStatus,
)

logger = logging.getLogger(__name__)


def create_builder_router() -> APIRouter:
    """Create the builder API router.

    All state is persisted via the DB repositories.

    Returns:
        An APIRouter with all builder endpoints.
    """
    router = APIRouter(prefix="/builder", tags=["builder"])

    @router.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse | JSONResponse:
        """Send a message to the Builder Agent.

        If ``session_id`` is omitted, a new session is created.
        Returns the builder's response and, if ready, a proposed AgentConfig.
        """
        async with async_session() as db:
            session_repo = SessionRepository(db)

            # Get or create session
            if request.session_id:
                session = await session_repo.get(request.session_id)
                if not session:
                    return JSONResponse(
                        status_code=404,
                        content={"detail": "Session not found"},
                    )
                if session.status not in (SessionStatus.ACTIVE, SessionStatus.PROPOSED):
                    return JSONResponse(
                        status_code=400,
                        content={"detail": f"Session is {session.status.value}, cannot chat"},
                    )
            else:
                session = BuilderSession()
                logger.info("Created builder session %s", session.id)

            # Add user message
            session.add_message(MessageRole.USER, request.message)

            # Run the builder
            history = session.to_history_dicts()
            lc_messages = messages_from_history(history)
            text_response, agent_config = await run_builder_turn(lc_messages)

            # Add assistant response
            session.add_message(MessageRole.ASSISTANT, text_response)

            # If builder produced a config, mark session as proposed
            if agent_config is not None:
                session.proposed_config = agent_config
                session.status = SessionStatus.PROPOSED
                logger.info(
                    "Builder proposed agent '%s' in session %s",
                    agent_config.name,
                    session.id,
                )

            # Persist session state
            await session_repo.save(session)

        return ChatResponse(
            session_id=session.id,
            response=text_response,
            status=session.status,
            proposed_config=session.proposed_config,
        )

    @router.get("/sessions", response_model=list[BuilderSession])
    async def list_sessions() -> list[BuilderSession]:
        """List all builder sessions."""
        async with async_session() as db:
            repo = SessionRepository(db)
            return await repo.list_all()

    @router.get("/sessions/{session_id}", response_model=BuilderSession)
    async def get_session(session_id: str) -> BuilderSession | JSONResponse:
        """Get a specific builder session with full conversation history."""
        async with async_session() as db:
            repo = SessionRepository(db)
            session = await repo.get(session_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"detail": "Session not found"},
            )
        return session

    @router.post("/sessions/{session_id}/confirm", response_model=AgentConfig)
    async def confirm_agent(session_id: str) -> AgentConfig | JSONResponse:
        """Confirm the proposed agent and register it.

        Takes the AgentConfig proposed by the builder, registers it in the
        agent store, and marks the session as confirmed.
        """
        async with async_session() as db:
            session_repo = SessionRepository(db)
            agent_repo = AgentRepository(db)

            session = await session_repo.get(session_id)
            if not session:
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Session not found"},
                )
            if session.status != SessionStatus.PROPOSED:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": f"Session is {session.status.value}, "
                        "expected 'proposed'"
                    },
                )
            if not session.proposed_config:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "No proposed config in this session"},
                )

            # Register the agent
            config = session.proposed_config
            await agent_repo.create(config)

            # Update session
            session.confirmed_agent_id = config.id
            session.status = SessionStatus.CONFIRMED
            await session_repo.save(session)

        logger.info(
            "Confirmed agent '%s' (%s) from session %s",
            config.name,
            config.id,
            session.id,
        )
        return config

    @router.post("/sessions/{session_id}/cancel", response_model=None)
    async def cancel_session(session_id: str) -> dict[str, str] | JSONResponse:
        """Cancel a builder session."""
        async with async_session() as db:
            session_repo = SessionRepository(db)

            session = await session_repo.get(session_id)
            if not session:
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Session not found"},
                )
            if session.status in (SessionStatus.CONFIRMED, SessionStatus.CANCELLED):
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Session is already {session.status.value}"},
                )

            session.status = SessionStatus.CANCELLED
            await session_repo.save(session)

        logger.info("Cancelled builder session %s", session.id)
        return {"status": "cancelled", "session_id": session.id}

    return router
