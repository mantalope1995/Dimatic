"""
AgentCore Observability Module

Provides CloudWatch integration, metrics collection, alerting,
and health monitoring for AgentCore operations in ap-southeast-2.

Phase 9: All observability operations use ap-southeast-2 (Australia) region.

Exports:
    - CloudWatchClient: CloudWatch metrics client
    - AlertingService: SNS/SES alert delivery
    - MetricsCollector: Centralized metrics collection
    - HealthChecker: Health status monitoring
    - PerformanceMonitor: Performance tracking
"""

from .cloudwatch_client import (
    PHASE_9_REGION as CLOUDWATCH_REGION,
    MetricNamespace,
    MetricUnit,
    MetricDimension,
    MetricDatum,
    MetricBatch,
    CloudWatchClient,
    AgentCoreMetrics,
    get_cloudwatch_client,
    put_execution_metric,
    put_timing_metric,
    increment_execution_count,
)

from .alerting_service import (
    PHASE_9_REGION as ALERTING_REGION,
    AlertSeverity,
    AlertChannel,
    AlertRecipient,
    Alert,
    AlertRule,
    AlertingService,
    DefaultAlertRules,
    get_alerting_service,
    send_alert,
)

from .metrics_collector import (
    PHASE_9_REGION as METRICS_REGION,
    MetricType,
    MetricRecord,
    MetricBuffer,
    MetricsCollector,
    ExecutionMetricsCollector,
    get_metrics_collector,
    get_execution_collector,
)

from .health_checker import (
    PHASE_9_REGION as HEALTH_REGION,
    HealthStatus,
    HealthCheckResult,
    SystemHealthSummary,
    HealthChecker,
    get_health_checker,
    check_system_health,
)

from .performance_monitor import (
    PHASE_9_REGION as PERF_REGION,
    PerformanceMetric,
    PerformanceSnapshot,
    PerformanceStats,
    PerformanceMonitor,
    LatencyTracker,
    get_performance_monitor,
    track_latency,
)

# Use PHASE_9_REGION consistently
PHASE_9_REGION = CLOUDWATCH_REGION

__all__ = [
    "PHASE_9_REGION",
    # CloudWatch
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
    # Alerting
    "AlertSeverity",
    "AlertChannel",
    "AlertRecipient",
    "Alert",
    "AlertRule",
    "AlertingService",
    "DefaultAlertRules",
    "get_alerting_service",
    "send_alert",
    # Metrics Collection
    "MetricType",
    "MetricRecord",
    "MetricBuffer",
    "MetricsCollector",
    "ExecutionMetricsCollector",
    "get_metrics_collector",
    "get_execution_collector",
    # Health Checking
    "HealthStatus",
    "HealthCheckResult",
    "SystemHealthSummary",
    "HealthChecker",
    "get_health_checker",
    "check_system_health",
    # Performance Monitoring
    "PerformanceMetric",
    "PerformanceSnapshot",
    "PerformanceStats",
    "PerformanceMonitor",
    "LatencyTracker",
    "get_performance_monitor",
    "track_latency",
]
