is t# Design Document

## Overview

The Multi-Tenant MCP Gateway is a serverless system built on AWS that manages OAuth authentication, credential storage, and MCP server deployments for third-party service integrations. It replaces Composio's managed service with a self-hosted solution that provides 1-click OAuth flows, secure credential management, and scalable tool invocation.

The system uses AWS Lambda for compute, DynamoDB for data storage, API Gateway for HTTP endpoints, KMS for encryption, and Secrets Manager for credential storage. It maintains strict tenant and user-level isolation while providing a compatible API interface with the existing Composio integration.

### Critical Design Considerations

**1. MCP Server Lambda Deployment Complexity:**
The current design proposes dynamically creating Lambda functions for each MCP server deployment. This introduces significant complexity:
- Lambda deployment requires packaging code, managing dependencies, and handling versioning
- Each toolkit (GitHub, Slack, etc.) needs different code and dependencies
- Cold starts will be significant for infrequently used toolkits
- Managing hundreds of Lambda functions per tenant is operationally complex

**Alternative Approach:** Use a single multi-tenant MCP Server Lambda that dynamically loads toolkit implementations based on configuration. This reduces operational complexity while maintaining isolation through runtime validation.

**2. Secrets Manager vs DynamoDB for Credentials:**
The design uses Secrets Manager for credential storage, which adds cost and latency:
- Secrets Manager charges per secret per month ($0.40/secret)
- Additional API call costs ($0.05 per 10,000 calls)
- Higher latency compared to DynamoDB (100-200ms vs 10-50ms)

**Alternative Approach:** Store encrypted credentials directly in DynamoDB with KMS encryption. This reduces cost and latency while maintaining security. Secrets Manager can be reserved for OAuth client secrets in AuthConfigs.

**3. One KMS Key Per Tenant:**
Creating a KMS key per tenant is expensive and unnecessary:
- KMS keys cost $1/month each
- For 1000 tenants, that's $1000/month just for keys
- KMS key limits (10,000 per region) could become a constraint

**Alternative Approach:** Use a single KMS key with encryption context to ensure tenant isolation. The encryption context includes account_id, preventing cross-tenant decryption even with the same key.

**4. API Gateway Configuration:**
The design doesn't specify whether to use REST API or HTTP API:
- REST API: More features but more expensive ($3.50 per million requests)
- HTTP API: Simpler, cheaper ($1.00 per million requests), sufficient for this use case

**Recommendation:** Use HTTP API for cost optimization.

**5. OAuth Callback URL Management:**
The design doesn't address how OAuth callback URLs are managed when multiple environments exist (dev, staging, prod). Each environment needs different callback URLs registered with OAuth providers.

**Solution:** Include environment identifier in callback URLs and maintain separate OAuth apps per environment in AuthConfigs.

**6. MCP URL Generation:**
The design generates MCP URLs but doesn't specify the format or how they're used by MCP clients. MCP URLs need to include authentication tokens or be protected by API Gateway authorizers.

**Solution:** Generate MCP URLs with embedded JWT tokens that encode account_id, user_id, and mcp_server_id. API Gateway validates these tokens before routing to Lambda.

**7. Tool Discovery:**
The design doesn't address how clients discover which tools are available on an MCP server. MCP protocol requires a tools/list endpoint.

**Solution:** Add tools/list endpoint that returns available tools based on the toolkit and allowed_tools configuration.

**8. Rate Limiting Granularity:**
Rate limiting at tenant and user level is good, but doesn't account for per-service limits (e.g., GitHub API has its own rate limits).

**Solution:** Implement per-service rate limiting and quota tracking to prevent exhausting third-party API limits.

**9. Credential Refresh Race Conditions:**
Multiple concurrent tool invocations with expired tokens could trigger simultaneous refresh attempts, causing race conditions.

**Solution:** Implement distributed locking (using DynamoDB conditional writes) to ensure only one refresh attempt occurs at a time per connected account.

**10. Migration Strategy:**
The design mentions migration from Composio but doesn't detail how existing MCP URLs and connected accounts are migrated without breaking existing integrations.

**Solution:** Implement a compatibility layer that accepts both old Composio URLs and new gateway URLs during a transition period. Provide migration scripts to update stored MCP URLs in the database.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Kortix Backend                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Composio Integration Service (Adapter)           │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└───────────────────────┼─────────────────────────────────────────┘
                        │ HTTPS/REST API
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS MCP Gateway System                       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   API Gateway (REST)                     │  │
│  │  /oauth/initiate  /oauth/callback  /tools/invoke        │  │
│  │  /servers/create  /accounts/list   /accounts/disconnect │  │
│  └────────────┬──────────────────────────┬──────────────────┘  │
│               │                          │                      │
│               ▼                          ▼                      │
│  ┌─────────────────────┐    ┌──────────────────────────────┐  │
│  │  Gateway Lambda     │    │   MCP Server Lambda          │  │
│  │  (Control Plane)    │    │   (Data Plane - per toolkit) │  │
│  │  - OAuth flows      │    │   - Tool execution           │  │
│  │  - Account mgmt     │    │   - Credential injection     │  │
│  │  - Server deploy    │    │   - API calls to services    │  │
│  └──────┬──────────────┘    └──────────┬───────────────────┘  │
│         │                               │                      │
│         ▼                               ▼                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                      DynamoDB Tables                     │  │
│  │  - ConnectedAccounts  - AuthConfigs  - MCPServers       │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              AWS Secrets Manager + KMS                   │  │
│  │  - Encrypted OAuth tokens (per user)                    │  │
│  │  - Tenant-specific KMS keys                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

**OAuth Flow:**
1. User initiates OAuth → API Gateway → Gateway Lambda
2. Gateway Lambda creates ConnectedAccount record (status: "pending")
3. Gateway Lambda generates OAuth URL with state parameter
4. User completes OAuth on provider site
5. Provider redirects to callback → API Gateway → Gateway Lambda
6. Gateway Lambda exchanges code for tokens
7. Gateway Lambda encrypts tokens with KMS and stores in Secrets Manager
8. Gateway Lambda updates ConnectedAccount (status: "active")

**Tool Invocation Flow:**
1. Agent invokes tool → API Gateway → MCP Server Lambda
2. MCP Server Lambda validates account_id + user_id
3. MCP Server Lambda retrieves encrypted credentials from Secrets Manager
4. MCP Server Lambda decrypts credentials with KMS
5. MCP Server Lambda calls third-party API with credentials
6. MCP Server Lambda returns result to agent


## Components and Interfaces

### 1. API Gateway

**Purpose:** HTTP endpoint for all gateway operations

**Endpoints:**
- `POST /oauth/initiate` - Start OAuth flow for a service
- `GET /oauth/callback` - Handle OAuth provider redirects
- `POST /servers/create` - Deploy new MCP server
- `POST /servers/{id}/url` - Generate MCP URL for server
- `GET /servers/list` - List MCP servers for tenant
- `POST /accounts/create` - Create connected account
- `GET /accounts/list` - List connected accounts for user
- `GET /accounts/{id}` - Get connected account details
- `DELETE /accounts/{id}` - Disconnect account
- `POST /tools/invoke` - Invoke tool on MCP server
- `POST /auth-configs/create` - Create auth configuration
- `GET /auth-configs/list` - List auth configurations

**Authentication:** API Gateway validates JWT tokens from Kortix backend containing account_id and user_id claims

**Rate Limiting:** 1000 requests per minute per tenant, 100 requests per minute per user

### 2. Gateway Lambda (Control Plane)

**Purpose:** Manages OAuth flows, account lifecycle, and MCP server deployments

**Responsibilities:**
- OAuth initiation and callback handling
- Token exchange with OAuth providers
- Credential encryption and storage
- Connected account CRUD operations
- MCP server deployment (creates Lambda + API Gateway config)
- Auth config management

**Environment Variables:**
- `DYNAMODB_TABLE_PREFIX` - Prefix for DynamoDB tables
- `KMS_KEY_ALIAS_PREFIX` - Prefix for KMS keys
- `SECRETS_MANAGER_PREFIX` - Prefix for secrets
- `OAUTH_CALLBACK_BASE_URL` - Base URL for OAuth callbacks

**IAM Permissions:**
- DynamoDB: Read/Write on ConnectedAccounts, AuthConfigs, MCPServers tables
- Secrets Manager: CreateSecret, GetSecretValue, UpdateSecret, DeleteSecret
- KMS: Encrypt, Decrypt, GenerateDataKey
- Lambda: CreateFunction, UpdateFunctionCode, DeleteFunction
- API Gateway: CreateRestApi, CreateResource, PutMethod, CreateDeployment
- CloudWatch Logs: CreateLogGroup, PutLogEvents

### 3. MCP Server Lambda (Data Plane) - Revised Architecture

**Purpose:** Multi-tenant Lambda that executes tools for any third-party service toolkit

**Responsibilities:**
- Tool invocation with credential injection
- Token refresh when access tokens expire with distributed locking
- API calls to third-party services
- Result formatting and error handling
- Dynamic toolkit loading based on MCP server configuration

**Architecture Change:**
Instead of deploying separate Lambda functions per MCP server, use a single multi-tenant Lambda that:
1. Receives requests with mcp_server_id in the path or JWT token
2. Loads the appropriate toolkit implementation dynamically
3. Validates account_id and user_id from JWT token
4. Retrieves and decrypts credentials with proper encryption context
5. Executes the tool and returns results

**Configuration (environment variables):**
- `DYNAMODB_TABLE_PREFIX` - Prefix for DynamoDB tables
- `KMS_KEY_ID` - KMS key ID for decryption
- `TOOLKIT_REGISTRY_PATH` - Path to toolkit implementations

**Request Format:**
```
POST /mcp/{mcp_server_id}/tools/invoke
Authorization: Bearer <jwt_token>
{
  "tool_name": "create_issue",
  "parameters": {...}
}
```

**JWT Token Claims:**
```json
{
  "account_id": "acc_123",
  "user_id": "user_456",
  "mcp_server_id": "srv_789",
  "connected_account_id": "conn_abc",
  "exp": 1234567890
}
```

**IAM Permissions:**
- DynamoDB: Read on ConnectedAccounts, MCPServers tables
- DynamoDB: Write on ConnectedAccounts (for token refresh)
- KMS: Decrypt with encryption context validation
- CloudWatch Logs: PutLogEvents

**Benefits:**
- Single Lambda to manage and monitor
- Faster cold starts (shared warm instances)
- Simpler deployment and versioning
- Lower operational complexity
- Easier to add new toolkits (just deploy new code, no infrastructure changes)

### 4. DynamoDB Tables

#### ConnectedAccounts Table
```
Partition Key: account_id (String)
Sort Key: connected_account_id (String)

Attributes:
- user_id (String) - User who owns this connection
- auth_config_id (String) - Reference to auth config
- status (String) - "pending", "active", "failed", "requires_reauth", "disconnected"
- service_name (String) - e.g., "github", "slack"
- encrypted_credentials (Binary) - KMS-encrypted OAuth credentials
- redirect_url (String) - OAuth redirect URL (if pending)
- refresh_lock (String) - Distributed lock for token refresh (optional)
- refresh_lock_expires_at (Number) - Lock expiration timestamp
- created_at (Number) - Unix timestamp
- updated_at (Number) - Unix timestamp
- last_used_at (Number) - Unix timestamp

GSI: user_id-index (for listing user's accounts)
  - Partition Key: user_id
  - Sort Key: connected_account_id
  
GSI: auth_config_id-index (for finding accounts by auth config)
  - Partition Key: auth_config_id
  - Sort Key: connected_account_id
```

#### AuthConfigs Table
```
Partition Key: account_id (String)
Sort Key: auth_config_id (String)

Attributes:
- toolkit_slug (String) - e.g., "github", "slack"
- auth_scheme (String) - "OAUTH2", "API_KEY", etc.
- is_custom (Boolean) - true if using custom OAuth app
- oauth_client_id (String) - OAuth client ID (encrypted)
- oauth_client_secret_arn (String) - ARN of secret containing client secret
- scopes (List<String>) - OAuth scopes
- authorization_url (String) - OAuth authorization endpoint
- token_url (String) - OAuth token endpoint
- created_at (Number) - Unix timestamp
- updated_at (Number) - Unix timestamp
```

#### MCPServers Table
```
Partition Key: account_id (String)
Sort Key: mcp_server_id (String)

Attributes:
- name (String) - Server name
- toolkit_name (String) - e.g., "GitHub", "Slack"
- auth_config_ids (List<String>) - Auth configs this server uses
- allowed_tools (List<String>) - Tool names allowed
- lambda_arn (String) - ARN of MCP server Lambda
- api_gateway_id (String) - API Gateway REST API ID
- mcp_url (String) - Base MCP URL
- created_at (Number) - Unix timestamp
- updated_at (Number) - Unix timestamp
```

### 5. Credential Storage (Revised Approach)

**Storage Location:** DynamoDB ConnectedAccounts table (encrypted credentials column)

**Encryption Strategy:**
- Credentials encrypted using AWS KMS with encryption context
- Encryption context includes: `{"account_id": "...", "user_id": "...", "connected_account_id": "..."}`
- Single KMS key shared across all tenants
- Encryption context ensures tenant/user isolation even with shared key

**Credential Structure (before encryption):**
```json
{
  "access_token": "token_value",
  "refresh_token": "refresh_value",
  "token_type": "Bearer",
  "expires_at": 1234567890,
  "scope": "repo user"
}
```

**Benefits of DynamoDB Storage:**
- Lower latency (10-50ms vs 100-200ms for Secrets Manager)
- Lower cost (no per-secret charges)
- Simpler architecture (one less service to manage)
- Atomic updates with conditional writes

**Secrets Manager Usage:**
- Reserved for OAuth client secrets in AuthConfigs
- Stores sensitive configuration that doesn't change frequently
- Provides audit trail for client secret access

### 6. AWS KMS (Revised Approach)

**Key Structure:**
- Single KMS key for the entire gateway: `alias/mcp-gateway-master`
- Tenant isolation achieved through encryption context, not separate keys
- Key policy allows Gateway Lambda and MCP Server Lambda to encrypt/decrypt
- Encryption context MUST include account_id and user_id for all operations

**Encryption Context Example:**
```python
encryption_context = {
    "account_id": "acc_123",
    "user_id": "user_456",
    "connected_account_id": "conn_789",
    "service_name": "github"
}
```

**Security Guarantee:**
- KMS will only decrypt data if the encryption context matches exactly
- Even with access to the key, cannot decrypt another tenant's data without their encryption context
- Provides cryptographic isolation without per-tenant key overhead

**Cost Savings:**
- Single key: $1/month
- 1000 tenants with individual keys: $1000/month
- Savings: $999/month per 1000 tenants

**Key Rotation:** Automatic annual rotation enabled


## Data Models

### ConnectedAccount
```python
@dataclass
class ConnectedAccount:
    account_id: str
    connected_account_id: str
    user_id: str
    auth_config_id: str
    status: Literal["pending", "active", "failed", "requires_reauth", "disconnected"]
    service_name: str
    secret_arn: str
    redirect_url: Optional[str] = None
    created_at: int
    updated_at: int
    last_used_at: Optional[int] = None
```

### AuthConfig
```python
@dataclass
class AuthConfig:
    account_id: str
    auth_config_id: str
    toolkit_slug: str
    auth_scheme: str
    is_custom: bool
    oauth_client_id: Optional[str] = None
    oauth_client_secret_arn: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    authorization_url: Optional[str] = None
    token_url: Optional[str] = None
    created_at: int
    updated_at: int
```

### MCPServer
```python
@dataclass
class MCPServer:
    account_id: str
    mcp_server_id: str
    name: str
    toolkit_name: str
    auth_config_ids: List[str]
    allowed_tools: List[str]
    lambda_arn: str
    api_gateway_id: str
    mcp_url: str
    created_at: int
    updated_at: int
```

### OAuthCredentials
```python
@dataclass
class OAuthCredentials:
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[int] = None
    scope: Optional[str] = None
```

### ToolInvocationRequest
```python
@dataclass
class ToolInvocationRequest:
    account_id: str
    user_id: str
    mcp_server_id: str
    tool_name: str
    parameters: Dict[str, Any]
    connected_account_id: str
```

### ToolInvocationResponse
```python
@dataclass
class ToolInvocationResponse:
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, several properties were identified as redundant or overlapping:
- Properties 3.3 and 10.1 both test user_id filtering for list operations - consolidated into Property 3
- Properties 2.4 and 4.5 both test tenant filtering for list operations - consolidated into Property 2
- Properties 12.1 and 12.3 both test API response format compatibility - consolidated into Property 24
- Several infrastructure properties (7.1-7.4, 8.2-8.3, 11.5, 12.5, 13.1-13.2, 13.4-13.5) cannot be tested via property-based testing

### OAuth Flow Properties

**Property 1: OAuth URL generation uniqueness**
*For any* valid service and user combination, generating an OAuth URL should produce a unique URL containing required OAuth parameters (client_id, redirect_uri, state, scope)
**Validates: Requirements 1.1**

**Property 2: OAuth token encryption before storage**
*For any* OAuth tokens received, the system should encrypt them using KMS before storing them in Secrets Manager
**Validates: Requirements 1.3**

**Property 3: OAuth success creates active account**
*For any* successful OAuth completion, the connected account status should transition to "active"
**Validates: Requirements 1.4**

**Property 4: OAuth failure updates status**
*For any* OAuth failure or cancellation, the connected account status should be "failed" and an error message should be present
**Validates: Requirements 1.5**

### Tenant Isolation Properties

**Property 5: Credential storage partitioning**
*For any* credential storage operation, the data should be partitioned by account_id as the primary key
**Validates: Requirements 2.1**

**Property 6: Tenant ownership validation on retrieval**
*For any* credential retrieval request, if the requesting account_id does not match the credential owner's account_id, the request should be rejected
**Validates: Requirements 2.2**

**Property 7: Tenant ownership validation on tool invocation**
*For any* tool invocation request, the system should verify the account_id matches the credential owner before allowing access
**Validates: Requirements 2.3**

**Property 8: Tenant filtering for list operations**
*For any* list operation (connected accounts, MCP servers, auth configs), all returned results should have an account_id matching the requesting tenant
**Validates: Requirements 2.4, 4.5**

**Property 9: Cascade deletion on tenant removal**
*For any* tenant deletion, all associated credentials, connected accounts, and MCP servers should be removed from storage
**Validates: Requirements 2.5**

### User Isolation Properties

**Property 10: Dual-key storage for connected accounts**
*For any* connected account creation, the record should contain both a non-empty account_id and a non-empty user_id
**Validates: Requirements 3.1**

**Property 11: Dual-key validation for credential retrieval**
*For any* credential retrieval for tool invocation, if either the account_id or user_id does not match the requesting context, the request should be rejected
**Validates: Requirements 3.2**

**Property 12: User filtering for connected account lists**
*For any* user listing their connected accounts, all returned accounts should have a user_id matching the requesting user
**Validates: Requirements 3.3, 10.1**

**Property 13: User ownership validation for tool invocation**
*For any* tool invocation, the user_id in the request should match the user_id of the connected account being used, otherwise the request should be rejected
**Validates: Requirements 3.4**

**Property 14: Cascade deletion on user removal**
*For any* user removal from an account, all of that user's connected accounts should be deleted or revoked
**Validates: Requirements 3.5**

### MCP Server Deployment Properties

**Property 15: Lambda deployment on server creation**
*For any* MCP server creation, a Lambda function should be deployed with configuration matching the specified toolkit
**Validates: Requirements 4.1**

**Property 16: Unique MCP URL generation**
*For any* MCP server creation, the generated MCP URL should be unique and properly formatted
**Validates: Requirements 4.2**

**Property 17: API Gateway route configuration**
*For any* MCP server deployment, API Gateway routes should be configured to route requests to the Lambda function
**Validates: Requirements 4.3**

**Property 18: Auth config association**
*For any* MCP server deployment, the server record should contain the specified auth_config_ids and account_id
**Validates: Requirements 4.4**

### Tool Invocation Properties

**Property 19: User-specific credential retrieval**
*For any* tool invocation, only credentials belonging to the specified user_id should be retrieved
**Validates: Requirements 5.1**

**Property 20: Credential decryption before use**
*For any* credential retrieval, the credentials should be decrypted using KMS before being passed to the MCP server Lambda
**Validates: Requirements 5.2**

**Property 21: Tool execution result return**
*For any* successful tool execution, a result should be returned to the caller
**Validates: Requirements 5.4**

**Property 22: Credential error includes user identification**
*For any* tool invocation failure due to missing or invalid credentials, the error should indicate which user needs to authenticate
**Validates: Requirements 5.5**

### Token Refresh Properties

**Property 23: Automatic token refresh on expiration**
*For any* expired access token during tool invocation, the system should automatically attempt to use the refresh token to obtain a new access token
**Validates: Requirements 6.1**

**Property 24: Token storage update after refresh**
*For any* successful token refresh, the stored credentials should be updated with the new tokens
**Validates: Requirements 6.2**

**Property 25: Status update on refresh failure**
*For any* refresh token that is invalid or expired, the connected account status should be updated to "requires_reauth"
**Validates: Requirements 6.3**

**Property 26: Retry after successful refresh**
*For any* successful token refresh, the original tool invocation should be retried with the new token
**Validates: Requirements 6.4**

**Property 27: Reauth error on refresh failure**
*For any* token refresh failure, the error returned should indicate that re-authentication is required
**Validates: Requirements 6.5**

### Concurrency and Isolation Properties

**Property 28: Isolation under concurrent load**
*For any* set of concurrent requests from different tenants and users, no request should access credentials or data belonging to a different tenant or user
**Validates: Requirements 7.5**

### Security Properties

**Property 29: Tenant-specific KMS key usage**
*For any* credential encryption operation, the system should use the KMS key specific to the tenant's account_id
**Validates: Requirements 8.1**

**Property 30: Secure credential deletion**
*For any* credential deletion operation, the credentials should be removed from all storage locations (Secrets Manager and any caches)
**Validates: Requirements 8.4**

**Property 31: Audit logging for credential access**
*For any* credential access event, an audit log entry should be created containing timestamp, actor information, account_id, and user_id
**Validates: Requirements 8.5**

### Auth Config Properties

**Property 32: Auth config validation**
*For any* auth config creation request, if required fields are missing, the request should be rejected
**Validates: Requirements 9.2**

**Property 33: Custom credential usage**
*For any* auth config marked as custom, OAuth operations should use the provided custom credentials instead of managed defaults
**Validates: Requirements 9.3**

**Property 34: Update isolation for auth configs**
*For any* auth config update, existing connected accounts should remain unchanged and only new connections should use the updated configuration
**Validates: Requirements 9.4**

**Property 35: Soft deletion for auth configs**
*For any* auth config deletion, new connection attempts should fail but existing connected accounts should be preserved
**Validates: Requirements 9.5**

### Account Management Properties

**Property 36: User authorization for disconnect**
*For any* disconnect operation, the system should verify the user_id matches the account owner before revoking tokens and updating status to "disconnected"
**Validates: Requirements 10.2**

**Property 37: User authorization for reconnect**
*For any* reconnect operation, the system should verify user_id ownership before initiating a new OAuth flow
**Validates: Requirements 10.3**

**Property 38: User authorization for account details**
*For any* account detail request, if the user_id does not match the account owner, the request should be rejected
**Validates: Requirements 10.4**

**Property 39: Disconnected account blocks tool invocations**
*For any* connected account with status "disconnected", tool invocation attempts using that account should be rejected
**Validates: Requirements 10.5**

### Logging and Monitoring Properties

**Property 40: Structured logging for all operations**
*For any* gateway operation, a log entry should be created containing structured metadata including account_id and user_id
**Validates: Requirements 11.1**

**Property 41: Error logging without credential exposure**
*For any* error that occurs, the log entry should contain stack traces and context but should not contain any credential values
**Validates: Requirements 11.2**

**Property 42: Metrics recording for tool invocations**
*For any* tool invocation, metrics should be recorded including latency, success/failure status, and error type
**Validates: Requirements 11.3**

**Property 43: OAuth completion logging**
*For any* OAuth flow completion (success or failure), a log entry should be created containing the outcome and user_id
**Validates: Requirements 11.4**

### API Compatibility Properties

**Property 44: Composio API response format compatibility**
*For any* API endpoint call, the response structure should match the format returned by the existing Composio integration
**Validates: Requirements 12.1, 12.3**

**Property 45: Migration preserves user associations**
*For any* connected account imported during migration, the user_id association should be preserved
**Validates: Requirements 12.2**

**Property 46: Composio error format compatibility**
*For any* error response, the error code and structure should match the format used by the existing Composio integration
**Validates: Requirements 12.4**

### Performance Properties

**Property 47: Cache reduces database queries**
*For any* frequently accessed data that is cached, subsequent accesses should not result in additional database queries until the cache expires
**Validates: Requirements 13.3**


## Error Handling

### Error Categories

**Authentication Errors:**
- `OAUTH_INITIATION_FAILED` - Failed to generate OAuth URL
- `OAUTH_EXCHANGE_FAILED` - Failed to exchange authorization code for tokens
- `TOKEN_REFRESH_FAILED` - Failed to refresh expired access token
- `INVALID_CREDENTIALS` - Credentials are invalid or malformed
- `REAUTH_REQUIRED` - User must re-authenticate

**Authorization Errors:**
- `TENANT_MISMATCH` - Requesting account_id does not match resource owner
- `USER_MISMATCH` - Requesting user_id does not match resource owner
- `INSUFFICIENT_PERMISSIONS` - User lacks permission for operation
- `ACCOUNT_DISCONNECTED` - Connected account is disconnected

**Resource Errors:**
- `CONNECTED_ACCOUNT_NOT_FOUND` - Connected account does not exist
- `AUTH_CONFIG_NOT_FOUND` - Auth config does not exist
- `MCP_SERVER_NOT_FOUND` - MCP server does not exist
- `TOOL_NOT_FOUND` - Requested tool does not exist on server

**Validation Errors:**
- `MISSING_REQUIRED_FIELD` - Required field is missing from request
- `INVALID_FIELD_VALUE` - Field value is invalid or malformed
- `INVALID_STATUS_TRANSITION` - Cannot transition from current status

**Infrastructure Errors:**
- `KMS_ENCRYPTION_FAILED` - Failed to encrypt with KMS
- `KMS_DECRYPTION_FAILED` - Failed to decrypt with KMS
- `SECRETS_MANAGER_ERROR` - Failed to access Secrets Manager
- `DYNAMODB_ERROR` - Failed to access DynamoDB
- `LAMBDA_DEPLOYMENT_FAILED` - Failed to deploy Lambda function

### Error Response Format

All errors follow this structure for Composio compatibility:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {
      "account_id": "acc_123",
      "user_id": "user_456",
      "resource_id": "res_789",
      "timestamp": 1234567890
    }
  }
}
```

### Retry Strategy

**Transient Errors (Retry with exponential backoff):**
- KMS throttling errors
- DynamoDB throttling errors
- Secrets Manager throttling errors
- Network timeouts

**Non-Retryable Errors (Fail immediately):**
- Authentication failures
- Authorization failures
- Validation errors
- Resource not found errors

**Token Refresh Retry:**
- On token expiration, attempt refresh once
- If refresh fails, return REAUTH_REQUIRED error
- Do not retry the original operation more than once after refresh


## Testing Strategy

### Dual Testing Approach

The MCP Gateway will use both unit testing and property-based testing to ensure correctness:

**Unit Tests** verify:
- Specific examples of OAuth flows
- Edge cases (empty inputs, malformed data)
- Error conditions and error messages
- Integration points between components
- API endpoint request/response handling

**Property-Based Tests** verify:
- Universal properties that should hold across all inputs
- Security properties (isolation, authorization)
- Data integrity properties (encryption, storage)
- Behavioral properties (state transitions, cascading operations)

Together they provide comprehensive coverage: unit tests catch concrete bugs, property tests verify general correctness.

### Property-Based Testing Framework

**Framework:** Hypothesis (Python)
- Minimum 100 iterations per property test
- Custom generators for domain objects (ConnectedAccount, AuthConfig, etc.)
- Stateful testing for complex workflows (OAuth flow, token refresh)

**Test Tagging Convention:**
Each property-based test must include a comment with this exact format:
```python
# Feature: mcp-gateway, Property {number}: {property_text}
```

Example:
```python
# Feature: mcp-gateway, Property 6: Tenant ownership validation on retrieval
@given(account_id=st.text(min_size=1), credential=credentials())
def test_tenant_ownership_validation(account_id, credential):
    # Test implementation
```

### Unit Testing Strategy

**Test Organization:**
- `tests/unit/test_oauth_flow.py` - OAuth initiation and callback handling
- `tests/unit/test_credentials.py` - Credential encryption, storage, retrieval
- `tests/unit/test_connected_accounts.py` - Connected account CRUD operations
- `tests/unit/test_mcp_servers.py` - MCP server deployment and management
- `tests/unit/test_tool_invocation.py` - Tool invocation and credential injection
- `tests/unit/test_token_refresh.py` - Token refresh logic
- `tests/unit/test_auth_configs.py` - Auth config management
- `tests/unit/test_isolation.py` - Tenant and user isolation

**Mocking Strategy:**
- Mock AWS services (KMS, Secrets Manager, DynamoDB, Lambda) using moto
- Mock OAuth provider responses
- Mock third-party API calls in MCP server tests
- Use real encryption/decryption logic (don't mock crypto)

**Edge Cases to Test:**
- Empty or null values for required fields
- Expired tokens
- Invalid OAuth codes
- Mismatched account_id or user_id
- Disconnected accounts
- Deleted auth configs
- Concurrent access to same resource
- Very long strings (credential values, URLs)
- Special characters in identifiers

### Integration Testing

**Local Integration Tests:**
- Use LocalStack for AWS service emulation
- Test full OAuth flow end-to-end
- Test tool invocation with real credential flow
- Test MCP server deployment and invocation
- Test migration from Composio format

**Staging Environment Tests:**
- Test with real AWS services (separate AWS account)
- Test with real OAuth providers (test apps)
- Load testing for concurrent requests
- Test tenant isolation under load
- Test cost optimization (Lambda cold starts, DynamoDB queries)

### Test Data Generators

**Hypothesis Strategies:**
```python
# Generate valid account IDs
account_ids = st.text(min_size=8, max_size=32, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))

# Generate valid user IDs
user_ids = st.text(min_size=8, max_size=64, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))

# Generate OAuth credentials
oauth_credentials = st.builds(
    OAuthCredentials,
    access_token=st.text(min_size=20, max_size=200),
    refresh_token=st.text(min_size=20, max_size=200),
    expires_at=st.integers(min_value=int(time.time()), max_value=int(time.time()) + 86400)
)

# Generate connected accounts
connected_accounts = st.builds(
    ConnectedAccount,
    account_id=account_ids,
    user_id=user_ids,
    status=st.sampled_from(["pending", "active", "failed", "requires_reauth", "disconnected"]),
    service_name=st.sampled_from(["github", "slack", "gmail", "notion"])
)
```

### Performance Testing

**Metrics to Track:**
- OAuth flow completion time (target: < 2 seconds)
- Tool invocation latency (target: < 500ms excluding third-party API time)
- Credential retrieval time (target: < 100ms)
- Token refresh time (target: < 1 second)
- Lambda cold start time (target: < 1 second)
- DynamoDB query time (target: < 50ms)

**Load Testing Scenarios:**
- 100 concurrent OAuth flows
- 1000 concurrent tool invocations
- 10,000 connected accounts per tenant
- 100 MCP servers per tenant

### Security Testing

**Security Test Cases:**
- Attempt to access credentials with wrong account_id
- Attempt to access credentials with wrong user_id
- Attempt to invoke tools with disconnected account
- Attempt to decrypt credentials without proper KMS permissions
- Verify credentials are encrypted in storage
- Verify credentials are not logged
- Verify audit logs contain all required fields
- Test SQL injection in DynamoDB queries (parameterized queries)
- Test for credential leakage in error messages



## Design Revisions Summary

After critical review, the following key changes were made to the original design:

### 1. Credential Storage
**Original:** AWS Secrets Manager with per-credential secrets
**Revised:** DynamoDB with KMS-encrypted binary column
**Rationale:** Lower cost, lower latency, simpler architecture

### 2. KMS Key Strategy
**Original:** One KMS key per tenant
**Revised:** Single shared KMS key with encryption context for isolation
**Rationale:** 99% cost reduction, no key limit concerns, cryptographically secure isolation

### 3. MCP Server Lambda Architecture
**Original:** Separate Lambda function per MCP server deployment
**Revised:** Single multi-tenant Lambda with dynamic toolkit loading
**Rationale:** Simpler operations, faster cold starts, easier to maintain and extend

### 4. API Gateway Type
**Original:** Not specified
**Revised:** HTTP API (not REST API)
**Rationale:** 70% cost reduction, sufficient features for this use case

### 5. Token Refresh Locking
**Original:** Not addressed
**Revised:** Distributed locking using DynamoDB conditional writes
**Rationale:** Prevents race conditions during concurrent token refresh attempts

### 6. MCP URL Format
**Original:** Not specified
**Revised:** URLs with embedded JWT tokens containing account_id, user_id, mcp_server_id
**Rationale:** Stateless authentication, no session management required

### 7. Tool Discovery
**Original:** Not addressed
**Revised:** Added tools/list endpoint per MCP protocol
**Rationale:** Required for MCP client compatibility

### 8. Migration Strategy
**Original:** Mentioned but not detailed
**Revised:** Compatibility layer with dual URL support during transition
**Rationale:** Zero-downtime migration from Composio

These revisions significantly improve cost efficiency, operational simplicity, and system reliability while maintaining all security and isolation requirements.



## Multi-Tenancy Security Analysis

### Is the Revised Design Safe and Secure?

**YES.** The revised design maintains the same security guarantees as the original while reducing cost and complexity. Here's why:

### 1. KMS Encryption Context Provides Cryptographic Isolation

**How it works:**
```python
# Encrypting credentials for tenant A, user 1
encryption_context_a = {
    "account_id": "tenant_a",
    "user_id": "user_1",
    "connected_account_id": "conn_123"
}
encrypted_data_a = kms.encrypt(
    KeyId="master-key",
    Plaintext=credentials,
    EncryptionContext=encryption_context_a
)

# Attempting to decrypt with wrong context FAILS
encryption_context_b = {
    "account_id": "tenant_b",  # Different tenant!
    "user_id": "user_2",
    "connected_account_id": "conn_123"
}
# This will raise an exception - KMS refuses to decrypt
kms.decrypt(
    CiphertextBlob=encrypted_data_a,
    EncryptionContext=encryption_context_b  # WRONG CONTEXT
)
```

**Security Guarantee:**
- KMS cryptographically binds the encryption context to the ciphertext
- Decryption ONLY succeeds if the encryption context matches exactly
- Even with access to the KMS key, you cannot decrypt data without the correct context
- This is a **cryptographic guarantee**, not just an application-level check

**AWS Documentation:**
> "The encryption context is cryptographically bound to the encrypted data so that the same encryption context is required to decrypt the data. If you specify an encryption context when you encrypt data, you must specify the same encryption context (a case-sensitive exact string match) when you decrypt the data. Otherwise, the decrypt request fails."
> — [AWS KMS Encryption Context Documentation](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html#encrypt_context)

### 2. DynamoDB Row-Level Security

**Partition Key Isolation:**
- ConnectedAccounts table uses `account_id` as partition key
- DynamoDB physically partitions data by partition key
- Queries MUST specify partition key, preventing cross-tenant scans

**Application-Level Validation:**
```python
def get_connected_account(account_id, connected_account_id, user_id):
    # Step 1: DynamoDB query with partition key (physical isolation)
    item = dynamodb.get_item(
        Key={
            'account_id': account_id,  # MUST match
            'connected_account_id': connected_account_id
        }
    )
    
    # Step 2: Validate user_id (application-level check)
    if item['user_id'] != user_id:
        raise UnauthorizedError("User does not own this account")
    
    # Step 3: Decrypt with encryption context (cryptographic isolation)
    credentials = kms.decrypt(
        CiphertextBlob=item['encrypted_credentials'],
        EncryptionContext={
            'account_id': account_id,
            'user_id': user_id,
            'connected_account_id': connected_account_id
        }
    )
    
    return credentials
```

**Three Layers of Protection:**
1. **Physical:** DynamoDB partition key isolation
2. **Application:** User ID validation
3. **Cryptographic:** KMS encryption context

### 3. JWT Token Security

**Token Structure:**
```json
{
  "account_id": "acc_123",
  "user_id": "user_456",
  "mcp_server_id": "srv_789",
  "connected_account_id": "conn_abc",
  "iat": 1234567890,
  "exp": 1234571490,
  "iss": "mcp-gateway"
}
```

**Security Properties:**
- Signed with HS256 or RS256 (cryptographically verified)
- Short expiration (1 hour max)
- Cannot be forged without the signing key
- Validated on every request before any data access

**Token Validation Flow:**
```python
def validate_request(jwt_token, requested_account_id, requested_user_id):
    # Step 1: Verify JWT signature
    claims = jwt.verify(jwt_token, secret_key)
    
    # Step 2: Check expiration
    if claims['exp'] < time.time():
        raise TokenExpiredError()
    
    # Step 3: Validate account_id matches
    if claims['account_id'] != requested_account_id:
        raise UnauthorizedError("Account ID mismatch")
    
    # Step 4: Validate user_id matches
    if claims['user_id'] != requested_user_id:
        raise UnauthorizedError("User ID mismatch")
    
    return claims
```

### 4. Single Lambda Multi-Tenancy Security

**Concern:** "Can one tenant's request access another tenant's data in a shared Lambda?"

**Answer:** No, because:

1. **Stateless Execution:** Each Lambda invocation is isolated
2. **No Shared State:** No global variables or caches shared between requests
3. **Request-Scoped Context:** All tenant/user context comes from JWT token
4. **Validation on Every Request:** Every data access validates account_id and user_id

**Example:**
```python
# Request 1: Tenant A
def lambda_handler(event, context):
    jwt_token = extract_token(event)
    claims = validate_jwt(jwt_token)  # account_id=A, user_id=1
    
    # All subsequent operations use claims['account_id'] and claims['user_id']
    credentials = get_credentials(
        account_id=claims['account_id'],  # A
        user_id=claims['user_id']  # 1
    )
    # Can ONLY access Tenant A, User 1 data

# Request 2: Tenant B (different invocation, completely isolated)
def lambda_handler(event, context):
    jwt_token = extract_token(event)
    claims = validate_jwt(jwt_token)  # account_id=B, user_id=2
    
    credentials = get_credentials(
        account_id=claims['account_id'],  # B
        user_id=claims['user_id']  # 2
    )
    # Can ONLY access Tenant B, User 2 data
```

### 5. Comparison: Per-Tenant Keys vs Encryption Context

| Aspect | Per-Tenant KMS Keys | Single Key + Encryption Context |
|--------|---------------------|----------------------------------|
| **Cryptographic Isolation** | ✅ Yes | ✅ Yes (same level) |
| **Physical Isolation** | ✅ Yes | ❌ No (but not needed) |
| **Cost** | ❌ $1/tenant/month | ✅ $1/month total |
| **Key Limits** | ❌ 10K keys/region | ✅ No limit concerns |
| **Operational Complexity** | ❌ High (manage 1000s of keys) | ✅ Low (1 key) |
| **Security Level** | 🔒 Excellent | 🔒 Excellent (equivalent) |

**AWS Best Practice:**
AWS recommends encryption context for multi-tenant applications:
> "You can use encryption context to implement a form of authorization. For example, you can use encryption context to ensure that only authorized users can decrypt data."
> — [AWS KMS Best Practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)

### 6. Attack Scenarios and Mitigations

**Scenario 1: Attacker gets access to DynamoDB**
- **Attack:** Read encrypted credentials from DynamoDB
- **Mitigation:** Credentials are encrypted; attacker cannot decrypt without KMS access AND correct encryption context
- **Result:** ✅ Data remains secure

**Scenario 2: Attacker gets KMS decrypt permission**
- **Attack:** Attempt to decrypt credentials with KMS key
- **Mitigation:** Decryption requires exact encryption context (account_id, user_id, connected_account_id)
- **Result:** ✅ Cannot decrypt other tenants' data without their encryption context

**Scenario 3: Attacker compromises Lambda execution**
- **Attack:** Inject malicious code into Lambda to steal credentials
- **Mitigation:** 
  - Lambda execution role has minimal permissions (least privilege)
  - CloudWatch logs audit all credential access
  - JWT validation prevents unauthorized requests
- **Result:** ✅ Limited blast radius, detected via audit logs

**Scenario 4: Attacker forges JWT token**
- **Attack:** Create fake JWT with different account_id
- **Mitigation:** JWT signature validation fails (cannot forge without signing key)
- **Result:** ✅ Request rejected at API Gateway

**Scenario 5: Attacker steals valid JWT token**
- **Attack:** Use stolen JWT to access data
- **Mitigation:** 
  - Short token expiration (1 hour)
  - Token includes specific connected_account_id (limited scope)
  - Audit logs track all access
- **Result:** ⚠️ Limited time window, limited scope, fully audited

**Scenario 6: Insider threat (malicious developer)**
- **Attack:** Developer with AWS access attempts to read credentials
- **Mitigation:**
  - IAM policies restrict KMS decrypt to Lambda execution role only
  - CloudTrail logs all KMS operations
  - Encryption context prevents bulk decryption
- **Result:** ✅ Prevented by IAM, detected by CloudTrail

### 7. Compliance and Audit

**Audit Trail:**
- CloudTrail logs all KMS encrypt/decrypt operations with encryption context
- CloudWatch logs all credential access with account_id and user_id
- DynamoDB streams can track all data modifications

**Compliance:**
- **SOC 2:** Encryption at rest (KMS), encryption in transit (TLS), audit logging
- **GDPR:** User data isolation, right to deletion (cascade delete), audit trail
- **HIPAA:** Encryption, access controls, audit logging (if needed)

### Conclusion

**The revised design is EQUALLY SECURE as per-tenant KMS keys** because:
1. KMS encryption context provides cryptographic isolation
2. DynamoDB partition keys provide physical data isolation
3. JWT tokens provide request-level authentication and authorization
4. Application-level validation provides defense in depth
5. Audit logging provides detection and compliance

**The revised design is MORE SECURE in practice** because:
1. Simpler architecture = fewer opportunities for misconfiguration
2. Single Lambda = easier to audit and monitor
3. Lower cost = more budget for security tooling and monitoring
4. Fewer moving parts = smaller attack surface

**This is a well-established pattern** used by:
- AWS itself for multi-tenant services
- Major SaaS providers (Stripe, Twilio, etc.)
- Enterprise applications requiring strong isolation

The key insight: **Cryptographic isolation (encryption context) is as strong as physical isolation (separate keys), but more practical at scale.**

