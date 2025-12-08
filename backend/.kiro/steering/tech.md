# Tech Stack

## Runtime & Package Management

- **Python**: 3.11+
- **Package Manager**: `uv` (fast Python package manager)
- **Lock File**: `uv.lock`

## Web Framework

- **FastAPI**: Main API server with async support
- **Uvicorn/Gunicorn**: ASGI server (Gunicorn with UvicornWorker in production)

## Database & Storage

- **Supabase**: PostgreSQL database with Row Level Security, Auth, and Realtime
- **Redis**: Caching, session management, and job queue backend

## Background Processing

- **Dramatiq**: Task queue for async agent execution
- **Redis**: Message broker for Dramatiq

## LLM Integration

- **LiteLLM**: Unified interface for multiple LLM providers
- **Supported Providers**: OpenAI, Anthropic, AWS Bedrock, Groq, OpenRouter, Gemini, xAI
- **Prompt Caching**: Anthropic-style caching optimization

## External Services

- **Daytona**: Cloud sandbox environments for code execution
- **Stripe**: Payment processing and subscriptions
- **Langfuse**: LLM observability and analytics
- **Sentry**: Error tracking
- **Composio**: External API integrations
- **MCP**: Model Context Protocol for tool integration

## Key Libraries

- `pydantic`: Data validation
- `structlog`: Structured logging
- `cryptography`: Credential encryption
- `boto3`: AWS SDK (for Bedrock)
- `mcp`: Model Context Protocol client

## Common Commands

```bash
# Install dependencies
uv sync

# Start Redis (required)
docker compose up redis

# Start background worker (always specify --processes)
uv run dramatiq --processes 4 --threads 4 run_agent_background

# Start API server
uv run api.py

# Run tests with coverage
uv run pytest -v --cov=core --cov-report=term-missing

# Run specific test markers
uv run pytest -m unit      # Fast, no external deps
uv run pytest -m integration  # Requires DB/services
uv run pytest -m api       # API endpoint tests

# Add dependency
uv add package-name
uv add --dev package-name

# Docker full stack
docker compose up
```

## Environment Configuration

- Config via `.env` file (see `.env.example`)
- Centralized in `core/utils/config.py`
- Modes: `local`, `staging`, `production`
- Feature flags for optional components (AgentCore, billing)
