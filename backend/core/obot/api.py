from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from core.utils.auth_utils import verify_and_get_user_id_from_jwt
from core.services.supabase import DBConnection

from .client import ObotClient, create_obot_client, ObotClientError
from .identity_service import ObotIdentityService, create_identity_service
from .models import (
    MCPCatalogEntry,
    MCPServer,
    CreateMCPServerRequest,
    UpdateMCPServerRequest,
    MCPTool,
    ToolCallResponse,
    ObotHealthResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/obot",
    tags=["obot"],
    responses={404: {"description": "Not found"}},
)

# Dependency to get ObotIdentityService
async def get_identity_service() -> ObotIdentityService:
    db = DBConnection()
    await db.initialize()
    # We create a new client for each request to ensure fresh connection handling
    # In a production environment, we might want to use a connection pool or singleton
    obot_client = create_obot_client()
    return create_identity_service(db, obot_client)

@router.get(
    "/catalog",
    response_model=List[MCPCatalogEntry],
    summary="List catalog entries",
    description="List available MCP servers from Obot catalog"
)
async def list_catalog_entries(
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """List availabe MCP catalog entries"""
    try:
        # Get Obot token for user
        token = await identity_service.get_obot_token(user_id)
        
        # Fetch catalog entries
        # Rate limiting is handled by global middleware or Obot client
        entries = await identity_service.obot_client.list_catalog_entries(token=token)
        
        return entries
        
    except ObotClientError as e:
        logger.error(f"Failed to list catalog entries for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with Obot service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in list_catalog_entries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get(
    "/catalog/{entry_id}",
    response_model=MCPCatalogEntry,
    summary="Get catalog entry",
    description="Get detailed information about a catalog entry"
)
async def get_catalog_entry(
    entry_id: str = Path(..., description="Catalog entry ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Get specific catalog entry details"""
    try:
        token = await identity_service.get_obot_token(user_id)
        entry = await identity_service.obot_client.get_catalog_entry(entry_id, token=token)
        return entry
        
    except ObotClientError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Catalog entry not found: {entry_id}"
            )
        logger.error(f"Failed to get catalog entry {entry_id} for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with Obot service: {str(e)}"
        )

@router.post(
    "/servers",
    response_model=MCPServer,
    status_code=status.HTTP_201_CREATED,
    summary="Create MCP server",
    description="Create a new MCP server instance from a catalog entry"
)
async def create_mcp_server(
    request: CreateMCPServerRequest,
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Create a new MCP server"""
    try:
        token = await identity_service.get_obot_token(user_id)
        
        # Create server in Obot
        server = await identity_service.obot_client.create_mcp_server(request, token=token)
        
        # TODO: Store additional profile info in obot_profiles if needed
        # For now, we rely on Obot to store the main state
        
        logger.info(f"User {user_id} created MCP server {server.id} ({server.name})")
        return server
        
    except ObotClientError as e:
        logger.error(f"Failed to create server for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create server: {str(e)}"
        )

@router.get(
    "/servers",
    response_model=List[MCPServer],
    summary="List MCP servers",
    description="List user's MCP server instances"
)
async def list_mcp_servers(
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """List user's MCP servers"""
    try:
        token = await identity_service.get_obot_token(user_id)
        servers = await identity_service.obot_client.list_mcp_servers(token=token)
        return servers
        
    except ObotClientError as e:
        logger.error(f"Failed to list servers for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list servers: {str(e)}"
        )

@router.get(
    "/servers/{server_id}",
    response_model=MCPServer,
    summary="Get MCP server",
    description="Get details of a specific MCP server instance"
)
async def get_mcp_server(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Get MCP server details"""
    try:
        token = await identity_service.get_obot_token(user_id)
        server = await identity_service.obot_client.get_mcp_server(server_id, token=token)
        return server
        
    except ObotClientError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Server not found: {server_id}"
            )
        logger.error(f"Failed to get server {server_id} for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get server details: {str(e)}"
        )

@router.delete(
    "/servers/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete MCP server",
    description="Delete an MCP server instance"
)
async def delete_mcp_server(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Delete MCP server"""
    try:
        token = await identity_service.get_obot_token(user_id)
        await identity_service.obot_client.delete_mcp_server(server_id, token=token)
        
        logger.info(f"User {user_id} deleted MCP server {server_id}")
        return None
        
    except ObotClientError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Server not found: {server_id}"
            )
        logger.error(f"Failed to delete server {server_id} for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete server: {str(e)}"
        )


# === Tool Endpoints ===

@router.get(
    "/servers/{server_id}/tools",
    response_model=List[MCPTool],
    summary="List server tools",
    description="List available tools for an MCP server"
)
async def list_server_tools(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """List available tools for a server"""
    try:
        token = await identity_service.get_obot_token(user_id)
        tools = await identity_service.obot_client.list_tools(server_id, token=token)
        return tools
    except ObotClientError as e:
        logger.error(f"Failed to list tools for server {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list tools: {str(e)}"
        )

@router.put(
    "/servers/{server_id}/tools",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set enabled tools",
    description="Set the list of enabled tools for a server"
)
async def set_server_tools(
    tool_names: List[str],
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Set enabled tools for a server"""
    try:
        token = await identity_service.get_obot_token(user_id)
        await identity_service.obot_client.set_tools(server_id, tool_names, token=token)
        return None
    except ObotClientError as e:
        logger.error(f"Failed to set tools for server {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to set tools: {str(e)}"
        )

@router.post(
    "/servers/{server_id}/tools/{tool_name}/call",
    response_model=ToolCallResponse,
    summary="Call tool",
    description="Execute a tool on an MCP server"
)
async def call_server_tool(
    arguments: Dict[str, Any],
    server_id: str = Path(..., description="Server ID"),
    tool_name: str = Path(..., description="Tool name"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Execute a tool"""
    # TODO: Apply rate limiting (60/min)
    # TODO: Record audit log
    try:
        token = await identity_service.get_obot_token(user_id)
        result = await identity_service.obot_client.call_tool(
            server_id, tool_name, arguments, token=token
        )
        return result
    except ObotClientError as e:
        logger.error(f"Failed to call tool {tool_name} on {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to call tool: {str(e)}"
        )

# === OAuth & Configuration Endpoints ===

@router.get(
    "/servers/{server_id}/oauth-url",
    summary="Get OAuth URL",
    description="Get the OAuth authorization URL for a server"
)
async def get_oauth_url(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Get OAuth URL"""
    # TODO: Apply rate limiting (5/min)
    try:
        token = await identity_service.get_obot_token(user_id)
        url = await identity_service.obot_client.get_oauth_url(server_id, token=token)
        return {"url": url}
    except ObotClientError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get OAuth URL: {str(e)}"
        )

@router.post(
    "/servers/{server_id}/configure",
    response_model=MCPServer,
    summary="Configure server",
    description="Set environment variables/credentials for a server"
)
async def configure_server(
    env: Dict[str, str],
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Configure server environment variables"""
    try:
        token = await identity_service.get_obot_token(user_id)
        # Re-use update_mcp_server for configuration
        request = UpdateMCPServerRequest(env=env)
        server = await identity_service.obot_client.update_mcp_server(
            server_id, request, token=token
        )
        return server
    except ObotClientError as e:
        logger.error(f"Failed to configure server {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to configure server: {str(e)}"
        )

@router.post(
    "/servers/{server_id}/launch",
    response_model=MCPServer,
    summary="Launch server",
    description="Start an MCP server instance"
)
async def launch_server(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Launch/Start server"""
    try:
        token = await identity_service.get_obot_token(user_id)
        server = await identity_service.obot_client.start_mcp_server(server_id, token=token)
        return server
    except ObotClientError as e:
        logger.error(f"Failed to launch server {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to launch server: {str(e)}"
        )

@router.get(
    "/servers/{server_id}/status",
    summary="Get server status",
    description="Get detailed connection status for a server"
)
async def get_server_status(
    server_id: str = Path(..., description="Server ID"),
    user_id: str = Depends(verify_and_get_user_id_from_jwt),
    identity_service: ObotIdentityService = Depends(get_identity_service)
):
    """Get server status"""
    try:
        token = await identity_service.get_obot_token(user_id)
        status_info = await identity_service.obot_client.get_connection_status(
            server_id, token=token
        )
        return status_info
    except ObotClientError as e:
        logger.error(f"Failed to get status for server {server_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get server status: {str(e)}"
        )

# === System Endpoints ===

@router.get(
    "/health",
    response_model=ObotHealthResponse,
    summary="Health check",
    description="Check Obot service health"
)
async def health_check():
    """Check Obot service health"""
    try:
        # We don't need a user token for health check, use bootstrap token via create_obot_client
        client = create_obot_client()
        async with client:
            return await client.check_health()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )

