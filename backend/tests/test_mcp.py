"""Tests for MCP models, MCPManager, and MCP API endpoints.

All MCP server connections are mocked -- no real MCP servers needed.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Stub third-party modules not available in the build environment
# ---------------------------------------------------------------------------
_STUBS = [
    "deepagents",
    "langchain",
    "langchain.agents",
    "langchain.agents.structured_output",
    "langchain.chat_models",
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.tools",
    "langchain_mcp_adapters",
    "langchain_mcp_adapters.client",
    "langchain_mcp_adapters.sessions",
    "langgraph",
    "langgraph.checkpoint",
    "langgraph.checkpoint.base",
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio",
    "langgraph.graph",
    "langgraph.graph.state",
    "langgraph.store",
    "langgraph.store.base",
    "langgraph.store.postgres",
    "phoenix",
    "phoenix.otel",
    "openinference",
    "openinference.instrumentation",
    "openinference.instrumentation.langchain",
    "sse_starlette",
    "sse_starlette.sse",
]

for _mod_name in _STUBS:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Ensure BaseTool is a usable class for isinstance checks
_mock_base_tool = type("BaseTool", (), {"name": "", "description": ""})
sys.modules["langchain_core.tools"].BaseTool = _mock_base_tool  # type: ignore[union-attr]

_sse_mod = sys.modules["sse_starlette.sse"]
_sse_mod.EventSourceResponse = MagicMock()  # type: ignore[union-attr]

from zerebro.models.mcp import (  # noqa: E402
    MCPServerConfig,
    MCPServerStatus,
    MCPToolInfo,
    MCPTransport,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestMCPServerConfig:
    def test_stdio_config(self) -> None:
        config = MCPServerConfig(
            name="mcp-github",
            transport=MCPTransport.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "ghp_test"},
            description="GitHub MCP server",
        )
        conn = config.to_connection_dict()
        assert conn["transport"] == "stdio"
        assert conn["command"] == "npx"
        assert conn["args"] == ["-y", "@modelcontextprotocol/server-github"]
        assert conn["env"] == {"GITHUB_TOKEN": "ghp_test"}

    def test_streamable_http_config(self) -> None:
        config = MCPServerConfig(
            name="mcp-web",
            transport=MCPTransport.STREAMABLE_HTTP,
            url="http://localhost:3001/mcp",
            headers={"Authorization": "Bearer test"},
        )
        conn = config.to_connection_dict()
        assert conn["transport"] == "streamable_http"
        assert conn["url"] == "http://localhost:3001/mcp"
        assert conn["headers"] == {"Authorization": "Bearer test"}

    def test_sse_config(self) -> None:
        config = MCPServerConfig(
            name="mcp-sse",
            transport=MCPTransport.SSE,
            url="http://localhost:3002/sse",
        )
        conn = config.to_connection_dict()
        assert conn["transport"] == "sse"
        assert conn["url"] == "http://localhost:3002/sse"
        assert "headers" not in conn  # No headers when empty

    def test_stdio_missing_command_raises(self) -> None:
        config = MCPServerConfig(
            name="bad",
            transport=MCPTransport.STDIO,
        )
        with pytest.raises(ValueError, match="requires 'command'"):
            config.to_connection_dict()

    def test_http_missing_url_raises(self) -> None:
        config = MCPServerConfig(
            name="bad",
            transport=MCPTransport.STREAMABLE_HTTP,
        )
        with pytest.raises(ValueError, match="requires 'url'"):
            config.to_connection_dict()

    def test_disabled_server(self) -> None:
        config = MCPServerConfig(
            name="disabled",
            transport=MCPTransport.STDIO,
            command="echo",
            enabled=False,
        )
        assert config.enabled is False

    def test_json_roundtrip(self) -> None:
        config = MCPServerConfig(
            name="test",
            transport=MCPTransport.STREAMABLE_HTTP,
            url="http://localhost:3000/mcp",
            description="Test server",
        )
        data = config.model_dump(mode="json")
        restored = MCPServerConfig.model_validate(data)
        assert restored.name == "test"
        assert restored.transport == MCPTransport.STREAMABLE_HTTP
        assert restored.url == "http://localhost:3000/mcp"


class TestMCPToolInfo:
    def test_tool_info_creation(self) -> None:
        info = MCPToolInfo(
            name="search_repos",
            description="Search GitHub repositories",
            server_name="mcp-github",
        )
        assert info.name == "search_repos"
        assert info.server_name == "mcp-github"


class TestMCPServerStatus:
    def test_status_with_tool_count(self) -> None:
        status = MCPServerStatus(
            name="mcp-github",
            transport=MCPTransport.STDIO,
            description="GitHub",
            tool_count=5,
        )
        assert status.tool_count == 5

    def test_status_without_tool_count(self) -> None:
        status = MCPServerStatus(
            name="mcp-github",
            transport=MCPTransport.STDIO,
        )
        assert status.tool_count is None


# ---------------------------------------------------------------------------
# MCPManager tests
# ---------------------------------------------------------------------------


class TestMCPManager:
    def test_register_and_list_servers(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        configs = [
            MCPServerConfig(
                name="server-a",
                transport=MCPTransport.STREAMABLE_HTTP,
                url="http://localhost:3001/mcp",
            ),
            MCPServerConfig(
                name="server-b",
                transport=MCPTransport.STDIO,
                command="echo",
                enabled=False,  # Should be excluded
            ),
        ]
        manager = MCPManager(configs)
        # Only enabled servers are registered
        assert "server-a" in manager.server_names
        assert "server-b" not in manager.server_names

    def test_register_server_dynamically(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        manager = MCPManager()
        assert manager.server_names == []

        manager.register_server(
            MCPServerConfig(
                name="dynamic",
                transport=MCPTransport.SSE,
                url="http://localhost:3003/sse",
            )
        )
        assert "dynamic" in manager.server_names

    def test_remove_server(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        manager = MCPManager(
            [
                MCPServerConfig(
                    name="removable",
                    transport=MCPTransport.STREAMABLE_HTTP,
                    url="http://localhost:3001/mcp",
                )
            ]
        )
        assert "removable" in manager.server_names
        manager.remove_server("removable")
        assert "removable" not in manager.server_names

    @pytest.mark.asyncio
    async def test_resolve_tools_empty(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        manager = MCPManager()
        tools = await manager.resolve_tools([])
        assert tools == []

    @pytest.mark.asyncio
    async def test_resolve_tools_unknown_server_skipped(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        manager = MCPManager()
        tools = await manager.resolve_tools(["nonexistent"])
        assert tools == []

    @pytest.mark.asyncio
    async def test_resolve_tools_with_mock_client(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        # Create mock tools
        mock_tool_1 = MagicMock()
        mock_tool_1.name = "mcp-github_search_repos"
        mock_tool_1.description = "Search repos"

        mock_tool_2 = MagicMock()
        mock_tool_2.name = "mcp-github_create_issue"
        mock_tool_2.description = "Create issue"

        manager = MCPManager(
            [
                MCPServerConfig(
                    name="mcp-github",
                    transport=MCPTransport.STDIO,
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-github"],
                )
            ]
        )

        # Mock the MultiServerMCPClient.get_tools call
        mock_client_instance = MagicMock()
        mock_client_instance.get_tools = AsyncMock(
            return_value=[mock_tool_1, mock_tool_2]
        )

        with patch(
            "zerebro.core.mcp_manager.MultiServerMCPClient",
            return_value=mock_client_instance,
        ):
            tools = await manager.resolve_tools(["mcp-github"])

        assert len(tools) == 2
        assert tools[0].name == "mcp-github_search_repos"
        assert tools[1].name == "mcp-github_create_issue"

    @pytest.mark.asyncio
    async def test_tool_caching(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        mock_tool = MagicMock()
        mock_tool.name = "cached_tool"
        mock_tool.description = "A cached tool"

        manager = MCPManager(
            [
                MCPServerConfig(
                    name="cached-server",
                    transport=MCPTransport.STREAMABLE_HTTP,
                    url="http://localhost:3001/mcp",
                )
            ]
        )

        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])

        with patch(
            "zerebro.core.mcp_manager.MultiServerMCPClient",
            return_value=mock_client,
        ):
            # First call loads from server
            tools1 = await manager.get_tools_for_server("cached-server")
            # Second call should use cache (client not called again)
            tools2 = await manager.get_tools_for_server("cached-server")

        assert tools1 == tools2
        # MultiServerMCPClient constructor called only once
        assert mock_client.get_tools.call_count == 1

    @pytest.mark.asyncio
    async def test_invalidate_cache(self) -> None:
        from zerebro.core.mcp_manager import MCPManager

        mock_tool = MagicMock()
        mock_tool.name = "tool"
        mock_tool.description = ""

        manager = MCPManager(
            [
                MCPServerConfig(
                    name="srv",
                    transport=MCPTransport.STREAMABLE_HTTP,
                    url="http://localhost:3001/mcp",
                )
            ]
        )

        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])

        with patch(
            "zerebro.core.mcp_manager.MultiServerMCPClient",
            return_value=mock_client,
        ):
            await manager.get_tools_for_server("srv")
            manager.invalidate_cache("srv")
            await manager.get_tools_for_server("srv")

        # Called twice because cache was invalidated
        assert mock_client.get_tools.call_count == 2


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    """Async HTTP client with MCP manager mocked."""
    with patch("zerebro.core.tracing.init_tracing"):
        from zerebro.api.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestMCPAPI:
    @pytest.mark.asyncio
    async def test_list_servers_empty(self, client: AsyncClient) -> None:
        """No MCP servers configured by default."""
        resp = await client.get("/mcp/servers")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_server_tools_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/mcp/servers/nonexistent/tools")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_servers_with_config(self) -> None:
        """Test with MCP servers configured via settings."""
        import json

        servers_json = json.dumps(
            [
                {
                    "name": "test-server",
                    "transport": "streamable_http",
                    "url": "http://localhost:3001/mcp",
                    "description": "Test MCP server",
                }
            ]
        )

        with (
            patch("zerebro.core.tracing.init_tracing"),
            patch("zerebro.api.app.settings") as mock_settings,
        ):
            # Copy real settings and override mcp_servers_json
            from zerebro.config import Settings
            from zerebro.config import settings as real_settings

            for field in Settings.model_fields:
                setattr(mock_settings, field, getattr(real_settings, field))
            mock_settings.mcp_servers_json = servers_json

            from zerebro.api.app import create_app

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/mcp/servers")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-server"
        assert data[0]["transport"] == "streamable_http"
        assert data[0]["tool_count"] is None  # Not loaded yet
