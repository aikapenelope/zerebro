"""Builder Agent -- creates other agents via conversational interface.

The Builder Agent is the core UX of Zerebro (twin.so style). A user describes
what they want in natural language, the builder asks clarifying questions, and
ultimately produces a complete ``AgentConfig`` as structured output.

Flow:
1. User sends a message describing what they want
2. Builder either asks clarifying questions OR produces an AgentConfig
3. User confirms the config -> agent is registered and ready to run

The builder uses a high-reasoning model (Anthropic Claude) with ``response_format``
set to produce structured output when it decides the config is ready.
"""

from __future__ import annotations

import logging
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.structured_output import AutoStrategy
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from zerebro.config import settings
from zerebro.core.memory import get_checkpointer, get_store
from zerebro.models.agent import AgentConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Builder system prompt
# ---------------------------------------------------------------------------

BUILDER_SYSTEM_PROMPT = """\
You are the Zerebro Builder Agent. Your job is to help users create AI agents \
through conversation. You translate natural language descriptions into complete \
agent configurations.

## How you work

1. **Listen** -- The user describes what they want their agent to do.
2. **Clarify** -- Ask focused questions to fill in gaps. Don't ask more than \
2-3 questions at a time. Common things to clarify:
   - What specific tasks should the agent perform?
   - Does it need access to external tools or APIs?
   - Should it have sub-agents for delegation?
   - What model tier is appropriate (fast/cheap worker vs high-reasoning builder)?
   - Should it run on a schedule or via webhook?
3. **Build** -- When you have enough information, produce the agent configuration.

## Guidelines

- Be concise and direct. No fluff.
- Default to `worker` model role (fast, cheap via Groq) unless the task \
requires complex reasoning.
- Write detailed, specific system prompts for the agent. The system prompt \
is the most important part -- it defines the agent's behavior.
- If the user's request is simple enough, skip clarifying questions and \
produce the config immediately.
- Tool names should be descriptive MCP server identifiers \
(e.g., "mcp-github", "mcp-slack", "mcp-web-search").
- Sub-agents are useful when the main agent needs to delegate specialized \
tasks (e.g., a "researcher" sub-agent for gathering info).

## When to produce the configuration

Produce the agent configuration when:
- You have a clear understanding of what the agent should do
- You've written a good system prompt for it
- The user has confirmed they're happy with the plan

When you produce the configuration, output it as a structured AgentConfig. \
Do NOT output JSON in your text response -- use the structured output format.

## Available model tiers

- `worker` (default): Fast and cheap. Good for most tasks. Uses Groq.
- `builder`: High-reasoning model. Use for complex multi-step tasks that \
require deep thinking.
"""


def create_builder_graph() -> CompiledStateGraph:
    """Create the Builder Agent graph with structured output capability.

    The builder uses the configured builder model (Anthropic Claude) and
    can produce an ``AgentConfig`` as structured output via AutoStrategy.

    Returns:
        A compiled LangGraph graph ready for invocation.
    """
    return create_deep_agent(
        model=settings.builder_model,
        system_prompt=BUILDER_SYSTEM_PROMPT,
        response_format=AutoStrategy(AgentConfig),
        name="builder",
        checkpointer=get_checkpointer(),
        store=get_store(),
    )


async def run_builder_turn(
    messages: list[BaseMessage],
) -> tuple[str, AgentConfig | None]:
    """Execute one turn of the builder conversation.

    Takes the full message history and returns the builder's text response
    plus an optional ``AgentConfig`` if the builder decided to produce one.

    Args:
        messages: Full conversation history as LangChain messages.

    Returns:
        A tuple of (text_response, agent_config_or_none).
    """
    graph = create_builder_graph()

    result = await graph.ainvoke(
        {"messages": messages},
        config={"configurable": {"thread_id": "builder"}},
    )

    # Extract the response -- walk all AI messages to find text and config.
    # Claude (Anthropic) returns multi-part content: text blocks mixed with
    # tool_use blocks.  deepagents may produce several AI messages in a
    # single turn (tool calls, planning, etc.), so we scan all of them.
    result_messages: list[Any] = result.get("messages", [])
    text_response = ""
    agent_config: AgentConfig | None = None

    for msg in reversed(result_messages):
        if not isinstance(msg, AIMessage):
            continue

        # Check for structured output (AgentConfig)
        if hasattr(msg, "response_metadata"):
            parsed = msg.response_metadata.get("parsed")
            if isinstance(parsed, AgentConfig):
                agent_config = parsed

        # Extract text content from this message
        msg_text = ""
        if isinstance(msg.content, str) and msg.content:
            msg_text = msg.content
        elif isinstance(msg.content, list):
            # Multi-part content (e.g., text + tool_use blocks)
            text_parts = [
                part.get("text", "")
                for part in msg.content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            if text_parts:
                msg_text = "\n".join(text_parts)

        # Use the first (most recent) AI message that has actual text
        if msg_text and not text_response:
            text_response = msg_text

        # If we found both text and config, we're done
        if text_response and agent_config is not None:
            break

    logger.debug(
        "Builder turn result: text_len=%d, has_config=%s, total_msgs=%d",
        len(text_response),
        agent_config is not None,
        len(result_messages),
    )

    return text_response, agent_config


def messages_from_history(
    history: list[dict[str, str]],
) -> list[BaseMessage]:
    """Convert a list of {role, content} dicts to LangChain messages.

    Args:
        history: List of dicts with "role" ("user" or "assistant") and "content".

    Returns:
        List of HumanMessage / AIMessage instances.
    """
    messages: list[BaseMessage] = []
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages
