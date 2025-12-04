# Technology Stack

## Backend

**Framework**: Python 3.11+ with FastAPI and Uvicorn

**Key Libraries**:
- `litellm` - Multi-provider LLM integration (Anthropic, OpenAI)
- `dramatiq` - Background task queue with Redis
- `supabase` - Database, auth, and storage
- `redis` - Caching and queue management
- `mcp` - Model Context Protocol integration
- `composio` - External tool and trigger integrations
- `e2b-code-interpreter` - Code execution sandbox
- `langfuse` - LLM observability
- `stripe` - Payment processing
- `sentry-sdk` - Error tracking
- `structlog` - Structured logging

**Build System**: `uv` (Python package manager)

## Frontend

**Framework**: Next.js 15 with React 18 and TypeScript

**Key Libraries**:
- `@supabase/ssr` - Supabase client for Next.js
- `@tanstack/react-query` - Data fetching and caching
- `tailwindcss` - Styling
- `framer-motion` - Animations
- `@radix-ui/*` - UI primitives
- `lucide-react` - Icons
- `@tiptap/*` - Rich text editor
- `recharts` - Data visualization
- `zustand` - State management
- `next-intl` - Internationalization

**Build System**: npm with Next.js build pipeline

## Mobile App

**Framework**: React Native with Expo SDK 54

**Key Libraries**:
- `expo-router` - File-based navigation
- `@tanstack/react-query` - Data fetching
- `@supabase/supabase-js` - Backend integration
- `nativewind` - Tailwind CSS for React Native
- `react-native-reanimated` - Animations
- `@rn-primitives/*` - UI components
- `react-native-purchases` - In-app purchases (RevenueCat)
- `expo-notifications` - Push notifications

**Build System**: npm with Expo CLI

## SDK

**Language**: Python 3.11+

**Purpose**: Programmatic agent creation and management

**Build System**: `uv`

## Infrastructure

- **Database**: Supabase (PostgreSQL)
- **Cache/Queue**: Redis
- **Storage**: Supabase Storage (S3-compatible)
- **Containerization**: Docker with docker-compose
- **Agent Runtime**: Isolated Docker execution environments

## Common Commands

### Backend
```bash
# Install dependencies
cd backend
uv sync

# Start Redis
docker compose up redis

# Start Dramatiq worker (4 processes, 4 threads each)
uv run dramatiq --processes 4 --threads 4 run_agent_background

# Start API server
uv run api.py

# Run tests
uv run pytest
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

### Full Stack Setup
```bash
# From project root
python setup.py  # Interactive setup wizard
python start.py  # Start all services
```

## Environment Configuration

All components require environment variables. Use the setup wizard (`python setup.py`) for automated configuration, or manually create:
- `backend/.env`
- `frontend/.env.local`
- `apps/mobile/.env`
