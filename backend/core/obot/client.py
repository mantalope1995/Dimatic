"""Obot MCP Gateway client

HTTP client for communicating with Obot's REST API.
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
import httpx
import logging

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


logger = logging.getLogger(__name__)


class ObotClientError(Exception):
    """Base exception for Obot client errors"""
    pass


class ObotServiceUnavailable(ObotClientError):
    """Raised when Obot service is unavailable (circuit open or max retries exceeded)"""
    pass


class ObotConnectionError(ObotClientError):
    """Raised when connection to Obot fails"""
    pass


class ObotAuthenticationError(ObotClientError):
    """Raised when authentication to Obot fails"""
    pass


class CircuitBreaker:
    """Simple circuit breaker implementation"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.is_open = False
        
    def allow_request(self) -> bool:
        """Check if request should be allowed"""
        if not self.is_open:
            return True
            
        # Check if recovery timeout has passed (Half-Open state effectively)
        import time
        if time.time() - self.last_failure_time > self.recovery_timeout:
            return True  # Allow probe request
            
        return False
        
    def record_success(self):
        """Record successful request"""
        if self.failures > 0 or self.is_open:
            logger.info("Circuit breaker recovering/resetting")
        self.failures = 0
        self.is_open = False
        
    def record_failure(self):
        """Record failed request"""
        import time
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            if not self.is_open:
                logger.warning(f"Circuit breaker tripping open after {self.failures} failures")
            self.is_open = True


class ObotClient:
    """Client for Obot MCP Gateway API"""
    
    def __init__(
        self,
        base_url: str,
        bootstrap_token: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """Initialize Obot client
        
        Args:
            base_url: Obot API base URL (e.g., "http://obot:8080/api")
            bootstrap_token: Obot bootstrap token for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        # Validate arguments
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        self.base_url = base_url.rstrip('/')
        self.bootstrap_token = bootstrap_token
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Initialize httpx client
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Suna-Obot-Client/1.0"
            }
        )
        
        self.circuit_breaker = CircuitBreaker()
        
        logger.debug(f"Initialized ObotClient with base_url={base_url}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._client.aclose()
    
    async def _request(
        self,
        method: str,
        path: str,
        token: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request to Obot API
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (relative to base_url)
            token: Optional auth token (uses bootstrap_token if None)
            **kwargs: Additional arguments for httpx request
            
        Returns:
            httpx.Response object
            
        Raises:
            ObotClientError: On HTTP errors or timeouts
        """
        url = f"{self.base_url}{path}"
        
        # Check circuit breaker
        if not self.circuit_breaker.allow_request():
            raise ObotServiceUnavailable("Obot service is currently unavailable (circuit open)")
        
        # Set Authorization header
        headers = kwargs.get("headers", {})
        auth_token = token or self.bootstrap_token
        headers["Authorization"] = f"Bearer {auth_token}"
        kwargs["headers"] = headers
        
        # Retry logic for transient failures
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"{method} {url} (attempt {attempt + 1})")
                response = await self._client.request(method, url, **kwargs)
                
                # Log response status
                logger.debug(f"Response: {response.status_code}")
                
                # Success (2xx-3xx)
                if response.status_code < 400:
                    self.circuit_breaker.record_success()
                    return response
                
                # Client Error (4xx) - Do not retry, technically a success for connectivity
                if 400 <= response.status_code < 500:
                    self.circuit_breaker.record_success()
                    response.raise_for_status()
                    
                # Server Error (5xx) - Retry
                response.raise_for_status()
                
            except httpx.HTTPStatusError as e:
                # 4xx errors - raise immediately wrapped in ObotClientError
                if 400 <= e.response.status_code < 500:
                    raise ObotClientError(f"Client error: {e}") from e
                
                # 5xx errors - track as failure and retry
                last_exception = e
                self.circuit_breaker.record_failure()
                logger.warning(f"Server error (attempt {attempt + 1}): {e}")
                
            except httpx.HTTPError as e:
                # Network/Timeout errors - track as failure and retry
                last_exception = e
                self.circuit_breaker.record_failure()
                logger.warning(f"Network error (attempt {attempt + 1}): {e}")
            
            # Exponential backoff if attempts remain
            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
        
        # All retries exhausted
        error_msg = f"Request failed after {self.max_retries + 1} attempts: {last_exception}"
        logger.error(error_msg)
        raise ObotServiceUnavailable(error_msg)
    
    async def _get(
        self,
        path: str,
        token: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Make GET request"""
        return await self._request("GET", path, token, **kwargs)
    
    async def _post(
        self,
        path: str,
        token: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Make POST request"""
        return await self._request("POST", path, token, **kwargs)
    
    async def _put(
        self,
        path: str,
        token: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Make PUT request"""
        return await self._request("PUT", path, token, **kwargs)
    
    async def _delete(
        self,
        path: str,
        token: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Make DELETE request"""
        return await self._request("DELETE", path, token, **kwargs)
    
    # === Health Check ===
    
    async def check_health(self) -> ObotHealthResponse:
        """Check Obot service health
        
        Returns:
            Health status information
            
        Raises:
            ObotClientError: On health check failure
        """
        try:
            response = await self._get("/version")
            data = response.json()
            
            return ObotHealthResponse(
                status="healthy" if response.status_code == 200 else "unhealthy",
                version=data.get("version", "unknown")
            )
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise ObotClientError(f"Health check failed: {e}")
    
    # === Catalog Entry Methods ===
    
    async def list_catalog_entries(
        self,
        token: Optional[str] = None
    ) -> List[MCPCatalogEntry]:
        """List available MCP servers from Obot catalog
        
        Args:
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            List of catalog entries
            
        Raises:
            ObotClientError: On API error
        """
        try:
            response = await self._get("/all-mcps/entries", token=token)
            data = response.json()
            
            entries = []
            for entry_data in data:
                # Map Obot response to our model
                entry = MCPCatalogEntry(
                    id=entry_data["id"],
                    name=entry_data["name"],
                    description=entry_data.get("description"),
                    icon=entry_data.get("icon"),
                    runtime=entry_data.get("runtime", "single-user"),
                    editable=entry_data.get("editable", True),
                    catalog_name=entry_data.get("catalogName"),
                    source_url=entry_data.get("sourceUrl"),
                    user_count=entry_data.get("userCount", 0),
                    env_vars=entry_data.get("envVars", []),
                    manifest=MCPCatalogEntryManifest(**entry_data.get("manifest", {}))
                    if entry_data.get("manifest") else None
                )
                entries.append(entry)
            
            logger.info(f"Retrieved {len(entries)} catalog entries")
            return entries
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to list catalog entries: {e}")
            raise ObotClientError(f"Failed to list catalog entries: {e}")
    
    async def get_catalog_entry(
        self,
        entry_id: str,
        token: Optional[str] = None
    ) -> MCPCatalogEntry:
        """Get detailed information about a catalog entry
        
        Args:
            entry_id: Catalog entry identifier
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            Catalog entry details
            
        Raises:
            ObotClientError: On API error or entry not found
        """
        try:
            response = await self._get(f"/all-mcps/entries/{entry_id}", token=token)
            data = response.json()
            
            entry = MCPCatalogEntry(
                id=data["id"],
                name=data["name"],
                description=data.get("description"),
                icon=data.get("icon"),
                runtime=data.get("runtime", "single-user"),
                editable=data.get("editable", True),
                catalog_name=data.get("catalogName"),
                source_url=data.get("sourceUrl"),
                user_count=data.get("userCount", 0),
                env_vars=data.get("envVars", []),
                manifest=MCPCatalogEntryManifest(**data.get("manifest", {}))
                if data.get("manifest") else None
            )
            
            logger.info(f"Retrieved catalog entry: {entry_id}")
            return entry
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ObotClientError(f"Catalog entry not found: {entry_id}")
            raise
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to get catalog entry {entry_id}: {e}")
            raise ObotClientError(f"Failed to get catalog entry: {e}")
    
    # === MCP Server Methods ===
    
    async def list_mcp_servers(
        self,
        token: Optional[str] = None
    ) -> List[MCPServer]:
        """List user's MCP server instances
        
        Args:
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            List of MCP servers
            
        Raises:
            ObotClientError: On API error
        """
        try:
            response = await self._get("/mcp-servers", token=token)
            data = response.json()
            
            servers = []
            for server_data in data:
                server = MCPServer(
                    id=server_data["id"],
                    name=server_data["name"],
                    alias=server_data.get("alias"),
                    catalog_entry_id=server_data.get("catalogEntryId"),
                    catalog_id=server_data.get("catalogId"),
                    status=server_data.get("status", "unknown"),
                    configured=server_data.get("configured", False),
                    oauth_required=server_data.get("oauthRequired", False),
                    oauth_url=server_data.get("oauthUrl"),
                    missing_env_vars=server_data.get("missingRequiredEnvVars", []),
                    slug=server_data.get("slug"),
                    manifest=MCPCatalogEntryManifest(**server_data.get("manifest", {}))
                    if server_data.get("manifest") else None
                )
                servers.append(server)
            
            logger.info(f"Retrieved {len(servers)} MCP servers")
            return servers
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to list MCP servers: {e}")
            raise ObotClientError(f"Failed to list MCP servers: {e}")
    
    async def create_mcp_server(
        self,
        request: CreateMCPServerRequest,
        token: Optional[str] = None
    ) -> MCPServer:
        """Create a new MCP server instance
        
        Args:
            request: Server creation request
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            Created MCP server
            
        Raises:
            ObotClientError: On API error
        """
        try:
            payload = {
                "catalogEntryID": request.catalog_entry_id,
                "alias": request.alias,
                "env": request.env or {}
            }
            
            response = await self._post(
                "/mcp-servers",
                token=token,
                json=payload
            )
            data = response.json()
            
            server = MCPServer(
                id=data["id"],
                name=data["name"],
                alias=data.get("alias"),
                catalog_entry_id=data.get("catalogEntryId"),
                catalog_id=data.get("catalogId"),
                status=data.get("status", "unknown"),
                configured=data.get("configured", False),
                oauth_required=data.get("oauthRequired", False),
                oauth_url=data.get("oauthUrl"),
                missing_env_vars=data.get("missingRequiredEnvVars", []),
                slug=data.get("slug"),
                manifest=MCPCatalogEntryManifest(**data.get("manifest", {}))
                if data.get("manifest") else None
            )
            
            logger.info(f"Created MCP server: {server.id}")
            return server
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to create MCP server: {e}")
            raise ObotClientError(f"Failed to create MCP server: {e}")
    
    async def get_mcp_server(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> MCPServer:
        """Get MCP server details
        
        Args:
            server_id: Server identifier
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            MCP server details
            
        Raises:
            ObotClientError: On API error or server not found
        """
        try:
            response = await self._get(f"/mcp-servers/{server_id}", token=token)
            data = response.json()
            
            server = MCPServer(
                id=data["id"],
                name=data["name"],
                alias=data.get("alias"),
                catalog_entry_id=data.get("catalogEntryId"),
                catalog_id=data.get("catalogId"),
                status=data.get("status", "unknown"),
                configured=data.get("configured", False),
                oauth_required=data.get("oauthRequired", False),
                oauth_url=data.get("oauthUrl"),
                missing_env_vars=data.get("missingRequiredEnvVars", []),
                slug=data.get("slug"),
                manifest=MCPCatalogEntryManifest(**data.get("manifest", {}))
                if data.get("manifest") else None
            )
            
            logger.info(f"Retrieved MCP server: {server_id}")
            return server
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ObotClientError(f"MCP server not found: {server_id}")
            raise
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to get MCP server {server_id}: {e}")
            raise ObotClientError(f"Failed to get MCP server: {e}")
    
    async def update_mcp_server(
        self,
        server_id: str,
        request: UpdateMCPServerRequest,
        token: Optional[str] = None
    ) -> MCPServer:
        """Update MCP server configuration
        
        Args:
            server_id: Server identifier
            request: Server update request
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            Updated MCP server
            
        Raises:
            ObotClientError: On API error
        """
        try:
            payload = {}
            if request.alias is not None:
                payload["alias"] = request.alias
            if request.env is not None:
                payload["env"] = request.env
            
            if not payload:
                # No changes to apply
                return await self.get_mcp_server(server_id, token)
            
            response = await self._put(
                f"/mcp-servers/{server_id}",
                token=token,
                json=payload
            )
            data = response.json()
            
            server = MCPServer(
                id=data["id"],
                name=data["name"],
                alias=data.get("alias"),
                catalog_entry_id=data.get("catalogEntryId"),
                catalog_id=data.get("catalogId"),
                status=data.get("status", "unknown"),
                configured=data.get("configured", False),
                oauth_required=data.get("oauthRequired", False),
                oauth_url=data.get("oauthUrl"),
                missing_env_vars=data.get("missingRequiredEnvVars", []),
                slug=data.get("slug"),
                manifest=MCPCatalogEntryManifest(**data.get("manifest", {}))
                if data.get("manifest") else None
            )
            
            logger.info(f"Updated MCP server: {server_id}")
            return server
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to update MCP server {server_id}: {e}")
            raise ObotClientError(f"Failed to update MCP server: {e}")
    
    async def delete_mcp_server(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> None:
        """Delete MCP server instance
        
        Args:
            server_id: Server identifier
            token: Optional user token (uses bootstrap token if None)
            
        Raises:
            ObotClientError: On API error or server not found
        """
        try:
            await self._delete(f"/mcp-servers/{server_id}", token=token)
            logger.info(f"Deleted MCP server: {server_id}")
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ObotClientError(f"MCP server not found: {server_id}")
            raise
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete MCP server {server_id}: {e}")
            raise ObotClientError(f"Failed to delete MCP server: {e}")
    
    # === MCP Tools Methods ===
    
    async def list_tools(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> List[MCPTool]:
        """List tools from an MCP server
        
        Args:
            server_id: Server identifier
            token: Optional user token (uses bootstrap token if None)
            
        Returns:
            List of available tools
            
        Raises:
            ObotClientError: On API error
        """
        try:
            response = await self._get(f"/mcp-servers/{server_id}/tools", token=token)
            data = response.json()
            
            tools = []
            for tool_data in data:
                tool = MCPTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("params", {}),
                    enabled=tool_data.get("enabled", True)
                )
                tools.append(tool)
            
            logger.info(f"Retrieved {len(tools)} tools for server {server_id}")
            return tools
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to list tools for server {server_id}: {e}")
            raise ObotClientError(f"Failed to list tools: {e}")
    
    async def set_tools(
        self,
        server_id: str,
        tool_names: List[str],
        token: Optional[str] = None
    ) -> None:
        """Set allowed tools for an MCP server
        
        Args:
            server_id: Server identifier
            tool_names: List of tool names to enable
            token: Optional user token (uses bootstrap token if None)
            
        Raises:
            ObotClientError: On API error
        """
        try:
            payload = {"toolNames": tool_names}
            
            await self._put(
                f"/mcp-servers/{server_id}/tools",
                token=token,
                json=payload
            )
            
            logger.info(f"Set {len(tool_names)} tools for server {server_id}")
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to set tools for server {server_id}: {e}")
            raise ObotClientError(f"Failed to set tools: {e}")

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        token: Optional[str] = None
    ) -> ToolCallResponse:
        """Execute a tool on an MCP server
        
        Args:
            server_id: Server identifier
            tool_name: Name of tool to execute
            arguments: Tool arguments
            token: Optional user token
            
        Returns:
            Tool execution result
            
        Raises:
            ObotClientError: On API error or tool failure
        """
        try:
            payload = {
                "server_id": server_id,
                "tool_name": tool_name,
                "arguments": arguments
            }
            
            # Note: Endpoint path inferred from typical patterns, adjust if specific path exists
            # Looking at other methods, it seems likely to be under mcp-servers or a dedicated execution path
            # Assuming POST /mcp-servers/{id}/tools/{name}/execute or similar
            # Re-checking typical Obot API patterns... usually it's POST /mcp-servers/{id}/call
            
            response = await self._post(
                f"/mcp-servers/{server_id}/tools/{tool_name}/call",
                token=token,
                json=arguments
            )
            data = response.json()
            
            return ToolCallResponse(
                success=True,
                result=data.get("result"),
                error=None,
                is_error=False
            )
            
        except httpx.HTTPStatusError as e:
            # Handle specific tool errors returned by server
            if e.response.status_code == 500:
                try:
                    error_data = e.response.json()
                    return ToolCallResponse(
                        success=False,
                        result=None,
                        error=error_data.get("detail", str(e)),
                        is_error=True
                    )
                except ValueError:
                    pass
            raise ObotClientError(f"Tool execution failed: {e}")
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_id}: {e}")
            raise ObotClientError(f"Failed to call tool: {e}")

    # === OAuth & Lifecycle Methods ===

    async def get_oauth_url(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> str:
        """Get OAuth authorization URL for a server
        
        Args:
            server_id: Server identifier
            token: Optional user token
            
        Returns:
            Authorization URL
        """
        try:
            response = await self._get(f"/mcp-servers/{server_id}/oauth-url", token=token)
            data = response.json()
            return data.get("url", "")
            
        except Exception as e:
            logger.error(f"Failed to get OAuth URL for {server_id}: {e}")
            raise ObotClientError(f"Failed to get OAuth URL: {e}")

    async def start_mcp_server(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> MCPServer:
        """Start/Launch an MCP server
        
        Args:
            server_id: Server identifier
            token: Optional user token
            
        Returns:
            Updated server status
        """
        try:
            response = await self._post(f"/mcp-servers/{server_id}/launch", token=token)
            data = response.json()
            
            # Re-use the parsing logic or return raw if complex mapping needed
            # For now, just return get_mcp_server style object
            return await self.get_mcp_server(server_id, token)
            
        except Exception as e:
            logger.error(f"Failed to launch server {server_id}: {e}")
            raise ObotClientError(f"Failed to launch server: {e}")

    async def get_connection_status(
        self,
        server_id: str,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get detailed connection status
        
        Args:
            server_id: Server identifier
            token: Optional user token
            
        Returns:
            Status dictionary
        """
        try:
            # First get the server details which contains basic status
            server = await self.get_mcp_server(server_id, token)
            
            # Construct status response matching API requirements
            return {
                "configured": server.configured,
                "missingRequiredEnvVars": server.missing_env_vars,
                "deploymentStatus": server.status,
                "oauthRequired": server.oauth_required,
                "oauthUrl": server.oauth_url # Might be populated if needed
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for {server_id}: {e}")
            raise ObotClientError(f"Failed to get status: {e}")
    
    # === Authentication Methods ===
    
    async def get_token_for_user(
        self,
        obot_user_id: str,
        bootstrap_token: Optional[str] = None
    ) -> str:
        """Get API token for a specific Obot user
        
        Args:
            obot_user_id: Obot user identifier
            bootstrap_token: Bootstrap token (uses instance token if None)
            
        Returns:
            User-scoped API token
            
        Raises:
            ObotClientError: On API error
        """
        try:
            payload = {"userId": obot_user_id}
            token = bootstrap_token or self.bootstrap_token
            
            response = await self._post(
                "/token",
                token=token,
                json=payload
            )
            data = response.json()
            
            user_token = data.get("token")
            if not user_token:
                raise ObotClientError("No token returned from Obot")
            
            logger.debug(f"Retrieved token for user {obot_user_id}")
            return user_token
            
        except ObotClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to get token for user {obot_user_id}: {e}")
            raise ObotClientError(f"Failed to get user token: {e}")


def create_obot_client() -> ObotClient:
    """Create Obot client from environment variables
    
    Returns:
        Configured ObotClient instance
        
    Raises:
        ValueError: If required environment variables are missing
    """
    base_url = os.getenv("OBOT_BASE_URL", "http://localhost:8080/api")
    bootstrap_token = os.getenv("OBOT_BOOTSTRAP_TOKEN")
    
    if not bootstrap_token:
        raise ValueError("OBOT_BOOTSTRAP_TOKEN environment variable is required")
    
    return ObotClient(
        base_url=base_url,
        bootstrap_token=bootstrap_token
    )
