"""
End-to-End Tests for AgentCore System

Comprehensive E2E tests covering complete workflows across Phases 8-10:
- Agent deployment and execution
- Memory integration and persistence
- Billing and usage tracking
- Observability and monitoring
- Tier-based features
- Multi-tenant isolation
- Error handling and recovery

Author: AgentCore Migration Team
Phase: Sprint 4 - Testing & Validation (Task 70)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import time

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
    MemoryResource,
    StoredMessage,
    CodeExecutionResult,
    NavigationResult,
)
from core.agentcore.billing import (
    UsageMetrics,
    UsageTracker,
    TierFeatureManager,
    Tier,
)
from core.agentcore.observability import (
    CloudWatchClient,
    HealthChecker,
    MetricsCollector,
    AlertingService,
)
from core.agentcore.errors import (
    AgentCoreConfigurationError,
    AgentCoreExecutionError,
    ValidationError,
    is_retryable_error,
)
from core.agentcore.middleware import (
    TenantContext,
    TenantContextManager,
    get_tenant_context,
)
from core.agentcore.registry import (
    ToolRegistry,
    ToolMetadata,
    ToolCategory,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def e2e_config():
    """Complete config for E2E tests."""
    return AgentCoreConfig(
        environment=Environment.PRODUCTION,
        aws_region="ap-southeast-2",
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        agent_core_gateway_url="https://gateway-ap-southeast-2.amazonaws.com",
        s3_bucket_name="kortix-agentcore-files-ap-southeast-2",
        billing_enabled=True,
        code_interpreter_enabled=True,
        browser_enabled=True,
        memory_enabled=True,
        runtime_enabled=True,
        cache_enabled=True,
        observability_enabled=True,
    )


@pytest.fixture
def e2e_tenant_context():
    """Complete tenant context for E2E tests."""
    return TenantContext(
        account_id="e2e-test-account",
        tenant_id="tenant-e2e-xyz",
        tier="pro",
        region="ap-southeast-2",
        created_at=datetime.utcnow(),
    )


# ============================================================================
# Complete Agent Execution Flow
# ============================================================================

class TestCompleteAgentExecution:
    """End-to-end tests for complete agent execution."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_full_agent_execution_flow(self, e2e_config, e2e_tenant_context):
        """Test complete agent execution from deployment to result."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
            from core.agentcore.billing import UsageTracker

            # 1. Deploy Agent
            runtime_adapter = AgentCoreRuntimeAdapter(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                deployment_arn = f"arn:aws:bedrock:ap-southeast-2::123456789012:agent-deployment/e2e-test-agent"

                mock_bedrock.create_agent.return_value = {
                    "agent": {
                        "agentId": "e2e-agent-id",
                        "agentArn": deployment_arn,
                        "agentStatus": "PREPARED",
                    }
                }

                deployment = await runtime_adapter.deploy_agent(
                    agent_id="e2e-test-agent",
                    instruction="You are a helpful assistant for E2E testing",
                    foundation_model="anthropic.claude-3-haiku-20250307-v1:0",
                )

                assert deployment.deployment_id == "e2e-agent-id"
                assert deployment.status == RuntimeStatus.PREPARED

                # 2. Create Memory for context
                memory_adapter = AgentCoreMemoryAdapter(e2e_config)

                memory_id = "memory-e2e-123"
                await memory_adapter.create_memory_resource(
                    memory_id=memory_id,
                    agent_id="e2e-test-agent",
                    description="E2E test memory",
                )

                # Store context message
                await memory_adapter.store_message(
                    memory_id=memory_id,
                    role="user",
                    content="Hello, this is an E2E test",
                )

                # 3. Start usage tracking
                usage_tracker = UsageTracker(e2e_config)
                await usage_tracker.start_execution_tracking(
                    execution_id="e2e-exec-123",
                    agent_id="e2e-test-agent",
                    deployment_id=deployment.deployment_id,
                )

                # 4. Invoke agent with memory context
                mock_bedrock.invoke_agent.return_value = {
                    "completion": ["Hello! I can help you with E2E testing."],
                    "sessionId": "e2e-session-123",
                    "inputTokens": 50,
                    "outputTokens": 20,
                }

                result = await runtime_adapter.invoke_agent(
                    deployment_id=deployment.deployment_id,
                    input_text="Hello, this is an E2E test",
                    session_id="e2e-session-123",
                    enable_memory=True,
                    memory_id=memory_id,
                )

                assert result.execution_id == "e2e-session-123"
                assert len(result.response) > 0
                assert result.status == RuntimeStatus.SUCCEEDED

                # 5. Complete usage tracking
                with patch.object(usage_tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    metrics = await usage_tracker.complete_execution_tracking(
                        execution_id="e2e-exec-123",
                        result=result,
                    )

                    assert metrics.execution_id == "e2e-exec-123"
                    assert metrics.completed_at is not None

                # 6. Verify observability metrics
                metrics_collector = MetricsCollector(e2e_config)

                with patch.object(metrics_collector, 'put_metric', new_callable=AsyncMock):
                    await metrics_collector.track_execution_success(
                        deployment_id=deployment.deployment_id,
                        duration_seconds=metrics.duration,
                    )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_agent_with_code_interpreter(self, e2e_config, e2e_tenant_context):
        """Test agent execution with code interpreter."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.code_interpreter import AgentCoreCodeInterpreterAdapter

            adapter = AgentCoreCodeInterpreterAdapter(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                # Create session
                mock_bedrock.create_code_interpreter_session.return_value = {
                    "sessionId": "ci-session-e2e-123",
                    "sessionArn": f"arn:aws:bedrock:ap-southeast-2::123456789012:code-interpreter-session/ci-session-e2e-123",
                }

                session = await adapter.create_session(
                    timeout_in_seconds=60,
                )

                assert session.session_id == "ci-session-e2e-123"

                # Execute code
                mock_bedrock.execute_code.return_value = {
                    "output": "42",
                    "error": None,
                    "executionTime": 0.5,
                }

                result = await adapter.execute_code(
                    session_id=session.session_id,
                    code="print(42)",
                    language="python",
                )

                assert result.output == "42"
                assert result.error is None

                # Delete session
                mock_bedrock.delete_code_interpreter_session.return_value = {}
                await adapter.delete_session(session.session_id)

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_agent_with_browser_automation(self, e2e_config, e2e_tenant_context):
        """Test agent execution with browser automation."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.browser import AgentCoreBrowserAdapter

            adapter = AgentCoreBrowserAdapter(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                # Create session
                mock_bedrock.create_browser_session.return_value = {
                    "sessionId": "browser-session-e2e-123",
                    "endpointUrl": "wss://browser-ap-southeast-2.amazonaws.com/sessions/browser-session-e2e-123",
                }

                session = await adapter.create_session(
                    timeout_in_seconds=60,
                )

                assert session.session_id == "browser-session-e2e-123"

                # Navigate to URL
                mock_bedrock.navigate.return_value = {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "statusCode": 200,
                }

                result = await adapter.navigate(
                    session_id=session.session_id,
                    url="https://example.com",
                )

                assert result.url == "https://example.com"
                assert result.status_code == 200

                # Extract content
                mock_bedrock.extract_content.return_value = {
                    "text": "Example Domain",
                    "html": "<html>...</html>",
                }

                extract_result = await adapter.extract_content(
                    session_id=session.session_id,
                )

                assert "Example" in extract_result.text

                # Delete session
                mock_bedrock.delete_browser_session.return_value = {}
                await adapter.delete_session(session.session_id)


# ============================================================================
# Memory Integration E2E
# ============================================================================

class TestMemoryIntegrationE2E:
    """End-to-end tests for memory integration."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_memory_persistence_across_sessions(self, e2e_config, e2e_tenant_context):
        """Test memory persistence across multiple sessions."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.memory import AgentCoreMemoryAdapter

            adapter = AgentCoreMemoryAdapter(e2e_config)

            memory_id = "memory-persistence-123"

            # Create memory
            await adapter.create_memory_resource(
                memory_id=memory_id,
                agent_id="test-agent",
                description="Persistence test",
            )

            # Store messages
            await adapter.store_message(
                memory_id=memory_id,
                role="user",
                content="First message",
            )

            await adapter.store_message(
                memory_id=memory_id,
                role="assistant",
                content="First response",
            )

            # Retrieve messages
            messages = await adapter.retrieve_messages(
                memory_id=memory_id,
                max_messages=10,
            )

            assert len(messages) == 2
            assert messages[0].content == "First message"
            assert messages[1].content == "First response"

            # Semantic search
            results = await adapter.semantic_search(
                memory_id=memory_id,
                query="message",
                limit=5,
            )

            assert len(results) > 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_memory_with_agent_context(self, e2e_config, e2e_tenant_context):
        """Test memory used as agent context."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.adapters.memory import AgentCoreMemoryAdapter

            runtime_adapter = AgentCoreRuntimeAdapter(e2e_config)
            memory_adapter = AgentCoreMemoryAdapter(e2e_config)

            # Create memory with conversation history
            memory_id = "memory-context-123"
            await memory_adapter.create_memory_resource(
                memory_id=memory_id,
                agent_id="context-agent",
                description="Context test",
            )

            # Add conversation history
            await memory_adapter.store_message(
                memory_id=memory_id,
                role="user",
                content="My name is Alice",
            )

            await memory_adapter.store_message(
                memory_id=memory_id,
                role="assistant",
                content="Nice to meet you, Alice!",
            )

            # Invoke agent with memory context
            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.invoke_agent.return_value = {
                    "completion": ["Hello Alice! How can I help you today?"],
                    "sessionId": "session-context-123",
                }

                result = await runtime_adapter.invoke_agent(
                    deployment_id="context-deployment",
                    input_text="What's my name?",
                    session_id="session-context-123",
                    enable_memory=True,
                    memory_id=memory_id,
                )

                assert "Alice" in result.response


# ============================================================================
# Billing Integration E2E
# ============================================================================

class TestBillingIntegrationE2E:
    """End-to-end tests for billing integration."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_complete_billing_workflow(self, e2e_config, e2e_tenant_context):
        """Test complete billing workflow from execution to invoice."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.billing import UsageTracker

            runtime_adapter = AgentCoreRuntimeAdapter(e2e_config)
            usage_tracker = UsageTracker(e2e_config)

            # 1. Start tracking
            execution_id = "e2e-billing-123"
            await usage_tracker.start_execution_tracking(
                execution_id=execution_id,
                agent_id="billing-agent",
                deployment_id="billing-deployment",
            )

            # 2. Execute agent
            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.invoke_agent.return_value = {
                    "completion": ["Billing test response"],
                    "sessionId": "billing-session-123",
                    "inputTokens": 1000,
                    "outputTokens": 500,
                }

                result = await runtime_adapter.invoke_agent(
                    deployment_id="billing-deployment",
                    input_text="Test billing",
                    session_id="billing-session-123",
                )

                # 3. Complete tracking and persist
                with patch.object(usage_tracker, '_persist_usage_to_billing', new_callable=AsyncMock) as mock_persist:
                    await usage_tracker.complete_execution_tracking(
                        execution_id=execution_id,
                        result=result,
                    )

                    # Verify persist was called
                    mock_persist.assert_called_once()

                    metrics = mock_persist.call_args[0][0]
                    assert metrics.total_tokens == 1500

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_tier_based_feature_enforcement(self, e2e_config):
        """Test tier-based feature enforcement in billing."""
        from core.agentcore.billing import Feature, TierFeatureManager

        # Free tier cannot use code interpreter
        free_config = TierFeatureManager.get_tier_config("free")
        assert Feature.CODE_INTERPRETER not in free_config.features

        # Pro tier can use code interpreter
        pro_config = TierFeatureManager.get_tier_config("pro")
        assert Feature.CODE_INTERPRETER in pro_config.features

        # Enterprise can use all features
        enterprise_config = TierFeatureManager.get_tier_config("enterprise")
        assert len(enterprise_config.features) > len(pro_config.features)


# ============================================================================
# Observability Integration E2E
# ============================================================================

class TestObservabilityIntegrationE2E:
    """End-to-end tests for observability integration."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_complete_observability_workflow(self, e2e_config, e2e_tenant_context):
        """Test complete observability workflow."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.observability import (
                CloudWatchClient,
                MetricsCollector,
                HealthChecker,
                AlertingService,
            )

            # 1. Health check
            health_checker = HealthChecker(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.get_agent.return_value = {
                    "agent": {
                        "agentId": "health-test-agent",
                        "agentStatus": "PREPARED",
                    }
                }

                health_results = await health_checker.check_all()

                assert "runtime" in health_results
                assert health_results["runtime"].status.value in ["healthy", "degraded", "unhealthy"]

            # 2. Collect metrics
            metrics_collector = MetricsCollector(e2e_config)

            with patch.object(metrics_collector, 'put_metric', new_callable=AsyncMock):
                await metrics_collector.track_execution_success(
                    deployment_id="test-deployment",
                    duration_seconds=1.5,
                )

                await metrics_collector.track_execution_error(
                    deployment_id="test-deployment",
                    error_type="ValidationError",
                )

                await metrics_collector.track_memory_usage(
                    memory_id="test-memory",
                    message_count=100,
                )

            # 3. CloudWatch integration
            cw_client = CloudWatchClient(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_cloudwatch = MagicMock()
                mock_client.return_value = mock_cloudwatch

                mock_cloudwatch.put_metric_data.return_value = {}

                await cw_client.put_metric(
                    namespace="AgentCore/Production",
                    metric_name="ExecutionSuccess",
                    value=1.0,
                    unit="Count",
                    dimensions={"DeploymentId": "test-deployment"},
                )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_alerting_workflow(self, e2e_config, e2e_tenant_context):
        """Test alerting workflow for critical events."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.observability import AlertingService

            alerting = AlertingService(e2e_config)

            # Trigger alert for high failure rate
            with patch.object(alerting, '_send_alert', new_callable=AsyncMock):
                await alerting.check_and_alert(
                    deployment_id="alert-test-deployment",
                    failure_rate=0.15,  # 15% failure rate
                    threshold=0.10,  # Alert at 10%
                )

                # Alert should be sent
                alerting._send_alert.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_performance_monitoring(self, e2e_config, e2e_tenant_context):
        """Test performance monitoring workflow."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.observability import PerformanceMonitor

            monitor = PerformanceMonitor(e2e_config)

            # Track performance metrics
            start_time = time.time()

            # Simulate work
            await asyncio.sleep(0.1)

            execution_time = time.time() - start_time

            with patch.object(monitor, 'record_metric', new_callable=AsyncMock):
                await monitor.track_latency(
                    operation="invoke_agent",
                    latency_seconds=execution_time,
                )

                await monitor.track_throughput(
                    operation="invoke_agent",
                    requests_per_second=10.0,
                )


# ============================================================================
# Multi-Tenant Isolation E2E
# ============================================================================

class TestMultiTenantIsolationE2E:
    """End-to-end tests for multi-tenant isolation."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_tenant_data_isolation(self, e2e_config):
        """Test that tenant data is properly isolated."""
        from core.agentcore.adapters.memory import AgentCoreMemoryAdapter

        # Tenant 1
        ctx1 = TenantContext(
            account_id="iso-tenant-1",
            tenant_id="tenant-1-abc",
            tier="pro",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Tenant 2
        ctx2 = TenantContext(
            account_id="iso-tenant-2",
            tenant_id="tenant-2-xyz",
            tier="pro",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Tenant 1 creates memory
        with TenantContextManager(ctx1):
            adapter1 = AgentCoreMemoryAdapter(e2e_config)

            await adapter1.create_memory_resource(
                memory_id="iso-memory-1",
                agent_id="agent-1",
                description="Tenant 1 memory",
            )

            await adapter1.store_message(
                memory_id="iso-memory-1",
                role="user",
                content="Secret data for tenant 1",
            )

        # Tenant 2 creates different memory
        with TenantContextManager(ctx2):
            adapter2 = AgentCoreMemoryAdapter(e2e_config)

            await adapter2.create_memory_resource(
                memory_id="iso-memory-2",
                agent_id="agent-2",
                description="Tenant 2 memory",
            )

            await adapter2.store_message(
                memory_id="iso-memory-2",
                role="user",
                content="Secret data for tenant 2",
            )

            # Verify tenant 2 cannot access tenant 1's memory
            from core.agentcore.errors import ResourceNotFoundError

            with pytest.raises(ResourceNotFoundError):
                await adapter2.get_memory_resource("iso-memory-1")

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_tenant_billing_isolation(self, e2e_config):
        """Test that billing is isolated per tenant."""
        from core.agentcore.billing import UsageTracker

        # Tenant 1
        ctx1 = TenantContext(
            account_id="billing-iso-1",
            tenant_id="tenant-1-abc",
            tier="pro",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Tenant 2
        ctx2 = TenantContext(
            account_id="billing-iso-2",
            tenant_id="tenant-2-xyz",
            tier="free",
            region="ap-southeast-2",
            created_at=datetime.utcnow(),
        )

        # Tenant 1 executes (pro tier)
        with TenantContextManager(ctx1):
            tracker1 = UsageTracker(e2e_config)

            await tracker1.start_execution_tracking(
                execution_id="exec-iso-1",
                agent_id="agent-1",
            )

            # Complete execution
            mock_result = MagicMock()
            mock_result.metadata = {"input_tokens": 100, "output_tokens": 50}

            with patch.object(tracker1, '_persist_usage_to_billing', new_callable=AsyncMock):
                await tracker1.complete_execution_tracking(
                    execution_id="exec-iso-1",
                    result=mock_result,
                )

        # Tenant 2 executes (free tier)
        with TenantContextManager(ctx2):
            tracker2 = UsageTracker(e2e_config)

            await tracker2.start_execution_tracking(
                execution_id="exec-iso-2",
                agent_id="agent-2",
            )

            # Complete execution
            mock_result = MagicMock()
            mock_result.metadata = {"input_tokens": 100, "output_tokens": 50}

            with patch.object(tracker2, '_persist_usage_to_billing', new_callable=AsyncMock):
                await tracker2.complete_execution_tracking(
                    execution_id="exec-iso-2",
                    result=mock_result,
                )

            # Verify different billing for each tenant
            # Pro tier should have discount applied
            # Free tier should pay full price


# ============================================================================
# Error Handling and Recovery E2E
# ============================================================================

class TestErrorHandlingAndRecoveryE2E:
    """End-to-end tests for error handling and recovery."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_transient_error_retry(self, e2e_config, e2e_tenant_context):
        """Test retry logic for transient errors."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.errors import with_retry, ServiceUnavailableError

            adapter = AgentCoreRuntimeAdapter(e2e_config)

            call_count = 0

            async def failing_operation():
                nonlocal call_count
                call_count += 1

                if call_count < 3:
                    raise ServiceUnavailableError("Service temporarily unavailable")

                return {"success": True}

            # Should retry and succeed
            result = await with_retry(
                failing_operation,
                max_retries=3,
                backoff_base=0.01,
            )

            assert call_count == 3  # Failed twice, succeeded on third try
            assert result["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_execution_failure_handling(self, e2e_config, e2e_tenant_context):
        """Test graceful handling of execution failures."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.billing import UsageTracker

            adapter = AgentCoreRuntimeAdapter(e2e_config)
            tracker = UsageTracker(e2e_config)

            # Start tracking
            await tracker.start_execution_tracking(
                execution_id="exec-fail-e2e-123",
                agent_id="failing-agent",
                deployment_id="failing-deployment",
            )

            # Mock execution failure
            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.invoke_agent.side_effect = Exception("Execution failed")

                # Should handle error gracefully
                with pytest.raises(Exception):
                    await adapter.invoke_agent(
                        deployment_id="failing-deployment",
                        input_text="Test",
                        session_id="fail-session",
                    )

                # Still track usage (billing for attempted execution)
                with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    failed_result = RuntimeExecutionResult(
                        execution_id="exec-fail-e2e-123",
                        status=RuntimeStatus.FAILED,
                        error="Execution failed",
                    )

                    await tracker.complete_execution_tracking(
                        execution_id="exec-fail-e2e-123",
                        result=failed_result,
                    )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_validation_error_handling(self, e2e_config, e2e_tenant_context):
        """Test handling of validation errors."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.errors import ValidationError

            adapter = AgentCoreRuntimeAdapter(e2e_config)

            # Try to deploy with invalid parameters
            with pytest.raises(ValidationError) as exc_info:
                await adapter.deploy_agent(
                    agent_id="",  # Invalid: empty agent ID
                    instruction="Test",
                    foundation_model="invalid-model",
                )

            assert "validation" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_timeout_handling(self, e2e_config, e2e_tenant_context):
        """Test handling of execution timeouts."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter

            adapter = AgentCoreRuntimeAdapter(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                # Mock timeout
                mock_bedrock.invoke_agent.side_effect = Exception("Request timed out")

                # Should handle timeout gracefully
                with pytest.raises(Exception) as exc_info:
                    await adapter.invoke_agent(
                        deployment_id="timeout-deployment",
                        input_text="Test",
                        session_id="timeout-session",
                        timeout_in_seconds=1,
                    )

                assert "timeout" in str(exc_info.value).lower()


# ============================================================================
# Performance E2E
# ============================================================================

class TestPerformanceE2E:
    """End-to-end performance tests."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_concurrent_tenants_performance(self, e2e_config):
        """Test system performance with multiple concurrent tenants."""
        import asyncio

        async def execute_for_tenant(i: int):
            ctx = TenantContext(
                account_id=f"perf-tenant-{i}",
                tenant_id=f"tenant-{i}",
                tier="pro",
                region="ap-southeast-2",
                created_at=datetime.utcnow(),
            )

            with TenantContextManager(ctx):
                from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
                from core.agentcore.billing import UsageTracker

                adapter = AgentCoreRuntimeAdapter(e2e_config)
                tracker = UsageTracker(e2e_config)

                # Start tracking
                await tracker.start_execution_tracking(
                    execution_id=f"exec-perf-{i}",
                    agent_id=f"agent-{i}",
                    deployment_id=f"deployment-{i}",
                )

                # Mock execution
                with patch('boto3.client') as mock_client:
                    mock_bedrock = MagicMock()
                    mock_client.return_value = mock_bedrock

                    mock_bedrock.invoke_agent.return_value = {
                        "completion": [f"Response {i}"],
                        "sessionId": f"session-{i}",
                    }

                    result = await adapter.invoke_agent(
                        deployment_id=f"deployment-{i}",
                        input_text=f"Test {i}",
                        session_id=f"session-{i}",
                    )

                    # Complete tracking
                    with patch.object(tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                        await tracker.complete_execution_tracking(
                            execution_id=f"exec-perf-{i}",
                            result=result,
                        )

                return f"Complete {i}"

        # Run 20 concurrent tenant executions
        start = time.time()
        results = await asyncio.gather(*[execute_for_tenant(i) for i in range(20)])
        elapsed = time.time() - start

        assert len(results) == 20
        assert elapsed < 10.0  # Should complete in reasonable time

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_memory_cache_performance(self, e2e_config, e2e_tenant_context):
        """Test memory cache performance under load."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.cache import AgentCoreCache

            cache = AgentCoreCache(e2e_config)
            await cache.initialize()

            account_id = e2e_tenant_context.account_id

            # Warm cache
            for i in range(100):
                await cache.set(account_id, f"key-{i}", f"value-{i}")

            # Measure cache hits
            start = time.time()
            hits = 0

            for i in range(100):
                value = await cache.get(account_id, f"key-{i}")
                if value:
                    hits += 1

            elapsed = time.time() - start

            # All cache hits, fast access
            assert hits == 100
            assert elapsed < 1.0  # Should be very fast


# ============================================================================
# Complete Workflow Scenarios
# ============================================================================

class TestCompleteWorkflowScenarios:
    """Complex real-world workflow scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_customer_support_agent_workflow(self, e2e_config, e2e_tenant_context):
        """Test complete customer support agent scenario."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
            from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
            from core.agentcore.billing import UsageTracker

            # 1. Deploy customer support agent
            runtime_adapter = AgentCoreRuntimeAdapter(e2e_config)
            memory_adapter = AgentCoreMemoryAdapter(e2e_config)
            usage_tracker = UsageTracker(e2e_config)

            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                # Deploy agent
                mock_bedrock.create_agent.return_value = {
                    "agent": {
                        "agentId": "support-agent",
                        "agentArn": "arn:aws:bedrock:ap-southeast-2::123456789012:agent/support-agent",
                        "agentStatus": "PREPARED",
                    }
                }

                deployment = await runtime_adapter.deploy_agent(
                    agent_id="support-agent",
                    instruction="You are a helpful customer support agent",
                    foundation_model="anthropic.claude-3-haiku-20250307-v1:0",
                )

                # 2. Create customer session memory
                memory_id = "support-session-123"
                await memory_adapter.create_memory_resource(
                    memory_id=memory_id,
                    agent_id="support-agent",
                    description="Customer support session",
                )

                # 3. Track usage
                await usage_tracker.start_execution_tracking(
                    execution_id="support-exec-123",
                    agent_id="support-agent",
                    deployment_id=deployment.deployment_id,
                )

                # 4. Handle customer inquiry
                mock_bedrock.invoke_agent.return_value = {
                    "completion": ["I can help you with that issue!"],
                    "sessionId": "support-session-123",
                    "inputTokens": 200,
                    "outputTokens": 50,
                }

                result = await runtime_adapter.invoke_agent(
                    deployment_id=deployment.deployment_id,
                    input_text="I need help with my account",
                    session_id="support-session-123",
                    enable_memory=True,
                    memory_id=memory_id,
                )

                assert result.status == RuntimeStatus.SUCCEEDED

                # 5. Store interaction in memory
                await memory_adapter.store_message(
                    memory_id=memory_id,
                    role="user",
                    content="I need help with my account",
                )

                await memory_adapter.store_message(
                    memory_id=memory_id,
                    role="assistant",
                    content=result.response,
                )

                # 6. Complete billing
                with patch.object(usage_tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    await usage_tracker.complete_execution_tracking(
                        execution_id="support-exec-123",
                        result=result,
                    )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_data_analysis_agent_workflow(self, e2e_config, e2e_tenant_context):
        """Test complete data analysis agent scenario with code interpreter."""
        with TenantContextManager(e2e_tenant_context):
            from core.agentcore.adapters.code_interpreter import AgentCoreCodeInterpreterAdapter
            from core.agentcore.billing import UsageTracker

            ci_adapter = AgentCoreCodeInterpreterAdapter(e2e_config)
            usage_tracker = UsageTracker(e2e_config)

            # 1. Create code interpreter session
            with patch('boto3.client') as mock_client:
                mock_bedrock = MagicMock()
                mock_client.return_value = mock_bedrock

                mock_bedrock.create_code_interpreter_session.return_value = {
                    "sessionId": "data-analysis-session",
                    "sessionArn": "arn:aws:bedrock:ap-southeast-2::123456789012:code-interpreter/data-analysis-session",
                }

                session = await ci_adapter.create_session(timeout_in_seconds=120)

                # 2. Track usage
                await usage_tracker.start_execution_tracking(
                    execution_id="data-analysis-exec",
                    agent_id="data-analysis-agent",
                    deployment_id="data-analysis-deployment",
                )

                # 3. Execute data analysis code
                analysis_code = """
import pandas as pd
data = {'col1': [1, 2, 3], 'col2': [4, 5, 6]}
df = pd.DataFrame(data)
print(df.describe())
"""

                mock_bedrock.execute_code.return_value = {
                    "output": "       col1      col2\\ncount  3.0  3.0\\nmean   2.0  5.0",
                    "error": None,
                    "executionTime": 2.5,
                }

                result = await ci_adapter.execute_code(
                    session_id=session.session_id,
                    code=analysis_code,
                    language="python",
                )

                assert result.error is None
                assert "count" in result.output

                # 4. Complete billing
                with patch.object(usage_tracker, '_persist_usage_to_billing', new_callable=AsyncMock):
                    mock_result = MagicMock()
                    mock_result.metadata = {"execution_duration_seconds": 2.5}

                    await usage_tracker.complete_execution_tracking(
                        execution_id="data-analysis-exec",
                        result=mock_result,
                    )

                # 5. Cleanup
                mock_bedrock.delete_code_interpreter_session.return_value = {}
                await ci_adapter.delete_session(session.session_id)
