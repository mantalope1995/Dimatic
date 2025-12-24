"""
AgentCore Performance Module (Phase 10)

Performance optimization components for AgentCore operations.

Phase 10: All performance optimization supports ap-southeast-2 (Australia) region
for data residency compliance.

Exports:
    - BatchProcessor: Request batching optimization
    - RuntimeBatchProcessor: Specialized Runtime batch processor
    - ConnectionPool: Generic connection pooling
    - RuntimeConnectionPool: Runtime-specific connection pooling
    - GracefulShutdown: Coordinated service shutdown
    - AgentCoreShutdownManager: Specialized AgentCore shutdown
"""

from .batch_processor import (
    PHASE_10_REGION as BATCH_PROCESSOR_REGION,
    BatchPriority,
    BatchItem,
    BatchResult,
    BatchConfig,
    BatchProcessor,
    RuntimeBatchProcessor,
    get_batch_processor,
    get_runtime_batch_processor,
)

from .connection_pool import (
    PHASE_10_REGION as CONNECTION_POOL_REGION,
    PoolState,
    ConnectionType,
    PooledConnection,
    PoolConfig,
    PoolStats,
    ConnectionPool,
    RuntimeConnectionPool,
    AcquireContext,
    get_connection_pool,
    initialize_pools,
    close_pools,
)

from .graceful_shutdown import (
    PHASE_10_REGION as SHUTDOWN_REGION,
    ShutdownState,
    ShutdownPriority,
    ShutdownHook,
    ShutdownResult,
    ShutdownConfig,
    GracefulShutdown,
    AgentCoreShutdownManager,
    get_shutdown_manager,
    initialize_shutdown,
    trigger_shutdown,
    ShutdownGuard,
)

# Use consistent region export
PHASE_10_REGION = BATCH_PROCESSOR_REGION

__all__ = [
    "PHASE_10_REGION",
    # Batch Processing
    "BatchPriority",
    "BatchItem",
    "BatchResult",
    "BatchConfig",
    "BatchProcessor",
    "RuntimeBatchProcessor",
    "get_batch_processor",
    "get_runtime_batch_processor",
    # Connection Pooling
    "PoolState",
    "ConnectionType",
    "PooledConnection",
    "PoolConfig",
    "PoolStats",
    "ConnectionPool",
    "RuntimeConnectionPool",
    "AcquireContext",
    "get_connection_pool",
    "initialize_pools",
    "close_pools",
    # Graceful Shutdown
    "ShutdownState",
    "ShutdownPriority",
    "ShutdownHook",
    "ShutdownResult",
    "ShutdownConfig",
    "GracefulShutdown",
    "AgentCoreShutdownManager",
    "get_shutdown_manager",
    "initialize_shutdown",
    "trigger_shutdown",
    "ShutdownGuard",
]
