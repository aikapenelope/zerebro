"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the Zerebro backend."""

    # --- Database ---
    database_url: str = (
        "postgresql+asyncpg://zerebro:zerebro_dev@localhost:5432/zerebro"
    )

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM Providers ---
    openai_api_key: str = ""
    groq_api_key: str = ""

    # --- Model Defaults ---
    builder_model: str = "openai:gpt-4o"
    worker_model: str = "groq:qwen/qwen3-32b"
    worker_fallback_model: str = "groq:llama-3.3-70b-versatile"

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
