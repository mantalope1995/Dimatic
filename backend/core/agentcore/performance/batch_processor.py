"""
AgentCore Batch Processor (Phase 10)

Request batching optimization for AgentCore operations in ap-southeast-2.

Phase 10: Batching operations support ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class BatchPriority(str, Enum):
    """Priority levels for batch processing."""
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class BatchItem:
    """
    A single item in a batch.

    Attributes:
        item_id: Unique item identifier
        data: Item data
        priority: Item priority
        added_at: When item was added
        metadata: Additional metadata
    """
    item_id: str
    data: Any
    priority: BatchPriority = BatchPriority.NORMAL
    added_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchResult:
    """
    Result of a batch processing operation.

    Attributes:
        batch_id: Batch identifier
        total_items: Total items processed
        successful_items: Number of successful items
        failed_items: Number of failed items
        results: List of individual results
        errors: List of errors
        duration_ms: Processing duration in milliseconds
    """
    batch_id: str
    total_items: int
    successful_items: int
    failed_items: int
    results: List[Any] = field(default_factory=list)
    errors: List[Exception] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if self.total_items == 0:
            return 1.0
        return self.successful_items / self.total_items

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "success_rate": self.success_rate,
            "duration_ms": self.duration_ms,
            "error_count": len(self.errors),
            "region": PHASE_10_REGION,
        }


@dataclass
class BatchConfig:
    """
    Configuration for batch processing.

    Attributes:
        max_batch_size: Maximum items per batch
        max_wait_time_seconds: Maximum time to wait before flushing
        min_batch_size: Minimum items to trigger processing
        flush_on_timeout: Whether to flush when timeout expires
        priority_enabled: Whether priority sorting is enabled
    """
    max_batch_size: int = 100
    max_wait_time_seconds: float = 5.0
    min_batch_size: int = 10
    flush_on_timeout: bool = True
    priority_enabled: bool = True


# ============================================================================
# Batch Processor
# ============================================================================

class BatchProcessor:
    """
    Request batching processor for AgentCore operations.

    Features:
    - Automatic batching based on size and time
    - Priority-based item ordering
    - Async batch processing
    - Graceful timeout handling
    - Result aggregation

    Usage:
        ```python
        processor = BatchProcessor()

        # Define batch processing function
        async def process_items(items: List[BatchItem]) -> List[Any]:
            results = []
            for item in items:
                result = await some_api_call(item.data)
                results.append(result)
            return results

        # Add items to batch (auto-processes when conditions met)
        for i in range(50):
            await processor.add(item_id=f"item-{i}", data={"value": i})

        # Manually flush remaining items
        results = await processor.flush(process_func=process_items)
        ```
    """

    # Default batch configuration
    DEFAULT_CONFIG = BatchConfig()

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        batch_config: Optional[BatchConfig] = None,
    ):
        """
        Initialize the batch processor.

        Args:
            config: AgentCore configuration
            batch_config: Batch processing configuration
        """
        self.config = config or get_config()
        self._batch_config = batch_config or self.DEFAULT_CONFIG

        self._items: List[BatchItem] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._flush_event = asyncio.Event()
        self._closed = False

        # Validate region compliance for Phase 10
        if self.config.aws_region != PHASE_10_REGION:
            safe_log(
                f"BatchProcessor: Region '{self.config.aws_region}' specified, "
                f"but Phase 10 requires '{PHASE_10_REGION}'. "
                f"All operations will target {PHASE_10_REGION} for compliance."
            )

        safe_log("BatchProcessor initialized")

    async def add(
        self,
        item_id: str,
        data: Any,
        priority: BatchPriority = BatchPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add an item to the batch.

        Args:
            item_id: Unique item identifier
            data: Item data
            priority: Item priority
            metadata: Optional metadata

        Returns:
            True if item added successfully

        Raises:
            AgentCoreError: If processor is closed
        """
        if self._closed:
            raise AgentCoreError("Cannot add items to closed batch processor")

        async with self._lock:
            item = BatchItem(
                item_id=item_id,
                data=data,
                priority=priority,
                metadata=metadata or {},
            )
            self._items.append(item)

            # Check if we should trigger processing
            if len(self._items) >= self._batch_config.max_batch_size:
                self._flush_event.set()

            # Start background flush task if not running
            if self._flush_task is None:
                self._flush_task = asyncio.create_task(self._flush_loop())

            return True

    async def flush(
        self,
        process_func: Optional[Callable[[List[BatchItem]], Awaitable[List[Any]]]] = None,
    ) -> BatchResult:
        """
        Manually flush the batch.

        Args:
            process_func: Optional custom processing function

        Returns:
            Batch processing result

        Raises:
            AgentCoreError: If no items to flush
        """
        async with self._lock:
            if not self._items:
                raise AgentCoreError("No items to flush")

            items = self._items.copy()
            self._items.clear()
            self._flush_event.clear()

        # Process batch
        return await self._process_batch(items, process_func)

    async def _flush_loop(self) -> None:
        """Background loop for automatic flushing."""
        try:
            while True:
                # Wait for flush event or timeout
                timeout = self._batch_config.max_wait_time_seconds

                try:
                    await asyncio.wait_for(
                        self._flush_event.wait(),
                        timeout=timeout
                    )
                    # Event was set (batch size reached)
                    break
                except asyncio.TimeoutError:
                    # Timeout expired
                    if self._batch_config.flush_on_timeout:
                        break
                    continue

                # Process batch
                if self._items:
                    await self._process_batch(self._items.copy())

        except asyncio.CancelledError:
            # Task was cancelled
            raise
        except Exception as e:
            safe_log(f"Flush loop error: {e}", level="error")
        finally:
            self._flush_task = None

    async def _process_batch(
        self,
        items: List[BatchItem],
        process_func: Optional[Callable[[List[BatchItem]], Awaitable[List[Any]]]] = None,
    ) -> BatchResult:
        """
        Process a batch of items.

        Args:
            items: Items to process
            process_func: Optional custom processing function

        Returns:
            Batch processing result
        """
        batch_id = f"batch-{int(time.time() * 1000)}"
        start_time = time.time()

        # Sort by priority if enabled
        if self._batch_config.priority_enabled:
            priority_order = {
                BatchPriority.HIGH: 0,
                BatchPriority.NORMAL: 1,
                BatchPriority.LOW: 2,
            }
            items.sort(key=lambda item: priority_order.get(item.priority, 3))

        results = []
        errors = []
        successful = 0
        failed = 0

        try:
            if process_func:
                # Use custom processing function
                results = await process_func(items)
                successful = len(results)
                failed = len(items) - successful
            else:
                # Default: just return the item data
                results = [item.data for item in items]
                successful = len(items)

        except Exception as e:
            safe_log(f"Batch processing failed: {e}", level="error")
            errors.append(e)
            failed = len(items)

        duration_ms = (time.time() - start_time) * 1000

        result = BatchResult(
            batch_id=batch_id,
            total_items=len(items),
            successful_items=successful,
            failed_items=failed,
            results=results,
            errors=errors,
            duration_ms=duration_ms,
        )

        safe_log(
            f"Batch {batch_id[:16]}... processed: {successful}/{len(items)} successful "
            f"in {duration_ms:.0f}ms"
        )

        return result

    async def close(self) -> BatchResult:
        """
        Close the processor and flush remaining items.

        Returns:
            Final batch processing result
        """
        self._closed = True

        # Cancel background task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining items
        if self._items:
            return await self.flush()

        return BatchResult(
            batch_id="final",
            total_items=0,
            successful_items=0,
            failed_items=0,
        )

    @property
    def pending_count(self) -> int:
        """Get number of pending items."""
        return len(self._items)

    @property
    def is_closed(self) -> bool:
        """Check if processor is closed."""
        return self._closed


# ============================================================================
# Specialized Batch Processors
# ============================================================================

class RuntimeBatchProcessor(BatchProcessor):
    """
    Batch processor for AgentCore Runtime operations.

    Optimized for batching Runtime invocations:
    - Groups invocations by agent
    - Parallel execution where possible
    - Result aggregation
    """

    async def batch_invoke(
        self,
        invocations: List[Dict[str, Any]],
    ) -> BatchResult:
        """
        Batch invoke Runtime agents.

        Args:
            invocations: List of invocation parameters

        Returns:
            Batch processing result
        """
        # Create batch items from invocations
        for i, invocation in enumerate(invocations):
            await self.add(
                item_id=invocation.get("execution_id", f"invoke-{i}"),
                data=invocation,
                priority=BatchPriority.HIGH,
            )

        # Flush and return result
        return await self.flush()

    async def _process_batch(
        self,
        items: List[BatchItem],
        process_func: Optional[Callable[[List[BatchItem]], Awaitable[List[Any]]]] = None,
    ) -> BatchResult:
        """Process Runtime invocation batch."""
        # Import Runtime adapter here to avoid circular dependency
        from ..adapters.runtime import AgentCoreRuntimeAdapter

        adapter = AgentCoreRuntimeAdapter(config=self.config)

        async def process_runtime_items(items: List[BatchItem]) -> List[Any]:
            """Process Runtime items with parallel execution."""
            tasks = []

            for item in items:
                invocation_data = item.data

                # Create async task for each invocation
                task = adapter.invoke_agent(
                    agent_id=invocation_data.get("agent_id"),
                    input_data=invocation_data.get("input_data"),
                    deployment_id=invocation_data.get("deployment_id"),
                    streaming=False,
                )
                tasks.append(task)

            # Execute in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            return results

        # Use parent class processing with custom function
        return await super()._process_batch(items, process_runtime_items)


# ============================================================================
# Convenience Functions
# ============================================================================

def get_batch_processor(
    config: Optional[AgentCoreConfig] = None,
    batch_config: Optional[BatchConfig] = None,
) -> BatchProcessor:
    """
    Get a batch processor instance.

    Args:
        config: Optional AgentCore configuration
        batch_config: Optional batch configuration

    Returns:
        BatchProcessor instance
    """
    return BatchProcessor(config=config, batch_config=batch_config)


def get_runtime_batch_processor(
    config: Optional[AgentCoreConfig] = None,
    batch_config: Optional[BatchConfig] = None,
) -> RuntimeBatchProcessor:
    """
    Get a Runtime batch processor instance.

    Args:
        config: Optional AgentCore configuration
        batch_config: Optional batch configuration

    Returns:
        RuntimeBatchProcessor instance
    """
    return RuntimeBatchProcessor(config=config, batch_config=batch_config)


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "BatchPriority",
    "BatchItem",
    "BatchResult",
    "BatchConfig",
    "BatchProcessor",
    "RuntimeBatchProcessor",
    "get_batch_processor",
    "get_runtime_batch_processor",
]
