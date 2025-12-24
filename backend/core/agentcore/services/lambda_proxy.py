"""
Lambda Proxy for MCP → Gateway Protocol Translation

This module provides protocol translation between MCP (Model Context Protocol)
and AgentCore Gateway API. It handles authentication, request/response transformation,
and acts as an intermediary layer for external MCP integrations.

Key responsibilities:
- Translate MCP protocol calls to Gateway API calls
- Handle authentication (OAuth tokens, API keys)
- Transform request/response formats between MCP and Gateway
- Support different MCP transport types (SSE, HTTP, stdio)
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime, timedelta
from dataclasses import asdict

from ..config import AgentCoreConfig, get_config
from ..errors import (
    GatewayError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
)
from .secrets_manager_adapter import SecretsManagerAdapter
from .oauth_flow_service import OAuthFlowService
from .mcp_catalog_service import MCPCatalogService

# Lazy imports to avoid circular dependency
if TYPE_CHECKING:
    from ..adapters.gateway import AgentCoreGatewayAdapter
    from ..models import MCPServerDeployment, MCPToolInvocationResult, GatewayConfig

logger = logging.getLogger(__name__)


class MCPProtocolTranslator:
    """
    Translates between MCP protocol and Gateway API format.

    Handles:
    - Request format transformation
    - Response format transformation
    - Error code mapping
    - Tool schema conversion
    """

    # MCP to Gateway error code mapping
    ERROR_CODE_MAP = {
        # MCP errors → Gateway errors
        "InvalidRequest": "ValidationError",
        "Unauthorized": "AuthenticationError",
        "Forbidden": "AuthorizationError",
        "NotFound": "ResourceNotFoundError",
        "RateLimitExceeded": "ThrottlingError",
        "InternalError": "ServiceUnavailableError",
    }

    @classmethod
    def mcp_request_to_gateway(cls, mcp_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate MCP request format to Gateway API format.

        Args:
            mcp_request: MCP protocol request

        Returns:
            Gateway API formatted request
        """
        # Extract common fields
        tool_name = mcp_request.get("method", mcp_request.get("tool", mcp_request.get("name")))
        parameters = mcp_request.get("params", mcp_request.get("arguments", {}))

        # Gateway expects specific format
        gateway_request = {
            "tool_name": tool_name,
            "parameters": parameters,
            "metadata": {
                "mcp_request_id": mcp_request.get("id", mcp_request.get("request_id")),
                "mcp_timestamp": mcp_request.get("timestamp", datetime.utcnow().isoformat()),
                "original_request": mcp_request
            }
        }

        # Add session context if present
        if "session_id" in mcp_request:
            gateway_request["metadata"]["session_id"] = mcp_request["session_id"]

        return gateway_request

    @classmethod
    def gateway_response_to_mcp(cls, gateway_result: "MCPToolInvocationResult", mcp_request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Translate Gateway result to MCP response format.

        Args:
            gateway_result: Result from Gateway API
            mcp_request_id: Original MCP request ID for correlation

        Returns:
            MCP protocol formatted response
        """
        mcp_response = {
            "id": mcp_request_id or gateway_result.metadata.get("mcp_request_id"),
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(gateway_result.output) if gateway_result.output else None
                    }
                ],
                "isError": not gateway_result.success
            },
            "meta": {
                "executionTimeSeconds": gateway_result.execution_time_seconds,
                "toolName": gateway_result.tool_name,
                "deploymentId": gateway_result.deployment_id,
                "timestamp": datetime.utcnow().isoformat(),
                "cached": gateway_result.is_cached
            }
        }

        # Add error information if present
        if gateway_result.error:
            mcp_response["error"] = {
                "code": cls._map_gateway_error_to_mcp(gateway_result.error),
                "message": gateway_result.error
            }

        return mcp_response

    @classmethod
    def tool_schema_to_mcp(cls, tool_name: str, gateway_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Gateway tool schema to MCP tool format.

        Args:
            tool_name: Name of the tool
            gateway_schema: Tool schema from Gateway

        Returns:
            MCP tool description format
        """
        return {
            "name": tool_name,
            "description": gateway_schema.get("description", ""),
            "inputSchema": gateway_schema.get("input_schema", {
                "type": "object",
                "properties": {},
                "required": []
            })
        }

    @classmethod
    def _map_gateway_error_to_mcp(cls, gateway_error: str) -> str:
        """Map Gateway error to MCP error code"""
        # Reverse mapping from ERROR_CODE_MAP
        reverse_map = {v: k for k, v in cls.ERROR_CODE_MAP.items()}
        return reverse_map.get(gateway_error, "InternalError")


class AuthenticationHandler:
    """
    Handles authentication and authorization for Gateway API calls.

    Supports:
    - OAuth token validation
    - API key validation
    - Bearer token authentication
    - Credential refresh
    """

    def __init__(
        self,
        secrets_adapter: SecretsManagerAdapter,
        oauth_service: OAuthFlowService,
        config: Optional[AgentCoreConfig] = None
    ):
        self.secrets_adapter = secrets_adapter
        self.oauth_service = oauth_service
        self.config = config or get_config()

    async def authenticate_request(
        self,
        auth_header: Optional[str] = None,
        account_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate an incoming request and extract credentials.

        Args:
            auth_header: Authorization header from request
            account_id: Account ID for tenant isolation
            service_name: Service name for credential lookup

        Returns:
            Dictionary containing authentication context and credentials
        """
        auth_context = {
            "authenticated": False,
            "auth_type": None,
            "credentials": None
        }

        if not auth_header:
            return auth_context

        # Handle Bearer token (OAuth)
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            auth_context["auth_type"] = "bearer"

            # Try to get stored credentials for this service
            if account_id and service_name:
                try:
                    stored_creds = await self.secrets_adapter.get_credentials(account_id, service_name)
                    if stored_creds.get("access_token") == token:
                        auth_context["authenticated"] = True
                        auth_context["credentials"] = stored_creds

                        # Check if token needs refresh
                        if self._should_refresh_token(stored_creds):
                            logger.info(f"Token needs refresh for {account_id}/{service_name}")
                            # Token refresh would happen here
                            # new_creds = await self.oauth_service.refresh_token(...)
                            # await self.secrets_adapter.update_credentials(...)
                except Exception as e:
                    logger.warning(f"Failed to validate credentials: {e}")

        # Handle API key
        elif auth_header.startswith("ApiKey "):
            api_key = auth_header[7:]  # Remove "ApiKey " prefix
            auth_context["auth_type"] = "api_key"

            # Validate API key against stored credentials
            if account_id and service_name:
                try:
                    stored_creds = await self.secrets_adapter.get_credentials(account_id, service_name)
                    if stored_creds.get("api_key") == api_key:
                        auth_context["authenticated"] = True
                        auth_context["credentials"] = stored_creds
                except Exception as e:
                    logger.warning(f"Failed to validate API key: {e}")

        return auth_context

    def _should_refresh_token(self, credentials: Dict[str, Any]) -> bool:
        """Check if OAuth token needs refresh"""
        expires_at = credentials.get("expires_at")
        if not expires_at:
            return False

        # Refresh if token expires within 5 minutes
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        return datetime.utcnow() + timedelta(minutes=5) >= expires_at

    async def get_credentials_for_deployment(
        self,
        deployment_id: str,
        account_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get credentials for a Gateway deployment.

        Args:
            deployment_id: Gateway deployment ID
            account_id: Account ID for tenant isolation

        Returns:
            Credentials dictionary or None if not found
        """
        # Extract service name from deployment_id
        # Format: gateway-{service_name}-{account_id}-{timestamp}
        parts = deployment_id.split("-")
        if len(parts) >= 2:
            service_name = parts[1]  # Second part is service name
        else:
            service_name = deployment_id

        try:
            return await self.secrets_adapter.get_credentials(account_id, service_name)
        except Exception as e:
            logger.warning(f"Failed to get credentials for {deployment_id}: {e}")
            return None


class LambdaProxy:
    """
    Lambda Proxy for MCP → Gateway protocol translation.

    This class acts as the main entry point for Lambda function handlers,
    translating MCP protocol requests to Gateway API calls.

    Usage in Lambda:
        proxy = LambdaProxy()
        response = await proxy.handle_event(event, context)
    """

    def __init__(
        self,
        gateway_adapter: Optional["AgentCoreGatewayAdapter"] = None,
        translator: Optional[MCPProtocolTranslator] = None,
        auth_handler: Optional[AuthenticationHandler] = None,
        config: Optional[AgentCoreConfig] = None
    ):
        """
        Initialize Lambda Proxy.

        Args:
            gateway_adapter: Gateway adapter for API calls
            translator: Protocol translator
            auth_handler: Authentication handler
            config: AgentCore configuration
        """
        self.config = config or get_config()

        # Lazy import to avoid circular dependency
        if gateway_adapter is None:
            from ..adapters.gateway import AgentCoreGatewayAdapter
            self.gateway_adapter = AgentCoreGatewayAdapter(config=self.config)
        else:
            self.gateway_adapter = gateway_adapter

        self.translator = translator or MCPProtocolTranslator()
        self.auth_handler = auth_handler or self._create_auth_handler()

        # Request/response cache for performance
        self._request_cache: Dict[str, Any] = {}

    def _create_auth_handler(self) -> AuthenticationHandler:
        """Create authentication handler with required services"""
        secrets_adapter = SecretsManagerAdapter(config=self.config)
        oauth_service = OAuthFlowService(config=self.config)
        return AuthenticationHandler(secrets_adapter, oauth_service, self.config)

    async def handle_event(self, event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        """
        Main Lambda handler entry point.

        Args:
            event: Lambda event (API Gateway request format)
            context: Lambda context

        Returns:
            Lambda response (API Gateway response format)
        """
        try:
            # Extract request details
            http_method = event.get("httpMethod", event.get("requestContext", {}).get("http", {}))
            path = event.get("path", event.get("rawPath", ""))

            logger.info(f"Received {http_method} request to {path}")

            # Route to appropriate handler
            if path == "/mcp/tools/list" or http_method == "GET" and "tools" in path:
                return await self._handle_list_tools(event)
            elif path == "/mcp/tools/invoke" or http_method == "POST" and "invoke" in path:
                return await self._handle_tool_invocation(event)
            elif path == "/mcp/deployments/create" or http_method == "POST" and "deploy" in path:
                return await self._handle_create_deployment(event)
            elif path == "/mcp/deployments/delete" or http_method == "DELETE" and "delete" in path:
                return await self._handle_delete_deployment(event)
            elif path == "/health":
                return self._health_check()
            else:
                return self._error_response(404, "Not Found", f"No handler for {path}")

        except Exception as e:
            logger.exception(f"Error handling Lambda event: {e}")
            return self._error_response(500, "Internal Server Error", str(e))

    async def _handle_list_tools(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle list tools request.

        Returns available tools from Gateway deployment.
        """
        try:
            # Extract query parameters
            query_params = event.get("queryStringParameters") or {}
            account_id = query_params.get("account_id", "default")
            deployment_id = query_params.get("deployment_id")

            if not deployment_id:
                return self._error_response(400, "Bad Request", "deployment_id parameter required")

            # Get deployment details
            deployment = await self.gateway_adapter.get_deployment(deployment_id)

            # Transform tools to MCP format
            tools = []
            # Tools would be retrieved from deployment.mcp_config
            # For now, return empty list as example

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "tools": tools,
                    "deployment_id": deployment_id,
                    "service_name": deployment.service_name
                })
            }

        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return self._error_response(500, "Internal Server Error", str(e))

    async def _handle_tool_invocation(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool invocation request.

        Translates MCP request to Gateway API call.
        """
        try:
            # Parse request body
            body = json.loads(event.get("body", "{}"))

            # Extract parameters
            deployment_id = body.get("deployment_id")
            mcp_request = body.get("request", {})
            account_id = body.get("account_id", "default")

            if not deployment_id:
                return self._error_response(400, "Bad Request", "deployment_id is required")

            # Authenticate request
            auth_header = event.get("headers", {}).get("Authorization", event.get("headers", {}).get("authorization"))
            auth_context = await self.auth_handler.authenticate_request(
                auth_header=auth_header,
                account_id=account_id,
                service_name=self._extract_service_name(deployment_id)
            )

            # Translate MCP request to Gateway format
            gateway_request = self.translator.mcp_request_to_gateway(mcp_request)

            # Get credentials if authenticated
            credentials = None
            if auth_context["authenticated"]:
                credentials = auth_context.get("credentials")
            else:
                # Try to get credentials from deployment
                credentials = await self.auth_handler.get_credentials_for_deployment(
                    deployment_id, account_id
                )

            # Invoke tool via Gateway
            gateway_result = await self.gateway_adapter.invoke_mcp_tool(
                gateway_deployment_id=deployment_id,
                tool_name=gateway_request["tool_name"],
                parameters=gateway_request["parameters"],
                credentials=credentials
            )

            # Translate Gateway result to MCP response
            mcp_response = self.translator.gateway_response_to_mcp(
                gateway_result,
                mcp_request_id=mcp_request.get("id")
            )

            return {
                "statusCode": 200 if gateway_result.success else 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(mcp_response)
            }

        except json.JSONDecodeError as e:
            return self._error_response(400, "Bad Request", f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error invoking tool: {e}")
            return self._error_response(500, "Internal Server Error", str(e))

    async def _handle_create_deployment(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle create deployment request.

        Creates a new Gateway deployment for MCP server.
        """
        try:
            body = json.loads(event.get("body", "{}"))

            mcp_config = body.get("mcp_config")
            account_id = body.get("account_id", "default")

            if not mcp_config:
                return self._error_response(400, "Bad Request", "mcp_config is required")

            # Deploy MCP server via Gateway
            deployment_id = await self.gateway_adapter.deploy_mcp_server(
                mcp_config=mcp_config,
                account_id=account_id
            )

            return {
                "statusCode": 201,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "deployment_id": deployment_id,
                    "status": "created",
                    "message": "MCP server deployment created successfully"
                })
            }

        except json.JSONDecodeError as e:
            return self._error_response(400, "Bad Request", f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error creating deployment: {e}")
            return self._error_response(500, "Internal Server Error", str(e))

    async def _handle_delete_deployment(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle delete deployment request.

        Deletes a Gateway deployment.
        """
        try:
            query_params = event.get("queryStringParameters") or {}
            deployment_id = query_params.get("deployment_id")

            if not deployment_id:
                return self._error_response(400, "Bad Request", "deployment_id is required")

            # Delete deployment via Gateway
            result = await self.gateway_adapter.delete_gateway_deployment(
                gateway_deployment_id=deployment_id
            )

            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "deployment_id": deployment_id,
                    "deleted": result,
                    "message": "Deployment deleted successfully"
                })
            }

        except Exception as e:
            logger.error(f"Error deleting deployment: {e}")
            return self._error_response(500, "Internal Server Error", str(e))

    def _health_check(self) -> Dict[str, Any]:
        """Health check endpoint"""
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "healthy",
                "service": "agentcore-lambda-proxy",
                "timestamp": datetime.utcnow().isoformat()
            })
        }

    def _error_response(self, status_code: int, error_type: str, message: str) -> Dict[str, Any]:
        """Generate error response in API Gateway format"""
        return {
            "statusCode": status_code,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": error_type,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            })
        }

    def _extract_service_name(self, deployment_id: str) -> str:
        """Extract service name from deployment ID"""
        parts = deployment_id.split("-")
        if len(parts) >= 2:
            return parts[1]
        return deployment_id

    async def warm_up(self) -> Dict[str, Any]:
        """
        Warm up the proxy for cold start optimization.

        Pre-loads configurations and establishes connections.
        """
        logger.info("Warming up Lambda Proxy...")

        # Warm up Gateway adapter
        # This would establish connections to AWS services

        return {
            "status": "warmed_up",
            "timestamp": datetime.utcnow().isoformat()
        }
