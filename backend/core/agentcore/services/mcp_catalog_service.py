"""
AWS DynamoDB MCP Catalog Service for AgentCore Gateway

Provides tenant-isolated service catalog for MCP integrations.
Stores service metadata and enablement status in DynamoDB.

Phase 7: Added tier-based access control for subscription-tier restrictions.
"""

import json
import logging
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from ..config import AgentCoreConfig, get_config
from ..errors import with_retry, AgentCoreError, AgentCoreNonRetryableError

logger = logging.getLogger(__name__)


class Tier(str, Enum):
    """
    Subscription tiers for MCP service access control.

    Phase 7: Tier-based filtering controls which MCP services are available
    to tenants based on their subscription level.

    Attributes:
        FREE: Basic tier with limited MCP tools
        PRO: Mid-tier with expanded integrations
        ENTERPRISE: Full access to all MCP services including custom
    """
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

    @classmethod
    def tier_order(cls, tier: str) -> int:
        """
        Get numeric ordering for tier comparison.

        Args:
            tier: Tier string (free, pro, enterprise)

        Returns:
            Integer value for comparison (0=free, 1=pro, 2=enterprise)

        Raises:
            ValueError: If tier is not recognized
        """
        try:
            tier_obj = cls(tier.lower())
            return {cls.FREE: 0, cls.PRO: 1, cls.ENTERPRISE: 2}[tier_obj]
        except ValueError:
            raise ValueError(f"Invalid tier: {tier}. Must be one of: free, pro, enterprise")

    @classmethod
    def can_access_tier(cls, tenant_tier: str, required_tier: str) -> bool:
        """
        Check if tenant tier can access a service requiring specific tier.

        Args:
            tenant_tier: Tenant's subscription tier
            required_tier: Minimum tier required for service

        Returns:
            True if tenant tier >= required tier

        Example:
            >>> Tier.can_access_tier("pro", "free")  # True
            >>> Tier.can_access_tier("pro", "pro")    # True
            >>> Tier.can_access_tier("pro", "enterprise")  # False
            >>> Tier.can_access_tier("free", "pro")  # False
        """
        return cls.tier_order(tenant_tier) >= cls.tier_order(required_tier)


class MCPCatalogNotFoundError(AgentCoreNonRetryableError):
    """Raised when a requested MCP service doesn't exist in the catalog"""
    pass


class MCPCatalogAlreadyExistsError(AgentCoreNonRetryableError):
    """Raised when attempting to create a service that already exists"""
    pass


@dataclass
class MCPServiceDefinition:
    """
    Definition of an MCP service available in the catalog

    Phase 7: Added required_tier field for tier-based access control.

    Attributes:
        service_name: Unique service identifier (github, slack, gmail, etc.)
        display_name: Human-readable service name
        description: Service description
        category: Service category (git, messaging, email, productivity, etc.)
        auth_type: Authentication type (oauth2, api_key, token, none)
        required_tier: Minimum subscription tier required (free, pro, enterprise)
        oauth_config: OAuth configuration (if auth_type is oauth2)
        mcp_server_config: MCP server deployment configuration
        features: List of features provided by this service
        requires_callback: Whether OAuth requires callback URL
        enabled_for_tenants: Set of tenant IDs that have enabled this service
        created_at: Service registration timestamp
        updated_at: Last update timestamp

    Tier Restrictions (Phase 7):
        - free: Basic MCP tools (web_search, wikipedia)
        - pro: Includes Google, GitHub integrations
        - enterprise: All MCP servers including custom deployments
    """
    service_name: str
    display_name: str
    description: str
    category: str
    auth_type: str  # oauth2, api_key, token, none
    required_tier: str = "free"  # Phase 7: Minimum tier required
    oauth_config: Optional[Dict[str, Any]] = None
    mcp_server_config: Optional[Dict[str, Any]] = None
    features: List[str] = field(default_factory=list)
    requires_callback: bool = False
    enabled_for_tenants: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for DynamoDB storage

        Phase 7: Fixed bug where empty lists were not being serialized.
        Empty lists [] are falsy in Python, so we need explicit type check.
        """
        data = asdict(self)
        # Convert lists to JSON strings for DynamoDB
        # Note: Empty lists are falsy in Python (bool([]) == False), so check type explicitly
        if isinstance(data.get('enabled_for_tenants'), list):
            data['enabled_for_tenants'] = json.dumps(data['enabled_for_tenants'])
        if isinstance(data.get('features'), list):
            data['features'] = json.dumps(data['features'])
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MCPServiceDefinition':
        """Create from dictionary for DynamoDB deserialization"""
        data = data.copy()
        # Parse JSON strings
        if isinstance(data.get('enabled_for_tenants'), str):
            data['enabled_for_tenants'] = json.loads(data['enabled_for_tenants'])
        if isinstance(data.get('features'), str):
            data['features'] = json.loads(data['features'])
        return cls(**data)


class MCPCatalogService:
    """
    DynamoDB-backed catalog for MCP services

    Manages available MCP integrations with tenant-scoped enablement.
    Table schema: agentcore_mcp_catalog (partition_key: service_name)

    Example services:
    - github: GitHub repository management and operations
    - slack: Slack messaging and workspace operations
    - gmail: Gmail email operations
    - google_drive: Google Drive file operations
    - notion: Notion workspace and page management
    - jira: Jira issue tracking
    - linear: Linear project management
    """

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize DynamoDB MCP Catalog service

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()

    def _validate_config(self):
        """Validate that required configuration is available"""
        if self.config.is_local():
            logger.warning("MCP Catalog service initialized in local mode (DynamoDB calls will be mocked)")

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for MCP Catalog in non-local environment")

            if not self.config.dynamodb_mcp_catalog_table:
                raise ValueError("DYNAMODB_MCP_CATALOG_TABLE must be configured")

    def _initialize_client(self):
        """Initialize boto3 DynamoDB client"""
        logger.info(
            f"Initializing MCP Catalog service for {self.config.environment} environment "
            f"(table: {self.config.dynamodb_mcp_catalog_table or 'mock'})"
        )

        if self.config.is_local():
            # For local development, create mock client
            self.client = None
            self._mock_catalog: Dict[str, MCPServiceDefinition] = {}
            logger.debug("MCP Catalog service in local mode (no real DynamoDB calls)")
        else:
            self.client = boto3.resource(
                'dynamodb',
                region_name=self.config.aws_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )
            logger.debug(f"DynamoDB client initialized (region: {self.config.aws_region})")

    def _get_table(self):
        """Get DynamoDB table reference"""
        if self.config.is_local():
            return None
        return self.client.Table(self.config.dynamodb_mcp_catalog_table)

    @with_retry(max_attempts=3)
    async def register_service(
        self,
        service_definition: MCPServiceDefinition
    ) -> MCPServiceDefinition:
        """
        Register a new MCP service in the catalog

        Args:
            service_definition: Service definition to register

        Returns:
            The registered service definition

        Raises:
            MCPCatalogAlreadyExistsError: If service already exists
            AgentCoreError: If registration fails after retries
        """
        service_name = service_definition.service_name
        logger.info(f"Registering MCP service: {service_name}")

        try:
            if self.config.is_local():
                # Mock implementation for local development
                if service_name in self._mock_catalog:
                    raise MCPCatalogAlreadyExistsError(
                        f"Service {service_name} already exists in catalog"
                    )
                self._mock_catalog[service_name] = service_definition
                logger.debug(f"[LOCAL] Mock registered service: {service_name}")
                return service_definition

            table = self._get_table()
            service_data = service_definition.to_dict()

            # Check if service already exists
            try:
                table.get_item(Key={'service_name': service_name})['Item']
                raise MCPCatalogAlreadyExistsError(
                    f"Service {service_name} already exists in catalog"
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise

            # Put new service
            table.put_item(Item=service_data)
            logger.info(f"Registered MCP service: {service_name}")
            return service_definition

        except MCPCatalogAlreadyExistsError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to register service: {error_message}")

    @with_retry(max_attempts=3)
    async def get_service(self, service_name: str) -> MCPServiceDefinition:
        """
        Get a service definition from the catalog

        Args:
            service_name: Service identifier

        Returns:
            Service definition

        Raises:
            MCPCatalogNotFoundError: If service doesn't exist
            AgentCoreError: If retrieval fails after retries
        """
        logger.debug(f"Getting service definition: {service_name}")

        try:
            if self.config.is_local():
                # Mock implementation
                if service_name not in self._mock_catalog:
                    raise MCPCatalogNotFoundError(
                        f"Service {service_name} not found in catalog"
                    )
                return self._mock_catalog[service_name]

            table = self._get_table()
            response = table.get_item(Key={'service_name': service_name})

            if 'Item' not in response:
                raise MCPCatalogNotFoundError(
                    f"Service {service_name} not found in catalog"
                )

            return MCPServiceDefinition.from_dict(response['Item'])

        except MCPCatalogNotFoundError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to get service: {error_message}")

    @with_retry(max_attempts=3)
    async def list_services(
        self,
        category: Optional[str] = None,
        auth_type: Optional[str] = None,
        required_tier: Optional[str] = None
    ) -> List[MCPServiceDefinition]:
        """
        List all services in the catalog

        Phase 7: Added tier-based filtering.

        Args:
            category: Optional filter by category
            auth_type: Optional filter by authentication type
            required_tier: Optional filter by minimum tier (free, pro, enterprise)

        Returns:
            List of service definitions

        Raises:
            AgentCoreError: If listing fails after retries
        """
        logger.debug(
            f"Listing services (category: {category}, auth_type: {auth_type}, "
            f"required_tier: {required_tier})"
        )

        try:
            if self.config.is_local():
                # Mock implementation - return predefined services
                # Phase 7: Added tier-based access control
                mock_services = [
                    {
                        'service_name': 'web_search',
                        'display_name': 'Web Search',
                        'description': 'Web search functionality for general queries',
                        'category': 'search',
                        'auth_type': 'none',
                        'required_tier': 'free',  # Available to all tiers
                        'oauth_config': None,
                        'features': ['search', 'query'],
                        'requires_callback': False,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'service_name': 'wikipedia',
                        'display_name': 'Wikipedia',
                        'description': 'Wikipedia encyclopedia access',
                        'category': 'reference',
                        'auth_type': 'none',
                        'required_tier': 'free',  # Available to all tiers
                        'oauth_config': None,
                        'features': ['search', 'article_content'],
                        'requires_callback': False,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'service_name': 'github',
                        'display_name': 'GitHub',
                        'description': 'GitHub repository management and operations',
                        'category': 'git',
                        'auth_type': 'oauth2',
                        'required_tier': 'pro',  # Pro tier and above
                        'oauth_config': {
                            'authorization_url': 'https://github.com/login/oauth/authorize',
                            'token_url': 'https://github.com/login/oauth/access_token',
                            'scope': 'repo,read:user'
                        },
                        'features': ['repositories', 'issues', 'pull_requests'],
                        'requires_callback': True,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'service_name': 'google',
                        'display_name': 'Google',
                        'description': 'Google Workspace integration (Gmail, Drive, Calendar)',
                        'category': 'productivity',
                        'auth_type': 'oauth2',
                        'required_tier': 'pro',  # Pro tier and above
                        'oauth_config': {
                            'authorization_url': 'https://accounts.google.com/o/oauth2/v2/auth',
                            'token_url': 'https://oauth2.googleapis.com/token',
                            'scope': 'https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/drive'
                        },
                        'features': ['gmail', 'drive', 'calendar'],
                        'requires_callback': True,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'service_name': 'slack',
                        'display_name': 'Slack',
                        'description': 'Slack messaging and workspace operations',
                        'category': 'messaging',
                        'auth_type': 'oauth2',
                        'required_tier': 'enterprise',  # Enterprise only
                        'oauth_config': {
                            'authorization_url': 'https://slack.com/oauth/v2/authorize',
                            'token_url': 'https://slack.com/api/oauth.v2.access',
                            'scope': 'chat:write,channels:read,files:write'
                        },
                        'features': ['messages', 'channels', 'files'],
                        'requires_callback': True,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                    {
                        'service_name': 'jira',
                        'display_name': 'Jira',
                        'description': 'Jira issue tracking and project management',
                        'category': 'project_management',
                        'auth_type': 'api_key',
                        'required_tier': 'enterprise',  # Enterprise only
                        'oauth_config': None,
                        'features': ['issues', 'projects', 'workflows'],
                        'requires_callback': False,
                        'enabled_for_tenants': '[]',
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    },
                ]

                services = [MCPServiceDefinition(**s) for s in mock_services]

                # Apply filters
                if category:
                    services = [s for s in services if s.category == category]
                if auth_type:
                    services = [s for s in services if s.auth_type == auth_type]

                # Phase 7: Apply tier filtering
                if required_tier:
                    services = [
                        s for s in services
                        if Tier.can_access_tier(required_tier, s.required_tier)
                    ]

                logger.debug(f"[LOCAL] Mock listing services: {len(services)} results")
                return services

            table = self._get_table()
            response = table.scan()

            services = [
                MCPServiceDefinition.from_dict(item)
                for item in response.get('Items', [])
            ]

            # Apply filters
            if category:
                services = [s for s in services if s.category == category]
            if auth_type:
                services = [s for s in services if s.auth_type == auth_type]

            # Phase 7: Apply tier filtering
            if required_tier:
                services = [
                    s for s in services
                    if Tier.can_access_tier(required_tier, s.required_tier)
                ]

            logger.debug(f"Found {len(services)} services")
            return services

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to list services: {error_message}")

    @with_retry(max_attempts=3)
    async def enable_service_for_tenant(
        self,
        service_name: str,
        account_id: str
    ) -> MCPServiceDefinition:
        """
        Enable a service for a specific tenant

        Args:
            service_name: Service identifier
            account_id: Tenant account ID

        Returns:
            Updated service definition

        Raises:
            MCPCatalogNotFoundError: If service doesn't exist
            AgentCoreError: If update fails after retries
        """
        logger.info(f"Enabling service {service_name} for tenant {account_id}")

        try:
            if self.config.is_local():
                # Mock implementation
                if service_name not in self._mock_catalog:
                    raise MCPCatalogNotFoundError(
                        f"Service {service_name} not found in catalog"
                    )
                service = self._mock_catalog[service_name]
                if account_id not in service.enabled_for_tenants:
                    service.enabled_for_tenants.append(account_id)
                    service.updated_at = datetime.now(timezone.utc).isoformat()
                logger.debug(f"[LOCAL] Mock enabled service for tenant")
                return service

            table = self._get_table()

            # Get current service
            response = table.get_item(Key={'service_name': service_name})
            if 'Item' not in response:
                raise MCPCatalogNotFoundError(
                    f"Service {service_name} not found in catalog"
                )

            item = response['Item']
            enabled_tenants = json.loads(item.get('enabled_for_tenants', '[]'))

            # Add tenant if not already enabled
            if account_id not in enabled_tenants:
                enabled_tenants.append(account_id)
                item['enabled_for_tenants'] = json.dumps(enabled_tenants)
                item['updated_at'] = datetime.now(timezone.utc).isoformat()

                # Update table
                table.put_item(Item=item)

            return MCPServiceDefinition.from_dict(item)

        except MCPCatalogNotFoundError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to enable service: {error_message}")

    @with_retry(max_attempts=3)
    async def disable_service_for_tenant(
        self,
        service_name: str,
        account_id: str
    ) -> MCPServiceDefinition:
        """
        Disable a service for a specific tenant

        Args:
            service_name: Service identifier
            account_id: Tenant account ID

        Returns:
            Updated service definition

        Raises:
            MCPCatalogNotFoundError: If service doesn't exist
            AgentCoreError: If update fails after retries
        """
        logger.info(f"Disabling service {service_name} for tenant {account_id}")

        try:
            if self.config.is_local():
                # Mock implementation
                if service_name not in self._mock_catalog:
                    raise MCPCatalogNotFoundError(
                        f"Service {service_name} not found in catalog"
                    )
                service = self._mock_catalog[service_name]
                if account_id in service.enabled_for_tenants:
                    service.enabled_for_tenants.remove(account_id)
                    service.updated_at = datetime.now(timezone.utc).isoformat()
                logger.debug(f"[LOCAL] Mock disabled service for tenant")
                return service

            table = self._get_table()

            # Get current service
            response = table.get_item(Key={'service_name': service_name})
            if 'Item' not in response:
                raise MCPCatalogNotFoundError(
                    f"Service {service_name} not found in catalog"
                )

            item = response['Item']
            enabled_tenants = json.loads(item.get('enabled_for_tenants', '[]'))

            # Remove tenant if present
            if account_id in enabled_tenants:
                enabled_tenants.remove(account_id)
                item['enabled_for_tenants'] = json.dumps(enabled_tenants)
                item['updated_at'] = datetime.now(timezone.utc).isoformat()

                # Update table
                table.put_item(Item=item)

            return MCPServiceDefinition.from_dict(item)

        except MCPCatalogNotFoundError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to disable service: {error_message}")

    @with_retry(max_attempts=3)
    async def get_enabled_services_for_tenant(
        self,
        account_id: str
    ) -> List[MCPServiceDefinition]:
        """
        Get all services enabled for a specific tenant

        Args:
            account_id: Tenant account ID

        Returns:
            List of enabled service definitions

        Raises:
            AgentCoreError: If retrieval fails after retries
        """
        logger.debug(f"Getting enabled services for tenant {account_id}")

        try:
            if self.config.is_local():
                # Mock implementation
                services = list(self._mock_catalog.values())
                enabled = [s for s in services if account_id in s.enabled_for_tenants]
                logger.debug(f"[LOCAL] Mock enabled services for tenant: {len(enabled)}")
                return enabled

            table = self._get_table()
            response = table.scan()

            services = []
            for item in response.get('Items', []):
                enabled_tenants = json.loads(item.get('enabled_for_tenants', '[]'))
                if account_id in enabled_tenants:
                    services.append(MCPServiceDefinition.from_dict(item))

            logger.debug(f"Found {len(services)} enabled services for tenant")
            return services

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to get enabled services: {error_message}")

    @with_retry(max_attempts=3)
    async def update_service(
        self,
        service_name: str,
        updates: Dict[str, Any]
    ) -> MCPServiceDefinition:
        """
        Update a service definition

        Args:
            service_name: Service identifier
            updates: Fields to update

        Returns:
            Updated service definition

        Raises:
            MCPCatalogNotFoundError: If service doesn't exist
            AgentCoreError: If update fails after retries
        """
        logger.info(f"Updating service: {service_name}")

        try:
            if self.config.is_local():
                # Mock implementation
                if service_name not in self._mock_catalog:
                    raise MCPCatalogNotFoundError(
                        f"Service {service_name} not found in catalog"
                    )
                service = self._mock_catalog[service_name]
                for key, value in updates.items():
                    if hasattr(service, key):
                        setattr(service, key, value)
                service.updated_at = datetime.now(timezone.utc).isoformat()
                logger.debug(f"[LOCAL] Mock updated service")
                return service

            table = self._get_table()

            # Get current service
            response = table.get_item(Key={'service_name': service_name})
            if 'Item' not in response:
                raise MCPCatalogNotFoundError(
                    f"Service {service_name} not found in catalog"
                )

            item = response['Item']

            # Update fields
            for key, value in updates.items():
                if key in ['enabled_for_tenants', 'features']:
                    # Serialize list fields
                    item[key] = json.dumps(value)
                else:
                    item[key] = value

            item['updated_at'] = datetime.now(timezone.utc).isoformat()

            # Update table
            table.put_item(Item=item)

            return MCPServiceDefinition.from_dict(item)

        except MCPCatalogNotFoundError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to update service: {error_message}")

    @with_retry(max_attempts=3)
    async def delete_service(self, service_name: str) -> bool:
        """
        Delete a service from the catalog

        Args:
            service_name: Service identifier

        Returns:
            True if deleted successfully

        Raises:
            MCPCatalogNotFoundError: If service doesn't exist
            AgentCoreError: If deletion fails after retries
        """
        logger.info(f"Deleting service: {service_name}")

        try:
            if self.config.is_local():
                # Mock implementation
                if service_name not in self._mock_catalog:
                    raise MCPCatalogNotFoundError(
                        f"Service {service_name} not found in catalog"
                    )
                del self._mock_catalog[service_name]
                logger.debug(f"[LOCAL] Mock deleted service")
                return True

            table = self._get_table()

            # Check if exists first
            response = table.get_item(Key={'service_name': service_name})
            if 'Item' not in response:
                raise MCPCatalogNotFoundError(
                    f"Service {service_name} not found in catalog"
                )

            # Delete
            table.delete_item(Key={'service_name': service_name})
            logger.info(f"Deleted service: {service_name}")
            return True

        except MCPCatalogNotFoundError:
            raise
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to delete service: {error_message}")

    async def is_service_enabled_for_tenant(
        self,
        service_name: str,
        account_id: str
    ) -> bool:
        """
        Check if a service is enabled for a tenant

        Args:
            service_name: Service identifier
            account_id: Tenant account ID

        Returns:
            True if enabled, False otherwise
        """
        try:
            service = await self.get_service(service_name)
            return account_id in service.enabled_for_tenants
        except MCPCatalogNotFoundError:
            return False
        except Exception as e:
            logger.warning(f"Error checking service enablement: {e}")
            return False

    @with_retry(max_attempts=3)
    async def list_available_mcp_servers(
        self,
        account_id: str,
        tenant_tier: str = "free"
    ) -> List[MCPServiceDefinition]:
        """
        List all MCP servers available to a tenant based on their subscription tier.

        Phase 7: Combines tier-based filtering with tenant enablement status.

        This method returns services that:
        1. Match the tenant's subscription tier (tenant_tier >= service.required_tier)
        2. Are either enabled for the tenant OR available by default (public services)

        Tier restrictions:
        - free: Basic MCP tools (web_search, wikipedia)
        - pro: Includes GitHub, Google integrations
        - enterprise: All MCP servers including custom deployments

        Args:
            account_id: Tenant account ID
            tenant_tier: Tenant's subscription tier (free, pro, enterprise)

        Returns:
            List of available service definitions for the tenant

        Raises:
            AgentCoreError: If listing fails after retries
        """
        logger.debug(
            f"Listing available MCP servers for tenant {account_id} "
            f"(tier: {tenant_tier})"
        )

        try:
            # Get all services in the catalog
            all_services = await self.list_services()

            # Filter by tier eligibility
            tier_eligible = [
                service for service in all_services
                if Tier.can_access_tier(tenant_tier, service.required_tier)
            ]

            # Get services explicitly enabled for this tenant
            enabled_services = await self.get_enabled_services_for_tenant(account_id)
            enabled_service_names = {s.service_name for s in enabled_services}

            # A service is "available" if:
            # 1. It's tier-eligible (already filtered above), AND
            # 2. It's either explicitly enabled for the tenant OR it's a public service
            #    (we consider free-tier services as "public" by default)
            available_services = []
            for service in tier_eligible:
                # Service is available if tenant enabled it OR it's a free service (public by default)
                if service.service_name in enabled_service_names:
                    # Tenant explicitly enabled this service
                    available_services.append(service)
                elif service.required_tier == "free":
                    # Free services are available to all tenants by default
                    available_services.append(service)
                # Pro/enterprise services require explicit enablement unless tenant has that tier

            logger.debug(
                f"Found {len(available_services)} available services for tenant {account_id} "
                f"({len(enabled_services)} explicitly enabled, "
                f"{len(available_services) - len(enabled_service_names)} public/default)"
            )
            return available_services

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"DynamoDB error: {error_code} - {error_message}")
            raise AgentCoreError(f"Failed to list available servers: {error_message}")
