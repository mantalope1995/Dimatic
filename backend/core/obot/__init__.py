"""Obot MCP Gateway Integration

This module provides integration with Obot as a self-hosted MCP Gateway sidecar
for the Suna AI agent platform.
"""

from .client import ObotClient
from .models import (
    MCPCatalogEntry,
    MCPCatalogEntryManifest,
    MCPServer,
    MCPTool,
    CreateMCPServerRequest,
    UpdateMCPServerRequest,
    ToolCallRequest,
    ToolCallResponse,
    ObotHealthResponse,
)
from .rate_limiter import (
    ObotRateLimiter,
    ObotRateLimitError,
    get_rate_limiter,
    check_catalog_rate_limit,
    check_server_ops_rate_limit,
    check_tool_calls_rate_limit,
    check_oauth_init_rate_limit,
    get_user_rate_limit_status,
    clear_user_rate_limits,
    check_rate_limiter_health,
    get_rate_limiter_stats,
)

__all__ = [
    "ObotClient",
    "MCPCatalogEntry",
    "MCPCatalogEntryManifest", 
    "MCPServer",
    "MCPTool",
    "CreateMCPServerRequest",
    "UpdateMCPServerRequest",
    "ToolCallRequest",
    "ToolCallResponse",
    "ObotHealthResponse",
    "ObotRateLimiter",
    "ObotRateLimitError",
    "get_rate_limiter",
    "check_catalog_rate_limit",
    "check_server_ops_rate_limit",
    "check_tool_calls_rate_limit",
    "check_oauth_init_rate_limit",
    "get_user_rate_limit_status",
    "clear_user_rate_limits",
    "check_rate_limiter_health",
    "get_rate_limiter_stats",
]
