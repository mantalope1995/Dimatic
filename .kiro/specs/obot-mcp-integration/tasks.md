# Implementation Plan

- [ ] 1. Set up Obot sidecar infrastructure
  - [ ] 1.1 Add Obot service to docker-compose.yaml
    - Add obot container (ghcr.io/obot-platform/obot:latest) with environment variables
    - Configure OBOT_SERVER_ENABLE_AUTHENTICATION, OBOT_BOOTSTRAP_TOKEN, OBOT_SERVER_DSN
    - Mount Docker socket for MCP server containers (/var/run/docker.sock)
    - Set up internal networking (obot:8080 accessible from backend)
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ] 1.2 Create Supabase migration for Obot tables
    - Create `obot_user_mappings` table with suna_user_id, obot_user_id, encrypted_token fields
    - Create `obot_profiles` table with obot_server_id, catalog_entry_id, status fields
    - Create `obot_audit_logs` table with user_id, action, server_id, tool_name, success fields
    - Add indexes and foreign key constraints to auth.users
    - Add update timestamp triggers
    - Enable Row Level Security on all tables
    - Add RLS policy "Users can only access own profiles" on obot_profiles
    - Add RLS policy "Users can only access own mapping" on obot_user_mappings
    - _Requirements: 7.1, 7.2, 8.1_
  - [x] 1.3 Add Obot configuration to backend environment
    - Add OBOT_BASE_URL (default: http://obot.dimatic.com.au:8080/api), OBOT_BOOTSTRAP_TOKEN, OBOT_ENABLED to .env.example
    - Add OBOT_TOKEN_ENCRYPTION_KEY (32-byte base64 key for Fernet encryption)
    - Create backend/core/obot/__init__.py module structure
    - Add obot config loading to backend/core/suna_config.py
    - _Requirements: 1.3, 9.1_

- [x] 2. Implement Obot client and identity service
  - [x] 2.1 Create ObotClient class (`backend/core/obot/client.py`)
    - Implement async httpx client with base_url and bootstrap_token
    - Add _request() helper with Authorization header injection
    - Implement check_health() - GET /api/version
    - Handle HTTP errors and timeouts gracefully
    - _Requirements: 1.4, 3.1_
  - [x] 2.2 Write property test for ObotClient configuration parsing
    - **Property 7: Environment Configuration Parsing** ✅ test_client.py, test_client_properties.py
    - **Validates: Requirements 1.3**
  - [x] 2.3 Implement catalog entry methods in ObotClient
    - list_catalog_entries() - GET /api/all-mcps/entries (returns MCPServerCatalogEntryList)
    - get_catalog_entry() - GET /api/all-mcps/entries/{entry_id} (returns MCPServerCatalogEntry)
    - Map Obot types (MCPServerCatalogEntry, MCPServerCatalogEntryManifest) to Pydantic models
    - _Requirements: 3.1_
  - [x] 2.4 Implement MCP server methods in ObotClient
    - list_mcp_servers() - GET /api/mcp-servers (returns MCPServerList)
    - create_mcp_server() - POST /api/mcp-servers (body: catalogEntryID, alias, env)
    - get_mcp_server() - GET /api/mcp-servers/{mcp_server_id}
    - update_mcp_server() - PUT /api/mcp-servers/{mcp_server_id}
    - delete_mcp_server() - DELETE /api/mcp-servers/{mcp_server_id}
    - Map Obot MCPServer type with manifest, configured, missingRequiredEnvVars fields
    - _Requirements: 3.2, 4.2, 4.3_
  - [x] 2.5 Implement MCP tools methods in ObotClient
    - list_tools() - GET /api/mcp-servers/{mcp_server_id}/tools (returns MCPServerTool[])
    - set_tools() - PUT /api/mcp-servers/{mcp_server_id}/tools (body: tool names array)
    - Map MCPServerTool with name, description, params, enabled fields
    - _Requirements: 3.3, 6.1_
  - [x] 2.6 Implement OAuth and lifecycle methods in ObotClient
    - launch_server() - POST /api/mcp-servers/{mcp_server_id}/launch
    - check_oauth() - POST /api/mcp-servers/{mcp_server_id}/check-oauth
    - get_oauth_url() - POST /api/mcp-servers/{mcp_server_id}/oauth-url
    - configure_credentials() - POST /api/mcp-servers/{mcp_server_id}/configure (body: env vars)
    - deconfigure_credentials() - POST /api/mcp-servers/{mcp_server_id}/deconfigure
    - _Requirements: 3.5, 4.4_
  - [x] 2.7 Create TokenEncryption utility (`backend/core/obot/encryption.py`)
    - Implement Fernet-based encryption using OBOT_TOKEN_ENCRYPTION_KEY
    - Add encrypt() and decrypt() methods for token storage
    - Handle key rotation gracefully (try new key, fallback to old)
    - _Requirements: 8.2, 9.2_
  - [x] 2.8 Write property test for token encryption round-trip
    - **Property 9: Token Encryption Round-Trip** ✅ test_encryption.py
    - **Validates: Requirements 8.2, 9.2**
  - [x] 2.9 Create ObotIdentityService class (`backend/core/obot/identity_service.py`)
    - Implement get_or_create_obot_user() - lookup in obot_user_mappings, create if not exists
    - Generate deterministic obot_username from suna_user_id (format: suna_{hash[:12]})
    - Implement get_obot_token() with encrypted token caching in database
    - Implement automatic token refresh when tokens expire
    - Implement delete_obot_user() for cleanup on Suna user deletion (revoke tokens)
    - _Requirements: 2.1, 2.2, 2.4, 9.2, 9.3, 9.4_
  - [x] 2.10 Write property test for user identity mapping
    - **Property 1: User Identity Mapping Consistency** ✅ test_security.py
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [x] 2.11 Write property test for JWT token generation
    - **Property 2: JWT Token Validity** ✅ test_security.py
    - **Validates: Requirements 2.5**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Obot profile service
  - [x] 4.1 Create ObotProfileService class (`backend/core/obot/profile_service.py`)
    - Implement create_profile() with Supabase insert
    - Implement get_profiles() with account filtering
    - Implement get_profile() with ownership check
    - Implement delete_profile() with cascade to Obot
    - Implement update_profile_status() for status sync
    - _Requirements: 4.1, 4.2, 4.3, 7.2, 7.3_
  - [x] 4.2 Write property test for profile query compatibility
    - **Property 8: Profile Query Compatibility** ✅ test_profile_service_properties.py
    - **Validates: Requirements 7.3**

- [x] 5. Implement security infrastructure
  - [x] 5.1 Create MCPAuditLog service (`backend/core/obot/audit.py`)
    - Implement record() method to log MCP operations to obot_audit_logs
    - Capture user_id, action, server_id, tool_name, success, error_message
    - Capture request metadata (ip_address, user_agent) from request context
    - _Requirements: 8.4_
  - [x] 5.2 Write property test for audit log completeness
    - **Property 11: Audit Log Completeness** ✅ test_audit.py
    - **Validates: Requirements 8.4**
  - [x] 5.3 Create ObotRateLimiter service (`backend/core/obot/rate_limiter.py`)
    - Implement sliding window rate limiting using Redis
    - Configure limits: catalog (100/min), server ops (10/min), tool calls (60/min), oauth (5/min)
    - Return 429 Too Many Requests when limit exceeded
    - _Requirements: 8.5_
  - [x] 5.4 Write property test for rate limit enforcement
    - **Property 12: Rate Limit Enforcement** ✅ test_rate_limiter.py
    - **Validates: Requirements 8.5**
  - [x] 5.5 Create user context validation middleware
    - Implement validate_user_context() to ensure user_id from JWT matches request context
    - Reject requests where authenticated user doesn't match requested resource owner
    - _Requirements: 8.3_
  - [x] 5.6 Write property test for tenant isolation
    - **Property 10: Tenant Isolation Enforcement** ✅ test_security.py
    - **Validates: Requirements 8.1, 8.3**

- [x] 6. Implement Obot integration API
  - [x] 6.1 Create API router (`backend/core/obot/api.py`)
    - Set up FastAPI router with /obot prefix and tags=["obot"]
    - Add verify_and_get_user_id_from_jwt dependency for authentication
    - Initialize ObotClient and ObotIdentityService
    - _Requirements: 3.1_
  - [x] 6.2 Implement catalog endpoints
    - GET /obot/catalog - List MCPServerCatalogEntry items, transform to Suna format
    - GET /obot/catalog/{entry_id} - Get entry with manifest details (name, description, icon, runtime, env)
    - Return runtime type (uvx, npx, containerized, remote, composite) and required env vars
    - Apply rate limiting (100/min for catalog queries)
    - _Requirements: 3.1, 8.5_
  - [x] 6.3 Write property test for response format transformation
    - **Property 3: Response Format Transformation** ✅ test_api_property.py
    - **Validates: Requirements 3.1, 4.1, 6.4**
  - [x] 6.4 Implement server management endpoints
    - POST /obot/servers - Create MCPServer from catalogEntryID, store profile in obot_profiles
    - GET /obot/servers - List user's servers, join with obot_profiles for display names
    - GET /obot/servers/{server_id} - Get server with configured status, missingRequiredEnvVars
    - DELETE /obot/servers/{server_id} - Delete from Obot and obot_profiles, revoke credentials
    - Apply rate limiting (10/min for server operations)
    - Record audit logs for create/delete operations
    - _Requirements: 3.2, 4.2, 4.3, 8.4, 8.5, 9.3_
  - [x] 6.5 Write property test for user context preservation
    - **Property 4: User Context Preservation** ✅ test_api_property.py
    - **Validates: Requirements 3.2, 3.4, 6.1, 6.2**
  - [x] 6.6 Implement tool endpoints
    - GET /obot/servers/{server_id}/tools - List MCPServerTool items with name, description, enabled
    - PUT /obot/servers/{server_id}/tools - Set enabled tools (array of tool names)
    - POST /obot/servers/{server_id}/tools/{tool_name}/call - Execute tool (body: arguments dict)
    - Apply rate limiting (60/min for tool calls)
    - Record audit logs for tool executions
    - _Requirements: 3.3, 6.1, 6.2, 8.4, 8.5_
  - [x] 6.7 Implement OAuth and credentials endpoints
    - GET /obot/servers/{server_id}/oauth-url - Get OAuth authorization URL
    - POST /obot/servers/{server_id}/configure - Set env var credentials
    - POST /obot/servers/{server_id}/launch - Start server and check health
    - GET /obot/servers/{server_id}/status - Get configured, missingRequiredEnvVars, deploymentStatus
    - Apply rate limiting (5/min for OAuth initiations)
    - Record audit logs for OAuth operations
    - _Requirements: 3.5, 4.4, 8.4, 8.5_
  - [x] 6.8 Write property test for connection status accuracy
    - **Property 6: Connection Status Accuracy** ✅ test_connection_status.py
    - **Validates: Requirements 4.4**
  - [x] 6.9 Implement health endpoint
    - GET /obot/health - Check Obot /api/version endpoint, return healthy/unhealthy
    - _Requirements: 1.4, 1.5_
  - [x] 6.10 Register router in main API
    - Import obot router in backend/core/api.py
    - Add router with prefix, conditionally based on OBOT_ENABLED config
    - Inject rate limiter and audit log dependencies
    - _Requirements: 3.1_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement MCP tool wrapper for agent framework
  - [x] 8.1 Create ObotMCPToolWrapper class (`backend/core/tools/obot_mcp_tool.py`)
    - Extend agentpress Tool base class
    - Map MCPServerTool to Tool interface (name, description, parameters from input_schema)
    - Implement execute() - call Obot tool endpoint with user token
    - Return ToolResult with content from Obot response
    - Handle 401/403 errors with re-auth indication (oauth_required flag)
    - Record audit log for each tool execution
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 8.4_
  - [x] 8.2 Create tool factory function
    - Implement create_obot_tools(obot_client, server_id, user_id) -> List[Tool]
    - Fetch tools from Obot, filter by enabled=True
    - Cache tool definitions per server_id with TTL
    - _Requirements: 6.1_
  - [x] 8.3 Integrate with agent tool registry
    - Update backend/core/tools/tool_registry.py to register Obot tools
    - Add load_obot_tools() in agent_setup.py for agents with Obot profiles
    - Pass user context through tool execution chain
    - _Requirements: 6.1, 6.2_
  - [x] 8.4 Write unit tests for tool wrapper
    - Test tool execution with mocked Obot client ✅ test_obot_mcp_tool.py
    - Test error handling for auth failures (401 -> oauth_required)
    - Test response format conversion (Obot result -> ToolResult)
    - _Requirements: 6.3, 6.4_

- [x] 9. Implement admin access proxy
  - [x] 9.1 Create admin proxy endpoint
    - Add /admin/obot/* proxy route for Admin GUI access
    - Implement admin role verification
    - Record audit logs for admin operations
    - _Requirements: 5.1, 5.2, 5.3, 8.4_
  - [x] 9.2 Write property test for admin access control
    - **Property 5: Admin Access Control** ✅ test_obot_admin_proxy.py
    - **Validates: Requirements 5.1**
  - [ ] 9.3 Configure Obot Admin GUI access
    - Document admin access URL and authentication flow
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 10. Implement graceful degradation
  - [x] 10.1 Add circuit breaker for Obot client
    - Implement connection failure detection
    - Add retry logic with exponential backoff
    - _Requirements: 1.5_
  - [x] 10.2 Implement fallback behavior
    - Return appropriate errors when Obot unavailable
    - Log failures for monitoring
    - _Requirements: 1.5_
  - [x] 10.3 Write unit tests for error handling
    - Test Obot unavailability scenarios ✅ test_client_resilience.py
    - Test graceful degradation behavior
    - _Requirements: 1.5_

- [ ] 11. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Property Test Summary

| Property | Description | Status | Test File |
|----------|-------------|--------|-----------|
| Property 1 | User Identity Mapping Consistency | ✅ | test_security.py |
| Property 2 | JWT Token Validity | ✅ | test_security.py |
| Property 3 | Response Format Transformation | ✅ | test_api_property.py |
| Property 4 | User Context Preservation | ✅ | test_api_property.py |
| Property 5 | Admin Access Control | ✅ | test_obot_admin_proxy.py |
| Property 6 | Connection Status Accuracy | ✅ | test_connection_status.py |
| Property 7 | Environment Configuration Parsing | ✅ | test_client.py, test_client_properties.py |
| Property 8 | Profile Query Compatibility | ✅ | test_profile_service_properties.py |
| Property 9 | Token Encryption Round-Trip | ✅ | test_encryption.py |
| Property 10 | Tenant Isolation Enforcement | ✅ | test_security.py |
| Property 11 | Audit Log Completeness | ✅ | test_audit.py |
| Property 12 | Rate Limit Enforcement | ✅ | test_rate_limiter.py |
