"""
AgentCore Cache Module (Phase 10)

Redis-based caching layer for AgentCore operations in ap-southeast-2.

Phase 10: All caching operations support ap-southeast-2 (Australia) region for
data residency compliance, with multi-region key namespacing.

Exports:
    - AgentCoreCache: Redis cache client
    - CacheManager: High-level cache management
    - CacheEntityType: Types of cached entities
    - CachePolicy: Cache policy configuration
    - CacheStats: Cache statistics
    - CacheEntry: Individual cache entry
    - cached: Decorator for caching function results
"""

from .redis_cache import (
    PHASE_10_REGION as REDIS_CACHE_REGION,
    CacheEntryStatus,
    CacheEntry,
    CacheStats,
    AgentCoreCache,
    cached,
    get_cache,
    initialize_cache,
    close_cache,
)

from .cache_manager import (
    PHASE_10_REGION as CACHE_MANAGER_REGION,
    CacheEntityType,
    CachePolicy,
    DEFAULT_POLICIES,
    CacheManager,
    get_cache_manager,
    initialize_cache_manager,
    close_cache_manager,
)

# Use consistent region export
PHASE_10_REGION = REDIS_CACHE_REGION

__all__ = [
    "PHASE_10_REGION",
    # Redis Cache
    "CacheEntryStatus",
    "CacheEntry",
    "CacheStats",
    "AgentCoreCache",
    "cached",
    "get_cache",
    "initialize_cache",
    "close_cache",
    # Cache Manager
    "CacheEntityType",
    "CachePolicy",
    "DEFAULT_POLICIES",
    "CacheManager",
    "get_cache_manager",
    "initialize_cache_manager",
    "close_cache_manager",
]
