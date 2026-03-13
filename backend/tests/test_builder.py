"""Tests for the Builder Agent and builder API endpoints.

The builder's LLM calls are mocked so tests don't require API keys.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Stub third-party modules not available in the build environment
# ---------------------------------------------------------------------------
_STUBS = [
    "deepagents",
    "langchain",
    "langchain.agents",
    "langchain.agents.structured_output",
    "langchain_core",
    "langchain_core.messages",
    "langgraph",
    "langgraph.graph",
    "langgraph.graph.state",
    "phoenix",
    "phoenix.otel",
    "openinference",
    "openinference.instrumentation",
    "openinference.instrumentation.langchain",
    "sse_starlette",
    "sse_starlette.sse",
]

for _mod_name in _STUBS:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

_sse_mod = sys.modules["sse_starlette.sse"]
_sse_mod.EventSourceResponse = MagicMock()  # type: ignore[union-attr]

from zerebro.models.agent import AgentConfig  # noqa: E402
from zerebro.models.conversation import (  # noqa: E402
    BuilderSession,
    MessageRole,
    SessionStatus,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestBuilderSession:
    def test_new_session_defaults(self) -> None:
        session = BuilderSession()
        assert session.status == SessionStatus.ACTIVE
        assert session.messages == []
        assert session.proposed_config is None
        assert session.confirmed_agent_id is None

    def test_add_message(self) -> None:
        session = BuilderSession()
        msg = session.add_message(MessageRole.USER, "I want an agent that summarizes PDFs")
        assert msg.role == MessageRole.USER
        assert msg.content == "I want an agent that summarizes PDFs"
        assert len(session.messages) == 1

    def test_to_history_dicts(self) -> None:
        session = BuilderSession()
        session.add_message(MessageRole.USER, "hello")
        session.add_message(MessageRole.ASSISTANT, "hi there")
        history = session.to_history_dicts()
        assert history == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def test_session_roundtrip_json(self) -> None:
        session = BuilderSession()
        session.add_message(MessageRole.USER, "test")
        session.proposed_config = AgentConfig(
            name="Test Agent",
            system_prompt="You are a test agent",
        )
        session.status = SessionStatus.PROPOSED

        data = session.model_dump(mode="json")
        restored = BuilderSession.model_validate(data)
        assert restored.status == SessionStatus.PROPOSED
        assert restored.proposed_config is not None
        assert restored.proposed_config.name == "Test Agent"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():  # type: ignore[no-untyped-def]
    """Async HTTP client with builder LLM mocked."""
    with patch("zerebro.core.tracing.init_tracing"):
        from zerebro.api.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestBuilderChat:
    @pytest.mark.asyncio
    async def test_new_session_created(self, client: AsyncClient) -> None:
        """Sending a chat without session_id creates a new session."""
        mock_config = AgentConfig(
            name="PDF Summarizer",
            system_prompt="You summarize PDF documents concisely.",
        )
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Here's your agent config for a PDF summarizer.", mock_config),
        ):
            resp = await client.post(
                "/builder/chat",
                json={"message": "I want an agent that summarizes PDFs"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert "PDF" in data["response"]
        assert data["status"] == "proposed"
        assert data["proposed_config"] is not None
        assert data["proposed_config"]["name"] == "PDF Summarizer"

    @pytest.mark.asyncio
    async def test_continue_existing_session(self, client: AsyncClient) -> None:
        """Can continue chatting in an existing session."""
        # First message -- builder asks a question
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("What format are the PDFs in?", None),
        ):
            resp1 = await client.post(
                "/builder/chat",
                json={"message": "I want a PDF agent"},
            )
        session_id = resp1.json()["session_id"]
        assert resp1.json()["status"] == "active"

        # Second message -- builder produces config
        mock_config = AgentConfig(
            name="PDF Agent",
            system_prompt="You process PDF documents.",
        )
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Got it, here's your agent.", mock_config),
        ):
            resp2 = await client.post(
                "/builder/chat",
                json={"session_id": session_id, "message": "Standard text PDFs"},
            )
        assert resp2.json()["status"] == "proposed"
        assert resp2.json()["proposed_config"]["name"] == "PDF Agent"

    @pytest.mark.asyncio
    async def test_chat_nonexistent_session(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/builder/chat",
            json={"session_id": "nonexistent", "message": "hello"},
        )
        assert resp.status_code == 404


class TestBuilderConfirm:
    @pytest.mark.asyncio
    async def test_confirm_registers_agent(self, client: AsyncClient) -> None:
        """Confirming a proposed session registers the agent."""
        mock_config = AgentConfig(
            id="test-agent-123",
            name="Confirmed Agent",
            system_prompt="You are confirmed.",
        )
        # Create session with proposed config
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Here's your agent.", mock_config),
        ):
            chat_resp = await client.post(
                "/builder/chat",
                json={"message": "Make me an agent"},
            )
        session_id = chat_resp.json()["session_id"]

        # Confirm
        confirm_resp = await client.post(f"/builder/sessions/{session_id}/confirm")
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["name"] == "Confirmed Agent"

        # Agent should now be in the agents list
        agents_resp = await client.get("/agents")
        ids = [a["id"] for a in agents_resp.json()]
        assert "test-agent-123" in ids

    @pytest.mark.asyncio
    async def test_confirm_active_session_fails(self, client: AsyncClient) -> None:
        """Cannot confirm a session that hasn't proposed a config yet."""
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("What do you need?", None),
        ):
            chat_resp = await client.post(
                "/builder/chat",
                json={"message": "hello"},
            )
        session_id = chat_resp.json()["session_id"]

        confirm_resp = await client.post(f"/builder/sessions/{session_id}/confirm")
        assert confirm_resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_session(self, client: AsyncClient) -> None:
        resp = await client.post("/builder/sessions/nonexistent/confirm")
        assert resp.status_code == 404


class TestBuilderSessions:
    @pytest.mark.asyncio
    async def test_list_sessions(self, client: AsyncClient) -> None:
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Hello!", None),
        ):
            await client.post("/builder/chat", json={"message": "hi"})

        resp = await client.get("/builder/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_get_session(self, client: AsyncClient) -> None:
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Hello!", None),
        ):
            chat_resp = await client.post("/builder/chat", json={"message": "hi"})
        session_id = chat_resp.json()["session_id"]

        resp = await client.get(f"/builder/sessions/{session_id}")
        assert resp.status_code == 200
        assert len(resp.json()["messages"]) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_cancel_session(self, client: AsyncClient) -> None:
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("Hello!", None),
        ):
            chat_resp = await client.post("/builder/chat", json={"message": "hi"})
        session_id = chat_resp.json()["session_id"]

        cancel_resp = await client.post(f"/builder/sessions/{session_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Cannot chat in cancelled session
        with patch(
            "zerebro.api.builder_routes.run_builder_turn",
            new_callable=AsyncMock,
            return_value=("nope", None),
        ):
            chat_resp2 = await client.post(
                "/builder/chat",
                json={"session_id": session_id, "message": "hello again"},
            )
        assert chat_resp2.status_code == 400
