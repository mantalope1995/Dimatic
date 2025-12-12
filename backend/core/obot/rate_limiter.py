"""
Obot Rate Limiter Service

Distributed rate limiting for Obot MCP Gateway operations using Redis sliding window algorithm.
Provides per-user rate limiting for different operation types to prevent abuse.
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from core.services.redis import get_client
from core.utils.retry import retry

logger = logging.getLogger(__name__)


class ObotRateLimitError(Exception):
    """Exception raised when rate limit is exceeded"""
    def __init__(self, operation: str, user_id: str, retry_after: int, limit: int, window_seconds: int):
        self.operation = operation
        self.user_id = user_id
        self.retry_after = retry_after
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(
            f"Rate limit exceeded for user {user_id} on {operation}: "
            f"{limit} requests per {window_seconds} seconds. "
            f"Retry after {retry_after} seconds."
        )


class ObotRateLimiter:
    """
    Distributed rate limiter using Redis sorted sets for sliding window algorithm.
    
    Features:
    - Per-user, per-operation rate limiting
    - Sliding window algorithm for accurate rate limiting
    - Automatic cleanup of expired entries
    - Health check functionality
    - Support for multiple rate limit configurations
    
    Rate Limits:
    - Catalog queries: 100/minute
    - Server operations (create/delete): 10/minute
    - Tool calls: 60/minute
    - OAuth initiations: 5/minute
    """
    
    # Rate limit configurations
    RATE_LIMITS = {
        "catalog": {"limit": 100, "window_seconds": 60},
        "server_ops": {"limit": 10, "window_seconds": 60},
        "tool_calls": {"limit": 60, "window_seconds": 60},
        "oauth_init": {"limit": 5, "window_seconds": 60},
    }
    
    def __init__(self):
        """Initialize rate limiter with configuration from environment variables"""
        # Allow environment-based override of rate limits
        self.config = self._load_config()
        
        # Redis key pattern
        self.key_pattern = "obot_ratelimit:{user_id}:{operation}"
        
        # Cleanup configuration
        self.cleanup_enabled = True
        self.cleanup_probability = 0.1  # 10% chance of cleanup on each check
        
        logger.info(f"Initialized ObotRateLimiter with config: {self.config}")
    
    def _load_config(self) -> Dict[str, Dict[str, int]]:
        """Load rate limit configuration from environment variables"""
        config = {}
        
        # Load from environment with fallbacks to defaults
        catalog_limit = int(os.getenv("OBOT_RATE_LIMIT_CATALOG", "100"))
        catalog_window = int(os.getenv("OBOT_RATE_LIMIT_CATALOG_WINDOW", "60"))
        
        server_ops_limit = int(os.getenv("OBOT_RATE_LIMIT_SERVER_OPS", "10"))
        server_ops_window = int(os.getenv("OBOT_RATE_LIMIT_SERVER_OPS_WINDOW", "60"))
        
        tool_calls_limit = int(os.getenv("OBOT_RATE_LIMIT_TOOL_CALLS", "60"))
        tool_calls_window = int(os.getenv("OBOT_RATE_LIMIT_TOOL_CALLS_WINDOW", "60"))
        
        oauth_init_limit = int(os.getenv("OBOT_RATE_LIMIT_OAUTH_INIT", "5"))
        oauth_init_window = int(os.getenv("OBOT_RATE_LIMIT_OAUTH_INIT_WINDOW", "60"))
        
        config = {
            "catalog": {"limit": catalog_limit, "window_seconds": catalog_window},
            "server_ops": {"limit": server_ops_limit, "window_seconds": server_ops_window},
            "tool_calls": {"limit": tool_calls_limit, "window_seconds": tool_calls_window},
            "oauth_init": {"limit": oauth_init_limit, "window_seconds": oauth_init_window},
        }
        
        logger.debug(f"Loaded rate limit config from environment: {config}")
        return config
    
    def _get_operation_key(self, user_id: str, operation: str) -> str:
        """Generate Redis key for user operation combination"""
        return self.key_pattern.format(user_id=user_id, operation=operation)
    
    async def check_rate_limit(
        self,
        user_id: str,
        operation: str,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None
    ) -> bool:
        """
        Check if user is within rate limit for the operation.
        
        Args:
            user_id: User identifier
            operation: Operation type (catalog, server_ops, tool_calls, oauth_init)
            limit: Override rate limit (optional)
            window_seconds: Override window in seconds (optional)
            
        Returns:
            bool: True if request is allowed, False if rate limited
            
        Raises:
            ObotRateLimitError: If rate limit is exceeded
        """
        if operation not in self.config:
            raise ValueError(f"Unknown operation: {operation}. Valid operations: {list(self.config.keys())}")
        
        # Get configuration
        config = self.config[operation]
        rate_limit = limit or config["limit"]
        window = window_seconds or config["window_seconds"]
        
        redis_client = await get_client()
        key = self._get_operation_key(user_id, operation)
        current_time = time.time()
        cutoff_time = current_time - window
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = redis_client.pipeline()
            
            # Remove expired entries (older than window)
            pipe.zremrangebyscore(key, 0, cutoff_time)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration for the key (window + buffer)
            pipe.expire(key, window + 300)  # 5 minute buffer
            
            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]  # Result of zcard
            
            # Check if limit exceeded
            if current_count >= rate_limit:
                # Calculate retry_after seconds
                # Get the oldest timestamp in the current window
                oldest_timestamps = await redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_timestamps:
                    oldest_timestamp = oldest_timestamps[0][1]
                    retry_after = int(oldest_timestamp + window - current_time) + 1
                else:
                    retry_after = window
                
                logger.warning(
                    f"Rate limit exceeded for user {user_id} on {operation}: "
                    f"{current_count}/{rate_limit} requests in {window}s. "
                    f"Retry after {retry_after} seconds."
                )
                
                raise ObotRateLimitError(
                    operation=operation,
                    user_id=user_id,
                    retry_after=retry_after,
                    limit=rate_limit,
                    window_seconds=window
                )
            
            # Log successful request (sampled to avoid log spam)
            if current_count % 10 == 0:  # Log every 10th request
                logger.debug(
                    f"Rate limit check passed for user {user_id} on {operation}: "
                    f"{current_count + 1}/{rate_limit} requests in {window}s"
                )
            
            return True
            
        except Exception as e:
            if isinstance(e, ObotRateLimitError):
                raise
            logger.error(f"Error checking rate limit for user {user_id} on {operation}: {e}")
            # On Redis errors, allow the request to proceed (fail open)
            return True
    
    async def get_rate_limit_status(
        self,
        user_id: str,
        operation: str
    ) -> Dict[str, Any]:
        """
        Get current rate limit status for user operation.
        
        Args:
            user_id: User identifier
            operation: Operation type
            
        Returns:
            dict: Status information including current count, remaining, reset time
        """
        if operation not in self.config:
            raise ValueError(f"Unknown operation: {operation}. Valid operations: {list(self.config.keys())}")
        
        config = self.config[operation]
        rate_limit = config["limit"]
        window = config["window_seconds"]
        
        redis_client = await get_client()
        key = self._get_operation_key(user_id, operation)
        current_time = time.time()
        cutoff_time = current_time - window
        
        try:
            # Remove expired entries
            await redis_client.zremrangebyscore(key, 0, cutoff_time)
            
            # Get current count
            current_count = await redis_client.zcard(key)
            
            # Get oldest timestamp for reset time calculation
            oldest_timestamps = await redis_client.zrange(key, 0, 0, withscores=True)
            if oldest_timestamps:
                oldest_timestamp = oldest_timestamps[0][1]
                reset_time = int(oldest_timestamp + window)
            else:
                reset_time = int(current_time)
            
            remaining = max(0, rate_limit - current_count)
            reset_in = max(0, reset_time - int(current_time))
            
            status = {
                "operation": operation,
                "user_id": user_id,
                "limit": rate_limit,
                "window_seconds": window,
                "current_count": current_count,
                "remaining": remaining,
                "reset_time": reset_time,
                "reset_in_seconds": reset_in,
                "rate_limited": current_count >= rate_limit
            }
            
            logger.debug(f"Rate limit status for {user_id} on {operation}: {status}")
            return status
            
        except Exception as e:
            logger.error(f"Error getting rate limit status for user {user_id} on {operation}: {e}")
            return {
                "operation": operation,
                "user_id": user_id,
                "error": str(e),
                "current_count": 0,
                "remaining": rate_limit,
                "rate_limited": False
            }
    
    async def clear_user_limits(self, user_id: str) -> None:
        """
        Clear all rate limit entries for a user.
        
        Args:
            user_id: User identifier
        """
        redis_client = await get_client()
        pattern = self._get_operation_key(user_id, "*")
        
        try:
            # Find all keys matching the pattern
            keys = await redis_client.keys(pattern)
            
            if keys:
                deleted_count = await redis_client.delete(*keys)
                logger.info(f"Cleared {deleted_count} rate limit entries for user {user_id}")
            else:
                logger.debug(f"No rate limit entries found for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error clearing rate limits for user {user_id}: {e}")
            raise
    
    async def cleanup_expired_entries(self) -> None:
        """Clean up expired rate limit entries from Redis"""
        redis_client = await get_client()
        
        try:
            # Find all rate limit keys
            pattern = self.key_pattern.format(user_id="*", operation="*")
            keys = await redis_client.keys(pattern)
            
            if not keys:
                return
            
            current_time = time.time()
            cleaned_count = 0
            
            # Use pipeline for batch operations
            pipe = redis_client.pipeline()
            
            for key in keys:
                # Remove expired entries
                pipe.zremrangebyscore(key, 0, current_time)
                # Get count after cleanup
                pipe.zcard(key)
            
            results = await pipe.execute()
            
            # Count cleaned entries (results are in pairs: cleaned_count, remaining_count)
            for i in range(0, len(results), 2):
                cleaned = results[i]
                remaining = results[i + 1]
                cleaned_count += cleaned
                
                # Remove keys with no remaining entries
                if remaining == 0:
                    pipe.delete(keys[i // 2])
            
            await pipe.execute()
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired rate limit entries")
            
        except Exception as e:
            logger.error(f"Error during rate limit cleanup: {e}")
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Check health of the rate limiter service.
        
        Returns:
            dict: Health status information
        """
        health_status = {
            "service": "obot_rate_limiter",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "redis_connected": False,
            "active_keys": 0,
            "config": self.config
        }
        
        try:
            redis_client = await get_client()
            
            # Test Redis connection
            await redis_client.ping()
            health_status["redis_connected"] = True
            
            # Count active rate limit keys
            pattern = self.key_pattern.format(user_id="*", operation="*")
            keys = await redis_client.keys(pattern)
            health_status["active_keys"] = len(keys)
            
            # Random cleanup check (probabilistic to avoid overhead)
            if self.cleanup_enabled and len(keys) > 0:
                import random
                if random.random() < self.cleanup_probability:
                    await self.cleanup_expired_entries()
            
            logger.debug(f"Rate limiter health check passed: {health_status}")
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
            logger.error(f"Rate limiter health check failed: {e}")
        
        return health_status
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about rate limiter usage.
        
        Returns:
            dict: Statistics including total keys and per-operation stats
        """
        redis_client = await get_client()
        
        try:
            # Get all rate limit keys
            pattern = self.key_pattern.format(user_id="*", operation="*")
            keys = await redis_client.keys(pattern)
            
            stats = {
                "total_keys": len(keys),
                "operations": {},
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Group keys by operation
            operation_counts = {}
            for key in keys:
                # Extract operation from key
                parts = key.split(":")
                if len(parts) >= 4:
                    operation = parts[3]
                    operation_counts[operation] = operation_counts.get(operation, 0) + 1
            
            stats["operations"] = operation_counts
            
            # Get detailed stats for each operation
            for operation in self.config.keys():
                op_pattern = self.key_pattern.format(user_id="*", operation=operation)
                op_keys = await redis_client.keys(op_pattern)
                
                if op_keys:
                    pipe = redis_client.pipeline()
                    for key in op_keys:
                        pipe.zcard(key)
                    
                    results = await pipe.execute()
                    total_requests = sum(results)
                    active_keys = len([r for r in results if r > 0])
                    
                    stats["operations"][operation] = {
                        "active_keys": active_keys,
                        "total_keys": len(op_keys),
                        "total_requests": total_requests,
                        "limit": self.config[operation]["limit"],
                        "window_seconds": self.config[operation]["window_seconds"]
                    }
                else:
                    stats["operations"][operation] = {
                        "active_keys": 0,
                        "total_keys": 0,
                        "total_requests": 0,
                        "limit": self.config[operation]["limit"],
                        "window_seconds": self.config[operation]["window_seconds"]
                    }
            
            logger.debug(f"Rate limiter stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error getting rate limiter stats: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global rate limiter instance
_rate_limiter: Optional[ObotRateLimiter] = None


async def get_rate_limiter() -> ObotRateLimiter:
    """Get global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = ObotRateLimiter()
    return _rate_limiter


# Convenience functions for common operations
async def check_catalog_rate_limit(user_id: str) -> bool:
    """Check rate limit for catalog queries"""
    limiter = await get_rate_limiter()
    return await limiter.check_rate_limit(user_id, "catalog")


async def check_server_ops_rate_limit(user_id: str) -> bool:
    """Check rate limit for server operations (create/delete)"""
    limiter = await get_rate_limiter()
    return await limiter.check_rate_limit(user_id, "server_ops")


async def check_tool_calls_rate_limit(user_id: str) -> bool:
    """Check rate limit for tool calls"""
    limiter = await get_rate_limiter()
    return await limiter.check_rate_limit(user_id, "tool_calls")


async def check_oauth_init_rate_limit(user_id: str) -> bool:
    """Check rate limit for OAuth initiations"""
    limiter = await get_rate_limiter()
    return await limiter.check_rate_limit(user_id, "oauth_init")


async def get_user_rate_limit_status(user_id: str) -> Dict[str, Any]:
    """Get rate limit status for all operations for a user"""
    limiter = await get_rate_limiter()
    
    status = {}
    for operation in limiter.config.keys():
        status[operation] = await limiter.get_rate_limit_status(user_id, operation)
    
    return status


async def clear_user_rate_limits(user_id: str) -> None:
    """Clear all rate limits for a user"""
    limiter = await get_rate_limiter()
    await limiter.clear_user_limits(user_id)


async def check_rate_limiter_health() -> Dict[str, Any]:
    """Check health of the rate limiter service"""
    limiter = await get_rate_limiter()
    return await limiter.check_health()


async def get_rate_limiter_stats() -> Dict[str, Any]:
    """Get statistics about rate limiter usage"""
    limiter = await get_rate_limiter()
    return await limiter.get_stats()
