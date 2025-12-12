# Design Document: Obot MCP Integration

## Overview

This design describes the integration of Obot as a self-hosted MCP Gateway sidecar for the Suna AI agent platform. The integration replaces the managed Composio service with Obot, providing enterprise-grade MCP server management including server discovery, authentication, credential management, and access control.

The architecture follows a sidecar pattern where Obot runs alongside Suna as a companion service. Suna's backend communicates with Obot's REST API for MCP operations, while Obot handles the actual MCP server connections, OAuth flows, and credential storage.

### Key Integration Points with Obot

Based on Obot's API structure, the integration will use:

1. **MCP Catalog Entries API** (`/api/all-mcps/entries`) - For discovering available MCP servers
2. **MCP Servers API** (`/api/mcp-servers`) - For creating/managing user-scoped MCP server instances
3. **MCP Tools API** (`/api/mcp-servers/{id}/tools`) - For listing and executing tools
4. **MCP Gateway** (`/mcp/{mcp_id}`) - For proxying MCP protocol requests
5. **Bootstrap Token Authentication** - For initial admin setup and API access

### User Identity Strategy

Obot uses its own user management system with authentication providers. For Suna integration, we will:

1. Use Obot's bootstrap token for admin operations
2. Create Obot users programmatically via API when Suna users first access MCP
3. Generate per-user JWT tokens for Obot API calls using Obot's token endpoint
4. Store the Suna-to-Obot user mapping in Supabase

## Architecture

### Obot Deployment Configuration

Obot will be deployed as a Docker container alongside Suna with the following configuration:

```yaml
# docker-compose addition for Obot sidecar
obot:
  image: ghcr.io/obot-platform/obot:latest
  ports:
    - "8081:8080"  # Internal port, not exposed externally
  environment:
    # Disable chat UI, keep admin and gateway
    OBOT_SERVER_ENABLE_AUTHENTICATION: "true"
    OBOT_BOOTSTRAP_TOKEN: "${OBOT_BOOTSTRAP_TOKEN}"
    OBOT_SERVER_AUTH_ADMIN_EMAILS: "${ADMIN_EMAILS}"
    # Database (separate from Suna)
    OBOT_DATABASE_DSN: "postgres://obot:password@postgres:5432/obot"
    # Model provider (can use same as Suna or separate)
    OPENAI_API_KEY: "${OPENAI_API_KEY}"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # For MCP server containers
  depends_on:
    - postgres
```

Key environment variables for Suna backend:
```env
OBOT_BASE_URL=http://obot:8080/api
OBOT_BOOTSTRAP_TOKEN=<generated-secure-token>
OBOT_ENABLED=true
```

```mermaid
graph TB
    subgraph "Suna Platform"
        FE[Frontend/Mobile]
        BE[Backend API]
        DB[(Supabase DB)]
        Agent[Agent Runtime]
    end
    
    subgraph "Obot Sidecar"
        OA[Obot API]
        OG[MCP Gateway]
        OAdmin[Admin GUI]
        ODB[(Obot DB)]
    end
    
    subgraph "External Services"
        MCP1[MCP Server 1]
        MCP2[MCP Server 2]
        OAuth[OAuth Providers]
    end
    
    FE --> BE
    BE --> OA
    BE --> DB
    Agent --> BE
    
    OA --> OG
    OA --> ODB
    OG --> MCP1
    OG --> MCP2
    OA --> OAuth
    
    OAdmin -.-> OA
```

### Key Design Decisions

1. **Sidecar Deployment**: Obot runs as a separate container/process alongside Suna, communicating via internal HTTP API. This provides isolation and allows independent scaling.

2. **User Identity Mapping**: Suna user IDs (UUIDs from Supabase) are mapped to Obot users using a deterministic hash-based approach. This ensures consistent identity across requests without requiring user synchronization.

3. **JWT-Based Authentication**: Suna generates JWT tokens for Obot API calls, signed with a shared secret. Obot validates these tokens and extracts user identity.

4. **Profile Storage Split**: User-facing profile metadata is stored in Suna's Supabase (for UI queries), while actual MCP credentials and server state are stored in Obot's database.

5. **Disabled Chat Interface**: Obot's built-in chat UI is disabled via configuration, exposing only the Admin GUI and MCP Gateway endpoints.

## Components and Interfaces

### 1. Obot Client Service (`backend/core/obot/client.py`)

A Python client for communicating with Obot's REST API. Based on Obot's actual API endpoints.

```python
class ObotClient:
    """Client for Obot MCP Gateway API"""
    
    def __init__(self, base_url: str, bootstrap_token: str):
        self.base_url = base_url  # e.g., "http://obot:8080/api"
        self.bootstrap_token = bootstrap_token
        self._http_client = httpx.AsyncClient(timeout=30.0)
    
    # === Authentication ===
    async def get_token_for_user(self, obot_user_id: str) -> str:
        """Get API token for a specific Obot user"""
        pass
    
    # === MCP Catalog Entries (GET /api/all-mcps/entries) ===
    async def list_catalog_entries(self, token: str) -> List[MCPCatalogEntry]:
        """List available MCP servers from all sources (catalogs + workspaces)"""
        pass
    
    async def get_catalog_entry(self, token: str, entry_id: str) -> MCPCatalogEntry:
        """Get details of a specific catalog entry (GET /api/all-mcps/entries/{entry_id})"""
        pass
    
    # === MCP Servers (User-deployed instances) ===
    async def list_mcp_servers(self, token: str) -> List[MCPServer]:
        """List user's MCP server instances (GET /api/mcp-servers)"""
        pass
    
    async def create_mcp_server(self, token: str, request: CreateMCPServerRequest) -> MCPServer:
        """Create MCP server instance from catalog entry (POST /api/mcp-servers)"""
        pass
    
    async def get_mcp_server(self, token: str, server_id: str) -> MCPServer:
        """Get MCP server details (GET /api/mcp-servers/{mcp_server_id})"""
        pass
    
    async def update_mcp_server(self, token: str, server_id: str, request: UpdateMCPServerRequest) -> MCPServer:
        """Update MCP server configuration (PUT /api/mcp-servers/{mcp_server_id})"""
        pass
    
    async def delete_mcp_server(self, token: str, server_id: str) -> None:
        """Delete MCP server instance (DELETE /api/mcp-servers/{mcp_server_id})"""
        pass
    
    # === MCP Server Tools ===
    async def list_tools(self, token: str, server_id: str) -> List[MCPTool]:
        """List tools from MCP server (GET /api/mcp-servers/{mcp_server_id}/tools)"""
        pass
    
    async def set_tools(self, token: str, server_id: str, tool_names: List[str]) -> None:
        """Set allowed tools for MCP server (PUT /api/mcp-servers/{mcp_server_id}/tools)"""
        pass
    
    # === MCP Server Resources ===
    async def list_resources(self, token: str, server_id: str) -> List[MCPResource]:
        """List resources from MCP server (GET /api/mcp-servers/{mcp_server_id}/resources)"""
        pass
    
    async def read_resource(self, token: str, server_id: str, resource_uri: str) -> Any:
        """Read a specific resource (GET /api/mcp-servers/{mcp_server_id}/resources/{resource_uri})"""
        pass
    
    # === MCP Server Prompts ===
    async def list_prompts(self, token: str, server_id: str) -> List[MCPPrompt]:
        """List prompts from MCP server (GET /api/mcp-servers/{mcp_server_id}/prompts)"""
        pass
    
    async def get_prompt(self, token: str, server_id: str, prompt_name: str) -> MCPPrompt:
        """Get a specific prompt (GET /api/mcp-servers/{mcp_server_id}/prompts/{prompt_name})"""
        pass
    
    # === MCP Server Lifecycle ===
    async def launch_server(self, token: str, server_id: str) -> None:
        """Launch/start MCP server (POST /api/mcp-servers/{mcp_server_id}/launch)"""
        pass
    
    async def check_oauth(self, token: str, server_id: str) -> bool:
        """Check if OAuth is required (POST /api/mcp-servers/{mcp_server_id}/check-oauth)"""
        pass
    
    async def get_oauth_url(self, token: str, server_id: str) -> str:
        """Get OAuth authorization URL (POST /api/mcp-servers/{mcp_server_id}/oauth-url)"""
        pass
    
    # === MCP Server Credentials ===
    async def configure_credentials(self, token: str, server_id: str, credentials: dict) -> None:
        """Configure credentials for MCP server (POST /api/mcp-servers/{mcp_server_id}/configure)"""
        pass
    
    async def deconfigure_credentials(self, token: str, server_id: str) -> None:
        """Remove credentials (POST /api/mcp-servers/{mcp_server_id}/deconfigure)"""
        pass
    
    # === Health ===
    async def check_health(self) -> bool:
        """Check Obot service health (GET /api/version)"""
        pass
```

### 2. User Identity Service (`backend/core/obot/identity_service.py`)

Handles mapping between Suna and Obot user identities. Since Obot has its own user management, we need to create Obot users for Suna users and maintain the mapping.

```python
class ObotIdentityService:
    """Manages Suna-to-Obot user identity mapping"""
    
    def __init__(self, db: DBConnection, obot_client: ObotClient):
        self.db = db
        self.obot_client = obot_client
    
    async def get_or_create_obot_user(self, suna_user_id: str, email: Optional[str] = None) -> ObotUserMapping:
        """
        Get existing Obot user mapping or create new Obot user.
        
        1. Check obot_user_mappings table for existing mapping
        2. If not found, create Obot user via API and store mapping
        3. Return the mapping with Obot user ID and token
        """
        pass
    
    async def get_obot_token(self, suna_user_id: str) -> str:
        """
        Get valid Obot API token for a Suna user.
        
        1. Look up Obot user mapping
        2. Check if cached token is still valid
        3. If expired, refresh token via Obot API
        4. Return valid token
        """
        pass
    
    async def delete_obot_user(self, suna_user_id: str) -> bool:
        """
        Delete Obot user when Suna user is deleted.
        
        1. Look up mapping
        2. Delete Obot user via API (if supported)
        3. Remove mapping from database
        """
        pass
    
    def generate_obot_username(self, suna_user_id: str, email: Optional[str] = None) -> str:
        """
        Generate deterministic Obot username from Suna user data.
        Format: suna_{hash(suna_user_id)[:12]}
        """
        pass
```

### 3. Obot Integration API (`backend/core/obot/api.py`)

FastAPI router exposing Obot functionality to Suna frontend.

```python
router = APIRouter(prefix="/obot", tags=["obot"])

@router.get("/catalog")
async def list_catalog(user_id: str = Depends(verify_and_get_user_id_from_jwt)):
    """List available MCP servers from Obot catalog"""
    pass

@router.get("/catalog/{entry_id}")
async def get_catalog_entry(entry_id: str, user_id: str = Depends(...)):
    """Get detailed info about a catalog entry"""
    pass

@router.post("/servers")
async def create_server(request: CreateServerRequest, user_id: str = Depends(...)):
    """Create a new MCP server connection for the user"""
    pass

@router.get("/servers")
async def list_servers(user_id: str = Depends(...)):
    """List user's MCP server connections"""
    pass

@router.delete("/servers/{server_id}")
async def delete_server(server_id: str, user_id: str = Depends(...)):
    """Delete an MCP server connection"""
    pass

@router.get("/servers/{server_id}/tools")
async def list_tools(server_id: str, user_id: str = Depends(...)):
    """List tools from an MCP server"""
    pass

@router.post("/servers/{server_id}/tools/{tool_name}")
async def call_tool(server_id: str, tool_name: str, request: ToolCallRequest, user_id: str = Depends(...)):
    """Execute an MCP tool"""
    pass

@router.get("/servers/{server_id}/oauth")
async def get_oauth_url(server_id: str, user_id: str = Depends(...)):
    """Get OAuth URL for MCP server authentication"""
    pass

@router.get("/health")
async def health_check():
    """Check Obot service health"""
    pass
```

### 4. Obot Profile Service (`backend/core/obot/profile_service.py`)

Manages user MCP profiles stored in Suna's database.

```python
class ObotProfileService:
    """Manages Obot MCP profiles in Suna's database"""
    
    def __init__(self, db: DBConnection):
        self.db = db
    
    async def create_profile(
        self,
        account_id: str,
        obot_server_id: str,
        catalog_entry_id: str,
        display_name: str,
        icon_url: Optional[str] = None
    ) -> ObotProfile:
        """Create a new Obot profile record"""
        pass
    
    async def get_profiles(self, account_id: str) -> List[ObotProfile]:
        """Get all profiles for a user"""
        pass
    
    async def get_profile(self, profile_id: str, account_id: str) -> Optional[ObotProfile]:
        """Get a specific profile"""
        pass
    
    async def delete_profile(self, profile_id: str, account_id: str) -> bool:
        """Delete a profile"""
        pass
    
    async def update_profile_status(self, profile_id: str, status: str) -> None:
        """Update profile connection status"""
        pass
```

### 5. MCP Tool Wrapper (`backend/core/tools/obot_mcp_tool.py`)

Wraps Obot MCP tools for use in Suna's agent framework.

```python
class ObotMCPToolWrapper(Tool):
    """Wrapper for Obot MCP tools in Suna's agent framework"""
    
    def __init__(self, obot_client: ObotClient, server_id: str, tool_def: MCPTool):
        self.obot_client = obot_client
        self.server_id = server_id
        self.tool_def = tool_def
    
    @property
    def name(self) -> str:
        return f"obot_{self.server_id}_{self.tool_def.name}"
    
    @property
    def description(self) -> str:
        return self.tool_def.description
    
    @property
    def parameters(self) -> dict:
        return self.tool_def.input_schema
    
    async def execute(self, user_id: str, **kwargs) -> ToolResult:
        """Execute the MCP tool through Obot"""
        pass
```

## Data Models

### Obot Profile Table (Supabase)

```sql
CREATE TABLE obot_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    obot_server_id VARCHAR(255) NOT NULL,
    catalog_entry_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    icon_url TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(account_id, obot_server_id)
);

CREATE INDEX idx_obot_profiles_account ON obot_profiles(account_id);
CREATE INDEX idx_obot_profiles_server ON obot_profiles(obot_server_id);
```

### Obot User Mapping Table (Supabase)

```sql
CREATE TABLE obot_user_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suna_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    obot_user_id VARCHAR(255) NOT NULL,
    obot_username VARCHAR(255) NOT NULL,
    -- Cache token to avoid repeated API calls
    cached_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(suna_user_id),
    UNIQUE(obot_user_id)
);

CREATE INDEX idx_obot_mappings_suna ON obot_user_mappings(suna_user_id);
CREATE INDEX idx_obot_mappings_obot ON obot_user_mappings(obot_user_id);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_obot_mapping_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER obot_user_mappings_updated
    BEFORE UPDATE ON obot_user_mappings
    FOR EACH ROW
    EXECUTE FUNCTION update_obot_mapping_timestamp();
```

### Pydantic Models

Based on Obot's API response structures:

```python
# === Obot User Mapping (Suna-side storage) ===
class ObotUserMapping(BaseModel):
    id: str
    suna_user_id: str
    obot_user_id: str
    obot_username: str
    token_expires_at: Optional[datetime]
    created_at: datetime

# === Obot Profile (Suna-side storage for UI) ===
class ObotProfile(BaseModel):
    id: str
    account_id: str
    obot_server_id: str
    catalog_entry_id: str
    display_name: str
    icon_url: Optional[str]
    status: str  # 'pending', 'connected', 'error', 'oauth_required'
    created_at: datetime
    updated_at: datetime

# === MCP Catalog Entry (from Obot API) ===
class MCPCatalogEntry(BaseModel):
    """Maps to Obot's MCPServerCatalogEntry type"""
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    runtime: str  # 'single-user', 'remote', 'composite'
    editable: bool
    catalog_name: Optional[str]
    source_url: Optional[str]
    user_count: int
    env_vars: List[str] = []  # Required environment variables
    
class MCPCatalogEntryManifest(BaseModel):
    """Detailed manifest for catalog entry"""
    name: str
    description: Optional[str]
    icon: Optional[str]
    runtime: str
    env: List[str] = []
    args: List[str] = []
    oauth_apps: List[str] = []

# === MCP Server (from Obot API) ===
class MCPServer(BaseModel):
    """Maps to Obot's MCPServer type"""
    id: str
    name: str
    alias: Optional[str]
    catalog_entry_id: Optional[str]
    catalog_id: Optional[str]
    status: str
    configured: bool
    oauth_required: bool
    oauth_url: Optional[str]
    missing_env_vars: List[str] = []
    slug: Optional[str]

# === MCP Tool (from Obot API) ===
class MCPTool(BaseModel):
    """Maps to Obot's Tool_Definition"""
    name: str
    description: str
    input_schema: dict
    enabled: bool = True

# === MCP Resource (from Obot API) ===
class MCPResource(BaseModel):
    uri: str
    name: str
    description: Optional[str]
    mime_type: Optional[str]

# === MCP Prompt (from Obot API) ===
class MCPPrompt(BaseModel):
    name: str
    description: Optional[str]
    arguments: List[dict] = []

# === API Request/Response Models ===
class CreateMCPServerRequest(BaseModel):
    catalog_entry_id: str
    alias: Optional[str] = None
    env: Optional[dict] = None

class UpdateMCPServerRequest(BaseModel):
    alias: Optional[str] = None
    env: Optional[dict] = None

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict

class ToolCallResponse(BaseModel):
    success: bool
    result: Optional[Any]
    error: Optional[str]
    is_error: bool = False
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following correctness properties have been identified:

### Property 1: User Identity Mapping Consistency

*For any* Suna user ID, the mapping function SHALL produce the same Obot user ID on every invocation, and different Suna user IDs SHALL produce different Obot user IDs (no collisions within practical limits).

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: JWT Token Validity

*For any* valid Suna user ID and role, the generated JWT token SHALL be verifiable using the shared secret and SHALL contain the correct user identity claims.

**Validates: Requirements 2.5**

### Property 3: Response Format Transformation

*For any* valid Obot API response (catalog entries, servers, tools, tool results), the transformation function SHALL produce a response that conforms to Suna's expected API schema.

**Validates: Requirements 3.1, 4.1, 6.4**

### Property 4: User Context Preservation

*For any* MCP operation (server creation, tool discovery, tool execution), the request to Obot SHALL include the correct user identity derived from the Suna user making the request.

**Validates: Requirements 3.2, 3.4, 6.1, 6.2**

### Property 5: Admin Access Control

*For any* request to Obot Admin GUI endpoints, the system SHALL grant access only to users with admin role in Suna's role system.

**Validates: Requirements 5.1**

### Property 6: Connection Status Accuracy

*For any* MCP server profile, the displayed connection status SHALL reflect the actual authentication and health status from Obot within a reasonable staleness window.

**Validates: Requirements 4.4**

### Property 7: Environment Configuration Parsing

*For any* valid environment variable configuration, the Obot client SHALL correctly parse and apply the configuration values for base URL, JWT secret, and timeout settings.

**Validates: Requirements 1.3**

### Property 8: Profile Query Compatibility

*For any* profile query by account ID, the query SHALL return all profiles associated with that account in a format compatible with the existing profile listing UI.

**Validates: Requirements 7.3**

## Error Handling

### Obot Unavailability

When Obot is unavailable:
1. Health check endpoint returns unhealthy status
2. MCP-related API endpoints return 503 Service Unavailable
3. Agent tool calls fail gracefully with appropriate error messages
4. Frontend displays "MCP services temporarily unavailable" message

### Authentication Errors

When OAuth re-authentication is required:
1. Tool calls return 401 with `oauth_required: true` flag
2. Response includes OAuth URL for re-authentication
3. Frontend prompts user to re-authenticate

### Tool Execution Errors

When MCP tool execution fails:
1. Error is logged with full context
2. Agent receives structured error response
3. Error type is categorized (auth, timeout, validation, server error)

## Testing Strategy

### Dual Testing Approach

This implementation uses both unit tests and property-based tests:

- **Unit tests** verify specific examples, edge cases, and integration points
- **Property-based tests** verify universal properties that should hold across all inputs

### Property-Based Testing Framework

The implementation will use **Hypothesis** for Python property-based testing.

Configuration:
- Minimum 100 iterations per property test
- Explicit seed logging for reproducibility
- Custom strategies for domain-specific types

### Test Categories

1. **Unit Tests**
   - ObotClient API method tests with mocked responses
   - UserIdentityMapper edge cases (empty strings, special characters)
   - Profile service CRUD operations
   - Error handling scenarios

2. **Property-Based Tests**
   - User identity mapping consistency (Property 1)
   - JWT token generation and validation (Property 2)
   - Response transformation correctness (Property 3)
   - User context preservation (Property 4)
   - Environment configuration parsing (Property 7)

3. **Integration Tests**
   - End-to-end MCP server connection flow
   - OAuth authentication flow
   - Tool execution through agent framework

### Test Annotations

Each property-based test will be annotated with:
```python
# **Feature: obot-mcp-integration, Property 1: User Identity Mapping Consistency**
# **Validates: Requirements 2.1, 2.2, 2.3**
```
