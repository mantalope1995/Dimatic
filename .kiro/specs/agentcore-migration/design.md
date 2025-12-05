# Design Document: AWS AgentCore Platform

## Overview

This design document outlines the technical approach for building the Kortix AI agent platform using AWS Bedrock AgentCore as the foundation. This is a **greenfield project** with no existing user data or legacy systems to migrate. The platform will be built as a serverless, AWS-native system from the ground up.

**Critical Requirement:** The AgentCore implementation must achieve **feature parity** with the existing Kortix platform. All current capabilities must be preserved or improved.

### Feature Parity Requirements

The AgentCore platform must support all existing Kortix features:

**Core Agent Features:**
- Agent creation, versioning, and management
- Multi-agent support with custom configurations
- Agent templates and installation
- Agent builder tools
- Suna (flagship generalist agent)

**Execution & Runtime:**
- Thread-based conversation management
- Streaming responses via SSE
- Background agent execution
- Concurrent agent runs with auto-scaling
- Agent run status tracking and cancellation

**Tools & Integrations (20+ tools):**
- **Sandbox Tools:** Shell execution, file operations, code interpreter, vision, upload
- **Browser Tools:** Web automation, scraping, form filling (via Stagehand)
- **Search Tools:** Web search (Tavily), image search (SERPER), paper search, people search, company search
- **Document Tools:** Google Docs, Google Slides, document parsing
- **Presentation Tools:** HTML presentation generation with styling
- **Knowledge Base:** KB-fusion integration for semantic search
- **Image Tools:** Image generation and editing (OpenAI)
- **Communication:** Message tool, expand message tool
- **Task Management:** Task list tool for action planning
- **Voice:** VAPI voice integration
- **MCP Tools:** MCP server integration via wrapper
- **Data Providers:** External data provider integrations
- **Agent Management:** Agent creation tool

**MCP & External Integrations:**
- Composio integration for OAuth and MCP servers
- Custom MCP server support
- MCP catalog browsing and configuration
- Connected accounts management
- Trigger system for automated workflows

**Multi-Tenancy & Security:**
- Account-based isolation
- User roles and permissions
- API key management
- Credential storage and encryption
- Rate limiting per tenant

**Billing & Subscriptions:**
- Credit-based billing system
- Token usage tracking
- Subscription management (Stripe)
- Tier-based access control
- Referral system

**Knowledge Base:**
- File upload and processing
- Vector search capabilities
- Document parsing and indexing

**Notifications:**
- Task completion notifications
- Failure notifications
- Presence system
- Novu integration

**Observability:**
- Langfuse tracing for LLM calls
- Queue metrics
- Error tracking
- Logging infrastructure

**Developer Features:**
- Prompt caching (Claude, Gemini)
- Context compression
- Tool registry and discovery
- Native tool parser
- XML tool parser
- Response processing

### Architecture

**Backend Layer:**
- FastAPI application (Python) serving REST APIs (preserves all existing endpoints)
- AgentCore Runtime for serverless agent execution
- LiteLLM for multi-provider LLM integration (unchanged)
- Supabase (PostgreSQL) for data persistence (unchanged)
- ElastiCache or DynamoDB DAX for caching (optional)

**Execution Layer:**
- AgentCore Runtime managing agent lifecycle
- AgentCore Code Interpreter for secure code execution (replaces Daytona/E2B)
- AgentCore Browser for web automation (replaces Stagehand)
- AgentCore Memory for conversation history
- All 20+ custom tools executed via Code Interpreter

**Integration Layer:**
- AgentCore Gateway for MCP server integration (replaces Composio)
- AWS Secrets Manager for credential storage
- AWS Cognito for OAuth flows
- DynamoDB for MCP catalog
- Lambda functions for OAuth token refresh

### Feature Mapping to AgentCore

**How AgentCore Supports Existing Features:**

1. **Sandbox Tools (Shell, Files, Code, Vision, Upload)**
   - Execute via AgentCore Code Interpreter
   - File operations use S3 with Code Interpreter access
   - Shell commands run in Code Interpreter environment
   - Vision tool uses Code Interpreter + LLM vision APIs

2. **Browser Tool (Stagehand)**
   - Replace with AgentCore Browser
   - Maintain same interface for backward compatibility
   - AgentCore Browser provides navigation, scraping, form filling

3. **Search Tools (Web, Image, Paper, People, Company)**
   - Execute via Code Interpreter calling external APIs
   - Tavily, SERPER, and other API integrations preserved
   - No changes to tool interfaces

4. **Document Tools (Google Docs, Slides, Parsing)**
   - Execute via Code Interpreter
   - Google API integrations preserved
   - Document parsing runs in Code Interpreter

5. **Presentation Tool**
   - Execute via Code Interpreter
   - HTML generation and styling preserved
   - File output stored in S3

6. **Knowledge Base (KB-fusion)**
   - AgentCore Memory for semantic search
   - KB-fusion binary runs in Code Interpreter if needed
   - Vector search via AgentCore Memory APIs

7. **Image Tools (Generation, Editing)**
   - Execute via Code Interpreter calling OpenAI APIs
   - Image storage in S3
   - No changes to tool interfaces

8. **MCP Tools**
   - AgentCore Gateway replaces Composio
   - MCP catalog in DynamoDB
   - OAuth via Cognito + Lambda
   - Maintain MCPToolWrapper interface

9. **Task Management, Communication, Voice**
   - Execute via Code Interpreter
   - VAPI integration preserved
   - No changes to tool interfaces

10. **Agent Management & Versioning**
    - AgentCore Runtime handles deployment
    - Version management in Supabase (unchanged)
    - Agent templates preserved

11. **Billing & Credits**
    - Token tracking from AgentCore usage metrics
    - Stripe integration preserved (unchanged)
    - Credit deduction logic preserved

12. **Notifications**
    - Novu integration preserved (unchanged)
    - Triggered from AgentCore execution callbacks
    - Presence system preserved

13. **Observability**
    - Langfuse tracing preserved (unchanged)
    - CloudWatch for AgentCore metrics
    - Error tracking preserved

14. **Prompt Caching & Context Compression**
    - ThreadManager preserved (unchanged)
    - Prompt caching logic preserved
    - Context compression preserved


## Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
│                    - Chat UI                                     │
│                    - Agent Configuration                         │
│                    - MCP Catalog Browser                         │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API + SSE
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Unchanged)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Agent Runs   │  │ Threads      │  │ Billing      │         │
│  │ API          │  │ API          │  │ Integration  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Supabase   │  │ AgentCore   │  │   AWS       │
│  Database   │  │  Runtime    │  │  Services   │
│             │  │             │  │             │
│ - Threads   │  │ - Agent     │  │ - Secrets   │
│ - Messages  │  │   Execution │  │   Manager   │
│ - Agents    │  │ - Streaming │  │ - Cognito   │
│ - Projects  │  │ - State Mgmt│  │ - DynamoDB  │
└─────────────┘  └──────┬──────┘  │ - Lambda    │
                        │         └─────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ AgentCore   │  │ AgentCore   │  │ AgentCore   │
│   Memory    │  │   Browser   │  │   Gateway   │
│             │  │             │  │             │
│ - Event     │  │ - Web Nav   │  │ - MCP       │
│   Memory    │  │ - Scraping  │  │   Servers   │
│ - Semantic  │  │ - Form Fill │  │ - Auth      │
│   Search    │  │             │  │   Handling  │
└─────────────┘  └─────────────┘  └─────────────┘
         │              │              │
         └──────────────┴──────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │   AgentCore     │
              │     Code        │
              │  Interpreter    │
              │                 │
              │ - Python Exec   │
              │ - File System   │
              │ - Custom Tools  │
              └─────────────────┘
```

### Data Flow

**Agent Run Initiation:**
1. Frontend calls POST /api/agent/start
2. FastAPI validates billing and creates agent_run record
3. FastAPI invokes AgentCore Runtime with agent configuration
4. AgentCore Runtime initializes execution environment
5. FastAPI returns agent_run_id and begins SSE stream

**Agent Execution:**
1. AgentCore Runtime loads agent code and configuration
2. ThreadManager fetches conversation history from AgentCore Memory
3. LLM generates response with tool calls
4. Tools route to appropriate AgentCore primitives:
   - Code execution → AgentCore Code Interpreter
   - Browser automation → AgentCore Browser
   - External APIs → AgentCore Gateway
5. Tool results flow back to ThreadManager
6. Responses stream to FastAPI via AgentCore streaming API
7. FastAPI forwards responses to frontend via SSE

**Multi-Tenant Isolation:**
1. Each tenant has isolated AgentCore Memory partitions
2. AgentCore Gateway enforces tenant-specific credential access
3. AWS Secrets Manager organizes credentials by tenant
4. AgentCore Runtime execution contexts are tenant-isolated
5. Billing attribution tracks usage per tenant account_id


## Components and Interfaces

### 1. AgentCore Runtime Integration

**Purpose:** Replace Dramatiq workers with serverless agent execution

**Interface:**
```python
class AgentCoreRuntimeAdapter:
    """Adapter for AgentCore Runtime deployment and invocation"""
    
    async def deploy_agent(
        self,
        agent_id: str,
        agent_config: dict,
        version_id: str
    ) -> str:
        """
        Deploy agent to AgentCore Runtime
        Returns: deployment_id
        """
        pass
    
    async def invoke_agent(
        self,
        deployment_id: str,
        thread_id: str,
        input_data: dict,
        stream: bool = True
    ) -> AsyncGenerator:
        """
        Invoke deployed agent
        Yields: response chunks
        """
        pass
    
    async def cancel_execution(
        self,
        execution_id: str
    ) -> bool:
        """Cancel running agent execution"""
        pass
    
    async def get_execution_status(
        self,
        execution_id: str
    ) -> dict:
        """Get current execution status"""
        pass
```

**Implementation Details:**
- Use AgentCore CLI/SDK for deployment
- Store deployment_id in agent_versions table metadata
- Map agent_run_id to AgentCore execution_id
- Handle streaming responses via AgentCore streaming API
- Implement retry logic for transient failures

### 2. AgentCore Memory Integration

**Purpose:** Replace database-based message storage with AgentCore Memory

**Interface:**
```python
class AgentCoreMemoryAdapter:
    """Adapter for AgentCore Memory operations"""
    
    async def create_memory_resource(
        self,
        thread_id: str,
        account_id: str
    ) -> str:
        """
        Create AgentCore Memory resource for thread
        Returns: memory_resource_id
        """
        pass
    
    async def store_message(
        self,
        memory_resource_id: str,
        message: dict,
        metadata: dict
    ) -> str:
        """
        Store message in AgentCore Memory
        Returns: message_id
        """
        pass
    
    async def retrieve_messages(
        self,
        memory_resource_id: str,
        limit: int = 100,
        semantic_query: Optional[str] = None
    ) -> List[dict]:
        """
        Retrieve messages from AgentCore Memory
        Supports semantic search if query provided
        """
        pass
    
    async def delete_memory_resource(
        self,
        memory_resource_id: str
    ) -> bool:
        """Delete AgentCore Memory resource"""
        pass
```

**Implementation Details:**
- Create memory resource on thread creation
- Store memory_resource_id in threads table metadata
- Partition memory by tenant account_id
- Implement fallback to database for legacy threads
- Use semantic search for context retrieval

### 2A. Long-Term Memory (LTM) Strategies

**Purpose:** Enable personalized agent experiences across sessions with tenant isolation

**LTM Strategy Configuration:**
```python
LTM_STRATEGIES = [
    {
        "summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }
    },
    {
        "userPreferenceMemoryStrategy": {
            "name": "PreferenceLearner",
            "namespaces": ["/preferences/{actorId}"]
        }
    },
    {
        "semanticMemoryStrategy": {
            "name": "FactExtractor",
            "namespaces": ["/facts/{actorId}"]
        }
    }
]
```

**Multi-Tenant Isolation:**
```python
class TenantIsolatedMemoryConfig:
    """Memory configuration with tenant isolation"""
    
    def create_memory_config(
        self,
        account_id: str,
        user_id: str,
        session_id: str
    ) -> AgentCoreMemoryConfig:
        """
        Create memory config with tenant-scoped namespaces
        
        Namespace pattern: /{account_id}/{user_id}/{data_type}
        This ensures:
        - Tenant data is isolated by account_id prefix
        - User data is isolated within tenant by user_id
        - No cross-tenant data leakage possible
        """
        return AgentCoreMemoryConfig(
            memory_id=self._get_tenant_memory_id(account_id),
            session_id=session_id,
            actor_id=f"{account_id}:{user_id}",  # Composite actor ID
            retrieval_config={
                f"/preferences/{account_id}:{user_id}": RetrievalConfig(
                    top_k=5,
                    relevance_score=0.7
                ),
                f"/facts/{account_id}:{user_id}": RetrievalConfig(
                    top_k=10,
                    relevance_score=0.5
                )
            }
        )
```

**Security Considerations:**
- Each tenant gets a separate Memory resource (memory_id per account_id)
- Actor IDs are prefixed with account_id to prevent cross-tenant queries
- Namespace patterns include account_id for data isolation
- Retrieval configs are scoped to tenant-specific namespaces

### 2B. Semantic Search Configuration

**Purpose:** Replace KB-fusion for conversation search with AgentCore Memory's built-in vector search

**Interface:**
```python
class SemanticSearchConfig:
    """Configuration for AgentCore Memory semantic search"""
    
    def configure_retrieval(
        self,
        account_id: str,
        user_id: str,
        search_type: str = "conversation"
    ) -> dict:
        """
        Configure semantic search with tenant isolation
        
        search_type options:
        - "conversation": Search conversation history
        - "preferences": Search user preferences
        - "facts": Search extracted facts
        """
        actor_id = f"{account_id}:{user_id}"
        
        configs = {
            "conversation": {
                f"/messages/{actor_id}": RetrievalConfig(
                    top_k=20,
                    relevance_score=0.3
                )
            },
            "preferences": {
                f"/preferences/{actor_id}": RetrievalConfig(
                    top_k=5,
                    relevance_score=0.7
                )
            },
            "facts": {
                f"/facts/{actor_id}": RetrievalConfig(
                    top_k=10,
                    relevance_score=0.5
                )
            }
        }
        return configs.get(search_type, configs["conversation"])
```

### 3. AgentCore Code Interpreter Integration

**Purpose:** Replace Daytona/E2B sandboxes with AgentCore Code Interpreter

**Interface:**
```python
class AgentCoreCodeInterpreterAdapter:
    """Adapter for AgentCore Code Interpreter"""
    
    async def execute_code(
        self,
        code: str,
        language: str,
        files: Optional[List[str]] = None,
        timeout: int = 30
    ) -> dict:
        """
        Execute code in isolated environment
        Returns: {output, error, files_created}
        """
        pass
    
    async def execute_shell_command(
        self,
        command: str,
        working_dir: str = "/workspace",
        timeout: int = 30
    ) -> dict:
        """
        Execute shell command
        Returns: {stdout, stderr, exit_code}
        """
        pass
    
    async def upload_file(
        self,
        file_path: str,
        content: bytes
    ) -> str:
        """
        Upload file to Code Interpreter environment
        Returns: file_path
        """
        pass
    
    async def download_file(
        self,
        file_path: str
    ) -> bytes:
        """Download file from Code Interpreter environment"""
        pass
    
    async def list_files(
        self,
        directory: str = "/workspace"
    ) -> List[str]:
        """List files in directory"""
        pass
```

**Implementation Details:**
- Map all SandboxToolsBase methods to Code Interpreter
- Store files in S3 with AgentCore-compatible paths
- Implement file upload/download via S3 pre-signed URLs
- Handle timeout and resource limits
- Preserve working directory semantics


### 4. AgentCore Browser Integration

**Purpose:** Replace custom BrowserTool with AgentCore Browser

**Interface:**
```python
class AgentCoreBrowserAdapter:
    """Adapter for AgentCore Browser"""
    
    async def navigate(
        self,
        url: str,
        wait_for: Optional[str] = None
    ) -> dict:
        """
        Navigate to URL
        Returns: {html, screenshot, status}
        """
        pass
    
    async def extract_content(
        self,
        url: str,
        selectors: Optional[List[str]] = None
    ) -> dict:
        """
        Extract structured content from page
        Returns: {text, links, images, structured_data}
        """
        pass
    
    async def fill_form(
        self,
        form_data: dict,
        submit: bool = True
    ) -> dict:
        """
        Fill and optionally submit form
        Returns: {success, response_url, screenshot}
        """
        pass
    
    async def click_element(
        self,
        selector: str
    ) -> dict:
        """Click element by selector"""
        pass
    
    async def take_screenshot(
        self,
        full_page: bool = False
    ) -> str:
        """
        Take screenshot
        Returns: base64 encoded image
        """
        pass
```

**Implementation Details:**
- Map BrowserTool methods to AgentCore Browser API
- Handle session management automatically
- Store screenshots in S3
- Implement retry logic for navigation failures
- Preserve existing browser tool interface for backward compatibility

### 5. AgentCore Gateway Integration

**Purpose:** Replace Composio with AgentCore Gateway for MCP integration

AgentCore Gateway natively supports four target types:
1. **Lambda** - Custom business logic
2. **OpenAPI** - External REST APIs with OpenAPI specs
3. **Smithy Model** - AWS services (DynamoDB, S3, etc.)
4. **MCP Server** - Native MCP-compatible services (no proxy needed)

**Interface:**
```python
class AgentCoreGatewayAdapter:
    """Adapter for AgentCore Gateway with native MCP support"""
    
    async def create_gateway(
        self,
        account_id: str,
        name: str,
        enable_semantic_search: bool = True
    ) -> dict:
        """
        Create AgentCore Gateway for tenant
        Returns: {gateway_arn, gateway_url, gateway_id, client_id, client_secret}
        """
        pass
    
    async def add_mcp_target(
        self,
        gateway_arn: str,
        gateway_url: str,
        role_arn: str,
        name: str,
        mcp_server_url: str,
        credentials: Optional[dict] = None
    ) -> str:
        """
        Add MCP server as native Gateway target (no Lambda proxy needed)
        Returns: target_id
        """
        pass
    
    async def add_openapi_target(
        self,
        gateway_arn: str,
        gateway_url: str,
        role_arn: str,
        name: str,
        openapi_spec_url: str,
        credentials: Optional[dict] = None
    ) -> str:
        """
        Add OpenAPI service as Gateway target
        Returns: target_id
        """
        pass
    
    async def add_lambda_target(
        self,
        gateway_arn: str,
        gateway_url: str,
        role_arn: str,
        name: str,
        lambda_arn: str,
        tool_schema: dict
    ) -> str:
        """
        Add Lambda function as Gateway target for custom tools
        Returns: target_id
        """
        pass
    
    async def invoke_tool(
        self,
        gateway_url: str,
        oauth_token: str,
        tool_name: str,
        parameters: dict
    ) -> dict:
        """
        Invoke tool via Gateway MCP endpoint
        Returns: tool result
        """
        pass
    
    async def list_targets(
        self,
        gateway_name: str
    ) -> List[dict]:
        """List all targets for a Gateway"""
        pass
    
    async def delete_target(
        self,
        gateway_name: str,
        target_name: str
    ) -> bool:
        """Delete Gateway target"""
        pass
    
    async def delete_gateway(
        self,
        gateway_name: str,
        force: bool = False
    ) -> bool:
        """Delete Gateway and all targets"""
        pass
```

**Implementation Details:**
- Create one Gateway per tenant with Cognito OAuth2 authentication
- Add MCP servers directly as native `mcpServer` targets (no Lambda proxies)
- Add REST APIs as `openApiSchema` targets
- Add custom tools as `lambda` targets
- Gateway handles authentication, rate limiting, and monitoring automatically
- Store gateway credentials in Secrets Manager
- Use Gateway's built-in semantic search for tool discovery

### 6. AWS Secrets Manager Integration

**Purpose:** Replace Composio credential management with AWS Secrets Manager

**Interface:**
```python
class SecretsManagerAdapter:
    """Adapter for AWS Secrets Manager"""
    
    async def store_credential(
        self,
        account_id: str,
        service_name: str,
        credential_data: dict
    ) -> str:
        """
        Store credential in Secrets Manager
        Returns: secret_arn
        """
        pass
    
    async def retrieve_credential(
        self,
        account_id: str,
        service_name: str
    ) -> dict:
        """Retrieve credential from Secrets Manager"""
        pass
    
    async def update_credential(
        self,
        secret_arn: str,
        credential_data: dict
    ) -> bool:
        """Update existing credential"""
        pass
    
    async def delete_credential(
        self,
        secret_arn: str
    ) -> bool:
        """Delete credential"""
        pass
    
    async def list_credentials(
        self,
        account_id: str
    ) -> List[dict]:
        """List all credentials for account"""
        pass
```

**Implementation Details:**
- Organize secrets by tenant: `kortix/{account_id}/{service_name}`
- Use IAM policies for tenant isolation
- Implement automatic secret rotation for OAuth tokens
- Store secret_arn in database for quick lookup
- Handle secret versioning for rollback


### 7. MCP Catalog Service

**Purpose:** Replace Composio's embedded MCP server list with AWS-hosted catalog

**Interface:**
```python
class MCPCatalogService:
    """Service for managing MCP server catalog"""
    
    async def list_servers(
        self,
        search_query: Optional[str] = None,
        category: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> List[dict]:
        """
        List available MCP servers
        Filters by tenant permissions if account_id provided
        """
        pass
    
    async def get_server_details(
        self,
        server_id: str
    ) -> dict:
        """Get detailed server information"""
        pass
    
    async def add_server(
        self,
        server_config: dict,
        admin_user_id: str
    ) -> str:
        """
        Add new MCP server to catalog
        Returns: server_id
        """
        pass
    
    async def update_server(
        self,
        server_id: str,
        server_config: dict
    ) -> bool:
        """Update server configuration"""
        pass
    
    async def get_deployment_template(
        self,
        server_id: str
    ) -> dict:
        """Get AgentCore Gateway deployment template"""
        pass
```

**Storage Schema (DynamoDB):**
```python
{
    "server_id": "string (partition key)",
    "name": "string",
    "description": "string",
    "category": "string",
    "provider": "string",
    "version": "string",
    "schema": {
        "openapi_spec": "object",
        "authentication": {
            "type": "oauth2|api_key|none",
            "config": "object"
        }
    },
    "deployment_template": {
        "gateway_config": "object",
        "required_permissions": ["list"]
    },
    "tier_restrictions": {
        "free": "boolean",
        "pro": "boolean",
        "enterprise": "boolean"
    },
    "created_at": "timestamp",
    "updated_at": "timestamp"
}
```

### 8. OAuth Flow Service

**Purpose:** Replace Composio OAuth handling with AWS Cognito + Lambda

**Interface:**
```python
class OAuthFlowService:
    """Service for handling OAuth flows"""
    
    async def initiate_oauth_flow(
        self,
        account_id: str,
        service_name: str,
        redirect_uri: str
    ) -> dict:
        """
        Initiate OAuth flow
        Returns: {authorization_url, state}
        """
        pass
    
    async def handle_oauth_callback(
        self,
        code: str,
        state: str
    ) -> dict:
        """
        Handle OAuth callback
        Returns: {access_token, refresh_token, expires_at}
        """
        pass
    
    async def refresh_token(
        self,
        account_id: str,
        service_name: str
    ) -> dict:
        """
        Refresh OAuth token
        Returns: {access_token, expires_at}
        """
        pass
```

**Lambda Functions:**
1. **oauth-initiator**: Generates authorization URL
2. **oauth-callback-handler**: Processes OAuth callback
3. **token-refresher**: Scheduled function to refresh expiring tokens

**Implementation Details:**
- Use AWS Cognito for OAuth provider configuration
- Store OAuth state in DynamoDB with TTL
- Trigger token refresh via EventBridge scheduled rules
- Store tokens in Secrets Manager
- Implement PKCE for security


## Data Models

### Database Schema

**threads table:**
```sql
CREATE TABLE threads (
    thread_id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    project_id VARCHAR(255),
    agentcore_memory_id VARCHAR(255),
    agentcore_execution_id VARCHAR(255),
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_threads_account ON threads(account_id);
CREATE INDEX idx_threads_project ON threads(project_id);
```

**agent_versions table:**
```sql
CREATE TABLE agent_versions (
    version_id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    version_number INT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Metadata structure:
{
  "agentcore_deployment_id": "string",
  "agentcore_deployment_status": "deployed|failed|pending",
  "agentcore_deployment_timestamp": "timestamp"
}
```

**agent_runs table:**
```sql
CREATE TABLE agent_runs (
    run_id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

-- Metadata structure:
{
  "agentcore_execution_id": "string",
  "agentcore_runtime_version": "string",
  "primitives_used": {
    "code_interpreter": "boolean",
    "browser": "boolean",
    "memory": "boolean",
    "gateway": "boolean"
  }
}
```

**messages table:**
```sql
CREATE TABLE messages (
    message_id VARCHAR(255) PRIMARY KEY,
    thread_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE INDEX idx_messages_thread ON messages(thread_id);
```

**projects table:**
```sql
CREATE TABLE projects (
    project_id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_projects_account ON projects(account_id);
```

**New table: mcp_catalog**
```sql
CREATE TABLE mcp_catalog (
    server_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    provider VARCHAR(255),
    version VARCHAR(50),
    schema JSONB NOT NULL,
    deployment_template JSONB NOT NULL,
    tier_restrictions JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_mcp_catalog_category ON mcp_catalog(category);
CREATE INDEX idx_mcp_catalog_provider ON mcp_catalog(provider);
```

**New table: oauth_states**
```sql
CREATE TABLE oauth_states (
    state VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    redirect_uri TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_oauth_states_account ON oauth_states(account_id);
CREATE INDEX idx_oauth_states_expires ON oauth_states(expires_at);
```

**New table: gateway_deployments**
```sql
CREATE TABLE gateway_deployments (
    deployment_id VARCHAR(255) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL,
    server_id VARCHAR(255) NOT NULL,
    gateway_deployment_id VARCHAR(255) NOT NULL,
    config JSONB NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (server_id) REFERENCES mcp_catalog(server_id)
);

CREATE INDEX idx_gateway_deployments_account ON gateway_deployments(account_id);
CREATE INDEX idx_gateway_deployments_status ON gateway_deployments(status);
```

### Configuration Models

**AgentCore Deployment Configuration:**
```python
@dataclass
class AgentCoreDeploymentConfig:
    agent_id: str
    version_id: str
    runtime_version: str = "latest"
    memory_limit_mb: int = 2048
    timeout_seconds: int = 300
    environment_variables: Dict[str, str] = field(default_factory=dict)
    primitives_enabled: Dict[str, bool] = field(default_factory=lambda: {
        "code_interpreter": True,
        "browser": True,
        "memory": True,
        "gateway": True
    })
```

**Memory Resource Configuration:**
```python
@dataclass
class MemoryResourceConfig:
    thread_id: str
    account_id: str
    retention_days: int = 90
    semantic_search_enabled: bool = True
    max_messages: int = 10000
```

**Gateway Deployment Configuration:**
```python
@dataclass
class GatewayDeploymentConfig:
    server_id: str
    account_id: str
    authentication: Dict[str, Any]
    enabled_tools: List[str]
    rate_limits: Dict[str, int] = field(default_factory=lambda: {
        "requests_per_minute": 60,
        "requests_per_day": 10000
    })
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: AgentCore Runtime Routing
*For any* agent run initiation, the system should invoke AgentCore Runtime APIs and not create Dramatiq tasks
**Validates: Requirements 1.1**

### Property 2: Concurrent Execution Scaling
*For any* set of concurrent agent runs, all runs should complete successfully without manual scaling configuration
**Validates: Requirements 1.2**

### Property 3: Execution Result Persistence
*For any* completed agent run, the database should contain a record with correct status and execution results
**Validates: Requirements 1.3**

### Property 4: Code Execution Routing
*For any* code execution request, the system should invoke AgentCore Code Interpreter APIs and not create Docker containers
**Validates: Requirements 2.1**

### Property 5: File Storage Compatibility
*For any* file upload, the file should be stored in S3 with AgentCore-compatible paths and be accessible to Code Interpreter
**Validates: Requirements 2.5**

### Property 6: Browser Automation Routing
*For any* browser automation request, the system should invoke AgentCore Browser APIs and not use custom BrowserTool
**Validates: Requirements 3.1**

### Property 7: Memory Resource Creation
*For any* new thread creation, an AgentCore Memory resource should be initialized and its ID stored in the thread record
**Validates: Requirements 4.1**

### Property 8: Message Storage in Memory
*For any* message added to a thread, the message should be stored in AgentCore Memory and retrievable with correct metadata
**Validates: Requirements 4.2**

### Property 9: Gateway Deployment Routing
*For any* MCP server configuration, the system should deploy to AgentCore Gateway and not use Composio APIs
**Validates: Requirements 5.1**

### Property 10: Catalog Data Source
*For any* MCP catalog query, the system should retrieve data from DynamoDB/S3 and not from Composio
**Validates: Requirements 5A.1**

### Property 11: OAuth Flow Routing
*For any* OAuth initiation, the system should use AWS Cognito/Lambda flows and not Composio authentication
**Validates: Requirements 5B.1**

### Property 12: Credential Storage Location
*For any* credential storage operation, credentials should be stored in AWS Secrets Manager with correct tenant isolation
**Validates: Requirements 5B.2**

### Property 13: ThreadManager Interface Compatibility
*For any* existing ThreadManager method call, the method should execute successfully with the same signature
**Validates: Requirements 6.1**

### Property 14: Tool Routing Logic
*For any* tool execution request, the system should route to the correct AgentCore primitive based on tool type
**Validates: Requirements 6.2**

### Property 15: Billing Integration
*For any* completed agent run, credit deduction should occur with token counts matching AgentCore usage data
**Validates: Requirements 7.1**

### Property 16: API Endpoint Behavior
*For any* POST /api/agent/start request, the system should create an agent run via AgentCore Runtime
**Validates: Requirements 8.1**

### Property 17: Streaming Functionality
*For any* agent run with streaming enabled, the SSE stream should deliver AgentCore responses in real-time
**Validates: Requirements 8.2**

### Property 18: Deployment Packaging
*For any* agent creation or update, the system should generate a valid AgentCore deployment package
**Validates: Requirements 10.1**

### Property 19: Deployment ID Persistence
*For any* successful deployment, the deployment ID should be stored in the database and retrievable
**Validates: Requirements 10.3**

### Property 20: Memory Fallback Behavior
*For any* message retrieval when AgentCore Memory is unavailable, the system should fall back to database retrieval
**Validates: Requirements 13.2**

### Property 21: Tenant Execution Isolation
*For any* two agent runs from different tenants, the executions should be isolated with no data leakage
**Validates: Requirements 15.1**

### Property 22: Memory Partitioning
*For any* AgentCore Memory resource, it should be partitioned by tenant account_id with no cross-tenant access
**Validates: Requirements 15.2**

### Property 23: Credential Access Isolation
*For any* Gateway API call, the system should enforce that tenants can only access their own credentials
**Validates: Requirements 15.3**

### Property 24: Memory Storage Integrity
*For any* conversation thread, messages stored in AgentCore Memory should be retrievable with correct content and metadata
**Validates: Requirements 16.3**

### Property 25: Lock Mechanism Replacement
*For any* agent run requiring coordination, the system should not use Redis locks and should rely on AgentCore isolation
**Validates: Requirements 19.1**

### Property 26: Streaming Mechanism Replacement
*For any* response streaming, the system should use AgentCore streaming APIs and not Redis pub/sub
**Validates: Requirements 19.2**

### Property 27: Environment Configuration
*For any* agent run, the system should use AgentCore resources matching the configured environment (dev/prod)
**Validates: Requirements 20.2, 20.3**


## Error Handling

### AgentCore Runtime Errors

**Deployment Failures:**
- Catch deployment errors and log detailed error messages
- Store deployment status as "failed" in agent_versions metadata
- Return user-friendly error message to frontend
- Maintain previous deployment for rollback

**Execution Failures:**
- Capture AgentCore execution errors and stack traces
- Update agent_run status to "failed" with error details
- Send failure notification to user
- Log error to observability platform (Langfuse, CloudWatch)

**Timeout Handling:**
- Set reasonable timeout limits (default: 300 seconds)
- Cancel execution if timeout exceeded
- Update run status to "timeout"
- Return partial results if available

### AgentCore Memory Errors

**Resource Creation Failures:**
- Fall back to database-only mode for the thread
- Log warning and continue execution
- Set flag in thread metadata to retry later

**Storage Failures:**
- Retry with exponential backoff (3 attempts)
- Fall back to database storage if all retries fail
- Log error for investigation

**Retrieval Failures:**
- Fall back to database retrieval
- Log warning about degraded performance
- Continue execution with database data

### AgentCore Code Interpreter Errors

**Execution Errors:**
- Capture stderr and exit codes
- Return error details to agent for handling
- Log execution failures for debugging

**Timeout Errors:**
- Cancel execution after timeout
- Return timeout error to agent
- Clean up any partial results

**File Operation Errors:**
- Retry file uploads/downloads (3 attempts)
- Return clear error messages
- Fall back to database storage if needed

### AgentCore Browser Errors

**Navigation Failures:**
- Retry navigation (2 attempts)
- Return error if page unreachable
- Capture screenshot of error state

**Element Not Found:**
- Return descriptive error to agent
- Suggest alternative selectors
- Provide page HTML for debugging

**Timeout Errors:**
- Cancel browser operation
- Return partial results if available
- Clean up browser session

### AgentCore Gateway Errors

**Deployment Failures:**
- Log deployment error details
- Mark deployment as "failed" in database
- Disable affected MCP tools
- Notify user of deployment failure

**API Call Failures:**
- Retry with exponential backoff (3 attempts)
- Return error to agent after retries exhausted
- Log API errors for investigation

**Authentication Errors:**
- Check if credentials expired
- Attempt token refresh if OAuth
- Return clear authentication error to user
- Prompt for re-authentication if needed

### AWS Service Errors

**Secrets Manager Errors:**
- Retry with exponential backoff
- Cache credentials to reduce API calls
- Return error if secret not found
- Log IAM permission errors

**DynamoDB Errors:**
- Retry with exponential backoff
- Use eventual consistency for reads
- Handle throttling with backoff
- Log capacity errors

**S3 Errors:**
- Retry uploads/downloads (3 attempts)
- Use multipart upload for large files
- Handle access denied errors
- Log bucket permission errors

### Fallback Strategy

**Priority Order:**
1. Try AgentCore primitive
2. Retry with exponential backoff (if transient error)
3. Fall back to database/legacy system (if available)
4. Return error to user with clear message

**Graceful Degradation:**
- Disable unavailable features rather than failing completely
- Show warning messages to users
- Log degraded state for monitoring
- Attempt recovery on next request


## Testing Strategy

### Unit Testing

**Adapter Layer Tests:**
- Test each AgentCore adapter (Runtime, Memory, Code Interpreter, Browser, Gateway)
- Mock AgentCore API responses
- Verify correct API calls with expected parameters
- Test error handling and retry logic
- Verify fallback behavior

**Service Layer Tests:**
- Test MCP Catalog Service CRUD operations
- Test OAuth Flow Service with mocked Cognito
- Test Secrets Manager Adapter with mocked AWS SDK
- Verify tenant isolation logic
- Test configuration validation

**Integration Tests:**
- Test end-to-end agent run flow with AgentCore
- Test file upload/download through Code Interpreter
- Test browser automation scenarios
- Test MCP tool invocation through Gateway
- Test OAuth flow completion
- Verify database persistence

### Property-Based Testing

**Property Test Framework:** Use Hypothesis (Python) for property-based testing

**Test Configuration:**
- Minimum 100 iterations per property test
- Generate random agent configurations, thread IDs, tenant IDs
- Use property test generators for realistic data

**Property Test 1: AgentCore Runtime Routing**
```python
@given(agent_run_request=agent_run_strategy())
def test_agentcore_runtime_routing(agent_run_request):
    """
    Feature: agentcore-migration, Property 1: AgentCore Runtime Routing
    For any agent run initiation, verify AgentCore Runtime APIs are called
    """
    result = initiate_agent_run(agent_run_request)
    assert result.used_agentcore_runtime == True
    assert result.used_dramatiq == False
```

**Property Test 2: Concurrent Execution Scaling**
```python
@given(concurrent_runs=st.lists(agent_run_strategy(), min_size=2, max_size=10))
def test_concurrent_execution_scaling(concurrent_runs):
    """
    Feature: agentcore-migration, Property 2: Concurrent Execution Scaling
    For any set of concurrent runs, all should complete successfully
    """
    results = execute_concurrent_runs(concurrent_runs)
    assert all(r.status == "completed" for r in results)
    assert no_manual_scaling_occurred()
```

**Property Test 3: Execution Result Persistence**
```python
@given(agent_run=agent_run_strategy())
def test_execution_result_persistence(agent_run):
    """
    Feature: agentcore-migration, Property 3: Execution Result Persistence
    For any completed run, database should contain correct record
    """
    result = execute_agent_run(agent_run)
    db_record = get_agent_run_from_db(result.agent_run_id)
    assert db_record.status == result.status
    assert db_record.execution_results == result.execution_results
```

**Property Test 7: Memory Resource Creation**
```python
@given(thread_data=thread_strategy())
def test_memory_resource_creation(thread_data):
    """
    Feature: agentcore-migration, Property 7: Memory Resource Creation
    For any new thread, AgentCore Memory resource should be initialized
    """
    thread = create_thread(thread_data)
    assert thread.agentcore_memory_id is not None
    memory_resource = get_memory_resource(thread.agentcore_memory_id)
    assert memory_resource.exists == True
```

**Property Test 12: Credential Storage Location**
```python
@given(credential=credential_strategy(), account_id=account_id_strategy())
def test_credential_storage_location(credential, account_id):
    """
    Feature: agentcore-migration, Property 12: Credential Storage Location
    For any credential storage, should use Secrets Manager with tenant isolation
    """
    secret_arn = store_credential(account_id, credential)
    assert secret_arn.startswith(f"arn:aws:secretsmanager")
    assert f"kortix/{account_id}/" in secret_arn
    # Verify other tenants cannot access
    with pytest.raises(PermissionError):
        retrieve_credential(other_account_id, credential.service_name)
```

**Property Test 21: Tenant Execution Isolation**
```python
@given(
    tenant1_run=agent_run_strategy(),
    tenant2_run=agent_run_strategy()
)
def test_tenant_execution_isolation(tenant1_run, tenant2_run):
    """
    Feature: agentcore-migration, Property 21: Tenant Execution Isolation
    For any two runs from different tenants, executions should be isolated
    """
    assume(tenant1_run.account_id != tenant2_run.account_id)
    
    result1 = execute_agent_run(tenant1_run)
    result2 = execute_agent_run(tenant2_run)
    
    # Verify no data leakage
    assert result1.memory_resource_id != result2.memory_resource_id
    assert result1.execution_context != result2.execution_context
    assert no_shared_resources(result1, result2)
```

**Property Test 24: Memory Storage Integrity**
```python
@given(thread_with_messages=thread_with_messages_strategy())
def test_memory_storage_integrity(thread_with_messages):
    """
    Feature: agentcore-migration, Property 24: Memory Storage Integrity
    For any thread with messages, AgentCore Memory should store and retrieve data correctly
    """
    # Store messages in AgentCore Memory
    for message in thread_with_messages.messages:
        store_message_in_memory(thread_with_messages.agentcore_memory_id, message)
    
    # Retrieve messages from AgentCore Memory
    retrieved_messages = get_messages_from_memory(thread_with_messages.agentcore_memory_id)
    
    assert len(thread_with_messages.messages) == len(retrieved_messages)
    for original, retrieved in zip(thread_with_messages.messages, retrieved_messages):
        assert original.content == retrieved.content
        assert original.metadata == retrieved.metadata
```

**Property Test 27: Environment Configuration**
```python
@given(
    agent_run=agent_run_strategy(),
    environment=st.sampled_from(['development', 'production'])
)
def test_environment_configuration(agent_run, environment):
    """
    Feature: agentcore-migration, Property 27: Environment Configuration
    For any run, should use correct AgentCore resources for environment
    """
    set_environment(environment)
    result = execute_agent_run(agent_run)
    
    expected_resource_prefix = f"agentcore-{environment}"
    assert result.agentcore_deployment_id.startswith(expected_resource_prefix)
    assert result.used_agentcore_runtime == True
```

### Integration Testing

**End-to-End Scenarios:**
1. Complete agent run with Code Interpreter usage
2. Browser automation workflow
3. MCP tool invocation through Gateway
4. OAuth flow completion and credential storage
5. Multi-tenant concurrent execution
6. Fallback to database when AgentCore unavailable

**Performance Testing:**
- Load test with 100 concurrent agent runs
- Measure latency for AgentCore API calls
- Test memory resource creation at scale
- Verify auto-scaling behavior
- Monitor cost per execution

**Deployment Testing:**
- Test initial deployment to development environment
- Verify all AgentCore services are accessible
- Test environment configuration switching
- Validate production deployment readiness
- Test disaster recovery procedures


## MCP Integration Deep Dive

### MCP Protocol Support in AgentCore Gateway

**Gateway Capabilities:**
- AgentCore Gateway natively supports MCP servers as a target type
- No Lambda proxies needed for SSE or WebSocket MCP servers
- Gateway handles authentication, rate limiting, and monitoring automatically
- Built-in OAuth2 via Cognito for secure access

**Native MCP Target Configuration:**
```python
class MCPTargetManager:
    """Manages MCP servers as native Gateway targets"""
    
    async def add_mcp_server(
        self,
        gateway_arn: str,
        gateway_url: str,
        role_arn: str,
        mcp_config: dict
    ) -> str:
        """
        Add MCP server directly as Gateway target
        
        Gateway natively supports:
        - SSE (Server-Sent Events) MCP servers
        - HTTP/REST MCP servers
        - WebSocket MCP servers
        
        No Lambda proxy required - Gateway handles all protocols natively.
        
        Returns: target_id
        """
        # Use agentcore CLI or SDK to create target
        target_payload = {
            "endpoint": mcp_config['url'],
            "protocol": mcp_config.get('protocol', 'sse')
        }
        
        credentials = None
        if mcp_config.get('authentication'):
            credentials = self._build_credentials(mcp_config['authentication'])
        
        return await self._create_gateway_target(
            gateway_arn=gateway_arn,
            gateway_url=gateway_url,
            role_arn=role_arn,
            name=mcp_config['name'],
            target_type="mcpServer",
            target_payload=target_payload,
            credentials=credentials
        )
    
    def _build_credentials(self, auth_config: dict) -> dict:
        """Build credentials for MCP server authentication"""
        auth_type = auth_config.get('type')
        
        if auth_type == 'api_key':
            return {
                "api_key": auth_config['api_key'],
                "credential_location": auth_config.get('location', 'header'),
                "credential_parameter_name": auth_config.get('header_name', 'Authorization')
            }
        elif auth_type == 'oauth2':
            return {
                "oauth2_provider_config": {
                    "customOauth2ProviderConfig": {
                        "oauthDiscovery": {
                            "discoveryUrl": auth_config['discovery_url']
                        },
                        "clientId": auth_config['client_id'],
                        "clientSecret": auth_config['client_secret']
                    }
                },
                "scopes": auth_config.get('scopes', [])
            }
        return None

### MCP Configuration Management

**MCPConfigurationService:**

```python
class MCPConfigurationService:
    """Service to manage MCP configurations and Gateway targets"""
    
    def __init__(self):
        self.gateway_adapter = AgentCoreGatewayAdapter()
        self.catalog_service = MCPCatalogService()
        self.secrets_adapter = SecretsManagerAdapter()
    
    async def ensure_tenant_gateway(
        self,
        account_id: str
    ) -> dict:
        """
        Ensure tenant has a Gateway, create if not exists
        
        Returns: {gateway_arn, gateway_url, role_arn, client_id, client_secret}
        """
        # Check if gateway exists for tenant
        existing = await self._get_tenant_gateway(account_id)
        if existing:
            return existing
        
        # Create new gateway for tenant
        gateway_name = f"kortix-{account_id}"
        gateway_info = await self.gateway_adapter.create_gateway(
            account_id=account_id,
            name=gateway_name,
            enable_semantic_search=True
        )
        
        # Store gateway credentials in Secrets Manager
        await self.secrets_adapter.store_credential(
            account_id=account_id,
            service_name="agentcore_gateway",
            credential_data={
                "gateway_arn": gateway_info["gateway_arn"],
                "gateway_url": gateway_info["gateway_url"],
                "role_arn": gateway_info["role_arn"],
                "client_id": gateway_info["client_id"],
                "client_secret": gateway_info["client_secret"]
            }
        )
        
        return gateway_info
    
    async def configure_agent_mcps(
        self,
        agent_id: str,
        account_id: str,
        mcp_configs: List[dict]
    ) -> dict:
        """
        Configure MCP servers for an agent as native Gateway targets
        
        Returns: {
            "configured_count": int,
            "failed_count": int,
            "target_ids": List[str]
        }
        """
        # Ensure tenant has a gateway
        gateway_info = await self.ensure_tenant_gateway(account_id)
        
        results = {
            "configured_count": 0,
            "failed_count": 0,
            "target_ids": []
        }
        
        for mcp in mcp_configs:
            try:
                target_id = await self._add_mcp_target(mcp, gateway_info, account_id)
                results["target_ids"].append(target_id)
                results["configured_count"] += 1
            except Exception as e:
                logger.error(f"Failed to configure MCP {mcp['name']}: {e}")
                results["failed_count"] += 1
        
        return results
    
    async def _add_mcp_target(
        self,
        mcp_config: dict,
        gateway_info: dict,
        account_id: str
    ) -> str:
        """Add MCP server as native Gateway target"""
        # Get MCP definition from catalog
        server_id = mcp_config.get('server_id')
        catalog_entry = await self.catalog_service.get_server_details(server_id)
        
        # Retrieve credentials if needed
        credentials = None
        if catalog_entry.get('authentication'):
            credentials = await self._get_mcp_credentials(
                account_id, server_id, catalog_entry['authentication']
            )
        
        # Add as native MCP target (no Lambda proxy needed)
        target_id = await self.gateway_adapter.add_mcp_target(
            gateway_arn=gateway_info["gateway_arn"],
            gateway_url=gateway_info["gateway_url"],
            role_arn=gateway_info["role_arn"],
            name=catalog_entry["name"],
            mcp_server_url=catalog_entry["url"],
            credentials=credentials
        )
        
        # Store target record
        await self._store_target_record(
            account_id=account_id,
            server_id=server_id,
            target_id=target_id
        )
        
        return target_id
```

### MCP Catalog Seeding

**Initial Catalog Population:**

```python
# Seed script for MCP catalog
INITIAL_MCP_SERVERS = [
    {
        "server_id": "github",
        "name": "GitHub",
        "description": "GitHub API integration",
        "category": "development",
        "provider": "github",
        "schema": {
            "openapi_spec": "https://api.github.com/openapi.json",
            "authentication": {
                "type": "oauth2",
                "config": {
                    "authorization_url": "https://github.com/login/oauth/authorize",
                    "token_url": "https://github.com/login/oauth/access_token",
                    "scopes": ["repo", "user"]
                }
            }
        },
        "deployment_template": {
            "gateway_config": {
                "type": "openapi",
                "base_url": "https://api.github.com"
            }
        },
        "tier_restrictions": {
            "free": True,
            "pro": True,
            "enterprise": True
        }
    },
    # Add more popular MCP servers...
]

async def seed_mcp_catalog():
    """Seed initial MCP catalog with popular servers"""
    catalog_service = MCPCatalogService()
    
    for server in INITIAL_MCP_SERVERS:
        await catalog_service.add_server(
            server_config=server,
            admin_user_id="system"
        )
```

### Composio Feature Parity

**Features to Replicate:**

1. **Embedded MCP List** → DynamoDB Catalog ✅
2. **OAuth Handling** → Gateway's built-in Cognito OAuth2 ✅
3. **Credential Storage** → Secrets Manager ✅
4. **MCP Server Discovery** → Catalog API ✅
5. **Tool Filtering** → Gateway semantic search ✅

**Additional Considerations:**

**MCP Server Configuration:**
- System supports standard MCP server configurations
- Users can configure MCP servers from the catalog
- Custom MCP servers can be added by administrators
- All MCP servers added as native Gateway targets (no proxies)

### Confidence Assessment

**High Confidence (8/10):**
- AgentCore Gateway natively supports MCP servers as a target type
- SSE, HTTP, and WebSocket MCP servers work without Lambda proxies
- OAuth flows are built into Gateway via Cognito
- Secrets Manager provides robust credential storage
- DynamoDB catalog is straightforward
- Gateway handles rate limiting and monitoring automatically

**Medium Confidence (7/10):**
- Initial catalog seeding needs manual curation
- MCP protocol version compatibility needs testing
- Per-tenant Gateway costs need monitoring

**Risks & Mitigations:**

1. **Risk:** MCP protocol version compatibility
   **Mitigation:** Test with major MCP servers, document supported protocol versions

2. **Risk:** Gateway cost at scale
   **Mitigation:** Monitor Gateway usage per tenant, implement usage quotas

3. **Risk:** Limited MCP catalog at launch
   **Mitigation:** Start with 10-15 popular integrations, allow custom MCP server URLs

4. **Risk:** Gateway cold start latency
   **Mitigation:** Keep Gateway warm with periodic health checks

**Recommendation:**
The MCP integration plan leverages AgentCore Gateway's native MCP support, eliminating the need for custom Lambda proxies. This significantly reduces complexity and improves reliability. Key implementation steps:
1. Create one Gateway per tenant with semantic search enabled
2. Add MCP servers as native `mcpServer` targets
3. Use Gateway's built-in OAuth2 for authentication
4. Store tenant Gateway credentials in Secrets Manager
5. Provide catalog UI for MCP server discovery and configuration

