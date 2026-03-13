"""Tests for the FastAPI application endpoints.

Uses httpx async client with the FastAPI test client. The runner module is
patched at the module level to avoid requiring deepagents (which needs
Docker to install properly on this platform).
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Stub out third-party modules that aren't available in the build env.
# This lets us import zerebro.api.app without deepagents installed.
# ---------------------------------------------------------------------------
_STUBS = [
    "deepagents",
    "langchain_core",
    "langchain_core.messages",
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

# Now we can safely import the app
from zerebro.models.agent import RunResult, RunStatus  # noqa: E402


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    """Async HTTP client bound to the test app with lifespan triggered."""
    with patch("zerebro.core.tracing.init_tracing"):
        from zerebro.api.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Trigger lifespan startup by making a request
            # The ASGI transport handles lifespan events automatically
            yield ac


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
