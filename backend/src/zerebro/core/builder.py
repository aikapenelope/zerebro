"""Builder Agent -- creates other agents via conversational interface.

The Builder Agent is the core UX of Zerebro (twin.so style). A user describes
what they want in natural language, the builder asks clarifying questions, and
ultimately produces a complete ``AgentConfig`` as structured output.

Flow:
1. User sends a message describing what they want
2. Builder either asks clarifying questions OR produces an AgentConfig
3. User confirms the config -> agent is registered and ready to run

The builder uses ChatAnthropic directly (not deepagents) because it only needs
to converse and produce structured output -- no file I/O, code execution, or
tool calls.  This keeps token usage minimal (~1 LLM call per turn instead of
the 10-15 calls that deepagents' autonomous loop would make).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from zerebro.config import settings
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

When ready, include a JSON block in your response fenced with \
```agent_config ... ``` containing the AgentConfig fields. Example:

```agent_config
{
  "name": "My Agent",
  "description": "Does X",
  "system_prompt": "You are an agent that ...",
  "model_role": "worker",
  "tools": [],
  "subagents": [],
  "triggers": []
}
```

Always include a conversational message alongside the config block.

## Available model tiers

- `worker` (default): Fast and cheap. Good for most tasks. Uses Groq.
- `builder`: High-reasoning model. Use for complex multi-step tasks that \
require deep thinking.
"""


def _get_model_name() -> str:
    """Extract the Anthropic model name from the builder_model setting.

    The setting is formatted as ``anthropic:<model-name>``.  We strip the
    provider prefix so it can be passed directly to ``ChatAnthropic``.
    """
    model = settings.builder_model
    if model.startswith("anthropic:"):
        return model[len("anthropic:"):]
    return model


def _create_chat_model() -> ChatAnthropic:
    """Create a ChatAnthropic instance for the builder."""
    # ChatAnthropic accepts **kwargs; pyright can't see the params.
    return ChatAnthropic(  # pyright: ignore[reportCallIssue]
        model=_get_model_name(),  # pyright: ignore[reportCallIssue]
        api_key=settings.anthropic_api_key,  # pyright: ignore[reportCallIssue]
        max_tokens=4096,  # pyright: ignore[reportCallIssue]
    )


async def run_builder_turn(
    messages: list[BaseMessage],
    *,
    session_id: str = "builder",
) -> tuple[str, AgentConfig | None]:
    """Execute one turn of the builder conversation.

    Uses a plain ChatAnthropic call (no tool calling, no structured output
    forcing).  The builder is instructed to include a fenced
    ``agent_config`` JSON block when it's ready to propose a config.
    We parse that block out of the response text.

    This approach avoids the problem where ``with_structured_output`` forces
    Claude into tool-calling mode, which swallows the conversational text
    when Claude just wants to ask clarifying questions.

    Args:
        messages: Full conversation history as LangChain messages.
        session_id: Unique session identifier (reserved for future use).

    Returns:
        A tuple of (text_response, agent_config_or_none).
    """
    llm = _create_chat_model()

    # Build the full message list with system prompt.
    full_messages: list[BaseMessage] = [
        SystemMessage(content=BUILDER_SYSTEM_PROMPT),
        *messages,
    ]

    try:
        ai_msg: AIMessage = await llm.ainvoke(full_messages)
    except Exception as exc:
        print(f"[builder] LLM call failed: {type(exc).__name__}: {exc}", flush=True)
        raise

    text = _extract_text(ai_msg)
    print(f"[builder] response length={len(text)}", flush=True)

    # Try to extract an AgentConfig from a fenced ```agent_config block.
    agent_config = _parse_agent_config(text)

    # Strip the fenced block from the user-visible response if present.
    if agent_config is not None:
        text = _strip_config_block(text)

    return text, agent_config


def _extract_text(msg: AIMessage) -> str:
    """Extract plain text from an AIMessage.

    Claude may return content as a string or as a list of content blocks
    (text + tool_use).  This handles both formats.
    """
    if isinstance(msg.content, str):
        return msg.content

    if isinstance(msg.content, list):
        text_parts: list[str] = []
        for part in msg.content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts)

    return ""


def _parse_agent_config(text: str) -> AgentConfig | None:
    """Try to extract an AgentConfig from a fenced code block in the text.

    Looks for ```agent_config ... ``` or ```json ... ``` blocks that
    contain valid AgentConfig JSON.
    """
    import re

    # Match ```agent_config { ... } ``` blocks
    pattern = r"```agent_config\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        # Also try ```json blocks as a fallback
        pattern = r"```json\s*\n?(.*?)\n?```"
        match = re.search(pattern, text, re.DOTALL)

    if not match:
        return None

    json_str = match.group(1).strip()
    try:
        data: dict[str, Any] = json.loads(json_str)
        return AgentConfig(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[builder] Failed to parse agent_config: {exc}", flush=True)
        return None


def _strip_config_block(text: str) -> str:
    """Remove the fenced agent_config or json block from the response text."""
    import re

    text = re.sub(r"```agent_config\s*\n?.*?\n?```", "", text, flags=re.DOTALL)
    text = re.sub(r"```json\s*\n?.*?\n?```", "", text, flags=re.DOTALL)
    return text.strip()


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
