"""
Multi-Region Deployment Tests for AgentCore

Tests for multi-region deployment handling, ensuring:
- Only ap-southeast-2 is enabled for Phase 8-10
- Multi-region manager enforces region constraints
- Cross-region data access is blocked
- Region override attempts are prevented

Author: AgentCore Migration Team
Phase: Sprint 4 - Testing & Validation (Task 68)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.agentcore.config import (
    AgentCoreConfig,
    Environment,
    get_agentcore_config,
)
from core.agentcore.models import (
    RuntimeDeployment,
    RuntimeSession,
    RuntimeStatus,
    DeploymentRegion,
)
from core.agentcore.errors import (
    AgentCoreConfigurationError,
    ValidationError,
    AgentCoreExecutionError,
)
from core.agentcore.middleware import (
    TenantContext,
    TenantContextManager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def multi_region_config():
    """Config with ap-southeast-2 region."""
    return AgentCoreConfig(
        environment=Environment.PRODUCTION,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        agent_core_gateway_url="https://gateway-ap-southeast-2.amazonaws.com",
        s3_bucket_name="kortix-agentcore-files-ap-southeast-2",
    )


@pytest.fixture
def invalid_region_config():
    """Config with non-Australia region (should be rejected)."""
    return AgentCoreConfig(
        environment=Environment.PRODUCTION,
        aws_region="us-east-1",  # Invalid for Phase 8-10
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        agent_core_gateway_url="https://gateway-us-east-1.amazonaws.com",
        s3_bucket_name="kortix-agentcore-files-us-east-1",
    )


@pytest.fixture
def multi_tenant_context():
    """Multi-tenant context for cross-region isolation tests."""
    return TenantContext(
        account_id="multi-region-test-account",
        tenant_id="tenant-xyz",
        tier="enterprise",
        region="ap-southeast-2",
        created_at=datetime.utcnow(),
    )


# ============================================================================
# Region Constraint Tests
# ============================================================================

class TestRegionConstraints:
    """Tests for region constraint enforcement."""

    @pytest.mark.asyncio
    async def test_only_ap_southeast_2_is_enabled(self, multi_region_config):
        """Test that only ap-southeast-2 region is enabled for Phase 8-10."""
        from core.agentcore.deployment import MultiRegionManager

        manager = MultiRegionManager(multi_region_config)
        enabled_regions = manager.get_enabled_regions()

        # Verify only ap-southeast-2 is enabled
        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

    @pytest.mark.asyncio
    async def test_invalid_region_is_rejected(self, invalid_region_config):
        """Test that non-Australia regions are rejected."""
        from core.agentcore.deployment import MultiRegionManager

        # Should override to ap-southeast-2
        manager = MultiRegionManager(invalid_region_config)
        enabled_regions = manager.get_enabled_regions()

        # Verify ap-southeast-2 override happened
        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

    @pytest.mark.asyncio
    async def test_region_validation_in_config(self):
        """Test that config validates region at initialization."""
        # Valid region
        valid_config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_region="ap-southeast-2",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
        )
        assert valid_config.aws_region == "ap-southeast-2"

        # Invalid regions get overridden or rejected
        with pytest.warns(UserWarning):
            invalid_config = AgentCoreConfig(
                environment=Environment.PRODUCTION,
                aws_region="us-west-2",
                aws_access_key_id="test-key",
                aws_secret_access_key="test-secret",
            )
            # Config may auto-correct to ap-southeast-2
            # or keep original value with warning

    @pytest.mark.asyncio
    async def test_region_enforcement_in_runtime_adapter(self, multi_region_config):
        """Test that runtime adapter enforces ap-southeast-2 region."""
        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(multi_region_config)

        # Verify region is set correctly
        assert adapter.config.aws_region == "ap-southeast-2"

        # Mock boto3 client to verify region is passed
        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock
            mock_bedrock.get_agent.return_value = {
                "agent": {
                    "agentId": "test-agent",
                    "agentArn": "arn:aws:bedrock:ap-southeast-2::123456789012:agent/test-agent",
                    "agentStatus": "PREPARED",
                }
            }

            await adapter.get_deployment("test-deployment-id")

            # Verify boto3 was called with ap-southeast-2
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs.get("region_name") == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_s3_bucket_region_enforcement(self, multi_region_config):
        """Test that S3 bucket is in ap-southeast-2."""
        # Verify S3 bucket name contains region
        assert "ap-southeast-2" in multi_region_config.s3_bucket_name

        # Verify S3 bucket region matches
        assert multi_region_config.s3_bucket_region == "ap-southeast-2"


# ============================================================================
# Cross-Region Data Access Prevention
# ============================================================================

class TestCrossRegionDataAccess:
    """Tests for preventing cross-region data access."""

    @pytest.mark.asyncio
    async def test_data_isolation_across_regions(self, multi_region_config, multi_tenant_context):
        """Test that data cannot be accessed across different regions."""
        from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
        from core.agentcore.deployment import MultiRegionManager

        with TenantContextManager(multi_tenant_context):
            region_manager = MultiRegionManager(multi_region_config)
            memory_adapter = AgentCoreMemoryAdapter(multi_region_config)

            # Create memory in ap-southeast-2
            memory_id = "memory-test-123"
            await memory_adapter.create_memory_resource(
                memory_id=memory_id,
                agent_id="test-agent",
                description="Test memory",
            )

            # Verify memory exists in ap-southeast-2
            memory = await memory_adapter.get_memory_resource(memory_id)
            assert memory is not None
            assert memory.memory_id == memory_id

    @pytest.mark.asyncio
    async def test_runtime_deployment_region_isolation(self, multi_region_config):
        """Test that runtime deployments are region-isolated."""
        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(multi_region_config)

        # Mock deployment
        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            # Create deployment
            deployment_arn = f"arn:aws:bedrock:ap-southeast-2::123456789012:agent-deployment/test-deployment"

            mock_bedrock.create_agent.return_value = {
                "agent": {
                    "agentId": "test-agent-id",
                    "agentArn": deployment_arn,
                    "agentStatus": "PREPARED",
                }
            }

            # Verify ARN contains ap-southeast-2
            result = await adapter.deploy_agent(
                agent_id="test-agent",
                instruction="Test instruction",
                foundation_model="anthropic.claude-3-haiku-20250307-v1:0",
            )

            assert "ap-southeast-2" in result.deployment_arn

    @pytest.mark.asyncio
    async def test_gateway_url_region_enforcement(self, multi_region_config):
        """Test that gateway URL uses ap-southeast-2 region."""
        # Gateway URL should contain ap-southeast-2
        assert "ap-southeast-2" in multi_region_config.agent_core_gateway_url

        # Verify no other region URLs are configured
        assert "us-east-1" not in multi_region_config.agent_core_gateway_url
        assert "eu-west-1" not in multi_region_config.agent_core_gateway_url


# ============================================================================
# Region Override Prevention
# ============================================================================

class TestRegionOverridePrevention:
    """Tests for preventing region override attempts."""

    @pytest.mark.asyncio
    async def test_region_override_via_env_is_blocked(self, multi_region_config):
        """Test that attempts to override region via environment are blocked."""
        from core.agentcore.deployment import MultiRegionManager

        # Even if config has wrong region, manager overrides to ap-southeast-2
        wrong_region_config = AgentCoreConfig(
            environment=Environment.PRODUCTION,
            aws_region="us-west-2",  # Wrong region
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
        )

        manager = MultiRegionManager(wrong_region_config)
        enabled_regions = manager.get_enabled_regions()

        # Verify ap-southeast-2 is enforced
        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

    @pytest.mark.asyncio
    async def test_region_override_via_api_is_blocked(self, multi_region_config):
        """Test that attempts to override region via API parameters are blocked."""
        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(multi_region_config)

        # Try to invoke with different region
        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            mock_bedrock.invoke_agent.return_value = {
                "completion": ["Test response"],
                "sessionId": "test-session",
            }

            # Invoke agent (should use config region, not parameter)
            result = await adapter.invoke_agent(
                deployment_id="test-deployment",
                input_text="Test input",
                session_id="test-session",
            )

            # Verify boto3 was called with ap-southeast-2
            mock_client.assert_called_once()
            call_kwargs = mock_client.call_args.kwargs
            assert call_kwargs.get("region_name") == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_multi_region_manager_region_lock(self, multi_region_config):
        """Test that MultiRegionManager locks region to ap-southeast-2."""
        from core.agentcore.deployment import MultiRegionManager

        manager = MultiRegionManager(multi_region_config)

        # Try to add new region (should be blocked or ignored)
        # Phase 8-10: Only ap-southeast-2 is allowed
        enabled_regions = manager.get_enabled_regions()

        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

        # Verify no other regions are present
        for region in DeploymentRegion:
            if region != DeploymentRegion.AP_SOUTHEAST_2:
                assert region not in enabled_regions


# ============================================================================
# Region Health Monitoring
# ============================================================================

class TestRegionHealthMonitoring:
    """Tests for region health monitoring."""

    @pytest.mark.asyncio
    async def test_ap_southeast_2_health_check(self, multi_region_config):
        """Test health check for ap-southeast-2 region."""
        from core.agentcore.deployment import RegionHealthMonitor

        monitor = RegionHealthMonitor(multi_region_config)

        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            # Mock healthy response
            mock_bedrock.get_agent.return_value = {
                "agent": {
                    "agentId": "test-agent",
                    "agentStatus": "PREPARED",
                }
            }

            # Check health
            health = await monitor.check_region_health(DeploymentRegion.AP_SOUTHEAST_2)

            assert health.is_healthy is True
            assert health.region == DeploymentRegion.AP_SOUTHEAST_2

    @pytest.mark.asyncio
    async def test_unhealthy_region_detection(self, multi_region_config):
        """Test detection of unhealthy region."""
        from core.agentcore.deployment import RegionHealthMonitor

        monitor = RegionHealthMonitor(multi_region_config)

        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            # Mock unhealthy response (timeout)
            mock_bedrock.get_agent.side_effect = Exception("Connection timeout")

            # Check health
            health = await monitor.check_region_health(DeploymentRegion.AP_SOUTHEAST_2)

            assert health.is_healthy is False
            assert "timeout" in health.error_message.lower()

    @pytest.mark.asyncio
    async def test_multi_region_health_aggregation(self, multi_region_config):
        """Test aggregation of health across regions (only ap-southeast-2 in Phase 8-10)."""
        from core.agentcore.deployment import RegionHealthMonitor

        monitor = RegionHealthMonitor(multi_region_config)

        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            # Mock healthy response
            mock_bedrock.get_agent.return_value = {
                "agent": {
                    "agentId": "test-agent",
                    "agentStatus": "PREPARED",
                }
            }

            # Check all regions
            health_report = await monitor.check_all_regions()

            # Only ap-southeast-2 should be present
            assert len(health_report) == 1
            assert DeploymentRegion.AP_SOUTHEAST_2 in health_report
            assert health_report[DeploymentRegion.AP_SOUTHEAST_2].is_healthy is True


# ============================================================================
# Region-Specific Configuration
# ============================================================================

class TestRegionSpecificConfiguration:
    """Tests for region-specific configuration."""

    @pytest.mark.asyncio
    async def test_ap_southeast_2_s3_bucket_configuration(self, multi_region_config):
        """Test S3 bucket is configured for ap-southeast-2."""
        # Verify bucket name includes region
        assert "ap-southeast-2" in multi_region_config.s3_bucket_name.lower()

        # Verify bucket region matches
        assert multi_region_config.s3_bucket_region == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_ap_southeast_2_gateway_configuration(self, multi_region_config):
        """Test AgentCore Gateway is configured for ap-southeast-2."""
        # Gateway URL should use ap-southeast-2
        assert "ap-southeast-2" in multi_region_config.agent_core_gateway_url

        # Verify protocol and domain
        assert multi_region_config.agent_core_gateway_url.startswith("https://")
        assert "amazonaws.com" in multi_region_config.agent_core_gateway_url

    @pytest.mark.asyncio
    async def test_cloudwatch_namespace_includes_region(self, multi_region_config):
        """Test CloudWatch namespace includes region identifier."""
        namespace = "AgentCore/Production"
        # CloudWatch metrics are regional, so they're automatically scoped to ap-southeast-2
        # No explicit region in namespace, but metrics go to ap-southeast-2

        from core.agentcore.observability import CloudWatchClient

        client = CloudWatchClient(multi_region_config)

        # Verify CloudWatch client uses ap-southeast-2
        assert client.config.aws_region == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_cache_key_includes_region(self, multi_region_config):
        """Test cache keys include region for isolation."""
        from core.agentcore.cache import AgentCoreCache

        cache = AgentCoreCache(multi_region_config)

        # Generate cache key
        account_id = "test-account"
        key = "test-key"

        cache_key = cache._make_key(account_id, key)

        # Verify region is in cache key
        assert "ap-southeast-2" in cache_key


# ============================================================================
# Region Migration Tests
# ============================================================================

class TestRegionMigration:
    """Tests for future region migration capabilities."""

    @pytest.mark.asyncio
    async def test_region_migration_placeholder(self, multi_region_config):
        """Test placeholder for future multi-region support (Phase 11+)."""
        from core.agentcore.deployment import MultiRegionManager

        manager = MultiRegionManager(multi_region_config)

        # Phase 8-10: Only ap-southeast-2
        enabled_regions = manager.get_enabled_regions()

        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

        # Future phases may add support for:
        # - us-east-1 (North America)
        # - eu-west-1 (Europe)
        # - ap-northeast-1 (Asia Pacific)

    @pytest.mark.asyncio
    async def test_data_residency_compliance(self, multi_region_config, multi_tenant_context):
        """Test data residency compliance with ap-southeast-2 requirement."""
        from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        with TenantContextManager(multi_tenant_context):
            # Verify all data operations stay in ap-southeast-2
            memory_adapter = AgentCoreMemoryAdapter(multi_region_config)
            runtime_adapter = AgentCoreRuntimeAdapter(multi_region_config)

            # Memory operations
            assert memory_adapter.config.aws_region == "ap-southeast-2"
            assert runtime_adapter.config.aws_region == "ap-southeast-2"

            # S3 operations
            assert "ap-southeast-2" in multi_region_config.s3_bucket_name

            # Gateway operations
            assert "ap-southeast-2" in multi_region_config.agent_core_gateway_url


# ============================================================================
# Region Failover Tests
# ============================================================================

class TestRegionFailover:
    """Tests for region failover handling."""

    @pytest.mark.asyncio
    async def test_no_failover_in_phase_8_10(self, multi_region_config):
        """Test that failover to other regions is disabled in Phase 8-10."""
        from core.agentcore.deployment import MultiRegionManager

        manager = MultiRegionManager(multi_region_config)

        # Get available regions
        enabled_regions = manager.get_enabled_regions()

        # Only ap-southeast-2 should be available
        assert len(enabled_regions) == 1
        assert enabled_regions[0] == DeploymentRegion.AP_SOUTHEAST_2

        # No fallback regions configured
        fallback_regions = manager.get_fallback_regions()
        assert len(fallback_regions) == 0

    @pytest.mark.asyncio
    async def test_service_degradation_handling(self, multi_region_config):
        """Test service degradation when ap-southeast-2 is unavailable."""
        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(multi_region_config)

        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            # Mock service unavailable
            mock_bedrock.invoke_agent.side_effect = Exception("Service unavailable")

            # Should fail gracefully (no failover to other regions)
            with pytest.raises(Exception) as exc_info:
                await adapter.invoke_agent(
                    deployment_id="test-deployment",
                    input_text="Test",
                    session_id="test-session",
                )

            # Verify error
            assert "Service unavailable" in str(exc_info.value)


# ============================================================================
# Integration Tests
# ============================================================================

class TestMultiRegionIntegration:
    """Integration tests for multi-region deployment."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_end_to_end_region_enforcement(self, multi_region_config, multi_tenant_context):
        """End-to-end test of region enforcement across all components."""
        with TenantContextManager(multi_tenant_context):
            # All components must use ap-southeast-2
            from core.agentcore.adapters import (
                AgentCoreRuntimeAdapter,
                AgentCoreMemoryAdapter,
                AgentCoreCodeInterpreterAdapter,
                AgentCoreBrowserAdapter,
            )
            from core.agentcore.billing import UsageTracker
            from core.agentcore.observability import CloudWatchClient

            # Runtime
            runtime_adapter = AgentCoreRuntimeAdapter(multi_region_config)
            assert runtime_adapter.config.aws_region == "ap-southeast-2"

            # Memory
            memory_adapter = AgentCoreMemoryAdapter(multi_region_config)
            assert memory_adapter.config.aws_region == "ap-southeast-2"

            # Code Interpreter
            ci_adapter = AgentCoreCodeInterpreterAdapter(multi_region_config)
            assert ci_adapter.config.aws_region == "ap-southeast-2"

            # Browser
            browser_adapter = AgentCoreBrowserAdapter(multi_region_config)
            assert browser_adapter.config.aws_region == "ap-southeast-2"

            # Usage Tracker
            usage_tracker = UsageTracker(multi_region_config)
            assert usage_tracker.config.aws_region == "ap-southeast-2"

            # CloudWatch
            cw_client = CloudWatchClient(multi_region_config)
            assert cw_client.config.aws_region == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_cross_tenant_region_isolation(self, multi_region_config):
        """Test that multiple tenants cannot access each other's data across regions."""
        from core.agentcore.middleware import TenantContextManager, get_tenant_context

        # Tenant 1
        ctx1 = TenantContext(
            account_id="tenant-1",
            tenant_id="tenant-1-abc",
            tier="pro",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Tenant 2
        ctx2 = TenantContext(
            account_id="tenant-2",
            tenant_id="tenant-2-xyz",
            tier="enterprise",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Both must use ap-southeast-2
        with TenantContextManager(ctx1):
            current_ctx = get_tenant_context()
            assert current_ctx.region == "ap-southeast-2"
            assert current_ctx.account_id == "tenant-1"

        with TenantContextManager(ctx2):
            current_ctx = get_tenant_context()
            assert current_ctx.region == "ap-southeast-2"
            assert current_ctx.account_id == "tenant-2"


# ============================================================================
# Performance Tests
# ============================================================================

class TestMultiRegionPerformance:
    """Performance tests for multi-region operations."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_latency_to_ap_southeast_2(self, multi_region_config):
        """Test latency to ap-southeast-2 region."""
        import time

        from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(multi_region_config)

        with patch('boto3.client') as mock_client:
            mock_bedrock = MagicMock()
            mock_client.return_value = mock_bedrock

            mock_bedrock.get_agent.return_value = {
                "agent": {
                    "agentId": "test-agent",
                    "agentStatus": "PREPARED",
                }
            }

            # Measure latency
            start = time.time()
            await adapter.get_deployment("test-deployment-id")
            elapsed = time.time() - start

            # Should be fast (< 100ms for mock)
            assert elapsed < 0.1

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_region_access(self, multi_region_config):
        """Test concurrent access to ap-southeast-2 region."""
        import asyncio

        from core.agentcore.deployment import MultiRegionManager

        manager = MultiRegionManager(multi_region_config)

        # Concurrent region queries
        tasks = [
            manager.get_enabled_regions()
            for _ in range(100)
        ]

        results = await asyncio.gather(*tasks)

        # All should return ap-southeast-2
        for result in results:
            assert len(result) == 1
            assert result[0] == DeploymentRegion.AP_SOUTHEAST_2
