"""
AgentCore Usage Tracker (Phase 8)

Tracks AgentCore execution metrics for billing integration.
Monitors execution time, token usage, API calls, and resource consumption.

Phase 8: All usage tracked in ap-southeast-2 (Australia) region for data residency.
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

logger = logging.getLogger(__name__)


@dataclass
class UsageMetrics:
    """
    Usage metrics for AgentCore execution billing.

    Attributes:
        account_id: Tenant account ID
        execution_id: Unique execution identifier
        agent_id: Agent being executed
        deployment_id: Optional AgentCore deployment ID
        started_at: Execution start timestamp
        completed_at: Execution completion timestamp
        execution_duration_seconds: Total execution time
        input_tokens: Input tokens consumed
        output_tokens: Output tokens consumed
        total_tokens: Total tokens used
        api_calls_made: Number of API calls invoked
        runtime_invocations: Runtime invocation count
        estimated_cost_usd: Estimated cost in USD
        tier: Subscription tier (free, pro, enterprise)
        region: AWS region (ap-southeast-2 for Phase 8)
        metadata: Additional metadata for billing
    """
    account_id: str
    execution_id: str
    agent_id: str
    deployment_id: Optional[str] = None

    # Time-based metrics
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    execution_duration_seconds: float = 0.0

    # Token-based metrics
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # API call metrics
    api_calls_made: int = 0
    runtime_invocations: int = 1

    # Cost tracking
    estimated_cost_usd: Optional[float] = None

    # Metadata
    tier: str = "free"
    region: str = "ap-southeast-2"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Get execution duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": self.account_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "deployment_id": self.deployment_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_duration_seconds": self.execution_duration_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "api_calls_made": self.api_calls_made,
            "runtime_invocations": self.runtime_invocations,
            "estimated_cost_usd": self.estimated_cost_usd,
            "tier": self.tier,
            "region": self.region,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UsageMetrics':
        """Create from dictionary for JSON deserialization."""
        data = data.copy()
        if isinstance(data.get('started_at'), str):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if isinstance(data.get('completed_at'), str):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CreditCost:
    """
    Credit cost calculation for billing.

    Attributes:
        base_credits: Base execution cost
        time_credits: Time-based credits
        token_credits: Token-based credits
        api_call_credits: API call credits
        total_credits: Total credits before discount
        discount_applied: Discount multiplier (1.0 = no discount)
        final_credits: Final credits after discount
    """
    base_credits: int = 1
    time_credits: int = 0
    token_credits: int = 0
    api_call_credits: int = 0
    total_credits: int = 0
    discount_applied: float = 1.0
    final_credits: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "base_credits": self.base_credits,
            "time_credits": self.time_credits,
            "token_credits": self.token_credits,
            "api_call_credits": self.api_call_credits,
            "total_credits": self.total_credits,
            "discount_applied": self.discount_applied,
            "final_credits": self.final_credits,
        }


class UsageTracker:
    """
    Track AgentCore usage for billing integration.

    Phase 8: Integrates with existing billing system to track execution
    metrics and deduct credits based on usage.

    Credit Calculation:
    - Base: 1 credit per execution
    - Time: 0.01 credits per second
    - Tokens: 0.5 credits per 1000 tokens
    - API Calls: 0.25 credits per tool usage

    Tier Discounts:
    - Free: No discount
    - Pro: 20% discount (0.8 multiplier)
    - Enterprise: 50% discount (0.5 multiplier)
    """

    # Pricing constants (configurable via environment)
    BASE_CREDIT_COST = 1
    CREDIT_PER_SECOND = Decimal("0.01")
    CREDIT_PER_1000_TOKENS = Decimal("0.5")
    CREDIT_PER_TOOL_USAGE = Decimal("0.25")

    # Tier discounts
    TIER_DISCOUNTS = {
        "free": 1.0,
        "pro": 0.8,
        "enterprise": 0.5,
    }

    # Phase 8 required region
    PHASE_8_REGION = "ap-southeast-2"

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the usage tracker.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If config is invalid for usage tracking.
        """
        self.config = config or get_config()
        self._active_executions: Dict[str, UsageMetrics] = {}

        # Validate region compliance for Phase 8
        if self.config.aws_region != self.PHASE_8_REGION:
            safe_log(
                f"Usage tracker: Region '{self.config.aws_region}' specified, "
                f"but Phase 8 requires '{self.PHASE_8_REGION}'. "
                f"All usage will be tracked in {self.PHASE_8_REGION} for compliance."
            )

        safe_log("UsageTracker initialized")

    async def start_execution_tracking(
        self,
        execution_id: str,
        agent_id: str,
        account_id: str,
        deployment_id: Optional[str] = None,
        tier: str = "free",
    ) -> UsageMetrics:
        """
        Start tracking a new AgentCore execution.

        Args:
            execution_id: Unique execution identifier
            agent_id: Agent being executed
            account_id: Tenant account ID
            deployment_id: Optional AgentCore deployment ID
            tier: Subscription tier (free, pro, enterprise)

        Returns:
            UsageMetrics instance for tracking

        Raises:
            AgentCoreError: If execution tracking fails to start
        """
        try:
            metrics = UsageMetrics(
                account_id=account_id,
                execution_id=execution_id,
                agent_id=agent_id,
                deployment_id=deployment_id,
                started_at=datetime.utcnow(),
                tier=tier,
                region=self.PHASE_8_REGION,  # Phase 8: Always ap-southeast-2
            )

            self._active_executions[execution_id] = metrics
            safe_log(
                f"Started tracking execution {execution_id[:8]}... "
                f"for account {account_id}, agent {agent_id}"
            )
            return metrics

        except Exception as e:
            safe_log(f"Failed to start execution tracking: {e}", level="error")
            raise AgentCoreError(f"Failed to start execution tracking: {e}") from e

    async def update_execution_metrics(
        self,
        execution_id: str,
        **updates
    ) -> Optional[UsageMetrics]:
        """
        Update metrics for an active execution.

        Args:
            execution_id: Execution identifier
            **updates: Metric fields to update (e.g., input_tokens=1000)

        Returns:
            Updated UsageMetrics if found, None otherwise
        """
        metrics = self._active_executions.get(execution_id)
        if not metrics:
            safe_log(
                f"Execution {execution_id[:8]}... not found in active tracking",
                level="warning"
            )
            return None

        # Update specified fields
        for key, value in updates.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Recalculate derived fields
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens

        return metrics

    async def complete_execution_tracking(
        self,
        execution_id: str,
        final_result: Optional[Dict[str, Any]] = None,
    ) -> Optional[UsageMetrics]:
        """
        Complete execution tracking and persist to billing.

        Args:
            execution_id: Execution identifier
            final_result: Optional final execution result with metrics

        Returns:
            Completed UsageMetrics with billing applied

        Raises:
            AgentCoreError: If billing persistence fails
        """
        if execution_id not in self._active_executions:
            safe_log(
                f"Execution {execution_id[:8]}... not found in active tracking",
                level="warning"
            )
            return None

        metrics = self._active_executions.pop(execution_id)
        metrics.completed_at = datetime.utcnow()
        metrics.execution_duration_seconds = metrics.duration

        # Extract metrics from final result if provided
        if final_result:
            metrics.input_tokens = final_result.get("input_tokens", metrics.input_tokens)
            metrics.output_tokens = final_result.get("output_tokens", metrics.output_tokens)
            metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
            metrics.api_calls_made = final_result.get("api_calls_made", metrics.api_calls_made)
            metrics.metadata.update(final_result.get("metadata", {}))

        # Persist to billing system
        await self._persist_usage_to_billing(metrics)

        safe_log(
            f"Completed tracking execution {execution_id[:8]}... "
            f"({metrics.execution_duration_seconds:.2f}s, {metrics.total_tokens} tokens)"
        )
        return metrics

    async def _persist_usage_to_billing(self, metrics: UsageMetrics) -> CreditCost:
        """
        Persist usage metrics to existing billing system.

        Args:
            metrics: Usage metrics to persist

        Returns:
            CreditCost with calculated credit deduction

        Raises:
            AgentCoreError: If billing persistence fails
        """
        try:
            # Import here to avoid circular dependencies
            from core.billing.credits.manager import CreditManager

            # Calculate credits to deduct
            credit_cost = self._calculate_credits_from_usage(metrics)

            # Initialize credit manager
            credit_manager = CreditManager()

            # Deduct credits using existing billing system
            deduction_result = await credit_manager.deduct_credits(
                account_id=metrics.account_id,
                amount=Decimal(str(credit_cost.final_credits)),
                description=f"AgentCore execution: {metrics.agent_id}",
                type="agentcore_usage",
                message_id=metrics.execution_id,
                metadata={
                    "agent_id": metrics.agent_id,
                    "deployment_id": metrics.deployment_id,
                    "execution_id": metrics.execution_id,
                    "duration_seconds": metrics.execution_duration_seconds,
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "total_tokens": metrics.total_tokens,
                    "api_calls_made": metrics.api_calls_made,
                    "tier": metrics.tier,
                    "region": metrics.region,
                }
            )

            safe_log(
                f"Deducted {credit_cost.final_credits} credits for execution "
                f"{metrics.execution_id[:8]}... (new balance: {deduction_result.get('balance', 'unknown')})"
            )

            return credit_cost

        except ImportError as e:
            safe_log(f"Billing system not available: {e}", level="warning")
            # Still calculate costs for logging
            return self._calculate_credits_from_usage(metrics)
        except Exception as e:
            safe_log(f"Failed to persist usage to billing: {e}", level="error")
            raise AgentCoreError(f"Failed to persist usage to billing: {e}") from e

    def _calculate_credits_from_usage(self, metrics: UsageMetrics) -> CreditCost:
        """
        Calculate credits to deduct based on usage metrics.

        Formula:
            base_credits = 1 (per execution)
            time_credits = duration_seconds * 0.01
            token_credits = (total_tokens / 1000) * 0.5
            api_call_credits = api_calls_made * 0.25

        Args:
            metrics: Usage metrics to calculate from

        Returns:
            CreditCost with breakdown and final amount
        """
        # Calculate base costs
        base_credits = self.BASE_CREDIT_COST

        # Time-based cost
        time_credits = int(
            Decimal(str(metrics.execution_duration_seconds)) * self.CREDIT_PER_SECOND
        )

        # Token-based cost
        token_credits = int(
            (Decimal(str(metrics.total_tokens)) / Decimal("1000")) * self.CREDIT_PER_1000_TOKENS
        )

        # API call cost
        api_call_credits = int(
            Decimal(str(metrics.api_calls_made)) * self.CREDIT_PER_TOOL_USAGE
        )

        # Total before discount
        total_credits = base_credits + time_credits + token_credits + api_call_credits

        # Apply tier-based discount
        discount = self.TIER_DISCOUNTS.get(metrics.tier, 1.0)
        final_credits = max(1, int(total_credits * discount))

        credit_cost = CreditCost(
            base_credits=base_credits,
            time_credits=time_credits,
            token_credits=token_credits,
            api_call_credits=api_call_credits,
            total_credits=total_credits,
            discount_applied=discount,
            final_credits=final_credits,
        )

        # Store estimated cost in USD (approximate: 1 credit = $0.01)
        credit_cost.estimated_cost_usd = final_credits * 0.01

        return credit_cost

    async def get_active_executions(self) -> List[UsageMetrics]:
        """
        Get list of currently tracked executions.

        Returns:
            List of active UsageMetrics
        """
        return list(self._active_executions.values())

    async def cancel_execution_tracking(
        self,
        execution_id: str,
    ) -> Optional[UsageMetrics]:
        """
        Cancel execution tracking without billing.

        Args:
            execution_id: Execution identifier to cancel

        Returns:
            Cancelled UsageMetrics if found, None otherwise
        """
        if execution_id not in self._active_executions:
            return None

        metrics = self._active_executions.pop(execution_id)
        metrics.completed_at = datetime.utcnow()
        metrics.execution_duration_seconds = metrics.duration

        safe_log(
            f"Cancelled tracking execution {execution_id[:8]}... "
            f"(duration: {metrics.execution_duration_seconds:.2f}s)"
        )
        return metrics


# Convenience functions

def get_usage_tracker(config: Optional[AgentCoreConfig] = None) -> UsageTracker:
    """
    Get the usage tracker instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        UsageTracker instance
    """
    return UsageTracker(config=config)


async def track_agent_execution(
    execution_id: str,
    agent_id: str,
    account_id: str,
    deployment_id: Optional[str] = None,
    tier: str = "free",
    config: Optional[AgentCoreConfig] = None,
) -> UsageMetrics:
    """
    Convenience function to start tracking an AgentCore execution.

    Args:
        execution_id: Unique execution identifier
        agent_id: Agent being executed
        account_id: Tenant account ID
        deployment_id: Optional AgentCore deployment ID
        tier: Subscription tier
        config: Optional AgentCore configuration

    Returns:
        UsageMetrics instance for tracking
    """
    tracker = get_usage_tracker(config)
    return await tracker.start_execution_tracking(
        execution_id=execution_id,
        agent_id=agent_id,
        account_id=account_id,
        deployment_id=deployment_id,
        tier=tier,
    )


async def complete_agent_execution(
    execution_id: str,
    final_result: Optional[Dict[str, Any]] = None,
    config: Optional[AgentCoreConfig] = None,
) -> Optional[UsageMetrics]:
    """
    Convenience function to complete AgentCore execution tracking.

    Args:
        execution_id: Execution identifier
        final_result: Optional final execution result
        config: Optional AgentCore configuration

    Returns:
        Completed UsageMetrics with billing applied
    """
    tracker = get_usage_tracker(config)
    return await tracker.complete_execution_tracking(
        execution_id=execution_id,
        final_result=final_result,
    )
