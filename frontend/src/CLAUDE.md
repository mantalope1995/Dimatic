# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kortix (formerly Dimatic) is a modern Next.js 15 application featuring AI agent management, real-time collaboration, and comprehensive business functionality. The app uses TypeScript, Tailwind CSS v4, and Supabase for authentication and database operations.

## Development Commands

```bash
# Setup and installation
npm install                    # Install dependencies
cd .. && python setup.py     # Run setup wizard to configure .env.local

# Development
npm run dev                  # Start development server with Turbopack (localhost:3015)
npm run build               # Build for production
npm run start               # Start production server
npm run lint                # Run ESLint
npm run format              # Format code with Prettier
npm run format:check        # Check code formatting
```

## Environment Setup

The project requires a `.env.local` file with these variables:
- `NEXT_PUBLIC_SUPABASE_URL` - Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` - Supabase anonymous key
- `NEXT_PUBLIC_BACKEND_URL` - Backend API URL (defaults to http://localhost:8000/api)
- `NEXT_PUBLIC_URL` - Frontend URL (defaults to http://localhost:3015)
- `NEXT_PUBLIC_ENV_MODE` - Environment mode (LOCAL/DEMO/PRODUCTION)
- `KORTIX_ADMIN_API_KEY` - Admin API key

Use the setup wizard (`python setup.py` from project root) for automatic configuration.

## Architecture Overview

### Directory Structure

- `/src/app` - Next.js App Router pages
  - `(dashboard)` - Authenticated pages (settings, projects, agents, admin)
  - `(home)` - Landing and marketing pages
  - `auth` - Authentication pages
  - `api` - API routes
- `/src/components` - React components
  - `ui` - shadcn/ui component library
  - `auth`, `settings`, `home` - Feature-specific components
- `/src/lib` - Utilities and configurations
  - `api/` - API client modules for different services
  - `supabase/` - Supabase client setup
  - `utils/` - Helper functions and utilities
- `/src/stores` - Zustand state management stores
- `/src/providers` - React context providers
- `/src/hooks` - Custom React hooks

### Key Technologies

- **Next.js 15.3.1** with App Router and Turbopack
- **React 18** with TypeScript
- **Tailwind CSS v4** with shadcn/ui components
- **Supabase** for authentication and database
- **TanStack Query** for server state management
- **Zustand** for client state management
- **Tiptap** for rich text editing
- **Yjs** for real-time collaboration

### State Management

- **Server State**: TanStack Query for API calls and caching
- **Client State**: Zustand stores (agent selection, model configuration, UI state)
- **Real-time**: Yjs for collaborative editing, Supabase subscriptions

### Data Flow

1. **API Layer**: `/src/lib/api/` modules handle backend communication
2. **State Layer**: Zustand stores manage client-side state
3. **Query Layer**: TanStack Query handles server state and caching
4. **Component Layer**: React components consume stores and queries

## Component System

### shadcn/ui Components

The project uses shadcn/ui components located in `/src/components/ui/`. These are built on Radix UI primitives and follow specific patterns:
- Use `cn()` utility for class merging
- Follow the established component structure and naming
- Components are configurable via props and support variant patterns

### Custom Components

- Feature-specific components in respective directories (`/src/components/auth/`, etc.)
- Rich text editor using Tiptap with extensions
- Code editor using CodeMirror
- File upload and processing components

## Authentication & Authorization

- **Provider**: Supabase Auth with SSR support
- **Configuration**: `/src/lib/supabase/` contains client and server setup
- **Middleware**: Route protection via Next.js middleware
- **Phone Verification**: Integrated phone number verification system

## API Integration

### Backend Communication

- **Base Client**: `/src/lib/api-client.ts` handles HTTP requests
- **Service Modules**: Individual modules in `/src/lib/api/` for different services
- **Error Handling**: Centralized error handling with user-friendly messages
- **Streaming**: Real-time streaming support for AI responses

### Key API Services

- Agents (`/src/lib/api/agents.ts`)
- Threads and conversations (`/src/lib/api/threads.ts`)
- Billing and usage (`/src/lib/api/billing.ts`, `/src/lib/api/usage.ts`)
- Notifications (`/src/lib/api/notifications.ts`)

## Development Patterns

### TypeScript Configuration

- **Strict Mode**: Disabled for flexibility (`strict: false`)
- **Path Aliases**: `@/*` maps to `./src/*`
- **Next.js Plugin**: Enabled for optimized builds

### Code Quality

- **ESLint**: Next.js recommended rules with some disabled (`no-unused-vars`, `no-explicit-any`)
- **Prettier**: Standard formatting with semi, single quotes, trailing commas
- **Import Organization**: Optimized package imports in Next.js config

### State Management Patterns

- Use Zustand for complex client state that needs to be shared
- Use React state for local component state
- Use TanStack Query for server state with caching
- Follow the established store patterns in `/src/stores/`

## Internationalization

- **Framework**: next-intl
- **Languages**: 8 languages (en, de, es, fr, it, ja, pt, zh)
- **Translations**: Located in `/translations/` directory
- **Usage**: Use `useTranslations()` hook in components

## Performance Optimizations

### Build Optimizations

- **Package Imports**: Optimized imports for common libraries (lucide-react, framer-motion, etc.)
- **Image Optimization**: AVIF/WebP support with responsive image sizes
- **Compression**: Enabled with proper caching headers
- **Standalone Output**: Docker builds use standalone Next.js output

### Runtime Optimizations

- **Turbopack**: Development server uses Turbopack for faster builds
- **Code Splitting**: Automatic code splitting with Next.js
- **Font Caching**: Aggressive caching for static assets
- **Image Optimization**: Next.js Image component with optimized formats

## Testing

**Note**: The codebase currently does not have a testing framework configured. Consider adding Jest/React Testing Library for unit and integration tests.

## Deployment

### Docker

- **Multi-stage build**: Optimized for production with Node.js 22-slim
- **Standalone output**: Uses Next.js standalone mode for smaller images
- **Non-root user**: Security-focused with dedicated nextjs user
- **Port**: Exposes port 3015 by default

### Environment Variables

Build-time and runtime variables are injected via Docker build args. See Dockerfile for the complete list.

## Common Development Tasks

### Adding New API Endpoints

1. Create API client module in `/src/lib/api/`
2. Use the base client with proper error handling
3. Add TanStack Query hooks in components
4. Update TypeScript types as needed

### Creating New Components

1. Use shadcn/ui patterns when applicable
2. Place in appropriate directory under `/src/components/`
3. Follow established naming conventions
4. Use `cn()` utility for class merging

### State Management

1. Use Zustand for complex shared state
2. Follow existing store patterns in `/src/stores/`
3. Keep stores focused and minimal
4. Use TypeScript for type safety

### Styling

1. Use Tailwind CSS v4 with the established design system
2. Follow shadcn/ui component patterns
3. Use the `cn()` utility for conditional classes
4. Maintain consistency with existing UI patterns

## Key Files to Understand

- `next.config.ts` - Next.js configuration with optimizations
- `src/lib/api-client.ts` - HTTP client configuration
- `src/lib/supabase/` - Authentication setup
- `src/stores/` - State management patterns
- `src/components/ui/` - Component library examples
- `Dockerfile` - Deployment configuration