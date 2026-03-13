"""Agent runner -- builds and executes deepagents from AgentConfig.

This module is the bridge between the Zerebro data model (``AgentConfig``)
and the ``deepagents`` SDK.  It resolves the correct LLM based on the
agent's ``model_role`` / ``model_override``, assembles sub-agents, invokes
the compiled LangGraph graph, and returns a ``RunResult``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from deepagents import SubAgent, create_deep_agent
from langchain_core.messages import AIMessage, HumanMessage

from zerebro.config import settings
from zerebro.models.agent import (
    AgentConfig,
    ModelRole,
    RunResult,
    RunStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def _resolve_model_string(config: AgentConfig) -> str:
    """Return the ``provider:model`` string for a given agent config.

    Priority:
    1. ``model_override`` (explicit model identifier)
    2. ``model_role`` mapping to ``settings.builder_model`` / ``settings.worker_model``
    """
    if config.model_override:
        return config.model_override
    if config.model_role == ModelRole.BUILDER:
        return settings.builder_model
    return settings.worker_model


# ---------------------------------------------------------------------------
# Sub-agent assembly
# ---------------------------------------------------------------------------


def _build_subagents(config: AgentConfig) -> list[SubAgent]:
    """Convert ``SubAgentConfig`` list into deepagents ``SubAgent`` dicts."""
    subagents: list[SubAgent] = []
    for sa in config.subagents:
        spec: SubAgent = {  # type: ignore[typeddict-unknown-key]
            "name": sa.name,
            "description": sa.description,
            "system_prompt": sa.system_prompt,
            "tools": [],  # MCP tools resolved in later sprints
        }
        if sa.model_override:
            spec["model"] = sa.model_override  # type: ignore[typeddict-unknown-key]
        subagents.append(spec)
    return subagents


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_agent(
    config: AgentConfig,
    message: str,
    context: dict[str, Any] | None = None,
) -> RunResult:
    """Execute an agent synchronously (non-streaming) and return the result.

    Args:
        config: The agent configuration produced by the Builder Agent.
        message: The user message / task to execute.
        context: Optional additional context dict.

    Returns:
        A ``RunResult`` with the agent's output, token usage, and timing.
    """
    run_id = str(uuid.uuid4())
    model_str = _resolve_model_string(config)
    logger.info("Running agent %s (%s) with model %s", config.name, config.id, model_str)

    start = time.monotonic()
    try:
        graph = create_deep_agent(
            model=model_str,
            system_prompt=config.system_prompt,
            subagents=_build_subagents(config) or None,
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": run_id}},
        )

        # Extract the final AI message from the result
        messages = result.get("messages", [])
        output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and isinstance(msg.content, str):
                output = msg.content
                break

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Extract token usage from the last AI message if available
        token_usage: dict[str, int] = {}
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                token_usage = {
                    "input": msg.usage_metadata.get("input_tokens", 0),
                    "output": msg.usage_metadata.get("output_tokens", 0),
                    "total": msg.usage_metadata.get("total_tokens", 0),
                }
                break

        return RunResult(
            run_id=run_id,
            agent_id=config.id,
            status=RunStatus.COMPLETED,
            output=output,
            token_usage=token_usage,
            duration_ms=elapsed_ms,
        )

    except Exception:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Agent run %s failed", run_id)
        return RunResult(
            run_id=run_id,
            agent_id=config.id,
            status=RunStatus.FAILED,
            error=f"Agent execution failed (see logs for run_id={run_id})",
            duration_ms=elapsed_ms,
        )


async def stream_agent(
    config: AgentConfig,
    message: str,
    context: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Execute an agent with streaming, yielding events as they arrive.

    Yields dicts suitable for Server-Sent Events (SSE):
    - ``{"event": "token", "data": "..."}`` for incremental text
    - ``{"event": "tool_call", "data": {...}}`` for tool invocations
    - ``{"event": "done", "data": {...}}`` with the final RunResult
    - ``{"event": "error", "data": "..."}`` on failure

    Args:
        config: The agent configuration.
        message: The user message / task to execute.
        context: Optional additional context dict.
    """
    run_id = str(uuid.uuid4())
    model_str = _resolve_model_string(config)
    logger.info(
        "Streaming agent %s (%s) with model %s",
        config.name,
        config.id,
        model_str,
    )

    start = time.monotonic()
    try:
        graph = create_deep_agent(
            model=model_str,
            system_prompt=config.system_prompt,
            subagents=_build_subagents(config) or None,
        )

        final_output = ""
        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": run_id}},
            version="v2",
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                    final_output += chunk.content
                    yield {"event": "token", "data": chunk.content}

            elif kind == "on_tool_start":
                yield {
                    "event": "tool_call",
                    "data": {
                        "tool": event.get("name", ""),
                        "input": event.get("data", {}).get("input", {}),
                    },
                }

        elapsed_ms = int((time.monotonic() - start) * 1000)
        result = RunResult(
            run_id=run_id,
            agent_id=config.id,
            status=RunStatus.COMPLETED,
            output=final_output,
            duration_ms=elapsed_ms,
        )
        yield {"event": "done", "data": result.model_dump(mode="json")}

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Streaming agent run %s failed", run_id)
        yield {"event": "error", "data": str(exc)}
        result = RunResult(
            run_id=run_id,
            agent_id=config.id,
            status=RunStatus.FAILED,
            error=str(exc),
            duration_ms=elapsed_ms,
        )
        yield {"event": "done", "data": result.model_dump(mode="json")}
