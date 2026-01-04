# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Kortix** (formerly Suna) is a full-stack open-source platform for building, managing, and training AI agents.

### Main Components

| Component | Location | Tech Stack |
|-----------|----------|------------|
| Backend API | `/backend` | Python 3.11+, FastAPI |
| Frontend Dashboard | `/frontend` | Next.js 15, TypeScript, Tailwind CSS v4 |
| Mobile App | `/apps/mobile` | React Native, Expo, NativeWind |
| Python SDK | `/sdk` | Python 3.11+ |

## Development Commands

### Root Level

```bash
# First-time setup (interactive wizard)
python setup.py

# Start the entire platform
python start.py

# Docker development
docker compose up -d
```

### Backend (`/backend`)

**IMPORTANT:** Dramatiq worker defaults to CPU count for processes. Always specify `--processes` to avoid too many Redis connections.

```bash
# Start Redis (caching)
docker compose up redis

# Start Dramatiq worker (background task processing)
uv run dramatiq --processes 4 --threads 4 run_agent_background

# Start main API server
uv run api.py
# OR with uvicorn for hot reload
uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Testing
uv run pytest
uv run pytest --coverage

# Linting (pre-commit hooks configured)
uv run ruff check .
uv run mypy .
```

### Frontend (`/frontend`)

```bash
npm run dev        # Development server with turbopack
npm run build      # Production build
npm start          # Start production server

# Testing
npm run test       # Vitest
npm run test:watch
npm run test:ui

# Code quality
npm run lint
npm run format
npm run format:check
```

### Mobile (`/apps/mobile`)

```bash
npx expo start --clear

# Production builds
eas build --platform all
```

## Architecture Overview

### Backend Architecture (`/backend`)

- **Entry Point:** `api.py` - Main FastAPI application with all REST endpoints
- **Core Engine:** `core/run.py` - Agent runtime and tool management system

**Key Directories:**

| Directory | Purpose |
|-----------|---------|
| `core/agentpress/` | Thread-based agent execution engine |
| `core/tools/` | Extensible tool framework (core, sandbox, utility, agent-builder categories) |
| `core/sandbox/` | Docker-based isolated execution environments |
| `core/supabase/` | Database layer (PostgreSQL + Real-time subscriptions) |
| `core/admin/` | Authentication system (JWT, OAuth providers) |
| `core/billing/` | Stripe payment integration |

**Background Processing:** Dramatiq + Redis for async operations

**Observability:** Langfuse tracing + Sentry error tracking

### Frontend Architecture (`/frontend`)

- **Framework:** Next.js 15 with App Router
- **Styling:** Tailwind CSS v4
- **State Management:** Zustand (client) + TanStack Query (server)
- **UI Components:** Radix UI primitives
- **Rich Text Editor:** TipTap
- **Real-time:** Supabase subscriptions for live updates

### Mobile Architecture (`/apps/mobile`)

The mobile app has **strict architecture rules** documented in `.cursorrules`:

- One component per file
- Feature-based folder organization
- All logic extracted to custom hooks
- Semantic design tokens (NO hardcoded colors)
- Roobert font family exclusively
- Lucide React Native icons only
- React Native Reanimated for animations

## Key Patterns & Conventions

### Mobile-Specific Rules

**Colors:** Use semantic design tokens from `global.css` ONLY
```tsx
// ✅ GOOD
className="bg-background text-foreground border-border"

// ❌ BAD
className="bg-[#F8F8F8] text-[#121215]"
```

**Fonts:** Use Roobert font classes
```tsx
className="font-roobert"           // Regular (400)
className="font-roobert-medium"    // Medium (500)
className="font-roobert-semibold"  // Semi-bold (600)
```

**Spacing:** Use Tailwind scale only (gap-1 to gap-12), never custom pixel values
```tsx
// ✅ GOOD
className="gap-3 p-4 mx-6"

// ❌ BAD
style={{ gap: 11.25, padding: 15.5 }}
```

**Icons:** Always use Lucide React Native via Icon wrapper
```tsx
import { Menu } from 'lucide-react-native';
<Icon as={Menu} size={24} className="text-foreground" />
```

**Logging:** Log user interactions with emoji conventions
- 🎯 User actions
- 🤖 Agent/AI operations
- 📳 Haptic feedback
- ⏰ Timestamps
- 📊 Data objects

**Theme:** Light mode first, dark mode as variant
```tsx
const { colorScheme } = useColorScheme();
const Symbol = colorScheme === 'dark' ? SymbolWhite : SymbolBlack;
```

### Cross-Platform Conventions

- **TypeScript:** Strict mode enabled across all platforms
- **Testing:** Pytest (backend), Vitest (frontend), Jest/RTL (mobile)
- **Pre-commit hooks:** Configured for automatic linting
- **British English:** Use "analyse" instead of "analyze", "colour" instead of "color", etc.

## Important Files

| File | Purpose |
|------|---------|
| `/backend/api.py` | Main FastAPI application entry point |
| `/backend/core/run.py` | Agent runtime and execution engine |
| `/backend/pyproject.toml` | Python dependencies (managed with uv) |
| `/frontend/package.json` | Frontend dependencies and scripts |
| `/apps/mobile/.cursorrules` | Detailed mobile development rules |
| `/README.md` | Project overview and quick start guide |
| `/CONTRIBUTING.md` | Contribution workflow guidelines |

## Tools & Integrations

| Category | Tool |
|----------|------|
| **LLM** | LiteLLM (OpenAI, Anthropic, Minimax, others) |
| **Database** | Supabase (PostgreSQL + Auth + Storage + Real-time) |
| **Cache/Queue** | Redis with Dramatiq |
| **Sandbox** | Docker containers for isolated agent execution |
| **Monitoring** | Langfuse (tracing) + Sentry (error tracking) |
| **Payments** | Stripe |
| **Package Managers** | uv (Python), npm (JavaScript) |

## British English Spelling

This codebase uses British English spelling conventions. When adding new code, maintain consistency:
- "analyse" (not "analyze")
- "colour" (not "color")
- "centre" (not "center")
- "licence" (not "license" - for the noun)
- "organise" (not "organize")
