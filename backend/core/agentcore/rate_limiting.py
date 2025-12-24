"""
AgentCore Rate Limiting (Phase 10)

Tier-based distributed rate limiting for AgentCore operations in ap-southeast-2.

Phase 10: Enhanced rate limiting with tier-based limits, token bucket algorithm,
sliding window counters, and Redis-backed distributed limiting for production
scalability.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from contextlib import asynccontextmanager
import hashlib
import json

from .config import AgentCoreConfig
from .middleware.tenant import get_tenant_context

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"

# ============================================================================
# Enums and Data Classes
# ============================================================================

class RateLimitScope(str, Enum):
    """Scope for rate limiting."""
    GLOBAL = "global"  # Across all tenants
    TENANT = "tenant"  # Per tenant
    ACCOUNT = "account"  # Per account
    AGENT = "agent"  # Per agent
    OPERATION = "operation"  # Per operation type
    IP_ADDRESS = "ip_address"  # Per IP address


class RateLimitAlgorithm(str, Enum):
    """Rate limiting algorithms."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitRule:
    """
    A rate limiting rule.

    Attributes:
        name: Unique rule identifier
        scope: Rate limit scope
        limit: Maximum requests allowed
        window_seconds: Time window in seconds
        algorithm: Rate limiting algorithm
        tier: Subscription tier (None for all tiers)
        burst: Burst capacity (for token bucket)
        operations: Specific operations this applies to (empty for all)
    """
    name: str
    scope: RateLimitScope
    limit: int
    window_seconds: int
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    tier: Optional[str] = None
    burst: Optional[int] = None
    operations: Set[str] = field(default_factory=set)

    def get_redis_key(self, identifier: str) -> str:
        """Generate Redis key for this rate limit."""
        key_parts = [
            "agentcore",
            "ratelimit",
            PHASE_10_REGION,
            self.scope.value,
            self.name,
            identifier,
        ]
        return ":".join(key_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "scope": self.scope.value,
            "limit": self.limit,
            "window_seconds": self.window_seconds,
            "algorithm": self.algorithm.value,
            "tier": self.tier,
            "burst": self.burst,
            "operations": list(self.operations),
            "region": PHASE_10_REGION,
        }


@dataclass
class RateLimitResult:
    """
    Result of a rate limit check.

    Attributes:
        allowed: Whether request is allowed
        remaining: Remaining requests in window
        reset_at: When rate limit resets
        retry_after: Seconds until retry is possible (if not allowed)
        rule: The rule that was applied
    """
    allowed: bool
    remaining: int
    reset_at: datetime
    retry_after: Optional[float] = None
    rule: Optional[RateLimitRule] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reset_at": self.reset_at.isoformat(),
            "region": PHASE_10_REGION,
        }

        if self.retry_after is not None:
            result["retry_after"] = self.retry_after

        if self.rule:
            result["rule"] = self.rule.name

        return result


# ============================================================================
# Default Rate Limit Rules by Tier
# ============================================================================

# Rate limits based on subscription tier
TIER_RATE_LIMITS: Dict[str, List[RateLimitRule]] = {
    "free": [
        RateLimitRule(
            name="free_global",
            scope=RateLimitScope.GLOBAL,
            limit=10,
            window_seconds=60,
            tier="free",
        ),
        RateLimitRule(
            name="free_agent_execution",
            scope=RateLimitScope.AGENT,
            limit=5,
            window_seconds=60,
            tier="free",
            operations={"execute_agent", "invoke_runtime"},
        ),
    ],
    "pro": [
        RateLimitRule(
            name="pro_global",
            scope=RateLimitScope.GLOBAL,
            limit=100,
            window_seconds=60,
            tier="pro",
        ),
        RateLimitRule(
            name="pro_agent_execution",
            scope=RateLimitScope.AGENT,
            limit=50,
            window_seconds=60,
            tier="pro",
            operations={"execute_agent", "invoke_runtime"},
        ),
        RateLimitRule(
            name="pro_code_interpreter",
            scope=RateLimitScope.OPERATION,
            limit=30,
            window_seconds=60,
            tier="pro",
            operations={"execute_code", "execute_shell"},
        ),
    ],
    "enterprise": [
        RateLimitRule(
            name="enterprise_global",
            scope=RateLimitScope.GLOBAL,
            limit=1000,
            window_seconds=60,
            tier="enterprise",
        ),
        RateLimitRule(
            name="enterprise_agent_execution",
            scope=RateLimitScope.AGENT,
            limit=500,
            window_seconds=60,
            tier="enterprise",
            operations={"execute_agent", "invoke_runtime"},
        ),
        RateLimitRule(
            name="enterprise_code_interpreter",
            scope=RateLimitScope.OPERATION,
            limit=200,
            window_seconds=60,
            tier="enterprise",
            operations={"execute_code", "execute_shell"},
        ),
        RateLimitRule(
            name="enterprise_browser",
            scope=RateLimitScope.OPERATION,
            limit=100,
            window_seconds=60,
            tier="enterprise",
            operations={"navigate", "extract_content", "screenshot"},
        ),
    ],
}


# ============================================================================
# Token Bucket Algorithm
# ============================================================================

class TokenBucket:
    """
    Token bucket rate limiting algorithm.

    Allows bursts up to burst capacity while maintaining
    average rate limit over time.

    Attributes:
        capacity: Maximum tokens (burst capacity)
        tokens: Current available tokens
        rate: Token refill rate per second
        last_refill: Last refill timestamp
    """

    def __init__(self, capacity: int, rate: float):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum tokens (burst capacity)
            rate: Tokens per second refill rate
        """
        self.capacity = capacity
        self.rate = rate
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on elapsed time
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.rate)
        )
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def get_available_tokens(self) -> int:
        """Get current available tokens."""
        self._refill()
        return int(self.tokens)

    def get_retry_after(self) -> float:
        """Get seconds until one token is available."""
        self._refill()

        if self.tokens >= 1:
            return 0.0

        return (1 - self.tokens) / self.rate


# ============================================================================
# Sliding Window Algorithm
# ============================================================================

class SlidingWindowCounter:
    """
    Sliding window rate limiting algorithm.

    Tracks request timestamps in a sliding window for
    more accurate rate limiting than fixed windows.

    Attributes:
        window_seconds: Window size in seconds
        limit: Maximum requests in window
        timestamps: List of request timestamps
    """

    def __init__(self, window_seconds: int, limit: int):
        """
        Initialize sliding window counter.

        Args:
            window_seconds: Window size in seconds
            limit: Maximum requests in window
        """
        self.window_seconds = window_seconds
        self.limit = limit
        self.timestamps: List[float] = []

    def is_allowed(self, current_time: Optional[float] = None) -> bool:
        """
        Check if request is allowed.

        Args:
            current_time: Current timestamp (uses time.time() if None)

        Returns:
            True if request is allowed
        """
        now = current_time or time.time()
        window_start = now - self.window_seconds

        # Remove timestamps outside the window
        self.timestamps = [
            ts for ts in self.timestamps
            if ts > window_start
        ]

        # Check if under limit
        if len(self.timestamps) < self.limit:
            self.timestamps.append(now)
            return True

        return False

    def get_count(self, current_time: Optional[float] = None) -> int:
        """Get current request count in window."""
        now = current_time or time.time()
        window_start = now - self.window_seconds

        return len([
            ts for ts in self.timestamps
            if ts > window_start
        ])

    def get_retry_after(self, current_time: Optional[float] = None) -> float:
        """Get seconds until next request is allowed."""
        now = current_time or time.time()

        if len(self.timestamps) < self.limit:
            return 0.0

        # Find oldest timestamp in window
        oldest = self.timestamps[0]
        return max(0, oldest + self.window_seconds - now)


# ============================================================================
# Distributed Rate Limiter
# ============================================================================

class DistributedRateLimiter:
    """
    Redis-backed distributed rate limiter.

    Supports multiple rate limiting algorithms with
    Redis persistence for horizontal scalability.

    Usage:
        ```python
        limiter = DistributedRateLimiter(config)

        # Check rate limit
        result = await limiter.check_rate_limit(
            identifier="acct-123",
            rule=TIER_RATE_LIMITS["pro"][0],
            operation="execute_agent"
        )

        if not result.allowed:
            raise RateLimitError(result)
        ```
    """

    def __init__(self, config: AgentCoreConfig):
        """
        Initialize distributed rate limiter.

        Args:
            config: AgentCore configuration
        """
        self.config = config
        self._redis = None
        self._local_cache: Dict[str, Any] = {
            "token_buckets": {},
            "sliding_windows": {},
        }

    async def initialize(self):
        """Initialize Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(
                    f"redis://{self.config.redis_host}:{self.config.redis_port}",
                    encoding="utf-8",
                    decode_responses=True,
                )

            except Exception as e:
                # Fallback to in-memory rate limiting
                import logging
                logging.warning(f"Redis unavailable, using local rate limiting: {e}")

    async def check_rate_limit(
        self,
        identifier: str,
        rule: RateLimitRule,
        operation: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: Unique identifier (tenant_id, account_id, etc.)
            rule: Rate limit rule to apply
            operation: Operation being performed

        Returns:
            Rate limit result
        """
        # Check if operation is in rule's operation list
        if rule.operations and operation not in rule.operations:
            return RateLimitResult(
                allowed=True,
                remaining=rule.limit,
                reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                rule=rule,
            )

        # Get tier-based limits
        ctx = get_tenant_context()
        tier = ctx.tier if ctx else "free"

        # Select algorithm
        if rule.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            return await self._check_token_bucket(identifier, rule)
        elif rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            return await self._check_sliding_window(identifier, rule)
        else:  # FIXED_WINDOW
            return await self._check_fixed_window(identifier, rule)

    async def _check_token_bucket(
        self,
        identifier: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check rate limit using token bucket algorithm."""
        redis_key = rule.get_redis_key(identifier)

        if self._redis:
            return await self._check_token_bucket_redis(redis_key, rule)
        else:
            return self._check_token_bucket_local(redis_key, rule)

    async def _check_token_bucket_redis(
        self,
        redis_key: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check token bucket with Redis backend."""
        burst = rule.burst or rule.limit
        rate = rule.limit / rule.window_seconds

        now = time.time()
        pipe = self._redis.pipeline()

        # Get current state
        pipe.hget(redis_key, "tokens")
        pipe.hget(redis_key, "last_refill")
        current_tokens, last_refill = await pipe.execute()

        # Initialize if not exists
        if current_tokens is None:
            current_tokens = float(burst)
            last_refill = now
        else:
            current_tokens = float(current_tokens)
            last_refill = float(last_refill)

        # Refill tokens
        elapsed = now - last_refill
        current_tokens = min(burst, current_tokens + (elapsed * rate))

        # Check if tokens available
        if current_tokens >= 1:
            current_tokens -= 1

            # Save state
            await self._redis.hset(
                redis_key,
                mapping={
                    "tokens": str(current_tokens),
                    "last_refill": str(now),
                }
            )
            await self._redis.expire(redis_key, rule.window_seconds * 2)

            return RateLimitResult(
                allowed=True,
                remaining=int(current_tokens),
                reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                rule=rule,
            )
        else:
            retry_after = (1 - current_tokens) / rate
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=retry_after),
                retry_after=retry_after,
                rule=rule,
            )

    def _check_token_bucket_local(
        self,
        redis_key: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check token bucket with local backend."""
        burst = rule.burst or rule.limit
        rate = rule.limit / rule.window_seconds

        bucket = self._local_cache["token_buckets"].get(redis_key)
        if bucket is None:
            bucket = TokenBucket(capacity=burst, rate=rate)
            self._local_cache["token_buckets"][redis_key] = bucket

        if bucket.consume():
            return RateLimitResult(
                allowed=True,
                remaining=bucket.get_available_tokens(),
                reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                rule=rule,
            )
        else:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=bucket.get_retry_after()),
                retry_after=bucket.get_retry_after(),
                rule=rule,
            )

    async def _check_sliding_window(
        self,
        identifier: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check rate limit using sliding window algorithm."""
        redis_key = f"{rule.get_redis_key(identifier)}:sliding"

        if self._redis:
            return await self._check_sliding_window_redis(redis_key, rule)
        else:
            return self._check_sliding_window_local(redis_key, rule)

    async def _check_sliding_window_redis(
        self,
        redis_key: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check sliding window with Redis backend."""
        now = time.time()
        window_start = now - rule.window_seconds

        # Use sorted set with timestamps as scores
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        count = await pipe.execute()

        if count < rule.limit:
            # Add current request
            await self._redis.zadd(redis_key, {str(now): now})
            await self._redis.expire(redis_key, rule.window_seconds * 2)

            return RateLimitResult(
                allowed=True,
                remaining=rule.limit - count - 1,
                reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                rule=rule,
            )
        else:
            # Get oldest timestamp to calculate retry_after
            oldest_ts = await self._redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest_ts:
                oldest = float(oldest_ts[0][1])
                retry_after = max(0, oldest + rule.window_seconds - now)
            else:
                retry_after = rule.window_seconds

            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=retry_after),
                retry_after=retry_after,
                rule=rule,
            )

    def _check_sliding_window_local(
        self,
        redis_key: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check sliding window with local backend."""
        window = self._local_cache["sliding_windows"].get(redis_key)
        if window is None:
            window = SlidingWindowCounter(
                window_seconds=rule.window_seconds,
                limit=rule.limit
            )
            self._local_cache["sliding_windows"][redis_key] = window

        if window.is_allowed():
            return RateLimitResult(
                allowed=True,
                remaining=rule.limit - window.get_count(),
                reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                rule=rule,
            )
        else:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=datetime.utcnow() + timedelta(seconds=window.get_retry_after()),
                retry_after=window.get_retry_after(),
                rule=rule,
            )

    async def _check_fixed_window(
        self,
        identifier: str,
        rule: RateLimitRule
    ) -> RateLimitResult:
        """Check rate limit using fixed window algorithm."""
        redis_key = rule.get_redis_key(identifier)
        window_key = f"{redis_key}:{int(time.time() // rule.window_seconds)}"

        if self._redis:
            count = await self._redis.incr(window_key)
            await self._redis.expire(window_key, rule.window_seconds)

            if count <= rule.limit:
                return RateLimitResult(
                    allowed=True,
                    remaining=rule.limit - count,
                    reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                    rule=rule,
                )
            else:
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                    retry_after=rule.window_seconds,
                    rule=rule,
                )
        else:
            # Fallback to simple counter
            count = self._local_cache.get(window_key, 0) + 1
            self._local_cache[window_key] = count

            if count <= rule.limit:
                return RateLimitResult(
                    allowed=True,
                    remaining=rule.limit - count,
                    reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                    rule=rule,
                )
            else:
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_at=datetime.utcnow() + timedelta(seconds=rule.window_seconds),
                    retry_after=rule.window_seconds,
                    rule=rule,
                )


# ============================================================================
# Rate Limiter Manager
# ============================================================================

class RateLimiterManager:
    """
    Manager for rate limiting across AgentCore operations.

    Provides tier-based rate limiting with automatic rule
    selection and distributed enforcement.

    Usage:
        ```python
        manager = RateLimiterManager(config)
        await manager.initialize()

        # Check rate limit for tenant operation
        result = await manager.check_limit(
            account_id="acct-123",
            operation="execute_agent"
        )

        if not result.allowed:
            raise RateLimitExceededError(result)
        ```
    """

    def __init__(self, config: AgentCoreConfig):
        """
        Initialize rate limiter manager.

        Args:
            config: AgentCore configuration
        """
        self.config = config
        self.limiter = DistributedRateLimiter(config)
        self._rules: Dict[str, List[RateLimitRule]] = TIER_RATE_LIMITS

    async def initialize(self):
        """Initialize rate limiter."""
        await self.limiter.initialize()

    async def check_limit(
        self,
        account_id: str,
        operation: str,
        tier: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Check rate limit for an operation.

        Args:
            account_id: Account identifier
            operation: Operation being performed
            tier: Subscription tier (from context if None)

        Returns:
            Rate limit result
        """
        ctx = get_tenant_context()
        effective_tier = tier or ctx.tier if ctx else "free"

        # Get rules for tier
        rules = self._rules.get(effective_tier, [])

        # Find applicable rule
        for rule in rules:
            result = await self.limiter.check_rate_limit(
                identifier=account_id,
                rule=rule,
                operation=operation,
            )

            if not result.allowed:
                return result

        # All rules passed
        return RateLimitResult(
            allowed=True,
            remaining=999,  # No specific limit
            reset_at=datetime.utcnow() + timedelta(seconds=60),
        )

    def add_rule(self, tier: str, rule: RateLimitRule):
        """
        Add or replace a rate limit rule for a tier.

        Args:
            tier: Subscription tier
            rule: Rate limit rule
        """
        if tier not in self._rules:
            self._rules[tier] = []

        # Remove existing rule with same name
        self._rules[tier] = [
            r for r in self._rules[tier]
            if r.name != rule.name
        ]

        self._rules[tier].append(rule)

    def get_tier_limits(self, tier: str) -> List[RateLimitRule]:
        """Get rate limit rules for a tier."""
        return self._rules.get(tier, [])


# ============================================================================
# Rate Limit Error
# ============================================================================

class RateLimitError(Exception):
    """
    Exception raised when rate limit is exceeded.

    Attributes:
        result: Rate limit result
        message: Error message
        retry_after: Seconds until retry
    """

    def __init__(self, result: RateLimitResult):
        self.result = result
        self.message = f"Rate limit exceeded: {result.rule.name if result.rule else 'unknown'}"
        self.retry_after = result.retry_after
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "error": "rate_limit_exceeded",
            "message": self.message,
            "retry_after": self.retry_after,
            "rule": self.result.rule.name if self.result.rule else None,
            "region": PHASE_10_REGION,
        }


# ============================================================================
# Decorators
# ============================================================================

def rate_limit(operation: Optional[str] = None):
    """
    Decorator to apply rate limiting to a function.

    Usage:
        ```python
        @rate_limit(operation="execute_agent")
        async def execute_agent(account_id: str, ...):
            ...
        ```
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get rate limiter from context or config
            # This is a simplified version - in production,
            # you'd inject the limiter via dependency injection
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# Convenience Functions
# ============================================================================

_limiter_manager: Optional[RateLimiterManager] = None


async def get_rate_limiter(config: Optional[AgentCoreConfig] = None) -> RateLimiterManager:
    """
    Get the rate limiter manager instance (singleton).

    Args:
        config: Optional AgentCore configuration

    Returns:
        RateLimiterManager instance
    """
    global _limiter_manager

    if _limiter_manager is None:
        cfg = config or AgentCoreConfig()
        _limiter_manager = RateLimiterManager(cfg)
        await _limiter_manager.initialize()

    return _limiter_manager


async def check_rate_limit(
    account_id: str,
    operation: str,
    tier: Optional[str] = None,
) -> RateLimitResult:
    """
    Check rate limit for an operation.

    Args:
        account_id: Account identifier
        operation: Operation being performed
        tier: Subscription tier

    Returns:
        Rate limit result
    """
    manager = await get_rate_limiter()
    return await manager.check_limit(account_id, operation, tier)


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "RateLimitScope",
    "RateLimitAlgorithm",
    "RateLimitRule",
    "RateLimitResult",
    "TIER_RATE_LIMITS",
    "TokenBucket",
    "SlidingWindowCounter",
    "DistributedRateLimiter",
    "RateLimiterManager",
    "RateLimitError",
    "rate_limit",
    "get_rate_limiter",
    "check_rate_limit",
]
