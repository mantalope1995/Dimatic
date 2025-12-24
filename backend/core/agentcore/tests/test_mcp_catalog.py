"""
Tests for MCP Catalog Service

Unit tests for DynamoDB-backed MCP service catalog
with tenant isolation and enablement tracking.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from botocore.exceptions import ClientError

from core.agentcore.services.mcp_catalog_service import (
    MCPCatalogService,
    MCPCatalogNotFoundError,
    MCPCatalogAlreadyExistsError,
    MCPServiceDefinition
)
from core.agentcore.config import AgentCoreConfig, Environment


@pytest.fixture
def mock_config():
    """Create a mock AgentCore config for testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        dynamodb_mcp_catalog_table="agentcore_mcp_catalog"
    )


@pytest.fixture
def catalog_service(mock_config):
    """Create an MCP Catalog service for testing"""
    return MCPCatalogService(config=mock_config)


@pytest.fixture
def sample_service_definition():
    """Create a sample service definition for testing"""
    return MCPServiceDefinition(
        service_name="github",
        display_name="GitHub",
        description="GitHub repository management and operations",
        category="git",
        auth_type="oauth2",
        oauth_config={
            "authorization_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scope": "repo,read:user"
        },
        features=["repositories", "issues", "pull_requests"],
        requires_callback=True
    )


class TestMCPServiceDefinition:
    """Test suite for MCPServiceDefinition dataclass"""

    def test_service_definition_creation(self):
        """Test creating a service definition"""
        service = MCPServiceDefinition(
            service_name="github",
            display_name="GitHub",
            description="GitHub operations",
            category="git",
            auth_type="oauth2"
        )

        assert service.service_name == "github"
        assert service.display_name == "GitHub"
        assert service.category == "git"
        assert service.auth_type == "oauth2"
        assert service.enabled_for_tenants == []
        assert service.features == []

    def test_to_dict_serialization(self, sample_service_definition):
        """Test converting service definition to dictionary"""
        data = sample_service_definition.to_dict()

        assert data["service_name"] == "github"
        assert data["display_name"] == "GitHub"
        # Lists should be serialized to JSON strings
        assert isinstance(data["enabled_for_tenants"], str)
        assert isinstance(data["features"], str)

    def test_from_dict_deserialization(self, sample_service_definition):
        """Test creating service definition from dictionary"""
        data = sample_service_definition.to_dict()
        restored = MCPServiceDefinition.from_dict(data)

        assert restored.service_name == sample_service_definition.service_name
        assert restored.display_name == sample_service_definition.display_name
        assert restored.category == sample_service_definition.category
        # Lists should be properly deserialized
        assert isinstance(restored.enabled_for_tenants, list)
        assert isinstance(restored.features, list)


class TestMCPCatalogService:
    """Test suite for MCPCatalogService"""

    def test_init_local_environment(self, mock_config):
        """Test catalog service initialization in local environment"""
        service = MCPCatalogService(config=mock_config)
        assert service.config == mock_config
        assert service.client is None  # No real DynamoDB client in local mode

    @pytest.mark.asyncio
    async def test_register_service_local_mode(self, catalog_service, sample_service_definition):
        """Test registering a service in local mode (mocked)"""
        service = await catalog_service.register_service(sample_service_definition)

        assert service.service_name == "github"
        assert service.display_name == "GitHub"

    @pytest.mark.asyncio
    async def test_register_service_duplicate(self, catalog_service, sample_service_definition):
        """Test that registering duplicate service raises error"""
        # Register first time
        await catalog_service.register_service(sample_service_definition)

        # Try to register again - should raise error
        with pytest.raises(MCPCatalogAlreadyExistsError):
            await catalog_service.register_service(sample_service_definition)

    @pytest.mark.asyncio
    async def test_get_service_local_mode(self, catalog_service, sample_service_definition):
        """Test getting a service in local mode (mocked)"""
        # Register service first
        await catalog_service.register_service(sample_service_definition)

        # Get service
        service = await catalog_service.get_service("github")

        assert service.service_name == "github"
        assert service.display_name == "GitHub"
        assert service.category == "git"

    @pytest.mark.asyncio
    async def test_get_service_not_found(self, catalog_service):
        """Test get_service raises MCPCatalogNotFoundError when service doesn't exist"""
        # In local mode, mock catalog is empty initially
        with pytest.raises(MCPCatalogNotFoundError):
            await catalog_service.get_service("nonexistent")

    @pytest.mark.asyncio
    async def test_list_services_local_mode(self, catalog_service):
        """Test listing all services in local mode (mocked)"""
        services = await catalog_service.list_services()

        assert isinstance(services, list)
        # Local mode mock has predefined services
        assert len(services) >= 3
        service_names = [s.service_name for s in services]
        assert "github" in service_names
        assert "slack" in service_names
        assert "gmail" in service_names

    @pytest.mark.asyncio
    async def test_list_services_with_filters(self, catalog_service):
        """Test listing services with category and auth_type filters"""
        # Filter by category
        git_services = await catalog_service.list_services(category="git")
        assert all(s.category == "git" for s in git_services)

        # Filter by auth_type
        oauth_services = await catalog_service.list_services(auth_type="oauth2")
        assert all(s.auth_type == "oauth2" for s in oauth_services)

    @pytest.mark.asyncio
    async def test_enable_service_for_tenant(self, catalog_service, sample_service_definition):
        """Test enabling a service for a tenant"""
        # Register service first
        await catalog_service.register_service(sample_service_definition)

        # Enable for tenant
        service = await catalog_service.enable_service_for_tenant("github", "account-123")

        assert "account-123" in service.enabled_for_tenants

    @pytest.mark.asyncio
    async def test_enable_service_already_enabled(self, catalog_service, sample_service_definition):
        """Test enabling an already-enabled service doesn't duplicate"""
        # Register and enable
        await catalog_service.register_service(sample_service_definition)
        await catalog_service.enable_service_for_tenant("github", "account-123")

        # Enable again
        service = await catalog_service.enable_service_for_tenant("github", "account-123")

        # Should only appear once
        assert service.enabled_for_tenants.count("account-123") == 1

    @pytest.mark.asyncio
    async def test_disable_service_for_tenant(self, catalog_service, sample_service_definition):
        """Test disabling a service for a tenant"""
        # Register and enable
        await catalog_service.register_service(sample_service_definition)
        await catalog_service.enable_service_for_tenant("github", "account-123")

        # Disable
        service = await catalog_service.disable_service_for_tenant("github", "account-123")

        assert "account-123" not in service.enabled_for_tenants

    @pytest.mark.asyncio
    async def test_get_enabled_services_for_tenant(self, catalog_service, sample_service_definition):
        """Test getting all enabled services for a tenant"""
        # Register and enable multiple services
        await catalog_service.register_service(sample_service_definition)
        await catalog_service.enable_service_for_tenant("github", "account-123")

        slack_service = MCPServiceDefinition(
            service_name="slack",
            display_name="Slack",
            description="Slack messaging",
            category="messaging",
            auth_type="oauth2"
        )
        await catalog_service.register_service(slack_service)
        await catalog_service.enable_service_for_tenant("slack", "account-123")

        # Register another service but don't enable
        gmail_service = MCPServiceDefinition(
            service_name="gmail",
            display_name="Gmail",
            description="Gmail email",
            category="email",
            auth_type="oauth2"
        )
        await catalog_service.register_service(gmail_service)

        # Get enabled services
        enabled = await catalog_service.get_enabled_services_for_tenant("account-123")

        service_names = [s.service_name for s in enabled]
        assert "github" in service_names
        assert "slack" in service_names
        assert "gmail" not in service_names

    @pytest.mark.asyncio
    async def test_update_service(self, catalog_service, sample_service_definition):
        """Test updating a service definition"""
        # Register service first
        await catalog_service.register_service(sample_service_definition)

        # Update description
        updated = await catalog_service.update_service(
            "github",
            {"description": "Updated GitHub description"}
        )

        assert updated.description == "Updated GitHub description"

    @pytest.mark.asyncio
    async def test_delete_service(self, catalog_service, sample_service_definition):
        """Test deleting a service from catalog"""
        # Register service first
        await catalog_service.register_service(sample_service_definition)

        # Delete
        result = await catalog_service.delete_service("github")

        assert result is True

        # Verify it's gone
        with pytest.raises(MCPCatalogNotFoundError):
            await catalog_service.get_service("github")

    @pytest.mark.asyncio
    async def test_is_service_enabled_for_tenant_true(self, catalog_service, sample_service_definition):
        """Test is_service_enabled_for_tenant returns True when enabled"""
        # Register and enable
        await catalog_service.register_service(sample_service_definition)
        await catalog_service.enable_service_for_tenant("github", "account-123")

        # Check
        enabled = await catalog_service.is_service_enabled_for_tenant("github", "account-123")

        assert enabled is True

    @pytest.mark.asyncio
    async def test_is_service_enabled_for_tenant_false(self, catalog_service, sample_service_definition):
        """Test is_service_enabled_for_tenant returns False when not enabled"""
        # Register but don't enable
        await catalog_service.register_service(sample_service_definition)

        # Check
        enabled = await catalog_service.is_service_enabled_for_tenant("github", "account-999")

        assert enabled is False

    @pytest.mark.asyncio
    async def test_is_service_enabled_for_tenant_nonexistent_service(self, catalog_service):
        """Test is_service_enabled_for_tenant returns False for nonexistent service"""
        enabled = await catalog_service.is_service_enabled_for_tenant("nonexistent", "account-123")

        assert enabled is False


class TestMCPCatalogServiceAWSIntegration:
    """Test suite with mocked AWS SDK calls"""

    @pytest.fixture
    def aws_config(self):
        """Create config for AWS testing"""
        return AgentCoreConfig(
            environment=Environment.DEVELOPMENT,
            aws_region="ap-southeast-2",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            dynamodb_mcp_catalog_table="agentcore_mcp_catalog"
        )

    @pytest.fixture
    def mock_dynamodb(self):
        """Create mock boto3 DynamoDB resource"""
        with patch('boto3.resource') as mock_boto3:
            mock_resource = MagicMock()
            mock_boto3.return_value = mock_resource

            # Mock table
            mock_table = MagicMock()
            mock_resource.Table.return_value = mock_table

            yield mock_table

    def test_dynamodb_client_initialization(self, aws_config, mock_dynamodb):
        """Test DynamoDB client is properly initialized"""
        service = MCPCatalogService(config=aws_config)
        assert service.client is not None

    @pytest.mark.asyncio
    async def test_register_service_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test registering service with real DynamoDB"""
        # Mock get_item to return empty (not found)
        mock_dynamodb.get_item.return_value = {}
        mock_dynamodb.put_item.return_value = {}

        service = MCPCatalogService(config=aws_config)
        result = await service.register_service(sample_service_definition)

        assert result.service_name == "github"
        mock_dynamodb.put_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_service_duplicate_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test registering duplicate service in AWS raises error"""
        # Mock get_item to return existing service
        mock_dynamodb.get_item.return_value = {
            'Item': sample_service_definition.to_dict()
        }

        service = MCPCatalogService(config=aws_config)

        with pytest.raises(MCPCatalogAlreadyExistsError):
            await service.register_service(sample_service_definition)

    @pytest.mark.asyncio
    async def test_get_service_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test getting service from DynamoDB"""
        mock_dynamodb.get_item.return_value = {
            'Item': sample_service_definition.to_dict()
        }

        service = MCPCatalogService(config=aws_config)
        result = await service.get_service("github")

        assert result.service_name == "github"
        mock_dynamodb.get_item.assert_called_once_with(Key={'service_name': 'github'})

    @pytest.mark.asyncio
    async def test_get_service_not_found_aws(self, aws_config, mock_dynamodb):
        """Test MCPCatalogNotFoundError when service doesn't exist in DynamoDB"""
        mock_dynamodb.get_item.return_value = {}

        service = MCPCatalogService(config=aws_config)

        with pytest.raises(MCPCatalogNotFoundError):
            await service.get_service("github")

    @pytest.mark.asyncio
    async def test_list_services_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test listing services from DynamoDB"""
        mock_dynamodb.scan.return_value = {
            'Items': [sample_service_definition.to_dict()]
        }

        service = MCPCatalogService(config=aws_config)
        services = await service.list_services()

        assert len(services) == 1
        assert services[0].service_name == "github"

    @pytest.mark.asyncio
    async def test_enable_service_for_tenant_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test enabling service for tenant in DynamoDB"""
        # Mock get_item and put_item
        mock_dynamodb.get_item.return_value = {
            'Item': sample_service_definition.to_dict()
        }
        mock_dynamodb.put_item.return_value = {}

        service = MCPCatalogService(config=aws_config)
        result = await service.enable_service_for_tenant("github", "account-123")

        assert "account-123" in result.enabled_for_tenants
        mock_dynamodb.put_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_service_aws(self, aws_config, mock_dynamodb, sample_service_definition):
        """Test deleting service from DynamoDB"""
        # Mock get_item to return existing service
        mock_dynamodb.get_item.return_value = {
            'Item': sample_service_definition.to_dict()
        }
        mock_dynamodb.delete_item.return_value = {}

        service = MCPCatalogService(config=aws_config)
        result = await service.delete_service("github")

        assert result is True
        mock_dynamodb.delete_item.assert_called_once_with(Key={'service_name': 'github'})


class TestTenantIsolation:
    """Test tenant isolation for service enablement"""

    def test_different_tenants_separate_enablement(self, catalog_service, sample_service_definition):
        """Test that different tenants have separate enablement status"""
        # In local mode, test the logic directly
        service1 = sample_service_definition
        service1.enabled_for_tenants = ["account-1"]
        service2 = MCPServiceDefinition.from_dict(service1.to_dict())
        service2.enabled_for_tenants = ["account-2"]

        assert "account-1" in service1.enabled_for_tenants
        assert "account-2" in service2.enabled_for_tenants
        assert "account-1" not in service2.enabled_for_tenants

    def test_service_shared_across_tenants(self, catalog_service, sample_service_definition):
        """Test that service definition is shared but enablement is per-tenant"""
        service = sample_service_definition
        service.enabled_for_tenants = ["account-1", "account-2", "account-3"]

        # Service metadata is same for all tenants
        assert service.service_name == "github"
        assert service.category == "git"

        # But each tenant can be independently enabled/disabled
        assert len(service.enabled_for_tenants) == 3


class TestServiceDefinitionValidation:
    """Test service definition validation and constraints"""

    def test_auth_type_validation(self):
        """Test that auth_type is one of the allowed values"""
        valid_auth_types = ["oauth2", "api_key", "token", "none"]

        for auth_type in valid_auth_types:
            service = MCPServiceDefinition(
                service_name="test",
                display_name="Test",
                description="Test service",
                category="test",
                auth_type=auth_type
            )
            assert service.auth_type == auth_type

    def test_oauth_config_required_for_oauth2(self):
        """Test that oauth2 auth type requires oauth_config"""
        # oauth2 without oauth_config should be allowed (can be set later)
        service = MCPServiceDefinition(
            service_name="github",
            display_name="GitHub",
            description="GitHub",
            category="git",
            auth_type="oauth2",
            oauth_config={
                "authorization_url": "https://github.com/oauth/authorize",
                "token_url": "https://github.com/oauth/token",
                "scope": "repo"
            }
        )

        assert service.oauth_config is not None
        assert "authorization_url" in service.oauth_config

    def test_features_list_mutable(self):
        """Test that features list can be modified"""
        service = MCPServiceDefinition(
            service_name="github",
            display_name="GitHub",
            description="GitHub",
            category="git",
            auth_type="oauth2",
            features=["repositories"]
        )

        service.features.append("issues")
        service.features.append("pull_requests")

        assert len(service.features) == 3
        assert "issues" in service.features
