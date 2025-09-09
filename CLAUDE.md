# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kortix (formerly Suna) is an open-source platform for building, managing, and training AI agents. It includes Suna, a flagship generalist AI worker agent, and provides infrastructure for creating custom agents.

## Architecture

### Technology Stack
- **Frontend**: Next.js 15+ with TypeScript, Tailwind CSS 4, Radix UI components
- **Backend**: Python 3.11+ with FastAPI, LiteLLM for LLM integration
- **Database**: Supabase (PostgreSQL) with Row Level Security
- **Agent Runtime**: Docker containers with isolated execution environments
- **Caching**: Redis for session management and caching
- **Background Jobs**: Dramatiq for worker processes
- **Monitoring**: Langfuse, Sentry, Prometheus

### Repository Structure
```
├── frontend/               # Next.js application
│   └── src/
│       ├── app/           # Next.js app router pages
│       ├── components/    # Reusable React components
│       ├── hooks/         # Custom React hooks
│       ├── lib/          # Utilities and configurations
│       ├── providers/    # Context providers
│       └── contexts/     # React contexts
├── backend/               # Python FastAPI backend
│   ├── core/             # Core agent and system logic
│   ├── admin/            # Admin functionality
│   ├── billing/          # Billing services
│   ├── supabase/         # Database migrations & config
│   ├── api.py            # Main FastAPI application
│   └── run_agent_background.py  # Background worker
├── sdk/                   # Python SDK
├── apps/mobile/          # Mobile application
└── docs/                 # Documentation
```

## Development Commands

### Initial Setup
```bash
# Run the automated setup wizard
python setup.py

# Start the platform (after setup)
python start.py
```

### Frontend Development
```bash
cd frontend

# Install dependencies (if needed)
npm install

# Run development server with Turbopack
npm run dev

# Build for production
npm run build

# Run linting
npm run lint

# Format code
npm run format

# Check formatting
npm run format:check
```

### Backend Development
```bash
cd backend

# Run the FastAPI server
uv run api.py

# Run background worker (in separate terminal)
uv run dramatiq run_agent_background

# Run tests
uv run pytest

# Run specific test
uv run pytest test_file.py::test_function
```

### Docker Development
```bash
# Start all services with Docker Compose
docker compose up -d

# Start only infrastructure (Redis)
docker compose up redis -d

# Stop all services
docker compose down

# View logs
docker compose logs -f [service_name]
```

## Core Patterns and Conventions

### Agent System
- **Agent Versions**: Managed through `agent_versions` table with JSONB configuration
- **Tool System**: Dual schema decorators (OpenAPI + XML) with consistent ToolResult returns
- **Workflows**: Step-by-step execution tracked in `agent_workflows` table
- **Triggers**: Event-based and scheduled automation via `agent_triggers`
- **Isolated Execution**: Each agent runs in Docker container with sandboxing

### Authentication & Security
- **JWT Validation**: Supabase tokens verified in backend
- **Row Level Security**: Database-level access control via Supabase RLS
- **Credential Encryption**: Sensitive API keys encrypted before storage
- **Input Validation**: Pydantic models for all API inputs

### Database Patterns
- **Migrations**: Located in `backend/supabase/migrations/`
- **Idempotent SQL**: All migrations handle duplicate runs safely
- **Enums**: Created with IF NOT EXISTS patterns
- **Indexes**: Foreign keys and query optimization

### API Structure
- **FastAPI Routes**: RESTful endpoints in `backend/api.py`
- **Error Handling**: Structured error responses with proper HTTP codes
- **Async/Await**: Throughout for performance
- **Connection Pooling**: Redis and database connections

### Frontend Patterns
- **Component Structure**: Reusable components in `frontend/src/components/`
- **State Management**: React Query for server state, Zustand for client state
- **Type Safety**: Strict TypeScript with comprehensive types
- **Styling**: Tailwind CSS 4 with custom components using Radix UI

### Tool Integration
- **LLM Providers**: Multi-provider support via LiteLLM (Anthropic, OpenAI, etc.)
- **Browser Automation**: Playwright integration for web tasks
- **File Processing**: Support for documents, spreadsheets, presentations
- **Web Intelligence**: Tavily for search, Firecrawl for scraping

## Environment Configuration
- Backend: Copy `backend/.env.example` to `backend/.env`
- Frontend: Environment variables in `frontend/.env.local`
- Use `mise.toml` for tool version management

## Testing
- **Backend**: Unit tests with pytest, async support with pytest-asyncio
- **Frontend**: Component testing with React Testing Library
- **Integration**: API endpoint testing
- **Performance**: Agent execution benchmarks

## Key Dependencies
### Frontend
- Next.js 15+, React 18+, TypeScript 5+
- @tanstack/react-query, @supabase/supabase-js
- @radix-ui components, tailwindcss 4
- react-hook-form, zod for validation

### Backend  
- FastAPI 0.115+, Python 3.11+
- supabase 2.17+, redis 5.2+, litellm 1.75+
- dramatiq 1.18+, pydantic for validation
- daytona for agent runtime management