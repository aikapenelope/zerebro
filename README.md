# Zerebro

Self-hosted agent builder platform. Describe what you want in natural language, and Zerebro creates, deploys, and manages AI agents for you — twin.so style, but on your own hardware.

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────┐
│  Frontend    │────▶│  Backend (FastAPI)                            │
│  Next.js     │     │                                              │
│  :3000       │     │  Builder Agent ──▶ AgentConfig (structured)  │
└─────────────┘     │  Runner ──▶ Worker agents (Groq/OpenAI)      │
                    │  MCP Manager ──▶ External tool servers        │
                    │                                              │
                    │  Checkpointer ──▶ Postgres (conversation)    │
                    │  Store ──▶ Postgres (cross-thread memory)    │
                    └──────────┬───────────────────────────────────┘
                               │
                    ┌──────────▼───────────┐  ┌──────────────────┐
                    │  PostgreSQL 16       │  │  Phoenix          │
                    │  Agent configs       │  │  AI Observability │
                    │  Run history         │  │  :6006            │
                    │  LangGraph state     │  └──────────────────┘
                    └──────────────────────┘
```

**Three-layer design:**

| Layer | What it does | Key tech |
|-------|-------------|----------|
| **Builder Agent** | Conversational UI → structured `AgentConfig` | OpenAI gpt-4.1, structured output via `AutoStrategy` |
| **Worker Agents** | Execute tasks defined by configs | Groq llama-3.3-70b (primary), qwen3-32b (fallback) |
| **MCP Tools** | Connect agents to external APIs | MCP stdio / HTTP / SSE transports |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key (builder agent)
- Groq API key (worker agents)

### 1. Clone and configure

```bash
git clone https://github.com/aikapenelope/zerebro.git
cd zerebro
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start everything

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** on `:5432` — agent configs, run history, LangGraph memory
- **Phoenix** on `:6006` — AI observability dashboard (traces, evals)
- **Backend** on `:8000` — FastAPI + deepagents
- **Frontend** on `:3000` — Next.js UI

### 3. Use it

Open `http://localhost:3000` and describe the agent you want to build.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness / readiness probe |
| `GET` | `/agents` | List all agents |
| `POST` | `/agents` | Create an agent from `AgentConfig` |
| `GET` | `/agents/{id}` | Get agent details |
| `PATCH` | `/agents/{id}` | Update an agent |
| `DELETE` | `/agents/{id}` | Delete an agent |
| `POST` | `/agents/run` | Execute an agent (blocking) |
| `POST` | `/agents/run/stream` | Execute with SSE streaming |
| `GET` | `/agents/{id}/runs` | Run history for an agent |
| `POST` | `/builder/chat` | Conversational agent builder |
| `POST` | `/builder/sessions/{id}/confirm` | Confirm a built agent |
| `GET` | `/mcp/servers` | List configured MCP servers |
| `GET` | `/mcp/servers/{name}/tools` | List tools from an MCP server |

## Model Tiers

| Tier | Model | Provider | Use case |
|------|-------|----------|----------|
| **Builder** | `gpt-4.1` | OpenAI | Agent creation (structured output, instruction following) |
| **Worker** (primary) | `llama-3.3-70b-versatile` | Groq | Task execution — Production model, stable, 280 tps |
| **Worker** (fallback) | `qwen/qwen3-32b` | Groq | Auto-retry on primary failure — Preview model, 400 tps |

Override defaults via environment variables: `BUILDER_MODEL`, `WORKER_MODEL`, `WORKER_FALLBACK_MODEL`.

## Persistent Memory

Agents share persistent memory across conversations via LangGraph's Postgres backends:

- **Checkpointer** (`AsyncPostgresSaver`): persists graph state (message history, tool results) per `thread_id`. Agents resume conversations where they left off.
- **Store** (`AsyncPostgresStore`): cross-thread key-value store for learned facts, user preferences, and shared context between agents.

Both use the same Postgres instance as the application database. No additional infrastructure required.

## MCP Tool Servers

Connect agents to external APIs via the [Model Context Protocol](https://modelcontextprotocol.io/):

```bash
# In .env:
MCP_SERVERS_JSON='[
  {"name": "mcp-github", "transport": "streamable_http",
   "url": "http://localhost:3001/mcp",
   "description": "GitHub MCP server"}
]'
```

Supported transports: `stdio`, `streamable_http`, `sse`.

> **Note:** `stdio` transport requires Node.js in the backend container. The default `python:3.11-slim` image does not include it. Use `streamable_http` or `sse` in Docker, or extend the Dockerfile.

## Development

### Backend (Python)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Type checking + linting
pyright src/
ruff check src/
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

### Database Migrations

```bash
cd backend
source .venv/bin/activate
# Create a new migration
alembic revision --autogenerate -m "description"
# Apply migrations
alembic upgrade head
```

## Environment Variables

See [`.env.example`](.env.example) for all available configuration. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI key for builder agent |
| `GROQ_API_KEY` | Yes | Groq key for worker agents |
| `DATABASE_URL` | No | Async Postgres URL (default: local Docker) |
| `DATABASE_URL_SYNC` | No | Sync Postgres URL for LangGraph memory |
| `BUILDER_MODEL` | No | Override builder model (default: `openai:gpt-4.1`) |
| `WORKER_MODEL` | No | Override worker model (default: `groq:llama-3.3-70b-versatile`) |
| `WORKER_FALLBACK_MODEL` | No | Override fallback model (default: `groq:qwen/qwen3-32b`) |
| `MCP_SERVERS_JSON` | No | JSON array of MCP server configs |
| `LOG_LEVEL` | No | Logging level (default: `info`) |

## Project Structure

```
zerebro/
├── backend/
│   ├── src/zerebro/
│   │   ├── api/          # FastAPI routes (agents, builder, MCP)
│   │   ├── core/         # Builder agent, runner, MCP manager, memory
│   │   ├── db/           # SQLAlchemy models, engine, repositories
│   │   └── models/       # Pydantic schemas (AgentConfig, RunResult, etc.)
│   ├── migrations/       # Alembic database migrations
│   ├── tests/            # pytest test suite (58 tests)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/             # Next.js UI
├── docker-compose.yml
└── .env.example
```

## License

MIT
