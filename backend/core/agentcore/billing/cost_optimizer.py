"""
AgentCore Cost Optimizer (Phase 8)

Provides cost optimization and monitoring for AgentCore operations.
Analyzes usage patterns and provides recommendations for cost reduction.

Phase 8: All cost tracking uses ap-southeast-2 (Australia) region.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    safe_log,
)
from .usage_tracker import UsageMetrics

logger = logging.getLogger(__name__)


class OptimizationType(str, Enum):
    """Types of cost optimization recommendations."""
    UPGRADE_TIER = "upgrade_tier"
    REDUCE_EXECUTION_TIME = "reduce_execution_time"
    OPTIMIZE_PROMPTS = "optimize_prompts"
    BATCH_EXECUTIONS = "batch_executions"
    CACHE_RESULTS = "cache_results"
    ADJUST_TIMEOUT = "adjust_timeout"
    LIMIT_TOKEN_USAGE = "limit_token_usage"


@dataclass
class CostRecommendation:
    """
    Cost optimization recommendation.

    Attributes:
        type: Type of recommendation
        title: Human-readable title
        description: Detailed explanation
        priority: Priority level (low, medium, high, critical)
        estimated_savings_usd: Estimated monthly savings in USD
        estimated_savings_percent: Estimated savings as percentage
        effort: Implementation effort (low, medium, high)
        action_items: List of actionable steps
        metadata: Additional metadata
    """
    type: OptimizationType
    title: str
    description: str
    priority: str  # low, medium, high, critical
    estimated_savings_usd: float
    estimated_savings_percent: float
    effort: str  # low, medium, high
    action_items: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "estimated_savings_usd": self.estimated_savings_usd,
            "estimated_savings_percent": self.estimated_savings_percent,
            "effort": self.effort,
            "action_items": self.action_items,
            "metadata": self.metadata,
        }


@dataclass
class CostAnalysis:
    """
    Analysis of AgentCore cost patterns.

    Attributes:
        account_id: Tenant account ID
        period_start: Analysis period start
        period_end: Analysis period end
        total_cost_usd: Total cost in period
        execution_count: Number of executions
        avg_cost_per_execution: Average cost per execution
        avg_duration_seconds: Average execution duration
        avg_tokens_per_execution: Average tokens per execution
        tier: Current subscription tier
        region: AWS region
        recommendations: Generated recommendations
    """
    account_id: str
    period_start: datetime
    period_end: datetime
    total_cost_usd: float
    execution_count: int
    avg_cost_per_execution: float
    avg_duration_seconds: float
    avg_tokens_per_execution: float
    tier: str
    region: str = "ap-southeast-2"
    recommendations: List[CostRecommendation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": self.account_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_cost_usd": self.total_cost_usd,
            "execution_count": self.execution_count,
            "avg_cost_per_execution": self.avg_cost_per_execution,
            "avg_duration_seconds": self.avg_duration_seconds,
            "avg_tokens_per_execution": self.avg_tokens_per_execution,
            "tier": self.tier,
            "region": self.region,
            "recommendations": [r.to_dict() for r in self.recommendations],
        }


@dataclass
class CostBreakdown:
    """
    Detailed cost breakdown by category.

    Attributes:
        account_id: Tenant account ID
        period_start: Analysis period start
        period_end: Analysis period end
        base_cost_usd: Base execution cost
        time_cost_usd: Time-based cost
        token_cost_usd: Token-based cost
        api_call_cost_usd: API call cost
        total_cost_usd: Total cost
        cost_by_agent: Cost breakdown by agent
        cost_by_day: Cost breakdown by day
    """
    account_id: str
    period_start: datetime
    period_end: datetime
    base_cost_usd: float = 0.0
    time_cost_usd: float = 0.0
    token_cost_usd: float = 0.0
    api_call_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    cost_by_agent: Dict[str, float] = field(default_factory=dict)
    cost_by_day: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": self.account_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "base_cost_usd": self.base_cost_usd,
            "time_cost_usd": self.time_cost_usd,
            "token_cost_usd": self.token_cost_usd,
            "api_call_cost_usd": self.api_call_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "cost_by_agent": self.cost_by_agent,
            "cost_by_day": self.cost_by_day,
        }


class CostOptimizer:
    """
    Analyze AgentCore usage and provide cost optimization recommendations.

    Phase 8: Analyzes usage in ap-southeast-2 (Australia) region.

    Capabilities:
    - Cost analysis and breakdown by category
    - Usage pattern analysis
    - Tier optimization recommendations
    - Performance vs. cost trade-off analysis
    - Budget forecasting
    """

    # Phase 8 required region
    PHASE_8_REGION = "ap-southeast-2"

    # Cost thresholds for recommendations
    HIGH_COST_THRESHOLD_USD = 100.0  # Monthly
    LONG_EXECUTION_THRESHOLD_SECONDS = 1800  # 30 minutes
    HIGH_TOKEN_THRESHOLD = 500000  # tokens per execution

    # Credit pricing (1 credit = $0.01)
    CREDIT_TO_USD = 0.01

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the cost optimizer.

        Args:
            config: AgentCore configuration. If None, uses global config.
        """
        self.config = config or get_config()
        self._billing_manager = None

        if self.config.aws_region != self.PHASE_8_REGION:
            safe_log(
                f"Cost optimizer: Region '{self.config.aws_region}' specified, "
                f"but Phase 8 requires '{self.PHASE_8_REGION}'. "
                f"All analysis will use {self.PHASE_8_REGION} for compliance."
            )

        safe_log("CostOptimizer initialized")

    def _get_billing_manager(self):
        """Lazy initialization of billing manager."""
        if self._billing_manager is None:
            from .billing_manager import get_billing_manager
            self._billing_manager = get_billing_manager(self.config)
        return self._billing_manager

    async def analyze_cost(
        self,
        account_id: str,
        period_days: int = 30,
    ) -> CostAnalysis:
        """
        Analyze AgentCore costs for an account over a period.

        Args:
            account_id: Tenant account ID
            period_days: Number of days to analyze (default: 30)

        Returns:
            CostAnalysis with usage patterns and recommendations

        Raises:
            AgentCoreError: If cost analysis fails
        """
        try:
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(days=period_days)

            # Get tier information
            tier_info = await self._get_billing_manager().get_account_tier(account_id)
            tier = tier_info.get("tier", "free")

            # TODO: Fetch actual usage metrics from database
            # For Phase 8, using mock data
            execution_count = 100
            total_credits = 1000
            total_cost_usd = total_credits * self.CREDIT_TO_USD
            avg_cost_per_execution = total_cost_usd / execution_count if execution_count > 0 else 0
            avg_duration_seconds = 45.0
            avg_tokens_per_execution = 50000

            analysis = CostAnalysis(
                account_id=account_id,
                period_start=period_start,
                period_end=period_end,
                total_cost_usd=total_cost_usd,
                execution_count=execution_count,
                avg_cost_per_execution=avg_cost_per_execution,
                avg_duration_seconds=avg_duration_seconds,
                avg_tokens_per_execution=avg_tokens_per_execution,
                tier=tier,
                region=self.PHASE_8_REGION,
            )

            # Generate recommendations
            analysis.recommendations = await self._generate_recommendations(analysis)

            safe_log(
                f"Cost analysis for {account_id}: ${total_cost_usd:.2f} "
                f"over {period_days} days ({len(analysis.recommendations)} recommendations)"
            )

            return analysis

        except Exception as e:
            safe_log(f"Failed to analyze cost: {e}", level="error")
            raise AgentCoreError(f"Failed to analyze cost: {e}") from e

    async def _generate_recommendations(
        self,
        analysis: CostAnalysis,
    ) -> List[CostRecommendation]:
        """
        Generate cost optimization recommendations based on analysis.

        Args:
            analysis: Cost analysis results

        Returns:
            List of cost recommendations
        """
        recommendations = []

        # High cost check
        if analysis.total_cost_usd > self.HIGH_COST_THRESHOLD_USD:
            recommendations.append(CostRecommendation(
                type=OptimizationType.UPGRADE_TIER,
                title="Consider upgrading to Pro tier",
                description=(
                    f"Your monthly AgentCore cost (${analysis.total_cost_usd:.2f}) "
                    f"exceeds the recommended threshold. Upgrading to Pro tier provides "
                    f"20% discount on credit usage, potentially saving "
                    f"${analysis.total_cost_usd * 0.2:.2f}/month."
                ),
                priority="high",
                estimated_savings_usd=analysis.total_cost_usd * 0.2,
                estimated_savings_percent=20.0,
                effort="low",
                action_items=[
                    "Review Pro tier features and pricing",
                    "Calculate potential savings with tier discount",
                    "Consider upgrade if usage is consistent",
                ],
            ))

        # Long execution check
        if analysis.avg_duration_seconds > self.LONG_EXECUTION_THRESHOLD_SECONDS:
            recommendations.append(CostRecommendation(
                type=OptimizationType.REDUCE_EXECUTION_TIME,
                title="Optimize agent execution time",
                description=(
                    f"Average execution time ({analysis.avg_duration_seconds:.0f}s) "
                    f"exceeds recommended threshold. Consider optimizing prompts, "
                    f"reducing tool usage, or breaking into smaller tasks."
                ),
                priority="medium",
                estimated_savings_usd=analysis.total_cost_usd * 0.15,
                estimated_savings_percent=15.0,
                effort="medium",
                action_items=[
                    "Review agent prompts for efficiency",
                    "Reduce unnecessary tool calls",
                    "Consider task parallelization",
                    "Use shorter time limits for non-critical operations",
                ],
            ))

        # High token usage check
        if analysis.avg_tokens_per_execution > self.HIGH_TOKEN_THRESHOLD:
            recommendations.append(CostRecommendation(
                type=OptimizationType.OPTIMIZE_PROMPTS,
                title="Reduce token consumption",
                description=(
                    f"Average token usage ({analysis.avg_tokens_per_execution:,}) "
                    f"per execution is high. Optimizing prompts can significantly "
                    f"reduce costs while maintaining performance."
                ),
                priority="medium",
                estimated_savings_usd=analysis.total_cost_usd * 0.1,
                estimated_savings_percent=10.0,
                effort="medium",
                action_items=[
                    "Use more concise prompts",
                    "Implement context window optimization",
                    "Cache frequently used responses",
                    "Consider using smaller models for simple tasks",
                ],
            ))

        # Caching recommendation
        recommendations.append(CostRecommendation(
            type=OptimizationType.CACHE_RESULTS,
            title="Enable result caching",
            description=(
                "Caching frequently used agent results can reduce redundant "
                "executions by 30-50%, especially for repetitive tasks."
            ),
            priority="low",
            estimated_savings_usd=analysis.total_cost_usd * 0.3,
            estimated_savings_percent=30.0,
            effort="medium",
            action_items=[
                "Identify repetitive execution patterns",
                "Implement result caching with TTL",
                "Configure cache invalidation strategy",
                "Monitor cache hit rates",
            ],
        ))

        # Batch execution recommendation
        if analysis.execution_count > 50:
            recommendations.append(CostRecommendation(
                type=OptimizationType.BATCH_EXECUTIONS,
                title="Batch similar executions",
                description=(
                    f"With {analysis.execution_count} executions, batching "
                    f"similar tasks can reduce overhead and improve efficiency."
                ),
                priority="low",
                estimated_savings_usd=analysis.total_cost_usd * 0.1,
                estimated_savings_percent=10.0,
                effort="high",
                action_items=[
                    "Group similar agent tasks",
                    "Implement batch execution API",
                    "Use asynchronous execution patterns",
                    "Monitor batch performance",
                ],
            ))

        return recommendations

    async def get_cost_breakdown(
        self,
        account_id: str,
        period_days: int = 30,
    ) -> CostBreakdown:
        """
        Get detailed cost breakdown by category.

        Args:
            account_id: Tenant account ID
            period_days: Number of days to analyze

        Returns:
            CostBreakdown with detailed cost breakdown

        Raises:
            AgentCoreError: If breakdown retrieval fails
        """
        try:
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(days=period_days)

            # TODO: Fetch actual breakdown from database
            # For Phase 8, using mock data
            breakdown = CostBreakdown(
                account_id=account_id,
                period_start=period_start,
                period_end=period_end,
                base_cost_usd=10.0,
                time_cost_usd=40.0,
                token_cost_usd=30.0,
                api_call_cost_usd=20.0,
                total_cost_usd=100.0,
                cost_by_agent={
                    "web_search_agent": 40.0,
                    "data_processor_agent": 35.0,
                    "code_analyzer_agent": 25.0,
                },
                cost_by_day={
                    "2024-01-01": 3.5,
                    "2024-01-02": 4.0,
                    "2024-01-03": 3.2,
                },
            )

            return breakdown

        except Exception as e:
            safe_log(f"Failed to get cost breakdown: {e}", level="error")
            raise AgentCoreError(f"Failed to get cost breakdown: {e}") from e

    async def forecast_cost(
        self,
        account_id: str,
        forecast_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Forecast future costs based on current usage patterns.

        Args:
            account_id: Tenant account ID
            forecast_days: Number of days to forecast

        Returns:
            Dictionary with forecast results

        Raises:
            AgentCoreError: If forecasting fails
        """
        try:
            # Get current cost analysis
            analysis = await self.analyze_cost(account_id, period_days=30)

            # Calculate daily average
            daily_cost = analysis.total_cost_usd / 30

            # Project forecast
            forecast_total = daily_cost * forecast_days

            # Calculate confidence bounds (±20%)
            lower_bound = forecast_total * 0.8
            upper_bound = forecast_total * 1.2

            return {
                "account_id": account_id,
                "forecast_days": forecast_days,
                "current_daily_avg": daily_cost,
                "forecast_total_usd": forecast_total,
                "lower_bound_usd": lower_bound,
                "upper_bound_usd": upper_bound,
                "confidence": "medium",
                "based_on_period_days": 30,
                "region": self.PHASE_8_REGION,
            }

        except Exception as e:
            safe_log(f"Failed to forecast cost: {e}", level="error")
            raise AgentCoreError(f"Failed to forecast cost: {e}") from e

    async def get_budget_alerts(
        self,
        account_id: str,
        budget_usd: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Check if account is approaching or exceeding budget.

        Args:
            account_id: Tenant account ID
            budget_usd: Monthly budget threshold (optional)

        Returns:
            List of budget alerts

        Raises:
            AgentCoreError: If alert check fails
        """
        alerts = []

        try:
            # Get forecast
            forecast = await self.forecast_cost(account_id, forecast_days=30)

            if budget_usd is None:
                # Use tier-based default budgets
                tier_info = await self._get_billing_manager().get_account_tier(account_id)
                tier = tier_info.get("tier", "free")
                budget_usd = {
                    "free": 20.0,
                    "pro": 200.0,
                    "enterprise": 2000.0,
                }.get(tier, 20.0)

            # Check if forecast exceeds budget
            if forecast["forecast_total_usd"] > budget_usd:
                alerts.append({
                    "severity": "critical",
                    "type": "budget_exceeded",
                    "message": (
                        f"Forecasted monthly cost (${forecast['forecast_total_usd']:.2f}) "
                        f"exceeds budget (${budget_usd:.2f})"
                    ),
                    "forecast_total_usd": forecast["forecast_total_usd"],
                    "budget_usd": budget_usd,
                    "overage_usd": forecast["forecast_total_usd"] - budget_usd,
                })

            # Check if approaching budget (80% threshold)
            elif forecast["upper_bound_usd"] > budget_usd * 0.8:
                alerts.append({
                    "severity": "warning",
                    "type": "budget_warning",
                    "message": (
                        f"Projected cost may approach budget (${budget_usd:.2f}). "
                        f"Forecast: ${forecast['forecast_total_usd']:.2f} "
                        f"(upper bound: ${forecast['upper_bound_usd']:.2f})"
                    ),
                    "forecast_total_usd": forecast["forecast_total_usd"],
                    "budget_usd": budget_usd,
                })

            return alerts

        except Exception as e:
            safe_log(f"Failed to check budget alerts: {e}", level="error")
            raise AgentCoreError(f"Failed to check budget alerts: {e}") from e


# Convenience functions

def get_cost_optimizer(config: Optional[AgentCoreConfig] = None) -> CostOptimizer:
    """
    Get the cost optimizer instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        CostOptimizer instance
    """
    return CostOptimizer(config=config)


async def analyze_cost(
    account_id: str,
    period_days: int = 30,
    config: Optional[AgentCoreConfig] = None,
) -> CostAnalysis:
    """
    Convenience function to analyze costs.

    Args:
        account_id: Tenant account ID
        period_days: Number of days to analyze
        config: Optional AgentCore configuration

    Returns:
        CostAnalysis with usage patterns and recommendations
    """
    optimizer = get_cost_optimizer(config)
    return await optimizer.analyze_cost(account_id, period_days)


async def get_cost_recommendations(
    account_id: str,
    period_days: int = 30,
    config: Optional[AgentCoreConfig] = None,
) -> List[CostRecommendation]:
    """
    Convenience function to get cost recommendations.

    Args:
        account_id: Tenant account ID
        period_days: Number of days to analyze
        config: Optional AgentCore configuration

    Returns:
        List of cost recommendations
    """
    optimizer = get_cost_optimizer(config)
    analysis = await optimizer.analyze_cost(account_id, period_days)
    return analysis.recommendations


async def forecast_cost(
    account_id: str,
    forecast_days: int = 30,
    config: Optional[AgentCoreConfig] = None,
) -> Dict[str, Any]:
    """
    Convenience function to forecast costs.

    Args:
        account_id: Tenant account ID
        forecast_days: Number of days to forecast
        config: Optional AgentCore configuration

    Returns:
        Dictionary with forecast results
    """
    optimizer = get_cost_optimizer(config)
    return await optimizer.forecast_cost(account_id, forecast_days)


async def check_budget_alerts(
    account_id: str,
    budget_usd: Optional[float] = None,
    config: Optional[AgentCoreConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to check budget alerts.

    Args:
        account_id: Tenant account ID
        budget_usd: Monthly budget threshold
        config: Optional AgentCore configuration

    Returns:
        List of budget alerts
    """
    optimizer = get_cost_optimizer(config)
    return await optimizer.get_budget_alerts(account_id, budget_usd)
