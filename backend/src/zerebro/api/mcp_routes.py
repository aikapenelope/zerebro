"""MCP server discovery and tool listing API routes.

Provides endpoints for discovering available MCP servers and their tools:
- ``GET  /mcp/servers``              -- list all configured MCP servers
- ``GET  /mcp/servers/{name}/tools`` -- list tools from a specific server
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from zerebro.core.mcp_manager import MCPManager
from zerebro.models.mcp import MCPServerStatus, MCPToolInfo

logger = logging.getLogger(__name__)


def create_mcp_router(mcp_manager: MCPManager) -> APIRouter:
    """Create the MCP API router.

    Args:
        mcp_manager: The shared MCPManager instance.

    Returns:
        An APIRouter with MCP discovery endpoints.
    """
    router = APIRouter(prefix="/mcp", tags=["mcp"])

    @router.get("/servers", response_model=list[MCPServerStatus])
    async def list_servers() -> list[MCPServerStatus]:
        """List all configured MCP servers and their status."""
        servers: list[MCPServerStatus] = []
        for name in mcp_manager.server_names:
            config = mcp_manager.get_server_config(name)
            if not config:
                continue
            # Check if tools are cached (don't trigger a load)
            cached_tools = mcp_manager._tool_cache.get(name)
            servers.append(
                MCPServerStatus(
                    name=config.name,
                    transport=config.transport,
                    description=config.description,
                    enabled=config.enabled,
                    tool_count=len(cached_tools) if cached_tools is not None else None,
                )
            )
        return servers

    @router.get("/servers/{server_name}/tools", response_model=list[MCPToolInfo])
    async def list_server_tools(server_name: str) -> list[MCPToolInfo] | JSONResponse:
        """List tools available from a specific MCP server.

        This will connect to the server and load tools if not already cached.
        """
        config = mcp_manager.get_server_config(server_name)
        if not config:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"MCP server '{server_name}' not found. "
                    f"Available: {mcp_manager.server_names}"
                },
            )
        try:
            tool_infos = await mcp_manager.get_tool_info(server_name)
            return tool_infos
        except Exception as exc:
            logger.exception("Failed to load tools from MCP server '%s'", server_name)
            return JSONResponse(
                status_code=502,
                content={
                    "detail": f"Failed to connect to MCP server '{server_name}': {exc}"
                },
            )

    return router
