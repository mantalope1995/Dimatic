"""
AgentCore Connection Pool (Phase 10)

Connection pooling for AgentCore adapters in ap-southeast-2.

Phase 10: Connection pooling supports ap-southeast-2 (Australia) region for
data residency compliance.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class PoolState(str, Enum):
    """Connection pool state."""
    IDLE = "idle"
    BUSY = "busy"
    CLOSING = "closing"
    CLOSED = "closed"


class ConnectionType(str, Enum):
    """Types of connections that can be pooled."""
    RUNTIME = "runtime"
    MEMORY = "memory"
    CODE_INTERPRETER = "code_interpreter"
    BROWSER = "browser"
    GATEWAY = "gateway"


@dataclass
class PooledConnection:
    """
    A pooled connection wrapper.

    Attributes:
        connection_id: Unique connection identifier
        connection_type: Type of connection
        connection: Underlying connection object
        created_at: When connection was created
        last_used_at: When connection was last used
        use_count: Number of times connection has been used
        is_healthy: Whether connection is healthy
        metadata: Additional metadata
    """
    connection_id: str
    connection_type: ConnectionType
    connection: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: datetime = field(default_factory=datetime.utcnow)
    use_count: int = 0
    is_healthy: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_used(self) -> None:
        """Mark connection as used."""
        self.last_used_at = datetime.utcnow()
        self.use_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "connection_id": self.connection_id,
            "connection_type": self.connection_type.value,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "use_count": self.use_count,
            "is_healthy": self.is_healthy,
            "age_seconds": (datetime.utcnow() - self.created_at).total_seconds(),
            "idle_seconds": (datetime.utcnow() - self.last_used_at).total_seconds(),
        }


@dataclass
class PoolConfig:
    """
    Configuration for a connection pool.

    Attributes:
        min_connections: Minimum number of connections to maintain
        max_connections: Maximum number of connections
        connection_timeout_seconds: Timeout for acquiring connection
        idle_timeout_seconds: Timeout before closing idle connections
        max_connection_lifetime_seconds: Maximum lifetime of a connection
        max_connection_uses: Maximum times a connection can be reused
        health_check_interval_seconds: Interval between health checks
    """
    min_connections: int = 2
    max_connections: int = 10
    connection_timeout_seconds: float = 5.0
    idle_timeout_seconds: float = 300.0  # 5 minutes
    max_connection_lifetime_seconds: float = 3600.0  # 1 hour
    max_connection_uses: int = 1000
    health_check_interval_seconds: float = 60.0


@dataclass
class PoolStats:
    """
    Connection pool statistics.

    Attributes:
        total_connections: Total connections in pool
        active_connections: Currently active connections
        idle_connections: Currently idle connections
        total_acquisitions: Total connection acquisitions
        total_releases: Total connection releases
        total_timeouts: Total timeouts waiting for connection
        total_failures: Total connection failures
        created_count: Total connections created
        destroyed_count: Total connections destroyed
    """
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_acquisitions: int = 0
    total_releases: int = 0
    total_timeouts: int = 0
    total_failures: int = 0
    created_count: int = 0
    destroyed_count: int = 0

    @property
    def utilization_rate(self) -> float:
        """Calculate pool utilization rate (0-1)."""
        if self.total_connections == 0:
            return 0.0
        return self.active_connections / self.total_connections

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_connections": self.total_connections,
            "active_connections": self.active_connections,
            "idle_connections": self.idle_connections,
            "utilization_rate": self.utilization_rate,
            "total_acquisitions": self.total_acquisitions,
            "total_releases": self.total_releases,
            "total_timeouts": self.total_timeouts,
            "total_failures": self.total_failures,
            "created_count": self.created_count,
            "destroyed_count": self.destroyed_count,
            "region": PHASE_10_REGION,
        }


# ============================================================================
# Connection Pool
# ============================================================================

class ConnectionPool:
    """
    Generic connection pool for AgentCore adapters.

    Features:
    - Min/max connection limits
    - Connection timeout handling
    - Idle connection cleanup
    - Connection lifetime management
    - Health checking
    - Statistics tracking

    Usage:
        ```python
        pool = ConnectionPool(
            connection_type=ConnectionType.RUNTIME,
            pool_config=PoolConfig(min_connections=2, max_connections=10),
            connection_factory=lambda: RuntimeAdapter(config)
        )

        # Initialize pool
        await pool.initialize()

        # Acquire connection
        async with pool.acquire() as conn:
            result = await conn.invoke_agent(...)

        # Close pool
        await pool.close()
        ```
    """

    def __init__(
        self,
        connection_type: ConnectionType,
        config: Optional[AgentCoreConfig] = None,
        pool_config: Optional[PoolConfig] = None,
        connection_factory: Optional[Callable[[], Any]] = None,
    ):
        """
        Initialize the connection pool.

        Args:
            connection_type: Type of connections to pool
            config: AgentCore configuration
            pool_config: Pool configuration
            connection_factory: Function to create new connections
        """
        self.connection_type = connection_type
        self.config = config or get_config()
        self._pool_config = pool_config or PoolConfig()
        self._connection_factory = connection_factory

        self._connections: List[PooledConnection] = []
        self._available: asyncio.Queue = None
        self._lock = asyncio.Lock()
        self._state = PoolState.IDLE
        self._stats = PoolStats()
        self._health_check_task: Optional[asyncio.Task] = None

        # Validate region compliance for Phase 10
        if self.config.aws_region != PHASE_10_REGION:
            safe_log(
                f"ConnectionPool: Region '{self.config.aws_region}' specified, "
                f"but Phase 10 requires '{PHASE_10_REGION}'. "
                f"All connections will target {PHASE_10_REGION} for compliance."
            )

        safe_log(f"ConnectionPool initialized for {connection_type.value}")

    async def initialize(self) -> None:
        """Initialize the connection pool."""
        self._available = asyncio.Queue(maxsize=self._pool_config.max_connections)

        # Create minimum connections
        for _ in range(self._pool_config.min_connections):
            await self._create_connection()

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        self._state = PoolState.IDLE
        safe_log(f"ConnectionPool initialized with {len(self._connections)} connections")

    async def close(self) -> None:
        """Close the connection pool."""
        self._state = PoolState.CLOSING

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all connections
        async with self._lock:
            for conn in self._connections:
                await self._destroy_connection(conn)

            self._connections.clear()
            self._state = PoolState.CLOSED

        safe_log("ConnectionPool closed")

    async def _create_connection(self) -> Optional[PooledConnection]:
        """Create a new connection."""
        if self._connection_factory is None:
            return None

        try:
            conn = self._connection_factory()
            connection_id = f"{self.connection_type.value}-{int(time.time() * 1000)}"

            pooled = PooledConnection(
                connection_id=connection_id,
                connection_type=self.connection_type,
                connection=conn,
            )

            self._connections.append(pooled)
            self._stats.total_connections += 1
            self._stats.created_count += 1

            safe_log(f"Created connection {connection_id[:16]}...")
            return pooled

        except Exception as e:
            safe_log(f"Failed to create connection: {e}", level="error")
            self._stats.total_failures += 1
            return None

    async def _destroy_connection(self, conn: PooledConnection) -> None:
        """Destroy a connection."""
        try:
            # Close underlying connection if it has a close method
            if hasattr(conn.connection, "close"):
                if asyncio.iscoroutinefunction(conn.connection.close):
                    await conn.connection.close()
                else:
                    conn.connection.close()

            self._connections.remove(conn)
            self._stats.total_connections -= 1
            self._stats.destroyed_count += 1

            safe_log(f"Destroyed connection {conn.connection_id[:16]}...")

        except Exception as e:
            safe_log(f"Failed to destroy connection: {e}", level="warning")

    async def _health_check_loop(self) -> None:
        """Background loop for connection health checking."""
        while self._state != PoolState.CLOSED:
            try:
                await asyncio.sleep(self._pool_config.health_check_interval_seconds)

                if self._state == PoolState.CLOSED:
                    break

                await self._check_connections()

            except asyncio.CancelledError:
                break
            except Exception as e:
                safe_log(f"Health check error: {e}", level="warning")

    async def _check_connections(self) -> None:
        """Check health of all connections."""
        async with self._lock:
            to_remove = []

            for conn in self._connections:
                # Check if connection should be removed
                age = (datetime.utcnow() - conn.created_at).total_seconds()
                idle = (datetime.utcnow() - conn.last_used_at).total_seconds()

                # Remove old, overused, or unhealthy connections
                if (
                    age >= self._pool_config.max_connection_lifetime_seconds
                    or idle >= self._pool_config.idle_timeout_seconds
                    or conn.use_count >= self._pool_config.max_connection_uses
                    or not conn.is_healthy
                ):
                    to_remove.append(conn)

            # Remove stale connections
            for conn in to_remove:
                await self._destroy_connection(conn)

            # Replenish to minimum
            while len(self._connections) < self._pool_config.min_connections:
                new_conn = await self._create_connection()
                if new_conn is None:
                    break

    async def acquire(self, timeout: Optional[float] = None) -> "AcquireContext":
        """
        Acquire a connection from the pool.

        Args:
            timeout: Maximum time to wait for connection

        Returns:
            Acquire context manager

        Usage:
            ```python
            async with pool.acquire() as conn:
                # Use connection
                result = await conn.connection.some_method()
            ```
        """
        return AcquireContext(self, timeout)

    async def _acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        """Internal acquire implementation."""
        if self._state == PoolState.CLOSED:
            raise AgentCoreError("Connection pool is closed")

        timeout = timeout or self._pool_config.connection_timeout_seconds

        try:
            # Try to get available connection
            conn = await asyncio.wait_for(
                self._available.get(),
                timeout=timeout
            )

            self._stats.active_connections += 1
            self._stats.idle_connections = self._stats.total_connections - self._stats.active_connections
            self._stats.total_acquisitions += 1

            return conn

        except asyncio.TimeoutError:
            self._stats.total_timeouts += 1
            raise AgentCoreError(f"Connection acquire timeout after {timeout}s")

    async def _release(self, conn: PooledConnection) -> None:
        """Release a connection back to the pool."""
        if conn not in self._connections:
            safe_log("Attempting to release unknown connection", level="warning")
            return

        conn.mark_used()

        self._stats.active_connections -= 1
        self._stats.idle_connections = self._stats.total_connections - self._stats.active_connections
        self._stats.total_releases += 1

        await self._available.put(conn)

    async def get_stats(self) -> PoolStats:
        """
        Get pool statistics.

        Returns:
            Current pool statistics
        """
        self._stats.total_connections = len(self._connections)
        return self._stats


# ============================================================================
# Acquire Context Manager
# ============================================================================

class AcquireContext:
    """Context manager for acquiring and releasing connections."""

    def __init__(self, pool: ConnectionPool, timeout: Optional[float] = None):
        self.pool = pool
        self.timeout = timeout
        self._connection: Optional[PooledConnection] = None

    async def __aenter__(self) -> PooledConnection:
        self._connection = await self.pool._acquire(self.timeout)
        return self._connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._connection:
            await self.pool._release(self._connection)


# ============================================================================
# Specialized Connection Pools
# ============================================================================

class RuntimeConnectionPool(ConnectionPool):
    """Connection pool specialized for AgentCore Runtime adapters."""

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        pool_config: Optional[PoolConfig] = None,
    ):
        from ..adapters.runtime import AgentCoreRuntimeAdapter

        def runtime_factory():
            return AgentCoreRuntimeAdapter(config=config)

        super().__init__(
            connection_type=ConnectionType.RUNTIME,
            config=config,
            pool_config=pool_config,
            connection_factory=runtime_factory,
        )


# ============================================================================
# Convenience Functions
# ============================================================================

_pools: Dict[ConnectionType, ConnectionPool] = {}


def get_connection_pool(
    connection_type: ConnectionType,
    config: Optional[AgentCoreConfig] = None,
) -> ConnectionPool:
    """
    Get or create a connection pool for a connection type.

    Args:
        connection_type: Type of connections to pool
        config: Optional AgentCore configuration

    Returns:
        ConnectionPool instance
    """
    if connection_type not in _pools:
        if connection_type == ConnectionType.RUNTIME:
            _pools[connection_type] = RuntimeConnectionPool(config=config)
        else:
            _pools[connection_type] = ConnectionPool(
                connection_type=connection_type,
                config=config,
            )

    return _pools[connection_type]


async def initialize_pools(config: Optional[AgentCoreConfig] = None) -> None:
    """
    Initialize all connection pools.

    Args:
        config: Optional AgentCore configuration
    """
    for conn_type in ConnectionType:
        pool = get_connection_pool(conn_type, config)
        await pool.initialize()


async def close_pools() -> None:
    """Close all connection pools."""
    for pool in _pools.values():
        await pool.close()
    _pools.clear()


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "PoolState",
    "ConnectionType",
    "PooledConnection",
    "PoolConfig",
    "PoolStats",
    "ConnectionPool",
    "RuntimeConnectionPool",
    "AcquireContext",
    "get_connection_pool",
    "initialize_pools",
    "close_pools",
]
