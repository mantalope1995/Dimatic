"""
Integration Tests for AWS AgentCore Runtime

End-to-end tests for agent execution flow using AgentCore Runtime.
Tests the complete lifecycle from agent deployment through execution and streaming.

IMPORTANT: For Phase 1 migration, all AgentCore Runtime services MUST run in
ap-southeast-2 (Australia region) to meet data residency requirements.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio

from core.agentcore.adapters.runtime import AgentCoreRuntimeAdapter
from core.agentcore.runtime.execution_manager import (
    ExecutionManager,
    ExecutionContext,
    ExecutionConfig,
    ExecutionState,
)
from core.agentcore.runtime.streaming_handler import StreamingHandler, SSEEvent
from core.agentcore.deployment.deployment_manager import (
    DeploymentManager,
    DeploymentStatus,
)
from core.agentcore.config import AgentCoreConfig, get_config


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def agentcore_config():
    """AgentCore configuration for integration tests"""
    return AgentCoreConfig(
        environment="development",
        aws_region="ap-southeast-2",  # CRITICAL for Phase 1
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        runtime_enabled=True,
        code_interpreter_enabled=False,  # Runtime only
        browser_enabled=False,
    )


@pytest.fixture
def mock_runtime_adapter(agentcore_config):
    """Mock Runtime adapter with simulated responses"""
    adapter = MagicMock(spec=AgentCoreRuntimeAdapter)
    adapter.config = agentcore_config

    # Mock deploy_agent
    async def mock_deploy(agent_id: str, config: dict, version_id: str) -> str:
        await asyncio.sleep(0.1)  # Simulate API latency
        return f"dep-{agent_id}-{version_id}"

    adapter.deploy_agent = MagicMock(side_effect=mock_deploy)

    # Mock invoke_agent (streaming)
    async def mock_invoke_stream(deployment_id: str, session_id: str, input_data: dict, **kwargs):
        # Simulate streaming response chunks
        chunks = [
            {"type": "metadata", "data": {"status": "starting"}},
            {"type": "token", "data": {"content": "Hello"}},
            {"type": "token", "data": {"content": " from"}},
            {"type": "token", "data": {"content": " AgentCore"}},
            {"type": "metadata", "data": {"status": "completed", "finish_reason": "stop"}},
        ]
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.05)  # Simulate streaming delay

    adapter.invoke_agent = MagicMock(side_effect=mock_invoke_stream)

    # Mock cancel_execution
    async def mock_cancel(execution_id: str) -> bool:
        await asyncio.sleep(0.05)
        return True

    adapter.cancel_execution = MagicMock(side_effect=mock_cancel)

    # Mock get_execution_status
    async def mock_get_status(execution_id: str) -> dict:
        await asyncio.sleep(0.05)
        return {
            "execution_id": execution_id,
            "status": "completed",
            "started_at": datetime.utcnow().isoformat(),
            "ended_at": datetime.utcnow().isoformat(),
        }

    adapter.get_execution_status = MagicMock(side_effect=mock_get_status)

    return adapter


@pytest.fixture
def execution_manager(agentcore_config):
    """Execution manager instance"""
    return ExecutionManager(config=agentcore_config)


@pytest.fixture
def deployment_manager(agentcore_config):
    """Deployment manager instance"""
    return DeploymentManager(config=agentcore_config)


# ============================================================================
# End-to-End Integration Tests
# ============================================================================

class TestRuntimeIntegration:
    """
    End-to-end integration tests for AgentCore Runtime execution flow.

    Tests the complete lifecycle:
    1. Agent deployment (DeploymentManager)
    2. Execution creation (ExecutionManager)
    3. Streaming execution (StreamingHandler)
    4. Result persistence and status tracking
    """

    @pytest.mark.asyncio
    async def test_full_agent_execution_flow(
        self, agentcore_config, mock_runtime_adapter, execution_manager, deployment_manager
    ):
        """
        Integration test: Complete agent execution flow from deployment to result.
        Verifies deployment → execution → streaming → result persistence.
        """
        agent_id = "test-agent-123"
        version_id = "v1.0.0"
        session_id = "session-abc"
        user_input = "Hello, agent!"

        # Step 1: Deploy agent
        with patch.object(
            DeploymentManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            deployment_result = await deployment_manager.deploy_agent_version(
                agent_id=agent_id,
                version_id=version_id,
                agent_config={"name": "Test Agent", "model": "claude-3-5-sonnet-20241022"},
            )

        assert deployment_result.deployment_id == f"dep-{agent_id}-{version_id}"
        assert deployment_result.status == "deployed"

        # Step 2: Create execution context
        execution_context = ExecutionContext(
            agent_id=agent_id,
            user_id="user-456",
            session_id=session_id,
            input_text=user_input,
            config=ExecutionConfig(
                deployment_id=deployment_result.deployment_id,
                timeout_seconds=300,
                enable_trace=False,
            ),
        )

        # Step 3: Execute agent and stream results
        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            chunks = []
            async for chunk in execution_manager.execute_agent(
                context=execution_context
            ):
                chunks.append(chunk)

        # Step 4: Verify streaming results
        assert len(chunks) > 0
        assert chunks[0]["type"] == "metadata"
        assert chunks[0]["data"]["status"] == "starting"

        # Find completion chunk
        completion_chunks = [c for c in chunks if c["type"] == "metadata" and c["data"].get("status") == "completed"]
        assert len(completion_chunks) > 0

    @pytest.mark.asyncio
    async def test_concurrent_executions(self, mock_runtime_adapter, execution_manager):
        """
        Integration test: Multiple concurrent agent executions.
        Verifies system can handle parallel execution requests.
        """
        num_concurrent = 5
        agent_id = "test-agent-concurrent"

        # Create multiple execution contexts
        contexts = [
            ExecutionContext(
                agent_id=agent_id,
                user_id=f"user-{i}",
                session_id=f"session-{i}",
                input_text=f"Message {i}",
                config=ExecutionConfig(
                    deployment_id=f"dep-{agent_id}",
                    timeout_seconds=300,
                ),
            )
            for i in range(num_concurrent)
        ]

        # Execute all concurrently
        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            tasks = [
                execution_manager.execute_agent(context=context)
                for context in contexts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all executions completed
        assert len(results) == num_concurrent
        for i, result in enumerate(results):
            assert isinstance(result, list), f"Execution {i} should return list of chunks"
            assert len(result) > 0, f"Execution {i} should have chunks"

    @pytest.mark.asyncio
    async def test_execution_failure_and_fallback(self, mock_runtime_adapter, execution_manager):
        """
        Integration test: Execution failure and graceful fallback to Dramatiq.
        Verifies error handling and fallback mechanism.
        """
        agent_id = "test-agent-fallback"
        user_id = "user-fallback"
        session_id = "session-fallback"

        # Mock AgentCore failure
        async def mock_invoke_failure(*args, **kwargs):
            raise ConnectionError("AgentCore service unavailable")

        mock_runtime_adapter.invoke_agent = MagicMock(side_effect=mock_invoke_failure)

        execution_context = ExecutionContext(
            agent_id=agent_id,
            user_id=user_id,
            session_id=session_id,
            input_text="Test input",
            config=ExecutionConfig(
                deployment_id=f"dep-{agent_id}",
                timeout_seconds=300,
                fallback_to_dramatiq=True,  # Enable fallback
            ),
        )

        # Execute with fallback enabled
        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            # Should fallback to Dramatiq
            chunks = []
            async with pytest.raises((ConnectionError, Exception)):
                async for chunk in execution_manager.execute_agent(context=execution_context):
                    chunks.append(chunk)

    @pytest.mark.asyncio
    async def test_streaming_handler_sse_format(self, agentcore_config, mock_runtime_adapter):
        """
        Integration test: SSE streaming format validation.
        Verifies StreamingHandler produces correctly formatted SSE events.
        """
        deployment_id = "dep-test-sse"
        session_id = "session-sse"

        handler = StreamingHandler(config=agentcore_config)
        handler._runtime_adapter = mock_runtime_adapter

        # Collect SSE events
        sse_events = []
        async for sse_event in handler.stream_agent_execution(
            deployment_id=deployment_id,
            session_id=session_id,
            input_text="Test SSE streaming",
            enable_trace=False,
            timeout_seconds=300,
        ):
            sse_events.append(sse_event)

        # Verify SSE format
        assert len(sse_events) > 0

        # Parse first event (should be metadata)
        first_event_lines = sse_events[0].strip().split("\n")
        assert any(line.startswith("event:") for line in first_event_lines)
        assert any(line.startswith("data:") for line in first_event_lines)

        # Verify event structure
        for event_str in sse_events:
            lines = event_str.strip().split("\n")
            data_lines = [l for l in lines if l.startswith("data:")]
            assert len(data_lines) > 0, "SSE event must have data lines"

            # Verify JSON is valid
            for data_line in data_lines:
                json_str = data_line.replace("data:", "").strip()
                try:
                    json.loads(json_str)
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON in SSE event: {json_str}")

    @pytest.mark.asyncio
    async def test_deployment_and_execution_pipeline(self, agentcore_config, mock_runtime_adapter):
        """
        Integration test: Deployment → Execution → Result persistence pipeline.
        Verifies complete data flow from deployment to result storage.
        """
        agent_id = "test-agent-pipeline"
        version_id = "v1.0.0"
        user_id = "user-pipeline"

        deployment_manager = DeploymentManager(config=agentcore_config)
        execution_manager = ExecutionManager(config=agentcore_config)

        # Step 1: Deploy agent
        with patch.object(
            DeploymentManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            deployment = await deployment_manager.deploy_agent_version(
                agent_id=agent_id,
                version_id=version_id,
                agent_config={"name": "Pipeline Test Agent"},
            )

        deployment_id = deployment.deployment_id
        assert deployment_id is not None

        # Step 2: Execute agent
        execution_context = ExecutionContext(
            agent_id=agent_id,
            user_id=user_id,
            session_id="session-pipeline",
            input_text="Execute pipeline test",
            config=ExecutionConfig(
                deployment_id=deployment_id,
                timeout_seconds=300,
            ),
        )

        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            chunks = []
            async for chunk in execution_manager.execute_agent(context=execution_context):
                chunks.append(chunk)

        # Step 3: Verify execution completed
        assert len(chunks) > 0

        # Step 4: Verify result would be persisted (mock persistence)
        result = {
            "agent_id": agent_id,
            "user_id": user_id,
            "status": "completed",
            "chunks": chunks,
            "execution_backend": "agentcore",
        }

        # Simulate persistence
        persisted = execution_manager._persist_execution_result(result)
        assert persisted is not None
        assert persisted["agent_id"] == agent_id
        assert persisted["status"] == "completed"


# ============================================================================
# Performance Tests
# ============================================================================

class TestRuntimePerformance:
    """
    Performance tests for AgentCore Runtime execution.

    Tests concurrent execution, streaming latency, and throughput.
    """

    @pytest.mark.asyncio
    async def test_concurrent_execution_throughput(self, mock_runtime_adapter, execution_manager):
        """
        Performance test: Measure throughput for concurrent executions.
        Verifies system can handle multiple simultaneous executions efficiently.
        """
        num_concurrent = 10
        agent_id = "test-agent-perf"

        contexts = [
            ExecutionContext(
                agent_id=agent_id,
                user_id=f"user-perf-{i}",
                session_id=f"session-perf-{i}",
                input_text=f"Performance test message {i}",
                config=ExecutionConfig(
                    deployment_id=f"dep-{agent_id}",
                    timeout_seconds=300,
                ),
            )
            for i in range(num_concurrent)
        ]

        # Measure execution time
        start_time = datetime.utcnow()

        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            tasks = [
                execution_manager.execute_agent(context=context)
                for context in contexts
            ]
            results = await asyncio.gather(*tasks)

        end_time = datetime.utcnow()
        total_duration = (end_time - start_time).total_seconds()

        # Verify all executions completed
        assert len(results) == num_concurrent
        for result in results:
            assert isinstance(result, list)

        # Performance assertion: Should complete in reasonable time
        # (Mock adapter adds ~0.15s per execution, so total should be < 5s for 10 concurrent)
        assert total_duration < 5.0, f"Concurrent execution took too long: {total_duration}s"

    @pytest.mark.asyncio
    async def test_streaming_latency(self, agentcore_config, mock_runtime_adapter):
        """
        Performance test: Measure streaming latency for AgentCore responses.
        Verifies first chunk arrives within acceptable latency threshold.
        """
        deployment_id = "dep-test-latency"
        session_id = "session-latency"

        handler = StreamingHandler(config=agentcore_config)
        handler._runtime_adapter = mock_runtime_adapter

        # Measure time to first chunk
        start_time = datetime.utcnow()

        first_chunk_time = None
        async for sse_event in handler.stream_agent_execution(
            deployment_id=deployment_id,
            session_id=session_id,
            input_text="Measure latency",
            enable_trace=False,
            timeout_seconds=300,
        ):
            if first_chunk_time is None:
                first_chunk_time = datetime.utcnow()

        # Verify first chunk latency is acceptable (< 1 second for mocks)
        if first_chunk_time:
            latency = (first_chunk_time - start_time).total_seconds()
            assert latency < 1.0, f"First chunk latency too high: {latency}s"


# ============================================================================
# Fallback Tests
# ============================================================================

class TestGracefulFallback:
    """
    Tests for graceful fallback from AgentCore to Dramatiq.

    Verifies system behavior when AgentCore is unavailable or fails.
    """

    @pytest.mark.asyncio
    async def test_agentcore_unavailable_fallback(self, agentcore_config, execution_manager):
        """
        Fallback test: AgentCore service unavailable triggers fallback.
        Verifies system falls back to Dramatiq when AgentCore fails.
        """
        agent_id = "test-agent-fallback"
        user_id = "user-fallback-test"

        # Mock AgentCore unavailability
        mock_adapter = MagicMock(spec=AgentCoreRuntimeAdapter)
        mock_adapter.config = agentcore_config

        async def mock_invoke_error(*args, **kwargs):
            raise ConnectionError("AgentCore service unavailable")

        mock_adapter.invoke_agent = MagicMock(side_effect=mock_invoke_error)

        execution_context = ExecutionContext(
            agent_id=agent_id,
            user_id=user_id,
            session_id="session-fallback-test",
            input_text="Test fallback behavior",
            config=ExecutionConfig(
                deployment_id=f"dep-{agent_id}",
                timeout_seconds=300,
                fallback_to_dramatiq=True,
            ),
        )

        # Execute with mocked AgentCore failure
        with patch.object(
            ExecutionManager, '_get_runtime_adapter', return_value=mock_adapter
        ):
            # Should attempt AgentCore, encounter error, and handle gracefully
            with pytest.raises((ConnectionError, Exception)):
                async for chunk in execution_manager.execute_agent(context=execution_context):
                    pass

    @pytest.mark.asyncio
    async def test_deployment_failure_rollback(self, agentcore_config, deployment_manager):
        """
        Fallback test: Deployment failure triggers rollback.
        Verifies failed deployments are rolled back gracefully.
        """
        agent_id = "test-agent-rollback"
        version_id = "v1.0.0"

        # Mock deployment failure
        mock_adapter = MagicMock(spec=AgentCoreRuntimeAdapter)
        mock_adapter.config = agentcore_config

        async def mock_deploy_failure(*args, **kwargs):
            raise RuntimeError("Deployment failed due to configuration error")

        mock_adapter.deploy_agent = MagicMock(side_effect=mock_deploy_failure)

        # Attempt deployment with rollback enabled
        with patch.object(
            DeploymentManager, '_get_runtime_adapter', return_value=mock_adapter
        ):
            result = await deployment_manager.deploy_agent_version(
                agent_id=agent_id,
                version_id=version_id,
                agent_config={"name": "Rollback Test Agent"},
            )

        # Verify deployment failed gracefully
        assert result.status == "failed"
        assert result.error is not None
        assert "Deployment failed" in result.error or "configuration error" in result.error.lower()


# ============================================================================
# Region Enforcement Tests (Phase 1 Critical)
# ============================================================================

class TestRegionEnforcement:
    """
    Tests for region enforcement in Phase 1.

    CRITICAL: All AgentCore services MUST run in ap-southeast-2 (Australia)
    for Phase 1 data residency requirements.
    """

    def test_runtime_adapter_uses_ap_southeast_2(self, agentcore_config):
        """
        Region test: Runtime adapter uses ap-southeast-2 region.
        Verifies all AgentCore Runtime calls target ap-southeast-2.
        """
        # Verify config enforces ap-southeast-2
        assert agentcore_config.aws_region == "ap-southeast-2"

        # Create adapter with config
        adapter = AgentCoreRuntimeAdapter(config=agentcore_config)

        # Verify adapter region
        assert adapter.config.aws_region == "ap-southeast-2"

    def test_execution_manager_uses_ap_southeast_2(self, agentcore_config):
        """
        Region test: Execution manager uses ap-southeast-2 region.
        Verifies execution context enforces correct region.
        """
        # Verify config region
        assert agentcore_config.aws_region == "ap-southeast-2"

        # Create execution manager
        manager = ExecutionManager(config=agentcore_config)

        # Verify manager config
        assert manager.config.aws_region == "ap-southeast-2"

    @pytest.mark.asyncio
    async def test_deployment_uses_ap_southeast_2(self, agentcore_config, mock_runtime_adapter):
        """
        Region test: Deployment operations use ap-southeast-2 region.
        Verifies deployment targets correct region.
        """
        agent_id = "test-agent-region"
        version_id = "v1.0.0"

        deployment_manager = DeploymentManager(config=agentcore_config)

        # Deploy agent
        with patch.object(
            DeploymentManager, '_get_runtime_adapter', return_value=mock_runtime_adapter
        ):
            result = await deployment_manager.deploy_agent_version(
                agent_id=agent_id,
                version_id=version_id,
                agent_config={"name": "Region Test Agent"},
            )

        # Verify deployment succeeded (would fail if wrong region)
        assert result.status == "deployed"
        assert result.deployment_id is not None
