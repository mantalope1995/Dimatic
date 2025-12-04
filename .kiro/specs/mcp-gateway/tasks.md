# Implementation Plan

## Overview

This implementation plan breaks down the MCP Gateway development into incremental, testable steps. Each task builds on previous work and includes specific requirements references. The plan follows an implementation-first approach with property-based tests integrated throughout.

## Task List

- [ ] 1. Set up project structure and AWS infrastructure foundation
  - Create Python project structure for Gateway Lambda and MCP Server Lambda
  - Set up AWS CDK infrastructure code for DynamoDB tables, KMS key, API Gateway
  - Configure development environment with LocalStack for local testing
  - Set up pytest with Hypothesis for property-based testing
  - _Requirements: All (foundation for entire system)_

- [ ] 2. Implement KMS encryption service with encryption context
  - [ ] 2.1 Create KMS encryption/decryption wrapper
    - Implement encrypt() method with encryption context support
    - Implement decrypt() method with encryption context validation
    - Handle KMS errors and throttling with exponential backoff
    - _Requirements: 1.3, 8.1_
  
  - [ ] 2.2 Write property test for encryption context isolation
    - **Property 29: Tenant-specific KMS key usage**
    - **Validates: Requirements 8.1**
  
  - [ ] 2.3 Write property test for encryption round-trip
    - Test that encrypt then decrypt returns original data
    - Test with various encryption contexts
    - _Requirements: 1.3, 8.1_

- [ ] 3. Implement DynamoDB data access layer
  - [ ] 3.1 Create DynamoDB table schemas and indexes
    - Define ConnectedAccounts table with GSIs
    - Define AuthConfigs table
    - Define MCPServers table
    - _Requirements: 2.1, 3.1_
  
  - [ ] 3.2 Implement ConnectedAccount repository
    - Create, read, update, delete operations
    - List by account_id and user_id
    - Conditional writes for distributed locking
    - _Requirements: 2.1, 3.1, 3.2_
  
  - [ ] 3.3 Implement AuthConfig repository
    - Create, read, update, delete operations
    - List by account_id
    - _Requirements: 9.1, 9.2_
  
  - [ ] 3.4 Implement MCPServer repository
    - Create, read, update, delete operations
    - List by account_id
    - _Requirements: 4.4_
  
  - [ ] 3.5 Write property test for tenant isolation in queries
    - **Property 8: Tenant filtering for list operations**
    - **Validates: Requirements 2.4, 4.5**
  
  - [ ] 3.6 Write property test for dual-key storage
    - **Property 10: Dual-key storage for connected accounts**
    - **Validates: Requirements 3.1**

- [ ] 4. Implement credential storage and retrieval
  - [ ] 4.1 Create credential encryption service
    - Encrypt OAuth credentials with KMS before DynamoDB storage
    - Decrypt credentials with encryption context validation
    - Handle encryption/decryption errors
    - _Requirements: 1.3, 8.1_
  
  - [ ] 4.2 Implement credential storage in ConnectedAccount
    - Store encrypted credentials in binary column
    - Update credentials during token refresh
    - _Requirements: 1.2, 1.3_
  
  - [ ] 4.3 Implement credential retrieval with validation
    - Validate account_id and user_id before retrieval
    - Decrypt credentials with proper encryption context
    - Return decrypted OAuthCredentials object
    - _Requirements: 3.2, 5.1, 5.2_
  
  - [ ] 4.4 Write property test for credential encryption before storage
    - **Property 2: OAuth token encryption before storage**
    - **Validates: Requirements 1.3**
  
  - [ ] 4.5 Write property test for tenant ownership validation
    - **Property 6: Tenant ownership validation on retrieval**
    - **Validates: Requirements 2.2**
  
  - [ ] 4.6 Write property test for dual-key validation
    - **Property 11: Dual-key validation for credential retrieval**
    - **Validates: Requirements 3.2**

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement OAuth flow initiation
  - [ ] 6.1 Create OAuth URL generator
    - Generate authorization URLs with required parameters
    - Include state parameter for CSRF protection
    - Support custom and managed OAuth apps
    - _Requirements: 1.1, 9.3_
  
  - [ ] 6.2 Implement /oauth/initiate endpoint
    - Create ConnectedAccount with "pending" status
    - Generate OAuth URL
    - Return redirect URL to client
    - _Requirements: 1.1_
  
  - [ ] 6.3 Write property test for OAuth URL uniqueness
    - **Property 1: OAuth URL generation uniqueness**
    - **Validates: Requirements 1.1**
  
  - [ ] 6.4 Write unit tests for OAuth initiation
    - Test with valid service and user
    - Test with missing required fields
    - Test with invalid auth config
    - _Requirements: 1.1_

- [ ] 7. Implement OAuth callback handling
  - [ ] 7.1 Create OAuth token exchange service
    - Exchange authorization code for access/refresh tokens
    - Handle OAuth provider errors
    - Support different OAuth providers (GitHub, Slack, etc.)
    - _Requirements: 1.2_
  
  - [ ] 7.2 Implement /oauth/callback endpoint
    - Validate state parameter
    - Exchange code for tokens
    - Encrypt and store tokens
    - Update ConnectedAccount status to "active"
    - _Requirements: 1.2, 1.3, 1.4_
  
  - [ ] 7.3 Implement OAuth error handling
    - Handle OAuth failures and cancellations
    - Update ConnectedAccount status to "failed"
    - Store error messages
    - _Requirements: 1.5_
  
  - [ ] 7.4 Write property test for OAuth success status
    - **Property 3: OAuth success creates active account**
    - **Validates: Requirements 1.4**
  
  - [ ] 7.5 Write property test for OAuth failure status
    - **Property 4: OAuth failure updates status**
    - **Validates: Requirements 1.5**
  
  - [ ] 7.6 Write unit tests for OAuth callback
    - Test successful OAuth completion
    - Test OAuth cancellation
    - Test invalid authorization code
    - Test state parameter mismatch
    - _Requirements: 1.2, 1.4, 1.5_

- [ ] 8. Implement token refresh logic with distributed locking
  - [ ] 8.1 Create distributed lock service using DynamoDB
    - Acquire lock with conditional write
    - Release lock after refresh
    - Handle lock expiration
    - _Requirements: 6.1, 6.2_
  
  - [ ] 8.2 Implement token refresh service
    - Check if access token is expired
    - Acquire distributed lock
    - Use refresh token to get new access token
    - Update stored credentials
    - Release lock
    - _Requirements: 6.1, 6.2_
  
  - [ ] 8.3 Implement refresh failure handling
    - Update status to "requires_reauth" on failure
    - Return appropriate error message
    - _Requirements: 6.3, 6.5_
  
  - [ ] 8.4 Write property test for automatic token refresh
    - **Property 23: Automatic token refresh on expiration**
    - **Validates: Requirements 6.1**
  
  - [ ] 8.5 Write property test for token storage update
    - **Property 24: Token storage update after refresh**
    - **Validates: Requirements 6.2**
  
  - [ ] 8.6 Write property test for refresh failure status
    - **Property 25: Status update on refresh failure**
    - **Validates: Requirements 6.3**
  
  - [ ] 8.7 Write unit tests for token refresh
    - Test successful refresh
    - Test refresh with invalid refresh token
    - Test concurrent refresh attempts (locking)
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement MCP server management
  - [ ] 10.1 Create MCP server configuration service
    - Generate unique MCP server IDs
    - Create MCP server records in DynamoDB
    - Associate with auth configs
    - _Requirements: 4.1, 4.4_
  
  - [ ] 10.2 Implement JWT token generation for MCP URLs
    - Generate JWT with account_id, user_id, mcp_server_id
    - Set appropriate expiration
    - Sign with secret key
    - _Requirements: 4.2_
  
  - [ ] 10.3 Implement /servers/create endpoint
    - Create MCP server record
    - Generate MCP URL with JWT token
    - Return server details
    - _Requirements: 4.1, 4.2, 4.4_
  
  - [ ] 10.4 Implement /servers/list endpoint
    - List MCP servers for tenant
    - Filter by account_id
    - _Requirements: 4.5_
  
  - [ ] 10.5 Write property test for unique MCP URL generation
    - **Property 16: Unique MCP URL generation**
    - **Validates: Requirements 4.2**
  
  - [ ] 10.6 Write property test for auth config association
    - **Property 18: Auth config association**
    - **Validates: Requirements 4.4**
  
  - [ ] 10.7 Write unit tests for MCP server management
    - Test server creation
    - Test server listing
    - Test with invalid auth configs
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [ ] 11. Implement MCP Server Lambda (multi-tenant)
  - [ ] 11.1 Create JWT validation middleware
    - Verify JWT signature
    - Check expiration
    - Extract claims (account_id, user_id, mcp_server_id)
    - _Requirements: 5.1, 5.3_
  
  - [ ] 11.2 Create toolkit registry and loader
    - Define toolkit interface
    - Implement dynamic toolkit loading
    - Support GitHub, Slack, Gmail toolkits initially
    - _Requirements: 4.1_
  
  - [ ] 11.3 Implement tool invocation handler
    - Validate JWT token
    - Load appropriate toolkit
    - Retrieve and decrypt credentials
    - Execute tool with credentials
    - Handle token refresh if needed
    - Return result
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ] 11.4 Implement /tools/list endpoint
    - Return available tools for MCP server
    - Filter by allowed_tools configuration
    - _Requirements: 4.1_
  
  - [ ] 11.5 Write property test for user-specific credential retrieval
    - **Property 19: User-specific credential retrieval**
    - **Validates: Requirements 5.1**
  
  - [ ] 11.6 Write property test for credential decryption
    - **Property 20: Credential decryption before use**
    - **Validates: Requirements 5.2**
  
  - [ ] 11.7 Write property test for user ownership validation
    - **Property 13: User ownership validation for tool invocation**
    - **Validates: Requirements 3.4**
  
  - [ ] 11.8 Write unit tests for tool invocation
    - Test successful tool execution
    - Test with expired token (triggers refresh)
    - Test with invalid JWT
    - Test with mismatched user_id
    - Test with disconnected account
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 12. Implement connected account management
  - [ ] 12.1 Implement /accounts/list endpoint
    - List connected accounts for user
    - Filter by user_id
    - Return account status and details
    - _Requirements: 10.1_
  
  - [ ] 12.2 Implement /accounts/{id} endpoint
    - Get connected account details
    - Validate user_id ownership
    - _Requirements: 10.4_
  
  - [ ] 12.3 Implement /accounts/{id}/disconnect endpoint
    - Validate user_id ownership
    - Revoke OAuth tokens (if supported by provider)
    - Update status to "disconnected"
    - _Requirements: 10.2, 10.5_
  
  - [ ] 12.4 Write property test for user filtering
    - **Property 12: User filtering for connected account lists**
    - **Validates: Requirements 3.3, 10.1**
  
  - [ ] 12.5 Write property test for user authorization
    - **Property 36: User authorization for disconnect**
    - **Property 38: User authorization for account details**
    - **Validates: Requirements 10.2, 10.4**
  
  - [ ] 12.6 Write property test for disconnected account blocking
    - **Property 39: Disconnected account blocks tool invocations**
    - **Validates: Requirements 10.5**
  
  - [ ] 12.7 Write unit tests for account management
    - Test listing accounts
    - Test getting account details
    - Test disconnecting account
    - Test with wrong user_id
    - _Requirements: 10.1, 10.2, 10.4, 10.5_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Implement auth config management
  - [ ] 14.1 Implement /auth-configs/create endpoint
    - Validate required fields
    - Store OAuth client secrets in Secrets Manager
    - Create auth config record
    - _Requirements: 9.1, 9.2_
  
  - [ ] 14.2 Implement /auth-configs/list endpoint
    - List auth configs for tenant
    - Filter by account_id
    - _Requirements: 9.1_
  
  - [ ] 14.3 Implement auth config update logic
    - Update configuration
    - Ensure existing connections unaffected
    - _Requirements: 9.4_
  
  - [ ] 14.4 Implement auth config deletion logic
    - Soft delete (prevent new connections)
    - Preserve existing connected accounts
    - _Requirements: 9.5_
  
  - [ ] 14.5 Write property test for auth config validation
    - **Property 32: Auth config validation**
    - **Validates: Requirements 9.2**
  
  - [ ] 14.6 Write property test for custom credential usage
    - **Property 33: Custom credential usage**
    - **Validates: Requirements 9.3**
  
  - [ ] 14.7 Write property test for update isolation
    - **Property 34: Update isolation for auth configs**
    - **Validates: Requirements 9.4**
  
  - [ ] 14.8 Write property test for soft deletion
    - **Property 35: Soft deletion for auth configs**
    - **Validates: Requirements 9.5**
  
  - [ ] 14.9 Write unit tests for auth config management
    - Test creating auth config
    - Test with missing required fields
    - Test updating auth config
    - Test deleting auth config
    - _Requirements: 9.1, 9.2, 9.4, 9.5_

- [ ] 15. Implement logging and monitoring
  - [ ] 15.1 Create structured logging service
    - Log all operations with account_id and user_id
    - Ensure credentials are never logged
    - Format logs for CloudWatch Insights
    - _Requirements: 11.1, 11.2_
  
  - [ ] 15.2 Implement audit logging for credential access
    - Log all credential retrievals
    - Include timestamp, actor, account_id, user_id
    - _Requirements: 8.5_
  
  - [ ] 15.3 Implement metrics collection
    - Record tool invocation metrics
    - Track latency, success rate, error types
    - _Requirements: 11.3_
  
  - [ ] 15.4 Implement OAuth flow logging
    - Log OAuth initiation and completion
    - Include user_id and outcome
    - _Requirements: 11.4_
  
  - [ ] 15.5 Write property test for structured logging
    - **Property 40: Structured logging for all operations**
    - **Validates: Requirements 11.1**
  
  - [ ] 15.6 Write property test for credential exposure prevention
    - **Property 41: Error logging without credential exposure**
    - **Validates: Requirements 11.2**
  
  - [ ] 15.7 Write property test for audit logging
    - **Property 31: Audit logging for credential access**
    - **Validates: Requirements 8.5**
  
  - [ ] 15.8 Write unit tests for logging
    - Test that credentials are not in logs
    - Test that required fields are present
    - Test error logging
    - _Requirements: 11.1, 11.2, 8.5_

- [ ] 16. Implement cascade deletion operations
  - [ ] 16.1 Implement tenant deletion cascade
    - Delete all connected accounts for tenant
    - Delete all MCP servers for tenant
    - Delete all auth configs for tenant
    - Delete all credentials from storage
    - _Requirements: 2.5_
  
  - [ ] 16.2 Implement user deletion cascade
    - Delete all connected accounts for user
    - Revoke OAuth tokens
    - Delete credentials
    - _Requirements: 3.5_
  
  - [ ] 16.3 Write property test for tenant cascade deletion
    - **Property 9: Cascade deletion on tenant removal**
    - **Validates: Requirements 2.5**
  
  - [ ] 16.4 Write property test for user cascade deletion
    - **Property 14: Cascade deletion on user removal**
    - **Validates: Requirements 3.5**
  
  - [ ] 16.5 Write property test for secure credential deletion
    - **Property 30: Secure credential deletion**
    - **Validates: Requirements 8.4**
  
  - [ ] 16.6 Write unit tests for cascade deletion
    - Test tenant deletion
    - Test user deletion
    - Verify all related resources removed
    - _Requirements: 2.5, 3.5, 8.4_

- [ ] 17. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Implement Composio API compatibility layer
  - [ ] 18.1 Create response format adapters
    - Map internal models to Composio response format
    - Ensure field names match
    - _Requirements: 12.1, 12.3_
  
  - [ ] 18.2 Create error format adapters
    - Map internal errors to Composio error codes
    - Ensure error structure matches
    - _Requirements: 12.4_
  
  - [ ] 18.3 Implement migration import endpoint
    - Accept Composio connected account format
    - Preserve user_id associations
    - Import credentials
    - _Requirements: 12.2_
  
  - [ ] 18.4 Write property test for API response compatibility
    - **Property 44: Composio API response format compatibility**
    - **Validates: Requirements 12.1, 12.3**
  
  - [ ] 18.5 Write property test for error format compatibility
    - **Property 46: Composio error format compatibility**
    - **Validates: Requirements 12.4**
  
  - [ ] 18.6 Write property test for migration preservation
    - **Property 45: Migration preserves user associations**
    - **Validates: Requirements 12.2**
  
  - [ ] 18.7 Write unit tests for compatibility layer
    - Test response format conversion
    - Test error format conversion
    - Test migration import
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 19. Implement concurrency and isolation testing
  - [ ] 19.1 Write property test for concurrent isolation
    - **Property 28: Isolation under concurrent load**
    - **Validates: Requirements 7.5**
  
  - [ ] 19.2 Write integration tests for concurrent requests
    - Test concurrent OAuth flows
    - Test concurrent tool invocations
    - Test concurrent token refreshes
    - Verify no cross-tenant data leakage
    - _Requirements: 7.5_

- [ ] 20. Implement caching layer
  - [ ] 20.1 Create in-memory cache for auth configs
    - Cache auth configs with TTL
    - Invalidate on update
    - _Requirements: 13.3_
  
  - [ ] 20.2 Create in-memory cache for MCP server configs
    - Cache MCP server records with TTL
    - Invalidate on update
    - _Requirements: 13.3_
  
  - [ ] 20.3 Write property test for cache effectiveness
    - **Property 47: Cache reduces database queries**
    - **Validates: Requirements 13.3**
  
  - [ ] 20.4 Write unit tests for caching
    - Test cache hits reduce DB queries
    - Test cache invalidation
    - Test cache expiration
    - _Requirements: 13.3_

- [ ] 21. Deploy AWS infrastructure with CDK
  - [ ] 21.1 Create CDK stack for DynamoDB tables
    - Define tables with proper indexes
    - Configure on-demand billing
    - Set up encryption at rest
    - _Requirements: 2.1, 3.1_
  
  - [ ] 21.2 Create CDK stack for KMS key
    - Create master KMS key
    - Configure key policy for Lambda access
    - Enable automatic rotation
    - _Requirements: 8.1_
  
  - [ ] 21.3 Create CDK stack for Lambda functions
    - Deploy Gateway Lambda
    - Deploy MCP Server Lambda
    - Configure IAM roles with least privilege
    - _Requirements: 4.1, 5.3_
  
  - [ ] 21.4 Create CDK stack for API Gateway
    - Configure HTTP API
    - Set up JWT authorizer
    - Configure rate limiting
    - _Requirements: 1.1, 5.3_
  
  - [ ] 21.5 Deploy to staging environment
    - Deploy all stacks
    - Verify connectivity
    - Run integration tests
    - _Requirements: All_

- [ ] 22. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 23. Integration testing and documentation
  - [ ] 23.1 Run full integration test suite
    - Test complete OAuth flow
    - Test tool invocation end-to-end
    - Test token refresh
    - Test account management
    - Test migration from Composio
    - _Requirements: All_
  
  - [ ] 23.2 Create API documentation
    - Document all endpoints
    - Provide example requests/responses
    - Document error codes
    - _Requirements: 12.1_
  
  - [ ] 23.3 Create deployment guide
    - Document AWS setup
    - Document environment variables
    - Document OAuth app configuration
    - _Requirements: All_
  
  - [ ] 23.4 Create migration guide
    - Document migration from Composio
    - Provide migration scripts
    - Document rollback procedures
    - _Requirements: 12.2_
