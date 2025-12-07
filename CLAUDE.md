# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kortix (formerly Dimatic) is an open-source platform for building, managing, and training AI agents. The platform includes:

- **Suna** - A flagship generalist AI worker agent
- **Multi-platform architecture** - Web frontend (Next.js), mobile app (React Native/Expo), and backend API (FastAPI)
- **Docker-based agent runtime** - Containerized services for scalable agent execution
- **AWS AgentCore integration** - Serverless agent execution with semantic memory

## Technology Stack

### Backend (Python/FastAPI)
- **Language**: Python 3.11+ with async/await patterns
- **Framework**: FastAPI with UV package manager
- **Key Dependencies**: LiteLLM (multi-LLM provider), Supabase (PostgreSQL + Auth), Redis (caching), Dramatiq (background jobs), Docker (agent runtime)

### Frontend (Next.js/React)
- **Framework**: Next.js 15.3.1 with App Router and Turbopack
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS v4 with design tokens (no hardcoded colors)
- **State Management**: Zustand + TanStack Query
- **UI**: Radix UI primitives with custom components

### Mobile (React Native/Expo)
- **Framework**: React Native with Expo Router
- **Styling**: NativeWind (Tailwind CSS for mobile)
- **Font**: Roobert custom font family

## Development Commands

### Backend Development
```bash
# Install and setup
cd backend && uv sync

# Development server (port 8000)
uv run uvicorn api:app --reload

# Run tests
uv run pytest

# Background worker for agent processing
uv run dramatiq --skip-logging --processes 4 --threads 4 run_agent_background
```

### Frontend Development
```bash
# Install dependencies
cd frontend && npm install

# Development server (port 3015)
npm run dev

# Build and lint
npm run build
npm run lint
npm run format:check
```

### Mobile Development
```bash
# Install dependencies
cd apps/mobile && npm install

# Expo development server
npx expo start --clear
npx expo start --android  # For Android
npx expo start --ios      # For iOS
```

### Full Platform
```bash
# Automated setup wizard (configures all services)
python setup.py

# Start entire platform (backend + frontend + worker)
python start.py

# Docker services
docker compose up -d
```

## Architecture

### Backend Structure
- **`core/agentcore/`** - AWS AgentCore integration for serverless execution
- **`core/sandbox/`** - Docker runtime for agent execution
- **`core/tools/`** - Extensible tool system (browser automation, code interpreter, file operations)
- **`core/prompts/`** - AI prompt templates and system messages
- **`supabase/`** - Database migrations and RPC functions
- **`api.py`** - Main FastAPI application entry point

### Frontend Structure
- **`src/app/`** - Next.js App Router pages (server components)
- **`src/components/`** - Reusable React components with Radix UI
- **`src/lib/`** - Utilities, database clients, and configuration
- **Design tokens** - All styling uses centralized design tokens

### Agent System
- **Thread-based conversations** - Persistent chat history with context
- **Tool extensibility** - Plugin system for adding agent capabilities
- **Sandboxed execution** - Docker containers for secure code execution
- **Real-time communication** - WebSocket-based chat interfaces
- **Multi-LLM support** - Anthropic, OpenAI, Google, Groq providers

## Key Development Patterns

### Backend Patterns
- **Async-first design** - All API endpoints and database operations use async/await
- **Type safety** - Comprehensive Pydantic models for request/response validation
- **Error handling** - Structured error responses with proper HTTP status codes
- **Background jobs** - Dramatiq for long-running agent tasks

### Frontend Patterns
- **Server components** - Next.js App Router for optimal performance
- **Component composition** - Radix UI primitives with custom styled wrappers
- **State management** - Zustand for client state, TanStack Query for server state
- **Strict TypeScript** - Explicit types, no implicit any

### Agent Development
- **Tool interface** - Standardized tool system for extending agent capabilities
- **Docker isolation** - Each agent runs in isolated containers
- **Memory system** - Semantic search and context retrieval via AWS AgentCore

## Environment Configuration

Key environment variables (see `.env.example`):
- **Supabase**: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- **LLM Providers**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`
- **AWS AgentCore**: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_AGENT_CORE_GATEWAY_URL`
- **Infrastructure**: `REDIS_HOST`, `REDIS_PORT`, `STRIPE_SECRET_KEY`

## Database

- **Primary**: Supabase (PostgreSQL)
- **Migrations**: Located in `backend/supabase/migrations/`
- **RPC Functions**: Custom PostgreSQL functions for complex queries
- **Realtime**: Supabase Realtime for live updates

## Testing

- **Backend**: pytest with async support and coverage reporting
- **Frontend**: React Testing Library for component testing
- **Integration**: Docker Compose for end-to-end testing scenarios

## Special Integrations

### MCP (Model Context Protocol)
- Dynamic tool loading from external services
- Standardized tool interfaces
- Plugin architecture for extending agent capabilities

### Langfuse Integration
- AI observability and performance monitoring
- Agent conversation tracking and analytics

### Payment Processing
- Stripe integration for subscription management
- Credit-based billing system