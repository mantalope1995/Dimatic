# Project Structure

## Root Layout

```
/
├── backend/          # Python FastAPI backend
├── frontend/         # Next.js web application
├── apps/mobile/      # React Native mobile app
├── sdk/              # Python SDK for programmatic access
├── docs/             # Documentation and diagrams
├── setup.py          # Interactive setup wizard
├── start.py          # Service orchestration script
└── docker-compose.yaml
```

## Backend (`/backend`)

```
backend/
├── api.py                    # FastAPI application entry point
├── run_agent_background.py   # Dramatiq worker entry point
├── core/                     # Core business logic
│   ├── agentpress/          # Agent orchestration framework
│   │   ├── thread_manager.py
│   │   ├── context_manager.py
│   │   ├── tool_registry.py
│   │   └── prompt_caching.py
│   ├── agentcore/           # AWS Bedrock AgentCore integration
│   ├── ai_models/           # LLM model registry and management
│   ├── api_models/          # Pydantic request/response models
│   ├── billing/             # Stripe integration and credit system
│   ├── composio_integration/ # External tool integrations
│   ├── credentials/         # Secure credential management
│   ├── knowledge_base/      # RAG and document processing
│   ├── mcp_module/          # Model Context Protocol integration
│   ├── notifications/       # Push notifications (Novu)
│   ├── prompts/             # System prompts and templates
│   ├── sandbox/             # Code execution environment
│   ├── services/            # Shared services (Redis, Supabase, LLM)
│   ├── templates/           # Agent templates and marketplace
│   ├── tools/               # Built-in agent tools
│   ├── triggers/            # Event-based automation
│   ├── utils/               # Utilities and helpers
│   └── admin/               # Admin API endpoints
├── supabase/                # Database migrations and config
│   └── migrations/          # SQL migration files
└── pyproject.toml           # Python dependencies (uv)
```

### Key Backend Patterns

- **API Structure**: FastAPI routers organized by domain in `core/*/api.py`
- **Services**: Singleton services in `core/services/` (Redis, Supabase, LLM)
- **Background Jobs**: Dramatiq actors in `run_agent_background.py`
- **Database**: Supabase client with async operations
- **Tool System**: Registry-based tool discovery in `core/tools/`
- **Agent Execution**: Thread-based conversation management via `agentpress/`

## Frontend (`/frontend`)

```
frontend/
├── src/
│   ├── app/                 # Next.js App Router pages
│   │   ├── (auth)/         # Auth-protected routes
│   │   ├── (public)/       # Public routes
│   │   └── api/            # API route handlers
│   ├── components/          # React components
│   │   ├── ui/             # Reusable UI primitives
│   │   ├── agents/         # Agent-specific components
│   │   ├── chat/           # Chat interface
│   │   └── settings/       # Settings panels
│   ├── hooks/               # Custom React hooks
│   ├── lib/                 # Utilities and helpers
│   ├── stores/              # Zustand state stores
│   ├── providers/           # React context providers
│   └── i18n/                # Internationalization
├── translations/            # Translation files (en, es, fr, etc.)
├── public/                  # Static assets
└── next.config.ts           # Next.js configuration
```

### Key Frontend Patterns

- **Routing**: File-based routing with Next.js App Router
- **Data Fetching**: React Query for server state, Zustand for client state
- **Styling**: Tailwind CSS with custom design tokens
- **Components**: Radix UI primitives with custom styling
- **Auth**: Supabase SSR for authentication
- **Real-time**: Supabase subscriptions for live updates

## Mobile App (`/apps/mobile`)

```
apps/mobile/
├── api/                     # Centralized API layer
│   ├── client.ts           # HTTP client configuration
│   ├── config.ts           # API configuration
│   ├── types.ts            # TypeScript types
│   ├── supabase.ts         # Supabase client
│   └── hooks/              # React Query hooks
├── app/                     # Expo Router screens
│   ├── (tabs)/             # Tab navigation
│   ├── auth/               # Authentication screens
│   └── _layout.tsx         # Root layout
├── components/              # React Native components
│   ├── ui/                 # Reusable UI components
│   ├── chat/               # Chat interface
│   └── agents/             # Agent components
├── hooks/                   # Custom hooks
├── lib/                     # Utilities (non-API)
├── contexts/                # React contexts
├── stores/                  # Zustand stores
├── locales/                 # Translation files
└── assets/                  # Images, fonts, etc.
```

### Key Mobile Patterns

- **Navigation**: Expo Router with file-based routing
- **API Layer**: Centralized in `/api` directory with React Query
- **Styling**: NativeWind (Tailwind for React Native)
- **Components**: RN Primitives for cross-platform UI
- **Auth**: Supabase with Expo Auth Session
- **Payments**: RevenueCat for in-app purchases

## SDK (`/sdk`)

```
sdk/
├── kortix/
│   ├── kortix.py           # Main client
│   ├── agent.py            # Agent management
│   ├── thread.py           # Thread management
│   ├── tools.py            # MCP tool integration
│   └── api/                # API client modules
├── example/                 # Usage examples
└── pyproject.toml          # Dependencies
```

## Database (`/backend/supabase`)

- **Migrations**: Sequential SQL files in `migrations/`
- **Schema**: PostgreSQL with RLS policies
- **Key Tables**: `agents`, `threads`, `messages`, `agent_runs`, `credit_accounts`, `agent_templates`
- **Storage**: Buckets for files, knowledge base documents, and profile pictures

## Configuration Files

- `pyproject.toml` - Python dependencies (backend, SDK)
- `package.json` - Node dependencies (frontend, mobile)
- `docker-compose.yml` - Service orchestration
- `next.config.ts` - Next.js configuration
- `app.json` - Expo configuration
- `tailwind.config.js` - Tailwind CSS configuration (frontend, mobile)
