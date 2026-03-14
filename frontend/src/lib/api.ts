/**
 * API client for the Zerebro FastAPI backend.
 *
 * All requests go through the Next.js rewrite proxy (/api/* -> backend:8000/*).
 * This keeps the browser origin-safe and avoids CORS in production.
 */

import type {
  AgentConfig,
  ChatRequest,
  ChatResponse,
  MCPServerStatus,
  MCPToolInfo,
  RunRequest,
  RunResult,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export async function listAgents(): Promise<AgentConfig[]> {
  return request<AgentConfig[]>("/agents");
}

export async function getAgent(id: string): Promise<AgentConfig> {
  return request<AgentConfig>(`/agents/${encodeURIComponent(id)}`);
}

export async function createAgent(config: Partial<AgentConfig>): Promise<AgentConfig> {
  return request<AgentConfig>("/agents", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function updateAgent(
  id: string,
  patch: Partial<AgentConfig>,
): Promise<AgentConfig> {
  return request<AgentConfig>(`/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteAgent(id: string): Promise<void> {
  await request<unknown>(`/agents/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Agent execution
// ---------------------------------------------------------------------------

export async function runAgent(req: RunRequest): Promise<RunResult> {
  return request<RunResult>("/agents/run", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/**
 * Stream agent execution via SSE.
 *
 * Returns the raw Response so the caller can read the event stream.
 * Use with EventSource-like parsing on the client side.
 */
export async function streamAgent(req: RunRequest): Promise<Response> {
  const res = await fetch(`${BASE}/agents/run/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Builder (Twin mode)
// ---------------------------------------------------------------------------

export async function builderChat(req: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/builder/chat", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function listBuilderSessions() {
  return request<import("./types").BuilderSession[]>("/builder/sessions");
}

export async function getBuilderSession(id: string) {
  return request<import("./types").BuilderSession>(
    `/builder/sessions/${encodeURIComponent(id)}`,
  );
}

export async function confirmSession(sessionId: string): Promise<AgentConfig> {
  return request<AgentConfig>(
    `/builder/sessions/${encodeURIComponent(sessionId)}/confirm`,
    { method: "POST" },
  );
}

export async function cancelSession(
  sessionId: string,
): Promise<{ status: string; session_id: string }> {
  return request<{ status: string; session_id: string }>(
    `/builder/sessions/${encodeURIComponent(sessionId)}/cancel`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// MCP
// ---------------------------------------------------------------------------

export async function listMCPServers(): Promise<MCPServerStatus[]> {
  return request<MCPServerStatus[]>("/mcp/servers");
}

export async function listMCPServerTools(
  serverName: string,
): Promise<MCPToolInfo[]> {
  return request<MCPToolInfo[]>(
    `/mcp/servers/${encodeURIComponent(serverName)}/tools`,
  );
}
