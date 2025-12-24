"""
AgentCore Multi-Region Deployment Manager (Phase 8)

Manages AgentCore deployments across multiple regions with data residency compliance.
Phase 8 Constraint: All deployments MUST use ap-southeast-2 (Australia).

This module provides:
- Multi-region orchestration (Australia-only for Phase 8)
- Region health monitoring
- Deployment targeting logic
- Data residency enforcement
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    safe_log,
)

logger = logging.getLogger(__name__)


class DeploymentRegion(str, Enum):
    """
    Supported deployment regions for AgentCore.

    Phase 8 Constraint: Only ap-southeast-2 (Australia) is enabled
    to meet data residency requirements.

    Future regions must comply with data residency laws.
    """
    AP_SOUTHEAST_2 = "ap-southeast-2"  # Australia (Primary - Phase 8 only)
    # Future regions (disabled in Phase 8):
    # US_EAST_1 = "us-east-1"
    # EU_WEST_1 = "eu-west-1"
    # AP_NORTHEAST_1 = "ap-northeast-1"


class RegionHealthStatus(str, Enum):
    """Health status of a deployment region"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class RegionDeploymentConfig:
    """
    Configuration for a specific region deployment.

    Attributes:
        region: Deployment region enum
        enabled: Whether this region is enabled for deployments
        gateway_url: AgentCore Gateway URL for this region
        s3_bucket: S3 bucket for this region's file storage
        weight: Load balancing weight (higher = more traffic)
        health_status: Current health status of the region
        last_health_check: Timestamp of last health check
    """
    region: DeploymentRegion
    enabled: bool = True
    gateway_url: Optional[str] = None
    s3_bucket: Optional[str] = None
    weight: int = 100
    health_status: RegionHealthStatus = RegionHealthStatus.UNKNOWN
    last_health_check: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "region": self.region.value,
            "enabled": self.enabled,
            "gateway_url": self.gateway_url,
            "s3_bucket": self.s3_bucket,
            "weight": self.weight,
            "health_status": self.health_status.value,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegionDeploymentConfig':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('region'), str):
            data['region'] = DeploymentRegion(data['region'])
        if isinstance(data.get('health_status'), str):
            data['health_status'] = RegionHealthStatus(data['health_status'])
        if isinstance(data.get('last_health_check'), str):
            data['last_health_check'] = datetime.fromisoformat(data['last_health_check'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RegionHealthCheckResult:
    """
    Result of a region health check.

    Attributes:
        region: Region that was checked
        status: Health status
        latency_ms: Round-trip latency in milliseconds
        error: Error message if health check failed
        checked_at: When the check was performed
    """
    region: DeploymentRegion
    status: RegionHealthStatus
    latency_ms: float
    error: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "region": self.region.value,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "checked_at": self.checked_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegionHealthCheckResult':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()
        if isinstance(data.get('region'), str):
            data['region'] = DeploymentRegion(data['region'])
        if isinstance(data.get('status'), str):
            data['status'] = RegionHealthStatus(data['status'])
        if isinstance(data.get('checked_at'), str):
            data['checked_at'] = datetime.fromisoformat(data['checked_at'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MultiRegionManager:
    """
    Manages AgentCore deployments across multiple regions.

    Phase 8 Constraint: Only ap-southeast-2 (Australia) is enabled.
    Multi-region capabilities are prepared for future phases.

    This manager:
    1. Enforces ap-southeast-2 for all deployments (Phase 8)
    2. Tracks health of enabled regions
    3. Provides region targeting logic for future use
    4. Ensures data residency compliance
    """

    PRIMARY_REGION = DeploymentRegion.AP_SOUTHEAST_2
    PHASE_8_REQUIRED_REGION = DeploymentRegion.AP_SOUTHEAST_2

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the multi-region manager.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If config is invalid for multi-region deployment.
        """
        self.config = config or get_config()
        self._region_configs: Dict[DeploymentRegion, RegionDeploymentConfig] = {}
        self._health_check_results: Dict[DeploymentRegion, RegionHealthCheckResult] = {}
        self._initialize_regions()
        self._validate_region_compliance()

        safe_log("MultiRegionManager initialized")

    def _initialize_regions(self):
        """
        Initialize available regions (Phase 8: Australia only).

        Phase 8 enforcement:
        - Only ap-southeast-2 is enabled
        - Other regions are blocked for data residency compliance
        """
        # Configure primary region (ap-southeast-2)
        self._region_configs[self.PRIMARY_REGION] = RegionDeploymentConfig(
            region=self.PRIMARY_REGION,
            enabled=True,
            gateway_url=self.config.agent_core_gateway_url,
            s3_bucket=self.config.s3_bucket_name,
            weight=100,
            health_status=RegionHealthStatus.UNKNOWN,
        )

        # Enforce Australia-only deployment for Phase 8
        if self.config.aws_region != self.PHASE_8_REQUIRED_REGION.value:
            safe_log(
                f"Region '{self.config.aws_region}' specified, "
                f"but Phase 8 requires '{self.PHASE_8_REQUIRED_REGION.value}'. "
                f"All deployments will use {self.PHASE_8_REQUIRED_REGION.value} for compliance."
            )

    def _validate_region_compliance(self):
        """
        Validate that configuration complies with Phase 8 region requirements.

        Raises:
            ConfigurationError: If region configuration violates Phase 8 requirements.
        """
        if self.config.aws_region != self.PHASE_8_REQUIRED_REGION.value:
            raise ConfigurationError(
                f"Phase 8 requires AgentCore to use {self.PHASE_8_REQUIRED_REGION.value} region. "
                f"Current config: {self.config.aws_region}. "
                f"Set AGENTCORE_AWS_REGION={self.PHASE_8_REQUIRED_REGION.value} in environment."
            )

        # Validate S3 bucket region if configured
        if self.config.s3_bucket_region:
            if self.config.s3_bucket_region != self.PHASE_8_REQUIRED_REGION.value:
                raise ConfigurationError(
                    f"Phase 8 requires S3 bucket in {self.PHASE_8_REQUIRED_REGION.value} region. "
                    f"Current S3 region: {self.config.s3_bucket_region}. "
                    f"Set AGENTCORE_S3_BUCKET_REGION={self.PHASE_8_REQUIRED_REGION.value} in environment."
                )

    def get_enabled_regions(self) -> List[DeploymentRegion]:
        """
        Get list of enabled regions.

        Phase 8: Returns only [ap-southeast-2]

        Returns:
            List of enabled deployment regions
        """
        return [
            r for r, cfg in self._region_configs.items()
            if cfg.enabled and r == DeploymentRegion.AP_SOUTHEAST_2
        ]

    def get_region_config(self, region: DeploymentRegion) -> Optional[RegionDeploymentConfig]:
        """
        Get configuration for a specific region.

        Args:
            region: Region to get configuration for

        Returns:
            RegionDeploymentConfig if region exists, None otherwise
        """
        return self._region_configs.get(region)

    def get_primary_region(self) -> DeploymentRegion:
        """
        Get the primary deployment region.

        Phase 8: Always returns ap-southeast-2

        Returns:
            Primary deployment region
        """
        return self.PRIMARY_REGION

    async def check_region_health(
        self,
        region: Optional[DeploymentRegion] = None,
    ) -> RegionHealthCheckResult:
        """
        Check health of a deployment region.

        Phase 8: Only checks ap-southeast-2 health.

        Args:
            region: Region to check. If None, checks primary region.

        Returns:
            RegionHealthCheckResult with health status
        """
        region = region or self.PRIMARY_REGION

        if region not in self._region_configs:
            return RegionHealthCheckResult(
                region=region,
                status=RegionHealthStatus.UNKNOWN,
                latency_ms=-1,
                error=f"Region {region.value} not configured",
            )

        import time
        start_time = time.time()

        try:
            # Phase 8: Basic health check - verify gateway URL is accessible
            config = self._region_configs[region]

            if not config.gateway_url:
                raise ConfigurationError(f"No gateway URL configured for {region.value}")

            # TODO: Add actual health check logic (ping gateway, check S3 access)
            # For Phase 8, we'll do a basic validation
            if not config.enabled:
                status = RegionHealthStatus.UNHEALTHY
                error_msg = f"Region {region.value} is disabled"
            else:
                status = RegionHealthStatus.HEALTHY
                error_msg = None

            latency_ms = (time.time() - start_time) * 1000

            result = RegionHealthCheckResult(
                region=region,
                status=status,
                latency_ms=latency_ms,
                error=error_msg,
            )

            # Update config
            config.health_status = status
            config.last_health_check = result.checked_at

            # Store health check result
            self._health_check_results[region] = result

            safe_log(f"Health check for {region.value}: {status.value} ({latency_ms:.2f}ms)")
            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            result = RegionHealthCheckResult(
                region=region,
                status=RegionHealthStatus.UNHEALTHY,
                latency_ms=latency_ms,
                error=str(e),
            )

            if region in self._region_configs:
                self._region_configs[region].health_status = RegionHealthStatus.UNHEALTHY
                self._region_configs[region].last_health_check = result.checked_at

            self._health_check_results[region] = result
            safe_log(f"Health check failed for {region.value}: {e}")
            return result

    async def check_all_regions_health(self) -> Dict[DeploymentRegion, RegionHealthCheckResult]:
        """
        Check health of all configured regions.

        Phase 8: Only checks ap-southeast-2

        Returns:
            Dictionary mapping regions to their health check results
        """
        results = {}

        for region in self._region_configs.keys():
            results[region] = await self.check_region_health(region)

        return results

    def get_healthy_regions(self) -> List[DeploymentRegion]:
        """
        Get list of healthy regions.

        Phase 8: Returns ap-southeast-2 if healthy, empty list otherwise

        Returns:
            List of healthy deployment regions
        """
        return [
            r for r, cfg in self._region_configs.items()
            if cfg.enabled and cfg.health_status == RegionHealthStatus.HEALTHY
        ]

    def select_region_for_deployment(
        self,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> DeploymentRegion:
        """
        Select the best region for a new deployment.

        Phase 8: Always returns ap-southeast-2

        Future phases will use:
        - User preferences
        - Latency optimization
        - Load balancing weights
        - Health status

        Args:
            preferences: Optional deployment preferences (for future use)

        Returns:
            Selected deployment region

        Raises:
            ConfigurationError: If no healthy regions available
        """
        # Phase 8: Always use ap-southeast-2
        if self.PRIMARY_REGION not in self.get_healthy_regions():
            # If primary is unhealthy but enabled, still use it (with warning)
            if self.PRIMARY_REGION in self.get_enabled_regions():
                safe_log(
                    f"Primary region {self.PRIMARY_REGION.value} is not healthy, "
                    f"but using it for deployment (Phase 8 single-region mode)"
                )
                return self.PRIMARY_REGION

        return self.PRIMARY_REGION

    def is_region_enabled(self, region: DeploymentRegion) -> bool:
        """
        Check if a region is enabled for deployments.

        Args:
            region: Region to check

        Returns:
            True if region is enabled, False otherwise
        """
        config = self._region_configs.get(region)
        return config.enabled if config else False

    def enable_region(self, region: DeploymentRegion) -> bool:
        """
        Enable a region for deployments.

        Phase 8: Only ap-southeast-2 can be enabled. Other regions are blocked.

        Args:
            region: Region to enable

        Returns:
            True if region was enabled, False if blocked

        Raises:
            ConfigurationError: If trying to enable non-Australia region in Phase 8
        """
        if region != self.PHASE_8_REQUIRED_REGION:
            raise ConfigurationError(
                f"Phase 8: Cannot enable {region.value}. "
                f"Only {self.PHASE_8_REQUIRED_REGION.value} is enabled for data residency compliance."
            )

        if region in self._region_configs:
            self._region_configs[region].enabled = True
            safe_log(f"Region {region.value} enabled")
            return True

        return False

    def disable_region(self, region: DeploymentRegion) -> bool:
        """
        Disable a region for deployments.

        Phase 8: Cannot disable ap-southeast-2 (primary region).

        Args:
            region: Region to disable

        Returns:
            True if region was disabled, False if blocked

        Raises:
            ConfigurationError: If trying to disable ap-southeast-2 in Phase 8
        """
        if region == self.PHASE_8_REQUIRED_REGION:
            raise ConfigurationError(
                f"Phase 8: Cannot disable {region.value}. "
                f"Primary region must remain enabled for data residency compliance."
            )

        if region in self._region_configs:
            self._region_configs[region].enabled = False
            safe_log(f"Region {region.value} disabled")
            return True

        return False

    def get_region_summary(self) -> Dict[str, Any]:
        """
        Get summary of all regions and their status.

        Returns:
            Dictionary with region summary
        """
        return {
            "primary_region": self.PRIMARY_REGION.value,
            "phase_8_required_region": self.PHASE_8_REQUIRED_REGION.value,
            "enabled_regions": [r.value for r in self.get_enabled_regions()],
            "healthy_regions": [r.value for r in self.get_healthy_regions()],
            "regions": {
                region.value: config.to_dict()
                for region, config in self._region_configs.items()
            },
            "health_checks": {
                region.value: result.to_dict()
                for region, result in self._health_check_results.items()
            },
        }


# Convenience functions

def get_multi_region_manager(config: Optional[AgentCoreConfig] = None) -> MultiRegionManager:
    """
    Get the multi-region manager instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        MultiRegionManager instance
    """
    return MultiRegionManager(config=config)


async def check_agentcore_region_health(
    region: Optional[str] = None,
    config: Optional[AgentCoreConfig] = None,
) -> RegionHealthCheckResult:
    """
    Convenience function to check AgentCore region health.

    Args:
        region: Region to check (default: ap-southeast-2)
        config: Optional AgentCore configuration

    Returns:
        RegionHealthCheckResult with health status
    """
    manager = get_multi_region_manager(config)

    target_region = (
        DeploymentRegion(region) if region
        else manager.PRIMARY_REGION
    )

    return await manager.check_region_health(target_region)
