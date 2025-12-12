"""Obot MCP Gateway data models

Pydantic models for Obot API responses and requests.
"""

from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field


# === Obot User Mapping (Suna-side storage) ===
class ObotUserMapping(BaseModel):
    """Maps a Suna user to an Obot user"""
    id: str = Field(description="Database ID")
    suna_user_id: str = Field(description="Suna user UUID")
    obot_user_id: str = Field(description="Obot user identifier")
    obot_username: str = Field(description="Obot username")
    token_expires_at: Optional[datetime] = Field(description="Cached token expiry")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


# === Obot Profile (Suna-side storage for UI) ===
class ObotProfile(BaseModel):
    """Stores Obot MCP server references in Suna's database"""
    id: str = Field(description="Database ID")
    account_id: str = Field(description="Suna account UUID")
    obot_server_id: str = Field(description="Obot MCP server ID")
    catalog_entry_id: str = Field(description="Original catalog entry ID")
    display_name: str = Field(description="User-friendly display name")
    icon_url: Optional[str] = Field(description="Icon URL for UI")
    status: str = Field(description="Connection status", default="pending")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


# === MCP Catalog Entry (from Obot API) ===
class MCPCatalogEntry(BaseModel):
    """Maps to Obot's MCPServerCatalogEntry type"""
    id: str = Field(description="Catalog entry identifier")
    name: str = Field(description="Server name")
    description: Optional[str] = Field(description="Server description", default=None)
    icon: Optional[str] = Field(description="Icon URL", default=None)
    runtime: str = Field(description="Runtime type", default="single-user")
    editable: bool = Field(description="Whether server config is editable", default=True)
    catalog_name: Optional[str] = Field(description="Source catalog name", default=None)
    source_url: Optional[str] = Field(description="Source repository URL", default=None)
    user_count: int = Field(description="Number of users", default=0)
    env_vars: List[str] = Field(description="Required environment variables", default_factory=list)
    manifest: Optional["MCPCatalogEntryManifest"] = Field(description="Detailed manifest", default=None)


class MCPCatalogEntryManifest(BaseModel):
    """Detailed manifest for catalog entry"""
    name: str = Field(description="Name")
    description: Optional[str] = Field(description="Description", default=None)
    icon: Optional[str] = Field(description="Icon URL", default=None)
    runtime: str = Field(description="Runtime type")
    env: List[str] = Field(description="Environment variables", default_factory=list)
    args: List[str] = Field(description="Command arguments", default_factory=list)
    oauth_apps: List[str] = Field(description="OAuth app identifiers", default_factory=list)


# === MCP Server (from Obot API) ===
class MCPServer(BaseModel):
    """Maps to Obot's MCPServer type"""
    id: str = Field(description="Server identifier")
    name: str = Field(description="Server name")
    alias: Optional[str] = Field(description="User-defined alias", default=None)
    catalog_entry_id: Optional[str] = Field(description="Source catalog entry ID", default=None)
    catalog_id: Optional[str] = Field(description="Source catalog ID", default=None)
    status: str = Field(description="Server status")
    configured: bool = Field(description="Whether server is configured", default=False)
    oauth_required: bool = Field(description="Whether OAuth is required", default=False)
    oauth_url: Optional[str] = Field(description="OAuth authorization URL", default=None)
    missing_env_vars: List[str] = Field(description="Missing required env vars", default_factory=list)
    slug: Optional[str] = Field(description="Server slug", default=None)
    manifest: Optional[MCPCatalogEntryManifest] = Field(description="Server manifest", default=None)


# === MCP Tool (from Obot API) ===
class MCPTool(BaseModel):
    """Maps to Obot's Tool_Definition"""
    name: str = Field(description="Tool name")
    description: str = Field(description="Tool description")
    input_schema: Dict[str, Any] = Field(description="Input schema")
    enabled: bool = Field(description="Whether tool is enabled", default=True)


# === MCP Resource (from Obot API) ===
class MCPResource(BaseModel):
    """MCP resource definition"""
    uri: str = Field(description="Resource URI")
    name: str = Field(description="Resource name")
    description: Optional[str] = Field(description="Resource description", default=None)
    mime_type: Optional[str] = Field(description="Resource MIME type", default=None)


# === MCP Prompt (from Obot API) ===
class MCPPrompt(BaseModel):
    """MCP prompt definition"""
    name: str = Field(description="Prompt name")
    description: Optional[str] = Field(description="Prompt description", default=None)
    arguments: List[Dict[str, Any]] = Field(description="Prompt arguments", default_factory=list)


# === API Request/Response Models ===
class CreateMCPServerRequest(BaseModel):
    """Request to create MCP server"""
    catalog_entry_id: str = Field(description="Catalog entry to instantiate")
    alias: Optional[str] = Field(description="Optional alias", default=None)
    env: Optional[Dict[str, str]] = Field(description="Environment variables", default=None)


class UpdateMCPServerRequest(BaseModel):
    """Request to update MCP server"""
    alias: Optional[str] = Field(description="Optional alias", default=None)
    env: Optional[Dict[str, str]] = Field(description="Environment variables", default=None)


class ToolCallRequest(BaseModel):
    """Request to call an MCP tool"""
    tool_name: str = Field(description="Tool name to execute")
    arguments: Dict[str, Any] = Field(description="Tool arguments")


class ToolCallResponse(BaseModel):
    """Response from tool execution"""
    success: bool = Field(description="Whether execution succeeded")
    result: Optional[Any] = Field(description="Execution result", default=None)
    error: Optional[str] = Field(description="Error message if any", default=None)
    is_error: bool = Field(description="Whether result is an error", default=False)


# Health check response
class ObotHealthResponse(BaseModel):
    """Obot service health status"""
    status: str = Field(description="Health status")
    version: str = Field(description="Obot version")


# Update forward references
MCPCatalogEntry.model_rebuild()
MCPServer.model_rebuild()
