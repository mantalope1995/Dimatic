"""
AgentCore Billing Manager (Phase 8)

Provides unified billing interface for AgentCore operations.
Integrates with existing billing system (CreditManager, SubscriptionService).

Phase 8: All billing operations use ap-southeast-2 (Australia) region.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    safe_log,
)
from .usage_tracker import UsageMetrics, CreditCost

logger = logging.getLogger(__name__)


@dataclass
class BillingSummary:
    """
    Summary of billing information for an account.

    Attributes:
        account_id: Tenant account ID
        current_balance: Current credit balance
        tier: Current subscription tier
        tier_name: Human-readable tier name
        total_executions: Total AgentCore executions this period
        total_cost_usd: Total cost in USD this period
        total_credits_used: Total credits consumed this period
        credits_remaining: Credits remaining in current period
        period_start: Current billing period start
        period_end: Current billing period end
        region: AWS region (ap-southeast-2 for Phase 8)
    """
    account_id: str
    current_balance: int
    tier: str
    tier_name: str
    total_executions: int = 0
    total_cost_usd: float = 0.0
    total_credits_used: int = 0
    credits_remaining: Optional[int] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    region: str = "ap-southeast-2"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": self.account_id,
            "current_balance": self.current_balance,
            "tier": self.tier,
            "tier_name": self.tier_name,
            "total_executions": self.total_executions,
            "total_cost_usd": self.total_cost_usd,
            "total_credits_used": self.total_credits_used,
            "credits_remaining": self.credits_remaining,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "region": self.region,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BillingSummary':
        """Create from dictionary for JSON deserialization."""
        data = data.copy()
        if isinstance(data.get('period_start'), str):
            data['period_start'] = datetime.fromisoformat(data['period_start'])
        if isinstance(data.get('period_end'), str):
            data['period_end'] = datetime.fromisoformat(data['period_end'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TierLimits:
    """
    Tier-based resource limits for AgentCore.

    Attributes:
        tier: Subscription tier (free, pro, enterprise)
        max_concurrent_executions: Maximum concurrent agent executions
        max_timeout_seconds: Maximum execution timeout
        max_memory_mb: Maximum memory allocation
        max_tokens_per_execution: Maximum tokens per execution
        rate_limit_per_minute: API rate limit per minute
        features: List of enabled features
    """
    tier: str
    max_concurrent_executions: int
    max_timeout_seconds: int
    max_memory_mb: int
    max_tokens_per_execution: int
    rate_limit_per_minute: int
    features: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tier": self.tier,
            "max_concurrent_executions": self.max_concurrent_executions,
            "max_timeout_seconds": self.max_timeout_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_tokens_per_execution": self.max_tokens_per_execution,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "features": self.features,
        }


# Tier limit configurations
TIER_LIMITS: Dict[str, TierLimits] = {
    "free": TierLimits(
        tier="free",
        max_concurrent_executions=1,
        max_timeout_seconds=300,  # 5 minutes
        max_memory_mb=2048,
        max_tokens_per_execution=100000,
        rate_limit_per_minute=10,
        features=["basic_execution", "memory_access"],
    ),
    "pro": TierLimits(
        tier="pro",
        max_concurrent_executions=5,
        max_timeout_seconds=1800,  # 30 minutes
        max_memory_mb=4096,
        max_tokens_per_execution=500000,
        rate_limit_per_minute=60,
        features=[
            "basic_execution",
            "memory_access",
            "code_interpreter",
            "browser_automation",
            "mcp_tools",
            "extended_timeout",
        ],
    ),
    "enterprise": TierLimits(
        tier="enterprise",
        max_concurrent_executions=50,
        max_timeout_seconds=7200,  # 2 hours
        max_memory_mb=16384,
        max_tokens_per_execution=1000000,
        rate_limit_per_minute=1000,
        features=[
            "basic_execution",
            "memory_access",
            "code_interpreter",
            "browser_automation",
            "mcp_tools",
            "extended_timeout",
            "multi_region",
            "dedicated_deployment",
            "custom_models",
            "api_access",
        ],
    ),
}


class AgentCoreBillingManager:
    """
    Unified billing manager for AgentCore operations.

    Provides integration with existing billing system:
    - CreditManager: Credit consumption and balance management
    - SubscriptionService: Tier and subscription management
    - Usage tracking and cost calculation
    - Tier-based feature access control

    Phase 8: All operations tracked in ap-southeast-2 (Australia).
    """

    # Phase 8 required region
    PHASE_8_REGION = "ap-southeast-2"

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the billing manager.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If config is invalid for billing operations.
        """
        self.config = config or get_config()
        self._credit_manager = None
        self._subscription_service = None

        # Validate region compliance for Phase 8
        if self.config.aws_region != self.PHASE_8_REGION:
            safe_log(
                f"Billing manager: Region '{self.config.aws_region}' specified, "
                f"but Phase 8 requires '{self.PHASE_8_REGION}'. "
                f"All billing will use {self.PHASE_8_REGION} for compliance."
            )

        safe_log("AgentCoreBillingManager initialized")

    def _get_credit_manager(self):
        """Lazy initialization of CreditManager."""
        if self._credit_manager is None:
            from core.billing.credits.manager import CreditManager
            self._credit_manager = CreditManager()
        return self._credit_manager

    def _get_subscription_service(self):
        """Lazy initialization of SubscriptionService."""
        if self._subscription_service is None:
            from core.billing.subscriptions.service import SubscriptionService
            self._subscription_service = SubscriptionService()
        return self._subscription_service

    async def check_account_balance(
        self,
        account_id: str,
    ) -> int:
        """
        Check current credit balance for an account.

        Args:
            account_id: Tenant account ID

        Returns:
            Current credit balance

        Raises:
            AgentCoreError: If balance check fails
        """
        try:
            manager = self._get_credit_manager()
            # Get credit account balance
            balance = await manager.get_credit_balance(account_id)
            return balance

        except Exception as e:
            safe_log(f"Failed to check balance for {account_id}: {e}", level="error")
            raise AgentCoreError(f"Failed to check balance: {e}") from e

    async def deduct_execution_credits(
        self,
        account_id: str,
        execution_id: str,
        agent_id: str,
        metrics: UsageMetrics,
    ) -> CreditCost:
        """
        Deduct credits for an AgentCore execution.

        Args:
            account_id: Tenant account ID
            execution_id: Execution identifier
            agent_id: Agent being executed
            metrics: Usage metrics for the execution

        Returns:
            CreditCost with breakdown of charges

        Raises:
            AgentCoreError: If credit deduction fails
            ConfigurationError: If insufficient credits
        """
        try:
            manager = self._get_credit_manager()

            # Calculate credits from usage
            from .usage_tracker import UsageTracker
            tracker = UsageTracker(config=self.config)
            credit_cost = tracker._calculate_credits_from_usage(metrics)

            # Deduct credits using existing billing system
            result = await manager.deduct_credits(
                account_id=account_id,
                amount=Decimal(str(credit_cost.final_credits)),
                description=f"AgentCore execution: {agent_id}",
                type="agentcore_usage",
                message_id=execution_id,
                metadata={
                    "agent_id": agent_id,
                    "execution_id": execution_id,
                    "duration_seconds": metrics.execution_duration_seconds,
                    "total_tokens": metrics.total_tokens,
                    "tier": metrics.tier,
                    "region": self.PHASE_8_REGION,
                },
            )

            safe_log(
                f"Deducted {credit_cost.final_credits} credits for {execution_id[:8]}... "
                f"(new balance: {result.get('balance', 'unknown')})"
            )

            return credit_cost

        except Exception as e:
            safe_log(f"Failed to deduct credits: {e}", level="error")
            raise AgentCoreError(f"Failed to deduct credits: {e}") from e

    async def get_account_tier(
        self,
        account_id: str,
        skip_cache: bool = False,
    ) -> Dict[str, Any]:
        """
        Get subscription tier for an account.

        Args:
            account_id: Tenant account ID
            skip_cache: Skip cache and fetch fresh data

        Returns:
            Dictionary with tier information (tier, tier_name, features, etc.)

        Raises:
            AgentCoreError: If tier lookup fails
        """
        try:
            service = self._get_subscription_service()
            tier_info = await service.get_user_subscription_tier(
                account_id=account_id,
                skip_cache=skip_cache,
            )
            return tier_info

        except Exception as e:
            safe_log(f"Failed to get tier for {account_id}: {e}", level="error")
            # Return default free tier on error
            return {
                "tier": "free",
                "tier_name": "Free",
                "features": TIER_LIMITS["free"].features,
            }

    async def check_feature_access(
        self,
        account_id: str,
        feature: str,
    ) -> bool:
        """
        Check if an account has access to a feature.

        Args:
            account_id: Tenant account ID
            feature: Feature name to check

        Returns:
            True if feature is accessible, False otherwise
        """
        try:
            tier_info = await self.get_account_tier(account_id)
            tier = tier_info.get("tier", "free")

            limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
            return feature in limits.features

        except Exception as e:
            safe_log(f"Failed to check feature access: {e}", level="warning")
            return False

    async def require_feature_access(
        self,
        account_id: str,
        feature: str,
    ) -> bool:
        """
        Check if an account has access to a feature, raise if not.

        Args:
            account_id: Tenant account ID
            feature: Feature name to check

        Returns:
            True if feature is accessible

        Raises:
            ConfigurationError: If feature is not accessible
        """
        has_access = await self.check_feature_access(account_id, feature)
        if not has_access:
            tier_info = await self.get_account_tier(account_id)
            raise ConfigurationError(
                f"Feature '{feature}' requires Pro tier or higher. "
                f"Current tier: {tier_info.get('tier_name', 'Unknown')}"
            )
        return True

    async def get_tier_limits(
        self,
        account_id: str,
    ) -> TierLimits:
        """
        Get tier-based resource limits for an account.

        Args:
            account_id: Tenant account ID

        Returns:
            TierLimits with resource constraints

        Raises:
            AgentCoreError: If limits lookup fails
        """
        try:
            tier_info = await self.get_account_tier(account_id)
            tier = tier_info.get("tier", "free")
            return TIER_LIMITS.get(tier, TIER_LIMITS["free"])

        except Exception as e:
            safe_log(f"Failed to get tier limits: {e}", level="warning")
            return TIER_LIMITS["free"]

    async def validate_execution_request(
        self,
        account_id: str,
        timeout_seconds: int,
        estimated_tokens: int = 0,
    ) -> Dict[str, Any]:
        """
        Validate if an execution request is within tier limits.

        Args:
            account_id: Tenant account ID
            timeout_seconds: Requested execution timeout
            estimated_tokens: Estimated token usage

        Returns:
            Dictionary with validation result and limits

        Raises:
            ConfigurationError: If request exceeds tier limits
        """
        limits = await self.get_tier_limits(account_id)

        validation_result = {
            "allowed": True,
            "limits": limits.to_dict(),
            "reason": None,
        }

        # Check timeout limit
        if timeout_seconds > limits.max_timeout_seconds:
            validation_result["allowed"] = False
            validation_result["reason"] = (
                f"Timeout {timeout_seconds}s exceeds tier limit "
                f"of {limits.max_timeout_seconds}s"
            )

        # Check token limit
        if estimated_tokens > limits.max_tokens_per_execution:
            validation_result["allowed"] = False
            validation_result["reason"] = (
                f"Estimated tokens {estimated_tokens} exceeds tier limit "
                f"of {limits.max_tokens_per_execution}"
            )

        return validation_result

    async def get_billing_summary(
        self,
        account_id: str,
    ) -> BillingSummary:
        """
        Get comprehensive billing summary for an account.

        Args:
            account_id: Tenant account ID

        Returns:
            BillingSummary with account billing information

        Raises:
            AgentCoreError: If summary retrieval fails
        """
        try:
            # Get current balance
            balance = await self.check_account_balance(account_id)

            # Get tier information
            tier_info = await self.get_account_tier(account_id)

            # Get subscription info for period dates
            service = self._get_subscription_service()
            subscription = await service.get_subscription(account_id)

            period_start = subscription.get("current_period_start")
            period_end = subscription.get("current_period_end")

            summary = BillingSummary(
                account_id=account_id,
                current_balance=balance,
                tier=tier_info.get("tier", "free"),
                tier_name=tier_info.get("tier_name", "Free"),
                period_start=datetime.fromisoformat(period_start) if period_start else None,
                period_end=datetime.fromisoformat(period_end) if period_end else None,
                region=self.PHASE_8_REGION,
            )

            return summary

        except Exception as e:
            safe_log(f"Failed to get billing summary: {e}", level="error")
            raise AgentCoreError(f"Failed to get billing summary: {e}") from e

    async def estimate_execution_cost(
        self,
        account_id: str,
        estimated_duration_seconds: float = 0,
        estimated_tokens: int = 0,
        estimated_api_calls: int = 0,
    ) -> Dict[str, Any]:
        """
        Estimate cost for an AgentCore execution.

        Args:
            account_id: Tenant account ID
            estimated_duration_seconds: Estimated execution duration
            estimated_tokens: Estimated token usage
            estimated_api_calls: Estimated API call count

        Returns:
            Dictionary with cost breakdown and credits required
        """
        try:
            # Get tier for discount calculation
            tier_info = await self.get_account_tier(account_id)
            tier = tier_info.get("tier", "free")
            discount = UsageTracker.TIER_DISCOUNTS.get(tier, 1.0)

            # Calculate base costs
            base_credits = UsageTracker.BASE_CREDIT_COST
            time_credits = int(
                Decimal(str(estimated_duration_seconds)) * UsageTracker.CREDIT_PER_SECOND
            )
            token_credits = int(
                (Decimal(str(estimated_tokens)) / Decimal("1000")) * UsageTracker.CREDIT_PER_1000_TOKENS
            )
            api_call_credits = int(
                Decimal(str(estimated_api_calls)) * UsageTracker.CREDIT_PER_TOOL_USAGE
            )

            total_credits = base_credits + time_credits + token_credits + api_call_credits
            final_credits = max(1, int(total_credits * discount))

            return {
                "base_credits": base_credits,
                "time_credits": time_credits,
                "token_credits": token_credits,
                "api_call_credits": api_call_credits,
                "total_credits": total_credits,
                "discount_applied": discount,
                "final_credits": final_credits,
                "estimated_cost_usd": final_credits * 0.01,
                "tier": tier,
            }

        except Exception as e:
            safe_log(f"Failed to estimate cost: {e}", level="error")
            raise AgentCoreError(f"Failed to estimate cost: {e}") from e


# Convenience functions

def get_billing_manager(config: Optional[AgentCoreConfig] = None) -> AgentCoreBillingManager:
    """
    Get the billing manager instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        AgentCoreBillingManager instance
    """
    return AgentCoreBillingManager(config=config)


async def check_account_balance(account_id: str) -> int:
    """
    Convenience function to check account credit balance.

    Args:
        account_id: Tenant account ID

    Returns:
        Current credit balance
    """
    manager = get_billing_manager()
    return await manager.check_account_balance(account_id)


async def get_account_tier(account_id: str, skip_cache: bool = False) -> Dict[str, Any]:
    """
    Convenience function to get account tier information.

    Args:
        account_id: Tenant account ID
        skip_cache: Skip cache and fetch fresh data

    Returns:
        Dictionary with tier information
    """
    manager = get_billing_manager()
    return await manager.get_account_tier(account_id, skip_cache=skip_cache)
