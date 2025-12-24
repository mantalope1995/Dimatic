"""
AgentCore Metrics Collector (Phase 9)

Centralized metrics collection for AgentCore operations in ap-southeast-2.

Phase 9: All metrics collection uses ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log
from .cloudwatch_client import (
    CloudWatchClient,
    MetricDatum,
    MetricDimension,
    MetricBatch,
    AgentCoreMetrics,
    MetricUnit,
)

logger = logging.getLogger(__name__)

# Phase 9 required region
PHASE_9_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class MetricType(str, Enum):
    """Types of metrics to collect."""
    COUNTER = "counter"  # Incrementing value (e.g., execution count)
    GAUGE = "gauge"  # Current value (e.g., active executions)
    TIMER = "timer"  # Timing measurement (e.g., duration)
    HISTOGRAM = "histogram"  # Distribution of values


@dataclass
class MetricRecord:
    """
    Individual metric record.

    Attributes:
        name: Metric name
        value: Metric value
        metric_type: Type of metric
        unit: Unit of measurement
        dimensions: Metric dimensions
        timestamp: When the metric was recorded
        account_id: Associated account ID
    """
    name: str
    value: float
    metric_type: MetricType = MetricType.COUNTER
    unit: MetricUnit = MetricUnit.COUNT
    dimensions: List[MetricDimension] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    account_id: Optional[str] = None

    def to_cloudwatch_metric(self) -> MetricDatum:
        """Convert to CloudWatch metric datum."""
        all_dimensions = self.dimensions.copy()
        all_dimensions.append(MetricDimension("Region", PHASE_9_REGION))
        if self.account_id:
            all_dimensions.append(MetricDimension("AccountId", self.account_id[:8]))

        return MetricDatum(
            metric_name=self.name,
            value=self.value,
            unit=self.unit,
            dimensions=all_dimensions,
            timestamp=self.timestamp,
        )


@dataclass
class MetricBuffer:
    """
    Buffer for collecting metrics before batch submission.

    Attributes:
        max_size: Maximum number of metrics to buffer
        max_age_seconds: Maximum age before flushing
        metrics: Buffered metrics
    """
    max_size: int = 100
    max_age_seconds: int = 60
    metrics: List[MetricRecord] = field(default_factory=list)
    _created_at: datetime = field(default_factory=datetime.utcnow)

    def add(self, metric: MetricRecord) -> None:
        """Add a metric to the buffer."""
        self.metrics.append(metric)

    def should_flush(self) -> bool:
        """Check if buffer should be flushed."""
        # Flush if size exceeded
        if len(self.metrics) >= self.max_size:
            return True

        # Flush if age exceeded
        age = (datetime.utcnow() - self._created_at).total_seconds()
        if age >= self.max_age_seconds:
            return True

        return False

    def clear(self) -> None:
        """Clear the buffer."""
        self.metrics.clear()
        self._created_at = datetime.utcnow()


# ============================================================================
# Metrics Collector
# ============================================================================

class MetricsCollector:
    """
    Centralized metrics collector for AgentCore operations.

    Features:
    - Collect metrics from multiple sources
    - Buffer and batch submission to CloudWatch
    - Automatic flushing based on size/age
    - Context manager for timing operations
    - Dimension-based metric organization

    Usage:
        ```python
        collector = MetricsCollector()

        # Record metrics
        collector.increment("ExecutionCount", account_id="account-123")
        collector.gauge("ActiveExecutions", 5.0)
        collector.time("ExecutionDuration", 1234.5)

        # Time a block of code
        async with collector.timed("AgentExecution"):
            await do_something()

        # Flush metrics
        await collector.flush()
        ```
    """

    # Default buffer configuration
    DEFAULT_BUFFER_SIZE = 100
    DEFAULT_BUFFER_AGE_SECONDS = 60

    # Auto-flush interval
    AUTO_FLUSH_INTERVAL_SECONDS = 30

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        buffer_age_seconds: int = DEFAULT_BUFFER_AGE_SECONDS,
        auto_flush: bool = True,
    ):
        """
        Initialize the metrics collector.

        Args:
            config: AgentCore configuration
            buffer_size: Maximum buffer size before flushing
            buffer_age_seconds: Maximum buffer age before flushing
            auto_flush: Enable automatic background flushing
        """
        self.config = config or get_config()
        self._cloudwatch_client: Optional[CloudWatchClient] = None
        self._buffer = MetricBuffer(
            max_size=buffer_size,
            max_age_seconds=buffer_age_seconds,
        )
        self._auto_flush_enabled = auto_flush
        self._auto_flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Validate region compliance for Phase 9
        if self.config.aws_region != PHASE_9_REGION:
            safe_log(
                f"MetricsCollector: Region '{self.config.aws_region}' specified, "
                f"but Phase 9 requires '{PHASE_9_REGION}'. "
                f"All metrics will be sent to {PHASE_9_REGION} for compliance."
            )

        safe_log("MetricsCollector initialized")

    def _get_cloudwatch_client(self) -> CloudWatchClient:
        """Lazy initialization of CloudWatch client."""
        if self._cloudwatch_client is None:
            self._cloudwatch_client = CloudWatchClient(config=self.config)
        return self._cloudwatch_client

    def increment(
        self,
        name: str,
        value: float = 1.0,
        account_id: Optional[str] = None,
        dimensions: Optional[List[MetricDimension]] = None,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            value: Value to add (default: 1.0)
            account_id: Optional account ID
            dimensions: Optional metric dimensions
        """
        metric = MetricRecord(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.COUNT,
            dimensions=dimensions or [],
            account_id=account_id,
        )
        self._add_metric(metric)

    def gauge(
        self,
        name: str,
        value: float,
        unit: MetricUnit = MetricUnit.COUNT,
        account_id: Optional[str] = None,
        dimensions: Optional[List[MetricDimension]] = None,
    ) -> None:
        """
        Record a gauge metric (current value).

        Args:
            name: Metric name
            value: Current value
            unit: Unit of measurement
            account_id: Optional account ID
            dimensions: Optional metric dimensions
        """
        metric = MetricRecord(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            unit=unit,
            dimensions=dimensions or [],
            account_id=account_id,
        )
        self._add_metric(metric)

    def time(
        self,
        name: str,
        value_ms: float,
        account_id: Optional[str] = None,
        dimensions: Optional[List[MetricDimension]] = None,
    ) -> None:
        """
        Record a timing metric.

        Args:
            name: Metric name
            value_ms: Timing value in milliseconds
            account_id: Optional account ID
            dimensions: Optional metric dimensions
        """
        metric = MetricRecord(
            name=name,
            value=value_ms,
            metric_type=MetricType.TIMER,
            unit=MetricUnit.MILLISECONDS,
            dimensions=dimensions or [],
            account_id=account_id,
        )
        self._add_metric(metric)

    @asynccontextmanager
    async def timed(
        self,
        name: str,
        account_id: Optional[str] = None,
        dimensions: Optional[List[MetricDimension]] = None,
    ):
        """
        Context manager for timing operations.

        Args:
            name: Metric name
            account_id: Optional account ID
            dimensions: Optional metric dimensions

        Yields:
            None

        Example:
            ```python
            async with collector.timed("AgentExecution"):
                await agent.execute()
            ```
        """
        start_time = time.time()

        try:
            yield
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            self.time(name, elapsed_ms, account_id, dimensions)

    def _add_metric(self, metric: MetricRecord) -> None:
        """Add a metric to the buffer."""
        self._buffer.add(metric)

        # Auto-flush if buffer is full
        if self._buffer.should_flush():
            asyncio.create_task(self.flush())

    async def flush(self) -> bool:
        """
        Flush buffered metrics to CloudWatch.

        Returns:
            True if flush was successful
        """
        async with self._lock:
            if not self._buffer.metrics:
                return True

            try:
                client = self._get_cloudwatch_client()

                # Convert to CloudWatch format
                batch = MetricBatch()
                for record in self._buffer.metrics:
                    batch.add_metric(record.to_cloudwatch_metric())

                # Send to CloudWatch
                await client.put_batch_metrics(batch)

                safe_log(f"Flushed {len(self._buffer.metrics)} metrics to CloudWatch")
                self._buffer.clear()
                return True

            except Exception as e:
                safe_log(f"Failed to flush metrics: {e}", level="error")
                # Clear buffer anyway to prevent memory buildup
                self._buffer.clear()
                return False

    async def start_auto_flush(self) -> None:
        """Start automatic background flushing."""
        if self._auto_flush_enabled and self._auto_flush_task is None:
            self._auto_flush_task = asyncio.create_task(self._auto_flush_loop())
            safe_log("Started auto-flush background task")

    async def stop_auto_flush(self) -> None:
        """Stop automatic background flushing."""
        if self._auto_flush_task:
            self._auto_flush_task.cancel()
            try:
                await self._auto_flush_task
            except asyncio.CancelledError:
                pass
            self._auto_flush_task = None
            safe_log("Stopped auto-flush background task")

    async def _auto_flush_loop(self) -> None:
        """Background loop for automatic flushing."""
        while True:
            try:
                await asyncio.sleep(self.AUTO_FLUSH_INTERVAL_SECONDS)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                safe_log(f"Auto-flush error: {e}", level="error")

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get summary of collected metrics.

        Returns:
            Dictionary with metrics summary
        """
        return {
            "buffer_size": len(self._buffer.metrics),
            "buffer_max_size": self._buffer.max_size,
            "buffer_age_seconds": (datetime.utcnow() - self._buffer._created_at).total_seconds(),
            "auto_flush_enabled": self._auto_flush_enabled,
            "region": PHASE_9_REGION,
        }


# ============================================================================
# Specialized Collectors
# ============================================================================

class ExecutionMetricsCollector:
    """
    Specialized collector for AgentCore execution metrics.

    Provides convenience methods for tracking execution lifecycle:
    - Start execution
    - Complete execution
    - Record tool usage
    - Track token usage
    """

    def __init__(
        self,
        collector: MetricsCollector,
        account_id: Optional[str] = None,
    ):
        """
        Initialize the execution metrics collector.

        Args:
            collector: Base metrics collector
            account_id: Default account ID
        """
        self.collector = collector
        self.account_id = account_id

    def start_execution(
        self,
        execution_id: str,
        agent_id: str,
        tier: str = "free",
    ) -> None:
        """
        Record execution start.

        Args:
            execution_id: Execution identifier
            agent_id: Agent identifier
            tier: Subscription tier
        """
        dimensions = [
            MetricDimension("AgentId", agent_id),
            MetricDimension("Tier", tier),
        ]

        self.collector.increment(
            AgentCoreMetrics.EXECUTION_COUNT,
            account_id=self.account_id,
            dimensions=dimensions,
        )
        self.collector.gauge(
            AgentCoreMetrics.CONCURRENT_EXECUTIONS,
            1.0,
            account_id=self.account_id,
            dimensions=dimensions,
        )

    def complete_execution(
        self,
        execution_id: str,
        agent_id: str,
        success: bool = True,
        duration_ms: Optional[float] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """
        Record execution completion.

        Args:
            execution_id: Execution identifier
            agent_id: Agent identifier
            success: Whether execution succeeded
            duration_ms: Execution duration in milliseconds
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
        """
        dimensions = [MetricDimension("AgentId", agent_id)]

        if success:
            self.collector.increment(
                AgentCoreMetrics.EXECUTION_SUCCESS,
                account_id=self.account_id,
                dimensions=dimensions,
            )
        else:
            self.collector.increment(
                AgentCoreMetrics.EXECUTION_FAILURE,
                account_id=self.account_id,
                dimensions=dimensions,
            )

        if duration_ms is not None:
            self.collector.time(
                AgentCoreMetrics.EXECUTION_DURATION,
                duration_ms,
                account_id=self.account_id,
                dimensions=dimensions,
            )

        if input_tokens:
            self.collector.increment(
                AgentCoreMetrics.INPUT_TOKENS,
                float(input_tokens),
                account_id=self.account_id,
                dimensions=dimensions,
            )

        if output_tokens:
            self.collector.increment(
                AgentCoreMetrics.OUTPUT_TOKENS,
                float(output_tokens),
                account_id=self.account_id,
                dimensions=dimensions,
            )

    def record_tool_usage(
        self,
        tool_name: str,
        duration_ms: Optional[float] = None,
        success: bool = True,
    ) -> None:
        """
        Record tool usage.

        Args:
            tool_name: Name of the tool
            duration_ms: Tool execution duration
            success: Whether tool execution succeeded
        """
        dimensions = [MetricDimension("ToolName", tool_name)]

        self.collector.increment(
            AgentCoreMetrics.TOOL_INVOCATION,
            account_id=self.account_id,
            dimensions=dimensions,
        )

        if not success:
            self.collector.increment(
                AgentCoreMetrics.TOOL_FAILURE,
                account_id=self.account_id,
                dimensions=dimensions,
            )

        if duration_ms is not None:
            self.collector.time(
                AgentCoreMetrics.TOOL_DURATION,
                duration_ms,
                account_id=self.account_id,
                dimensions=dimensions,
            )


# ============================================================================
# Convenience Functions
# ============================================================================

def get_metrics_collector(config: Optional[AgentCoreConfig] = None) -> MetricsCollector:
    """
    Get the metrics collector instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        MetricsCollector instance
    """
    return MetricsCollector(config=config)


def get_execution_collector(
    account_id: Optional[str] = None,
    config: Optional[AgentCoreConfig] = None,
) -> ExecutionMetricsCollector:
    """
    Get the execution metrics collector instance.

    Args:
        account_id: Default account ID
        config: Optional AgentCore configuration

    Returns:
        ExecutionMetricsCollector instance
    """
    base_collector = get_metrics_collector(config)
    return ExecutionMetricsCollector(base_collector, account_id=account_id)


# Export public symbols
__all__ = [
    "PHASE_9_REGION",
    "MetricType",
    "MetricRecord",
    "MetricBuffer",
    "MetricsCollector",
    "ExecutionMetricsCollector",
    "get_metrics_collector",
    "get_execution_collector",
]
