"""Models for MCP (Model Context Protocol) server configuration and tools.

These models define how MCP servers are configured and discovered. Each
``MCPServerConfig`` maps to a connection entry in ``MultiServerMCPClient``.
The transport type determines which connection parameters are required.

Supported transports:
- ``stdio``: Local process (command + args)
- ``streamable_http``: HTTP-based MCP server (url)
- ``sse``: Server-Sent Events transport (url)
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MCPTransport(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"
    SSE = "sse"


# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server.

    The ``transport`` field determines which connection parameters are used:
    - ``stdio``: requires ``command`` (and optionally ``args``, ``env``)
    - ``streamable_http``: requires ``url`` (and optionally ``headers``)
    - ``sse``: requires ``url`` (and optionally ``headers``)
    """

    name: str = Field(description="Unique identifier for this MCP server (e.g. 'mcp-github')")
    transport: MCPTransport = Field(description="Transport type for connecting to the server")
    description: str = Field(
        default="",
        description="Human-readable description of what this server provides",
    )
    enabled: bool = Field(default=True, description="Whether this server is active")

    # --- stdio transport fields ---
    command: str | None = Field(
        default=None,
        description="Command to run for stdio transport (e.g. 'npx', 'python')",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Arguments for the stdio command",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the stdio process",
    )

    # --- HTTP-based transport fields (streamable_http, sse) ---
    url: str | None = Field(
        default=None,
        description="URL for streamable_http or sse transport",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP headers for streamable_http or sse transport",
    )

    def to_connection_dict(self) -> dict[str, Any]:
        """Convert to the dict format expected by MultiServerMCPClient.

        Returns:
            A dict matching StdioConnection, StreamableHttpConnection,
            or SSEConnection TypedDict format.

        Raises:
            ValueError: If required fields for the transport are missing.
        """
        if self.transport == MCPTransport.STDIO:
            if not self.command:
                msg = f"MCP server '{self.name}': stdio transport requires 'command'"
                raise ValueError(msg)
            conn: dict[str, Any] = {
                "transport": "stdio",
                "command": self.command,
                "args": self.args,
            }
            if self.env:
                conn["env"] = self.env
            return conn

        if self.transport == MCPTransport.STREAMABLE_HTTP:
            if not self.url:
                msg = f"MCP server '{self.name}': streamable_http transport requires 'url'"
                raise ValueError(msg)
            conn = {
                "transport": "streamable_http",
                "url": self.url,
            }
            if self.headers:
                conn["headers"] = self.headers
            return conn

        if self.transport == MCPTransport.SSE:
            if not self.url:
                msg = f"MCP server '{self.name}': sse transport requires 'url'"
                raise ValueError(msg)
            conn = {
                "transport": "sse",
                "url": self.url,
            }
            if self.headers:
                conn["headers"] = self.headers
            return conn

        msg = f"Unsupported transport: {self.transport}"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Tool metadata (returned by API, not used for connection)
# ---------------------------------------------------------------------------


class MCPToolInfo(BaseModel):
    """Metadata about a tool exposed by an MCP server.

    This is a lightweight representation for API responses -- the actual
    ``BaseTool`` instances live in the MCPManager at runtime.
    """

    name: str = Field(description="Tool name as exposed by the MCP server")
    description: str = Field(default="", description="What this tool does")
    server_name: str = Field(description="Which MCP server provides this tool")


class MCPServerStatus(BaseModel):
    """Status information for an MCP server, returned by the API."""

    name: str
    transport: MCPTransport
    description: str = ""
    enabled: bool = True
    tool_count: int | None = Field(
        default=None,
        description="Number of tools available (None if not yet loaded)",
    )
