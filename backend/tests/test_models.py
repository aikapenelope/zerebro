"""Tests for Pydantic models -- validates serialization, defaults, and enums."""

from __future__ import annotations

from zerebro.models.agent import (
    AgentConfig,
    ModelRole,
    RunRequest,
    RunResult,
    RunStatus,
    SubAgentConfig,
    TriggerConfig,
    TriggerType,
)


class TestAgentConfig:
    """AgentConfig model tests."""

    def test_minimal_creation(self) -> None:
        """An agent can be created with just name and system_prompt."""
        agent = AgentConfig(name="test", system_prompt="Do stuff")
        assert agent.name == "test"
        assert agent.system_prompt == "Do stuff"
        assert agent.model_role == ModelRole.WORKER
        assert agent.model_override is None
        assert agent.tools == []
        assert agent.subagents == []
        assert agent.triggers == []
        assert agent.id  # auto-generated UUID

    def test_full_creation(self) -> None:
        """An agent with all fields populated round-trips through JSON."""
        agent = AgentConfig(
            name="full-agent",
            description="A fully configured agent",
            system_prompt="You are a test agent",
            model_role=ModelRole.BUILDER,
            model_override="openai:gpt-4o",
            tools=["mcp-github", "mcp-slack"],
            subagents=[
                SubAgentConfig(
                    name="researcher",
                    description="Researches topics",
                    system_prompt="Research the given topic",
                    tools=["mcp-web-search"],
                )
            ],
            triggers=[
                TriggerConfig(type=TriggerType.CRON, cron_expression="0 9 * * 1-5")
            ],
        )
        data = agent.model_dump(mode="json")
        restored = AgentConfig.model_validate(data)
        assert restored.name == "full-agent"
        assert restored.model_role == ModelRole.BUILDER
        assert len(restored.subagents) == 1
        assert restored.subagents[0].name == "researcher"
        assert len(restored.triggers) == 1
        assert restored.triggers[0].cron_expression == "0 9 * * 1-5"

    def test_json_schema_generation(self) -> None:
        """AgentConfig produces a valid JSON schema (used for structured output)."""
        schema = AgentConfig.model_json_schema()
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "system_prompt" in schema["properties"]


class TestRunModels:
    """RunRequest and RunResult model tests."""

    def test_run_request_minimal(self) -> None:
        req = RunRequest(agent_id="abc", message="Hello")
        assert req.agent_id == "abc"
        assert req.context == {}

    def test_run_request_with_context(self) -> None:
        req = RunRequest(
            agent_id="abc",
            message="Process this",
            context={"file": "/tmp/data.csv"},
        )
        assert req.context["file"] == "/tmp/data.csv"

    def test_run_result_defaults(self) -> None:
        result = RunResult(agent_id="abc")
        assert result.status == RunStatus.COMPLETED
        assert result.output == ""
        assert result.error is None
        assert result.run_id  # auto-generated

    def test_run_result_failed(self) -> None:
        result = RunResult(
            agent_id="abc",
            status=RunStatus.FAILED,
            error="Something went wrong",
            duration_ms=1500,
        )
        assert result.status == RunStatus.FAILED
        assert result.error == "Something went wrong"
        assert result.duration_ms == 1500


class TestEnums:
    """Enum serialization tests."""

    def test_model_role_values(self) -> None:
        assert ModelRole.BUILDER.value == "builder"
        assert ModelRole.WORKER.value == "worker"

    def test_trigger_type_values(self) -> None:
        assert TriggerType.MANUAL.value == "manual"
        assert TriggerType.CRON.value == "cron"
        assert TriggerType.WEBHOOK.value == "webhook"

    def test_run_status_values(self) -> None:
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"
