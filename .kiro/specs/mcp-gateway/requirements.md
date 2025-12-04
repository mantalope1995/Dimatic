# Requirements Document

## Introduction

This document specifies the requirements for a multi-tenant MCP (Model Context Protocol) Gateway built with AWS services. The gateway will replace Composio's managed service, providing 1-click OAuth authentication for users to connect third-party services (GitHub, Slack, Gmail, etc.) to their AI agents. The system will handle OAuth flows, credential storage, MCP server deployment, and secure tool invocation with proper tenant isolation.

## Glossary

- **MCP Gateway**: A serverless system that manages MCP server deployments and routes tool invocations with authentication
- **Tenant**: An isolated account or organization using the gateway, identified by account_id
- **Connected Account**: An authenticated connection to a third-party service (e.g., GitHub, Slack) for a specific user
- **Auth Config**: Configuration defining how to authenticate with a third-party service (OAuth credentials, scopes, etc.)
- **MCP Server**: A deployed instance that exposes tools for a specific third-party service
- **Tool Invocation**: A request to execute a specific tool (e.g., "create_github_issue") with user credentials
- **OAuth Flow**: The process of obtaining user authorization to access their third-party service accounts
- **Toolkit**: A collection of tools for a specific third-party service (e.g., GitHub toolkit, Slack toolkit)
- **User ID**: A unique identifier for an end user within a tenant's account
- **Credential Profile**: A saved configuration linking a user to their connected accounts and MCP servers

## Requirements

### Requirement 1

**User Story:** As a user, I want to authenticate with third-party services using OAuth with a single click, so that I can quickly connect my accounts without manual credential management.

#### Acceptance Criteria

1. WHEN a user initiates OAuth for a supported service THEN the MCP Gateway SHALL generate a unique authorization URL and redirect the user to the service's OAuth consent page
2. WHEN the OAuth provider redirects back with an authorization code THEN the MCP Gateway SHALL exchange the code for access tokens and store them securely
3. WHEN OAuth tokens are received THEN the MCP Gateway SHALL encrypt the tokens before storage using AWS KMS
4. WHEN a user completes OAuth THEN the MCP Gateway SHALL create a connected account record with status "active"
5. WHEN OAuth fails or is cancelled THEN the MCP Gateway SHALL update the connected account status to "failed" and provide an error message

### Requirement 2

**User Story:** As a system administrator, I want all tenant data to be isolated, so that one tenant cannot access another tenant's credentials or data.

#### Acceptance Criteria

1. WHEN storing credentials THEN the MCP Gateway SHALL partition data by account_id to ensure tenant isolation
2. WHEN retrieving credentials THEN the MCP Gateway SHALL validate that the requesting account_id matches the credential owner
3. WHEN invoking tools THEN the MCP Gateway SHALL verify tenant ownership before allowing access to credentials
4. WHEN listing resources THEN the MCP Gateway SHALL filter results to only include resources owned by the requesting tenant
5. WHEN a tenant is deleted THEN the MCP Gateway SHALL remove all associated credentials, connected accounts, and MCP servers

### Requirement 3

**User Story:** As a user, I want my connected accounts to be private to me, so that other users in my organization cannot access my personal service credentials.

#### Acceptance Criteria

1. WHEN storing connected accounts THEN the MCP Gateway SHALL associate each account with both account_id and user_id for dual-level isolation
2. WHEN retrieving credentials for tool invocation THEN the MCP Gateway SHALL verify both account_id and user_id match the requesting context
3. WHEN a user lists their connected accounts THEN the MCP Gateway SHALL return only accounts where the user_id matches the requesting user
4. WHEN invoking a tool THEN the MCP Gateway SHALL ensure the user_id in the request matches the user_id of the connected account being used
5. WHEN a user is removed from an account THEN the MCP Gateway SHALL delete or revoke access to all of that user's connected accounts

### Requirement 4

**User Story:** As a developer, I want to deploy MCP servers for different third-party services, so that my agents can use tools from those services.

#### Acceptance Criteria

1. WHEN creating an MCP server THEN the MCP Gateway SHALL deploy a Lambda function configured with the specified toolkit
2. WHEN an MCP server is created THEN the MCP Gateway SHALL generate a unique MCP URL for client connections
3. WHEN deploying an MCP server THEN the MCP Gateway SHALL configure API Gateway to route requests to the Lambda function
4. WHEN an MCP server is deployed THEN the MCP Gateway SHALL associate it with the specified auth configs and tenant
5. WHEN listing MCP servers THEN the MCP Gateway SHALL return only servers owned by the requesting tenant

### Requirement 5

**User Story:** As an AI agent, I want to invoke tools on MCP servers with user credentials, so that I can perform actions on behalf of users.

#### Acceptance Criteria

1. WHEN invoking a tool THEN the MCP Gateway SHALL retrieve credentials only for the specific user_id provided in the request
2. WHEN credentials are retrieved THEN the MCP Gateway SHALL decrypt them using AWS KMS before use
3. WHEN a tool is invoked THEN the MCP Gateway SHALL pass the decrypted credentials to the MCP server Lambda function
4. WHEN a tool execution completes THEN the MCP Gateway SHALL return the result to the caller
5. WHEN a tool invocation fails due to missing or invalid user credentials THEN the MCP Gateway SHALL return an error indicating which user needs to authenticate

### Requirement 6

**User Story:** As a user, I want my OAuth tokens to be automatically refreshed when they expire, so that my integrations continue working without manual intervention.

#### Acceptance Criteria

1. WHEN an access token expires THEN the MCP Gateway SHALL automatically use the refresh token to obtain a new access token
2. WHEN tokens are refreshed THEN the MCP Gateway SHALL update the stored credentials with the new tokens
3. WHEN a refresh token is invalid or expired THEN the MCP Gateway SHALL mark the connected account as "requires_reauth"
4. WHEN token refresh succeeds THEN the MCP Gateway SHALL retry the original tool invocation with the new token
5. WHEN token refresh fails THEN the MCP Gateway SHALL return an error indicating re-authentication is required

### Requirement 7

**User Story:** As a system architect, I want the gateway to scale automatically with demand, so that it can handle varying loads without manual intervention.

#### Acceptance Criteria

1. WHEN request volume increases THEN the MCP Gateway SHALL automatically scale Lambda functions to handle the load
2. WHEN request volume decreases THEN the MCP Gateway SHALL scale down to minimize costs
3. WHEN concurrent invocations exceed limits THEN the MCP Gateway SHALL queue requests and process them as capacity becomes available
4. WHEN the system is under load THEN the MCP Gateway SHALL maintain response times within acceptable thresholds
5. WHEN scaling occurs THEN the MCP Gateway SHALL maintain both tenant-level and user-level isolation and data security

### Requirement 8

**User Story:** As a security engineer, I want all credentials to be encrypted at rest and in transit, so that sensitive data is protected from unauthorized access.

#### Acceptance Criteria

1. WHEN storing credentials THEN the MCP Gateway SHALL encrypt them using AWS KMS with tenant-specific keys
2. WHEN transmitting credentials THEN the MCP Gateway SHALL use TLS 1.2 or higher for all network communication
3. WHEN accessing KMS THEN the MCP Gateway SHALL use IAM roles with least-privilege permissions
4. WHEN credentials are no longer needed THEN the MCP Gateway SHALL securely delete them from all storage locations
5. WHEN audit logs are generated THEN the MCP Gateway SHALL record all credential access events with timestamps, actor information, and user_id

### Requirement 9

**User Story:** As a developer, I want to configure auth settings for third-party services, so that I can customize OAuth scopes and parameters for my use case.

#### Acceptance Criteria

1. WHEN creating an auth config THEN the MCP Gateway SHALL accept OAuth client credentials and configuration parameters
2. WHEN an auth config is created THEN the MCP Gateway SHALL validate that required fields are present
3. WHEN using custom OAuth credentials THEN the MCP Gateway SHALL use the provided credentials instead of managed defaults
4. WHEN an auth config is updated THEN the MCP Gateway SHALL apply changes to new connections without affecting existing ones
5. WHEN an auth config is deleted THEN the MCP Gateway SHALL prevent new connections but preserve existing connected accounts

### Requirement 10

**User Story:** As a user, I want to manage my connected accounts, so that I can view, disconnect, or reconnect services as needed.

#### Acceptance Criteria

1. WHEN listing connected accounts THEN the MCP Gateway SHALL return only accounts where the user_id matches the requesting user
2. WHEN disconnecting an account THEN the MCP Gateway SHALL verify the user_id matches before revoking OAuth tokens and marking the account as "disconnected"
3. WHEN reconnecting an account THEN the MCP Gateway SHALL verify user_id ownership before initiating a new OAuth flow
4. WHEN viewing account details THEN the MCP Gateway SHALL display connection status, last used timestamp, and associated services only if the user_id matches
5. WHEN an account is disconnected THEN the MCP Gateway SHALL prevent tool invocations using that account's credentials

### Requirement 11

**User Story:** As a system operator, I want comprehensive logging and monitoring, so that I can troubleshoot issues and track system health.

#### Acceptance Criteria

1. WHEN any operation occurs THEN the MCP Gateway SHALL log the event to CloudWatch with structured metadata including account_id and user_id
2. WHEN errors occur THEN the MCP Gateway SHALL log stack traces and context information for debugging without exposing credentials
3. WHEN tool invocations are made THEN the MCP Gateway SHALL record metrics including latency, success rate, and error types per user
4. WHEN OAuth flows complete THEN the MCP Gateway SHALL log the outcome and any errors encountered with user_id context
5. WHEN viewing logs THEN the MCP Gateway SHALL support filtering by tenant, user, service, and time range

### Requirement 12

**User Story:** As a developer, I want to integrate the gateway with my existing Kortix backend, so that I can replace Composio with minimal code changes.

#### Acceptance Criteria

1. WHEN the gateway is deployed THEN the MCP Gateway SHALL provide API endpoints compatible with the existing Composio integration interface
2. WHEN migrating from Composio THEN the MCP Gateway SHALL support importing existing connected accounts with their user_id associations
3. WHEN the gateway is called THEN the MCP Gateway SHALL return responses in the same format as the current Composio integration
4. WHEN errors occur THEN the MCP Gateway SHALL use the same error codes and structures as the existing integration
5. WHEN the gateway is integrated THEN the MCP Gateway SHALL work with existing credential profile and MCP module code

### Requirement 13

**User Story:** As a cost-conscious operator, I want the system to minimize AWS costs, so that the gateway is economical to run at scale.

#### Acceptance Criteria

1. WHEN Lambda functions are idle THEN the MCP Gateway SHALL incur no compute costs
2. WHEN storing credentials THEN the MCP Gateway SHALL use DynamoDB with on-demand pricing to avoid over-provisioning
3. WHEN caching is beneficial THEN the MCP Gateway SHALL cache frequently accessed data to reduce database queries
4. WHEN API Gateway is used THEN the MCP Gateway SHALL configure appropriate throttling to prevent cost overruns
5. WHEN monitoring costs THEN the MCP Gateway SHALL provide CloudWatch metrics for cost tracking and optimization
