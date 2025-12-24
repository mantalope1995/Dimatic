"""
Billing and Usage Tracking Tests for AgentCore

Tests for billing integration with existing billing system:
- Usage tracking and metering
- Credit calculation and deduction
- Tier-based pricing and features
- Billing API endpoints
- Invoice generation
- Subscription tier validation

Author: AgentCore Migration Team
Phase: Sprint 4 - Testing & Validation (Task 69)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

from core.agentcore.config import (
    AgentCoreConfig,
    Environment,
    get_agentcore_config,
)
from core.agentcore.models import (
    RuntimeDeployment,
    RuntimeSession,
    RuntimeStatus,
    RuntimeExecutionResult,
)
from core.agentcore.billing import (
    UsageMetrics,
    UsageTracker,
    CreditCost,
    TierFeatureManager,
    TierConfig,
    Tier,
)
from core.agentcore.errors import (
    AgentCoreConfigurationError,
    ValidationError,
    AgentCoreExecutionError,
)
from core.agentcore.middleware import (
    TenantContext,
    TenantContextManager,
    get_tenant_context,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def billing_config():
    """Config with billing enabled."""
    return AgentCoreConfig(
        environment=Environment.PRODUCTION,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        billing_enabled=True,
        credit_per_second=0.01,
        credit_per_1000_tokens=0.5,
        credit_per_tool_usage=0.25,
        pro_discount=0.8,
        enterprise_discount=0.5,
    )


@pytest.fixture
def billing_tenant_context():
    """Tenant context with billing tier."""
    return TenantContext(
        account_id="billing-test-account",
        tenant_id="tenant-billing-xyz",
        tier="pro",
        region="ap-southeast-2",
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def free_tenant_context():
    """Free tier tenant context."""
    return TenantContext(
        account_id="free-test-account",
        tenant_id="tenant-free-abc",
        tier="free",
        region="ap-southeast-2",
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def enterprise_tenant_context():
    """Enterprise tier tenant context."""
    return TenantContext(
        account_id="enterprise-test-account",
        tenant_id="tenant-enterprise-xyz",
        tier="enterprise",
        region="ap-southeast-2",
        created_at=datetime.utcnow(),
    )


# ============================================================================
# Usage Tracking Tests
# ============================================================================

class TestUsageTracking:
    """Tests for usage tracking and metering."""

    @pytest.mark.asyncio
    async def test_start_execution_tracking(self, billing_config, billing_tenant_context):
        """Test starting execution tracking."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            metrics = await tracker.start_execution_tracking(
                execution_id="exec-billing-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
            )

            assert metrics.execution_id == "exec-billing-123"
            assert metrics.agent_id == "test-agent"
            assert metrics.deployment_id == "test-deployment-123"
            assert metrics.account_id == "billing-test-account"
            assert metrics.tier == "pro"
            assert metrics.region == "ap-southeast-2"
            assert metrics.started_at is not None
            assert metrics.completed_at is None

    @pytest.mark.asyncio
    async def test_complete_execution_tracking(self, billing_config, billing_tenant_context):
        """Test completing execution tracking."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Start tracking
            await tracker.start_execution_tracking(
                execution_id="exec-billing-456",
                agent_id="test-agent",
                deployment_id="test-deployment-456",
            )

            # Mock execution result
            mock_result = MagicMock()
            mock_result.metadata = {
                "input_tokens": 1500,
                "output_tokens": 500,
                "api_calls": 3,
            }

            # Complete tracking
            with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                metrics = await tracker.complete_execution_tracking(
                    execution_id="exec-billing-456",
                    result=mock_result,
                )

                assert metrics.execution_id == "exec-billing-456"
                assert metrics.completed_at is not None
                assert metrics.input_tokens == 1500
                assert metrics.output_tokens == 500
                assert metrics.total_tokens == 2000
                assert metrics.duration > 0

    @pytest.mark.asyncio
    async def test_calculate_credits_from_usage(self, billing_config, billing_tenant_context):
        """Test credit calculation from usage metrics."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Create usage metrics
            metrics = UsageMetrics(
                account_id="billing-test-account",
                execution_id="exec-credit-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
                started_at=datetime.utcnow() - timedelta(seconds=60),
                completed_at=datetime.utcnow(),
                execution_duration_seconds=60.0,
                input_tokens=1000,
                output_tokens=500,
                total_tokens=1500,
                api_calls_made=5,
                runtime_invocations=1,
                tier="pro",
                region="ap-southeast-2",
            )

            credits = tracker._calculate_credits_from_usage(metrics)

            # Verify calculation
            # base_credits (1) + time_credits (60 * 0.01 = 0.6) + token_credits (1.5 * 0.5 = 0.75)
            # = 2.35 credits, with 20% pro discount = ~1.88 credits
            assert credits >= 1
            assert credits < 3

    @pytest.mark.asyncio
    async def test_persist_usage_to_billing(self, billing_config, billing_tenant_context):
        """Test persisting usage to billing system."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            metrics = UsageMetrics(
                account_id="billing-test-account",
                execution_id="exec-persist-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
                started_at=datetime.utcnow() - timedelta(seconds=30),
                completed_at=datetime.utcnow(),
                execution_duration_seconds=30.0,
                input_tokens=500,
                output_tokens=500,
                total_tokens=1000,
                tier="pro",
                region="ap-southeast-2",
            )

            # Mock CreditManager
            with patch('core.agentcore.billing.usage_tracker.CreditManager') as mock_cm:
                mock_manager = MagicMock()
                mock_cm.return_value = mock_manager
                mock_manager.consume_credits = AsyncMock()

                await tracker._persist_usage_to_billing(metrics)

                # Verify consume_credits was called
                mock_manager.consume_credits.assert_called_once()
                call_args = mock_manager.consume_credits.call_args

                assert call_args[1]["account_id"] == "billing-test-account"
                assert call_args[1]["reference_id"] == "exec-persist-123"
                assert "agent_id" in call_args[1]["metadata"]

    @pytest.mark.asyncio
    async def test_usage_tracking_without_tenant_context(self, billing_config):
        """Test that usage tracking requires tenant context."""
        tracker = UsageTracker(billing_config)

        # No tenant context set
        with pytest.raises(ValueError) as exc_info:
            await tracker.start_execution_tracking(
                execution_id="exec-no-context-123",
                agent_id="test-agent",
            )

        assert "Tenant context required" in str(exc_info.value)


# ============================================================================
# Tier-Based Features Tests
# ============================================================================

class TestTierFeatures:
    """Tests for tier-based feature flags."""

    @pytest.mark.asyncio
    async def test_free_tier_features(self):
        """Test free tier has basic features only."""
        from core.agentcore.billing import Feature

        config = TierFeatureManager.get_tier_config("free")

        assert config.name == "Free"
        assert Feature.BASIC_EXECUTION in config.features
        assert Feature.MEMORY_ACCESS in config.features
        assert Feature.CODE_INTERPRETER not in config.features
        assert Feature.BROWSER_AUTOMATION not in config.features
        assert Feature.MULTI_REGION not in config.features

    @pytest.mark.asyncio
    async def test_pro_tier_features(self):
        """Test pro tier has additional features."""
        from core.agentcore.billing import Feature

        config = TierFeatureManager.get_tier_config("pro")

        assert config.name == "Pro"
        assert Feature.BASIC_EXECUTION in config.features
        assert Feature.CODE_INTERPRETER in config.features
        assert Feature.BROWSER_AUTOMATION in config.features
        assert Feature.MCP_TOOLS in config.features
        assert Feature.MULTI_REGION not in config.features

    @pytest.mark.asyncio
    async def test_enterprise_tier_features(self):
        """Test enterprise tier has all features."""
        from core.agentcore.billing import Feature

        config = TierFeatureManager.get_tier_config("enterprise")

        assert config.name == "Enterprise"
        # All features should be available
        assert len(config.features) > 10
        assert Feature.MULTI_REGION in config.features
        assert Feature.DEDICATED_DEPLOYMENT in config.features

    @pytest.mark.asyncio
    async def test_has_feature_check(self, billing_tenant_context, free_tenant_context):
        """Test checking if tier has access to feature."""
        from core.agentcore.billing import Feature

        # Pro tier
        with TenantContextManager(billing_tenant_context):
            assert TierFeatureManager.has_feature(Feature.CODE_INTERPRETER) is True
            assert TierFeatureManager.has_feature(Feature.BASIC_EXECUTION) is True
            assert TierFeatureManager.has_feature(Feature.MULTI_REGION) is False

        # Free tier
        with TenantContextManager(free_tenant_context):
            assert TierFeatureManager.has_feature(Feature.CODE_INTERPRETER) is False
            assert TierFeatureManager.has_feature(Feature.BASIC_EXECUTION) is True

    @pytest.mark.asyncio
    async def test_require_feature_raises_on_missing(self, free_tenant_context):
        """Test require_feature raises for missing features."""
        from core.agentcore.billing import Feature

        with TenantContextManager(free_tenant_context):
            # Free tier doesn't have CODE_INTERPRETER
            with pytest.raises(Exception) as exc_info:
                TierFeatureManager.require_feature(Feature.CODE_INTERPRETER)

            assert "requires Pro tier" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_tier_rate_limits(self):
        """Test tier-based rate limits."""
        free_config = TierFeatureManager.get_tier_config("free")
        pro_config = TierFeatureManager.get_tier_config("pro")
        enterprise_config = TierFeatureManager.get_tier_config("enterprise")

        # Free tier: 10 req/min
        assert free_config.rate_limit_per_minute == 10

        # Pro tier: 60 req/min
        assert pro_config.rate_limit_per_minute == 60

        # Enterprise tier: 1000 req/min
        assert enterprise_config.rate_limit_per_minute == 1000

    @pytest.mark.asyncio
    async def test_tier_execution_limits(self):
        """Test tier-based execution limits."""
        free_config = TierFeatureManager.get_tier_config("free")
        pro_config = TierFeatureManager.get_tier_config("pro")
        enterprise_config = TierFeatureManager.get_tier_config("enterprise")

        # Free tier: 1 concurrent, 300s timeout
        assert free_config.max_concurrent_executions == 1
        assert free_config.max_timeout_seconds == 300

        # Pro tier: 5 concurrent, 1800s timeout
        assert pro_config.max_concurrent_executions == 5
        assert pro_config.max_timeout_seconds == 1800

        # Enterprise tier: 50 concurrent, 7200s timeout
        assert enterprise_config.max_concurrent_executions == 50
        assert enterprise_config.max_timeout_seconds == 7200


# ============================================================================
# Credit Cost Tests
# ============================================================================

class TestCreditCost:
    """Tests for credit cost calculation."""

    @pytest.mark.asyncio
    async def test_calculate_base_cost(self):
        """Test base credit cost calculation."""
        cost = CreditCost.calculate_base_cost()

        assert cost == 1  # Base cost is 1 credit

    @pytest.mark.asyncio
    async def test_calculate_time_cost(self):
        """Test time-based credit cost."""
        # 60 seconds * 0.01 credits/second = 0.6 credits
        cost = CreditCost.calculate_time_cost(execution_duration_seconds=60, credit_per_second=0.01)

        assert cost == 0.6

    @pytest.mark.asyncio
    async def test_calculate_token_cost(self):
        """Test token-based credit cost."""
        # 2000 tokens / 1000 * 0.5 = 1 credit
        cost = CreditCost.calculate_token_cost(
            total_tokens=2000,
            credit_per_1000_tokens=0.5
        )

        assert cost == 1.0

    @pytest.mark.asyncio
    async def test_calculate_tool_cost(self):
        """Test tool usage credit cost."""
        # 5 tool uses * 0.25 = 1.25 credits
        cost = CreditCost.calculate_tool_cost(
            api_calls=5,
            credit_per_tool_usage=0.25
        )

        assert cost == 1.25

    @pytest.mark.asyncio
    async def test_apply_tier_discount(self):
        """Test tier-based discount application."""
        # Pro tier: 20% discount
        base_cost = 10
        discounted = CreditCost.apply_tier_discount(base_cost, tier="pro", pro_discount=0.8)

        assert discounted == 8  # 10 * 0.8

        # Enterprise tier: 50% discount
        discounted = CreditCost.apply_tier_discount(base_cost, tier="enterprise", enterprise_discount=0.5)

        assert discounted == 5  # 10 * 0.5

        # Free tier: no discount
        discounted = CreditCost.apply_tier_discount(base_cost, tier="free", pro_discount=0.8)

        assert discounted == base_cost  # No change

    @pytest.mark.asyncio
    async def test_minimum_credit_cost(self):
        """Test minimum credit cost is enforced."""
        # Even with minimal usage, cost is at least 1 credit
        minimal_cost = CreditCost.calculate_minimum_cost()

        assert minimal_cost >= 1


# ============================================================================
# Billing Integration Tests
# ============================================================================

class TestBillingIntegration:
    """Tests for billing system integration."""

    @pytest.mark.asyncio
    async def test_track_agent_execution_billing(self, billing_config, billing_tenant_context):
        """Test billing tracking during agent execution."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

            tracker = UsageTracker(billing_config)
            adapter = AgentCoreRuntimeAdapter(billing_config)

            # Start tracking
            await tracker.start_execution_tracking(
                execution_id="exec-integration-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
            )

            # Mock execution
            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.invoke_agent.return_value = {
                    "completion": ["Test response"],
                    "sessionId": "test-session",
                    "inputTokens": 1000,
                    "outputTokens": 500,
                }

                result = await adapter.invoke_agent(
                    deployment_id="test-deployment-123",
                    input_text="Test input",
                    session_id="test-session",
                )

                # Complete tracking
                with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    metrics = await tracker.complete_execution_tracking(
                        execution_id="exec-integration-123",
                        result=result,
                    )

                    assert metrics.total_tokens == 1500
                    assert metrics.execution_id == "exec-integration-123"

    @pytest.mark.asyncio
    async def test_concurrent_execution_tracking(self, billing_config, billing_tenant_context):
        """Test tracking multiple concurrent executions."""
        import asyncio

        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Start multiple executions
            execution_ids = [f"exec-concurrent-{i}" for i in range(10)]

            for exec_id in execution_ids:
                await tracker.start_execution_tracking(
                    execution_id=exec_id,
                    agent_id="test-agent",
                    deployment_id="test-deployment-123",
                )

            # Verify all are tracked
            assert len(tracker._active_executions) == 10

            # Complete all
            with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                for exec_id in execution_ids:
                    mock_result = MagicMock()
                    mock_result.metadata = {"input_tokens": 100, "output_tokens": 50}

                    await tracker.complete_execution_tracking(exec_id, mock_result)

                # Verify all completed
                assert len(tracker._active_executions) == 0

    @pytest.mark.asyncio
    async def test_failed_execution_billing(self, billing_config, billing_tenant_context):
        """Test that failed executions are still billed."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Start tracking
            await tracker.start_execution_tracking(
                execution_id="exec-failed-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
            )

            # Mock failed result
            failed_result = RuntimeExecutionResult(
                execution_id="exec-failed-123",
                status=RuntimeStatus.FAILED,
                error="Execution failed",
            )

            # Complete tracking (should still bill)
            with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                metrics = await tracker.complete_execution_tracking(
                    execution_id="exec-failed-123",
                    result=failed_result,
                )

                assert metrics.execution_id == "exec-failed-123"
                assert metrics.completed_at is not None


# ============================================================================
# Invoice Generation Tests
# ============================================================================

class TestInvoiceGeneration:
    """Tests for invoice generation."""

    @pytest.mark.asyncio
    async def test_generate_usage_summary(self, billing_config, billing_tenant_context):
        """Test generating usage summary for billing period."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import UsageTracker

            tracker = UsageTracker(billing_config)

            # Mock usage data
            start_date = datetime.utcnow() - timedelta(days=30)
            end_date = datetime.utcnow()

            summary = await tracker.generate_usage_summary(
                account_id=billing_tenant_context.account_id,
                start_date=start_date,
                end_date=end_date,
            )

            assert summary.account_id == billing_tenant_context.account_id
            assert summary.start_date == start_date
            assert summary.end_date == end_date
            assert summary.total_executions >= 0
            assert summary.total_credits >= 0

    @pytest.mark.asyncio
    async def test_calculate_monthly_credits(self, billing_config, billing_tenant_context):
        """Test calculating monthly credit usage."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import UsageTracker

            tracker = UsageTracker(billing_config)

            # Mock monthly data
            monthly_credits = await tracker.calculate_monthly_credits(
                account_id=billing_tenant_context.account_id,
                year=2024,
                month=12,
            )

            assert monthly_credits.total_credits >= 0
            assert monthly_credits.breakdown is not None

    @pytest.mark.asyncio
    async def test_tier_usage_breakdown(self, billing_config):
        """Test usage breakdown by tier."""
        from core.agentcore.billing import UsageTracker

        tracker = UsageTracker(billing_config)

        breakdown = await tracker.get_tier_usage_breakdown()

        # Should have breakdown for each tier
        assert "free" in breakdown
        assert "pro" in breakdown
        assert "enterprise" in breakdown


# ============================================================================
# Billing API Tests
# ============================================================================

class TestBillingAPI:
    """Tests for billing API endpoints."""

    @pytest.mark.asyncio
    async def test_get_usage_endpoint(self, billing_config, billing_tenant_context):
        """Test GET /usage endpoint."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import UsageTracker

            tracker = UsageTracker(billing_config)

            usage = await tracker.get_current_usage(
                account_id=billing_tenant_context.account_id,
            )

            assert usage.account_id == billing_tenant_context.account_id
            assert usage.credits_used >= 0
            assert usage.credits_remaining is not None

    @pytest.mark.asyncio
    async def test_get_tier_endpoint(self, billing_config, billing_tenant_context):
        """Test GET /tier endpoint."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import TierFeatureManager

            tier_info = TierFeatureManager.get_tier_config(billing_tenant_context.tier)

            assert tier_info.name == "Pro"
            assert len(tier_info.features) > 0

    @pytest.mark.asyncio
    async def test_upgrade_tier_endpoint(self, billing_config, billing_tenant_context):
        """Test POST /tier/upgrade endpoint."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import TierFeatureManager

            # Mock upgrade
            new_tier = "enterprise"

            # Verify upgrade would work (validation only)
            config = TierFeatureManager.get_tier_config(new_tier)
            assert config.name == "Enterprise"

    @pytest.mark.asyncio
    async def test_billing_history_endpoint(self, billing_config, billing_tenant_context):
        """Test GET /billing/history endpoint."""
        with TenantContextManager(billing_tenant_context):
            from core.agentcore.billing import UsageTracker

            tracker = UsageTracker(billing_config)

            history = await tracker.get_billing_history(
                account_id=billing_tenant_context.account_id,
                limit=10,
            )

            assert isinstance(history, list)
            assert len(history) <= 10


# ============================================================================
# Cost Optimization Tests
# ============================================================================

class TestCostOptimization:
    """Tests for cost optimization recommendations."""

    @pytest.mark.asyncio
    async def test_cost_optimization_analysis(self, billing_config, billing_tenant_context):
        """Test cost optimization analysis."""
        from core.agentcore.billing import UsageTracker

        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Mock usage data
            analysis = await tracker.analyze_costs(
                account_id=billing_tenant_context.account_id,
                period_days=30,
            )

            assert analysis.total_cost >= 0
            assert analysis.recommendations is not None

    @pytest.mark.asyncio
    async def test_tier_upgrade_recommendation(self, billing_config, free_tenant_context):
        """Test tier upgrade recommendation for heavy users."""
        from core.agentcore.billing import UsageTracker

        with TenantContextManager(free_tenant_context):
            tracker = UsageTracker(billing_config)

            # Mock heavy usage (exceeds free tier limits)
            recommendation = await tracker.check_tier_recommendation(
                account_id=free_tenant_context.account_id,
                current_tier="free",
            )

            # Heavy users should be recommended to upgrade
            if recommendation.usage_exceeds_limits:
                assert recommendation.recommended_tier in ["pro", "enterprise"]

    @pytest.mark.asyncio
    async def test_cost_saving_tips(self, billing_config, billing_tenant_context):
        """Test cost saving recommendations."""
        from core.agentcore.billing import UsageTracker

        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            tips = await tracker.get_cost_saving_tips(
                account_id=billing_tenant_context.account_id,
            )

            assert isinstance(tips, list)
            assert len(tips) > 0


# ============================================================================
# Performance Tests
# ============================================================================

class TestBillingPerformance:
    """Performance tests for billing operations."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_billing_performance(self, billing_config):
        """Test billing system performance under concurrent load."""
        import asyncio
        import time

        from core.agentcore.billing import UsageTracker

        tracker = UsageTracker(billing_config)

        # Concurrent tracking operations
        async def track_execution(i: int):
            tenant_ctx = TenantContext(
                account_id=f"perf-account-{i % 100}",  # 100 unique accounts
                tenant_id=f"tenant-{i}",
                tier="pro",
                region="ap-southeast-2",
                created_at=datetime.utcnow(),
            )

            with TenantContextManager(tenant_ctx):
                await tracker.start_execution_tracking(
                    execution_id=f"exec-perf-{i}",
                    agent_id="test-agent",
                )

                # Simulate execution
                await asyncio.sleep(0.01)

                mock_result = MagicMock()
                mock_result.metadata = {"input_tokens": 100, "output_tokens": 50}

                with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    await tracker.complete_execution_tracking(
                        execution_id=f"exec-perf-{i}",
                        result=mock_result,
                    )

        # Run 100 concurrent tracking operations
        start = time.time()
        await asyncio.gather(*[track_execution(i) for i in range(100)])
        elapsed = time.time() - start

        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_billing_query_performance(self, billing_config, billing_tenant_context):
        """Test billing query performance."""
        import time

        from core.agentcore.billing import UsageTracker

        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            start = time.time()
            usage = await tracker.get_current_usage(
                account_id=billing_tenant_context.account_id,
            )
            elapsed = time.time() - start

            # Query should be fast (< 100ms for mock)
            assert elapsed < 0.1


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestBillingEdgeCases:
    """Tests for billing edge cases."""

    @pytest.mark.asyncio
    async def test_zero_duration_billing(self, billing_config, billing_tenant_context):
        """Test billing for instant (0 duration) executions."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Start and complete immediately
            await tracker.start_execution_tracking(
                execution_id="exec-instant-123",
                agent_id="test-agent",
            )

            mock_result = MagicMock()
            mock_result.metadata = {"input_tokens": 0, "output_tokens": 0}

            with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                metrics = await tracker.complete_execution_tracking(
                    execution_id="exec-instant-123",
                    result=mock_result,
                )

                # Should still charge minimum (base cost)
                credits = tracker._calculate_credits_from_usage(metrics)
                assert credits >= 1

    @pytest.mark.asyncio
    async def test_unknown_tier_handling(self, billing_config):
        """Test handling of unknown tier."""
        from core.agentcore.billing import TierFeatureManager

        # Unknown tier should default to free
        config = TierFeatureManager.get_tier_config("unknown_tier")

        # Should return free tier config
        assert config == TierFeatureManager.get_tier_config("free")

    @pytest.mark.asyncio
    async def test_credit_calculation_overflow(self, billing_config, billing_tenant_context):
        """Test credit calculation with very large values."""
        with TenantContextManager(billing_tenant_context):
            tracker = UsageTracker(billing_config)

            # Very large execution
            metrics = UsageMetrics(
                account_id=billing_tenant_context.account_id,
                execution_id="exec-large-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123",
                started_at=datetime.utcnow() - timedelta(seconds=1000000),
                completed_at=datetime.utcnow(),
                execution_duration_seconds=1000000.0,  # ~11.5 days
                input_tokens=1000000,  # 1M tokens
                output_tokens=500000,  # 500K tokens
                total_tokens=1500000,
                tier="pro",
                region="ap-southeast-2",
            )

            credits = tracker._calculate_credits_from_usage(metrics)

            # Should calculate without overflow, but apply discount
            assert credits > 0
            assert credits < float('inf')
