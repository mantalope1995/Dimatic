/**
 * TypeScript types for Obot MCP Gateway API
 * These match the backend Pydantic models in backend/core/obot/models.py
 */

// === MCP Catalog Entry ===
export interface MCPCatalogEntryManifest {
    name: string;
    description?: string;
    icon?: string;
    runtime: string;
    env: string[];
    args: string[];
    oauth_apps: string[];
}

export interface MCPCatalogEntry {
    id: string;
    name: string;
    description?: string;
    icon?: string;
    runtime: string;
    editable: boolean;
    catalog_name?: string;
    source_url?: string;
    user_count: number;
    env_vars: string[];
    manifest?: MCPCatalogEntryManifest;
}

// === MCP Server ===
export interface MCPServer {
    id: string;
    name: string;
    alias?: string;
    catalog_entry_id?: string;
    catalog_id?: string;
    status: string;
    configured: boolean;
    oauth_required: boolean;
    oauth_url?: string;
    missing_env_vars: string[];
    slug?: string;
    manifest?: MCPCatalogEntryManifest;
}

// === MCP Tool ===
export interface MCPTool {
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
    enabled: boolean;
}

// === MCP Resource ===
export interface MCPResource {
    uri: string;
    name: string;
    description?: string;
    mime_type?: string;
}

// === MCP Prompt ===
export interface MCPPrompt {
    name: string;
    description?: string;
    arguments: Record<string, unknown>[];
}

// === Obot Profile (Suna-side storage) ===
export interface ObotProfile {
    id: string;
    account_id: string;
    obot_server_id: string;
    catalog_entry_id: string;
    display_name: string;
    icon_url?: string;
    status: 'pending' | 'connected' | 'error' | 'oauth_required';
    created_at: string;
    updated_at: string;
}

// === API Request Types ===
export interface CreateMCPServerRequest {
    catalog_entry_id: string;
    alias?: string;
    env?: Record<string, string>;
}

export interface UpdateMCPServerRequest {
    alias?: string;
    env?: Record<string, string>;
}

export interface ToolCallRequest {
    tool_name: string;
    arguments: Record<string, unknown>;
}

// === API Response Types ===
export interface ToolCallResponse {
    success: boolean;
    result?: unknown;
    error?: string;
    is_error: boolean;
}

export interface ObotHealthResponse {
    status: string;
    version: string;
}

// === List Response Wrappers ===
export interface CatalogListResponse {
    entries: MCPCatalogEntry[];
    total: number;
}

export interface ServerListResponse {
    servers: MCPServer[];
    total: number;
}

export interface ToolListResponse {
    tools: MCPTool[];
    total: number;
}

export interface ProfileListResponse {
    profiles: ObotProfile[];
    total: number;
}
