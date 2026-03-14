"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Clock,
  Cpu,
  Loader2,
  Save,
  Trash2,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { AgentRunPanel } from "@/components/agent-run-panel";
import { deleteAgent, getAgent, updateAgent } from "@/lib/api";
import type { AgentConfig, ModelRole } from "@/lib/types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [agent, setAgent] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const [editRole, setEditRole] = useState<ModelRole>("worker");
  const [editTools, setEditTools] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Fetch agent
  useEffect(() => {
    if (!params.id) return;
    setLoading(true);
    getAgent(params.id)
      .then((data) => {
        setAgent(data);
        setEditName(data.name);
        setEditDescription(data.description);
        setEditPrompt(data.system_prompt);
        setEditRole(data.model_role);
        setEditTools(data.tools.join(", "));
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load agent"),
      )
      .finally(() => setLoading(false));
  }, [params.id]);

  // Save edits
  const handleSave = useCallback(async () => {
    if (!agent) return;
    setSaving(true);
    try {
      const updated = await updateAgent(agent.id, {
        name: editName,
        description: editDescription,
        system_prompt: editPrompt,
        model_role: editRole,
        tools: editTools
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      setAgent(updated);
      setEditing(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save",
      );
    } finally {
      setSaving(false);
    }
  }, [agent, editName, editDescription, editPrompt, editRole, editTools]);

  // Delete agent
  const handleDelete = useCallback(async () => {
    if (!agent || !confirm(`Delete agent "${agent.name}"?`)) return;
    setDeleting(true);
    try {
      await deleteAgent(agent.id);
      router.push("/agents");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete",
      );
      setDeleting(false);
    }
  }, [agent, router]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading agent...
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">
            {error || "Agent not found"}
          </p>
        </div>
        <Link href="/agents">
          <Button variant="outline" size="sm">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to agents
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href="/agents">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              <h1 className="text-2xl font-bold tracking-tight">
                {agent.name}
              </h1>
              <Badge
                variant={
                  agent.model_role === "builder" ? "default" : "secondary"
                }
              >
                {agent.model_role}
              </Badge>
            </div>
            {agent.description && (
              <p className="mt-1 text-muted-foreground">
                {agent.description}
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing(!editing)}
          >
            {editing ? "Cancel" : "Edit"}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="mr-2 h-4 w-4" />
            )}
            Delete
          </Button>
        </div>
      </div>

      {/* Edit form */}
      {editing && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Edit Agent</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium">Name</label>
                <Input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">
                  Model Role
                </label>
                <select
                  value={editRole}
                  onChange={(e) =>
                    setEditRole(e.target.value as ModelRole)
                  }
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                >
                  <option value="worker">Worker (fast/cheap)</option>
                  <option value="builder">Builder (high-reasoning)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">
                Description
              </label>
              <Input
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">
                System Prompt
              </label>
              <Textarea
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                rows={6}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium">
                Tools (comma-separated MCP server names)
              </label>
              <Input
                value={editTools}
                onChange={(e) => setEditTools(e.target.value)}
                placeholder="mcp-github, mcp-web-search"
              />
            </div>

            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Save Changes
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Agent info (read-only) */}
      {!editing && (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                System Prompt
              </p>
              <p className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
                {agent.system_prompt}
              </p>
            </div>

            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              {agent.tools.length > 0 && (
                <div className="flex items-center gap-1">
                  <Wrench className="h-4 w-4" />
                  <span>Tools:</span>
                  {agent.tools.map((t) => (
                    <Badge key={t} variant="outline">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
              {agent.subagents.length > 0 && (
                <div className="flex items-center gap-1">
                  <Cpu className="h-4 w-4" />
                  <span>
                    {agent.subagents.length} sub-agent
                    {agent.subagents.length !== 1 && "s"}
                  </span>
                </div>
              )}
              <div className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                <span>Created {formatDate(agent.created_at)}</span>
              </div>
            </div>

            {agent.subagents.length > 0 && (
              <>
                <Separator />
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Sub-agents
                  </p>
                  <div className="space-y-2">
                    {agent.subagents.map((sa) => (
                      <div
                        key={sa.name}
                        className="rounded-md border p-3 text-sm"
                      >
                        <p className="font-medium">{sa.name}</p>
                        <p className="text-muted-foreground">
                          {sa.description}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {sa.system_prompt.slice(0, 100)}
                          {sa.system_prompt.length > 100 && "..."}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Run panel */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Run Agent</h2>
        <AgentRunPanel agentId={agent.id} />
      </div>
    </div>
  );
}
