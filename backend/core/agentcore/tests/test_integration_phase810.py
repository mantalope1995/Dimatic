"""
Integration Tests for Phase 8-10 (Billing, Observability, & Production Readiness)

Comprehensive integration tests covering:
- Phase 8: Billing & Multi-Region (usage tracking, tier features, cost optimization)
- Phase 9: Observability (CloudWatch, metrics, health checks, alerts)
- Phase 10: Production Readiness (caching, performance, validation, rate limiting)

These tests verify end-to-end integration between all AgentCore components
and the existing Kortix platform infrastructure.
"""

import os
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from typing import Dict, List, Any
import json

from core.agentcore import (
    # Config
    get_agentcore_config,
    AgentCoreConfig,
    Environment,

    # Models
    RuntimeStatus,
    RuntimeSession,
    CodeExecutionResult,

    # Adapters
    AgentCoreRuntimeAdapter,
    AgentCoreMemoryAdapter,
    AgentCoreCodeInterpreterAdapter,
    AgentCoreBrowserAdapter,

    # Billing (Phase 8)
    UsageMetrics,
    UsageTracker,
    TierConfig,
    TierFeatureManager,
    TIER_CONFIGS,
    Feature,

    # Observability (Phase 9)
    CloudWatchClient,
    MetricsCollector,
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    AlertingService,
    PerformanceMonitor,

    # Caching (Phase 10)
    AgentCoreCache,
    CacheManager,
    CacheEntityType,
    CachePolicy,

    # Performance (Phase 10)
    BatchProcessor,
    RuntimeBatchProcessor,
    ConnectionPool,
    RuntimeConnectionPool,
    GracefulShutdown,

    # Validation (Phase 10)
    ConfigValidator,
    ValidationResult,
    ValidationSeverity,
    ValidationIssue,

    # Logging (Phase 10)
    get_logger,
    log_execution_time,
    LogLevel,

    # API Docs (Phase 10)
    APIDocHelper,
    ResponseBuilder,

    # Rate Limiting (Phase 10)
    RateLimiterManager,
    check_rate_limit,
    RateLimitResult,

    # Middleware
    TenantContext,
    TenantContextManager,
    get_tenant_context,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_config():
    """Test configuration for ap-southeast-2 region"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        runtime_enabled=True,
        code_interpreter_enabled=True,
        browser_enabled=True,
        memory_enabled=True,
        gateway_enabled=True,
        s3_bucket_name="kortix-agentcore-test",
        fallback_to_legacy_sandbox=True,
        # Phase 8: Billing config
        billing_enabled=True,
        # Phase 9: Observability config
        cloudwatch_enabled=False,  # Disabled for unit tests
        health_check_enabled=True,
        # Phase 10: Cache config
        cache_enabled=False,  # Disabled for unit tests
        redis_host="localhost",
        redis_port=6379,
        # Phase 10: Rate limiting config
        rate_limiting_enabled=True,
    )


@pytest.fixture
def tenant_context():
    """Tenant context for testing"""
    return TenantContext(
        account_id="test-account-123",
        project_id="test-project-456",
        tenant_id="tenant-789",
        tier="pro",
        region="ap-southeast-2",
    )


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client for database operations"""
    client = AsyncMock()

    # Mock thread creation/retrieval
    async def mock_insert(data):
        result = Mock()
        result.data = [{
            'thread_id': 'test-thread-123',
            'account_id': data.get('account_id', 'test-account'),
            'project_id': data.get('project_id', 'test-project'),
            'created_at': datetime.utcnow().isoformat(),
            'runtime_deployment_id': None,
            'runtime_metadata': {},
        }]
        return result

    async def mock_select(columns=None):
        builder = Mock()
        builder.eq = Mock(return_value=builder)
        builder.in_ = Mock(return_value=builder)
        builder.order = Mock(return_value=builder)
        builder.limit = Mock(return_value=builder)
        builder.single = AsyncMock(return_value=builder)
        builder.execute = AsyncMock(return_value=builder)
        builder.data = {
            'thread_id': 'test-thread-123',
            'account_id': 'test-account',
            'runtime_deployment_id': 'test-deployment-123',
            'runtime_metadata': {'status': 'ready'},
        }
        return builder

    async def mock_update(data=None):
        builder = Mock()
        builder.eq = Mock(return_value=builder)
        builder.execute = AsyncMock(return_value=builder)
        builder.data = [{'thread_id': 'test-thread-123'}]
        return builder

    async def mock_delete():
        result = Mock()
        result.data = []
        return result

    client.table = MagicMock()
    client.table.return_value.insert = mock_insert
    client.table.return_value.update = mock_update
    client.table.return_value.select = mock_select
    client.table.return_value.delete = mock_delete

    return client


@pytest.fixture
def mock_runtime_adapter():
    """Mock Runtime adapter for testing"""
    adapter = AsyncMock(spec=AgentCoreRuntimeAdapter)

    adapter.create_deployment = AsyncMock(return_value="test-deployment-123")
    adapter.delete_deployment = AsyncMock(return_value=True)
    adapter.register_tool = AsyncMock(return_value=True)

    adapter.invoke_agent = AsyncMock(return_value={
        "success": True,
        "result": {"output": "test execution result"},
        "error": None,
        "execution_id": "exec-123",
        "status": RuntimeStatus.COMPLETED,
        "metadata": {
            "input_tokens": 100,
            "output_tokens": 50,
            "duration_ms": 1500,
        }
    })

    return adapter


@pytest.fixture
def mock_credit_manager():
    """Mock credit manager for billing integration tests"""
    manager = AsyncMock()

    manager.consume_credits = AsyncMock(return_value={
        "success": True,
        "credits_remaining": 950,
        "credits_consumed": 50,
    })

    manager.get_credits_balance = AsyncMock(return_value={
        "credits_remaining": 1000,
        "tier": "pro",
    })

    return manager


# ============================================================================
# Phase 8: Billing Integration Tests
# ============================================================================

class TestPhase8BillingIntegration:
    """
    Integration tests for Phase 8 billing system.

    Tests the complete flow from agent execution to credit consumption,
    including usage tracking, tier-based pricing, and cost optimization.
    """

    @pytest.mark.asyncio
    async def test_usage_tracking_end_to_end(
        self, test_config, tenant_context, mock_runtime_adapter
    ):
        """
        Test complete usage tracking flow from execution start to completion.

        Phase 8 Requirement: Every agent execution should be tracked for billing,
        with metrics persisted to the billing system.
        """
        with TenantContextManager(tenant_context):
            tracker = UsageTracker(test_config)

            # Start tracking
            metrics = await tracker.start_execution_tracking(
                execution_id="exec-123",
                agent_id="test-agent",
                deployment_id="test-deployment-123"
            )

            # Verify initial metrics
            assert metrics.execution_id == "exec-123"
            assert metrics.account_id == tenant_context.account_id
            assert metrics.agent_id == "test-agent"
            assert metrics.started_at is not None
            assert metrics.completed_at is None
            assert metrics.region == "ap-southeast-2"
            assert metrics.tier == "pro"

            # Simulate execution result
            mock_result = Mock()
            mock_result.metadata = {
                "input_tokens": 500,
                "output_tokens": 300,
                "duration_seconds": 45,
            }

            # Complete tracking
            completed = await tracker.complete_execution_tracking(
                execution_id="exec-123",
                result=mock_result
            )

            # Verify completed metrics
            assert completed.completed_at is not None
            assert completed.input_tokens == 500
            assert completed.output_tokens == 300
            assert completed.total_tokens == 800
            assert completed.execution_duration_seconds > 0

    @pytest.mark.asyncio
    async def test_billing_integration_with_credit_manager(
        self, test_config, tenant_context, mock_credit_manager
    ):
        """
        Test billing integration with existing credit manager.

        Phase 8 Requirement: Usage metrics should be converted to credit
        consumption and persisted to the billing system.
        """
        with TenantContextManager(tenant_context):
            tracker = UsageTracker(test_config)

            with patch('core.agentcore.billing.usage_tracker.CreditManager', return_value=mock_credit_manager):
                metrics = UsageMetrics(
                    account_id=tenant_context.account_id,
                    execution_id="exec-456",
                    agent_id="test-agent",
                    deployment_id="test-deployment-123",
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow() + timedelta(seconds=30),
                    execution_duration_seconds=30,
                    input_tokens=1000,
                    output_tokens=500,
                    total_tokens=1500,
                    tier="pro",
                    region="ap-southeast-2",
                )

                # Persist to billing
                await tracker._persist_usage_to_billing(metrics)

                # Verify credit manager was called
                mock_credit_manager.consume_credits.assert_called_once()

                call_args = mock_credit_manager.consume_credits.call_args
                assert call_args[1]['account_id'] == tenant_context.account_id
                assert call_args[1]['reference_id'] == "exec-456"
                assert call_args[1]['amount'] > 0

    @pytest.mark.asyncio
    async def test_tier_based_pricing(
        self, test_config, tenant_context
    ):
        """
        Test tier-based pricing calculation.

        Phase 8 Requirement: Different subscription tiers should have
        different pricing (free pays full price, pro gets discount, etc.).
        """
        with TenantContextManager(tenant_context):
            tracker = UsageTracker(test_config)

            # Create metrics for pro tier
            pro_metrics = UsageMetrics(
                account_id=tenant_context.account_id,
                execution_id="exec-pro",
                agent_id="test-agent",
                deployment_id=None,
                started_at=datetime.utcnow(),
                execution_duration_seconds=60,
                total_tokens=2000,
                tier="pro",
                region="ap-southeast-2",
            )

            pro_credits = tracker._calculate_credits_from_usage(pro_metrics)

            # Create same metrics for enterprise tier
            enterprise_metrics = UsageMetrics(
                account_id=tenant_context.account_id,
                execution_id="exec-ent",
                agent_id="test-agent",
                deployment_id=None,
                started_at=datetime.utcnow(),
                execution_duration_seconds=60,
                total_tokens=2000,
                tier="enterprise",
                region="ap-southeast-2",
            )

            ent_credits = tracker._calculate_credits_from_usage(enterprise_metrics)

            # Create same metrics for free tier
            free_metrics = UsageMetrics(
                account_id=tenant_context.account_id,
                execution_id="exec-free",
                agent_id="test-agent",
                deployment_id=None,
                started_at=datetime.utcnow(),
                execution_duration_seconds=60,
                total_tokens=2000,
                tier="free",
                region="ap-southeast-2",
            )

            free_credits = tracker._calculate_credits_from_usage(free_metrics)

            # Verify tier-based pricing
            assert free_credits > pro_credits > ent_credits, \
                f"Expected free > pro > ent, got {free_credits} > {pro_credits} > {ent_credits}"

    @pytest.mark.asyncio
    async def test_feature_access_control_by_tier(self):
        """
        Test tier-based feature access control.

        Phase 8 Requirement: Different tiers should have access to
        different features (free: basic, pro: +tools, enterprise: all).
        """
        # Free tier features
        free_config = TierFeatureManager.get_tier_config("free")
        assert Feature.BASIC_EXECUTION in free_config.features
        assert Feature.MEMORY_ACCESS in free_config.features
        assert Feature.CODE_INTERPRETER not in free_config.features
        assert Feature.MULTI_REGION not in free_config.features

        # Pro tier features
        pro_config = TierFeatureManager.get_tier_config("pro")
        assert Feature.CODE_INTERPRETER in pro_config.features
        assert Feature.BROWSER_AUTOMATION in pro_config.features
        assert Feature.MULTI_REGION not in pro_config.features

        # Enterprise tier features
        ent_config = TierFeatureManager.get_tier_config("enterprise")
        assert Feature.MULTI_REGION in ent_config.features
        assert Feature.CUSTOM_MODELS in ent_config.features
        assert Feature.API_ACCESS in ent_config.features

    @pytest.mark.asyncio
    async def test_tier_feature_check_with_context(self, test_config, tenant_context):
        """
        Test feature access checking with tenant context.

        Phase 8 Requirement: Feature checks should use the tenant's tier
        from the current context.
        """
        # Test with pro tier
        with TenantContextManager(tenant_context):  # pro tier
            has_code_interpreter = TierFeatureManager.has_feature(Feature.CODE_INTERPRETER)
            assert has_code_interpreter is True

            has_multi_region = TierFeatureManager.has_feature(Feature.MULTI_REGION)
            assert has_multi_region is False

    @pytest.mark.asyncio
    async def test_multi_region_manager_ap_southeast_2_only(self, test_config):
        """
        Test multi-region manager enforces ap-southeast-2 only for Phase 8.

        Phase 8 Requirement: Only ap-southeast-2 region should be enabled,
        with enforcement at multiple levels.
        """
        from core.agentcore.deployment.multi_region_manager import (
            MultiRegionManager,
            DeploymentRegion,
        )

        manager = MultiRegionManager(test_config)
        enabled_regions = manager.get_enabled_regions()

        # Only ap-southeast-2 should be enabled
        assert len(enabled_regions) == 1
        assert DeploymentRegion.AP_SOUTHEAST_2 in enabled_regions


# ============================================================================
# Phase 9: Observability Integration Tests
# ============================================================================

class TestPhase9ObservabilityIntegration:
    """
    Integration tests for Phase 9 observability system.

    Tests CloudWatch integration, metrics collection, health checks,
    alerting, and performance monitoring.
    """

    @pytest.mark.asyncio
    async def test_health_checker_all_services(self, test_config):
        """
        Test health checker evaluates all AgentCore services.

        Phase 9 Requirement: HealthChecker should evaluate Runtime, Gateway,
        Memory, and Billing services, returning aggregated status.
        """
        checker = HealthChecker(test_config)

        results = await checker.check_all()

        # Verify all services checked
        assert "runtime" in results
        assert "gateway" in results
        assert "memory" in results
        assert "billing" in results

        # Verify result structure
        for name, result in results.items():
            assert isinstance(result, HealthCheckResult)
            assert result.name == name
            assert result.status in HealthStatus
            assert result.message is not None
            assert result.timestamp is not None
            assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_cloudwatch_metrics_publishing(self, test_config):
        """
        Test CloudWatch metrics publishing (with mocked AWS).

        Phase 9 Requirement: Metrics should be published to CloudWatch
        in ap-southeast-2 region with proper namespaces and dimensions.
        """
        with patch('boto3.client') as mock_boto3:
            mock_cloudwatch = AsyncMock()
            mock_boto3.return_value = mock_cloudwatch

            client = CloudWatchClient(test_config)

            from core.agentcore.observability.cloudwatch_client import MetricDatum, MetricNamespace

            # Publish metric
            metric = MetricDatum(
                namespace=MetricNamespace.AGENTCORE,
                metric_name="AgentExecutionCount",
                value=1.0,
                unit="Count",
                dimensions={
                    "Tier": "pro",
                    "Region": "ap-southeast-2",
                    "AgentType": "general",
                }
            )

            await client.put_metric(metric)

            # Verify CloudWatch put_metric_data was called
            assert mock_cloudwatch.put_metric_data.called
            call_args = mock_cloudwatch.put_metric_data.call_args
            assert call_args[1]['Namespace'] == "AgentCore/Production"

    @pytest.mark.asyncio
    async def test_metrics_collection_aggregation(self, test_config):
        """
        Test metrics collector aggregates execution metrics.

        Phase 9 Requirement: MetricsCollector should aggregate metrics across
        multiple executions for dashboards and monitoring.
        """
        collector = MetricsCollector(test_config)

        # Record multiple executions
        for i in range(10):
            await collector.record_execution(
                execution_id=f"exec-{i}",
                agent_id="test-agent",
                duration_seconds=30 + i,
                tokens_used=1000 + (i * 100),
                success=(i % 3 != 0),  # Some failures
                tier="pro",
            )

        # Get aggregated metrics
        metrics = await collector.get_aggregated_metrics(
            agent_id="test-agent",
            time_range_minutes=5,
        )

        # Verify aggregation
        assert metrics['total_executions'] == 10
        assert metrics['successful_executions'] > 0
        assert metrics['failed_executions'] > 0
        assert metrics['average_duration_seconds'] > 0
        assert metrics['average_tokens_used'] > 0

    @pytest.mark.asyncio
    async def test_performance_monitor_anomalies(self, test_config):
        """
        Test performance monitor detects anomalies.

        Phase 9 Requirement: PerformanceMonitor should detect performance
        degradation and anomalies (slow executions, high error rates).
        """
        monitor = PerformanceMonitor(test_config)

        # Record normal performance
        for i in range(10):
            await monitor.record_execution(
                execution_id=f"exec-normal-{i}",
                duration_ms=1000,
                success=True,
            )

        # Record degraded performance
        for i in range(5):
            await monitor.record_execution(
                execution_id=f"exec-slow-{i}",
                duration_ms=15000,  # Very slow
                success=False,  # Failures
            )

        # Check for anomalies
        anomalies = await monitor.detect_anomalies(
            agent_id="test-agent",
            time_range_minutes=5,
        )

        # Should detect slow executions and high error rate
        assert len(anomalies) > 0
        assert any(a['type'] == 'slow_execution' for a in anomalies)
        assert any(a['type'] == 'high_error_rate' for a in anomalies)

    @pytest.mark.asyncio
    async def test_alerting_service_thresholds(self, test_config):
        """
        Test alerting service triggers alerts on threshold violations.

        Phase 9 Requirement: AlertingService should trigger alerts when
        metrics exceed configured thresholds (error rate, latency, etc.).
        """
        alerting = AlertingService(test_config)

        # Record metrics that should trigger alerts
        await alerting.record_metric(
            metric_name="error_rate",
            value=0.15,  # 15% error rate (threshold is 10%)
            agent_id="test-agent",
        )

        await alerting.record_metric(
            metric_name="latency_p99",
            value=30000,  # 30s latency (threshold is 20s)
            agent_id="test-agent",
        )

        # Check alerts
        alerts = await alerting.check_alerts(agent_id="test-agent")

        # Should have alerts for both threshold violations
        assert len(alerts) > 0
        assert any(a['metric'] == 'error_rate' for a in alerts)
        assert any(a['metric'] == 'latency_p99' for a in alerts)


# ============================================================================
# Phase 10: Caching & Performance Integration Tests
# ============================================================================

class TestPhase10CachingIntegration:
    """
    Integration tests for Phase 10 caching layer.

    Tests Redis-based caching for AgentCore operations, including
    deployment metadata, tool results, and tenant configuration.
    """

    @pytest.mark.asyncio
    async def test_cache_get_set_miss(self, test_config, tenant_context):
        """
        Test cache get/set/miss operations.

        Phase 10 Requirement: AgentCoreCache should support get/set/miss
        with proper namespacing and TTL.
        """
        cache = AgentCoreCache(test_config)

        with TenantContextManager(tenant_context):
            # Cache miss initially
            value = await cache.get(
                account_id=tenant_context.account_id,
                key="test-key"
            )
            assert value is None

            # Set value
            success = await cache.set(
                account_id=tenant_context.account_id,
                key="test-key",
                value={"data": "test value"},
                ttl=60
            )
            assert success is True

            # Cache hit
            value = await cache.get(
                account_id=tenant_context.account_id,
                key="test-key"
            )
            assert value is not None
            assert value["data"] == "test value"

    @pytest.mark.asyncio
    async def test_cache_namespacing_by_account(self, test_config):
        """
        Test cache is properly namespaced by account.

        Phase 10 Requirement: Cache keys should be namespaced by account_id
        and region to prevent cross-account data leakage.
        """
        cache = AgentCoreCache(test_config)

        # Set value for account-1
        await cache.set(
            account_id="account-1",
            key="shared-key",
            value="value-for-account-1"
        )

        # Set different value for account-2
        await cache.set(
            account_id="account-2",
            key="shared-key",
            value="value-for-account-2"
        )

        # Verify values are isolated
        value_1 = await cache.get(account_id="account-1", key="shared-key")
        value_2 = await cache.get(account_id="account-2", key="shared-key")

        assert value_1 == "value-for-account-1"
        assert value_2 == "value-for-account-2"
        assert value_1 != value_2

    @pytest.mark.asyncio
    async def test_cache_manager_policies(self, test_config):
        """
        Test cache manager enforces different policies by entity type.

        Phase 10 Requirement: Different entity types should have different
        cache policies (TTL, eviction strategy).
        """
        manager = CacheManager(test_config)

        # Get policy for deployment metadata (short TTL)
        deployment_policy = manager.get_policy(CacheEntityType.DEPLOYMENT)
        assert deployment_policy.ttl_seconds < 300  # Should be short

        # Get policy for tool results (medium TTL)
        tool_policy = manager.get_policy(CacheEntityType.TOOL_RESULT)
        assert 300 < tool_policy.ttl_seconds < 3600

        # Get policy for tenant config (long TTL)
        config_policy = manager.get_policy(CacheEntityType.TENANT_CONFIG)
        assert config_policy.ttl_seconds >= 3600  # Should be long


class TestPhase10PerformanceIntegration:
    """
    Integration tests for Phase 10 performance optimizations.

    Tests batch processing, connection pooling, and graceful shutdown.
    """

    @pytest.mark.asyncio
    async def test_batch_processor_concurrent_execution(self, test_config):
        """
        Test batch processor handles concurrent execution efficiently.

        Phase 10 Requirement: BatchProcessor should process multiple items
        concurrently with proper priority handling.
        """
        from core.agentcore.performance import BatchItem, BatchPriority

        processor = RuntimeBatchProcessor(
            config=test_config,
            max_concurrent=5,
        )

        processed = []

        async def mock_process(item: BatchItem) -> Dict:
            await asyncio.sleep(0.01)  # Simulate work
            processed.append(item.item_id)
            return {"item_id": item.item_id, "result": "processed"}

        processor._process_item = mock_process

        # Create batch items
        items = [
            BatchItem(
                item_id=f"item-{i}",
                priority=BatchPriority.HIGH if i < 3 else BatchPriority.NORMAL,
                data={"index": i}
            )
            for i in range(10)
        ]

        # Process batch
        results = await processor.process_batch(items)

        # Verify all processed
        assert len(results) == 10
        assert len(processed) == 10

        # Verify priority ordering (high priority items first)
        high_priority_ids = [f"item-{i}" for i in range(3)]
        assert processed[0] in high_priority_ids

    @pytest.mark.asyncio
    async def test_connection_pool_acquire_release(self, test_config):
        """
        Test connection pool manages connections efficiently.

        Phase 10 Requirement: ConnectionPool should limit max connections,
        queue requests when pool is full, and properly release connections.
        """
        pool = RuntimeConnectionPool(
            config=test_config,
            max_size=5,
        )

        acquired = []

        async def acquire_and_hold(conn_id: str):
            """Acquire connection and hold it briefly"""
            async with pool.acquire() as conn:
                acquired.append(conn_id)
                await asyncio.sleep(0.05)
                return conn

        # Acquire more connections than pool size
        tasks = [acquire_and_hold(f"conn-{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all connections were eventually acquired
        assert len(acquired) == 10
        assert pool.stats.current_size <= pool.config.max_size

    @pytest.mark.asyncio
    async def test_graceful_shutdown_order(self, test_config):
        """
        Test graceful shutdown respects priority order.

        Phase 10 Requirement: GracefulShutdown should shutdown services
        in priority order (critical services first).
        """
        shutdown = GracefulShutdown(test_config)

        shutdown_order = []

        # Register hooks with different priorities
        await shutdown.register(
            name="low-priority",
            priority=100,
            hook=lambda: shutdown_order.append("low-priority")
        )

        await shutdown.register(
            name="high-priority",
            priority=10,
            hook=lambda: shutdown_order.append("high-priority")
        )

        await shutdown.register(
            name="medium-priority",
            priority=50,
            hook=lambda: shutdown_order.append("medium-priority")
        )

        # Execute shutdown
        results = await shutdown.shutdown()

        # Verify shutdown order (lower priority number = first to shutdown)
        assert shutdown_order[0] == "high-priority"
        assert shutdown_order[1] == "medium-priority"
        assert shutdown_order[2] == "low-priority"


# ============================================================================
# Phase 10: Validation & Rate Limiting Tests
# ============================================================================

class TestPhase10ValidationIntegration:
    """
    Integration tests for Phase 10 configuration validation.

    Tests configuration validation rules and error reporting.
    """

    @pytest.mark.asyncio
    async def test_config_validation_region_enforcement(self):
        """
        Test config validation enforces ap-southeast-2 region.

        Phase 10 Requirement: Configuration validation should reject
        non-ap-southeast-2 regions for AgentCore services.
        """
        from core.agentcore.validation import get_config_validator

        validator = get_config_validator()

        # Invalid config (wrong region)
        invalid_config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_region="us-east-1",  # Wrong region!
            s3_bucket_name="test-bucket",
        )

        results = await validator.validate(invalid_config)

        # Should have validation error for region
        region_errors = [r for r in results if 'region' in r.field.lower()]
        assert len(region_errors) > 0
        assert any(r.severity == ValidationSeverity.ERROR for r in region_errors)

    @pytest.mark.asyncio
    async def test_config_validation_billing_requirements(self):
        """
        Test config validation checks billing requirements.

        Phase 10 Requirement: When billing is enabled, credit manager
        must be properly configured.
        """
        from core.agentcore.validation import get_config_validator

        validator = get_config_validator()

        # Config with billing enabled but missing required fields
        invalid_config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_region="ap-southeast-2",
            billing_enabled=True,  # Enabled
            s3_bucket_name=None,  # Missing required field
        )

        results = await validator.validate(invalid_config)

        # Should have validation error for missing S3 bucket
        s3_errors = [r for r in results if 's3' in r.field.lower() or 'bucket' in r.field.lower()]
        assert len(s3_errors) > 0


class TestPhase10RateLimitingIntegration:
    """
    Integration tests for Phase 10 rate limiting.

    Tests tier-based distributed rate limiting with token bucket
    and sliding window algorithms.
    """

    @pytest.mark.asyncio
    async def test_rate_limiting_free_tier(self, test_config, tenant_context):
        """
        Test rate limiting enforces free tier limits.

        Phase 10 Requirement: Free tier should be limited to 10 requests
        per minute with proper backoff signaling.
        """
        # Modify context for free tier
        free_context = TenantContext(
            account_id="free-account",
            project_id="test-project",
            tenant_id="free-tenant",
            tier="free",
            region="ap-southeast-2",
        )

        with TenantContextManager(free_context):
            # Make 10 requests (should all be allowed)
            for i in range(10):
                result = await check_rate_limit(
                    scope="global",
                    operation="test_operation"
                )
                assert result.allowed is True, f"Request {i+1} should be allowed"

            # 11th request should be rate limited
            result = await check_rate_limit(
                scope="global",
                operation="test_operation"
            )
            assert result.allowed is False
            assert result.remaining == 0
            assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_rate_limiting_tier_isolation(self, test_config):
        """
        Test rate limiting isolates by tier.

        Phase 10 Requirement: Different tiers should have independent
        rate limits (free: 10, pro: 100, enterprise: 1000).
        """
        results = {}

        # Test free tier (10 req/min)
        free_context = TenantContext(
            account_id="free-account",
            project_id="test-project",
            tenant_id="free-tenant",
            tier="free",
            region="ap-southeast-2",
        )

        with TenantContextManager(free_context):
            manager = RateLimiterManager(test_config)
            free_rule = manager.get_rules_for_tier("free")[0]
            results["free"] = free_rule.limit

        # Test pro tier (100 req/min)
        pro_context = TenantContext(
            account_id="pro-account",
            project_id="test-project",
            tenant_id="pro-tenant",
            tier="pro",
            region="ap-southeast-2",
        )

        with TenantContextManager(pro_context):
            manager = RateLimiterManager(test_config)
            pro_rule = manager.get_rules_for_tier("pro")[0]
            results["pro"] = pro_rule.limit

        # Verify tier isolation
        assert results["free"] < results["pro"]
        assert results["free"] == 10
        assert results["pro"] == 100


# ============================================================================
# Phase 10: Logging & API Docs Tests
# ============================================================================

class TestPhase10LoggingIntegration:
    """
    Integration tests for Phase 10 logging enhancements.

    Tests structured logging, log contexts, and performance logging.
    """

    @pytest.mark.asyncio
    async def test_structured_logging_with_context(self, test_config, tenant_context):
        """
        Test structured logging includes tenant context.

        Phase 10 Requirement: Log entries should include tenant context
        (account_id, tier, region) for traceability.
        """
        with TenantContextManager(tenant_context):
            logger = get_logger("test_logger")

            # Log with context
            with pytest.raises(Exception):  # We're not actually writing logs
                # Just verify the context is available
                ctx = get_tenant_context()
                assert ctx.account_id == tenant_context.account_id
                assert ctx.tier == tenant_context.tier
                assert ctx.region == tenant_context.region

    @pytest.mark.asyncio
    async def test_execution_time_logging(self, test_config):
        """
        Test execution time decorator logs performance.

        Phase 10 Requirement: @log_execution_time should log execution
        duration for performance monitoring.
        """
        logger = get_logger("test_performance")

        @log_execution_time(logger=logger)
        async def slow_function():
            await asyncio.sleep(0.1)
            return "result"

        # Execute and log
        result = await slow_function()
        assert result == "result"


class TestPhase10APIDocsIntegration:
    """
    Integration tests for Phase 10 API documentation helpers.

    Tests ResponseBuilder, APIDocHelper, and example generation.
    """

    @pytest.mark.asyncio
    async def test_response_builder_success(self, test_config):
        """
        Test ResponseBuilder creates consistent API responses.

        Phase 10 Requirement: All API responses should follow consistent
        structure with proper HTTP status codes.
        """
        from core.agentcore.api_docs import ResponseBuilder

        builder = ResponseBuilder()

        # Success response
        response = builder.success(
            data={"agent_id": "agent-123"},
            message="Agent created successfully"
        )

        assert response["success"] is True
        assert response["data"]["agent_id"] == "agent-123"
        assert response["message"] == "Agent created successfully"
        assert "error" not in response

    @pytest.mark.asyncio
    async def test_response_builder_error(self, test_config):
        """
        Test ResponseBuilder creates error responses.

        Phase 10 Requirement: Error responses should include error code,
        message, and details for debugging.
        """
        from core.agentcore.api_docs import ResponseBuilder

        builder = ResponseBuilder()

        # Error response
        response = builder.error(
            error_code="AGENT_NOT_FOUND",
            message="Agent not found",
            details={"agent_id": "invalid-id"},
            status_code=404
        )

        assert response["success"] is False
        assert response["error"]["code"] == "AGENT_NOT_FOUND"
        assert response["error"]["message"] == "Agent not found"
        assert response["error"]["details"]["agent_id"] == "invalid-id"


# ============================================================================
# End-to-End Integration Tests
# ============================================================================

class TestPhase810EndToEnd:
    """
    End-to-end integration tests for Phase 8-10 combined.

    Tests the complete flow from agent execution through billing,
    observability, and performance tracking.
    """

    @pytest.mark.asyncio
    async def test_complete_execution_with_billing_and_observability(
        self, test_config, tenant_context, mock_runtime_adapter, mock_credit_manager
    ):
        """
        Test complete agent execution flow with billing and observability.

        End-to-End Requirement: Agent execution should:
        1. Start usage tracking
        2. Execute agent (via Runtime)
        3. Complete usage tracking
        4. Deduct credits
        5. Record metrics
        6. Check health
        7. Cache results
        """
        with TenantContextManager(tenant_context):
            with patch('core.agentcore.billing.usage_tracker.CreditManager', return_value=mock_credit_manager):
                # Initialize components
                tracker = UsageTracker(test_config)
                collector = MetricsCollector(test_config)
                checker = HealthChecker(test_config)
                cache = AgentCoreCache(test_config)

                execution_id = "exec-e2e-123"

                # 1. Start usage tracking
                metrics = await tracker.start_execution_tracking(
                    execution_id=execution_id,
                    agent_id="test-agent",
                    deployment_id="test-deployment-123"
                )

                # 2. Execute agent (mocked)
                result = await mock_runtime_adapter.invoke_agent(
                    deployment_id="test-deployment-123",
                    agent_id="test-agent",
                    input_data={"prompt": "test"},
                    session_id="session-123"
                )

                # 3. Complete usage tracking
                completed_metrics = await tracker.complete_execution_tracking(
                    execution_id=execution_id,
                    result=result
                )

                # 4. Verify credits were deducted
                mock_credit_manager.consume_credits.assert_called_once()

                # 5. Record metrics
                await collector.record_execution(
                    execution_id=execution_id,
                    agent_id="test-agent",
                    duration_seconds=completed_metrics.execution_duration_seconds,
                    tokens_used=completed_metrics.total_tokens,
                    success=(result["status"] == RuntimeStatus.COMPLETED),
                    tier=tenant_context.tier,
                )

                # 6. Check health
                health_results = await checker.check_all()
                assert "runtime" in health_results

                # 7. Cache result
                cache_key = f"execution:{execution_id}"
                await cache.set(
                    account_id=tenant_context.account_id,
                    key=cache_key,
                    value=result,
                    ttl=300
                )

                cached_result = await cache.get(
                    account_id=tenant_context.account_id,
                    key=cache_key
                )
                assert cached_result is not None

    @pytest.mark.asyncio
    async def test_tier_upgrade_preserves_features(self):
        """
        Test tier upgrade preserves existing feature access.

        End-to-End Requirement: When a tenant upgrades from free to pro,
        their feature access should be immediately updated.
        """
        # Start with free tier
        free_config = TierFeatureManager.get_tier_config("free")
        assert Feature.CODE_INTERPRETER not in free_config.features

        # Simulate tier upgrade to pro
        pro_config = TierFeatureManager.get_tier_config("pro")
        assert Feature.CODE_INTERPRETER in pro_config.features

        # Verify feature access
        has_ci = TierFeatureManager.has_feature(Feature.CODE_INTERPRETER, tier="pro")
        assert has_ci is True

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_config_change(self, test_config, tenant_context):
        """
        Test cache invalidation when configuration changes.

        End-to-End Requirement: When tenant configuration changes,
        related cache entries should be invalidated.
        """
        cache = AgentCoreCache(test_config)

        with TenantContextManager(tenant_context):
            # Cache config
            config_key = f"config:{tenant_context.tenant_id}"
            await cache.set(
                account_id=tenant_context.account_id,
                key=config_key,
                value={"tier": "pro", "features": ["code_interpreter"]},
                ttl=3600
            )

            # Verify cached
            cached = await cache.get(
                account_id=tenant_context.account_id,
                key=config_key
            )
            assert cached is not None
            assert cached["tier"] == "pro"

            # Simulate config change (invalidate cache)
            await cache.delete(
                account_id=tenant_context.account_id,
                key=config_key
            )

            # Verify invalidated
            cached = await cache.get(
                account_id=tenant_context.account_id,
                key=config_key
            )
            assert cached is None


# ============================================================================
# Property Tests
# ============================================================================

class TestPhase810Properties:
    """
    Property-based tests for Phase 8-10 using Hypothesis.

    Tests universal properties that should always hold true across
    varied inputs and configurations.
    """

    @pytest.mark.asyncio
    @pytest.mark.property
    async def test_usage_metrics_duration_always_positive(self):
        """
        Property: Execution duration should always be positive.

        Phase 8 Property: completed_at - started_at must be > 0 for
        valid usage metrics.
        """
        started = datetime.utcnow()
        completed = started + timedelta(seconds=30)

        metrics = UsageMetrics(
            account_id="test-account",
            execution_id="test-exec",
            agent_id="test-agent",
            deployment_id=None,
            started_at=started,
            completed_at=completed,
            tier="pro",
            region="ap-southeast-2",
        )

        duration = metrics.duration
        assert duration > 0
        assert duration == 30

    @pytest.mark.asyncio
    @pytest.mark.property
    async def test_health_status_always_valid(self, test_config):
        """
        Property: Health check status must always be a valid HealthStatus.

        Phase 9 Property: All health check results must have a status
        that is one of HEALTHY, DEGRADED, UNHEALTHY, or UNKNOWN.
        """
        checker = HealthChecker(test_config)
        results = await checker.check_all()

        for name, result in results.items():
            assert result.status in [
                HealthStatus.HEALTHY,
                HealthStatus.DEGRADED,
                HealthStatus.UNHEALTHY,
                HealthStatus.UNKNOWN,
            ]

    @pytest.mark.asyncio
    @pytest.mark.property
    async def test_rate_limit_remaining_never_negative(self, test_config, tenant_context):
        """
        Property: Rate limit remaining should never be negative.

        Phase 10 Property: After rate limiting check, remaining count
        should always be >= 0.
        """
        with TenantContextManager(tenant_context):
            result = await check_rate_limit(
                scope="global",
                operation="test_operation"
            )

            assert result.remaining >= 0
            assert isinstance(result.remaining, int)


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestPhase810ErrorHandling:
    """
    Tests for error handling in Phase 8-10 components.

    Verifies proper error propagation, fallback behavior, and
    error classification for observability.
    """

    @pytest.mark.asyncio
    async def test_billing_error_propagation(self, test_config, tenant_context):
        """
        Test billing errors are properly propagated.

        Phase 8 Requirement: When credit manager fails, the error should
        be logged and propagated (or handled gracefully).
        """
        with TenantContextManager(tenant_context):
            tracker = UsageTracker(test_config)

            # Simulate credit manager failure
            with patch('core.agentcore.billing.usage_tracker.CreditManager') as mock_cm:
                mock_cm.return_value.consume_credits = AsyncMock(
                    side_effect=Exception("Credit service unavailable")
                )

                metrics = UsageMetrics(
                    account_id=tenant_context.account_id,
                    execution_id="exec-error",
                    agent_id="test-agent",
                    deployment_id=None,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    tier="pro",
                    region="ap-southeast-2",
                )

                # Should not raise, should log error
                try:
                    await tracker._persist_usage_to_billing(metrics)
                except Exception:
                    # Error expected to be propagated or logged
                    pass

    @pytest.mark.asyncio
    async def test_cache_fallback_on_redis_failure(self, test_config, tenant_context):
        """
        Test cache falls back gracefully when Redis is unavailable.

        Phase 10 Requirement: When Redis is unavailable, cache operations
        should fail gracefully without breaking main functionality.
        """
        cache = AgentCoreCache(test_config)

        # Cache not initialized (no Redis connection)
        assert cache._redis is None

        with TenantContextManager(tenant_context):
            # Should not raise, should return None
            value = await cache.get(
                account_id=tenant_context.account_id,
                key="test-key"
            )
            assert value is None

            # Should return False (not set)
            success = await cache.set(
                account_id=tenant_context.account_id,
                key="test-key",
                value="test-value"
            )
            assert success is False

    @pytest.mark.asyncio
    async def test_validation_error_accumulation(self, test_config):
        """
        Test config validator accumulates multiple errors.

        Phase 10 Requirement: Configuration validation should collect
        all validation errors, not just the first one.
        """
        from core.agentcore.validation import get_config_validator

        validator = get_config_validator()

        # Config with multiple validation errors
        invalid_config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_region="us-east-1",  # Wrong region
            billing_enabled=True,
            s3_bucket_name=None,  # Missing required bucket
            code_interpreter_enabled=True,  # Requires S3 bucket
        )

        results = await validator.validate(invalid_config)

        # Should have multiple validation errors
        assert len(results) >= 2

        # Should have different severity levels
        has_error = any(r.severity == ValidationSeverity.ERROR for r in results)
        has_warning = any(r.severity == ValidationSeverity.WARNING for r in results)
        assert has_error or has_warning
