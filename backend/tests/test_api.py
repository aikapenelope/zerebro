"""Tests for the FastAPI application endpoints.

Uses httpx async client with the FastAPI test client. The runner module is
patched at the module level to avoid requiring deepagents (which needs
Docker to install properly on this platform).

Database: Each test gets a fresh in-memory SQLite database via ``set_engine()``.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Stub out third-party modules that aren't available in the build env.
# This lets us import zerebro.api.app without deepagents installed.
# ---------------------------------------------------------------------------
_STUBS = [
    "deepagents",
    # langchain / langchain_core / langgraph have deep import chains
    "langchain",
    "langchain.agents",
    "langchain.agents.structured_output",
    "langchain_core",
    "langchain_core.language_models",
    "langchain_core.language_models.chat_models",
    "langchain_core.messages",
    "langchain_core.prompts",
    "langchain_core.tools",
    "langchain_mcp_adapters",
    "langchain_mcp_adapters.client",
    "langgraph",
    "langgraph.graph",
    "langgraph.graph.state",
    "langgraph.prebuilt",
    "phoenix",
    "phoenix.otel",
    "openinference",
    "openinference.instrumentation",
    "openinference.instrumentation.langchain",
    "sse_starlette",
    "sse_starlette.sse",
]

_saved: dict[str, ModuleType | None] = {}
for _mod_name in _STUBS:
    if _mod_name not in sys.modules:
        _saved[_mod_name] = None
        sys.modules[_mod_name] = MagicMock()
    else:
        _saved[_mod_name] = sys.modules[_mod_name]

# Provide a real-ish EventSourceResponse so the app module can reference it
_sse_mod = sys.modules["sse_starlette.sse"]
_sse_mod.EventSourceResponse = MagicMock()  # type: ignore[union-attr]

# Now we can safely import app-level modules
from zerebro.db.engine import set_engine  # noqa: E402
from zerebro.models.agent import RunResult, RunStatus  # noqa: E402


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    """Async HTTP client backed by a fresh in-memory SQLite database.

    Each test gets its own database so tests are fully isolated.
    We manually create tables and seed the demo agent because httpx's
    ASGITransport does not trigger ASGI lifespan events.
    """
    # Create a fresh in-memory SQLite engine BEFORE importing app modules
    # so the lazy engine in db.engine never tries to connect to PostgreSQL.
    test_engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
    )
    set_engine(test_engine)

    from zerebro.db.engine import init_db

    await init_db()

    # Import after engine is set so module-level app = create_app() uses SQLite
    from zerebro.api.app import _seed_demo_agent, create_app

    await _seed_demo_agent()

    with patch("zerebro.core.tracing.init_tracing"):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    # Dispose the engine after the test
    await test_engine.dispose()


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAgentCRUD:
    @pytest.mark.asyncio
    async def test_list_agents_includes_demo(self, client: AsyncClient) -> None:
        resp = await client.get("/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert any(a["id"] == "demo" for a in agents)

    @pytest.mark.asyncio
    async def test_get_demo_agent(self, client: AsyncClient) -> None:
        resp = await client.get("/agents/demo")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Demo Agent"

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, client: AsyncClient) -> None:
        resp = await client.get("/agents/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_agent(self, client: AsyncClient) -> None:
        payload = {
            "name": "Test Agent",
            "system_prompt": "You are a test agent",
        }
        resp = await client.post("/agents", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Agent"
        assert data["id"]  # auto-generated

        # Verify it's now in the list
        list_resp = await client.get("/agents")
        ids = [a["id"] for a in list_resp.json()]
        assert data["id"] in ids

    @pytest.mark.asyncio
    async def test_update_agent(self, client: AsyncClient) -> None:
        """PATCH /agents/{id} applies partial updates."""
        resp = await client.patch(
            "/agents/demo",
            json={"name": "Updated Demo", "description": "new desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Demo"
        assert data["description"] == "new desc"
        # system_prompt should remain unchanged
        assert data["system_prompt"] != ""

    @pytest.mark.asyncio
    async def test_update_nonexistent_agent(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/agents/nonexistent",
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_agent(self, client: AsyncClient) -> None:
        # Create an agent to delete
        create_resp = await client.post(
            "/agents",
            json={"name": "To Delete", "system_prompt": "delete me"},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.delete(f"/agents/{agent_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/agents/{agent_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_agent(self, client: AsyncClient) -> None:
        resp = await client.delete("/agents/nonexistent")
        assert resp.status_code == 404


class TestRunAgent:
    @pytest.mark.asyncio
    async def test_run_nonexistent_agent(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/agents/run",
            json={"agent_id": "nonexistent", "message": "hello"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_run_agent_success(self, client: AsyncClient) -> None:
        """Run the demo agent with a mocked runner."""
        mock_result = RunResult(
            agent_id="demo",
            status=RunStatus.COMPLETED,
            output="Hello! I'm the demo agent.",
            duration_ms=100,
        )
        with patch(
            "zerebro.api.app.run_agent",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(
                "/agents/run",
                json={"agent_id": "demo", "message": "hello"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output"] == "Hello! I'm the demo agent."
        assert data["duration_ms"] == 100


class TestRunHistory:
    @pytest.mark.asyncio
    async def test_list_runs_empty(self, client: AsyncClient) -> None:
        """A fresh agent has no run history."""
        resp = await client.get("/agents/demo/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_runs_after_execution(self, client: AsyncClient) -> None:
        """After running an agent, the run appears in history."""
        mock_result = RunResult(
            agent_id="demo",
            status=RunStatus.COMPLETED,
            output="Test output",
            duration_ms=50,
        )
        with patch(
            "zerebro.api.app.run_agent",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await client.post(
                "/agents/run",
                json={"agent_id": "demo", "message": "test run"},
            )

        resp = await client.get("/agents/demo/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 1
        assert runs[0]["agent_id"] == "demo"
        assert runs[0]["output"] == "Test output"

    @pytest.mark.asyncio
    async def test_list_runs_nonexistent_agent(self, client: AsyncClient) -> None:
        resp = await client.get("/agents/nonexistent/runs")
        assert resp.status_code == 404
