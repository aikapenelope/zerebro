"""FastAPI application -- the main entry point for the Zerebro backend.

Provides:
- ``POST /agents/run``       -- execute an agent (blocking, returns RunResult)
- ``POST /agents/run/stream`` -- execute an agent with SSE streaming
- ``GET  /health``            -- liveness / readiness probe
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from zerebro.config import settings
from zerebro.core.runner import run_agent, stream_agent
from zerebro.core.tracing import init_tracing
from zerebro.models.agent import AgentConfig, RunRequest, RunResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    """Application startup / shutdown hooks."""
    init_tracing()
    logger.info("Zerebro backend started on %s:%s", settings.backend_host, settings.backend_port)
    yield
    logger.info("Zerebro backend shutting down")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title="Zerebro",
        description="Self-hosted agent builder platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS -- wide open for local dev, tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # In-memory agent store (replaced by DB in Sprint 2)
    agents: dict[str, AgentConfig] = {}

    # Seed a demo agent so the API is testable out of the box
    demo = AgentConfig(
        id="demo",
        name="Demo Agent",
        description="A simple demo agent for testing the API",
        system_prompt=(
            "You are a helpful assistant. Answer questions concisely. "
            "If you don't know the answer, say so."
        ),
    )
    agents[demo.id] = demo

    # --- Routes -----------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    @app.get("/agents", response_model=list[AgentConfig])
    async def list_agents() -> list[AgentConfig]:
        """List all registered agents."""
        return list(agents.values())

    @app.post("/agents", response_model=AgentConfig, status_code=201)
    async def create_agent(config: AgentConfig) -> AgentConfig:
        """Register a new agent configuration."""
        agents[config.id] = config
        logger.info("Created agent %s (%s)", config.name, config.id)
        return config

    @app.get("/agents/{agent_id}", response_model=AgentConfig)
    async def get_agent(agent_id: str) -> AgentConfig | JSONResponse:
        """Get a single agent by ID."""
        agent = agents.get(agent_id)
        if not agent:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})
        return agent

    @app.post("/agents/run", response_model=RunResult)
    async def run_agent_endpoint(request: RunRequest) -> RunResult | JSONResponse:
        """Execute an agent (blocking) and return the result."""
        agent = agents.get(request.agent_id)
        if not agent:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})
        result = await run_agent(agent, request.message, request.context)
        return result

    @app.post("/agents/run/stream", response_model=None)
    async def stream_agent_endpoint(request: RunRequest) -> EventSourceResponse | JSONResponse:
        """Execute an agent with Server-Sent Events streaming."""
        agent = agents.get(request.agent_id)
        if not agent:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})

        async def event_generator() -> AsyncGenerator[dict[str, str], None]:
            async for event in stream_agent(agent, request.message, request.context):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"])
                    if isinstance(event["data"], dict)
                    else str(event["data"]),
                }

        return EventSourceResponse(event_generator())

    return app


# Module-level app instance used by uvicorn
app = create_app()
