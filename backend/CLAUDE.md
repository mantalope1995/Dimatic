# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend Development

**Start the full backend stack:**
```bash
# Start Redis (required for caching and queue)
docker compose up redis

# Start Dramatiq worker for background agent execution
# IMPORTANT: Always specify --processes to control worker count
uv run dramatiq --processes 4 --threads 4 run_agent_background

# Start the main API server
uv run api.py
```

**Running tests:**
```bash
# Run all tests with coverage
uv run pytest -v --cov=core --cov-report=term-missing --cov-report=html

# Run specific test file
uv run pytest core/agentcore/tests/test_config.py -v

# Run tests by marker
uv run pytest -m unit  # Fast tests, no external dependencies
uv run pytest -m integration  # Tests with database/external services
uv run pytest -m api  # API endpoint tests
uv run pytest -m llm  # LLM integration tests (requires API keys)
```

**Single test execution:**
```bash
uv run pytest tests/test_specific_file.py::test_function_name -v -s
```

### Docker Development

**Full stack with Docker:**
```bash
# Build and run all services (API, worker, Redis)
docker compose up

# Run specific service
docker compose up api
docker compose up worker
docker compose up redis
```

### Python Package Management

This project uses `uv` for fast Python package management:

```bash
# Install dependencies
uv sync

# Add new dependency
uv add package-name

# Add dev dependency
uv add --dev package-name

# Run Python scripts
uv run python script.py

# Run with module path
uv run python -m module.name
```

## High-Level Architecture

### Core Components

1. **FastAPI Main Application** (`api.py`)
   - Main API server with CORS, authentication, and rate limiting
   - Includes routers for core features, billing, admin, and external services
   - Handles health checks and monitoring

2. **AgentPress Framework** (`core/agentpress/`)
   - Thread management for LLM conversations
   - Tool registry and execution system
   - Prompt caching with Anthropic API optimization
   - Error processing and retry logic

3. **Background Processing** (`run_agent_background.py`)
   - Dramatiq-based worker for async agent execution
   - Redis-backed queue system
   - Handles long-running agent tasks

4. **Database Layer** (`core/services/supabase.py`)
   - Supabase async client wrapper
   - Thread-safe singleton pattern
   - Handles all database operations

5. **LLM Integration** (`core/services/llm.py`)
   - LiteLLM-based multi-provider support
   - Supports OpenAI, Anthropic, Groq, OpenRouter, Gemini, xAI
   - Unified error handling and retry logic

6. **Tool System** (`core/tools/`)
   - Modular tool architecture
   - MCP (Model Context Protocol) integration
   - Web search, data providers, messaging capabilities

7. **Sandbox Integration** (`core/sandbox/`)
   - Daytona-based code execution sandboxes
   - Docker-based presentation processing
   - Secure environment for agent code execution

8. **Billing System** (`core/billing/`)
   - Stripe integration for payments
   - Credit-based usage tracking
   - Subscription management
   - Trial and plan handling

### External Services Integration

- **AWS AgentCore** (`core/agentcore/`): Serverless agent infrastructure (optional, feature-flagged)
- **Daytona**: Cloud development environments for code execution
- **Composio**: External API integrations
- **Langfuse**: LLM observability and analytics
- **Sentry**: Error tracking and monitoring
- **Redis**: Caching and queue management
- **Supabase**: Database and auth

### Configuration Management

- Environment-based configuration via `.env` file
- Centralized config in `core/utils/config.py`
- Support for multiple environment modes: `local`, `staging`, `production`
- Feature flags for optional components (AgentCore, billing features)

### Agent Execution Flow

1. **Request**: API receives agent request via FastAPI endpoint
2. **Queue**: Task queued to Redis via Dramatiq
3. **Worker**: Background worker processes task using `run_agent_background.py`
4. **Thread Management**: `ThreadManager` handles LLM conversation flow
5. **Tool Execution**: Tools from registry executed as needed
6. **Response**: Results streamed back to client via WebSocket/HTTP streaming

### Testing Strategy

- **Unit tests**: Fast, isolated tests without external dependencies
- **Integration tests**: Tests requiring database/external services
- **API tests**: Endpoint testing with FastAPI TestClient
- **LLM tests**: Tests requiring actual LLM API calls (marked separately)
- **Coverage**: Target 60% minimum coverage configured in pytest.ini

### Key Development Patterns

- **Async/Await**: All I/O operations use async patterns
- **Dependency Injection**: Services passed via constructor/function parameters
- **Error Handling**: Comprehensive error processing with retry logic
- **Logging**: Structured logging via `structlog`
- **Rate Limiting**: Built-in rate limiting for API endpoints
- **Health Checks**: Dedicated health check endpoints for all services

### Important Files

- `api.py`: Main FastAPI application entry point
- `run_agent_background.py`: Background worker entry point
- `core/agentpress/thread_manager.py`: Core conversation management
- `core/services/supabase.py`: Database connection management
- `core/services/llm.py`: LLM provider abstraction
- `core/billing/api.py`: Billing and subscription endpoints
- `core/agentcore/`: AWS AgentCore integration (new feature)
- `pytest.ini`: Test configuration with markers and coverage settings

### Environment Variables

Key required environment variables (see `.env.example`):

**Database**: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
**LLM Providers**: At least one of `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.
**External Services**: `REDIS_HOST`, `DAYTONA_API_KEY`, `FIRECRAWL_API_KEY`
**Optional**: `STRIPE_SECRET_KEY` (billing), `LANGFUSE_*` (observability)

### Migration Notes

The codebase is currently migrating from legacy systems to AWS AgentCore. This migration is feature-flagged and can be enabled/disabled via `AGENTCORE_*` environment variables. During the transition period, both systems may coexist.