# Requirements Document: AWS AgentCore Migration

## Introduction

This document outlines the requirements for building the Kortix AI agent platform using AWS Bedrock AgentCore as the foundation. This is a greenfield project with no existing user data. The platform will leverage AgentCore's serverless runtime, managed infrastructure, and integrated primitives (Memory, Browser, Code Interpreter, Gateway) to provide a scalable, multi-tenant AI agent platform.

## Glossary

- **Kortix Platform**: A new open-source AI agent platform for building, managing, and training AI agents
- **AgentCore Runtime**: AWS Bedrock's serverless deployment and scaling service for AI agents
- **AgentCore Memory**: Persistent knowledge service with event and semantic memory capabilities
- **AgentCore Browser**: Fast, secure cloud-based browser for web interaction
- **AgentCore Code Interpreter**: Secure code execution in isolated sandboxes
- **AgentCore Gateway**: Service to transform existing APIs into agent tools via MCP protocol
- **ThreadManager**: Conversation thread management system with LLM integration
- **MCP (Model Context Protocol)**: Protocol for connecting external tools and services to agents
- **Suna**: The flagship generalist AI worker agent included with Kortix
- **Agent Run**: A single execution instance of an agent processing a thread
- **Project**: A workspace containing threads, files, and sandbox environment

## Requirements

### Requirement 1

**User Story:** As a platform operator, I want to use AgentCore Runtime for agent execution, so that I can leverage serverless scaling without infrastructure management overhead.

#### Acceptance Criteria

1. WHEN an agent run is initiated THEN the system SHALL execute the agent using AgentCore Runtime
2. WHEN multiple agent runs execute concurrently THEN AgentCore Runtime SHALL handle scaling automatically without manual configuration
3. WHEN an agent run completes THEN the system SHALL capture execution results and persist them to the database
4. WHEN an agent run fails THEN the system SHALL capture error details and update the run status appropriately
5. WHEN the system starts up THEN the system SHALL only require AgentCore SDK configuration

### Requirement 2

**User Story:** As a platform operator, I want to use AgentCore Code Interpreter for code execution, so that I can provide secure, isolated execution environments without managing infrastructure.

#### Acceptance Criteria

1. WHEN an agent needs to execute code THEN the system SHALL use AgentCore Code Interpreter
2. WHEN code execution is requested THEN AgentCore Code Interpreter SHALL provide isolated execution environments with appropriate resource limits
3. WHEN file operations are needed THEN AgentCore Code Interpreter SHALL provide file system access within the isolated environment
4. WHEN code execution completes THEN the system SHALL automatically clean up execution resources
5. WHEN the system handles file uploads THEN the system SHALL store files in S3 with AgentCore-compatible paths

### Requirement 3

**User Story:** As a platform operator, I want to integrate AgentCore Browser for web automation, so that agents can interact with web pages securely and efficiently.

#### Acceptance Criteria

1. WHEN an agent needs browser automation THEN the system SHALL use AgentCore Browser
2. WHEN browser navigation is requested THEN AgentCore Browser SHALL provide fast, secure cloud-based browsing capabilities
3. WHEN web scraping is needed THEN AgentCore Browser SHALL extract data and return structured results
4. WHEN form filling is required THEN AgentCore Browser SHALL interact with web elements programmatically
5. WHEN browser sessions complete THEN the system SHALL automatically clean up browser resources

### Requirement 4

**User Story:** As a platform operator, I want to use AgentCore Memory for conversation history, so that I can leverage persistent knowledge storage with semantic search capabilities.

#### Acceptance Criteria

1. WHEN a thread is created THEN the system SHALL initialize an AgentCore Memory resource for that thread
2. WHEN messages are added to a thread THEN the system SHALL store them in AgentCore Memory with appropriate metadata
3. WHEN an agent needs conversation context THEN the system SHALL retrieve relevant messages from AgentCore Memory
4. WHEN semantic search is needed THEN AgentCore Memory SHALL provide vector-based retrieval of relevant context
5. WHEN a thread is deleted THEN the system SHALL clean up the associated AgentCore Memory resource

### Requirement 5

**User Story:** As a platform operator, I want to use AgentCore Gateway for MCP integration, so that I can provide AWS-native API connectivity for external services.

#### Acceptance Criteria

1. WHEN an MCP server configuration is provided THEN the system SHALL deploy it to AgentCore Gateway
2. WHEN an agent needs to call an external API THEN the system SHALL route the request through AgentCore Gateway
3. WHEN authentication is required THEN the system SHALL use AWS Secrets Manager or AgentCore Identity for credential management
4. WHEN API schemas change THEN the system SHALL update Gateway configurations without agent code changes
5. WHEN Gateway targets are deployed THEN the system SHALL validate connectivity and schema compatibility

### Requirement 5A

**User Story:** As a platform operator, I want to build an MCP server catalog using AWS services, so that users can discover and configure available MCP integrations.

#### Acceptance Criteria

1. WHEN the frontend needs to display available MCP servers THEN the system SHALL retrieve the catalog from DynamoDB or S3
2. WHEN new MCP servers are added THEN the system SHALL store server metadata in DynamoDB or S3
3. WHEN users browse the MCP catalog THEN the system SHALL provide search and filtering capabilities
4. WHEN MCP server configurations are selected THEN the system SHALL provide deployment templates for AgentCore Gateway
5. WHEN the catalog is updated THEN the system SHALL version control server definitions and support rollback

### Requirement 5B

**User Story:** As a platform operator, I want to implement OAuth and API authentication flows using AWS services, so that users can securely connect third-party services.

#### Acceptance Criteria

1. WHEN users need to connect third-party services THEN the system SHALL use AWS Cognito or custom OAuth flows
2. WHEN API credentials are stored THEN the system SHALL use AWS Secrets Manager for secure credential storage
3. WHEN OAuth tokens need refresh THEN the system SHALL implement token refresh logic using AWS Lambda
4. WHEN multiple users share an integration THEN the system SHALL manage per-user credentials in AWS Secrets Manager with appropriate access controls
5. WHEN credentials are accessed by agents THEN AgentCore Identity SHALL provide secure credential retrieval during execution

### Requirement 6

**User Story:** As a platform operator, I want to implement a ThreadManager interface, so that agent execution logic is clean and maintainable.

#### Acceptance Criteria

1. WHEN ThreadManager methods are called THEN the system SHALL provide a clean, consistent API
2. WHEN tool execution is requested THEN the system SHALL route to appropriate AgentCore primitives (Browser, Code Interpreter, Gateway)
3. WHEN LLM calls are made THEN the system SHALL continue using the existing LiteLLM integration
4. WHEN prompt caching is enabled THEN the system SHALL implement efficient caching strategies
5. WHEN context compression is needed THEN the system SHALL implement ContextManager functionality

### Requirement 7

**User Story:** As a platform operator, I want to implement billing integration, so that credit deduction works correctly with AgentCore-based execution.

#### Acceptance Criteria

1. WHEN an agent run completes THEN the system SHALL deduct credits based on token usage from AgentCore
2. WHEN cache hits occur THEN the system SHALL apply appropriate cache read token pricing
3. WHEN cache writes occur THEN the system SHALL charge for cache creation tokens
4. WHEN model access is checked THEN the system SHALL validate against the user's tier and available models
5. WHEN billing fails THEN the system SHALL prevent agent execution and return appropriate error messages

### Requirement 8

**User Story:** As a platform operator, I want to maintain the existing API endpoints, so that frontend applications continue to work without modifications.

#### Acceptance Criteria

1. WHEN the frontend calls POST /api/agent/start THEN the system SHALL create an agent run using AgentCore Runtime
2. WHEN the frontend streams responses THEN the system SHALL provide real-time updates from AgentCore execution
3. WHEN the frontend stops an agent run THEN the system SHALL cancel the AgentCore execution
4. WHEN the frontend queries agent run status THEN the system SHALL return current execution state from AgentCore
5. WHEN the frontend uploads files THEN the system SHALL store them in AgentCore-compatible storage

### Requirement 9

**User Story:** As a platform operator, I want to preserve the tool registry system, so that custom tools continue to work alongside AgentCore primitives.

#### Acceptance Criteria

1. WHEN tools are registered THEN the system SHALL distinguish between AgentCore primitives and custom tools
2. WHEN AgentCore primitives are available THEN the system SHALL prefer them over custom implementations
3. WHEN custom tools are needed THEN the system SHALL execute them through AgentCore Code Interpreter
4. WHEN tool schemas are generated THEN the system SHALL include both AgentCore and custom tool definitions
5. WHEN tool execution fails THEN the system SHALL provide clear error messages indicating the tool source

### Requirement 10

**User Story:** As a platform operator, I want to implement AgentCore deployment automation, so that agent configurations can be deployed programmatically.

#### Acceptance Criteria

1. WHEN an agent is created or updated THEN the system SHALL package it for AgentCore deployment
2. WHEN deployment is triggered THEN the system SHALL use AgentCore CLI or SDK to deploy the agent
3. WHEN deployment succeeds THEN the system SHALL store the AgentCore deployment ID for future invocations
4. WHEN deployment fails THEN the system SHALL log errors and maintain the previous deployment
5. WHEN multiple agent versions exist THEN the system SHALL manage separate AgentCore deployments per version

### Requirement 11

**User Story:** As a platform operator, I want to implement a notification system, so that users receive task completion and failure notifications.

#### Acceptance Criteria

1. WHEN an agent run completes successfully THEN the system SHALL send completion notifications
2. WHEN an agent run fails THEN the system SHALL send failure notifications with error details
3. WHEN the complete tool is called THEN the system SHALL trigger task completion notifications
4. WHEN notifications are sent THEN the system SHALL include thread context and agent information
5. WHEN notification delivery fails THEN the system SHALL log errors without blocking agent execution

### Requirement 12

**User Story:** As a platform operator, I want to maintain observability and monitoring, so that I can track agent performance and debug issues.

#### Acceptance Criteria

1. WHEN agent runs execute THEN the system SHALL log execution metrics to CloudWatch or similar logging infrastructure
2. WHEN errors occur THEN the system SHALL capture stack traces and context for debugging
3. WHEN performance issues arise THEN the system SHALL provide timing breakdowns for key operations
4. WHEN AgentCore primitives are used THEN the system SHALL log primitive invocations and results
5. WHEN Langfuse tracing is enabled THEN the system SHALL continue to send traces for LLM calls

### Requirement 13

**User Story:** As a platform operator, I want to implement graceful fallback mechanisms, so that the system can handle AgentCore service disruptions.

#### Acceptance Criteria

1. WHEN AgentCore Runtime is unavailable THEN the system SHALL return clear error messages to users
2. WHEN AgentCore Memory is unavailable THEN the system SHALL fall back to database-based message retrieval
3. WHEN AgentCore Browser is unavailable THEN the system SHALL disable browser-dependent features gracefully
4. WHEN AgentCore Code Interpreter is unavailable THEN the system SHALL prevent code execution requests
5. WHEN AgentCore Gateway is unavailable THEN the system SHALL disable affected MCP tools

### Requirement 14

**User Story:** As a platform operator, I want to implement a clean database schema, so that user data, threads, and agent configurations are well-organized.

#### Acceptance Criteria

1. WHEN the system is deployed THEN the system SHALL use Supabase (PostgreSQL) for data persistence
2. WHEN agent runs are created THEN the system SHALL store records in the agent_runs table
3. WHEN messages are added THEN the system SHALL store them in the messages table
4. WHEN projects are managed THEN the system SHALL use the projects table
5. WHEN AgentCore-specific metadata is needed THEN the system SHALL store it in appropriate metadata columns

### Requirement 15

**User Story:** As a platform operator, I want to implement multi-tenant isolation, so that tenant data and resources remain securely separated.

#### Acceptance Criteria

1. WHEN AgentCore Runtime executes agents THEN the system SHALL ensure tenant isolation at the execution level
2. WHEN AgentCore Memory stores conversation history THEN the system SHALL partition memory resources by tenant account_id
3. WHEN AgentCore Gateway handles API calls THEN the system SHALL enforce tenant-specific credential access
4. WHEN AWS Secrets Manager stores credentials THEN the system SHALL organize secrets by tenant with appropriate IAM policies
5. WHEN the MCP catalog is accessed THEN the system SHALL filter available servers based on tenant permissions and subscriptions
6. WHEN billing is calculated THEN the system SHALL attribute AgentCore usage costs to the correct tenant account
7. WHEN multiple tenants use the same agent template THEN the system SHALL maintain separate AgentCore deployments or execution contexts per tenant

### Requirement 16

**User Story:** As a platform operator, I want to initialize AgentCore-compatible storage for new data, so that all data is stored correctly from the start.

#### Acceptance Criteria

1. WHEN the system starts THEN the system SHALL use AgentCore Memory for all new conversation threads
2. WHEN files are uploaded THEN the system SHALL store them in S3 with AgentCore-compatible paths
3. WHEN new threads are created THEN the system SHALL initialize AgentCore Memory resources immediately
4. WHEN the system is deployed THEN the system SHALL NOT require any data migration from legacy systems
5. WHEN storage is initialized THEN the system SHALL verify connectivity to all AgentCore services

### Requirement 17

**User Story:** As a platform operator, I want to optimize AgentCore costs, so that the migration does not significantly increase operational expenses.

#### Acceptance Criteria

1. WHEN AgentCore Runtime executes agents THEN the system SHALL monitor execution costs per tenant
2. WHEN AgentCore Memory stores data THEN the system SHALL implement retention policies to manage storage costs
3. WHEN AgentCore Browser is used THEN the system SHALL track browser session costs and optimize usage patterns
4. WHEN AgentCore Code Interpreter executes code THEN the system SHALL monitor compute costs and set appropriate limits
5. WHEN cost thresholds are exceeded THEN the system SHALL alert operators and optionally throttle usage

### Requirement 18

**User Story:** As a platform operator, I want to implement a frontend for the AWS-based MCP catalog, so that users can browse and configure MCP servers.

#### Acceptance Criteria

1. WHEN users access the MCP configuration UI THEN the system SHALL display the AWS-hosted catalog
2. WHEN users search for MCP servers THEN the frontend SHALL query the AWS catalog API
3. WHEN users configure an MCP server THEN the frontend SHALL provide OAuth flows using AWS Cognito
4. WHEN users view connected integrations THEN the frontend SHALL display credentials managed in AWS Secrets Manager
5. WHEN users disconnect an integration THEN the frontend SHALL revoke credentials through the AWS-based system

### Requirement 19

**User Story:** As a platform operator, I want to use AgentCore-native mechanisms for coordination, so that I minimize external infrastructure dependencies.

#### Acceptance Criteria

1. WHEN agent runs need isolation THEN the system SHALL use AgentCore Runtime's built-in execution isolation
2. WHEN response streaming is needed THEN the system SHALL use AgentCore's streaming APIs
3. WHEN caching is required THEN the system SHALL use ElastiCache or DynamoDB DAX for auth/API key caching
4. WHEN agent run coordination is needed THEN the system SHALL leverage AgentCore's execution state management
5. WHEN the system is deployed THEN the system SHALL NOT require Redis for core functionality

### Requirement 20

**User Story:** As a platform operator, I want to implement environment-based configuration, so that I can test AgentCore integration in development before production deployment.

#### Acceptance Criteria

1. WHEN the system starts THEN the system SHALL load AgentCore configuration from environment variables
2. WHEN running in development mode THEN the system SHALL use development AgentCore resources
3. WHEN running in production mode THEN the system SHALL use production AgentCore resources
4. WHEN configuration is invalid THEN the system SHALL fail fast with clear error messages
5. WHEN AgentCore services are unavailable THEN the system SHALL return appropriate error messages to users
