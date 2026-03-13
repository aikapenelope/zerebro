"""MCP Manager -- manages MCP server connections and tool resolution.

The ``MCPManager`` is the bridge between Zerebro's ``MCPServerConfig`` models
and the ``langchain-mcp-adapters`` ``MultiServerMCPClient``. It:

1. Builds connection dicts from ``MCPServerConfig`` instances
2. Creates a ``MultiServerMCPClient`` with those connections
3. Loads tools from servers (with caching)
4. Resolves tool name strings from ``AgentConfig.tools`` into actual
   ``BaseTool`` instances that ``create_deep_agent()`` can use

Usage::

    manager = MCPManager(server_configs)
    tools = await manager.resolve_tools(["mcp-github", "mcp-slack"])
    # tools is a list[BaseTool] ready for create_deep_agent(tools=tools)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from zerebro.models.mcp import MCPServerConfig, MCPToolInfo

logger = logging.getLogger(__name__)


class MCPManager:
    """Manages MCP server connections and tool resolution.

    Wraps ``MultiServerMCPClient`` and provides a higher-level API for
    resolving tool names (as stored in ``AgentConfig.tools``) into actual
    ``BaseTool`` instances.
    """

    def __init__(self, server_configs: list[MCPServerConfig] | None = None) -> None:
        """Initialize the MCP Manager.

        Args:
            server_configs: List of MCP server configurations. Only enabled
                servers are registered. Can be updated later via
                ``register_server()``.
        """
        self._configs: dict[str, MCPServerConfig] = {}
        self._tool_cache: dict[str, list[BaseTool]] = {}

        if server_configs:
            for config in server_configs:
                if config.enabled:
                    self._configs[config.name] = config

    @property
    def server_names(self) -> list[str]:
        """Return names of all registered (enabled) servers."""
        return list(self._configs.keys())

    def get_server_config(self, name: str) -> MCPServerConfig | None:
        """Get the configuration for a specific server."""
        return self._configs.get(name)

    def register_server(self, config: MCPServerConfig) -> None:
        """Register or update an MCP server configuration.

        Args:
            config: The server configuration to register.
        """
        self._configs[config.name] = config
        # Invalidate cache for this server
        self._tool_cache.pop(config.name, None)
        logger.info("Registered MCP server '%s' (%s)", config.name, config.transport.value)

    def remove_server(self, name: str) -> None:
        """Remove an MCP server and its cached tools.

        Args:
            name: The server name to remove.
        """
        self._configs.pop(name, None)
        self._tool_cache.pop(name, None)
        logger.info("Removed MCP server '%s'", name)

    def _build_client(self, server_names: list[str]) -> MultiServerMCPClient:
        """Build a MultiServerMCPClient for the specified servers.

        Args:
            server_names: Names of servers to include in the client.

        Returns:
            A configured MultiServerMCPClient.

        Raises:
            ValueError: If a server name is not registered.
        """
        connections: dict[str, Any] = {}
        for name in server_names:
            config = self._configs.get(name)
            if not config:
                msg = (
                    f"MCP server '{name}' is not registered. "
                    f"Available: {self.server_names}"
                )
                raise ValueError(msg)
            connections[name] = config.to_connection_dict()

        return MultiServerMCPClient(
            connections=connections,
            tool_name_prefix=True,
        )

    async def get_tools_for_server(self, server_name: str) -> list[BaseTool]:
        """Load tools from a specific MCP server.

        Results are cached -- subsequent calls return the cached tools.
        Call ``invalidate_cache()`` to force a reload.

        Args:
            server_name: Name of the server to load tools from.

        Returns:
            List of BaseTool instances from the server.

        Raises:
            ValueError: If the server is not registered.
        """
        if server_name in self._tool_cache:
            return self._tool_cache[server_name]

        client = self._build_client([server_name])
        tools = await client.get_tools(server_name=server_name)
        self._tool_cache[server_name] = tools
        logger.info(
            "Loaded %d tools from MCP server '%s': %s",
            len(tools),
            server_name,
            [t.name for t in tools],
        )
        return tools

    async def resolve_tools(self, tool_names: list[str]) -> list[BaseTool]:
        """Resolve a list of MCP server names into BaseTool instances.

        This is the main method used by the runner. It takes the tool name
        strings from ``AgentConfig.tools`` (which are MCP server names) and
        returns all tools from those servers.

        Args:
            tool_names: List of MCP server names to load tools from.

        Returns:
            Flat list of all BaseTool instances from the specified servers.
        """
        if not tool_names:
            return []

        all_tools: list[BaseTool] = []
        for name in tool_names:
            try:
                tools = await self.get_tools_for_server(name)
                all_tools.extend(tools)
            except ValueError:
                logger.warning(
                    "MCP server '%s' not registered, skipping. Available: %s",
                    name,
                    self.server_names,
                )
            except Exception:
                logger.exception("Failed to load tools from MCP server '%s'", name)

        return all_tools

    async def get_tool_info(self, server_name: str) -> list[MCPToolInfo]:
        """Get metadata about tools from a server (for API responses).

        Args:
            server_name: Name of the server.

        Returns:
            List of MCPToolInfo with name, description, and server_name.
        """
        tools = await self.get_tools_for_server(server_name)
        return [
            MCPToolInfo(
                name=tool.name,
                description=tool.description or "",
                server_name=server_name,
            )
            for tool in tools
        ]

    def invalidate_cache(self, server_name: str | None = None) -> None:
        """Clear the tool cache.

        Args:
            server_name: If provided, only clear cache for this server.
                If None, clear all caches.
        """
        if server_name:
            self._tool_cache.pop(server_name, None)
        else:
            self._tool_cache.clear()
        logger.info(
            "Invalidated tool cache%s",
            f" for '{server_name}'" if server_name else " (all)",
        )
