# Project Structure

```
├── api.py                    # FastAPI application entry point
├── run_agent_background.py   # Dramatiq worker entry point
├── pyproject.toml            # Python dependencies (uv)
├── docker-compose.yml        # Local development services
├── Dockerfile                # Production container
│
├── core/                     # Main application code
│   ├── api.py                # Core API router aggregation
│   │
│   ├── agentpress/           # LLM conversation framework
│   │   ├── thread_manager.py # Conversation thread management
│   │   ├── tool_registry.py  # Tool registration system
│   │   ├── context_manager.py# Context window compression
│   │   ├── prompt_caching.py # Anthropic prompt caching
│   │   └── response_processor.py
│   │
│   ├── tools/                # Agent tool implementations
│   │   ├── tool_registry.py  # Tool discovery and loading
│   │   ├── sb_*.py           # Sandbox tools (files, shell, etc.)
│   │   ├── web_search_tool.py
│   │   └── mcp_tool_wrapper.py
│   │
│   ├── services/             # External service integrations
│   │   ├── llm.py            # LiteLLM wrapper
│   │   ├── supabase.py       # Database client
│   │   ├── redis.py          # Redis client
│   │   └── langfuse.py       # Observability
│   │
│   ├── billing/              # Payment and credits system
│   │   ├── api.py            # Billing endpoints
│   │   ├── credits/          # Credit calculation and tracking
│   │   ├── subscriptions/    # Subscription management
│   │   └── external/         # Stripe/RevenueCat integrations
│   │
│   ├── sandbox/              # Code execution environments
│   │   ├── sandbox.py        # Daytona integration
│   │   └── docker/           # Sandbox container config
│   │
│   ├── ai_models/            # Model configuration
│   │   ├── manager.py        # Model resolution and params
│   │   └── registry.py       # Model definitions
│   │
│   ├── utils/                # Shared utilities
│   │   ├── config.py         # Environment configuration
│   │   ├── logger.py         # Structured logging
│   │   └── rate_limiter.py   # API rate limiting
│   │
│   ├── admin/                # Admin API endpoints
│   ├── credentials/          # Secure credential storage
│   ├── knowledge_base/       # Agent knowledge management
│   ├── notifications/        # User notifications
│   ├── triggers/             # Automated agent triggers
│   └── templates/            # Agent templates
│
└── supabase/                 # Database configuration
    ├── config.toml           # Supabase local config
    └── migrations/           # SQL migrations (timestamped)
```

## Key Patterns

- **Router Aggregation**: Sub-routers in `core/` modules included via `core/api.py`
- **Service Singletons**: Database/Redis connections via singleton pattern
- **Tool Registration**: Tools registered via `ToolRegistry` with OpenAPI schemas
- **Async Throughout**: All I/O operations use async/await
- **Feature Modules**: Self-contained modules with own `api.py` router

## Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **API Routers**: `router = APIRouter()` in each module's `api.py`
- **Migrations**: `YYYYMMDDHHMMSS_description.sql`
- **Tools**: `sb_*_tool.py` for sandbox tools, `*_tool.py` for others
