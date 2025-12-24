"""
AgentCore Redis Cache (Phase 10)

Redis-based caching layer for AgentCore operations in ap-southeast-2.

Phase 10: All caching operations support ap-southeast-2 (Australia) region for
data residency compliance, with multi-region key namespacing.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class CacheEntryStatus(str, Enum):
    """Status of a cache entry."""
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    EXPIRED = "expired"


@dataclass
class CacheEntry:
    """
    A cached entry with metadata.

    Attributes:
        key: Cache key
        value: Cached value
        created_at: When entry was created
        accessed_at: When entry was last accessed
        ttl_seconds: Time-to-live in seconds
        access_count: Number of times accessed
        size_bytes: Approximate size in bytes
        metadata: Additional metadata
    """
    key: str
    value: Any
    created_at: datetime
    accessed_at: datetime
    ttl_seconds: int
    access_count: int = 0
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds <= 0:
            return False  # Never expires
        age = (datetime.utcnow() - self.created_at).total_seconds()
        return age >= self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "access_count": self.access_count,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
            "is_expired": self.is_expired(),
        }


@dataclass
class CacheStats:
    """
    Cache statistics.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        evictions: Number of evictions
        total_entries: Total entries in cache
        total_size_bytes: Total cache size in bytes
        hit_rate: Cache hit rate (0-1)
    """
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    total_size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_entries": self.total_entries,
            "total_size_bytes": self.total_size_bytes,
            "hit_rate": self.hit_rate,
            "region": PHASE_10_REGION,
        }


# ============================================================================
# Redis Cache Implementation
# ============================================================================

class AgentCoreCache:
    """
    Redis-based caching for AgentCore operations.

    Features:
    - Async Redis operations
    - Account-based key namespacing
    - Configurable TTL
    - Cache statistics tracking
    - Automatic connection pooling
    - Graceful degradation when Redis unavailable

    Usage:
        ```python
        cache = AgentCoreCache(config)
        await cache.initialize()

        # Set and get
        await cache.set(account_id="account-123", key="agent_config", value={"model": "claude"})
        value = await cache.get(account_id="account-123", key="agent_config")

        # Delete
        await cache.delete(account_id="account-123", key="agent_config")

        # Clear account cache
        await cache.clear_account(account_id="account-123")
        ```
    """

    # Cache configuration
    CACHE_PREFIX = "agentcore"
    DEFAULT_TTL = 3600  # 1 hour
    MAX_KEY_LENGTH = 250  # Redis limit
    MAX_VALUE_SIZE = 1024 * 1024  # 1MB default

    # Connection pool settings
    CONNECTION_POOL_SIZE = 10
    CONNECTION_TIMEOUT = 5
    SOCKET_TIMEOUT = 5
    SOCKET_CONNECT_TIMEOUT = 5

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        enabled: bool = True,
        default_ttl: int = DEFAULT_TTL,
        max_value_size: int = MAX_VALUE_SIZE,
    ):
        """
        Initialize the Redis cache.

        Args:
            config: AgentCore configuration
            enabled: Whether caching is enabled
            default_ttl: Default TTL in seconds
            max_value_size: Maximum value size in bytes
        """
        self.config = config or get_config()
        self._enabled = enabled and self.config.cache_enabled
        self._default_ttl = default_ttl
        self._max_value_size = max_value_size

        self._redis = None
        self._stats = CacheStats()
        self._lock = asyncio.Lock()

        # Validate region compliance for Phase 10
        if self.config.aws_region != PHASE_10_REGION:
            safe_log(
                f"AgentCoreCache: Region '{self.config.aws_region}' specified, "
                f"but Phase 10 requires '{PHASE_10_REGION}'. "
                f"Cache keys will include region identifier for compliance."
            )

        safe_log(f"AgentCoreCache initialized (enabled={self._enabled})")

    async def initialize(self) -> bool:
        """
        Initialize Redis connection.

        Returns:
            True if initialization successful
        """
        if not self._enabled:
            safe_log("Cache is disabled, skipping Redis initialization")
            return False

        try:
            import redis.asyncio as aioredis

            # Build Redis URL
            redis_url = f"redis://{self.config.redis_host}:{self.config.redis_port}"

            # Create connection pool
            self._redis = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=self.CONNECTION_POOL_SIZE,
                socket_timeout=self.SOCKET_TIMEOUT,
                socket_connect_timeout=self.SOCKET_CONNECT_TIMEOUT,
            )

            # Test connection
            await self._redis.ping()

            safe_log(f"Redis cache initialized: {self.config.redis_host}:{self.config.redis_port}")
            return True

        except Exception as e:
            safe_log(f"Failed to initialize Redis cache: {e}", level="warning")
            self._enabled = False
            self._redis = None
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            safe_log("Redis cache connection closed")

    def _make_key(self, account_id: str, key: str) -> str:
        """
        Create namespaced cache key.

        Format: {prefix}:{region}:{account_id}:{key}

        Args:
            account_id: Account ID
            key: Cache key

        Returns:
            Full cache key with namespace
        """
        full_key = f"{self.CACHE_PREFIX}:{self.config.aws_region}:{account_id}:{key}"

        # Truncate if too long
        if len(full_key) > self.MAX_KEY_LENGTH:
            # Hash the key part if too long
            import hashlib
            hash_suffix = hashlib.md5(key.encode()).hexdigest()[:8]
            prefix = full_key[:self.MAX_KEY_LENGTH - 9]
            full_key = f"{prefix}:{hash_suffix}"

        return full_key

    def _serialize_value(self, value: Any) -> str:
        """Serialize value to JSON string."""
        try:
            serialized = json.dumps(value)
            size = len(serialized.encode('utf-8'))

            if size > self._max_value_size:
                raise ValueError(f"Value size ({size} bytes) exceeds maximum ({self._max_value_size} bytes)")

            return serialized

        except Exception as e:
            raise ValueError(f"Failed to serialize value: {e}")

    def _deserialize_value(self, serialized: str) -> Any:
        """Deserialize JSON string to value."""
        try:
            return json.loads(serialized)
        except Exception as e:
            safe_log(f"Failed to deserialize cached value: {e}", level="warning")
            return None

    async def get(
        self,
        account_id: str,
        key: str,
    ) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            account_id: Account ID
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if not self._enabled or self._redis is None:
            self._stats.misses += 1
            return None

        try:
            cache_key = self._make_key(account_id, key)
            serialized = await self._redis.get(cache_key)

            if serialized is None:
                self._stats.misses += 1
                return None

            value = self._deserialize_value(serialized)
            self._stats.hits += 1

            return value

        except Exception as e:
            safe_log(f"Cache get failed for {key}: {e}", level="warning")
            self._stats.misses += 1
            return None

    async def set(
        self,
        account_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            account_id: Account ID
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: use default_ttl)

        Returns:
            True if set successful
        """
        if not self._enabled or self._redis is None:
            return False

        try:
            cache_key = self._make_key(account_id, key)
            serialized = self._serialize_value(value)
            ttl = ttl or self._default_ttl

            await self._redis.setex(cache_key, ttl, serialized)

            return True

        except Exception as e:
            safe_log(f"Cache set failed for {key}: {e}", level="warning")
            return False

    async def delete(
        self,
        account_id: str,
        key: str,
    ) -> bool:
        """
        Delete value from cache.

        Args:
            account_id: Account ID
            key: Cache key

        Returns:
            True if deleted (or didn't exist)
        """
        if not self._enabled or self._redis is None:
            return False

        try:
            cache_key = self._make_key(account_id, key)
            await self._redis.delete(cache_key)
            return True

        except Exception as e:
            safe_log(f"Cache delete failed for {key}: {e}", level="warning")
            return False

    async def exists(
        self,
        account_id: str,
        key: str,
    ) -> bool:
        """
        Check if key exists in cache.

        Args:
            account_id: Account ID
            key: Cache key

        Returns:
            True if key exists
        """
        if not self._enabled or self._redis is None:
            return False

        try:
            cache_key = self._make_key(account_id, key)
            return await self._redis.exists(cache_key) > 0

        except Exception as e:
            safe_log(f"Cache exists check failed for {key}: {e}", level="warning")
            return False

    async def clear_account(self, account_id: str) -> int:
        """
        Clear all cache entries for an account.

        Args:
            account_id: Account ID

        Returns:
            Number of keys deleted
        """
        if not self._enabled or self._redis is None:
            return 0

        try:
            # Find all keys for this account
            pattern = self._make_key(account_id, "*")
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                await self._redis.delete(*keys)

            safe_log(f"Cleared {len(keys)} cache entries for account {account_id[:8]}...")
            return len(keys)

        except Exception as e:
            safe_log(f"Cache clear failed for account {account_id[:8]}...: {e}", level="warning")
            return 0

    async def get_stats(self) -> CacheStats:
        """
        Get cache statistics.

        Returns:
            Current cache statistics
        """
        # Update total entries from Redis
        if self._enabled and self._redis is not None:
            try:
                pattern = f"{self.CACHE_PREFIX}:{self.config.aws_region}:*"
                keys = []
                async for key in self._redis.scan_iter(match=pattern, count=100):
                    keys.append(key)

                self._stats.total_entries = len(keys)

                # Estimate total size (info command may not be available)
                info = await self._redis.info("memory")
                self._stats.total_size_bytes = info.get("used_memory", 0)

            except Exception as e:
                safe_log(f"Failed to get cache stats from Redis: {e}", level="warning")

        return self._stats

    async def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = CacheStats()


# ============================================================================
# Cache Decorators
# ============================================================================

def cached(
    ttl: int = AgentCoreCache.DEFAULT_TTL,
    key_prefix: str = "",
    account_id_param: str = "account_id",
):
    """
    Decorator for caching function results.

    Args:
        ttl: Time-to-live in seconds
        key_prefix: Prefix for cache key
        account_id_param: Parameter name containing account_id

    Usage:
        ```python
        @cached(ttl=300, key_prefix="agent_config")
        async def get_agent_config(account_id: str, agent_id: str):
            return fetch_config(account_id, agent_id)
        ```
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Extract account_id from parameters
            account_id = kwargs.get(account_id_param)
            if not account_id and len(args) > 0:
                # Try to get from positional args
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                if account_id_param in param_names:
                    idx = param_names.index(account_id_param)
                    if idx < len(args):
                        account_id = args[idx]

            if not account_id:
                return await func(*args, **kwargs)

            # Build cache key
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{kwargs}"
            cache_key = cache_key.replace(" ", "_")[:200]  # Sanitize

            # Get cache instance
            cache = get_cache()
            if cache:
                # Try cache first
                cached_value = await cache.get(account_id, cache_key)
                if cached_value is not None:
                    return cached_value

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            if cache and result is not None:
                await cache.set(account_id, cache_key, result, ttl=ttl)

            return result

        return wrapper
    return decorator


# ============================================================================
# Convenience Functions
# ============================================================================

_cache_instance: Optional[AgentCoreCache] = None


def get_cache(config: Optional[AgentCoreConfig] = None) -> Optional[AgentCoreCache]:
    """
    Get the cache instance (singleton).

    Args:
        config: Optional AgentCore configuration

    Returns:
        AgentCoreCache instance or None if caching disabled
    """
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = AgentCoreCache(config=config)

    return _cache_instance


async def initialize_cache(config: Optional[AgentCoreConfig] = None) -> bool:
    """
    Initialize the cache instance.

    Args:
        config: Optional AgentCore configuration

    Returns:
        True if initialization successful
    """
    cache = get_cache(config)
    if cache:
        return await cache.initialize()
    return False


async def close_cache() -> None:
    """Close the cache instance."""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.close()
        _cache_instance = None


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "CacheEntryStatus",
    "CacheEntry",
    "CacheStats",
    "AgentCoreCache",
    "cached",
    "get_cache",
    "initialize_cache",
    "close_cache",
]
