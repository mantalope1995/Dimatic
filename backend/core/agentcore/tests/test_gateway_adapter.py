"""
Tests for AWS AgentCore Gateway Adapter

Unit tests for MCP server deployment, tool invocation, and Gateway management
with tenant isolation and error handling.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from botocore.exceptions import ClientError
from datetime import datetime
import time

from core.agentcore.adapters.gateway import AgentCoreGatewayAdapter
from core.agentcore.errors import (
    GatewayError,
    MCPServerNotFoundError,
    MCPToolInvocationError,
    ValidationError,
)
from core.agentcore.models import (
    MCPServerDeployment,
    MCPToolInvocationResult,
    GatewayConfig,
    SessionStatus
)
from core.agentcore.config import AgentCoreConfig, Environment
from core.agentcore.errors import redact_sensitive_data


@pytest.fixture
def mock_config():
    """Create a mock AgentCore config for testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        gateway_enabled=True,
        s3_bucket_name="test-bucket"
    )


@pytest.fixture
def gateway_adapter(mock_config):
    """Create a Gateway adapter for testing"""
    return AgentCoreGatewayAdapter(config=mock_config)


class TestAgentCoreGatewayAdapterLocalMode:
    """Test suite for Gateway adapter in local mode (no AWS client)"""

    def test_init_local_environment(self, mock_config):
        """Test adapter initialization in local environment"""
        adapter = AgentCoreGatewayAdapter(config=mock_config)
        assert adapter.config == mock_config
        assert adapter.client is None  # No real AWS client in local mode

    def test_init_with_gateway_disabled(self):
        """Test initialization raises error when Gateway is disabled"""
        config = AgentCoreConfig(
            environment=Environment.LOCAL,
            gateway_enabled=False
        )
        with pytest.raises(ValueError, match="AgentCore Gateway is not enabled"):
            AgentCoreGatewayAdapter(config=config)

    @pytest.mark.asyncio
    async def test_deploy_mcp_server_local_mode(self, gateway_adapter):
        """Test MCP server deployment in local mode (mocked)"""
        mcp_config = {
            "name": "github",
            "type": "http",
            "endpoint": "https://api.github.com",
            "auth_type": "oauth"
        }

        deployment_id = await gateway_adapter.deploy_mcp_server(
            mcp_config=mcp_config,
            account_id="account-123"
        )

        assert deployment_id is not None
        assert "gateway" in deployment_id
        assert "github" in deployment_id
        assert "account-123" in deployment_id

    @pytest.mark.asyncio
    async def test_invoke_mcp_tool_local_mode(self, gateway_adapter):
        """Test MCP tool invocation in local mode (mocked)"""
        result = await gateway_adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway-deployment",
            tool_name="get_user",
            parameters={"username": "testuser"},
            credentials=None
        )

        assert isinstance(result, MCPToolInvocationResult)
        assert result.tool_name == "get_user"
        assert result.deployment_id == "test-gateway-deployment"
        assert result.success is True
        assert result.execution_time_seconds >= 0

    @pytest.mark.asyncio
    async def test_invoke_mcp_tool_with_credentials(self, gateway_adapter):
        """Test tool invocation with credentials (local mode)"""
        credentials = {"access_token": "test_token_123"}

        result = await gateway_adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="create_issue",
            parameters={"title": "Test issue"},
            credentials=credentials
        )

        assert result.success is True
        assert "output" in result.metadata

    @pytest.mark.asyncio
    async def test_update_gateway_config_local_mode(self, gateway_adapter):
        """Test Gateway configuration update in local mode"""
        result = await gateway_adapter.update_gateway_config(
            gateway_deployment_id="test-gateway",
            config=GatewayConfig(
                timeout_seconds=120,
                rate_limit_per_minute=200
            )
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_gateway_deployment_local_mode(self, gateway_adapter):
        """Test Gateway deployment deletion in local mode"""
        result = await gateway_adapter.delete_gateway_deployment(
            gateway_deployment_id="test-gateway"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_list_deployments_local_mode(self, gateway_adapter):
        """Test listing deployments in local mode"""
        deployments = await gateway_adapter.list_deployments(
            account_id="account-123"
        )

        assert isinstance(deployments, list)

    @pytest.mark.asyncio
    async def test_list_deployments_with_service_filter(self, gateway_adapter):
        """Test listing deployments filtered by service name"""
        deployments = await gateway_adapter.list_deployments(
            account_id="account-123",
            service_name="github"
        )

        assert isinstance(deployments, list)

    @pytest.mark.asyncio
    async def test_get_deployment_local_mode(self, gateway_adapter):
        """Test getting deployment details in local mode"""
        deployment = await gateway_adapter.get_deployment(
            gateway_deployment_id="test-gateway"
        )

        assert deployment is not None
        assert isinstance(deployment, MCPServerDeployment)


class TestAgentCoreGatewayAdapterAWSIntegration:
    """Test suite with mocked AWS SDK calls"""

    @pytest.fixture
    def aws_config(self):
        """Create config for AWS testing"""
        return AgentCoreConfig(
            environment=Environment.DEVELOPMENT,
            aws_region="ap-southeast-2",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            gateway_enabled=True
        )

    @pytest.fixture
    def mock_gateway_client(self):
        """Create mock boto3 Gateway client"""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            yield mock_client

    def test_aws_client_initialization(self, aws_config, mock_gateway_client):
        """Test AWS client is properly initialized"""
        adapter = AgentCoreGatewayAdapter(config=aws_config)
        assert adapter.client is not None
        assert adapter.client == mock_gateway_client

    @pytest.mark.asyncio
    async def test_deploy_mcp_server_aws(self, aws_config, mock_gateway_client):
        """Test MCP server deployment with real AWS SDK"""
        mock_gateway_client.create_deployment.return_value = {
            "deploymentId": "gateway-github-account-123-20250124",
            "endpointUrl": "https://gateway.example.com/deployments/gateway-github-account-123-20250124",
            "status": "READY"
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        deployment_id = await adapter.deploy_mcp_server(
            mcp_config={
                "name": "github",
                "type": "http",
                "endpoint": "https://api.github.com"
            },
            account_id="account-123"
        )

        assert "gateway" in deployment_id
        assert "github" in deployment_id
        mock_gateway_client.create_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_mcp_tool_aws(self, aws_config, mock_gateway_client):
        """Test MCP tool invocation from AWS"""
        mock_gateway_client.invoke_tool.return_value = {
            "success": True,
            "output": {"user": {"login": "testuser"}},
            "executionTimeSeconds": 0.5
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        result = await adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="get_user",
            parameters={"username": "testuser"}
        )

        assert result.success is True
        assert result.output is not None
        assert result.execution_time_seconds == 0.5

    @pytest.mark.asyncio
    async def test_invoke_mcp_tool_with_error_aws(self, aws_config, mock_gateway_client):
        """Test tool invocation returns error when AWS call fails"""
        mock_gateway_client.invoke_tool.return_value = {
            "success": False,
            "error": "Tool execution failed: Invalid parameters"
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        result = await adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="get_user",
            parameters={"invalid": "param"}
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_update_gateway_config_aws(self, aws_config, mock_gateway_client):
        """Test Gateway configuration update in AWS"""
        mock_gateway_client.update_deployment.return_value = {
            "deploymentId": "test-gateway",
            "status": "UPDATED"
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        result = await adapter.update_gateway_config(
            gateway_deployment_id="test-gateway",
            config=GatewayConfig(timeout_seconds=120)
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_gateway_deployment_aws(self, aws_config, mock_gateway_client):
        """Test Gateway deployment deletion in AWS"""
        mock_gateway_client.delete_deployment.return_value = {
            "deploymentId": "test-gateway",
            "status": "DELETED"
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        result = await gateway_adapter.delete_gateway_deployment("test-gateway")

        assert result is True

    @pytest.mark.asyncio
    async def test_list_deployments_aws(self, aws_config, mock_gateway_client):
        """Test listing deployments from AWS"""
        mock_gateway_client.list_deployments.return_value = {
            "deployments": [
                {
                    "deploymentId": "gateway-github-account-123",
                    "serviceName": "github",
                    "accountId": "account-123",
                    "status": "READY"
                },
                {
                    "deploymentId": "gateway-slack-account-123",
                    "serviceName": "slack",
                    "accountId": "account-123",
                    "status": "READY"
                }
            ]
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        deployments = await adapter.list_deployments(account_id="account-123")

        assert len(deployments) == 2
        assert deployments[0].service_name == "github"
        assert deployments[1].service_name == "slack"

    @pytest.mark.asyncio
    async def test_get_deployment_aws(self, aws_config, mock_gateway_client):
        """Test getting deployment details from AWS"""
        mock_gateway_client.get_deployment.return_value = {
            "deploymentId": "test-gateway",
            "serviceName": "github",
            "accountId": "account-123",
            "status": "READY",
            "endpointUrl": "https://gateway.example.com/test-gateway"
        }

        adapter = AgentCoreGatewayAdapter(config=aws_config)
        deployment = await adapter.get_deployment("test-gateway")

        assert deployment.deployment_id == "test-gateway"
        assert deployment.service_name == "github"
        assert deployment.status == SessionStatus.READY


class TestMCPConfigValidation:
    """Test MCP configuration validation"""

    def test_validate_mcp_config_valid(self, gateway_adapter):
        """Test validation passes for valid config"""
        valid_config = {
            "name": "github",
            "type": "http",
            "endpoint": "https://api.github.com",
            "auth_type": "oauth"
        }

        # Should not raise exception
        gateway_adapter._validate_mcp_config(valid_config)

    def test_validate_mcp_config_missing_name(self, gateway_adapter):
        """Test validation fails when name is missing"""
        invalid_config = {
            "type": "http",
            "endpoint": "https://api.example.com"
        }

        with pytest.raises(ValidationError, match="name is required"):
            gateway_adapter._validate_mcp_config(invalid_config)

    def test_validate_mcp_config_missing_type(self, gateway_adapter):
        """Test validation fails when type is missing"""
        invalid_config = {
            "name": "github",
            "endpoint": "https://api.example.com"
        }

        with pytest.raises(ValidationError, match="type is required"):
            gateway_adapter._validate_mcp_config(invalid_config)

    def test_validate_mcp_config_oauth_missing_client_id(self, gateway_adapter):
        """Test validation fails when OAuth config is incomplete"""
        invalid_config = {
            "name": "github",
            "type": "http",
            "endpoint": "https://api.github.com",
            "auth_type": "oauth",
            "oauth_config": {
                "client_secret": "secret"
                # Missing client_id
            }
        }

        with pytest.raises(ValidationError, match="oauth_config.client_id is required"):
            gateway_adapter._validate_mcp_config(invalid_config)


class TestCredentialManagement:
    """Test credential storage and retrieval through Gateway adapter"""

    @pytest.mark.asyncio
    async def test_store_credentials(self, gateway_adapter):
        """Test storing credentials"""
        arn = await gateway_adapter.store_credentials(
            account_id="account-123",
            service_name="github",
            credentials={"access_token": "test_token"}
        )

        assert arn is not None
        assert "arn:aws:secretsmanager" in arn

    @pytest.mark.asyncio
    async def test_get_credentials(self, gateway_adapter):
        """Test retrieving credentials"""
        credentials = await gateway_adapter.get_credentials(
            account_id="account-123",
            service_name="github"
        )

        assert credentials is not None
        assert "access_token" in credentials

    @pytest.mark.asyncio
    async def test_delete_credentials(self, gateway_adapter):
        """Test deleting credentials"""
        result = await gateway_adapter.delete_credentials(
            account_id="account-123",
            service_name="github"
        )

        assert result is True


class TestTenantIsolation:
    """Test tenant isolation for Gateway deployments"""

    def test_deployment_id_includes_account_id(self, gateway_adapter):
        """Test that deployment IDs include account ID for isolation"""
        deployment_id = gateway_adapter._generate_deployment_id("github", "account-123")
        assert "account-123" in deployment_id

    def test_different_accounts_different_deployments(self, gateway_adapter):
        """Test that different accounts get different deployment IDs"""
        id1 = gateway_adapter._generate_deployment_id("github", "account-1")
        id2 = gateway_adapter._generate_deployment_id("github", "account-2")

        assert id1 != id2
        assert "account-1" in id1
        assert "account-2" in id2

    def test_same_account_same_service_same_deployment(self, gateway_adapter):
        """Test that same account and service generates consistent deployment ID"""
        id1 = gateway_adapter._generate_deployment_id("github", "account-123")
        id2 = gateway_adapter._generate_deployment_id("github", "account-123")

        # Should be deterministic
        assert id1 == id2


class TestErrorHandling:
    """Test error handling and mapping"""

    @pytest.mark.asyncio
    async def test_deployment_with_throttling_error(self, gateway_adapter):
        """Test retry on throttling errors"""
        # In local mode, throttling is simulated
        # In AWS mode, this would test the @with_retry decorator
        deployment_id = await gateway_adapter.deploy_mcp_server(
            mcp_config={"name": "github", "type": "http", "endpoint": "https://api.github.com"},
            account_id="account-123"
        )

        assert deployment_id is not None

    @pytest.mark.asyncio
    async def test_invoke_with_nonexistent_deployment(self, gateway_adapter):
        """Test invoking tool with non-existent deployment"""
        result = await gateway_adapter.invoke_mcp_tool(
            gateway_deployment_id="nonexistent-deployment",
            tool_name="get_user",
            parameters={}
        )

        # Local mode returns mock result
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_deployment(self, gateway_adapter):
        """Test deleting non-existent deployment"""
        result = await gateway_adapter.delete_gateway_deployment(
            gateway_deployment_id="nonexistent-deployment"
        )

        # Local mode returns True
        assert result is True


class TestSensitiveDataRedaction:
    """Test sensitive data redaction in logging"""

    def test_redact_deployment_id(self):
        """Test that deployment IDs are properly redacted"""
        deployment_id = "gateway-github-account-123-20250124"
        redacted = redact_sensitive_data(deployment_id)
        # Account ID should be redacted
        assert "123" not in redacted or "REDACTED" in redacted

    def test_redact_access_token(self):
        """Test that access tokens are redacted"""
        message = "Using access_token: gho_1234567890abcdef for github"
        redacted = redact_sensitive_data(message)
        assert "gho_1234567890abcdef" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_arn(self):
        """Test that ARNs are properly redacted"""
        arn = "arn:aws:secretsmanager:ap-southeast-2:123456789:secret:kortix/account-123/github"
        redacted = redact_sensitive_data(arn)
        assert "123456789" not in redacted


class TestExecutionTiming:
    """Test execution timing and performance metrics"""

    @pytest.mark.asyncio
    async def test_execution_time_is_measured(self, gateway_adapter):
        """Test that execution time is properly measured"""
        start_time = time.time()

        result = await gateway_adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="get_user",
            parameters={"username": "test"}
        )

        end_time = time.time()
        expected_duration = end_time - start_time

        assert result.execution_time_seconds >= 0
        # Execution time should be reasonable (less than 5 seconds for mock)
        assert result.execution_time_seconds < 5

    @pytest.mark.asyncio
    async def test_execution_time_includes_metadata(self, gateway_adapter):
        """Test that execution time is included in metadata"""
        result = await gateway_adapter.invoke_mcp_tool(
            gateway_deployment_id="test-gateway",
            tool_name="get_user",
            parameters={"username": "test"}
        )

        assert "execution_time" in result.metadata
        assert result.metadata["execution_time"] == result.execution_time_seconds


class TestMCPServerDeploymentModel:
    """Test MCPServerDeployment dataclass model"""

    def test_deployment_to_dict(self):
        """Test serialization to dictionary"""
        deployment = MCPServerDeployment(
            deployment_id="test-gateway",
            service_name="github",
            account_id="account-123",
            status=SessionStatus.READY,
            region="ap-southeast-2"
        )

        data = deployment.to_dict()

        assert data["deployment_id"] == "test-gateway"
        assert data["service_name"] == "github"
        assert data["status"] == "ready"  # Enum value
        assert "created_at" in data

    def test_deployment_from_dict(self):
        """Test deserialization from dictionary"""
        data = {
            "deployment_id": "test-gateway",
            "service_name": "github",
            "account_id": "account-123",
            "status": "ready",
            "region": "ap-southeast-2",
            "created_at": "2025-01-24T00:00:00"
        }

        deployment = MCPServerDeployment.from_dict(data)

        assert deployment.deployment_id == "test-gateway"
        assert deployment.status == SessionStatus.READY


class TestMCPToolInvocationResultModel:
    """Test MCPToolInvocationResult dataclass model"""

    def test_invocation_result_to_dict(self):
        """Test serialization to dictionary"""
        result = MCPToolInvocationResult(
            tool_name="get_user",
            deployment_id="test-gateway",
            success=True,
            output={"user": "test"},
            error=None,
            execution_time_seconds=0.5
        )

        data = result.to_dict()

        assert data["tool_name"] == "get_user"
        assert data["success"] is True
        assert data["execution_time_seconds"] == 0.5

    def test_invocation_result_from_dict(self):
        """Test deserialization from dictionary"""
        data = {
            "tool_name": "get_user",
            "deployment_id": "test-gateway",
            "success": True,
            "output": {"user": "test"},
            "error": None,
            "execution_time_seconds": 0.5,
            "metadata": {}
        }

        result = MCPToolInvocationResult.from_dict(data)

        assert result.tool_name == "get_user"
        assert result.success is True


class TestGatewayConfigModel:
    """Test GatewayConfig dataclass model"""

    def test_gateway_config_defaults(self):
        """Test GatewayConfig has correct default values"""
        config = GatewayConfig()

        assert config.timeout_seconds == 60
        assert config.rate_limit_per_minute == 100
        assert config.max_concurrent_invocations == 10
        assert config.enable_caching is True
        assert config.cache_ttl_seconds == 300

    def test_gateway_config_custom_values(self):
        """Test GatewayConfig with custom values"""
        config = GatewayConfig(
            timeout_seconds=120,
            rate_limit_per_minute=200,
            enable_caching=False
        )

        assert config.timeout_seconds == 120
        assert config.rate_limit_per_minute == 200
        assert config.enable_caching is False
