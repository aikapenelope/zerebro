/**
 * TypeScript types mirroring the backend Pydantic models.
 *
 * These are the data contracts between the Next.js frontend and the
 * FastAPI backend. Keep in sync with backend/src/zerebro/models/*.py.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export type ModelRole = "builder" | "worker";
export type TriggerType = "manual" | "cron" | "webhook";
export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export type SessionStatus = "active" | "proposed" | "confirmed" | "cancelled";
export type MCPTransport = "stdio" | "streamable_http" | "sse";

// ---------------------------------------------------------------------------
// Agent models
// ---------------------------------------------------------------------------

export interface SubAgentConfig {
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  model_override: string | null;
}

export interface TriggerConfig {
  type: TriggerType;
  cron_expression: string | null;
  webhook_path: string | null;
}

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model_role: ModelRole;
  model_override: string | null;
  tools: string[];
  subagents: SubAgentConfig[];
  triggers: TriggerConfig[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Run models
// ---------------------------------------------------------------------------

export interface RunRequest {
  agent_id: string;
  message: string;
  context?: Record<string, unknown>;
}

export interface RunResult {
  run_id: string;
  agent_id: string;
  status: RunStatus;
  output: string;
  structured_output: Record<string, unknown> | null;
  error: string | null;
  token_usage: Record<string, number>;
  duration_ms: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Builder / conversation models
// ---------------------------------------------------------------------------

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface BuilderSession {
  id: string;
  status: SessionStatus;
  messages: ConversationMessage[];
  proposed_config: AgentConfig | null;
  confirmed_agent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatRequest {
  session_id?: string | null;
  message: string;
}

export interface ChatResponse {
  session_id: string;
  response: string;
  status: SessionStatus;
  proposed_config: AgentConfig | null;
}

// ---------------------------------------------------------------------------
// MCP models
// ---------------------------------------------------------------------------

export interface MCPServerStatus {
  name: string;
  transport: MCPTransport;
  description: string;
  enabled: boolean;
  tool_count: number | null;
}

export interface MCPToolInfo {
  name: string;
  description: string;
  server_name: string;
}
