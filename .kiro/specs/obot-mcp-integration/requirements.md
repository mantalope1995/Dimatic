# Requirements Document

## Introduction

This document specifies the requirements for replacing Composio (a managed MCP integration service) with Obot as a self-hosted MCP Gateway sidecar for the Suna AI agent platform. Obot provides enterprise-grade MCP server management, including server discovery, authentication, credential management, and access control. The integration will enable Suna users to connect to MCP servers through Obot while maintaining their existing identity and authentication context.

The key challenge is mapping Suna's Supabase-based user identity system to Obot's internal user management, ensuring that each Suna user is recognized as a unique user within Obot for proper credential isolation and access control.

## Glossary

- **Suna**: The AI agent platform (Kortix) that currently uses Composio for MCP integrations
- **Obot**: An open-source MCP Gateway and management platform that will replace Composio
- **MCP (Model Context Protocol)**: An industry standard protocol for connecting AI applications to external systems and data
- **MCP Server**: A service that exposes tools and resources via the MCP protocol
- **MCP Gateway**: A proxy layer that manages authentication, access control, and routing for MCP servers
- **Composio**: A managed MCP integration service (not used in this implementation)
- **Supabase**: The database and authentication service used by Suna
- **Sidecar**: A deployment pattern where Obot runs alongside Suna as a companion service
- **User Identity Mapping**: The process of associating a Suna user with a corresponding Obot user
- **OAuth 2.1**: The authentication protocol used by Obot for external service integrations
- **Admin GUI**: Obot's administrative interface for managing MCP servers and configurations
- **Profile**: A Suna concept representing a user's configured connection to an MCP server
- **RLS (Row Level Security)**: A Supabase/PostgreSQL feature that restricts database row access based on user identity
- **Tenant Isolation**: The security principle ensuring one user cannot access another user's data
- **Audit Log**: A record of security-relevant operations for compliance and debugging

## Requirements

### Requirement 1

**User Story:** As a Suna platform operator, I want to deploy Obot as a sidecar service, so that I can provide self-hosted MCP gateway capabilities without relying on external managed services.

#### Acceptance Criteria

1. WHEN the Suna platform starts THEN the Obot sidecar SHALL be available at a configurable internal endpoint
2. WHEN Obot is deployed THEN the system SHALL disable Obot's built-in chat interface and expose only the Admin GUI and MCP Gateway endpoints
3. WHEN configuring Obot THEN the system SHALL support environment-based configuration for database, authentication, and model provider settings
4. WHEN Obot starts THEN the system SHALL perform health checks and report readiness status to Suna
5. IF Obot becomes unavailable THEN the system SHALL log the failure and gracefully degrade MCP functionality

### Requirement 2

**User Story:** As a Suna user, I want my identity to be automatically recognized by Obot, so that I can access MCP servers with proper credential isolation without creating a separate Obot account.

#### Acceptance Criteria

1. WHEN a Suna user makes an MCP request THEN the system SHALL map the Suna user ID to a corresponding Obot user identity
2. WHEN a new Suna user first accesses MCP functionality THEN the system SHALL create or retrieve the corresponding Obot user record
3. WHEN mapping user identities THEN the system SHALL use a deterministic mapping function that produces consistent Obot user IDs for the same Suna user
4. WHEN a Suna user is deleted THEN the system SHALL provide a mechanism to clean up the corresponding Obot user data
5. WHEN authenticating with Obot THEN the system SHALL use JWT tokens signed with a shared secret or public key infrastructure

### Requirement 3

**User Story:** As a Suna backend developer, I want to replace Composio API calls with Obot API calls, so that the existing MCP integration functionality continues to work with the new backend.

#### Acceptance Criteria

1. WHEN listing available MCP servers THEN the system SHALL query Obot's catalog API and return results in a format compatible with the existing Suna frontend
2. WHEN a user connects to an MCP server THEN the system SHALL create the appropriate Obot MCP server instance with user-scoped credentials
3. WHEN discovering tools from an MCP server THEN the system SHALL proxy the request through Obot's MCP Gateway
4. WHEN executing MCP tools THEN the system SHALL route requests through Obot with proper user context
5. WHEN an MCP server requires OAuth authentication THEN the system SHALL redirect the user through Obot's OAuth flow and store credentials in Obot

### Requirement 4

**User Story:** As a Suna user, I want to manage my MCP server connections through the existing Suna interface, so that I do not need to learn a new admin interface for basic operations.

#### Acceptance Criteria

1. WHEN a user views their connected integrations THEN the system SHALL display MCP servers from Obot using the existing Suna profile UI
2. WHEN a user initiates a new MCP connection THEN the system SHALL create the connection through Obot's API and store a reference in Suna's profile system
3. WHEN a user disconnects an MCP server THEN the system SHALL remove the connection from both Obot and Suna's profile storage
4. WHEN displaying connection status THEN the system SHALL query Obot for real-time authentication and health status

### Requirement 5

**User Story:** As a Suna platform administrator, I want to access Obot's Admin GUI, so that I can manage the MCP server catalog, configure authentication providers, and monitor usage.

#### Acceptance Criteria

1. WHEN an admin accesses the Obot Admin GUI THEN the system SHALL authenticate the admin using Suna's admin role verification
2. WHEN configuring MCP server catalogs THEN the admin SHALL be able to add, remove, and configure available MCP servers
3. WHEN managing OAuth providers THEN the admin SHALL be able to configure client credentials for external services
4. WHEN viewing usage analytics THEN the admin SHALL see aggregated MCP usage statistics across all Suna users

### Requirement 6

**User Story:** As a Suna agent, I want to call MCP tools during conversation execution, so that I can perform actions on external services on behalf of the user.

#### Acceptance Criteria

1. WHEN an agent needs to call an MCP tool THEN the system SHALL resolve the tool through Obot's MCP Gateway with the user's credentials
2. WHEN executing a tool call THEN the system SHALL pass the user's Obot identity for proper credential lookup
3. WHEN a tool call fails due to authentication THEN the system SHALL return an appropriate error indicating re-authentication is required
4. WHEN a tool call succeeds THEN the system SHALL return the result in the format expected by Suna's agent framework

### Requirement 7

**User Story:** As a Suna platform operator, I want Obot to integrate with Suna's existing database schema, so that user mappings and configuration are stored consistently.

#### Acceptance Criteria

1. WHEN storing user identity mappings THEN the system SHALL use Suna's Supabase database with appropriate foreign key relationships
2. WHEN storing MCP profile references THEN the system SHALL extend the existing composio_profiles table or create a compatible obot_profiles table
3. WHEN querying profile data THEN the system SHALL support the same query patterns used by the existing Composio integration
4. WHEN Obot stores its own data THEN the system SHALL use a separate database or schema to avoid conflicts with Suna's data

### Requirement 8

**User Story:** As a Suna platform operator, I want proper tenant isolation and data privacy controls, so that users cannot access other users' MCP credentials or configurations.

#### Acceptance Criteria

1. WHEN storing Obot-related data in Supabase THEN the system SHALL enforce Row Level Security policies that restrict access to the owning user
2. WHEN caching Obot tokens in the database THEN the system SHALL encrypt tokens at rest using application-level encryption
3. WHEN making Obot API requests THEN the system SHALL validate user context server-side and reject requests with mismatched user identities
4. WHEN a user performs MCP operations THEN the system SHALL record an audit log entry with user ID, operation type, and timestamp
5. WHEN users make MCP API requests THEN the system SHALL enforce rate limits per user to prevent abuse

### Requirement 9

**User Story:** As a Suna platform operator, I want secure credential management, so that sensitive tokens and secrets are protected throughout their lifecycle.

#### Acceptance Criteria

1. WHEN storing the Obot bootstrap token THEN the system SHALL load the token from environment variables and restrict access to backend services only
2. WHEN generating user-scoped Obot tokens THEN the system SHALL use short-lived tokens with automatic refresh
3. WHEN a user disconnects an MCP server THEN the system SHALL revoke associated credentials in Obot and remove cached tokens from Suna
4. WHEN Obot tokens expire THEN the system SHALL automatically refresh tokens without user intervention

