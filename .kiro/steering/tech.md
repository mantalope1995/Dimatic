# Technology Stack

## Backend

**Language & Framework**: Python 3.11+ with FastAPI
**Package Manager**: uv (Astral's fast Python package manager)
**Key Dependencies**:
- `litellm` - Multi-provider LLM integration (Anthropic, OpenAI, etc.)
- `dramatiq` - Background task processing with Redis
- `supabase` - Database client and authentication
- `prisma` - Database ORM
- `mcp` - Model Context Protocol for tool integrations
- `composio` - Third-party service integrations
- `e2b-code-interpreter` - Code execution sandbox
- `stripe` - Payment processing
- `langfuse` - LLM observability
- `sentry-sdk` - Error tracking

**Database**: PostgreSQL via Supabase (with pg_cron, pg_net extensions)
**Cache/Queue**: Redis (for Dramatiq workers and caching)
**Storage**: Supabase Storage (S3-compatible)

## Frontend

**Framework**: Next.js 15 (App Router) with React 18
**Language**: TypeScript (strict mode)
**Package Manager**: npm
**Styling**: Tailwind CSS 4 with tailwindcss-animate
**UI Components**: Radix UI primitives with custom components
**Key Dependencies**:
- `@supabase/ssr` - Supabase client for Next.js
- `@tanstack/react-query` - Data fetching and state management
- `@tiptap/react` - Rich text editor
- `framer-motion` - Animations
- `zustand` - Client state management
- `next-intl` - Internationalization
- `recharts` - Data visualization
- `zod` - Schema validation
- `react-hook-form` - Form handling

## Mobile App

**Framework**: React Native with Expo SDK 54
**Language**: TypeScript
**Package Manager**: npm
**Styling**: NativeWind (Tailwind CSS for React Native)
**Navigation**: Expo Router (file-based routing)
**Key Dependencies**:
- `@supabase/supabase-js` - Backend integration
- `@tanstack/react-query` - Data fetching
- `react-native-purchases` - In-app purchases (RevenueCat)
- `@rn-primitives/*` - UI component primitives
- `expo-notifications` - Push notifications
- `lottie-react-native` - Animations

## Infrastructure

**Containerization**: Docker with Docker Compose
**Orchestration**: Docker Compose for local development
**Sandbox**: Docker containers for isolated agent execution
**Deployment**: Supports cloud deployment (configuration via setup wizard)

## Development Tools

**Python**:
- `pytest` - Testing framework
- `uv` - Package management and virtual environments

**Frontend**:
- `eslint` - Linting
- `prettier` - Code formatting
- `typescript` - Type checking

**Mobile**:
- `patch-package` - Package patching
- `prettier` - Code formatting

## Common Commands

### Backend
```bash
# Install dependencies
cd backend
uv sync

# Start Redis
docker compose up redis -d

# Start backend API
uv run api.py

# Start background worker (IMPORTANT: always specify --processes)
uv run dramatiq --processes 4 --threads 4 run_agent_background

# Run tests
uv run pytest

# Database migrations (via Supabase CLI)
cd backend/supabase
npx supabase db push
```

### Frontend
```bash
# Install dependencies
cd frontend
npm install

# Development server
npm run dev

# Production build
npm run build
npm run start

# Linting and formatting
npm run lint
npm run format
```

### Mobile
```bash
# Install dependencies
cd apps/mobile
npm install

# Start development server
npm run dev

# Run on specific platform
npm run ios
npm run android
npm run web

# Clean cache
npm run clean
```

### Full Stack (Docker Compose)
```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Start specific service
docker compose up redis -d
```

### Setup & Start
```bash
# Initial setup wizard
python setup.py

# Start services (based on setup method)
python start.py
```

## Environment Configuration

Configuration is managed through `.env` files:
- `backend/.env` - Backend configuration
- `frontend/.env.local` - Frontend configuration
- `apps/mobile/.env` - Mobile app configuration

Use `setup.py` wizard for guided configuration.

## API Integration Patterns

**LLM Providers**: Unified via LiteLLM (supports OpenAI, Anthropic, Groq, OpenRouter, XAI, Gemini, AWS Bedrock)
**Tool System**: MCP (Model Context Protocol) for extensible tool integrations
**Authentication**: Supabase Auth with JWT tokens
**Real-time**: Supabase Realtime for live updates
**Background Jobs**: Dramatiq with Redis broker
