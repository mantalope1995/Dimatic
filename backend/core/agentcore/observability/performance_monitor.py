"""
AgentCore Performance Monitor (Phase 9)

Performance monitoring and tracking for AgentCore operations in ap-southeast-2.

Phase 9: All performance monitoring uses ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log
from .cloudwatch_client import CloudWatchClient, MetricDatum, MetricDimension

logger = logging.getLogger(__name__)

# Phase 9 required region
PHASE_9_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class PerformanceMetric(str, Enum):
    """Types of performance metrics to track."""
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    CONCURRENT_REQUESTS = "concurrent_requests"
    QUEUE_DEPTH = "queue_depth"


@dataclass
class PerformanceSnapshot:
    """
    Snapshot of performance metrics at a point in time.

    Attributes:
        timestamp: When snapshot was taken
        metrics: Metric name to value mapping
        dimensions: Associated dimensions
    """
    timestamp: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    dimensions: List[MetricDimension] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "metrics": self.metrics.copy(),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "region": PHASE_9_REGION,
        }


@dataclass
class PerformanceStats:
    """
    Aggregated performance statistics.

    Attributes:
        metric_name: Name of the metric
        count: Number of data points
        min: Minimum value
        max: Maximum value
        avg: Average value
        p50: 50th percentile (median)
        p95: 95th percentile
        p99: 99th percentile
    """
    metric_name: str
    count: int = 0
    min: float = float("inf")
    max: float = 0.0
    avg: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0

    def update(self, value: float) -> None:
        """Update statistics with a new value."""
        self.count += 1
        self.min = min(self.min, value)
        self.max = max(self.max, value)

        # Update running average
        self.avg = self.avg + (value - self.avg) / self.count

        # Update percentiles (simplified - in production use proper algorithm)
        # For now, just store the value
        if self.count == 1:
            self.p50 = value
            self.p95 = value
            self.p99 = value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metric_name": self.metric_name,
            "count": self.count,
            "min": self.min if self.count > 0 else 0,
            "max": self.max,
            "avg": self.avg,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
        }


# ============================================================================
# Performance Monitor
# ============================================================================

class PerformanceMonitor:
    """
    Performance monitoring for AgentCore operations.

    Features:
    - Track latency, throughput, error rates
    - Calculate percentiles and statistics
    - Performance threshold alerts
    - Historical performance data
    - Real-time performance tracking

    Usage:
        ```python
        monitor = PerformanceMonitor()

        # Record latency
        with monitor.track_latency("AgentExecution"):
            await agent.execute()

        # Record throughput
        monitor.record_throughput("RequestsPerSecond", 100.0)

        # Get statistics
        stats = monitor.get_statistics("AgentExecution")
        ```
    """

    # Default retention period
    DEFAULT_RETENTION_HOURS = 24

    # Performance thresholds for alerting
    DEFAULT_THRESHOLDS = {
        PerformanceMetric.LATENCY: 5000.0,  # 5 seconds
        PerformanceMetric.ERROR_RATE: 0.05,  # 5%
        PerformanceMetric.MEMORY_USAGE: 0.9,  # 90%
    }

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        retention_hours: int = DEFAULT_RETENTION_HOURS,
    ):
        """
        Initialize the performance monitor.

        Args:
            config: AgentCore configuration
            retention_hours: How long to keep performance data
        """
        self.config = config or get_config()
        self._cloudwatch_client: Optional[CloudWatchClient] = None

        # Performance data storage
        self._snapshots: List[PerformanceSnapshot] = []
        self._stats: Dict[str, PerformanceStats] = defaultdict(
            lambda: PerformanceStats(metric_name="")
        )

        # Threshold tracking
        self._thresholds = self.DEFAULT_THRESHOLDS.copy()

        # Validate region compliance for Phase 9
        if self.config.aws_region != PHASE_9_REGION:
            safe_log(
                f"PerformanceMonitor: Region '{self.config.aws_region}' specified, "
                f"but Phase 9 requires '{PHASE_9_REGION}'. "
                f"All metrics will be sent to {PHASE_9_REGION} for compliance."
            )

        safe_log("PerformanceMonitor initialized")

    def _get_cloudwatch_client(self) -> CloudWatchClient:
        """Lazy initialization of CloudWatch client."""
        if self._cloudwatch_client is None:
            self._cloudwatch_client = CloudWatchClient(config=self.config)
        return self._cloudwatch_client

    def set_threshold(self, metric: PerformanceMetric, value: float) -> None:
        """
        Set performance threshold for alerting.

        Args:
            metric: Performance metric
            value: Threshold value
        """
        self._thresholds[metric] = value

    def record_metric(
        self,
        metric: str,
        value: float,
        dimensions: Optional[List[MetricDimension]] = None,
        account_id: Optional[str] = None,
    ) -> None:
        """
        Record a performance metric value.

        Args:
            metric: Metric name
            value: Metric value
            dimensions: Optional dimensions
            account_id: Optional account ID
        """
        # Update statistics
        if metric not in self._stats:
            self._stats[metric] = PerformanceStats(metric_name=metric)
        self._stats[metric].update(value)

        # Create snapshot
        all_dimensions = dimensions or []
        all_dimensions.append(MetricDimension("Region", PHASE_9_REGION))
        if account_id:
            all_dimensions.append(MetricDimension("AccountId", account_id[:8]))

        snapshot = PerformanceSnapshot(
            timestamp=datetime.utcnow(),
            metrics={metric: value},
            dimensions=all_dimensions,
        )

        self._snapshots.append(snapshot)

        # Check threshold
        self._check_threshold(metric, value)

        # Cleanup old snapshots
        self._cleanup_old_snapshots()

    def _check_threshold(self, metric: str, value: float) -> None:
        """Check if value exceeds threshold."""
        try:
            metric_enum = PerformanceMetric(metric)
            threshold = self._thresholds.get(metric_enum)

            if threshold and value > threshold:
                safe_log(
                    f"Performance threshold exceeded: {metric}={value} > {threshold}",
                    level="warning"
                )

        except ValueError:
            # Not a known performance metric type
            pass

    def _cleanup_old_snapshots(self) -> None:
        """Remove snapshots older than retention period."""
        cutoff = datetime.utcnow() - timedelta(hours=self.DEFAULT_RETENTION_HOURS)
        self._snapshots = [
            s for s in self._snapshots
            if s.timestamp > cutoff
        ]

    def get_statistics(
        self,
        metric: str,
    ) -> Optional[PerformanceStats]:
        """
        Get statistics for a metric.

        Args:
            metric: Metric name

        Returns:
            PerformanceStats if metric exists, None otherwise
        """
        return self._stats.get(metric)

    def get_recent_snapshots(
        self,
        metric: Optional[str] = None,
        limit: int = 100,
    ) -> List[PerformanceSnapshot]:
        """
        Get recent performance snapshots.

        Args:
            metric: Optional metric name to filter by
            limit: Maximum number of snapshots to return

        Returns:
            List of recent snapshots
        """
        snapshots = self._snapshots[-limit:]

        if metric:
            snapshots = [
                s for s in snapshots
                if metric in s.metrics
            ]

        return snapshots

    def get_percentile(
        self,
        metric: str,
        percentile: float = 95.0,
    ) -> Optional[float]:
        """
        Calculate percentile for a metric.

        Args:
            metric: Metric name
            percentile: Percentile to calculate (0-100)

        Returns:
            Percentile value if data exists, None otherwise
        """
        snapshots = self.get_recent_snapshots(metric)
        if not snapshots:
            return None

        values = [s.metrics.get(metric, 0) for s in snapshots]
        values.sort()

        if not values:
            return None

        index = int(len(values) * percentile / 100)
        index = min(index, len(values) - 1)
        return values[index]

    async def flush_to_cloudwatch(
        self,
        account_id: Optional[str] = None,
    ) -> bool:
        """
        Flush aggregated statistics to CloudWatch.

        Args:
            account_id: Optional account ID

        Returns:
            True if flush was successful
        """
        try:
            client = self._get_cloudwatch_client()

            tasks = []
            for metric_name, stats in self._stats.items():
                if stats.count > 0:
                    # Send average value
                    datum = MetricDatum(
                        metric_name=f"{metric_name}Avg",
                        value=stats.avg,
                        dimensions=[
                            MetricDimension("Region", PHASE_9_REGION),
                        ],
                    )
                    tasks.append(client.put_metric(datum))

                    # Send min/max
                    if stats.count > 0:
                        datum_min = MetricDatum(
                            metric_name=f"{metric_name}Min",
                            value=stats.min if stats.min != float("inf") else 0,
                            dimensions=[MetricDimension("Region", PHASE_9_REGION)],
                        )
                        tasks.append(client.put_metric(datum_min))

                        datum_max = MetricDatum(
                            metric_name=f"{metric_name}Max",
                            value=stats.max,
                            dimensions=[MetricDimension("Region", PHASE_9_REGION)],
                        )
                        tasks.append(client.put_metric(datum_max))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                safe_log(
                    f"Failed to send {len(failures)} metrics to CloudWatch",
                    level="warning"
                )
                return False

            safe_log(f"Flushed {len(tasks)} performance metrics to CloudWatch")

            # Clear statistics after flush
            self._stats.clear()

            return True

        except Exception as e:
            safe_log(f"Failed to flush performance metrics: {e}", level="error")
            return False


# ============================================================================
# Context Managers
# ============================================================================

class LatencyTracker:
    """
    Context manager for tracking operation latency.

    Usage:
        ```python
        with LatencyTracker(monitor, "AgentExecution"):
            await agent.execute()
        ```
    """

    def __init__(
        self,
        monitor: PerformanceMonitor,
        operation: str,
        dimensions: Optional[List[MetricDimension]] = None,
        account_id: Optional[str] = None,
    ):
        self.monitor = monitor
        self.operation = operation
        self.dimensions = dimensions or []
        self.account_id = account_id
        self.start_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            latency_ms = (time.time() - self.start_time) * 1000
            self.monitor.record_metric(
                self.operation,
                latency_ms,
                self.dimensions,
                self.account_id,
            )


# ============================================================================
# Convenience Functions
# ============================================================================

def get_performance_monitor(config: Optional[AgentCoreConfig] = None) -> PerformanceMonitor:
    """
    Get the performance monitor instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        PerformanceMonitor instance
    """
    return PerformanceMonitor(config=config)


async def track_latency(
    operation: str,
    monitor: Optional[PerformanceMonitor] = None,
    config: Optional[AgentCoreConfig] = None,
) -> LatencyTracker:
    """
    Convenience function to create a latency tracker.

    Args:
        operation: Operation name
        monitor: Optional performance monitor
        config: Optional AgentCore configuration

    Returns:
        LatencyTracker context manager
    """
    if monitor is None:
        monitor = get_performance_monitor(config)
    return LatencyTracker(monitor, operation)


# Export public symbols
__all__ = [
    "PHASE_9_REGION",
    "PerformanceMetric",
    "PerformanceSnapshot",
    "PerformanceStats",
    "PerformanceMonitor",
    "LatencyTracker",
    "get_performance_monitor",
    "track_latency",
]
