"""
AgentCore Runtime Execution Management

Provides execution lifecycle management and SSE streaming for AgentCore Runtime agents.
"""

from .execution_manager import (
    ExecutionManager,
    ExecutionContext,
    ExecutionConfig,
    ExecutionState,
    execute_agent_with_runtime,
    get_execution_info,
)

from .streaming_handler import (
    StreamingHandler,
    SSEEvent,
    stream_agent_execution_sse,
    format_sse_event,
)

__all__ = [
    # Execution management
    "ExecutionManager",
    "ExecutionContext",
    "ExecutionConfig",
    "ExecutionState",
    "execute_agent_with_runtime",
    "get_execution_info",
    # Streaming
    "StreamingHandler",
    "SSEEvent",
    "stream_agent_execution_sse",
    "format_sse_event",
]
