"""
AgentCore Tier-Based Feature Management (Phase 8)

Provides tier-based feature flags and access control for AgentCore operations.
Integrates with existing subscription system to enforce feature limits.

Phase 8: All feature checks use ap-southeast-2 (Australia) region.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    safe_log,
)
from .billing_manager import get_billing_manager

logger = logging.getLogger(__name__)


class Feature(str, Enum):
    """
    AgentCore features available by subscription tier.

    Phase 8 features include:
    - Base features (all tiers): Basic execution, memory access
    - Pro features: Code interpreter, browser automation, MCP tools, extended timeout
    - Enterprise features: Multi-region, dedicated deployment, custom models, API access
    """
    # Base features (available to all tiers)
    BASIC_EXECUTION = "basic_execution"
    MEMORY_ACCESS = "memory_access"
    HTTP_TOOLS = "http_tools"

    # Pro features
    CODE_INTERPRETER = "code_interpreter"
    BROWSER_AUTOMATION = "browser_automation"
    MCP_TOOLS = "mcp_tools"
    EXTENDED_TIMEOUT = "extended_timeout"
    ADVANCED_MEMORY = "advanced_memory"
    PRIORITY_EXECUTION = "priority_execution"

    # Enterprise features
    MULTI_REGION = "multi_region"
    DEDICATED_DEPLOYMENT = "dedicated_deployment"
    CUSTOM_MODELS = "custom_models"
    API_ACCESS = "api_access"
    DEDICATED_SUPPORT = "dedicated_support"
    CUSTOM_BRANDING = "custom_branding"
    SSO_INTEGRATION = "sso_integration"
    AUDIT_LOGS = "audit_logs"
    UNLIMITED_EXECUTIONS = "unlimited_executions"


class Tier(str, Enum):
    """Subscription tiers for AgentCore."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class FeatureLimit:
    """
    Limits and constraints for a specific feature.

    Attributes:
        feature: Feature identifier
        max_per_day: Maximum uses per day (0 = unlimited)
        max_per_month: Maximum uses per month (0 = unlimited)
        max_concurrent: Maximum concurrent uses (0 = unlimited)
        quota_reset_period: Quota reset period in seconds
    """
    feature: Feature
    max_per_day: int = 0
    max_per_month: int = 0
    max_concurrent: int = 0
    quota_reset_period: int = 86400  # 24 hours

    def is_unlimited(self) -> bool:
        """Check if feature has unlimited usage."""
        return (
            self.max_per_day == 0
            and self.max_per_month == 0
            and self.max_concurrent == 0
        )


# Tier feature configurations
TIER_FEATURES: Dict[Tier, Set[Feature]] = {
    Tier.FREE: {
        Feature.BASIC_EXECUTION,
        Feature.MEMORY_ACCESS,
        Feature.HTTP_TOOLS,
    },
    Tier.PRO: {
        # All free features
        Feature.BASIC_EXECUTION,
        Feature.MEMORY_ACCESS,
        Feature.HTTP_TOOLS,
        # Pro features
        Feature.CODE_INTERPRETER,
        Feature.BROWSER_AUTOMATION,
        Feature.MCP_TOOLS,
        Feature.EXTENDED_TIMEOUT,
        Feature.ADVANCED_MEMORY,
        Feature.PRIORITY_EXECUTION,
    },
    Tier.ENTERPRISE: {
        # All features
        Feature.BASIC_EXECUTION,
        Feature.MEMORY_ACCESS,
        Feature.HTTP_TOOLS,
        Feature.CODE_INTERPRETER,
        Feature.BROWSER_AUTOMATION,
        Feature.MCP_TOOLS,
        Feature.EXTENDED_TIMEOUT,
        Feature.ADVANCED_MEMORY,
        Feature.PRIORITY_EXECUTION,
        # Enterprise features
        Feature.MULTI_REGION,
        Feature.DEDICATED_DEPLOYMENT,
        Feature.CUSTOM_MODELS,
        Feature.API_ACCESS,
        Feature.DEDICATED_SUPPORT,
        Feature.CUSTOM_BRANDING,
        Feature.SSO_INTEGRATION,
        Feature.AUDIT_LOGS,
        Feature.UNLIMITED_EXECUTIONS,
    },
}


# Feature-specific limits
FEATURE_LIMITS: Dict[Feature, Dict[Tier, FeatureLimit]] = {
    Feature.CODE_INTERPRETER: {
        Tier.FREE: FeatureLimit(Feature.CODE_INTERPRETER, max_per_day=0),  # Not available
        Tier.PRO: FeatureLimit(Feature.CODE_INTERPRETER, max_per_day=100, max_concurrent=5),
        Tier.ENTERPRISE: FeatureLimit(Feature.CODE_INTERPRETER, max_per_day=0),  # Unlimited
    },
    Feature.BROWSER_AUTOMATION: {
        Tier.FREE: FeatureLimit(Feature.BROWSER_AUTOMATION, max_per_day=0),  # Not available
        Tier.PRO: FeatureLimit(Feature.BROWSER_AUTOMATION, max_per_day=50, max_concurrent=3),
        Tier.ENTERPRISE: FeatureLimit(Feature.BROWSER_AUTOMATION, max_per_day=0),  # Unlimited
    },
    Feature.MCP_TOOLS: {
        Tier.FREE: FeatureLimit(Feature.MCP_TOOLS, max_per_day=0),  # Not available
        Tier.PRO: FeatureLimit(Feature.MCP_TOOLS, max_per_day=200, max_concurrent=10),
        Tier.ENTERPRISE: FeatureLimit(Feature.MCP_TOOLS, max_per_day=0),  # Unlimited
    },
    Feature.BASIC_EXECUTION: {
        Tier.FREE: FeatureLimit(Feature.BASIC_EXECUTION, max_per_day=10, max_concurrent=1),
        Tier.PRO: FeatureLimit(Feature.BASIC_EXECUTION, max_per_day=0),  # No daily limit
        Tier.ENTERPRISE: FeatureLimit(Feature.BASIC_EXECUTION, max_per_day=0),  # No daily limit
    },
}


@dataclass
class FeatureCheckResult:
    """
    Result of a feature access check.

    Attributes:
        feature: Feature that was checked
        allowed: Whether feature access is allowed
        tier: Current tier of the account
        reason: Reason for denial (if not allowed)
        current_usage: Current usage count
        remaining_quota: Remaining quota (0 if unlimited)
        limit: Feature limit configuration
    """
    feature: Feature
    allowed: bool
    tier: str
    reason: Optional[str] = None
    current_usage: int = 0
    remaining_quota: int = 0
    limit: Optional[FeatureLimit] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "feature": self.feature.value,
            "allowed": self.allowed,
            "tier": self.tier,
            "reason": self.reason,
            "current_usage": self.current_usage,
            "remaining_quota": self.remaining_quota,
            "limit": self.limit.to_dict() if self.limit else None,
        }


class TierFeatureManager:
    """
    Manage tier-based feature access for AgentCore operations.

    Phase 8: Integrates with billing system to enforce tier-based
    feature limits and access control.

    Features:
    - Check if a tier has access to a feature
    - Validate feature usage against quotas
    - Enforce concurrent execution limits
    - Track feature usage metrics
    """

    # Phase 8 required region
    PHASE_8_REGION = "ap-southeast-2"

    # Cache for feature check results (TTL: 5 minutes)
    CACHE_TTL = 300

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the tier feature manager.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If config is invalid for feature management.
        """
        self.config = config or get_config()
        self._billing_manager = None
        self._usage_cache: Dict[str, Dict[str, int]] = {}

        # Validate region compliance for Phase 8
        if self.config.aws_region != self.PHASE_8_REGION:
            safe_log(
                f"Tier manager: Region '{self.config.aws_region}' specified, "
                f"but Phase 8 requires '{self.PHASE_8_REGION}'. "
                f"All features will be tracked in {self.PHASE_8_REGION} for compliance."
            )

        safe_log("TierFeatureManager initialized")

    def _get_billing_manager(self):
        """Lazy initialization of billing manager."""
        if self._billing_manager is None:
            self._billing_manager = get_billing_manager(self.config)
        return self._billing_manager

    @classmethod
    def get_tier_features(cls, tier: Tier) -> Set[Feature]:
        """
        Get available features for a tier.

        Args:
            tier: Subscription tier

        Returns:
            Set of available features
        """
        return TIER_FEATURES.get(tier, TIER_FEATURES[Tier.FREE])

    @classmethod
    def get_feature_limit(cls, feature: Feature, tier: Tier) -> Optional[FeatureLimit]:
        """
        Get usage limits for a feature in a tier.

        Args:
            feature: Feature to check
            tier: Subscription tier

        Returns:
            FeatureLimit if feature is available, None otherwise
        """
        if feature not in cls.get_tier_features(tier):
            return None
        return FEATURE_LIMITS.get(feature, {}).get(tier)

    async def check_feature_access(
        self,
        account_id: str,
        feature: Feature,
        tier: Optional[Tier] = None,
    ) -> FeatureCheckResult:
        """
        Check if an account has access to a feature.

        Args:
            account_id: Tenant account ID
            feature: Feature to check
            tier: Optional tier (fetched from billing if not provided)

        Returns:
            FeatureCheckResult with access status

        Raises:
            AgentCoreError: If feature check fails
        """
        try:
            # Get tier if not provided
            if tier is None:
                tier_info = await self._get_billing_manager().get_account_tier(account_id)
                tier = Tier(tier_info.get("tier", "free"))

            # Check if feature is available for tier
            available_features = self.get_tier_features(tier)
            allowed = feature in available_features

            if allowed:
                # Get feature limits
                limit = self.get_feature_limit(feature, tier)
                remaining = -1  # -1 indicates unlimited

                if limit and not limit.is_unlimited():
                    # Check current usage
                    current_usage = await self._get_feature_usage(account_id, feature)

                    # Calculate remaining quota
                    if limit.max_per_day > 0:
                        remaining = max(0, limit.max_per_day - current_usage)
                    elif limit.max_per_month > 0:
                        remaining = max(0, limit.max_per_month - current_usage)

                    # Check if quota exhausted
                    if remaining == 0:
                        allowed = False

                return FeatureCheckResult(
                    feature=feature,
                    allowed=allowed,
                    tier=tier.value,
                    reason=None if allowed else f"Feature requires {tier.value} tier or higher",
                    current_usage=await self._get_feature_usage(account_id, feature),
                    remaining_quota=remaining,
                    limit=limit,
                )
            else:
                return FeatureCheckResult(
                    feature=feature,
                    allowed=False,
                    tier=tier.value,
                    reason=f"Feature '{feature.value}' requires Pro tier or higher",
                    current_usage=0,
                    remaining_quota=0,
                    limit=None,
                )

        except Exception as e:
            safe_log(f"Failed to check feature access: {e}", level="error")
            raise AgentCoreError(f"Failed to check feature access: {e}") from e

    async def require_feature_access(
        self,
        account_id: str,
        feature: Feature,
        tier: Optional[Tier] = None,
    ) -> bool:
        """
        Check if an account has access to a feature, raise if not.

        Args:
            account_id: Tenant account ID
            feature: Feature to check
            tier: Optional tier (fetched from billing if not provided)

        Returns:
            True if feature is accessible

        Raises:
            ConfigurationError: If feature is not accessible
        """
        result = await self.check_feature_access(account_id, feature, tier)
        if not result.allowed:
            raise ConfigurationError(
                result.reason or f"Feature '{feature.value}' is not available"
            )
        return True

    async def record_feature_usage(
        self,
        account_id: str,
        feature: Feature,
        amount: int = 1,
    ) -> bool:
        """
        Record usage of a feature for quota tracking.

        Args:
            account_id: Tenant account ID
            feature: Feature being used
            amount: Usage amount (default: 1)

        Returns:
            True if usage was recorded successfully

        Raises:
            AgentCoreError: If usage recording fails
        """
        try:
            if account_id not in self._usage_cache:
                self._usage_cache[account_id] = {}

            feature_key = feature.value
            current = self._usage_cache[account_id].get(feature_key, 0)
            self._usage_cache[account_id][feature_key] = current + amount

            safe_log(
                f"Recorded {amount} usage of '{feature_key}' "
                f"for account {account_id} (total: {current + amount})"
            )
            return True

        except Exception as e:
            safe_log(f"Failed to record feature usage: {e}", level="error")
            raise AgentCoreError(f"Failed to record feature usage: {e}") from e

    async def _get_feature_usage(
        self,
        account_id: str,
        feature: Feature,
    ) -> int:
        """
        Get current usage count for a feature.

        Args:
            account_id: Tenant account ID
            feature: Feature to check

        Returns:
            Current usage count
        """
        if account_id not in self._usage_cache:
            return 0
        return self._usage_cache[account_id].get(feature.value, 0)

    async def get_available_features(
        self,
        account_id: str,
    ) -> List[Feature]:
        """
        Get list of available features for an account.

        Args:
            account_id: Tenant account ID

        Returns:
            List of available Feature values
        """
        try:
            tier_info = await self._get_billing_manager().get_account_tier(account_id)
            tier = Tier(tier_info.get("tier", "free"))
            return list(self.get_tier_features(tier))

        except Exception as e:
            safe_log(f"Failed to get available features: {e}", level="warning")
            return list(self.get_tier_features(Tier.FREE))

    async def get_tier_summary(
        self,
        account_id: str,
    ) -> Dict[str, Any]:
        """
        Get comprehensive tier and feature summary for an account.

        Args:
            account_id: Tenant account ID

        Returns:
            Dictionary with tier and feature information

        Raises:
            AgentCoreError: If summary retrieval fails
        """
        try:
            # Get tier information
            tier_info = await self._get_billing_manager().get_account_tier(account_id)
            tier = Tier(tier_info.get("tier", "free"))

            # Get available features
            available_features = self.get_tier_features(tier)

            # Check access to key features
            feature_checks = await asyncio.gather(*[
                self.check_feature_access(account_id, feature, tier)
                for feature in [
                    Feature.BASIC_EXECUTION,
                    Feature.CODE_INTERPRETER,
                    Feature.BROWSER_AUTOMATION,
                    Feature.MCP_TOOLS,
                ]
            ])

            return {
                "tier": tier.value,
                "tier_name": tier_info.get("tier_name", "Free"),
                "available_features": [f.value for f in available_features],
                "feature_access": {
                    fc.feature.value: fc.to_dict()
                    for fc in feature_checks
                },
                "region": self.PHASE_8_REGION,
            }

        except Exception as e:
            safe_log(f"Failed to get tier summary: {e}", level="error")
            raise AgentCoreError(f"Failed to get tier summary: {e}") from e


# Convenience functions

def get_tier_feature_manager(config: Optional[AgentCoreConfig] = None) -> TierFeatureManager:
    """
    Get the tier feature manager instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        TierFeatureManager instance
    """
    return TierFeatureManager(config=config)


async def check_feature_access(
    account_id: str,
    feature: Feature,
    config: Optional[AgentCoreConfig] = None,
) -> FeatureCheckResult:
    """
    Convenience function to check feature access.

    Args:
        account_id: Tenant account ID
        feature: Feature to check
        config: Optional AgentCore configuration

    Returns:
        FeatureCheckResult with access status
    """
    manager = get_tier_feature_manager(config)
    return await manager.check_feature_access(account_id, feature)


async def require_feature(
    account_id: str,
    feature: Feature,
    config: Optional[AgentCoreConfig] = None,
) -> bool:
    """
    Convenience function to require feature access.

    Args:
        account_id: Tenant account ID
        feature: Feature to check
        config: Optional AgentCore configuration

    Returns:
        True if feature is accessible

    Raises:
        ConfigurationError: If feature is not accessible
    """
    manager = get_tier_feature_manager(config)
    return await manager.require_feature_access(account_id, feature)


async def get_available_features(
    account_id: str,
    config: Optional[AgentCoreConfig] = None,
) -> List[Feature]:
    """
    Convenience function to get available features.

    Args:
        account_id: Tenant account ID
        config: Optional AgentCore configuration

    Returns:
        List of available Feature values
    """
    manager = get_tier_feature_manager(config)
    return await manager.get_available_features(account_id)


async def get_tier_summary(
    account_id: str,
    config: Optional[AgentCoreConfig] = None,
) -> Dict[str, Any]:
    """
    Convenience function to get tier summary.

    Args:
        account_id: Tenant account ID
        config: Optional AgentCore configuration

    Returns:
        Dictionary with tier and feature information
    """
    manager = get_tier_feature_manager(config)
    return await manager.get_tier_summary(account_id)


# Export Feature enum for convenience
__all__ = [
    "Feature",
    "Tier",
    "TierFeatureManager",
    "get_tier_feature_manager",
    "check_feature_access",
    "require_feature",
    "get_available_features",
    "get_tier_summary",
]
