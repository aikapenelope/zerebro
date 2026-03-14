"""FastAPI application -- the main entry point for the Zerebro backend.

Provides:
- ``GET    /agents``                       -- list all agents
- ``POST   /agents``                       -- create an agent
- ``GET    /agents/{id}``                  -- get an agent
- ``PATCH  /agents/{id}``                  -- partially update an agent
- ``DELETE /agents/{id}``                  -- delete an agent
- ``POST   /agents/run``                   -- execute an agent (blocking)
- ``POST   /agents/run/stream``            -- execute an agent with SSE streaming
- ``POST   /builder/chat``                 -- conversational agent builder
- ``POST   /builder/sessions/{id}/confirm``-- confirm a built agent
- ``GET    /mcp/servers``                  -- list configured MCP servers
- ``GET    /mcp/servers/{name}/tools``     -- list tools from an MCP server
- ``GET    /health``                       -- liveness / readiness probe
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

from zerebro.api.builder_routes import create_builder_router
from zerebro.api.mcp_routes import create_mcp_router
from zerebro.config import settings
from zerebro.core.mcp_manager import MCPManager
from zerebro.core.runner import run_agent, set_mcp_manager, stream_agent
from zerebro.core.tracing import init_tracing
from zerebro.models.agent import AgentConfig, AgentUpdate, RunRequest, RunResult
from zerebro.models.conversation import BuilderSession
from zerebro.models.mcp import MCPServerConfig

logger = logging.getLogger(__name__)


def _load_mcp_servers_from_settings() -> list[MCPServerConfig]:
    """Load MCP server configurations from settings / environment.

    MCP servers are configured via the ``MCP_SERVERS`` environment variable
    as a JSON array of server config objects. Example::

        MCP_SERVERS='[
            {"name": "mcp-github", "transport": "stdio",
             "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
             "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."},
             "description": "GitHub MCP server"},
            {"name": "mcp-web", "transport": "streamable_http",
             "url": "http://localhost:3001/mcp",
             "description": "Web search MCP server"}
        ]'

    Returns:
        List of MCPServerConfig instances. Empty if not configured.
    """
    mcp_servers_json = settings.mcp_servers_json
    if not mcp_servers_json:
        return []

    import json as json_mod

    try:
        raw_configs = json_mod.loads(mcp_servers_json)
        if not isinstance(raw_configs, list):
            logger.error("MCP_SERVERS must be a JSON array, got %s", type(raw_configs).__name__)
            return []
        configs = [MCPServerConfig.model_validate(c) for c in raw_configs]
        logger.info("Loaded %d MCP server configs from MCP_SERVERS", len(configs))
        return configs
    except Exception:
        logger.exception("Failed to parse MCP_SERVERS environment variable")
        return []


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
        version="0.3.0",
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

    # In-memory stores (replaced by DB in a future sprint)
    agents: dict[str, AgentConfig] = {}
    builder_sessions: dict[str, BuilderSession] = {}

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

    # --- MCP Manager ------------------------------------------------------
    mcp_configs = _load_mcp_servers_from_settings()
    mcp_manager = MCPManager(mcp_configs)
    set_mcp_manager(mcp_manager)

    # --- Routers ----------------------------------------------------------
    builder_router = create_builder_router(builder_sessions, agents)
    app.include_router(builder_router)

    mcp_router = create_mcp_router(mcp_manager)
    app.include_router(mcp_router)

    # --- Agent routes -----------------------------------------------------

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

    @app.patch("/agents/{agent_id}", response_model=AgentConfig)
    async def update_agent(agent_id: str, update: AgentUpdate) -> AgentConfig | JSONResponse:
        """Partially update an agent configuration.

        Only fields present in the request body are applied.
        """
        agent = agents.get(agent_id)
        if not agent:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})

        # Apply only the fields that were explicitly provided
        update_data = update.model_dump(exclude_unset=True)
        updated = agent.model_copy(update=update_data)
        agents[agent_id] = updated
        logger.info(
            "Updated agent %s (%s), fields: %s",
            updated.name, agent_id, list(update_data.keys()),
        )
        return updated

    @app.delete("/agents/{agent_id}", status_code=204, response_model=None)
    async def delete_agent(agent_id: str) -> JSONResponse | None:
        """Delete an agent by ID."""
        if agent_id not in agents:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})
        del agents[agent_id]
        logger.info("Deleted agent %s", agent_id)
        return None

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
