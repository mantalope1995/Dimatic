"""
AgentCore Services Module

Provides AWS service integrations for AgentCore Gateway integration:
- SecretsManagerAdapter: AWS Secrets Manager for tenant-isolated credential storage
- MCPCatalogService: DynamoDB-backed MCP server catalog
- OAuthFlowService: AWS Cognito OAuth 3-legged flow management
- LambdaProxy: MCP → Gateway protocol translation layer
- MCPConfigurationService: Runtime configuration management for MCP servers
- seed_mcp_catalog: Initial catalog seeding with 15 common services
"""

from .secrets_manager_adapter import SecretsManagerAdapter, SecretNotFoundError, SecretAlreadyExistsError
from .mcp_catalog_service import MCPCatalogService, MCPCatalogNotFoundError, MCPCatalogAlreadyExistsError, MCPServiceDefinition, Tier
from .oauth_flow_service import (
    OAuthFlowService,
    OAuthTokenExchangeError,
    OAuthAuthorizationError,
    OAuthState,
    OAuthTokens
)
from .lambda_proxy import LambdaProxy, MCPProtocolTranslator, AuthenticationHandler
from .mcp_config_service import MCPConfigurationService, MCPConfiguration
from . import seed_mcp_catalog

__all__ = [
    "SecretsManagerAdapter",
    "SecretNotFoundError",
    "SecretAlreadyExistsError",
    "MCPCatalogService",
    "MCPCatalogNotFoundError",
    "MCPCatalogAlreadyExistsError",
    "MCPServiceDefinition",
    "Tier",  # Phase 7: Subscription tier enum for MCP catalog filtering
    "OAuthFlowService",
    "OAuthTokenExchangeError",
    "OAuthAuthorizationError",
    "OAuthState",
    "OAuthTokens",
    "LambdaProxy",
    "MCPProtocolTranslator",
    "AuthenticationHandler",
    "MCPConfigurationService",
    "MCPConfiguration",
    "seed_mcp_catalog",
]
