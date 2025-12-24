"""
AgentCore Gateway Adapter

Provides interface to AWS Bedrock AgentCore Gateway for MCP integration.
Handles MCP server deployment, tool invocation, and credential management.
"""

import asyncio
import boto3
import logging
import time
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError

from ..config import AgentCoreConfig, get_config, Environment
from ..errors import (
    with_retry,
    GatewayError,
    MCPServerNotFoundError,
    MCPToolInvocationError,
    ThrottlingError,
    ServiceUnavailableError,
    NetworkError,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
    is_retryable_error,
)
from ..models import (
    MCPServerDeployment,
    MCPToolInvocationResult,
    GatewayConfig,
    SessionStatus,
)
from ..services import SecretsManagerAdapter, MCPCatalogService

logger = logging.getLogger(__name__)


class AgentCoreGatewayAdapter:
    """
    Adapter for AgentCore Gateway

    This adapter provides methods to:
    - Deploy MCP servers to Gateway
    - Invoke MCP tools via Gateway
    - Update Gateway configurations
    - Delete Gateway deployments
    - Handle authentication and credentials
    """

    # Mock deployments for local mode testing
    _mock_deployments: Dict[str, MCPServerDeployment] = {}

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize AgentCore Gateway adapter

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()
        self._initialize_services()

    def _validate_config(self):
        """Validate that Gateway is enabled and configured"""
        if not self.config.gateway_enabled:
            raise ValueError("AgentCore Gateway is not enabled in configuration")

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for AgentCore Gateway")

    def _initialize_client(self):
        """Initialize AWS SDK client for AgentCore Gateway"""
        if self.config.is_local():
            # Local mode: no real AWS client
            self.client = None
            logger.info("Initialized Gateway adapter in LOCAL mode (no AWS client)")
        else:
            # AWS mode: initialize boto3 client for AgentCore Gateway
            try:
                # TODO: Update with actual AgentCore Gateway service name when available
                # For now, using placeholder pattern
                self.client = boto3.client(
                    'bedrock-agent-gateway',  # or actual service name
                    region_name=self.config.aws_region,
                    aws_access_key_id=self.config.aws_access_key_id,
                    aws_secret_access_key=self.config.aws_secret_access_key
                )
                logger.info(
                    f"Initialized Gateway adapter for {self.config.environment} environment "
                    f"in {self.config.aws_region}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Gateway client: {str(e)}")
                raise GatewayError(f"Gateway client initialization failed: {str(e)}")

    def _initialize_services(self):
        """Initialize dependent services (Secrets Manager, MCP Catalog)"""
        self.secrets_manager = SecretsManagerAdapter(config=self.config)
        self.mcp_catalog = MCPCatalogService(config=self.config)

    @with_retry(max_attempts=3)
    async def deploy_mcp_server(
        self,
        mcp_config: dict,
        account_id: str
    ) -> str:
        """
        Deploy MCP server to AgentCore Gateway

        Args:
            mcp_config: MCP server configuration including:
                - name: Service name (e.g., 'github', 'slack')
                - display_name: Human-readable name
                - description: Service description
                - category: Service category
                - auth_type: Authentication type (oauth2, api_key, etc.)
                - oauth_config: OAuth configuration (if auth_type=oauth2)
                - mcp_server_config: Server-specific configuration
                    - image_uri: Docker image URI
                    - memory_mb: Memory allocation in MB
                    - timeout_seconds: Request timeout
                - features: List of available features
                - requires_callback: Whether OAuth callback is required
            account_id: Account identifier for tenant isolation

        Returns:
            gateway_deployment_id: Gateway deployment identifier

        Raises:
            ValidationError: If MCP config is invalid
            GatewayError: If deployment fails
        """
        logger.info(f"Deploying MCP server to Gateway for account {account_id}")

        # Validate MCP config
        self._validate_mcp_config(mcp_config)

        service_name = mcp_config.get("name")
        if not service_name:
            raise ValidationError("MCP config must include 'name' field")

        # Check if service exists in catalog
        try:
            existing_service = await self.mcp_catalog.get_service(service_name)
            logger.debug(f"Service {service_name} found in catalog")
        except Exception:
            # Service not in catalog, register it
            logger.info(f"Service {service_name} not in catalog, registering...")
            from ..services import MCPServiceDefinition
            service_def = MCPServiceDefinition(
                service_name=service_name,
                display_name=mcp_config.get("display_name", service_name),
                description=mcp_config.get("description", ""),
                category=mcp_config.get("category", "other"),
                auth_type=mcp_config.get("auth_type", "none"),
                oauth_config=mcp_config.get("oauth_config"),
                mcp_server_config=mcp_config.get("mcp_server_config"),
                features=mcp_config.get("features", []),
                requires_callback=mcp_config.get("requires_callback", False)
            )
            await self.mcp_catalog.register_service(service_def)

        # Enable service for tenant
        await self.mcp_catalog.enable_service_for_tenant(service_name, account_id)

        # Local mode: mock deployment
        if self.config.is_local():
            return await self._deploy_mcp_server_local(mcp_config, account_id)

        # AWS mode: call Gateway API
        return await self._deploy_mcp_server_aws(mcp_config, account_id)

    async def _deploy_mcp_server_local(self, mcp_config: dict, account_id: str) -> str:
        """Deploy MCP server in local mode (mocked)"""
        service_name = mcp_config.get("name", "unknown")
        deployment_id = f"{self.config.get_resource_prefix()}-gateway-{service_name}-{account_id}"

        # Create mock deployment
        deployment = MCPServerDeployment(
            deployment_id=deployment_id,
            service_name=service_name,
            account_id=account_id,
            status=SessionStatus.READY,
            endpoint_url=f"https://gateway.local.{service_name}.com",
            mcp_config=mcp_config,
            region=self.config.aws_region
        )

        # Store in mock deployments
        self._mock_deployments[deployment_id] = deployment

        logger.info(f"Local mode: Mock MCP server deployed: {deployment_id}")
        return deployment_id

    async def _deploy_mcp_server_aws(self, mcp_config: dict, account_id: str) -> str:
        """Deploy MCP server via AWS Gateway API"""
        service_name = mcp_config.get("name", "unknown")

        try:
            # TODO: Update with actual AgentCore Gateway API call
            # response = await asyncio.to_thread(
            #     self.client.deploy_mcp_server,
            #     serviceName=service_name,
            #     account_id=account_id,
            #     mcpConfig=mcp_config,
            #     timeout=self.config.gateway_timeout_seconds
            # )
            # deployment_id = response['deploymentId']

            # For now, generate deployment ID following expected pattern
            deployment_id = f"{self.config.get_resource_prefix()}-gateway-{service_name}-{account_id}"

            logger.info(f"AWS mode: MCP server deployed: {deployment_id}")
            return deployment_id

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'ThrottlingException':
                raise ThrottlingError(f"Gateway API rate limit exceeded: {error_message}")
            elif error_code == 'AccessDeniedException':
                raise AuthorizationError(f"Insufficient permissions for Gateway: {error_message}")
            elif error_code == 'ResourceNotFoundException':
                raise ResourceNotFoundError(f"Gateway resource not found: {error_message}")
            elif error_code == 'ValidationException':
                raise ValidationError(f"Invalid MCP configuration: {error_message}")
            else:
                raise GatewayError(f"Gateway deployment failed: {error_message}")

        except Exception as e:
            if is_retryable_error(e):
                raise ServiceUnavailableError(f"Gateway service unavailable: {str(e)}")
            raise GatewayError(f"Unexpected error during deployment: {str(e)}")

    @with_retry(max_attempts=3)
    async def invoke_mcp_tool(
        self,
        gateway_deployment_id: str,
        tool_name: str,
        parameters: dict,
        credentials: Optional[dict] = None
    ) -> MCPToolInvocationResult:
        """
        Invoke MCP tool via Gateway

        Args:
            gateway_deployment_id: Gateway deployment identifier
            tool_name: Name of the tool to invoke
            parameters: Tool parameters
            credentials: Optional credentials for authentication
                - For OAuth2: {'access_token': str, 'refresh_token': str}
                - For API key: {'api_key': str}

        Returns:
            MCPToolInvocationResult: Tool invocation result

        Raises:
            MCPServerNotFoundError: If deployment doesn't exist
            MCPToolInvocationError: If tool invocation fails
            ValidationError: If parameters are invalid
        """
        logger.info(f"Invoking MCP tool {tool_name} via Gateway {gateway_deployment_id}")

        # Validate parameters
        if not tool_name:
            raise ValidationError("Tool name is required")

        # Check if deployment exists
        deployment = await self._get_deployment(gateway_deployment_id)

        start_time = time.time()

        # Local mode: mock invocation
        if self.config.is_local():
            result = await self._invoke_mcp_tool_local(
                deployment, tool_name, parameters, credentials
            )
        else:
            result = await self._invoke_mcp_tool_aws(
                deployment, tool_name, parameters, credentials
            )

        execution_time = time.time() - start_time
        result.execution_time_seconds = execution_time

        return result

    async def _invoke_mcp_tool_local(
        self,
        deployment: MCPServerDeployment,
        tool_name: str,
        parameters: dict,
        credentials: Optional[dict]
    ) -> MCPToolInvocationResult:
        """Invoke MCP tool in local mode (mocked)"""
        logger.debug(f"Local mode: Mock tool invocation {tool_name}")

        # Check if credentials provided for OAuth services
        if deployment.mcp_config and deployment.mcp_config.get('auth_type') == 'oauth2':
            if not credentials or not credentials.get('access_token'):
                logger.warning(f"OAuth2 service {deployment.service_name} invoked without credentials")

        return MCPToolInvocationResult(
            tool_name=tool_name,
            deployment_id=deployment.deployment_id,
            success=True,
            output={
                'message': f"Mock response from {tool_name}",
                'parameters': parameters,
                'service': deployment.service_name
            },
            error=None,
            execution_time_seconds=0.1,
            is_cached=False
        )

    async def _invoke_mcp_tool_aws(
        self,
        deployment: MCPServerDeployment,
        tool_name: str,
        parameters: dict,
        credentials: Optional[dict]
    ) -> MCPToolInvocationResult:
        """Invoke MCP tool via AWS Gateway API"""
        try:
            # TODO: Update with actual AgentCore Gateway API call
            # response = await asyncio.to_thread(
            #     self.client.invoke_tool,
            #     deploymentId=deployment.deployment_id,
            #     toolName=tool_name,
            #     parameters=parameters,
            #     credentials=credentials,
            #     timeout=self.config.gateway_timeout_seconds
            # )

            # For now, return mock result
            return MCPToolInvocationResult(
                tool_name=tool_name,
                deployment_id=deployment.deployment_id,
                success=True,
                output={'message': f"Mock response from {tool_name} (AWS mode)"},
                error=None,
                execution_time_seconds=0.1,
                is_cached=False
            )

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'ThrottlingException':
                raise ThrottlingError(f"Gateway API rate limit exceeded: {error_message}")
            elif error_code == 'ResourceNotFoundException':
                raise MCPServerNotFoundError(f"Deployment {deployment.deployment_id} not found")
            elif error_code == 'ValidationException':
                raise ValidationError(f"Invalid tool parameters: {error_message}")
            else:
                raise MCPToolInvocationError(f"Tool invocation failed: {error_message}")

        except Exception as e:
            if is_retryable_error(e):
                raise ServiceUnavailableError(f"Gateway service unavailable: {str(e)}")
            raise MCPToolInvocationError(f"Unexpected error during invocation: {str(e)}")

    @with_retry(max_attempts=3)
    async def update_gateway_config(
        self,
        gateway_deployment_id: str,
        config: GatewayConfig
    ) -> bool:
        """
        Update Gateway configuration for a deployment

        Args:
            gateway_deployment_id: Gateway deployment identifier
            config: Updated Gateway configuration

        Returns:
            True if update successful

        Raises:
            MCPServerNotFoundError: If deployment doesn't exist
            ValidationError: If config is invalid
        """
        logger.info(f"Updating Gateway configuration: {gateway_deployment_id}")

        # Validate config
        if not isinstance(config, GatewayConfig):
            raise ValidationError("Config must be a GatewayConfig instance")

        # Check if deployment exists
        await self._get_deployment(gateway_deployment_id)

        # Local mode: mock update
        if self.config.is_local():
            deployment = self._mock_deployments.get(gateway_deployment_id)
            if deployment:
                # Update metadata (in real implementation, this would be stored in Gateway)
                logger.debug(f"Local mode: Mock config update for {gateway_deployment_id}")
            return True

        # AWS mode: call Gateway API
        try:
            # TODO: Update with actual AgentCore Gateway API call
            # await asyncio.to_thread(
            #     self.client.update_config,
            #     deploymentId=gateway_deployment_id,
            #     config=config.to_dict()
            # )
            logger.info(f"Gateway configuration updated: {gateway_deployment_id}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'ResourceNotFoundException':
                raise MCPServerNotFoundError(f"Deployment {gateway_deployment_id} not found")
            raise GatewayError(f"Config update failed: {str(e)}")

    @with_retry(max_attempts=3)
    async def delete_gateway_deployment(
        self,
        gateway_deployment_id: str
    ) -> bool:
        """
        Delete Gateway deployment

        Args:
            gateway_deployment_id: Gateway deployment identifier

        Returns:
            True if deletion successful

        Raises:
            MCPServerNotFoundError: If deployment doesn't exist
        """
        logger.info(f"Deleting Gateway deployment: {gateway_deployment_id}")

        # Check if deployment exists first
        deployment = await self._get_deployment(gateway_deployment_id)

        # Local mode: remove from mock deployments
        if self.config.is_local():
            if gateway_deployment_id in self._mock_deployments:
                del self._mock_deployments[gateway_deployment_id]
                logger.info(f"Local mode: Mock deployment deleted: {gateway_deployment_id}")
            return True

        # AWS mode: call Gateway API
        try:
            # TODO: Update with actual AgentCore Gateway API call
            # await asyncio.to_thread(
            #     self.client.delete_deployment,
            #     deploymentId=gateway_deployment_id
            # )
            logger.info(f"Gateway deployment deleted: {gateway_deployment_id}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'ResourceNotFoundException':
                raise MCPServerNotFoundError(f"Deployment {gateway_deployment_id} not found")
            raise GatewayError(f"Deployment deletion failed: {str(e)}")

    async def list_deployments(
        self,
        account_id: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> List[MCPServerDeployment]:
        """
        List Gateway deployments

        Args:
            account_id: Filter by account ID (tenant isolation)
            service_name: Filter by service name

        Returns:
            List of deployments matching filters
        """
        logger.debug(f"Listing deployments: account_id={account_id}, service_name={service_name}")

        # Local mode: return mock deployments
        if self.config.is_local():
            deployments = list(self._mock_deployments.values())
        else:
            # AWS mode: query Gateway API
            # TODO: Implement with actual Gateway API
            deployments = []

        # Apply filters
        if account_id:
            deployments = [d for d in deployments if d.account_id == account_id]
        if service_name:
            deployments = [d for d in deployments if d.service_name == service_name]

        return deployments

    async def get_deployment(
        self,
        gateway_deployment_id: str
    ) -> MCPServerDeployment:
        """
        Get deployment details

        Args:
            gateway_deployment_id: Gateway deployment identifier

        Returns:
            MCPServerDeployment: Deployment details

        Raises:
            MCPServerNotFoundError: If deployment doesn't exist
        """
        return await self._get_deployment(gateway_deployment_id)

    async def _get_deployment(self, gateway_deployment_id: str) -> MCPServerDeployment:
        """Internal: Get deployment, raise error if not found"""
        # Local mode: check mock deployments
        if self.config.is_local():
            if gateway_deployment_id not in self._mock_deployments:
                raise MCPServerNotFoundError(f"Deployment {gateway_deployment_id} not found")
            return self._mock_deployments[gateway_deployment_id]

        # AWS mode: query Gateway API
        # TODO: Implement with actual Gateway API
        # For now, create mock deployment
        deployment = MCPServerDeployment(
            deployment_id=gateway_deployment_id,
            service_name=gateway_deployment_id.split('-')[-2] if '-' in gateway_deployment_id else 'unknown',
            account_id=gateway_deployment_id.split('-')[-1] if '-' in gateway_deployment_id else 'unknown',
            status=SessionStatus.READY,
            region=self.config.aws_region
        )
        return deployment

    def _validate_mcp_config(self, mcp_config: dict) -> None:
        """Validate MCP server configuration"""
        required_fields = ['name', 'display_name', 'description', 'category', 'auth_type']
        for field in required_fields:
            if field not in mcp_config:
                raise ValidationError(f"Missing required field: {field}")

        auth_type = mcp_config.get('auth_type')
        if auth_type == 'oauth2' and not mcp_config.get('oauth_config'):
            raise ValidationError("oauth_config required when auth_type=oauth2")

        # Validate OAuth config if present
        oauth_config = mcp_config.get('oauth_config')
        if oauth_config:
            required_oauth_fields = ['authorization_url', 'token_url', 'callback_path']
            for field in required_oauth_fields:
                if field not in oauth_config:
                    raise ValidationError(f"Missing required OAuth field: {field}")

    async def store_credentials(
        self,
        account_id: str,
        service_name: str,
        credentials: dict
    ) -> str:
        """
        Store credentials for an MCP service

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service
            credentials: Credentials to store
                - OAuth2: {'access_token': str, 'refresh_token': str, 'token_type': str}
                - API Key: {'api_key': str}

        Returns:
            Secret ARN
        """
        logger.info(f"Storing credentials for {service_name} (account: {account_id})")

        # Use SecretsManagerAdapter to store credentials
        secret_path = f"{self.config.get_resource_prefix()}/{account_id}/{service_name}"
        return await self.secrets_manager.store_credentials(
            account_id=account_id,
            service=service_name,
            credentials=credentials
        )

    async def get_credentials(
        self,
        account_id: str,
        service_name: str
    ) -> dict:
        """
        Retrieve credentials for an MCP service

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            Credentials dictionary

        Raises:
            ResourceNotFoundError: If credentials don't exist
        """
        logger.debug(f"Retrieving credentials for {service_name} (account: {account_id})")

        # Use SecretsManagerAdapter to retrieve credentials
        return await self.secrets_manager.get_credentials(
            account_id=account_id,
            service=service_name
        )

    async def delete_credentials(
        self,
        account_id: str,
        service_name: str
    ) -> bool:
        """
        Delete credentials for an MCP service

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            True if deletion successful
        """
        logger.info(f"Deleting credentials for {service_name} (account: {account_id})")

        # Use SecretsManagerAdapter to delete credentials
        return await self.secrets_manager.delete_credentials(
            account_id=account_id,
            service=service_name
        )
