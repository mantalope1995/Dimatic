"""
AgentCore Execution Manager

Manages the execution lifecycle of agents using AgentCore Runtime.
Handles state transitions, error recovery, and result persistence.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from ..config import AgentCoreConfig, get_config
from ..models import (
    RuntimeSession,
    RuntimeExecutionResult,
    RuntimeStatus,
    SessionStatus,
)
from ..errors import (
    AgentCoreError,
    AgentCoreExecutionError as ExecutionError,
    AgentCoreRetryableError as TransientError,
    with_retry,
    safe_log,
)
from ..adapters.runtime import (
    AgentCoreRuntimeAdapter,
    RuntimeInvokeParams,
    RuntimeSessionInfo,
)

logger = logging.getLogger(__name__)


class ExecutionState(str, Enum):
    """States in the execution lifecycle"""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class ExecutionContext:
    """
    Context for a single agent execution

    Attributes:
        execution_id: Unique identifier for this execution
        agent_id: Agent being executed
        session_id: Session identifier for conversation continuity
        deployment_id: Runtime deployment identifier
        state: Current execution state
        input_text: User input text
        input_data: Additional input data
        result: Execution result when completed
        created_at: Execution start time
        updated_at: Last state update time
        started_at: Actual execution start time
        completed_at: Execution completion time
        error: Error message if execution failed
        metadata: Additional execution metadata
    """
    execution_id: str
    agent_id: str
    session_id: str
    deployment_id: str
    state: ExecutionState
    input_text: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    result: Optional[RuntimeExecutionResult] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "deployment_id": self.deployment_id,
            "state": self.state.value,
            "input_text": self.input_text,
            "input_data": self.input_data,
            "result": self.result.to_dict() if self.result else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionContext':
        """Create from dictionary for JSON deserialization"""
        data = data.copy()

        # Convert datetime strings back to datetime objects
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('started_at'), str):
            data['started_at'] = datetime.fromisoformat(data['started_at'])
        if isinstance(data.get('completed_at'), str):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])

        # Convert state string back to enum
        if isinstance(data.get('state'), str):
            data['state'] = ExecutionState(data['state'])

        # Convert result dict back to RuntimeExecutionResult
        if data.get('result'):
            data['result'] = RuntimeExecutionResult.from_dict(data['result'])

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutionConfig:
    """
    Configuration for agent execution

    Attributes:
        timeout_seconds: Maximum execution time in seconds
        enable_trace: Enable execution tracing
        enable_streaming: Enable streaming responses
        retry_on_transient_error: Retry on transient errors
        max_retries: Maximum number of retries
        persist_results: Persist results to database
        cleanup_on_complete: Cleanup resources after execution
    """
    timeout_seconds: int = 300
    enable_trace: bool = False
    enable_streaming: bool = True
    retry_on_transient_error: bool = True
    max_retries: int = 3
    persist_results: bool = True
    cleanup_on_complete: bool = True


class ExecutionManager:
    """
    Manages AgentCore Runtime agent execution lifecycle.

    This manager handles:
    1. Creating and managing execution contexts
    2. Executing agents with streaming responses
    3. Tracking execution state transitions
    4. Handling failures and retries
    5. Persisting results

    All executions use the ap-southeast-2 region for Phase 1 compliance.
    """

    # Valid state transitions
    VALID_TRANSITIONS = {
        ExecutionState.INITIALIZING: [ExecutionState.READY, ExecutionState.FAILED],
        ExecutionState.READY: [ExecutionState.RUNNING, ExecutionState.CANCELLED],
        ExecutionState.RUNNING: [
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.TIMEOUT,
        ],
        ExecutionState.COMPLETED: [],
        ExecutionState.FAILED: [],
        ExecutionState.CANCELLED: [],
        ExecutionState.TIMEOUT: [],
    }

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        runtime_adapter: Optional[AgentCoreRuntimeAdapter] = None,
    ):
        """
        Initialize the execution manager.

        Args:
            config: AgentCore configuration. If None, uses global config.
            runtime_adapter: Runtime adapter instance. If None, creates new instance.

        Raises:
            ConfigurationError: If Runtime is not enabled or config is invalid.
        """
        self.config = config or get_config()
        self._validate_config()

        self.runtime_adapter = runtime_adapter or AgentCoreRuntimeAdapter(config=self.config)

        # In-memory execution tracking (in production, use database)
        self._executions: Dict[str, ExecutionContext] = {}

        safe_log("ExecutionManager initialized")

    def _validate_config(self) -> None:
        """Validate configuration for execution manager"""
        if not self.config.runtime_enabled:
            raise ConfigurationError(
                "AgentCore Runtime is not enabled. "
                "Set AGENTCORE_RUNTIME_ENABLED=true to use execution features."
            )

        # Phase 1: Enforce ap-southeast-2 region
        if self.config.aws_region != "ap-southeast-2":
            safe_log(
                f"Execution manager initialized with region '{self.config.aws_region}'. "
                f"Phase 1 requires 'ap-southeast-2' for Runtime executions."
            )

    async def create_execution_context(
        self,
        agent_id: str,
        deployment_id: str,
        input_text: str,
        input_data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:
        """
        Create a new execution context.

        Args:
            agent_id: Agent being executed
            deployment_id: Runtime deployment identifier
            input_text: User input text
            input_data: Additional input data
            session_id: Existing session ID for continuation, or None for new session
            metadata: Additional execution metadata

        Returns:
            ExecutionContext with initialized state

        Raises:
            ExecutionError: If context creation fails
        """
        import uuid

        execution_id = str(uuid.uuid4())

        # Create new session if not provided
        if not session_id:
            session = await self.runtime_adapter.create_session(
                agent_id=agent_id,
                timeout_seconds=self.config.runtime_timeout_seconds,
            )
            session_id = session.session_id

        context = ExecutionContext(
            execution_id=execution_id,
            agent_id=agent_id,
            session_id=session_id,
            deployment_id=deployment_id,
            state=ExecutionState.READY,
            input_text=input_text,
            input_data=input_data or {},
            metadata=metadata or {},
        )

        self._executions[execution_id] = context
        safe_log(f"Created execution context {execution_id} for agent {agent_id}")

        return context

    async def execute_agent(
        self,
        context: ExecutionContext,
        execution_config: Optional[ExecutionConfig] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute an agent with streaming response.

        This method:
        1. Validates execution context
        2. Transitions to RUNNING state
        3. Invokes the agent via Runtime adapter
        4. Streams responses back
        5. Transitions to COMPLETED/FAILED state
        6. Persists results if enabled

        Args:
            context: Execution context
            execution_config: Execution configuration

        Yields:
            Dict containing streaming chunks with keys:
                - 'type': 'token' | 'trace' | 'error' | 'metadata'
                - 'data': chunk-specific data

        Raises:
            ExecutionError: If execution fails
            TransientError: If execution fails due to transient issues
        """
        config = execution_config or ExecutionConfig()

        # Validate and update state
        self._validate_state_transition(context.state, ExecutionState.RUNNING)
        context.state = ExecutionState.RUNNING
        context.started_at = datetime.utcnow()
        context.updated_at = datetime.utcnow()

        execution_start_time = datetime.utcnow()
        output_parts = []
        error_message = None
        final_status = RuntimeStatus.COMPLETED

        try:
            safe_log(
                f"Executing agent {context.agent_id} "
                f"(execution: {context.execution_id}, session: {context.session_id})"
            )

            # Execute with timeout
            timeout_task = asyncio.create_task(
                self._execute_with_streaming(context, config)
            )

            # Wait for completion or timeout
            done, pending = await asyncio.wait(
                [timeout_task],
                timeout=config.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if pending:
                # Timeout occurred
                safe_log(f"Execution {context.execution_id} timed out after {config.timeout_seconds}s")
                timeout_task.cancel()
                context.state = ExecutionState.TIMEOUT
                final_status = RuntimeStatus.TIMEOUT
                error_message = f"Execution timed out after {config.timeout_seconds} seconds"

                # Try to cancel the execution
                await self._cancel_internal(context)

                yield {
                    "type": "error",
                    "data": {"error": error_message, "code": "TIMEOUT"}
                }

            elif done:
                # Execution completed
                try:
                    async for chunk in timeout_task:
                        if chunk.get("type") == "token":
                            output_parts.append(chunk["data"].get("content", ""))
                        yield chunk
                except Exception as e:
                    safe_log(f"Error streaming execution {context.execution_id}: {e}")
                    raise

                # Collect final result
                output = "".join(output_parts)

        except asyncio.CancelledError:
            safe_log(f"Execution {context.execution_id} was cancelled")
            context.state = ExecutionState.CANCELLED
            final_status = RuntimeStatus.CANCELLED
            error_message = "Execution was cancelled"

            yield {
                "type": "error",
                "data": {"error": error_message, "code": "CANCELLED"}
            }

        except Exception as e:
            safe_log(f"Execution {context.execution_id} failed: {e}")
            context.state = ExecutionState.FAILED
            final_status = RuntimeStatus.FAILED
            error_message = str(e)

            # Determine if error is retryable
            if self._is_transient_error(e) and config.retry_on_transient_error:
                raise TransientError(f"Transient execution error: {e}") from e

            raise ExecutionError(f"Failed to execute agent {context.agent_id}: {e}") from e

        finally:
            # Update final state
            context.updated_at = datetime.utcnow()
            context.completed_at = datetime.utcnow()
            context.error = error_message

            # Create and store result
            execution_time = (
                context.completed_at - execution_start_time
            ).total_seconds()

            context.result = RuntimeExecutionResult(
                execution_id=context.execution_id,
                session_id=context.session_id,
                agent_id=context.agent_id,
                status=final_status,
                output="".join(output_parts) if output_parts else "",
                error=error_message,
                execution_time_seconds=execution_time,
                trace_data=context.metadata.get("trace_data"),
            )

            # Transition to final state
            if context.state == ExecutionState.RUNNING:
                context.state = ExecutionState.COMPLETED

            # Persist result if enabled
            if config.persist_results:
                await self._persist_result(context)

            safe_log(
                f"Execution {context.execution_id} completed: "
                f"state={context.state.value}, status={final_status.value}, "
                f"time={execution_time:.2f}s"
            )

    async def _execute_with_streaming(
        self,
        context: ExecutionContext,
        config: ExecutionConfig,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Internal method to execute agent with streaming"""
        try:
            async for chunk in self.runtime_adapter.invoke_agent(
                deployment_id=context.deployment_id,
                session_id=context.session_id,
                input_text=context.input_text,
                input_data=context.input_data,
                stream=config.enable_streaming,
                timeout_seconds=config.timeout_seconds,
                enable_trace=config.enable_trace,
                session_state=context.metadata.get("session_state"),
            ):
                # Store trace data if enabled
                if config.enable_trace and chunk.get("type") == "trace":
                    context.metadata.setdefault("trace_data", [])
                    context.metadata["trace_data"].append(chunk.get("data"))

                yield chunk

        except Exception as e:
            safe_log(f"Error during agent invocation: {e}")
            raise

    async def cancel_execution(
        self,
        execution_id: str,
    ) -> bool:
        """
        Cancel an ongoing execution.

        Args:
            execution_id: Execution identifier

        Returns:
            True if cancellation was successful, False otherwise

        Raises:
            ExecutionError: If cancellation fails
        """
        context = self._executions.get(execution_id)
        if not context:
            raise ExecutionError(f"Execution {execution_id} not found")

        # Check if execution can be cancelled
        if context.state not in [ExecutionState.READY, ExecutionState.RUNNING]:
            safe_log(
                f"Cannot cancel execution {execution_id} in state {context.state.value}"
            )
            return False

        try:
            # Cancel via Runtime adapter
            success = await self.runtime_adapter.cancel_execution(
                execution_id=context.agent_id,
                session_id=context.session_id,
            )

            if success:
                context.state = ExecutionState.CANCELLED
                context.updated_at = datetime.utcnow()
                safe_log(f"Execution {execution_id} cancelled successfully")

            return success

        except Exception as e:
            safe_log(f"Failed to cancel execution {execution_id}: {e}")
            return False

    async def get_execution_status(
        self,
        execution_id: str,
    ) -> ExecutionContext:
        """
        Get status of an execution.

        Args:
            execution_id: Execution identifier

        Returns:
            ExecutionContext with current status

        Raises:
            ExecutionError: If execution not found
        """
        context = self._executions.get(execution_id)
        if not context:
            raise ExecutionError(f"Execution {execution_id} not found")

        # Optionally refresh from Runtime
        try:
            session_info = await self.runtime_adapter.get_execution_status(
                execution_id=context.agent_id,
                session_id=context.session_id,
            )
            # Update context with Runtime status
            context.metadata["runtime_session_info"] = session_info

        except Exception as e:
            safe_log(f"Failed to refresh execution status from Runtime: {e}")

        return context

    async def list_executions(
        self,
        agent_id: Optional[str] = None,
        state: Optional[ExecutionState] = None,
        limit: int = 100,
    ) -> List[ExecutionContext]:
        """
        List executions with optional filtering.

        Args:
            agent_id: Filter by agent ID
            state: Filter by execution state
            limit: Maximum number of results

        Returns:
            List of execution contexts
        """
        executions = list(self._executions.values())

        # Apply filters
        if agent_id:
            executions = [e for e in executions if e.agent_id == agent_id]
        if state:
            executions = [e for e in executions if e.state == state]

        # Sort by created_at descending
        executions.sort(key=lambda e: e.created_at, reverse=True)

        return executions[:limit]

    async def delete_execution(
        self,
        execution_id: str,
    ) -> bool:
        """
        Delete an execution from tracking.

        Args:
            execution_id: Execution identifier

        Returns:
            True if execution was deleted, False if not found
        """
        if execution_id in self._executions:
            del self._executions[execution_id]
            safe_log(f"Deleted execution tracking for {execution_id}")
            return True
        return False

    def _validate_state_transition(
        self,
        current_state: ExecutionState,
        new_state: ExecutionState,
    ) -> None:
        """
        Validate that a state transition is allowed.

        Args:
            current_state: Current execution state
            new_state: Target execution state

        Raises:
            ExecutionError: If transition is not allowed
        """
        allowed_transitions = self.VALID_TRANSITIONS.get(current_state, [])
        if new_state not in allowed_transitions:
            raise ExecutionError(
                f"Invalid state transition: {current_state.value} -> {new_state.value}"
            )

    def _is_transient_error(self, error: Exception) -> bool:
        """Check if an error is transient and should be retried"""
        error_str = str(error).lower()
        transient_keywords = [
            "timeout",
            "throttling",
            "too many requests",
            "service unavailable",
            "internal error",
            "network",
            "connection",
        ]
        return any(keyword in error_str for keyword in transient_keywords)

    async def _cancel_internal(self, context: ExecutionContext) -> None:
        """Internal method to cancel an execution"""
        try:
            await self.runtime_adapter.cancel_execution(
                execution_id=context.agent_id,
                session_id=context.session_id,
            )
        except Exception as e:
            safe_log(f"Error during internal cancellation: {e}")

    async def _persist_result(self, context: ExecutionContext) -> None:
        """
        Persist execution result to database.

        For Phase 1, this is a stub. In production, this would
        write to the agent_runs or agent_messages table.

        Args:
            context: Execution context with result
        """
        # Stub for Phase 1
        # In production, write to Supabase:
        # await client.table("agent_runs").update({
        #     "status": context.result.status.value,
        #     "output": context.result.output,
        #     "error": context.result.error,
        #     "execution_time_seconds": context.result.execution_time_seconds,
        # }).eq("run_id", context.execution_id).execute()
        pass


# Convenience functions for common operations

async def execute_agent_with_runtime(
    agent_id: str,
    deployment_id: str,
    input_text: str,
    input_data: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    execution_config: Optional[ExecutionConfig] = None,
    config: Optional[AgentCoreConfig] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Convenience function to execute an agent with AgentCore Runtime.

    This function creates an ExecutionManager, creates an execution context,
    and executes the agent in a single call.

    Args:
        agent_id: Agent being executed
        deployment_id: Runtime deployment identifier
        input_text: User input text
        input_data: Additional input data
        session_id: Existing session ID for continuation
        execution_config: Execution configuration
        config: AgentCore configuration

    Yields:
        Dict containing streaming chunks
    """
    manager = ExecutionManager(config=config)

    context = await manager.create_execution_context(
        agent_id=agent_id,
        deployment_id=deployment_id,
        input_text=input_text,
        input_data=input_data,
        session_id=session_id,
    )

    async for chunk in manager.execute_agent(context, execution_config):
        yield chunk


async def get_execution_info(
    execution_id: str,
    config: Optional[AgentCoreConfig] = None,
) -> Optional[ExecutionContext]:
    """
    Convenience function to get execution information.

    Args:
        execution_id: Execution identifier
        config: AgentCore configuration

    Returns:
        ExecutionContext if found, None otherwise
    """
    manager = ExecutionManager(config=config)
    try:
        return await manager.get_execution_status(execution_id)
    except ExecutionError:
        return None
