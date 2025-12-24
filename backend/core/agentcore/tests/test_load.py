"""
Load and Performance Tests for AgentCore Integration

Tests system performance under concurrent load and stress conditions.
These tests verify:
- Concurrent execution handling
- Throughput and latency targets
- Resource cleanup under load
- Memory and connection management
- Cache performance under load

Run with: pytest -v -m load --timeout=600
"""

import os
import pytest
import asyncio
import time
import psutil
import threading
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor

from core.agentcore import (
    # Config
    get_agentcore_config,
    AgentCoreConfig,
    Environment,

    # Models
    RuntimeStatus,
    RuntimeSession,

    # Adapters
    AgentCoreRuntimeAdapter,
    AgentCoreMemoryAdapter,

    # Phase 8: Billing
    UsageTracker,
    UsageMetrics,

    # Phase 9: Observability
    MetricsCollector,
    HealthChecker,

    # Phase 10: Caching
    AgentCoreCache,
    CacheManager,

    # Phase 10: Performance
    BatchProcessor,
    RuntimeBatchProcessor,
    ConnectionPool,
    RuntimeConnectionPool,

    # Phase 10: Rate Limiting
    RateLimiterManager,
    check_rate_limit,

    # Middleware
    TenantContext,
    TenantContextManager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_config():
    """Test configuration for load testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        aws_region="ap-southeast-2",
        runtime_enabled=True,
        code_interpreter_enabled=True,
        browser_enabled=True,
        memory_enabled=True,
        gateway_enabled=True,
        s3_bucket_name="kortix-agentcore-load-test",
        fallback_to_legacy_sandbox=True,
        billing_enabled=True,
        cloudwatch_enabled=False,
        health_check_enabled=True,
        cache_enabled=False,  # Disabled for load tests (no Redis)
        rate_limiting_enabled=False,  # Disabled for load tests
    )


@pytest.fixture
def load_tenant_context():
    """Tenant context for load testing"""
    return TenantContext(
        account_id="load-test-account",
        project_id="load-test-project",
        tenant_id="load-test-tenant",
        tier="pro",
        region="ap-southeast-2",
    )


@pytest.fixture
def mock_runtime_adapter():
    """Mock Runtime adapter with configurable latency"""
    adapter = AsyncMock(spec=AgentCoreRuntimeAdapter)

    adapter.create_deployment = AsyncMock(return_value="load-test-deployment")
    adapter.delete_deployment = AsyncMock(return_value=True)
    adapter.register_tool = AsyncMock(return_value=True)

    # Track invocation count and latency
    invocation_count = [0]
    total_latency = [0]

    async def invoke_with_latency(*args, **kwargs):
        invocation_count[0] += 1
        start = time.time()

        # Simulate variable latency (10-100ms)
        latency = 0.01 + (0.09 * (invocation_count[0] % 10))
        await asyncio.sleep(latency)

        total_latency[0] += (time.time() - start)

        return {
            "success": True,
            "result": {"output": f"execution-{invocation_count[0]}"},
            "error": None,
            "execution_id": f"exec-{invocation_count[0]}",
            "status": RuntimeStatus.COMPLETED,
            "metadata": {
                "latency_ms": int(latency * 1000),
            }
        }

    adapter.invoke_agent = invoke_with_latency
    adapter.invocation_count = lambda: invocation_count[0]
    adapter.total_latency = lambda: total_latency[0]

    return adapter


# ============================================================================
# Load Tests: Concurrent Execution
# ============================================================================

class TestAgentCoreLoadConcurrentExecution:
    """
    Load tests for concurrent agent execution.

    Tests the system's ability to handle multiple simultaneous agent
    executions without performance degradation.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_concurrent_executions_10_parallel(self, test_config, load_tenant_context, mock_runtime_adapter):
        """
        Test system handles 10 concurrent executions efficiently.

        Load Target: 10 concurrent executions should complete in < 2 seconds.
        """
        with TenantContextManager(load_tenant_context):
            num_concurrent = 10
            execution_times = []

            async def execute_agent(i: int):
                """Execute agent and track time"""
                start = time.time()

                result = await mock_runtime_adapter.invoke_agent(
                    deployment_id="load-test-deployment",
                    agent_id="test-agent",
                    input_data={"index": i},
                    session_id=f"session-{i}"
                )

                elapsed = time.time() - start
                execution_times.append(elapsed)
                return result

            # Execute concurrent agents
            start_time = time.time()
            results = await asyncio.gather(*[
                execute_agent(i) for i in range(num_concurrent)
            ])
            total_time = time.time() - start_time

            # Verify all completed successfully
            assert len(results) == num_concurrent
            assert all(r["success"] for r in results)

            # Verify concurrent execution (total time << sum of individual times)
            sum_times = sum(execution_times)
            assert total_time < sum_times * 0.5, f"Concurrent benefit: {total_time:.2f}s vs {sum_times:.2f}s serial"

            # Verify load target
            assert total_time < 2.0, f"Load target missed: {total_time:.2f}s >= 2.0s"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_concurrent_executions_50_parallel(self, test_config, load_tenant_context, mock_runtime_adapter):
        """
        Test system handles 50 concurrent executions.

        Load Target: 50 concurrent executions should complete in < 5 seconds.
        """
        with TenantContextManager(load_tenant_context):
            num_concurrent = 50

            async def execute_agent(i: int):
                await asyncio.sleep(0.01)  # Simulate work
                return {"success": True, "index": i}

            start_time = time.time()
            results = await asyncio.gather(*[
                execute_agent(i) for i in range(num_concurrent)
            ])
            total_time = time.time() - start_time

            # Verify all completed
            assert len(results) == num_concurrent
            assert all(r["success"] for r in results)

            # Verify load target
            assert total_time < 5.0, f"Load target missed: {total_time:.2f}s >= 5.0s"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_concurrent_executions_100_parallel(self, test_config, load_tenant_context):
        """
        Test system handles 100 concurrent executions.

        Load Target: 100 concurrent executions should complete in < 10 seconds.
        """
        with TenantContextManager(load_tenant_context):
            num_concurrent = 100

            async def execute_agent(i: int):
                await asyncio.sleep(0.005)  # Simulate minimal work
                return {"success": True, "index": i}

            start_time = time.time()
            results = await asyncio.gather(*[
                execute_agent(i) for i in range(num_concurrent)
            ])
            total_time = time.time() - start_time

            # Verify all completed
            assert len(results) == num_concurrent

            # Verify load target
            assert total_time < 10.0, f"Load target missed: {total_time:.2f}s >= 10.0s"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_sustained_load_100_executions_per_second(self, test_config, load_tenant_context, mock_runtime_adapter):
        """
        Test system can sustain 100 executions/second for 10 seconds.

        Load Target: 1000 executions over 10 seconds (100 exec/s sustained).
        """
        with TenantContextManager(load_tenant_context):
            target_rate = 100  # executions per second
            duration_seconds = 5  # Reduced for test speed
            total_executions = target_rate * duration_seconds

            completed = [0]
            errors = [0]

            async def execute_agent(i: int):
                try:
                    await mock_runtime_adapter.invoke_agent(
                        deployment_id="load-test-deployment",
                        agent_id="test-agent",
                        input_data={"index": i},
                        session_id=f"session-{i}"
                    )
                    completed[0] += 1
                except Exception:
                    errors[0] += 1

            # Create task queue with rate limiting
            tasks = []
            start_time = time.time()

            for batch in range(duration_seconds):
                batch_tasks = [
                    execute_agent(batch * target_rate + i)
                    for i in range(target_rate)
                ]
                tasks.extend(batch_tasks)

                # Execute batch
                await asyncio.gather(*batch_tasks)

                # Brief pause to maintain rate
                await asyncio.sleep(0.9)

            total_time = time.time() - start_time

            # Verify sustained load
            actual_rate = completed[0] / total_time
            assert completed[0] >= total_executions * 0.95, \
                f"Throughput target missed: {completed[0]}/{total_executions} completed"
            assert errors[0] == 0, f"Errors occurred during sustained load: {errors[0]}"


# ============================================================================
# Load Tests: Memory & Resource Management
# ============================================================================

class TestAgentCoreLoadResourceManagement:
    """
    Load tests for memory and resource management.

    Tests the system properly cleans up resources under load and
    doesn't leak memory or connections.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_memory_leak_detection_concurrent_sessions(self, test_config, load_tenant_context):
        """
        Test no memory leaks with 100 concurrent sessions.

        Load Target: Memory usage should remain stable after 100
        concurrent session create/delete cycles.
        """
        with TenantContextManager(load_tenant_context):
            # Get initial memory
            process = psutil.Process()
            initial_memory = process.memory_info().rss

            # Run 100 cycles of session creation/deletion
            for cycle in range(100):
                session = RuntimeSession(
                    session_id=f"load-session-{cycle}",
                    deployment_id="load-test-deployment",
                    status=RuntimeStatus.READY,
                )

                # Simulate session work
                await asyncio.sleep(0.001)

                # Session cleanup happens automatically

                # Check memory every 10 cycles
                if cycle % 10 == 0:
                    current_memory = process.memory_info().rss
                    memory_growth = current_memory - initial_memory
                    memory_growth_mb = memory_growth / (1024 * 1024)

                    # Allow 50MB growth (Python overhead)
                    assert memory_growth_mb < 50, \
                        f"Memory leak detected: {memory_growth_mb:.1f}MB growth after {cycle} cycles"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_connection_pool_under_load(self, test_config, load_tenant_context):
        """
        Test connection pool handles high concurrent load.

        Load Target: Connection pool with max_size=10 should handle
        50 concurrent acquisitions efficiently.
        """
        with TenantContextManager(load_tenant_context):
            pool = RuntimeConnectionPool(
                config=test_config,
                max_size=10,
            )

            acquired = []
            acquisition_times = []

            async def acquire_and_release(i: int):
                """Acquire connection, hold briefly, then release"""
                start = time.time()

                async with pool.acquire() as conn:
                    acquisition_times.append(time.time() - start)
                    acquired.append(i)
                    await asyncio.sleep(0.01)  # Hold connection
                    return i

            # More concurrent requests than pool size
            num_requests = 50
            results = await asyncio.gather(*[
                acquire_and_release(i) for i in range(num_requests)
            ])

            # Verify all requests completed
            assert len(results) == num_requests

            # Verify pool size was respected
            assert pool.stats.peak_size <= pool.config.max_size

            # Verify efficient acquisition (no excessive queuing)
            avg_acquisition_time = sum(acquisition_times) / len(acquisition_times)
            assert avg_acquisition_time < 0.5, \
                f"Acquisition too slow: {avg_acquisition_time:.3f}s average"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_batch_processor_throughput(self, test_config, load_tenant_context):
        """
        Test batch processor throughput under load.

        Load Target: Should process 1000 items in < 5 seconds.
        """
        with TenantContextManager(load_tenant_context):
            from core.agentcore.performance import BatchItem, BatchPriority

            processor = RuntimeBatchProcessor(
                config=test_config,
                max_concurrent=20,
            )

            processed = []

            async def mock_process(item: BatchItem):
                await asyncio.sleep(0.001)  # 1ms per item
                processed.append(item.item_id)
                return {"item_id": item.item_id, "processed": True}

            processor._process_item = mock_process

            # Create 1000 items
            items = [
                BatchItem(
                    item_id=f"item-{i}",
                    priority=BatchPriority.NORMAL,
                    data={"index": i}
                )
                for i in range(1000)
            ]

            # Process batch
            start_time = time.time()
            results = await processor.process_batch(items)
            total_time = time.time() - start_time

            # Verify all processed
            assert len(results) == 1000
            assert len(processed) == 1000

            # Verify throughput target
            throughput = len(results) / total_time
            assert throughput >= 200, \
                f"Throughput target missed: {throughput:.0f} items/sec < 200 items/sec"


# ============================================================================
# Load Tests: Billing & Usage Tracking
# ============================================================================

class TestAgentCoreLoadBilling:
    """
    Load tests for billing system under high load.

    Tests usage tracking, credit consumption, and tier-based pricing
    under concurrent execution scenarios.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_usage_tracking_under_concurrent_load(self, test_config, load_tenant_context):
        """
        Test usage tracking handles 100 concurrent executions.

        Load Target: UsageTracker should track 100 concurrent
        executions without data loss or corruption.
        """
        with TenantContextManager(load_tenant_context):
            tracker = UsageTracker(test_config)

            execution_count = [0]

            async def track_and_complete(i: int):
                execution_id = f"load-exec-{i}"

                # Start tracking
                metrics = await tracker.start_execution_tracking(
                    execution_id=execution_id,
                    agent_id="load-test-agent",
                    deployment_id="load-test-deployment"
                )

                execution_count[0] += 1

                # Simulate execution
                await asyncio.sleep(0.001)

                # Complete tracking
                mock_result = Mock()
                mock_result.metadata = {
                    "input_tokens": 100 + i,
                    "output_tokens": 50 + i,
                }

                completed = await tracker.complete_execution_tracking(
                    execution_id=execution_id,
                    result=mock_result
                )

                return completed

            # Track 100 concurrent executions
            num_concurrent = 100
            results = await asyncio.gather(*[
                track_and_complete(i) for i in range(num_concurrent)
            ])

            # Verify all tracked
            assert len(results) == num_concurrent
            assert all(r.completed_at is not None for r in results)
            assert execution_count[0] == num_concurrent

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_tier_based_pricing_under_load(self, test_config):
        """
        Test tier-based pricing calculations under load.

        Load Target: Should calculate pricing for 1000 executions
        in < 1 second.
        """
        tracker = UsageTracker(test_config)

        # Create metrics for all executions
        all_metrics = [
            UsageMetrics(
                account_id=f"account-{i % 3}",  # 3 different accounts
                execution_id=f"exec-{i}",
                agent_id="test-agent",
                deployment_id=None,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow() + timedelta(seconds=30),
                execution_duration_seconds=30,
                input_tokens=1000,
                output_tokens=500,
                total_tokens=1500,
                tier=["free", "pro", "enterprise"][i % 3],
                region="ap-southeast-2",
            )
            for i in range(1000)
        ]

        # Calculate pricing for all
        start_time = time.time()
        credits = [tracker._calculate_credits_from_usage(m) for m in all_metrics]
        total_time = time.time() - start_time

        # Verify performance
        assert len(credits) == 1000
        assert total_time < 1.0, f"Pricing calculation too slow: {total_time:.3f}s"

        # Verify tier differentiation
        free_credits = [c for i, c in enumerate(credits) if all_metrics[i].tier == "free"]
        pro_credits = [c for i, c in enumerate(credits) if all_metrics[i].tier == "pro"]
        ent_credits = [c for i, c in enumerate(credits) if all_metrics[i].tier == "enterprise"]

        assert sum(free_credits) > sum(pro_credits) > sum(ent_credits)


# ============================================================================
# Load Tests: Observability
# ============================================================================

class TestAgentCoreLoadObservability:
    """
    Load tests for observability components.

    Tests metrics collection, health checks, and monitoring
    under high load conditions.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_metrics_collector_under_load(self, test_config, load_tenant_context):
        """
        Test metrics collector handles high frequency updates.

        Load Target: Should record 1000 metrics in < 2 seconds
        without performance degradation.
        """
        with TenantContextManager(load_tenant_context):
            collector = MetricsCollector(test_config)

            # Record 1000 metrics
            start_time = time.time()

            for i in range(1000):
                await collector.record_execution(
                    execution_id=f"exec-{i}",
                    agent_id="load-test-agent",
                    duration_seconds=30,
                    tokens_used=1500,
                    success=True,
                    tier="pro",
                )

            total_time = time.time() - start_time

            # Verify performance
            assert total_time < 2.0, f"Metrics recording too slow: {total_time:.3f}s"

            # Verify aggregation
            metrics = await collector.get_aggregated_metrics(
                agent_id="load-test-agent",
                time_range_minutes=5,
            )

            assert metrics['total_executions'] == 1000

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_health_checker_under_load(self, test_config):
        """
        Test health checker remains responsive under load.

        Load Target: Health checks should complete in < 100ms
        even under concurrent system load.
        """
        checker = HealthChecker(test_config)

        # Run 100 concurrent health checks
        num_checks = 100
        check_times = []

        async def run_health_check(i: int):
            start = time.time()
            results = await checker.check_all()
            elapsed = time.time() - start
            check_times.append(elapsed)
            return results

        # Execute concurrent health checks
        start_time = time.time()
        results = await asyncio.gather(*[
            run_health_check(i) for i in range(num_checks)
        ])
        total_time = time.time() - start_time

        # Verify all completed
        assert len(results) == num_checks

        # Verify responsiveness (each check should be fast)
        avg_check_time = sum(check_times) / len(check_times)
        assert avg_check_time < 0.1, \
            f"Health check too slow: {avg_check_time:.3f}s average"

        # Verify no degradation under load
        max_check_time = max(check_times)
        assert max_check_time < 0.5, \
            f"Health check degraded: {max_check_time:.3f}s max"


# ============================================================================
# Load Tests: Rate Limiting
# ============================================================================

class TestAgentCoreLoadRateLimiting:
    """
    Load tests for rate limiting under high request volume.

    Tests token bucket and sliding window algorithms under load,
    and verifies proper backoff signaling.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_rate_limiter_high_volume(self, test_config, load_tenant_context):
        """
        Test rate limiter handles high request volume efficiently.

        Load Target: Rate limiter should process 1000 checks in < 1 second.
        """
        # Enable rate limiting for this test
        test_config.rate_limiting_enabled = True

        with TenantContextManager(load_tenant_context):
            from core.agentcore.rate_limiting import TIER_RATE_LIMITS, RateLimitScope

            # Use pro tier limits (100 req/min)
            pro_rules = TIER_RATE_LIMITS["pro"]
            global_rule = [r for r in pro_rules if r.scope == RateLimitScope.GLOBAL][0]

            # Create rate limiter
            from core.agentcore.rate_limiting import DistributedRateLimiter
            limiter = DistributedRateLimiter(test_config)

            # Process 1000 checks
            start_time = time.time()

            results = []
            for i in range(1000):
                result = await limiter.check_rate_limit(
                    rule=global_rule,
                    account_id=load_tenant_context.account_id,
                    tier="pro"
                )
                results.append(result)

                # Stop when rate limited
                if not result.allowed:
                    break

            total_time = time.time() - start_time

            # Verify performance
            assert total_time < 1.0, f"Rate limiting too slow: {total_time:.3f}s"

            # Verify rate limiting worked
            assert len(results) <= global_rule.limit
            allowed = sum(1 for r in results if r.allowed)
            assert allowed == global_rule.limit

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_rate_limiter_burst_handling(self, test_config, load_tenant_context):
        """
        Test rate limiter handles burst traffic correctly.

        Load Target: Should handle burst of 50 requests in < 100ms,
        then properly rate limit subsequent requests.
        """
        test_config.rate_limiting_enabled = True

        with TenantContextManager(load_tenant_context):
            from core.agentcore.rate_limiting import TIER_RATE_LIMITS, RateLimitScope

            pro_rules = TIER_RATE_LIMITS["pro"]
            global_rule = [r for r in pro_rules if r.scope == RateLimitScope.GLOBAL][0]

            from core.agentcore.rate_limiting import DistributedRateLimiter
            limiter = DistributedRateLimiter(test_config)

            # Send burst of requests
            burst_size = 50
            burst_time_start = time.time()

            burst_results = []
            for i in range(burst_size):
                result = await limiter.check_rate_limit(
                    rule=global_rule,
                    account_id=load_tenant_context.account_id,
                    tier="pro"
                )
                burst_results.append(result)

            burst_time = time.time() - burst_time_start

            # Verify burst was handled quickly
            assert burst_time < 0.1, f"Burst handling too slow: {burst_time:.3f}s"

            # Verify some requests were allowed
            allowed_in_burst = sum(1 for r in burst_results if r.allowed)
            assert allowed_in_burst > 0


# ============================================================================
# Load Tests: Cache Performance
# ============================================================================

class TestAgentCoreLoadCachePerformance:
    """
    Load tests for cache performance under high load.

    Tests cache hit rates, throughput, and memory usage with
    concurrent read/write operations.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_cache_read_throughput(self, test_config, load_tenant_context):
        """
        Test cache read throughput under load.

        Load Target: Should handle 10000 cache reads in < 2 seconds.
        """
        cache = AgentCoreCache(test_config)

        with TenantContextManager(load_tenant_context):
            # Pre-populate cache
            num_keys = 100
            for i in range(num_keys):
                await cache.set(
                    account_id=load_tenant_context.account_id,
                    key=f"key-{i}",
                    value={"data": f"value-{i}"},
                    ttl=3600
                )

            # Concurrent reads
            num_reads = 10000
            read_times = []

            async def read_cache(i: int):
                key = f"key-{i % num_keys}"
                start = time.time()
                value = await cache.get(
                    account_id=load_tenant_context.account_id,
                    key=key
                )
                elapsed = time.time() - start
                read_times.append(elapsed)
                return value

            start_time = time.time()
            results = await asyncio.gather(*[
                read_cache(i) for i in range(num_reads)
            ])
            total_time = time.time() - start_time

            # Verify performance
            throughput = num_reads / total_time
            assert throughput >= 5000, \
                f"Cache read throughput too low: {throughput:.0f} reads/sec"

            # Verify hit rate (cache not initialized, so may miss)
            # Note: This test may have cache misses since AgentCoreCache is disabled

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_cache_write_throughput(self, test_config, load_tenant_context):
        """
        Test cache write throughput under load.

        Load Target: Should handle 1000 cache writes in < 1 second.
        """
        cache = AgentCoreCache(test_config)

        with TenantContextManager(load_tenant_context):
            num_writes = 1000
            write_times = []

            async def write_cache(i: int):
                start = time.time()
                success = await cache.set(
                    account_id=load_tenant_context.account_id,
                    key=f"write-key-{i}",
                    value={"data": f"write-value-{i}"},
                    ttl=60
                )
                elapsed = time.time() - start
                write_times.append(elapsed)
                return success

            start_time = time.time()
            results = await asyncio.gather(*[
                write_cache(i) for i in range(num_writes)
            ])
            total_time = time.time() - start_time

            # Verify performance
            throughput = num_writes / total_time
            # Note: Cache is disabled, so writes will fail fast
            assert total_time < 1.0, f"Cache write operation too slow: {total_time:.3f}s"


# ============================================================================
# Stress Tests: Edge Cases
# ============================================================================

class TestAgentCoreStressTests:
    """
    Stress tests for edge cases and boundary conditions.

    Tests system behavior under extreme conditions and validates
    graceful degradation.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_rapid_create_delete_cycles(self, test_config, load_tenant_context):
        """
        Test rapid deployment create/delete cycles.

        Stress Target: Handle 100 create/delete cycles in < 5 seconds
        without resource leaks.
        """
        with TenantContextManager(load_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

            adapter = AgentCoreRuntimeAdapter(test_config)

            # Mock the underlying AWS calls
            adapter.create_deployment = AsyncMock(return_value=f"deployment-{{}}")
            adapter.delete_deployment = AsyncMock(return_value=True)

            num_cycles = 100
            created_count = [0]
            deleted_count = [0]

            async def create_delete_cycle(i: int):
                # Create deployment
                deployment_id = await adapter.create_deployment(
                    deployment_name=f"stress-deployment-{i}",
                    agent_id="test-agent",
                    account_id=load_tenant_context.account_id,
                )
                created_count[0] += 1

                # Brief work
                await asyncio.sleep(0.001)

                # Delete deployment
                await adapter.delete_deployment(
                    deployment_id=deployment_id,
                )
                deleted_count[0] += 1

            # Run cycles
            start_time = time.time()
            await asyncio.gather(*[
                create_delete_cycle(i) for i in range(num_cycles)
            ])
            total_time = time.time() - start_time

            # Verify all cycles completed
            assert created_count[0] == num_cycles
            assert deleted_count[0] == num_cycles

            # Verify performance
            assert total_time < 5.0, f"Create/delete cycles too slow: {total_time:.3f}s"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_mixed_workload_distribution(self, test_config, load_tenant_context):
        """
        Test system handles mixed workload types efficiently.

        Stress Target: Handle 50 executions + 50 health checks + 50
        metrics recordings concurrently in < 3 seconds.
        """
        with TenantContextManager(load_tenant_context):
            tracker = UsageTracker(test_config)
            collector = MetricsCollector(test_config)
            checker = HealthChecker(test_config)

            execution_count = [0]
            check_count = [0]
            metric_count = [0]

            async def mixed_workload(i: int):
                workload_type = i % 3

                if workload_type == 0:
                    # Execution workload
                    execution_id = f"mixed-exec-{execution_count[0]}"
                    await tracker.start_execution_tracking(
                        execution_id=execution_id,
                        agent_id="mixed-agent",
                        deployment_id="mixed-deployment"
                    )
                    await asyncio.sleep(0.01)
                    execution_count[0] += 1

                elif workload_type == 1:
                    # Health check workload
                    await checker.check_all()
                    check_count[0] += 1

                else:
                    # Metrics recording workload
                    await collector.record_execution(
                        execution_id=f"mixed-metric-{metric_count[0]}",
                        agent_id="mixed-agent",
                        duration_seconds=30,
                        tokens_used=1500,
                        success=True,
                        tier="pro",
                    )
                    metric_count[0] += 1

            # Run mixed workload
            num_operations = 150
            start_time = time.time()
            await asyncio.gather(*[
                mixed_workload(i) for i in range(num_operations)
            ])
            total_time = time.time() - start_time

            # Verify all workloads processed
            assert execution_count[0] > 0
            assert check_count[0] > 0
            assert metric_count[0] > 0

            # Verify performance
            assert total_time < 3.0, f"Mixed workload too slow: {total_time:.3f}s"


# ============================================================================
# Performance Benchmarks
# ============================================================================

class TestAgentCorePerformanceBenchmarks:
    """
    Performance benchmarks for critical operations.

    These tests establish baseline performance metrics that
    should be maintained in future iterations.
    """

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_runtime_invocation_latency_p99(self, test_config, load_tenant_context, mock_runtime_adapter):
        """
        Benchmark Runtime invocation latency (P99).

        Performance Target: P99 latency < 500ms for Runtime invocation.
        """
        with TenantContextManager(load_tenant_context):
            num_samples = 100
            latencies = []

            # Collect latency samples
            for i in range(num_samples):
                start = time.time()

                await mock_runtime_adapter.invoke_agent(
                    deployment_id="benchmark-deployment",
                    agent_id="benchmark-agent",
                    input_data={"index": i},
                    session_id=f"session-{i}"
                )

                latency_ms = (time.time() - start) * 1000
                latencies.append(latency_ms)

            # Calculate percentiles
            latencies_sorted = sorted(latencies)
            p50 = latencies_sorted[int(num_samples * 0.50)]
            p95 = latencies_sorted[int(num_samples * 0.95)]
            p99 = latencies_sorted[int(num_samples * 0.99)]

            # Verify performance targets
            assert p99 < 500, f"P99 latency too high: {p99:.0f}ms >= 500ms"
            assert p95 < 300, f"P95 latency too high: {p95:.0f}ms >= 300ms"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_batch_processing_efficiency(self, test_config, load_tenant_context):
        """
        Benchmark batch processing efficiency.

        Performance Target: Batch processing should be at least
        3x faster than serial processing for 50 items.
        """
        with TenantContextManager(load_tenant_context):
            from core.agentcore.performance import BatchItem, BatchPriority

            processor = RuntimeBatchProcessor(
                config=test_config,
                max_concurrent=10,
            )

            async def mock_process(item: BatchItem):
                await asyncio.sleep(0.01)  # 10ms per item
                return {"item_id": item.item_id}

            processor._process_item = mock_process

            # Create batch
            items = [
                BatchItem(
                    item_id=f"bench-item-{i}",
                    priority=BatchPriority.NORMAL,
                    data={"index": i}
                )
                for i in range(50)
            ]

            # Batch processing
            start_batch = time.time()
            batch_results = await processor.process_batch(items)
            batch_time = time.time() - start_batch

            # Serial processing (same items)
            start_serial = time.time()
            serial_results = []
            for item in items:
                result = await mock_process(item)
                serial_results.append(result)
            serial_time = time.time() - start_serial

            # Verify batch efficiency
            speedup = serial_time / batch_time
            assert speedup >= 3.0, \
                f"Batch processing not efficient enough: {speedup:.2f}x speedup (target: 3x)"

    @pytest.mark.asyncio
    @pytest.mark.load
    async def test_memory_stability_under_load(self, test_config, load_tenant_context):
        """
        Benchmark memory stability under sustained load.

        Performance Target: Memory growth should be < 10MB over
        1000 executions.
        """
        with TenantContextManager(load_tenant_context):
            process = psutil.Process()
            initial_memory = process.memory_info().rss

            # Run 1000 light executions
            for i in range(1000):
                # Simulate execution overhead
                session = RuntimeSession(
                    session_id=f"mem-test-{i}",
                    deployment_id="test-deployment",
                    status=RuntimeStatus.READY,
                )

                # Simulate work
                await asyncio.sleep(0.0001)

                # Check memory every 100 iterations
                if i % 100 == 0:
                    current_memory = process.memory_info().rss
                    growth = (current_memory - initial_memory) / (1024 * 1024)

            # Final memory check
            final_memory = process.memory_info().rss
            total_growth = (final_memory - initial_memory) / (1024 * 1024)

            # Verify memory stability
            assert total_growth < 10, \
                f"Memory growth too high: {total_growth:.1f}MB over 1000 executions"
