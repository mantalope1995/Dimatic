"""
AgentCore Streaming Handler

Handles Server-Sent Events (SSE) streaming from AWS Bedrock AgentCore Runtime.
Provides real-time agent execution results to clients via streaming responses.

IMPORTANT: For Phase 1 migration, all AgentCore Runtime services MUST run in
ap-southeast-2 (Australia region) to meet data residency requirements.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

from ..config import AgentCoreConfig, get_config
from ..models import RuntimeStatus, RuntimeExecutionResult
from ..errors import (
    AgentCoreError,
    AgentCoreExecutionError as StreamingError,
    AgentCoreRetryableError as TransientError,
    safe_log,
)
from .execution_manager import ExecutionContext, ExecutionConfig, ExecutionState

logger = logging.getLogger(__name__)


class SSEEvent:
    """Server-Sent Event format wrapper"""

    def __init__(
        self,
        data: Dict[str, Any],
        event_type: Optional[str] = None,
        event_id: Optional[str] = None,
        retry: Optional[int] = None,
    ):
        self.data = data
        self.event_type = event_type
        self.event_id = event_id
        self.retry = retry

    def format(self) -> str:
        """Format as SSE message"""
        lines = []

        if self.event_id:
            lines.append(f"id: {self.event_id}")

        if self.event_type:
            lines.append(f"event: {self.event_type}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # Data must be JSON serialized and may span multiple lines
        data_str = json.dumps(self.data, ensure_ascii=False)
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")

        lines.append("")  # Empty line to end the event
        return "\n".join(lines) + "\n"


class StreamingHandler:
    """
    Handles Server-Sent Events streaming from AgentCore Runtime.

    This handler wraps the Runtime adapter's streaming invocation and formats
    responses as SSE events for real-time delivery to clients.

    SSE Event Types:
        - 'token': Streaming token/response chunk
        - 'trace': Execution trace/debug information
        - 'error': Error during execution
        - 'metadata': Execution metadata (start, end, status)
        - 'heartbeat': Keep-alive for long-running executions
    """

    # SSE settings
    HEARTBEAT_INTERVAL_SECONDS = 15  # Send heartbeat every 15 seconds
    MAX_STREAM_DURATION_SECONDS = 900  # Maximum 15 minutes for streaming

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        runtime_adapter=None,
    ):
        """
        Initialize the streaming handler.

        Args:
            config: AgentCore configuration. If None, uses global config.
            runtime_adapter: Optional Runtime adapter instance. If None,
                          creates one on demand.

        Raises:
            AgentCoreError: If streaming is not enabled or config is invalid.
        """
        self.config = config or get_config()
        self._validate_config()

        # Lazy initialization of runtime adapter
        self._runtime_adapter = runtime_adapter

        # Track active streams for cleanup
        self._active_streams: Dict[str, bool] = {}

    def _validate_config(self) -> None:
        """Validate configuration for streaming handler"""
        if not self.config.runtime_enabled:
            raise AgentCoreError(
                "AgentCore Runtime is not enabled. "
                "Set AGENTCORE_RUNTIME_ENABLED=true to use streaming features."
            )

    @property
    def runtime_adapter(self):
        """Get or create runtime adapter"""
        if self._runtime_adapter is None:
            from ..adapters.runtime import AgentCoreRuntimeAdapter
            self._runtime_adapter = AgentCoreRuntimeAdapter(config=self.config)
        return self._runtime_adapter

    async def stream_agent_execution(
        self,
        deployment_id: str,
        session_id: str,
        input_text: str,
        input_data: Optional[Dict[str, Any]] = None,
        enable_trace: bool = False,
        timeout_seconds: int = 300,
    ) -> AsyncGenerator[str, None]:
        """
        Stream agent execution results via SSE.

        This method orchestrates the entire streaming flow:
        1. Send initial metadata event
        2. Stream response tokens as they arrive
        3. Send completion/error metadata
        4. Handle timeouts and errors gracefully

        Args:
            deployment_id: Agent deployment identifier (agent_id)
            session_id: Session identifier for conversation continuity
            input_text: User input text
            input_data: Additional input data
            enable_trace: Enable execution tracing
            timeout_seconds: Execution timeout

        Yields:
            Formatted SSE event strings

        Raises:
            StreamingError: If streaming fails fatally
            TransientError: If streaming fails due to transient issues
        """
        execution_id = f"{deployment_id}-{session_id}"
        self._active_streams[execution_id] = True

        try:
            safe_log(
                f"Starting SSE stream for execution {execution_id}: "
                f"deployment={deployment_id}, session={session_id}"
            )

            # Send initial metadata
            yield SSEEvent(
                data={
                    "type": "metadata",
                    "deployment_id": deployment_id,
                    "session_id": session_id,
                    "execution_id": execution_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "starting",
                },
                event_type="metadata",
            ).format()

            # Start heartbeat task
            heartbeat_task = asyncio.create_task(
                self._send_heartbeat(execution_id)
            )

            # Stream agent invocation
            start_time = datetime.utcnow()
            complete = False
            error_message = None

            try:
                async for chunk in self.runtime_adapter.invoke_agent(
                    deployment_id=deployment_id,
                    session_id=session_id,
                    input_text=input_text,
                    input_data=input_data,
                    stream=True,
                    timeout_seconds=timeout_seconds,
                    enable_trace=enable_trace,
                ):
                    # Check if stream was cancelled
                    if not self._active_streams.get(execution_id, False):
                        safe_log(f"Stream {execution_id} was cancelled")
                        break

                    # Forward chunk as SSE event
                    chunk_type = chunk.get("type", "unknown")

                    if chunk_type == "token":
                        # Response token
                        yield SSEEvent(
                            data={
                                "content": chunk.get("data", {}).get("content", ""),
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            event_type="token",
                        ).format()

                    elif chunk_type == "trace":
                        # Trace data
                        if enable_trace:
                            yield SSEEvent(
                                data={
                                    "trace": chunk.get("data", {}),
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                                event_type="trace",
                            ).format()

                    elif chunk_type == "error":
                        # Error during execution
                        error_message = chunk.get("data", {}).get("error", "Unknown error")
                        yield SSEEvent(
                            data={
                                "error": error_message,
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            event_type="error",
                        ).format()

                    elif chunk_type == "metadata":
                        # Forward metadata events
                        yield SSEEvent(
                            data={
                                **chunk.get("data", {}),
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                            event_type="metadata",
                        ).format()

                complete = True

            except asyncio.CancelledError:
                safe_log(f"Stream {execution_id} cancelled by client")
                yield SSEEvent(
                    data={
                        "status": "cancelled",
                        "message": "Stream cancelled by client",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    event_type="metadata",
                ).format()

            except Exception as e:
                error_message = str(e)
                safe_log(f"Error during stream {execution_id}: {e}")

                # Check if transient
                if self._is_transient_error(e):
                    yield SSEEvent(
                        data={
                            "error": f"Transient error: {error_message}",
                            "retryable": True,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        event_type="error",
                    ).format()
                    raise TransientError(f"Transient streaming error: {e}") from e
                else:
                    yield SSEEvent(
                        data={
                            "error": error_message,
                            "retryable": False,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        event_type="error",
                    ).format()

            finally:
                # Cancel heartbeat
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Send completion metadata
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            if complete and not error_message:
                yield SSEEvent(
                    data={
                        "status": "completed",
                        "execution_time_seconds": execution_time,
                        "finish_reason": "stop",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    event_type="metadata",
                ).format()

            safe_log(
                f"Stream {execution_id} completed: "
                f"time={execution_time:.2f}s, complete={complete}"
            )

        except GeneratorExit:
            safe_log(f"Client disconnected from stream {execution_id}")

        finally:
            # Cleanup
            self._active_streams.pop(execution_id, None)

    async def _send_heartbeat(self, execution_id: str) -> None:
        """
        Send periodic heartbeat events to keep connection alive.

        Args:
            execution_id: Execution identifier for this stream
        """
        try:
            while self._active_streams.get(execution_id, False):
                await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

                if self._active_streams.get(execution_id, False):
                    yield SSEEvent(
                        data={
                            "type": "heartbeat",
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                        event_type="heartbeat",
                    ).format()

        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass

    async def cancel_stream(self, execution_id: str) -> bool:
        """
        Cancel an active stream.

        Args:
            execution_id: Execution identifier to cancel

        Returns:
            True if stream was cancelled, False if not found
        """
        if execution_id in self._active_streams:
            self._active_streams[execution_id] = False
            safe_log(f"Cancelled stream {execution_id}")
            return True
        return False

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


# Convenience functions for common streaming operations

async def stream_agent_execution_sse(
    deployment_id: str,
    session_id: str,
    input_text: str,
    input_data: Optional[Dict[str, Any]] = None,
    enable_trace: bool = False,
    timeout_seconds: int = 300,
    config: Optional[AgentCoreConfig] = None,
) -> AsyncGenerator[str, None]:
    """
    Convenience function to stream agent execution via SSE.

    Args:
        deployment_id: Agent deployment identifier
        session_id: Session identifier
        input_text: User input text
        input_data: Additional input data
        enable_trace: Enable execution tracing
        timeout_seconds: Execution timeout
        config: Optional AgentCore configuration

    Yields:
        Formatted SSE event strings
    """
    handler = StreamingHandler(config=config)

    async for event in handler.stream_agent_execution(
        deployment_id=deployment_id,
        session_id=session_id,
        input_text=input_text,
        input_data=input_data,
        enable_trace=enable_trace,
        timeout_seconds=timeout_seconds,
    ):
        yield event


def format_sse_event(
    data: Dict[str, Any],
    event_type: Optional[str] = None,
    event_id: Optional[str] = None,
) -> str:
    """
    Convenience function to format a single SSE event.

    Args:
        data: Event data
        event_type: Optional event type
        event_id: Optional event ID

    Returns:
        Formatted SSE event string
    """
    return SSEEvent(data=data, event_type=event_type, event_id=event_id).format()
