"""
AgentCore Deployment Module

Provides multi-region deployment management with data residency compliance.
Phase 8: All deployments use ap-southeast-2 (Australia) region.

Exports:
    - DeploymentRegion: Supported deployment regions enum
    - RegionHealthStatus: Health status of deployment regions
    - RegionDeploymentConfig: Configuration for region deployment
    - RegionHealthCheckResult: Result of region health check
    - MultiRegionManager: Manages multi-region deployments
"""

from .multi_region_manager import (
    DeploymentRegion,
    RegionHealthStatus,
    RegionDeploymentConfig,
    RegionHealthCheckResult,
    MultiRegionManager,
    get_multi_region_manager,
    check_agentcore_region_health,
)

__all__ = [
    "DeploymentRegion",
    "RegionHealthStatus",
    "RegionDeploymentConfig",
    "RegionHealthCheckResult",
    "MultiRegionManager",
    "get_multi_region_manager",
    "check_agentcore_region_health",
]
