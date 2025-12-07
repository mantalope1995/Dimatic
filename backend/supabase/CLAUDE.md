# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Directory Purpose

This is the **Supabase database configuration and migrations directory** for the Suna AI platform (formerly Dimatic/Kortix). It contains all database schema definitions, migrations, and Supabase-specific configuration.

## Development Commands

### Supabase Local Development
```bash
# Start local Supabase services (database, API, etc.)
supabase start

# Stop local Supabase services
supabase stop

# Reset local database (destructive - all data lost)
supabase db reset

# Run database migrations
supabase db push

# Generate TypeScript types from database schema
supabase gen types typescript --local > types.ts

# View database logs
supabase logs db

# Access database shell
supabase db shell
```

### Migration Management
```bash
# Create new migration
supabase migration new new_migration_name

# Check migration status
supabase migration list

# Apply specific migration (not usually needed - db push handles this)
supabase migration apply 20240414161707_basejump-setup.sql
```

### Database Schema Management
```bash
# View current schema
supabase db describe

# Export schema to SQL
supabase db describe --format=sql > schema.sql

# Create database diff (for schema changes)
supabase db diff --schema public --use-migra
```

## High-Level Architecture

### Database Schema Structure

The database is organized around several key systems:

1. **Basejump Foundation** (migrations starting with `basejump-`)
   - User accounts and authentication
   - Team invitations and management
   - Billing and subscription infrastructure
   - Base ACL (Access Control Layer) for multi-tenancy

2. **AgentPress Core** (migrations starting with `agentpress_`)
   - **Projects**: User workspaces containing AI agents
   - **Threads**: Conversation threads between users and agents
   - **Messages**: Individual messages within threads (supports multiple content types)
   - Metadata system for flexible data storage

3. **Agent System** (agent-related migrations)
   - **Agents**: AI agent definitions and configurations
   - **Agent Versioning**: Version control for agent configurations
   - **Agent Marketplace**: Public agent sharing and discovery
   - Secure credential storage for external integrations

4. **Workflow System** (workflow migrations)
   - **Workflows**: Multi-step agent processes
   - **Workflow Flows**: Execution flow definitions
   - Integration with agent execution engine

5. **Security & Integration**
   - **MCP (Model Context Protocol)**: Secure external tool integration
   - **Credential Profiles**: Reusable credential management
   - Encrypted storage for sensitive data (API keys, tokens)
   - Row Level Security (RLS) policies for data isolation

### Key Configuration Files

- **`config.toml`**: Supabase local development configuration
  - Project ID: `agentpress`
  - API port: `54321`
  - Database port: `54322`
  - Enabled schemas: `public`, `graphql_public`, `basejump`

- **`email-template.html`**: Transactional email template
- **`RUN_VIA_PSQL_index_optimisations.sql`**: Database performance optimizations
- **`emails/`**: Directory for email template assets

### Migration Naming Convention

Migrations follow a timestamp naming pattern: `YYYYMMDDHHMMSS_description.sql`

- **Basejump migrations**: Core infrastructure (accounts, billing, invitations)
- **AgentPress migrations**: Core application schema (projects, threads, messages)
- **Feature migrations**: Specific features (agents, workflows, marketplace)
- **Fix migrations**: Schema corrections and optimizations

### Database Features

1. **Multi-tenancy**: Row Level Security isolates data by account
2. **Encrypted Storage**: Sensitive data (API keys, credentials) stored encrypted
3. **JSONB Support**: Flexible metadata and configuration storage
4. **UUID Primary Keys**: Distributed-friendly ID system
5. **Audit Trails**: `created_at`/`updated_at` timestamps on all tables
6. **Soft Deletes**: Logical deletion where appropriate for data recovery

### Integration Points

- **Backend API**: Database accessed via `core/services/supabase.py`
- **Authentication**: Supabase Auth handles user management
- **Realtime**: Supabase Realtime for live updates
- **Storage**: Supabase Storage for file management
- **Edge Functions**: Server-side business logic near database

### Development Workflow

1. **Schema Changes**:
   - Create migration: `supabase migration new describe_change`
   - Write SQL migration with proper up/down behavior
   - Test locally with `supabase db reset`
   - Generate TypeScript types if needed

2. **Testing**:
   - Reset database: `supabase db reset`
   - Apply migrations: `supabase db push`
   - Run backend tests that connect to local database

3. **Security**:
   - Always add Row Level Security policies for new tables
   - Use encrypted storage for sensitive data
   - Test with different user contexts

### Important Notes

- **Required Environment**: Supabase CLI must be installed locally
- **Database Version**: PostgreSQL 15 (configured in config.toml)
- **Local Development**: Uses Docker containers for database services
- **Migration Dependencies**: Some migrations depend on Basejump foundation tables
- **Data Loss Warning**: `supabase db reset` destroys all local data

### Common Operations

- **Add new table**: Create migration with table definition and RLS policies
- **Add column**: Create migration with ALTER TABLE statement
- **Update RLS policy**: Create migration to DROP and CREATE policy
- **Performance optimization**: Add indexes via dedicated migration
- **Credential management**: Use encrypted credential tables for API keys