"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Server,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listMCPServers, listMCPServerTools } from "@/lib/api";
import type { MCPServerStatus, MCPToolInfo } from "@/lib/types";

/**
 * MCP Servers page -- list configured MCP servers and their tools.
 *
 * Each server card is expandable to show the tools it provides.
 */
export default function MCPPage() {
  const [servers, setServers] = useState<MCPServerStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track which servers are expanded and their tools
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [tools, setTools] = useState<Record<string, MCPToolInfo[]>>({});
  const [toolsLoading, setToolsLoading] = useState<Record<string, boolean>>({});

  const fetchServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMCPServers();
      setServers(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load MCP servers",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  const toggleServer = useCallback(
    async (serverName: string) => {
      const isExpanded = expanded[serverName];
      setExpanded((prev) => ({ ...prev, [serverName]: !isExpanded }));

      // Load tools on first expand
      if (!isExpanded && !tools[serverName]) {
        setToolsLoading((prev) => ({ ...prev, [serverName]: true }));
        try {
          const serverTools = await listMCPServerTools(serverName);
          setTools((prev) => ({ ...prev, [serverName]: serverTools }));
        } catch {
          setTools((prev) => ({ ...prev, [serverName]: [] }));
        } finally {
          setToolsLoading((prev) => ({ ...prev, [serverName]: false }));
        }
      }
    },
    [expanded, tools],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">MCP Servers</h1>
          <p className="mt-1 text-muted-foreground">
            View configured MCP servers and available tools.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchServers}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading servers...
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {!loading && !error && servers.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Server className="mb-4 h-12 w-12 text-muted-foreground/50" />
            <p className="text-lg font-medium">No MCP servers configured</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Set the MCP_SERVERS environment variable to configure servers.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {servers.map((server) => (
          <Card key={server.name}>
            <CardHeader className="pb-3">
              <button
                onClick={() => toggleServer(server.name)}
                className="flex w-full items-center gap-3 text-left"
              >
                {expanded[server.name] ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
                <Server className="h-5 w-5" />
                <div className="flex-1">
                  <CardTitle className="text-base">{server.name}</CardTitle>
                  {server.description && (
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      {server.description}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{server.transport}</Badge>
                  <Badge
                    variant={server.enabled ? "default" : "secondary"}
                  >
                    {server.enabled ? "Active" : "Disabled"}
                  </Badge>
                  {server.tool_count !== null && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Wrench className="h-3 w-3" />
                      {server.tool_count}
                    </span>
                  )}
                </div>
              </button>
            </CardHeader>

            {expanded[server.name] && (
              <CardContent className="pt-0">
                {toolsLoading[server.name] && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Loading tools...
                  </div>
                )}

                {!toolsLoading[server.name] &&
                  tools[server.name]?.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No tools available from this server.
                    </p>
                  )}

                {!toolsLoading[server.name] &&
                  tools[server.name] &&
                  tools[server.name].length > 0 && (
                    <div className="space-y-2">
                      {tools[server.name].map((tool) => (
                        <div
                          key={tool.name}
                          className="rounded-md border p-3"
                        >
                          <div className="flex items-center gap-2">
                            <Wrench className="h-4 w-4 text-muted-foreground" />
                            <span className="font-mono text-sm font-medium">
                              {tool.name}
                            </span>
                          </div>
                          {tool.description && (
                            <p className="mt-1 pl-6 text-sm text-muted-foreground">
                              {tool.description}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
              </CardContent>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
