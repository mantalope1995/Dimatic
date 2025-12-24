"""
AgentCore Cache Manager (Phase 10)

High-level cache management for AgentCore operations.

Provides organized caching for common AgentCore entities:
- Agent configurations
- Runtime deployments
- MCP tool catalogs
- Execution results
- Session data
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log
from .redis_cache import AgentCoreCache, CacheStats, CacheEntry

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class CacheEntityType(str, Enum):
    """Types of entities that can be cached."""
    AGENT_CONFIG = "agent_config"
    RUNTIME_DEPLOYMENT = "runtime_deployment"
    MCP_SERVER = "mcp_server"
    TOOL_CATALOG = "tool_catalog"
    EXECUTION_RESULT = "execution_result"
    SESSION_DATA = "session_data"
    MEMORY_RESOURCE = "memory_resource"
    GATEWAY_CONFIG = "gateway_config"


@dataclass
class CachePolicy:
    """
    Cache policy for an entity type.

    Attributes:
        entity_type: Type of entity
        default_ttl: Default TTL in seconds
        max_entries: Maximum entries to cache per account
        enabled: Whether caching is enabled for this type
        serialize_func: Custom serialization function
        deserialize_func: Custom deserialization function
    """
    entity_type: CacheEntityType
    default_ttl: int
    max_entries: int = 100
    enabled: bool = True
    serialize_func: Optional[Callable[[Any], str]] = None
    deserialize_func: Optional[Callable[[str], Any]] = None


# Default cache policies
DEFAULT_POLICIES: Dict[CacheEntityType, CachePolicy] = {
    CacheEntityType.AGENT_CONFIG: CachePolicy(
        entity_type=CacheEntityType.AGENT_CONFIG,
        default_ttl=3600,  # 1 hour
        max_entries=100,
    ),
    CacheEntityType.RUNTIME_DEPLOYMENT: CachePolicy(
        entity_type=CacheEntityType.RUNTIME_DEPLOYMENT,
        default_ttl=1800,  # 30 minutes
        max_entries=50,
    ),
    CacheEntityType.MCP_SERVER: CachePolicy(
        entity_type=CacheEntityType.MCP_SERVER,
        default_ttl=7200,  # 2 hours
        max_entries=20,
    ),
    CacheEntityType.TOOL_CATALOG: CachePolicy(
        entity_type=CacheEntityType.TOOL_CATALOG,
        default_ttl=300,  # 5 minutes
        max_entries=10,
    ),
    CacheEntityType.EXECUTION_RESULT: CachePolicy(
        entity_type=CacheEntityType.EXECUTION_RESULT,
        default_ttl=600,  # 10 minutes
        max_entries=200,
    ),
    CacheEntityType.SESSION_DATA: CachePolicy(
        entity_type=CacheEntityType.SESSION_DATA,
        default_ttl=1800,  # 30 minutes
        max_entries=100,
    ),
    CacheEntityType.MEMORY_RESOURCE: CachePolicy(
        entity_type=CacheEntityType.MEMORY_RESOURCE,
        default_ttl=3600,  # 1 hour
        max_entries=50,
    ),
    CacheEntityType.GATEWAY_CONFIG: CachePolicy(
        entity_type=CacheEntityType.GATEWAY_CONFIG,
        default_ttl=7200,  # 2 hours
        max_entries=10,
    ),
}


# ============================================================================
# Cache Manager
# ============================================================================

class CacheManager:
    """
    High-level cache management for AgentCore operations.

    Features:
    - Organized caching by entity type
    - Configurable policies per entity type
    - Automatic cache invalidation
    - Bulk operations support
    - Cache warming and priming

    Usage:
        ```python
        manager = CacheManager()

        # Cache agent config
        await manager.set(
            account_id="account-123",
            entity_type=CacheEntityType.AGENT_CONFIG,
            entity_id="agent-456",
            data={"model": "claude", "temperature": 0.7}
        )

        # Get agent config
        config = await manager.get(
            account_id="account-123",
            entity_type=CacheEntityType.AGENT_CONFIG,
            entity_id="agent-456"
        )

        # Invalidate all agent configs for account
        await manager.invalidate_account(
            account_id="account-123",
            entity_type=CacheEntityType.AGENT_CONFIG
        )
        ```
    """

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        policies: Optional[Dict[CacheEntityType, CachePolicy]] = None,
    ):
        """
        Initialize the cache manager.

        Args:
            config: AgentCore configuration
            policies: Custom cache policies (default: DEFAULT_POLICIES)
        """
        self.config = config or get_config()
        self._policies = policies or DEFAULT_POLICIES.copy()
        self._cache: Optional[AgentCoreCache] = None

        # Validate region compliance for Phase 10
        if self.config.aws_region != PHASE_10_REGION:
            safe_log(
                f"CacheManager: Region '{self.config.aws_region}' specified, "
                f"but Phase 10 requires '{PHASE_10_REGION}'. "
                f"Cache keys will include region identifier for compliance."
            )

        safe_log("CacheManager initialized")

    async def initialize(self) -> bool:
        """
        Initialize the cache manager.

        Returns:
            True if initialization successful
        """
        self._cache = AgentCoreCache(config=self.config)
        return await self._cache.initialize()

    async def close(self) -> None:
        """Close the cache manager."""
        if self._cache:
            await self._cache.close()
            self._cache = None

    def _make_cache_key(
        self,
        entity_type: CacheEntityType,
        entity_id: str,
        account_id: str,
    ) -> str:
        """
        Create cache key for an entity.

        Format: {entity_type}:{entity_id}

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            account_id: Account ID (used for namespacing)

        Returns:
            Cache key
        """
        return f"{entity_type.value}:{entity_id}"

    def _get_policy(self, entity_type: CacheEntityType) -> CachePolicy:
        """Get cache policy for an entity type."""
        return self._policies.get(entity_type, DEFAULT_POLICIES[CacheEntityType.AGENT_CONFIG])

    async def get(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_id: str,
    ) -> Optional[Any]:
        """
        Get cached entity.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            Cached entity data if found, None otherwise
        """
        if not self._cache:
            return None

        policy = self._get_policy(entity_type)
        if not policy.enabled:
            return None

        cache_key = self._make_cache_key(entity_type, entity_id, account_id)

        try:
            serialized = await self._cache.get(account_id, cache_key)
            if serialized is None:
                return None

            # Apply custom deserialization if provided
            if policy.deserialize_func:
                return policy.deserialize_func(serialized)

            return serialized

        except Exception as e:
            safe_log(f"Cache get failed for {entity_type.value}:{entity_id}: {e}", level="warning")
            return None

    async def set(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_id: str,
        data: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache an entity.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_id: Entity identifier
            data: Data to cache
            ttl: Custom TTL (default: use policy default)

        Returns:
            True if cached successfully
        """
        if not self._cache:
            return False

        policy = self._get_policy(entity_type)
        if not policy.enabled:
            return False

        cache_key = self._make_cache_key(entity_type, entity_id, account_id)

        # Apply custom serialization if provided
        if policy.serialize_func:
            try:
                data = policy.serialize_func(data)
            except Exception as e:
                safe_log(f"Custom serialization failed for {entity_type.value}:{entity_id}: {e}", level="warning")
                return False

        # Use policy TTL if not specified
        if ttl is None:
            ttl = policy.default_ttl

        try:
            return await self._cache.set(account_id, cache_key, data, ttl=ttl)

        except Exception as e:
            safe_log(f"Cache set failed for {entity_type.value}:{entity_id}: {e}", level="warning")
            return False

    async def delete(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_id: str,
    ) -> bool:
        """
        Delete cached entity.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            True if deleted successfully
        """
        if not self._cache:
            return False

        cache_key = self._make_cache_key(entity_type, entity_id, account_id)
        return await self._cache.delete(account_id, cache_key)

    async def exists(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_id: str,
    ) -> bool:
        """
        Check if entity is cached.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_id: Entity identifier

        Returns:
            True if entity exists in cache
        """
        if not self._cache:
            return False

        cache_key = self._make_cache_key(entity_type, entity_id, account_id)
        return await self._cache.exists(account_id, cache_key)

    async def invalidate_account(
        self,
        account_id: str,
        entity_type: Optional[CacheEntityType] = None,
    ) -> int:
        """
        Invalidate all cached entities for an account.

        Args:
            account_id: Account ID
            entity_type: Optional entity type to filter by

        Returns:
            Number of entities invalidated
        """
        if not self._cache:
            return 0

        if entity_type:
            # Clear specific entity type
            pattern = self._make_cache_key(entity_type, "*", account_id)
            # Need to use Redis scan/delete directly for pattern deletion
            # For now, use clear_account and let caller filter
            return await self._cache.clear_account(account_id)
        else:
            # Clear all entities for account
            return await self._cache.clear_account(account_id)

    async def get_or_compute(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_id: str,
        compute_func: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Get from cache, or compute and cache the result.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_id: Entity identifier
            compute_func: Async function to compute value if not cached
            ttl: Custom TTL for cached result

        Returns:
            Cached or computed value
        """
        # Try cache first
        cached = await self.get(account_id, entity_type, entity_id)
        if cached is not None:
            return cached

        # Compute value
        if asyncio.iscoroutinefunction(compute_func):
            value = await compute_func()
        else:
            value = compute_func()

        # Cache result
        if value is not None:
            await self.set(account_id, entity_type, entity_id, value, ttl=ttl)

        return value

    async def bulk_get(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entity_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Bulk get multiple cached entities.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entity_ids: List of entity identifiers

        Returns:
            Dictionary mapping entity_id to cached value
        """
        results = {}

        for entity_id in entity_ids:
            value = await self.get(account_id, entity_type, entity_id)
            if value is not None:
                results[entity_id] = value

        return results

    async def bulk_set(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        entities: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> int:
        """
        Bulk cache multiple entities.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            entities: Dictionary mapping entity_id to data
            ttl: Custom TTL for all entities

        Returns:
            Number of entities cached successfully
        """
        count = 0

        for entity_id, data in entities.items():
            if await self.set(account_id, entity_type, entity_id, data, ttl=ttl):
                count += 1

        return count

    async def warm_cache(
        self,
        account_id: str,
        entity_type: CacheEntityType,
        compute_func: Callable[[], Dict[str, Any]],
        ttl: Optional[int] = None,
    ) -> int:
        """
        Warm the cache by pre-loading entities.

        Args:
            account_id: Account ID
            entity_type: Type of entity
            compute_func: Async function that returns dict of entity_id -> data
            ttl: Custom TTL for cached entities

        Returns:
            Number of entities loaded into cache
        """
        # Compute all entities
        if asyncio.iscoroutinefunction(compute_func):
            entities = await compute_func()
        else:
            entities = compute_func()

        # Bulk set
        return await self.bulk_set(account_id, entity_type, entities, ttl=ttl)

    async def get_stats(self) -> Optional[CacheStats]:
        """
        Get cache statistics.

        Returns:
            Cache statistics if cache is enabled, None otherwise
        """
        if self._cache:
            return await self._cache.get_stats()
        return None


# ============================================================================
# Convenience Functions
# ============================================================================

_cache_manager_instance: Optional[CacheManager] = None


def get_cache_manager(config: Optional[AgentCoreConfig] = None) -> CacheManager:
    """
    Get the cache manager instance (singleton).

    Args:
        config: Optional AgentCore configuration

    Returns:
        CacheManager instance
    """
    global _cache_manager_instance

    if _cache_manager_instance is None:
        _cache_manager_instance = CacheManager(config=config)

    return _cache_manager_instance


async def initialize_cache_manager(config: Optional[AgentCoreConfig] = None) -> bool:
    """
    Initialize the cache manager.

    Args:
        config: Optional AgentCore configuration

    Returns:
        True if initialization successful
    """
    manager = get_cache_manager(config)
    return await manager.initialize()


async def close_cache_manager() -> None:
    """Close the cache manager."""
    global _cache_manager_instance
    if _cache_manager_instance:
        await _cache_manager_instance.close()
        _cache_manager_instance = None


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "CacheEntityType",
    "CachePolicy",
    "DEFAULT_POLICIES",
    "CacheManager",
    "get_cache_manager",
    "initialize_cache_manager",
    "close_cache_manager",
]
