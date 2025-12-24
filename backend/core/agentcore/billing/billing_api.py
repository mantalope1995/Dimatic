"""
AgentCore Billing API Endpoints (Phase 8)

FastAPI endpoints for AgentCore billing operations.

Phase 8: All billing operations use ap-southeast-2 (Australia) region.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    safe_log,
)
from ..middleware.auth import get_current_account
from .usage_tracker import UsageMetrics, UsageTracker
from .billing_manager import AgentCoreBillingManager, BillingSummary
from .tier_features import (
    TierFeatureManager,
    Feature,
    Tier,
    get_tier_feature_manager,
)
from .cost_optimizer import (
    CostOptimizer,
    CostAnalysis,
    CostRecommendation,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/agentcore/billing", tags=["agentcore-billing"])

# Phase 8 required region
PHASE_8_REGION = "ap-southeast-2"


# ============================================================================
# Request/Response Models
# ============================================================================

class UsageTrackingStartRequest(BaseModel):
    """Request to start usage tracking."""
    execution_id: str = Field(..., description="Unique execution identifier")
    agent_id: str = Field(..., description="Agent being executed")
    deployment_id: Optional[str] = Field(None, description="AgentCore deployment ID")
    tier: str = Field("free", description="Subscription tier")


class UsageTrackingUpdateRequest(BaseModel):
    """Request to update usage metrics."""
    execution_id: str = Field(..., description="Execution identifier")
    input_tokens: Optional[int] = Field(None, description="Input tokens consumed")
    output_tokens: Optional[int] = Field(None, description="Output tokens consumed")
    api_calls_made: Optional[int] = Field(None, description="API calls made")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class UsageTrackingCompleteRequest(BaseModel):
    """Request to complete usage tracking."""
    execution_id: str = Field(..., description="Execution identifier")
    final_result: Optional[Dict[str, Any]] = Field(None, description="Final execution result")


class FeatureCheckRequest(BaseModel):
    """Request to check feature access."""
    account_id: str = Field(..., description="Tenant account ID")
    feature: str = Field(..., description="Feature to check")


class FeatureCheckResponse(BaseModel):
    """Response for feature access check."""
    feature: str
    allowed: bool
    tier: str
    reason: Optional[str] = None
    current_usage: int = 0
    remaining_quota: int = 0


class CostAnalysisRequest(BaseModel):
    """Request for cost analysis."""
    account_id: str = Field(..., description="Tenant account ID")
    period_days: int = Field(30, description="Number of days to analyze", ge=1, le=90)


class CostForecastRequest(BaseModel):
    """Request for cost forecast."""
    account_id: str = Field(..., description="Tenant account ID")
    forecast_days: int = Field(30, description="Number of days to forecast", ge=1, le=365)


class BudgetAlertRequest(BaseModel):
    """Request for budget alerts."""
    account_id: str = Field(..., description="Tenant account ID")
    budget_usd: Optional[float] = Field(None, description="Monthly budget threshold")


# ============================================================================
# Dependencies
# ============================================================================

def get_billing_manager() -> AgentCoreBillingManager:
    """Get billing manager instance."""
    return AgentCoreBillingManager(config=get_config())


def get_usage_tracker() -> UsageTracker:
    """Get usage tracker instance."""
    return UsageTracker(config=get_config())


def get_tier_manager() -> TierFeatureManager:
    """Get tier feature manager instance."""
    return get_tier_feature_manager(config=get_config())


def get_cost_optimizer() -> CostOptimizer:
    """Get cost optimizer instance."""
    return CostOptimizer(config=get_config())


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/usage/start")
async def start_usage_tracking(
    request: UsageTrackingStartRequest,
    tracker: UsageTracker = Depends(get_usage_tracker),
) -> Dict[str, Any]:
    """
    Start tracking AgentCore execution usage.

    Args:
        request: Usage tracking start request

    Returns:
        UsageMetrics for the execution
    """
    try:
        # Get account_id from auth context (optional, for logging)
        account_id = getattr(tracker, 'account_id', request.agent_id)

        metrics = await tracker.start_execution_tracking(
            execution_id=request.execution_id,
            agent_id=request.agent_id,
            account_id=account_id,
            deployment_id=request.deployment_id,
            tier=request.tier,
        )

        safe_log(f"Started usage tracking for execution {request.execution_id[:8]}...")

        return {
            "status": "success",
            "metrics": metrics.to_dict(),
            "region": PHASE_8_REGION,
        }

    except AgentCoreError as e:
        safe_log(f"Failed to start usage tracking: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/usage/update")
async def update_usage_tracking(
    request: UsageTrackingUpdateRequest,
    tracker: UsageTracker = Depends(get_usage_tracker),
) -> Dict[str, Any]:
    """
    Update usage metrics for an active execution.

    Args:
        request: Usage tracking update request

    Returns:
        Updated UsageMetrics
    """
    try:
        # Build updates dict
        updates = {}
        if request.input_tokens is not None:
            updates["input_tokens"] = request.input_tokens
        if request.output_tokens is not None:
            updates["output_tokens"] = request.output_tokens
        if request.api_calls_made is not None:
            updates["api_calls_made"] = request.api_calls_made
        if request.metadata is not None:
            updates["metadata"] = request.metadata

        metrics = await tracker.update_execution_metrics(
            execution_id=request.execution_id,
            **updates
        )

        if metrics is None:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {request.execution_id} not found in active tracking"
            )

        return {
            "status": "success",
            "metrics": metrics.to_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_log(f"Failed to update usage tracking: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/usage/complete")
async def complete_usage_tracking(
    request: UsageTrackingCompleteRequest,
    tracker: UsageTracker = Depends(get_usage_tracker),
) -> Dict[str, Any]:
    """
    Complete usage tracking and persist to billing.

    Args:
        request: Usage tracking complete request

    Returns:
        Completed UsageMetrics with billing applied
    """
    try:
        metrics = await tracker.complete_execution_tracking(
            execution_id=request.execution_id,
            final_result=request.final_result,
        )

        if metrics is None:
            raise HTTPException(
                status_code=404,
                detail=f"Execution {request.execution_id} not found in active tracking"
            )

        safe_log(f"Completed usage tracking for execution {request.execution_id[:8]}...")

        return {
            "status": "success",
            "metrics": metrics.to_dict(),
            "credits_deducted": True,
            "region": PHASE_8_REGION,
        }

    except HTTPException:
        raise
    except Exception as e:
        safe_log(f"Failed to complete usage tracking: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance")
async def check_account_balance(
    account_id: str = Query(..., description="Tenant account ID"),
    billing_manager: AgentCoreBillingManager = Depends(get_billing_manager),
) -> Dict[str, Any]:
    """
    Check current credit balance for an account.

    Args:
        account_id: Tenant account ID

    Returns:
        Account balance information
    """
    try:
        balance = await billing_manager.check_account_balance(account_id)

        return {
            "account_id": account_id,
            "balance": balance,
            "region": PHASE_8_REGION,
        }

    except AgentCoreError as e:
        safe_log(f"Failed to check balance: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tier")
async def get_account_tier(
    account_id: str = Query(..., description="Tenant account ID"),
    skip_cache: bool = Query(False, description="Skip cache and fetch fresh data"),
    billing_manager: AgentCoreBillingManager = Depends(get_billing_manager),
) -> Dict[str, Any]:
    """
    Get subscription tier for an account.

    Args:
        account_id: Tenant account ID
        skip_cache: Skip cache and fetch fresh data

    Returns:
        Tier information
    """
    try:
        tier_info = await billing_manager.get_account_tier(account_id, skip_cache)

        return {
            "account_id": account_id,
            **tier_info,
            "region": PHASE_8_REGION,
        }

    except Exception as e:
        safe_log(f"Failed to get tier: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/features/check")
async def check_feature_access(
    request: FeatureCheckRequest,
    tier_manager: TierFeatureManager = Depends(get_tier_manager),
) -> FeatureCheckResponse:
    """
    Check if an account has access to a feature.

    Args:
        request: Feature check request

    Returns:
        Feature access check result
    """
    try:
        result = await tier_manager.check_feature_access(
            account_id=request.account_id,
            feature=Feature(request.feature),
        )

        return FeatureCheckResponse(
            feature=result.feature.value,
            allowed=result.allowed,
            tier=result.tier,
            reason=result.reason,
            current_usage=result.current_usage,
            remaining_quota=result.remaining_quota,
        )

    except ConfigurationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        safe_log(f"Failed to check feature: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/features")
async def get_available_features(
    account_id: str = Query(..., description="Tenant account ID"),
    tier_manager: TierFeatureManager = Depends(get_tier_manager),
) -> Dict[str, Any]:
    """
    Get list of available features for an account.

    Args:
        account_id: Tenant account ID

    Returns:
        List of available features
    """
    try:
        features = await tier_manager.get_available_features(account_id)

        return {
            "account_id": account_id,
            "features": [f.value for f in features],
            "region": PHASE_8_REGION,
        }

    except Exception as e:
        safe_log(f"Failed to get available features: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_billing_summary(
    account_id: str = Query(..., description="Tenant account ID"),
    billing_manager: AgentCoreBillingManager = Depends(get_billing_manager),
) -> Dict[str, Any]:
    """
    Get comprehensive billing summary for an account.

    Args:
        account_id: Tenant account ID

    Returns:
        Billing summary
    """
    try:
        summary = await billing_manager.get_billing_summary(account_id)

        return summary.to_dict()

    except AgentCoreError as e:
        safe_log(f"Failed to get billing summary: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost/analyze")
async def analyze_costs(
    request: CostAnalysisRequest,
    cost_optimizer: CostOptimizer = Depends(get_cost_optimizer),
) -> Dict[str, Any]:
    """
    Analyze AgentCore costs and get optimization recommendations.

    Args:
        request: Cost analysis request

    Returns:
        Cost analysis with recommendations
    """
    try:
        analysis = await cost_optimizer.analyze_cost(
            account_id=request.account_id,
            period_days=request.period_days,
        )

        return analysis.to_dict()

    except AgentCoreError as e:
        safe_log(f"Failed to analyze costs: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost/forecast")
async def forecast_costs(
    request: CostForecastRequest,
    cost_optimizer: CostOptimizer = Depends(get_cost_optimizer),
) -> Dict[str, Any]:
    """
    Forecast future costs based on current usage patterns.

    Args:
        request: Cost forecast request

    Returns:
        Cost forecast
    """
    try:
        forecast = await cost_optimizer.forecast_cost(
            account_id=request.account_id,
            forecast_days=request.forecast_days,
        )

        return forecast

    except AgentCoreError as e:
        safe_log(f"Failed to forecast costs: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cost/budget-alerts")
async def check_budget_alerts(
    request: BudgetAlertRequest,
    cost_optimizer: CostOptimizer = Depends(get_cost_optimizer),
) -> Dict[str, Any]:
    """
    Check budget alerts for an account.

    Args:
        request: Budget alert request

    Returns:
        List of budget alerts
    """
    try:
        alerts = await cost_optimizer.get_budget_alerts(
            account_id=request.account_id,
            budget_usd=request.budget_usd,
        )

        return {
            "account_id": request.account_id,
            "alerts": alerts,
            "alert_count": len(alerts),
        }

    except AgentCoreError as e:
        safe_log(f"Failed to check budget alerts: {e}", level="error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for AgentCore billing services.

    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "service": "agentcore-billing",
        "region": PHASE_8_REGION,
        "timestamp": datetime.utcnow().isoformat(),
    }


# Export router
__all__ = ["router"]
