"""Models for the Builder Agent conversation flow.

These models track the multi-turn conversation between a user and the
Builder Agent. A ``BuilderSession`` holds the full message history and
the resulting ``AgentConfig`` once the builder produces one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from zerebro.models.agent import AgentConfig


class MessageRole(str, Enum):
    """Who sent the message."""

    USER = "user"
    ASSISTANT = "assistant"


class SessionStatus(str, Enum):
    """Lifecycle of a builder session."""

    ACTIVE = "active"  # Conversation in progress
    PROPOSED = "proposed"  # Builder produced an AgentConfig, awaiting confirmation
    CONFIRMED = "confirmed"  # User confirmed, agent registered
    CANCELLED = "cancelled"  # User abandoned the session


class ConversationMessage(BaseModel):
    """A single message in the builder conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BuilderSession(BaseModel):
    """A builder conversation session.

    Tracks the full history of messages between the user and the Builder
    Agent, plus the resulting AgentConfig when the builder produces one.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = Field(default=SessionStatus.ACTIVE)
    messages: list[ConversationMessage] = Field(default_factory=list)
    proposed_config: AgentConfig | None = Field(
        default=None,
        description="The AgentConfig produced by the builder, pending confirmation",
    )
    confirmed_agent_id: str | None = Field(
        default=None,
        description="ID of the registered agent after confirmation",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_message(self, role: MessageRole, content: str) -> ConversationMessage:
        """Append a message to the conversation history.

        Args:
            role: Who sent the message.
            content: The message text.

        Returns:
            The created message.
        """
        msg = ConversationMessage(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now(UTC)
        return msg

    def to_history_dicts(self) -> list[dict[str, str]]:
        """Convert messages to the {role, content} format expected by the builder.

        Returns:
            List of dicts with "role" and "content" keys.
        """
        return [{"role": m.role.value, "content": m.content} for m in self.messages]


class ChatRequest(BaseModel):
    """Request to send a message to the Builder Agent."""

    session_id: str | None = Field(
        default=None,
        description="Existing session ID. Omit to start a new session.",
    )
    message: str = Field(description="User message to the builder")


class ChatResponse(BaseModel):
    """Response from the Builder Agent."""

    session_id: str = Field(description="The session ID (new or existing)")
    response: str = Field(description="Builder's text response")
    status: SessionStatus = Field(description="Current session status")
    proposed_config: AgentConfig | None = Field(
        default=None,
        description="The proposed AgentConfig if the builder produced one",
    )
