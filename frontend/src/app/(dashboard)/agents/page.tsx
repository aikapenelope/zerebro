"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquare, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentCard } from "@/components/agent-card";
import { listAgents } from "@/lib/api";
import type { AgentConfig } from "@/lib/types";

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchAgents() {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgents();
      setAgents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAgents();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your AI agents. Create new ones via the Builder or manually.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchAgents}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Link href="/builder">
            <Button size="sm">
              <MessageSquare className="mr-2 h-4 w-4" />
              New Agent
            </Button>
          </Link>
        </div>
      </div>

      {loading && (
        <p className="text-sm text-muted-foreground">Loading agents...</p>
      )}

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">{error}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Make sure the backend is running on port 8000.
          </p>
        </div>
      )}

      {!loading && !error && agents.length === 0 && (
        <div className="flex flex-col items-center gap-4 rounded-md border border-dashed p-12">
          <Plus className="h-8 w-8 text-muted-foreground" />
          <div className="text-center">
            <p className="font-medium">No agents yet</p>
            <p className="text-sm text-muted-foreground">
              Create your first agent using the Builder.
            </p>
          </div>
          <Link href="/builder">
            <Button>
              <MessageSquare className="mr-2 h-4 w-4" />
              Open Builder
            </Button>
          </Link>
        </div>
      )}

      {!loading && agents.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      )}
    </div>
  );
}
