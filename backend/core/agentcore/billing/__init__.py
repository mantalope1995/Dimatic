"""
AgentCore Billing Module

Provides usage tracking, billing integration, and tier-based features
for AgentCore execution in ap-southeast-2 (Australia) region.

Phase 8: All billing operations use ap-southeast-2 region for data residency compliance.

Exports:
    - UsageMetrics: Usage metrics dataclass for tracking executions
    - CreditCost: Credit cost calculation breakdown
    - UsageTracker: Main usage tracking service
    - get_usage_tracker: Convenience function to get tracker instance
    - track_agent_execution: Start tracking execution
    - complete_agent_execution: Complete tracking with billing
"""

from .usage_tracker import (
    UsageMetrics,
    CreditCost,
    UsageTracker,
    get_usage_tracker,
    track_agent_execution,
    complete_agent_execution,
)

__all__ = [
    "UsageMetrics",
    "CreditCost",
    "UsageTracker",
    "get_usage_tracker",
    "track_agent_execution",
    "complete_agent_execution",
]
