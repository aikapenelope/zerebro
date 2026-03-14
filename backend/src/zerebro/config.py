"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the Zerebro backend."""

    # --- Database ---
    database_url: str = (
        "postgresql+asyncpg://zerebro:zerebro_dev@localhost:5432/zerebro"
    )

    # Sync URL for Alembic and LangGraph checkpointer (psycopg3).
    # Must use the +psycopg driver prefix so SQLAlchemy uses psycopg3
    # instead of the absent psycopg2.
    database_url_sync: str = (
        "postgresql+psycopg://zerebro:zerebro_dev@localhost:5432/zerebro"
    )

    # --- LLM Providers ---
    openai_api_key: str = ""
    groq_api_key: str = ""

    # --- Model Defaults ---
    # Builder: high-reasoning model for creating agents via structured output.
    # gpt-4.1 has superior instruction following and structured output vs gpt-4o.
    builder_model: str = "openai:gpt-4.1"

    # Worker: primary model for executing agent tasks.
    # llama-3.3-70b-versatile is a Production model on Groq (stable, battle-tested).
    worker_model: str = "groq:llama-3.3-70b-versatile"

    # Worker fallback: used when the primary worker model fails.
    # qwen3-32b is fast (400 tps) but Preview on Groq (may be deprecated).
    worker_fallback_model: str = "groq:qwen/qwen3-32b"

    # --- MCP Servers ---
    # JSON array of MCPServerConfig objects. See api/app.py for format.
    mcp_servers_json: str = ""

    # --- Phoenix Observability ---
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"

    # --- Server ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
