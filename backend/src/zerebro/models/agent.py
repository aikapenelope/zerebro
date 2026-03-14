"""Pydantic models for agent configuration and execution.

These models define the schema for creating, configuring, and running agents.
The AgentConfig is the core model that the Builder Agent produces as structured
output when creating new agents conversationally (twin.so style).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ModelRole(str, Enum):
    """Determines which LLM tier to use for an agent."""

    BUILDER = "builder"  # High-reasoning model (OpenAI/Anthropic)
    WORKER = "worker"  # Fast/cheap model (Groq)


class TriggerType(str, Enum):
    """How an agent run can be initiated."""

    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"


class RunStatus(str, Enum):
    """Lifecycle states of an agent run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Sub-agent definition
# ---------------------------------------------------------------------------


class SubAgentConfig(BaseModel):
    """Configuration for a sub-agent that can be spawned by a parent agent.

    Maps directly to the deepagents subagent dict format:
    {"name": ..., "description": ..., "system_prompt": ..., "tools": ..., "model": ...}
    """

    name: str = Field(description="Unique identifier for the sub-agent")
    description: str = Field(
        description="What this sub-agent does. The parent uses this to decide when to delegate."
    )
    system_prompt: str = Field(description="Instructions for the sub-agent")
    tools: list[str] = Field(
        default_factory=list,
        description="MCP server names or tool identifiers this sub-agent can use",
    )
    model_override: str | None = Field(
        default=None,
        description="Override the default model for this sub-agent",
    )


# ---------------------------------------------------------------------------
# Trigger definition
# ---------------------------------------------------------------------------


class TriggerConfig(BaseModel):
    """Defines how and when an agent should be triggered automatically."""

    type: TriggerType = Field(default=TriggerType.MANUAL)
    cron_expression: str | None = Field(
        default=None,
        description="Cron expression for scheduled runs (e.g. '0 9 * * 1-5' for weekdays at 9am)",
    )
    webhook_path: str | None = Field(
        default=None,
        description="URL path suffix for webhook triggers (e.g. '/hooks/my-agent')",
    )


# ---------------------------------------------------------------------------
# Agent configuration - the core model
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Complete configuration for an agent.

    This is the structured output that the Builder Agent produces when a user
    describes what they want conversationally. It contains everything needed
    to instantiate and run a deepagent.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="Human-readable name for the agent")
    description: str = Field(
        default="",
        description="What this agent does, shown in the agent list",
    )
    system_prompt: str = Field(
        description="Detailed instructions that define the agent's behavior and capabilities"
    )
    model_role: ModelRole = Field(
        default=ModelRole.WORKER,
        description="Model tier: 'builder' for complex reasoning, 'worker' for fast execution",
    )
    model_override: str | None = Field(
        default=None,
        description="Explicit model identifier, overrides model_role default",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="MCP server names or tool identifiers this agent can use",
    )
    subagents: list[SubAgentConfig] = Field(
        default_factory=list,
        description="Sub-agents this agent can delegate work to",
    )
    triggers: list[TriggerConfig] = Field(
        default_factory=list,
        description="Automatic triggers for this agent",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------


class AgentUpdate(BaseModel):
    """Partial update for an agent configuration.

    All fields are optional -- only provided fields are applied.
    """

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_role: ModelRole | None = None
    model_override: str | None = None
    tools: list[str] | None = None
    subagents: list[SubAgentConfig] | None = None
    triggers: list[TriggerConfig] | None = None


class RunRequest(BaseModel):
    """Request to execute an agent."""

    agent_id: str = Field(description="ID of the agent to run")
    message: str = Field(description="User message / task to execute")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context passed to the agent (e.g. file paths, parameters)",
    )


class RunResult(BaseModel):
    """Result of an agent execution."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    status: RunStatus = Field(default=RunStatus.COMPLETED)
    output: str = Field(default="", description="Final text output from the agent")
    structured_output: dict[str, Any] | None = Field(
        default=None,
        description="Structured data if the agent was configured with response_format",
    )
    error: str | None = Field(default=None, description="Error message if the run failed")
    token_usage: dict[str, int] = Field(
        default_factory=dict,
        description="Token usage breakdown: {'input': N, 'output': N, 'total': N}",
    )
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
