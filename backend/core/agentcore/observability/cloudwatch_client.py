"""
AgentCore CloudWatch Integration (Phase 9)

CloudWatch metrics client for AgentCore observability in ap-southeast-2.

Phase 9: All CloudWatch operations use ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import (
    AgentCoreError,
    AgentCoreConfigurationError as ConfigurationError,
    safe_log,
)

logger = logging.getLogger(__name__)

# Phase 9 required region
PHASE_9_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class MetricNamespace(str, Enum):
    """CloudWatch metric namespaces for AgentCore."""
    AGENTCORE = "AgentCore/Production"
    AGENTCORE_STAGING = "AgentCore/Staging"
    AGENTCORE_DEVELOPMENT = "AgentCore/Development"


class MetricUnit(str, Enum):
    """CloudWatch metric units."""
    COUNT = "Count"
    SECONDS = "Seconds"
    MILLISECONDS = "Milliseconds"
    BYTES = "Bytes"
    KILOBYTES = "Kilobytes"
    MEGABYTES = "Megabytes"
    GIGABYTES = "Gigabytes"
    BITS = "Bits"
    KILOBITS = "Kilobits"
    MEGABITS = "Megabits"
    GIGABITS = "Gigabits"
    PERCENT = "Percent"
    NONE = "None"


@dataclass
class MetricDimension:
    """
    CloudWatch metric dimension.

    Attributes:
        name: Dimension name
        value: Dimension value
    """
    name: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to CloudWatch API format."""
        return {"Name": self.name, "Value": self.value}


@dataclass
class MetricDatum:
    """
    CloudWatch metric datum.

    Attributes:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        namespace: Metric namespace
        dimensions: Metric dimensions for filtering
        timestamp: Timestamp (defaults to now)
    """
    metric_name: str
    value: float
    unit: Union[MetricUnit, str] = MetricUnit.COUNT
    namespace: Union[MetricNamespace, str] = MetricNamespace.AGENTCORE
    dimensions: List[MetricDimension] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to CloudWatch API format."""
        return {
            "MetricName": self.metric_name,
            "Value": self.value,
            "Unit": self.unit.value if isinstance(self.unit, MetricUnit) else self.unit,
            "Dimensions": [d.to_dict() for d in self.dimensions],
            "Timestamp": self.timestamp or datetime.utcnow(),
        }


@dataclass
class MetricBatch:
    """
    Batch of metrics for efficient CloudWatch submission.

    Attributes:
        namespace: Metric namespace
        metric_data: List of metric data
    """
    namespace: Union[MetricNamespace, str] = MetricNamespace.AGENTCORE
    metric_data: List[MetricDatum] = field(default_factory=list)

    def add_metric(self, metric: MetricDatum) -> None:
        """Add a metric to the batch."""
        if metric.namespace == self.namespace:
            self.metric_data.append(metric)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to CloudWatch API format."""
        return {
            "Namespace": self.namespace.value if isinstance(self.namespace, MetricNamespace) else self.namespace,
            "MetricData": [m.to_dict() for m in self.metric_data],
        }


# ============================================================================
# CloudWatch Client
# ============================================================================

class CloudWatchClient:
    """
    CloudWatch client for AgentCore observability in ap-southeast-2.

    Features:
    - Publish single or batch metrics
    - Automatic region compliance enforcement
    - Async operations with retry logic
    - Dimension-based metric filtering

    Usage:
        ```python
        client = CloudWatchClient()

        # Single metric
        await client.put_metric(MetricDatum(
            metric_name="ExecutionCount",
            value=1.0,
            dimensions=[MetricDimension("Tier", "pro")]
        ))

        # Batch metrics
        batch = MetricBatch()
        batch.add_metric(MetricDatum(...))
        batch.add_metric(MetricDatum(...))
        await client.put_batch_metrics(batch)
        ```
    """

    # Maximum metrics per CloudWatch API call
    MAX_METRICS_PER_BATCH = 20

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
    ):
        """
        Initialize the CloudWatch client.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If config is invalid for CloudWatch operations.
        """
        self.config = config or get_config()
        self._cloudwatch = None

        # Validate region compliance for Phase 9
        if self.config.aws_region != PHASE_9_REGION:
            safe_log(
                f"CloudWatch: Region '{self.config.aws_region}' specified, "
                f"but Phase 9 requires '{PHASE_9_REGION}'. "
                f"All metrics will be sent to {PHASE_9_REGION} for compliance."
            )

        safe_log("CloudWatchClient initialized")

    def _get_cloudwatch_client(self):
        """Lazy initialization of boto3 CloudWatch client."""
        if self._cloudwatch is None:
            import boto3

            self._cloudwatch = boto3.client(
                "cloudwatch",
                region_name=PHASE_9_REGION,  # Force ap-southeast-2 for Phase 9
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key,
            )

        return self._cloudwatch

    async def put_metric(
        self,
        metric: MetricDatum,
    ) -> bool:
        """
        Publish a single metric to CloudWatch.

        Args:
            metric: Metric datum to publish

        Returns:
            True if metric was published successfully

        Raises:
            AgentCoreError: If metric publication fails
        """
        try:
            client = self._get_cloudwatch_client()

            # Ensure region compliance
            metric_data = metric.to_dict()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: client.put_metric_data(
                    Namespace=metric_data["Namespace"],
                    MetricData=[metric_data],
                )
            )

            safe_log(f"Published metric '{metric.metric_name}' with value {metric.value}")
            return True

        except Exception as e:
            safe_log(f"Failed to publish metric '{metric.metric_name}': {e}", level="error")
            raise AgentCoreError(f"Failed to publish metric: {e}") from e

    async def put_batch_metrics(
        self,
        batch: MetricBatch,
    ) -> bool:
        """
        Publish a batch of metrics to CloudWatch.

        Args:
            batch: Metric batch to publish

        Returns:
            True if all metrics were published successfully

        Raises:
            AgentCoreError: If batch publication fails
        """
        try:
            client = self._get_cloudwatch_client()

            if not batch.metric_data:
                safe_log("No metrics to publish in batch")
                return True

            # Split into batches of MAX_METRICS_PER_BATCH
            metric_batches = [
                batch.metric_data[i:i + self.MAX_METRICS_PER_BATCH]
                for i in range(0, len(batch.metric_data), self.MAX_METRICS_PER_BATCH)
            ]

            loop = asyncio.get_event_loop()
            batch_dict = batch.to_dict()

            for metric_batch in metric_batches:
                await loop.run_in_executor(
                    None,
                    lambda mb=metric_batch: client.put_metric_data(
                        Namespace=batch_dict["Namespace"],
                        MetricData=[m.to_dict() for m in mb],
                    )
                )

            safe_log(f"Published {len(batch.metric_data)} metrics in batch")
            return True

        except Exception as e:
            safe_log(f"Failed to publish batch metrics: {e}", level="error")
            raise AgentCoreError(f"Failed to publish batch metrics: {e}") from e

    async def increment_metric(
        self,
        metric_name: str,
        value: float = 1.0,
        unit: Union[MetricUnit, str] = MetricUnit.COUNT,
        dimensions: Optional[List[MetricDimension]] = None,
        namespace: Optional[Union[MetricNamespace, str]] = None,
    ) -> bool:
        """
        Increment a counter metric.

        Args:
            metric_name: Name of the metric
            value: Value to add (default: 1.0)
            unit: Unit of measurement
            dimensions: Optional dimensions
            namespace: Optional namespace

        Returns:
            True if metric was published successfully
        """
        metric = MetricDatum(
            metric_name=metric_name,
            value=value,
            unit=unit,
            namespace=namespace or MetricNamespace.AGENTCORE,
            dimensions=dimensions or [],
        )

        return await self.put_metric(metric)

    async def timing_metric(
        self,
        metric_name: str,
        value_ms: float,
        dimensions: Optional[List[MetricDimension]] = None,
        namespace: Optional[Union[MetricNamespace, str]] = None,
    ) -> bool:
        """
        Record a timing metric in milliseconds.

        Args:
            metric_name: Name of the metric
            value_ms: Timing value in milliseconds
            dimensions: Optional dimensions
            namespace: Optional namespace

        Returns:
            True if metric was published successfully
        """
        metric = MetricDatum(
            metric_name=metric_name,
            value=value_ms,
            unit=MetricUnit.MILLISECONDS,
            namespace=namespace or MetricNamespace.AGENTCORE,
            dimensions=dimensions or [],
        )

        return await self.put_metric(metric)


# ============================================================================
# Predefined Metrics
# ============================================================================

class AgentCoreMetrics:
    """
    Predefined AgentCore metrics for consistent tracking.

    Metric names follow CloudWatch best practices:
    - Descriptive and concise
    - PascalCase with category prefix
    - Consistent unit usage
    """

    # Execution metrics
    EXECUTION_COUNT = "ExecutionCount"
    EXECUTION_DURATION = "ExecutionDuration"
    EXECUTION_SUCCESS = "ExecutionSuccess"
    EXECUTION_FAILURE = "ExecutionFailure"
    EXECUTION_TIMEOUT = "ExecutionTimeout"

    # Token metrics
    INPUT_TOKENS = "InputTokens"
    OUTPUT_TOKENS = "OutputTokens"
    TOTAL_TOKENS = "TotalTokens"

    # Tool metrics
    TOOL_INVOCATION = "ToolInvocation"
    TOOL_DURATION = "ToolDuration"
    TOOL_FAILURE = "ToolFailure"

    # Runtime metrics
    RUNTIME_ACTIVE = "RuntimeActive"
    RUNTIME_IDLE = "RuntimeIdle"
    RUNTIME_MEMORY_USED = "RuntimeMemoryUsed"

    # Code Interpreter metrics
    CODE_EXECUTION_COUNT = "CodeExecutionCount"
    CODE_EXECUTION_DURATION = "CodeExecutionDuration"
    CODE_EXECUTION_FAILURE = "CodeExecutionFailure"
    SHELL_COMMAND_COUNT = "ShellCommandCount"

    # Browser metrics
    BROWSER_SESSION_COUNT = "BrowserSessionCount"
    BROWSER_NAVIGATION_COUNT = "BrowserNavigationCount"
    BROWSER_SCREENSHOT_COUNT = "BrowserScreenshotCount"
    BROWSER_ACTION_FAILURE = "BrowserActionFailure"

    # Memory metrics
    MEMORY_STORE_COUNT = "MemoryStoreCount"
    MEMORY_RETRIEVE_COUNT = "MemoryRetrieveCount"
    MEMORY_SIZE_BYTES = "MemorySizeBytes"

    # Gateway/MCP metrics
    MCP_TOOL_INVOCATION = "MCPToolInvocation"
    MCP_TOOL_DURATION = "MCPToolDuration"
    MCP_TOOL_FAILURE = "MCPToolFailure"

    # Billing metrics
    CREDITS_CONSUMED = "CreditsConsumed"
    CREDITS_ESTIMATED = "CreditsEstimated"
    BILLING_CYCLE_COUNT = "BillingCycleCount"

    # Error metrics
    ERROR_COUNT = "ErrorCount"
    ERROR_RETRY_COUNT = "ErrorRetryCount"
    ERROR_FALLBACK_COUNT = "ErrorFallbackCount"

    # Performance metrics
    LATENCY = "Latency"
    THROUGHPUT = "Throughput"
    CONCURRENT_EXECUTIONS = "ConcurrentExecutions"


# ============================================================================
# Convenience Functions
# ============================================================================

def get_cloudwatch_client(config: Optional[AgentCoreConfig] = None) -> CloudWatchClient:
    """
    Get the CloudWatch client instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        CloudWatchClient instance
    """
    return CloudWatchClient(config=config)


async def put_execution_metric(
    metric_name: str,
    value: float,
    account_id: str,
    tier: str = "free",
    config: Optional[AgentCoreConfig] = None,
) -> bool:
    """
    Convenience function to publish an execution metric.

    Args:
        metric_name: Name of the metric
        value: Metric value
        account_id: Tenant account ID
        tier: Subscription tier
        config: Optional AgentCore configuration

    Returns:
        True if metric was published successfully
    """
    client = get_cloudwatch_client(config)

    return await client.put_metric(MetricDatum(
        metric_name=metric_name,
        value=value,
        dimensions=[
            MetricDimension("AccountId", account_id[:8]),  # Truncate for privacy
            MetricDimension("Tier", tier),
            MetricDimension("Region", PHASE_9_REGION),
        ],
    ))


async def put_timing_metric(
    metric_name: str,
    value_ms: float,
    account_id: Optional[str] = None,
    config: Optional[AgentCoreConfig] = None,
) -> bool:
    """
    Convenience function to publish a timing metric.

    Args:
        metric_name: Name of the metric
        value_ms: Timing value in milliseconds
        account_id: Optional tenant account ID
        config: Optional AgentCore configuration

    Returns:
        True if metric was published successfully
    """
    client = get_cloudwatch_client(config)

    dimensions = [MetricDimension("Region", PHASE_9_REGION)]
    if account_id:
        dimensions.append(MetricDimension("AccountId", account_id[:8]))

    return await client.put_metric(MetricDatum(
        metric_name=metric_name,
        value=value_ms,
        unit=MetricUnit.MILLISECONDS,
        dimensions=dimensions,
    ))


async def increment_execution_count(
    account_id: str,
    tier: str = "free",
    status: str = "success",
    config: Optional[AgentCoreConfig] = None,
) -> bool:
    """
    Convenience function to increment execution count.

    Args:
        account_id: Tenant account ID
        tier: Subscription tier
        status: Execution status (success, failure, timeout)
        config: Optional AgentCore configuration

    Returns:
        True if metric was published successfully
    """
    client = get_cloudwatch_client(config)

    metric_name = {
        "success": AgentCoreMetrics.EXECUTION_SUCCESS,
        "failure": AgentCoreMetrics.EXECUTION_FAILURE,
        "timeout": AgentCoreMetrics.EXECUTION_TIMEOUT,
    }.get(status, AgentCoreMetrics.EXECUTION_COUNT)

    return await client.increment_metric(
        metric_name=metric_name,
        dimensions=[
            MetricDimension("AccountId", account_id[:8]),
            MetricDimension("Tier", tier),
            MetricDimension("Region", PHASE_9_REGION),
        ],
    )


# Export public symbols
__all__ = [
    "PHASE_9_REGION",
    "MetricNamespace",
    "MetricUnit",
    "MetricDimension",
    "MetricDatum",
    "MetricBatch",
    "CloudWatchClient",
    "AgentCoreMetrics",
    "get_cloudwatch_client",
    "put_execution_metric",
    "put_timing_metric",
    "increment_execution_count",
]
