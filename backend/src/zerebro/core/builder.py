"""Builder Agent -- creates other agents via conversational interface.

The Builder Agent is the core UX of Zerebro (twin.so style). A user describes
what they want in natural language, the builder asks clarifying questions, and
ultimately produces a complete ``AgentConfig`` as structured output.

**Two-node pattern** (provider-agnostic structured output):

Many LLM providers (Groq, Gemini, etc.) cannot combine tool calling with
structured output in a single request -- only OpenAI handles both natively.
To work with *any* provider we split the work into two steps:

1. **Conversation node** -- a ``create_deep_agent`` graph that chats with the
   user, asks clarifying questions, and decides when the config is ready.
   When ready it emits a special marker ``CONFIG_READY`` in its text response.
2. **Formatter node** -- a lightweight LLM call that takes the conversation
   summary and produces a validated ``AgentConfig`` Pydantic object via
   ``with_structured_output()``.  This call has *no tools*, so structured
   output works on every provider.

Flow:
1. User sends a message describing what they want
2. Builder either asks clarifying questions OR signals CONFIG_READY
3. If CONFIG_READY, the formatter extracts the AgentConfig
4. User confirms the config -> agent is registered and ready to run
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from zerebro.config import settings
from zerebro.core.memory import get_checkpointer, get_store
from zerebro.models.agent import AgentConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Marker the conversation node emits when the config is ready
# ---------------------------------------------------------------------------

CONFIG_READY_MARKER = "CONFIG_READY"

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
- The user has confirmed they're happy with the plan, OR the request is \
simple enough that you can produce the config immediately

When you are ready to produce the configuration, you MUST:
1. Write a brief summary of the agent you're about to create.
2. Then output a JSON block with the agent details using EXACTLY this format:

CONFIG_READY
```json
{
  "name": "Agent Name",
  "description": "What this agent does",
  "system_prompt": "Detailed instructions for the agent...",
  "model_role": "worker",
  "tools": [],
  "subagents": [],
  "triggers": []
}
```

IMPORTANT: The CONFIG_READY marker and JSON block MUST appear together. \
Do NOT output CONFIG_READY without the JSON block.

## Available model tiers

- `worker` (default): Fast and cheap. Good for most tasks. Uses Groq.
- `builder`: High-reasoning model. Use for complex multi-step tasks that \
require deep thinking.
"""

# ---------------------------------------------------------------------------
# Formatter prompt -- used by the second node to produce AgentConfig
# ---------------------------------------------------------------------------

FORMATTER_SYSTEM_PROMPT = """\
You are a JSON formatter. You receive a conversation summary and agent \
specification, and you produce a valid AgentConfig JSON object.

Extract the agent configuration from the provided text and return it as \
a structured AgentConfig. Use exactly the field names and types specified. \
If a field is not mentioned, use sensible defaults.

Fields:
- name (str, required): Human-readable name
- description (str): What the agent does
- system_prompt (str, required): Detailed instructions for the agent
- model_role (str): "worker" (default) or "builder"
- tools (list[str]): MCP server identifiers, default []
- subagents (list[object]): Sub-agent configs, default []
- triggers (list[object]): Trigger configs, default []
"""


def create_builder_graph() -> CompiledStateGraph:
    """Create the Builder Agent graph (conversation node only).

    The builder uses the configured builder model and does NOT use
    ``response_format`` -- structured output is handled separately by
    the formatter in ``run_builder_turn()``.

    Returns:
        A compiled LangGraph graph ready for invocation.
    """
    return create_deep_agent(
        model=settings.builder_model,
        system_prompt=BUILDER_SYSTEM_PROMPT,
        name="builder",
        checkpointer=get_checkpointer(),
        store=get_store(),
    )


def _extract_config_json(text: str) -> str | None:
    """Extract JSON from a CONFIG_READY response.

    Looks for the CONFIG_READY marker followed by a JSON code block.
    Returns the raw JSON string, or None if not found.
    """
    # Pattern: CONFIG_READY followed by optional whitespace, then ```json ... ```
    pattern = re.compile(
        r"CONFIG_READY\s*```json\s*(\{.*?\})\s*```",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        return match.group(1)

    # Fallback: CONFIG_READY followed by a bare JSON object
    pattern_bare = re.compile(
        r"CONFIG_READY\s*(\{.*\})",
        re.DOTALL,
    )
    match_bare = pattern_bare.search(text)
    if match_bare:
        return match_bare.group(1)

    return None


def _parse_agent_config(json_str: str) -> AgentConfig | None:
    """Try to parse a JSON string into an AgentConfig.

    Returns None if parsing fails.
    """
    try:
        data = json.loads(json_str)
        return AgentConfig.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse AgentConfig from JSON: %s", exc)
        return None


async def _format_with_llm(text: str) -> AgentConfig | None:
    """Use a separate LLM call to extract AgentConfig via structured output.

    This is the formatter node -- it uses ``with_structured_output()``
    which works on all providers because there are no tools involved.

    Falls back to manual JSON parsing if structured output fails.
    """
    try:
        model = init_chat_model(settings.builder_model)
        formatter = model.with_structured_output(AgentConfig)
        result = await formatter.ainvoke(
            [
                {"role": "system", "content": FORMATTER_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        if isinstance(result, AgentConfig):
            return result
    except Exception as exc:
        logger.warning("Formatter LLM call failed: %s", exc)

    return None


def _extract_text_response(result: dict[str, Any]) -> str:
    """Extract the text response from the last AI message in the result."""
    result_messages: list[Any] = result.get("messages", [])

    for msg in reversed(result_messages):
        if not isinstance(msg, AIMessage):
            continue
        if isinstance(msg.content, str) and msg.content:
            return msg.content
        if isinstance(msg.content, list):
            # Multi-part content (e.g., text + tool_use blocks)
            text_parts = [
                part.get("text", "")
                for part in msg.content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            if text_parts:
                return "\n".join(text_parts)

    return ""


async def run_builder_turn(
    messages: list[BaseMessage],
) -> tuple[str, AgentConfig | None]:
    """Execute one turn of the builder conversation.

    Takes the full message history and returns the builder's text response
    plus an optional ``AgentConfig`` if the builder decided to produce one.

    Two-node pattern:
    1. Invoke the conversation graph (``create_deep_agent`` without
       ``response_format``).
    2. If the response contains ``CONFIG_READY``, extract the JSON and
       parse it into an ``AgentConfig``.  If direct parsing fails, fall
       back to a formatter LLM call using ``with_structured_output()``.

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

    text_response = _extract_text_response(result)

    # --- Two-node structured output extraction ---
    agent_config: AgentConfig | None = None

    if CONFIG_READY_MARKER in text_response:
        # Step 1: Try direct JSON extraction from the response text
        json_str = _extract_config_json(text_response)
        if json_str:
            agent_config = _parse_agent_config(json_str)

        # Step 2: If direct parsing failed, use the formatter LLM
        if agent_config is None:
            logger.info("Direct JSON parse failed, falling back to formatter LLM")
            agent_config = await _format_with_llm(text_response)

        # Clean up the CONFIG_READY marker and JSON block from the user-facing
        # response so the frontend gets clean text.
        if agent_config is not None:
            # Remove everything from CONFIG_READY onwards
            clean = text_response.split(CONFIG_READY_MARKER)[0].strip()
            if clean:
                text_response = clean
            else:
                # The entire response was the config block
                text_response = (
                    f"Here's your agent configuration for **{agent_config.name}**. "
                    "Please confirm to register it."
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
