"""
MCP Configuration Service

Provides runtime configuration management for MCP servers integrated via
AgentCore Gateway. Handles:

- Per-tenant configuration overrides
- Feature flag integration
- Configuration validation
- Configuration persistence and retrieval
- Dynamic configuration updates
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import asdict, replace
from datetime import datetime, timedelta

from ..config import AgentCoreConfig, get_config
from ..models import GatewayConfig
from ..errors import ValidationError, GatewayError
from .mcp_catalog_service import MCPCatalogService

logger = logging.getLogger(__name__)


class MCPConfiguration:
    """
    Configuration for a specific MCP server deployment.

    Attributes:
        service_name: Name of the MCP service
        enabled: Whether the service is enabled
        timeout_seconds: Request timeout
        rate_limit_per_minute: Rate limit per tenant
        enable_caching: Enable result caching
        cache_ttl_seconds: Cache TTL
        max_retries: Maximum retry attempts
        custom_config: Service-specific configuration
    """

    def __init__(
        self,
        service_name: str,
        enabled: bool = True,
        timeout_seconds: int = 60,
        rate_limit_per_minute: int = 100,
        enable_caching: bool = True,
        cache_ttl_seconds: int = 300,
        max_retries: int = 3,
        custom_config: Optional[Dict[str, Any]] = None
    ):
        self.service_name = service_name
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_minute = rate_limit_per_minute
        self.enable_caching = enable_caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_retries = max_retries
        self.custom_config = custom_config or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "service_name": self.service_name,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "enable_caching": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "max_retries": self.max_retries,
            "custom_config": self.custom_config
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfiguration":
        """Create from dictionary for JSON deserialization"""
        return cls(
            service_name=data.get("service_name", ""),
            enabled=data.get("enabled", True),
            timeout_seconds=data.get("timeout_seconds", 60),
            rate_limit_per_minute=data.get("rate_limit_per_minute", 100),
            enable_caching=data.get("enable_caching", True),
            cache_ttl_seconds=data.get("cache_ttl_seconds", 300),
            max_retries=data.get("max_retries", 3),
            custom_config=data.get("custom_config", {})
        )

    def merge_with(self, other: "MCPConfiguration") -> "MCPConfiguration":
        """Merge with another configuration, other takes precedence"""
        return MCPConfiguration(
            service_name=self.service_name,
            enabled=other.enabled if other.enabled is not None else self.enabled,
            timeout_seconds=other.timeout_seconds if other.timeout_seconds else self.timeout_seconds,
            rate_limit_per_minute=other.rate_limit_per_minute if other.rate_limit_per_minute else self.rate_limit_per_minute,
            enable_caching=other.enable_caching if other.enable_caching is not None else self.enable_caching,
            cache_ttl_seconds=other.cache_ttl_seconds if other.cache_ttl_seconds else self.cache_ttl_seconds,
            max_retries=other.max_retries if other.max_retries else self.max_retries,
            custom_config={**self.custom_config, **other.custom_config}
        )


class MCPConfigurationService:
    """
    Service for managing MCP server runtime configurations.

    Provides:
    - Global defaults for all MCP servers
    - Per-tenant overrides
    - Per-service overrides
    - Configuration validation
    - Dynamic configuration updates
    """

    # Global default configuration for all MCP services
    GLOBAL_DEFAULTS = {
        "timeout_seconds": 60,
        "rate_limit_per_minute": 100,
        "enable_caching": True,
        "cache_ttl_seconds": 300,
        "max_retries": 3
    }

    # Service-specific defaults
    SERVICE_DEFAULTS = {
        "github": {
            "timeout_seconds": 30,
            "rate_limit_per_minute": 5000,  # GitHub has higher rate limits
            "enable_caching": True,
            "cache_ttl_seconds": 600  # 10 minutes
        },
        "slack": {
            "timeout_seconds": 30,
            "rate_limit_per_minute": 200,
            "enable_caching": True,
            "cache_ttl_seconds": 300
        },
        "gmail": {
            "timeout_seconds": 45,
            "rate_limit_per_minute": 250,
            "enable_caching": True,
            "cache_ttl_seconds": 300
        },
        "notion": {
            "timeout_seconds": 30,
            "rate_limit_per_minute": 100,
            "enable_caching": True,
            "cache_ttl_seconds": 600
        }
    }

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        catalog_service: Optional[MCPCatalogService] = None
    ):
        """
        Initialize MCP Configuration Service.

        Args:
            config: AgentCore configuration
            catalog_service: MCP Catalog service for service validation
        """
        self.config = config or get_config()
        self.catalog_service = catalog_service or MCPCatalogService(config=self.config)

        # In-memory configuration cache
        # In production, this would be backed by DynamoDB or Redis
        self._tenant_configs: Dict[str, Dict[str, MCPConfiguration]] = {}
        self._global_overrides: Dict[str, Any] = {}

    async def get_configuration(
        self,
        service_name: str,
        account_id: str
    ) -> MCPConfiguration:
        """
        Get effective configuration for a service and tenant.

        Resolution order:
        1. Tenant-specific override for this service
        2. Service-specific default
        3. Global default

        Args:
            service_name: Name of the MCP service
            account_id: Account ID for tenant isolation

        Returns:
            Effective MCP configuration
        """
        # Start with global defaults
        config = MCPConfiguration(
            service_name=service_name,
            **self.GLOBAL_DEFAULTS
        )

        # Apply service-specific defaults
        if service_name in self.SERVICE_DEFAULTS:
            service_defaults = self.SERVICE_DEFAULTS[service_name]
            for key, value in service_defaults.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Apply tenant-specific override if exists
        tenant_config = self._tenant_configs.get(account_id, {}).get(service_name)
        if tenant_config:
            config = config.merge_with(tenant_config)

        # Apply global overrides if any
        if self._global_overrides:
            for key, value in self._global_overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        return config

    async def set_tenant_configuration(
        self,
        account_id: str,
        service_name: str,
        configuration: MCPConfiguration
    ) -> bool:
        """
        Set tenant-specific configuration for a service.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service
            configuration: Configuration to set

        Returns:
            True if successful

        Raises:
            ValidationError: If configuration is invalid
        """
        # Validate configuration
        await self._validate_configuration(configuration)

        # Store tenant configuration
        if account_id not in self._tenant_configs:
            self._tenant_configs[account_id] = {}

        self._tenant_configs[account_id][service_name] = configuration

        logger.info(
            f"Set configuration for {service_name} in account {account_id}: "
            f"enabled={configuration.enabled}, timeout={configuration.timeout_seconds}s"
        )

        return True

    async def reset_tenant_configuration(
        self,
        account_id: str,
        service_name: str
    ) -> bool:
        """
        Reset tenant-specific configuration for a service.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            True if configuration was reset
        """
        if account_id in self._tenant_configs and service_name in self._tenant_configs[account_id]:
            del self._tenant_configs[account_id][service_name]
            logger.info(f"Reset configuration for {service_name} in account {account_id}")
            return True

        return False

    async def get_all_configurations(
        self,
        account_id: str
    ) -> Dict[str, MCPConfiguration]:
        """
        Get all configurations for a tenant.

        Args:
            account_id: Account ID for tenant isolation

        Returns:
            Dictionary of service_name → configuration
        """
        configurations = {}

        # Get all enabled services from catalog
        enabled_services = await self.catalog_service.list_enabled_services(account_id)

        for service in enabled_services:
            config = await self.get_configuration(service.service_name, account_id)
            configurations[service.service_name] = config

        return configurations

    async def set_global_override(
        self,
        key: str,
        value: Any
    ) -> bool:
        """
        Set a global configuration override.

        Global overrides apply to all services and tenants.

        Args:
            key: Configuration key
            value: Configuration value

        Returns:
            True if successful

        Raises:
            ValidationError: If key or value is invalid
        """
        valid_keys = ["timeout_seconds", "rate_limit_per_minute", "enable_caching", "cache_ttl_seconds", "max_retries"]

        if key not in valid_keys:
            raise ValidationError(
                f"Invalid configuration key: {key}. Valid keys: {valid_keys}"
            )

        # Validate value
        if key == "timeout_seconds" and (not isinstance(value, int) or value < 1 or value > 300):
            raise ValidationError("timeout_seconds must be between 1 and 300")

        if key == "rate_limit_per_minute" and (not isinstance(value, int) or value < 1):
            raise ValidationError("rate_limit_per_minute must be positive")

        if key == "cache_ttl_seconds" and (not isinstance(value, int) or value < 0):
            raise ValidationError("cache_ttl_seconds must be non-negative")

        if key == "max_retries" and (not isinstance(value, int) or value < 0 or value > 10):
            raise ValidationError("max_retries must be between 0 and 10")

        self._global_overrides[key] = value
        logger.info(f"Set global override: {key}={value}")

        return True

    def clear_global_overrides(self) -> bool:
        """Clear all global configuration overrides"""
        self._global_overrides.clear()
        logger.info("Cleared all global overrides")
        return True

    async def enable_service(
        self,
        account_id: str,
        service_name: str
    ) -> bool:
        """
        Enable an MCP service for a tenant.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            True if successful
        """
        # Enable service in catalog
        await self.catalog_service.enable_service_for_tenant(account_id, service_name)

        # Set enabled configuration
        config = await self.get_configuration(service_name, account_id)
        config.enabled = True
        await self.set_tenant_configuration(account_id, service_name, config)

        logger.info(f"Enabled service {service_name} for account {account_id}")
        return True

    async def disable_service(
        self,
        account_id: str,
        service_name: str
    ) -> bool:
        """
        Disable an MCP service for a tenant.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            True if successful
        """
        # Set disabled configuration
        config = await self.get_configuration(service_name, account_id)
        config.enabled = False
        await self.set_tenant_configuration(account_id, service_name, config)

        logger.info(f"Disabled service {service_name} for account {account_id}")
        return True

    async def is_service_enabled(
        self,
        account_id: str,
        service_name: str
    ) -> bool:
        """
        Check if a service is enabled for a tenant.

        Args:
            account_id: Account ID for tenant isolation
            service_name: Name of the MCP service

        Returns:
            True if service is enabled
        """
        # Check catalog
        is_enabled_in_catalog = await self.catalog_service.is_service_enabled(account_id, service_name)

        # Check configuration
        config = await self.get_configuration(service_name, account_id)

        return is_enabled_in_catalog and config.enabled

    async def _validate_configuration(self, configuration: MCPConfiguration) -> None:
        """
        Validate MCP configuration.

        Args:
            configuration: Configuration to validate

        Raises:
            ValidationError: If configuration is invalid
        """
        # Validate timeout
        if configuration.timeout_seconds < 1 or configuration.timeout_seconds > 300:
            raise ValidationError(
                f"timeout_seconds must be between 1 and 300, got {configuration.timeout_seconds}"
            )

        # Validate rate limit
        if configuration.rate_limit_per_minute < 1:
            raise ValidationError(
                f"rate_limit_per_minute must be positive, got {configuration.rate_limit_per_minute}"
            )

        # Validate cache TTL
        if configuration.cache_ttl_seconds < 0:
            raise ValidationError(
                f"cache_ttl_seconds must be non-negative, got {configuration.cache_ttl_seconds}"
            )

        # Validate max retries
        if configuration.max_retries < 0 or configuration.max_retries > 10:
            raise ValidationError(
                f"max_retries must be between 0 and 10, got {configuration.max_retries}"
            )

        # Validate service name
        if not configuration.service_name or not isinstance(configuration.service_name, str):
            raise ValidationError("service_name must be a non-empty string")

    async def export_configuration(
        self,
        account_id: str,
        format: str = "json"
    ) -> str:
        """
        Export all configurations for a tenant.

        Args:
            account_id: Account ID for tenant isolation
            format: Export format ('json' or 'yaml')

        Returns:
            Exported configuration as string
        """
        configs = await self.get_all_configurations(account_id)

        if format == "json":
            return json.dumps(
                {name: config.to_dict() for name, config in configs.items()},
                indent=2
            )
        elif format == "yaml":
            # Simple YAML-like export
            lines = [f"# MCP Configuration for account {account_id}"]
            for service_name, config in configs.items():
                lines.append(f"\n[{service_name}]")
                for key, value in config.to_dict().items():
                    if key != "service_name":
                        lines.append(f"{key} = {value}")
            return "\n".join(lines)
        else:
            raise ValidationError(f"Unsupported export format: {format}")

    async def import_configuration(
        self,
        account_id: str,
        configuration_data: str,
        format: str = "json"
    ) -> int:
        """
        Import configurations for a tenant.

        Args:
            account_id: Account ID for tenant isolation
            configuration_data: Configuration data to import
            format: Import format ('json' or 'yaml')

        Returns:
            Number of configurations imported
        """
        imported = 0

        if format == "json":
            data = json.loads(configuration_data)

            for service_name, config_data in data.items():
                config = MCPConfiguration.from_dict(config_data)
                await self.set_tenant_configuration(account_id, service_name, config)
                imported += 1

        else:
            raise ValidationError(f"Unsupported import format: {format}")

        logger.info(f"Imported {imported} configurations for account {account_id}")
        return imported

    async def get_configuration_summary(
        self,
        account_id: str
    ) -> Dict[str, Any]:
        """
        Get a summary of MCP configurations for a tenant.

        Args:
            account_id: Account ID for tenant isolation

        Returns:
            Configuration summary
        """
        configs = await self.get_all_configurations(account_id)

        enabled_count = sum(1 for c in configs.values() if c.enabled)
        disabled_count = len(configs) - enabled_count

        # Calculate average values
        total_timeout = sum(c.timeout_seconds for c in configs.values())
        total_rate_limit = sum(c.rate_limit_per_minute for c in configs.values())

        return {
            "account_id": account_id,
            "total_services": len(configs),
            "enabled_services": enabled_count,
            "disabled_services": disabled_count,
            "average_timeout_seconds": total_timeout / len(configs) if configs else 0,
            "total_rate_limit_per_minute": total_rate_limit,
            "services": {
                name: {
                    "enabled": config.enabled,
                    "timeout_seconds": config.timeout_seconds,
                    "rate_limit_per_minute": config.rate_limit_per_minute
                }
                for name, config in configs.items()
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    async def cleanup(self):
        """
        Clean up resources.

        Clears cached configurations to free memory.
        """
        self._tenant_configs.clear()
        self._global_overrides.clear()
        logger.info("Cleaned up MCP Configuration Service")
