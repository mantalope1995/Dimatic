# Project Structure

## Repository Layout

```
kortix/
├── backend/              # Python FastAPI backend
├── frontend/             # Next.js frontend
├── apps/mobile/          # React Native mobile app
├── sdk/                  # Python SDK for Kortix API
├── docs/                 # Documentation
├── docker-compose.yaml   # Docker orchestration
├── setup.py             # Setup wizard
└── start.py             # Service management script
```

## Backend Structure (`backend/`)

```
backend/
├── core/                           # Core application logic
│   ├── agentpress/                # Agent execution framework
│   │   ├── context_manager.py    # Context and prompt management
│   │   ├── thread_manager.py     # Conversation thread handling
│   │   ├── tool_registry.py      # Tool registration system
│   │   └── prompt_caching.py     # LLM prompt caching
│   ├── ai_models/                 # LLM model management
│   │   ├── ai_models.py          # Model definitions
│   │   ├── manager.py            # Model lifecycle management
│   │   └── registry.py           # Model registry
│   ├── api_models/                # API request/response models
│   ├── billing/                   # Billing and subscription system
│   │   ├── credits/              # Credit management
│   │   ├── payments/             # Payment processing
│   │   └── subscriptions/        # Subscription handling
│   ├── composio_integration/      # Composio service integrations
│   ├── credentials/               # Credential management
│   ├── google/                    # Google Workspace integrations
│   ├── knowledge_base/            # Knowledge base and RAG
│   ├── mcp_module/                # MCP (Model Context Protocol) integration
│   ├── notifications/             # Push notifications (Novu)
│   ├── prompts/                   # System prompts and templates
│   ├── referrals/                 # Referral system
│   ├── sandbox/                   # Docker sandbox execution
│   ├── services/                  # Core services
│   │   ├── docker/               # Docker management
│   │   ├── email.py              # Email service
│   │   ├── langfuse.py           # LLM observability
│   │   ├── llm.py                # LLM client wrapper
│   │   ├── redis.py              # Redis client
│   │   ├── redis_worker.py       # Dramatiq worker
│   │   └── supabase.py           # Supabase client
│   ├── templates/                 # Agent templates
│   ├── tools/                     # Agent tools
│   │   ├── agent_builder_tools/  # Tools for building agents
│   │   ├── data_providers/       # Data provider integrations
│   │   ├── sb_*.py               # Sandbox tools (files, shell, vision, etc.)
│   │   └── tool_registry.py      # Tool registration
│   ├── triggers/                  # Event triggers and webhooks
│   ├── utils/                     # Utility functions
│   ├── agent_service.py           # Agent orchestration
│   ├── agent_runs.py              # Agent execution management
│   ├── api.py                     # API route definitions
│   ├── auth.py                    # Authentication logic
│   └── threads.py                 # Thread management
├── supabase/                      # Supabase configuration
│   ├── migrations/               # Database migrations
│   └── config.toml               # Supabase config
├── api.py                         # Main FastAPI application entry
├── run_agent_background.py        # Dramatiq worker entry
├── pyproject.toml                 # Python dependencies (uv)
└── Dockerfile                     # Backend container image
```

## Frontend Structure (`frontend/`)

```
frontend/
├── src/
│   ├── app/                       # Next.js App Router pages
│   │   ├── (auth)/               # Authentication pages
│   │   ├── (dashboard)/          # Main dashboard pages
│   │   ├── api/                  # API routes
│   │   └── layout.tsx            # Root layout
│   ├── components/                # React components
│   │   ├── ui/                   # Reusable UI components
│   │   ├── agents/               # Agent-related components
│   │   ├── chat/                 # Chat interface components
│   │   ├── settings/             # Settings components
│   │   └── ...                   # Feature-specific components
│   ├── hooks/                     # Custom React hooks
│   ├── lib/                       # Utility libraries
│   │   ├── supabase/             # Supabase client setup
│   │   ├── utils.ts              # General utilities
│   │   └── api.ts                # API client
│   ├── stores/                    # Zustand state stores
│   ├── providers/                 # React context providers
│   ├── i18n/                      # Internationalization
│   └── middleware.ts              # Next.js middleware
├── public/                        # Static assets
├── translations/                  # Translation files (en, de, es, fr, etc.)
├── package.json                   # npm dependencies
├── next.config.ts                 # Next.js configuration
├── tailwind.config.js             # Tailwind CSS config
└── tsconfig.json                  # TypeScript config
```

## Mobile App Structure (`apps/mobile/`)

```
apps/mobile/
├── api/                           # Centralized API layer
│   ├── index.ts                  # API exports
│   ├── config.ts                 # Configuration
│   ├── supabase.ts               # Supabase client
│   └── types.ts                  # Type definitions
├── app/                           # Expo Router screens
│   ├── _layout.tsx               # Root layout
│   ├── index.tsx                 # Entry screen
│   ├── home.tsx                  # Home screen
│   ├── auth/                     # Auth screens
│   └── ...                       # Other screens
├── components/                    # React Native components
│   ├── ui/                       # Reusable UI components
│   ├── agents/                   # Agent components
│   ├── chat/                     # Chat components
│   └── ...                       # Feature components
├── contexts/                      # React contexts
│   ├── AuthContext.tsx           # Authentication
│   ├── AgentContext.tsx          # Agent state
│   └── ...                       # Other contexts
├── hooks/                         # Custom hooks
├── lib/                           # Utilities
├── locales/                       # Translation files
├── assets/                        # Images, fonts, etc.
├── android/                       # Android native code
├── ios/                           # iOS native code
├── app.json                       # Expo configuration
├── package.json                   # npm dependencies
└── tsconfig.json                  # TypeScript config
```

## SDK Structure (`sdk/`)

```
sdk/
├── kortix/                        # Python SDK package
│   ├── api/                      # API client modules
│   ├── agent.py                  # Agent interface
│   ├── thread.py                 # Thread interface
│   ├── tools.py                  # Tool definitions
│   └── kortix.py                 # Main SDK class
├── example/                       # Usage examples
└── pyproject.toml                # SDK dependencies
```

## Key Architectural Patterns

### Backend
- **Modular structure**: Features organized in `core/` subdirectories
- **Service layer**: Core services in `core/services/`
- **Tool system**: Extensible tools in `core/tools/`
- **API routes**: Defined in `core/api.py` and feature-specific `*_api.py` files
- **Background jobs**: Dramatiq actors in `run_agent_background.py`
- **Database**: Supabase with migrations in `supabase/migrations/`

### Frontend
- **App Router**: File-based routing in `src/app/`
- **Component library**: Reusable components in `src/components/ui/`
- **State management**: Zustand stores + React Query for server state
- **API client**: Centralized in `src/lib/api.ts`
- **Styling**: Tailwind CSS with design tokens

### Mobile
- **Centralized API**: All API code in `api/` directory
- **File-based routing**: Expo Router in `app/`
- **Context providers**: Global state in `contexts/`
- **NativeWind**: Tailwind CSS for React Native
- **Type safety**: Full TypeScript coverage

## Configuration Files

- `backend/.env` - Backend environment variables
- `frontend/.env.local` - Frontend environment variables
- `apps/mobile/.env` - Mobile app environment variables
- `docker-compose.yaml` - Service orchestration
- `backend/supabase/config.toml` - Supabase configuration
- `.setup_progress` - Setup wizard state (generated)

## Important Conventions

1. **Python imports**: Use absolute imports from `core.*`
2. **TypeScript paths**: Use `@/` alias for `src/` directory
3. **API routes**: Backend at `/api/*`, frontend API routes at `/api/*`
4. **Environment variables**: Prefix with `NEXT_PUBLIC_` for client-side access in Next.js
5. **Database migrations**: Sequential numbered files in `backend/supabase/migrations/`
6. **Tool naming**: Tools prefixed with `sb_` for sandbox tools
7. **Component organization**: Group by feature, not by type
