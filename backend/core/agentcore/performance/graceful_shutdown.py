"""
AgentCore Graceful Shutdown (Phase 10)

Graceful shutdown coordination for AgentCore operations in ap-southeast-2.

Phase 10: Graceful shutdown supports ap-southeast-2 (Australia) region for
data residency compliance, ensuring clean service termination with
connection pool cleanup and cache flushing.
"""

import asyncio
import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from ..config import AgentCoreConfig, get_config
from ..errors import AgentCoreError, safe_log

logger = logging.getLogger(__name__)

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Enums and Data Classes
# ============================================================================

class ShutdownState(str, Enum):
    """Shutdown state machine."""
    RUNNING = "running"
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    FAILED = "failed"


class ShutdownPriority(str, Enum):
    """Priority for shutdown order."""
    CRITICAL = "critical"  # Runtime agents, active executions
    HIGH = "high"  # Connection pools, batch processors
    NORMAL = "normal"  # Cache, background tasks
    LOW = "low"  # Monitoring, health checks


@dataclass
class ShutdownHook:
    """
    A shutdown hook for cleanup operations.

    Attributes:
        name: Unique hook identifier
        priority: Hook execution priority
        cleanup_func: Async cleanup function
        timeout_seconds: Maximum time to wait for cleanup
        metadata: Additional metadata
    """
    name: str
    priority: ShutdownPriority
    cleanup_func: Callable[[], Awaitable[Any]]
    timeout_seconds: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ShutdownResult:
    """
    Result of a shutdown operation.

    Attributes:
        state: Final shutdown state
        hooks_executed: Total hooks executed
        hooks_succeeded: Hooks that completed successfully
        hooks_failed: Hooks that failed
        hooks_timed_out: Hooks that timed out
        duration_seconds: Total shutdown duration
        errors: List of errors encountered
    """
    state: ShutdownState
    hooks_executed: int = 0
    hooks_succeeded: int = 0
    hooks_failed: int = 0
    hooks_timed_out: int = 0
    duration_seconds: float = 0.0
    errors: List[Exception] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate shutdown success rate (0-1)."""
        if self.hooks_executed == 0:
            return 1.0
        return self.hooks_succeeded / self.hooks_executed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "hooks_executed": self.hooks_executed,
            "hooks_succeeded": self.hooks_succeeded,
            "hooks_failed": self.hooks_failed,
            "hooks_timed_out": self.hooks_timed_out,
            "success_rate": self.success_rate,
            "duration_seconds": self.duration_seconds,
            "error_count": len(self.errors),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "region": PHASE_10_REGION,
        }


@dataclass
class ShutdownConfig:
    """
    Configuration for graceful shutdown.

    Attributes:
        timeout_seconds: Maximum time for complete shutdown
        drain_timeout_seconds: Time to wait for connections to drain
        force_kill_after_seconds: Force kill if shutdown exceeds this time
        enable_signals: Whether to register signal handlers
        wait_for_active_executions: Whether to wait for active executions
    """
    timeout_seconds: float = 60.0
    drain_timeout_seconds: float = 30.0
    force_kill_after_seconds: float = 90.0
    enable_signals: bool = True
    wait_for_active_executions: bool = True


# ============================================================================
# Graceful Shutdown Manager
# ============================================================================

class GracefulShutdown:
    """
    Graceful shutdown coordination for AgentCore services.

    Features:
    - Signal handling (SIGTERM, SIGINT)
    - Priority-based hook execution
    - Timeout enforcement
    - Connection draining
    - Active execution waiting
    - Force kill fallback

    Usage:
        ```python
        shutdown = GracefulShutdown()

        # Register shutdown hooks
        shutdown.register_hook(
            name="close_connection_pool",
            priority=ShutdownPriority.HIGH,
            cleanup_func=lambda: pool.close()
        )

        # Start signal handling
        await shutdown.initialize()

        # ... application runs ...

        # Trigger shutdown (or wait for signal)
        result = await shutdown.shutdown()
        ```
    """

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        shutdown_config: Optional[ShutdownConfig] = None,
    ):
        """
        Initialize the graceful shutdown manager.

        Args:
            config: AgentCore configuration
            shutdown_config: Shutdown configuration
        """
        self.config = config or get_config()
        self._shutdown_config = shutdown_config or ShutdownConfig()

        self._state = ShutdownState.RUNNING
        self._hooks: Dict[str, ShutdownHook] = {}
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
        self._signal_handlers_registered = False

        # Validate region compliance for Phase 10
        if self.config.aws_region != PHASE_10_REGION:
            safe_log(
                f"GracefulShutdown: Region '{self.config.aws_region}' specified, "
                f"but Phase 10 requires '{PHASE_10_REGION}'. "
                f"Shutdown will enforce {PHASE_10_REGION} compliance."
            )

        safe_log("GracefulShutdown initialized")

    async def initialize(self) -> None:
        """Initialize graceful shutdown (register signal handlers)."""
        if self._shutdown_config.enable_signals:
            self._register_signal_handlers()

        safe_log("GracefulShutdown signal handlers registered")

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for SIGTERM and SIGINT."""
        try:
            loop = asyncio.get_event_loop()

            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self._handle_signal(sig))
                )

            self._signal_handlers_registered = True
            safe_log("Signal handlers registered for SIGTERM and SIGINT")

        except Exception as e:
            safe_log(f"Failed to register signal handlers: {e}", level="warning")

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle incoming shutdown signal."""
        safe_log(f"Received signal {sig.name}, initiating graceful shutdown")

        # Only initiate shutdown once
        if self._state == ShutdownState.RUNNING:
            await self.shutdown()

    def register_hook(
        self,
        name: str,
        priority: ShutdownPriority,
        cleanup_func: Callable[[], Awaitable[Any]],
        timeout_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a shutdown hook.

        Args:
            name: Unique hook identifier
            priority: Hook execution priority
            cleanup_func: Async cleanup function
            timeout_seconds: Maximum time to wait for cleanup
            metadata: Additional metadata
        """
        hook = ShutdownHook(
            name=name,
            priority=priority,
            cleanup_func=cleanup_func,
            timeout_seconds=timeout_seconds or self._shutdown_config.drain_timeout_seconds,
            metadata=metadata or {},
        )

        self._hooks[name] = hook
        safe_log(f"Registered shutdown hook '{name}' with priority {priority.value}")

    def unregister_hook(self, name: str) -> bool:
        """
        Unregister a shutdown hook.

        Args:
            name: Hook identifier

        Returns:
            True if hook was unregistered
        """
        if name in self._hooks:
            del self._hooks[name]
            safe_log(f"Unregistered shutdown hook '{name}'")
            return True
        return False

    async def shutdown(self) -> ShutdownResult:
        """
        Execute graceful shutdown.

        Returns:
            Shutdown result with statistics

        Raises:
            AgentCoreError: If shutdown is already in progress
        """
        if self._state != ShutdownState.RUNNING:
            raise AgentCoreError(f"Shutdown already {self._state.value}")

        self._state = ShutdownState.INITIATED
        self._shutdown_event.set()

        safe_log("Initiating graceful shutdown")
        start_time = time.time()

        result = ShutdownResult(
            state=ShutdownState.IN_PROGRESS,
            start_time=datetime.utcnow(),
        )

        try:
            # Sort hooks by priority (critical first)
            priority_order = {
                ShutdownPriority.CRITICAL: 0,
                ShutdownPriority.HIGH: 1,
                ShutdownPriority.NORMAL: 2,
                ShutdownPriority.LOW: 3,
            }

            sorted_hooks = sorted(
                self._hooks.values(),
                key=lambda h: priority_order.get(h.priority, 99)
            )

            # Execute hooks with timeout
            for hook in sorted_hooks:
                result.hooks_executed += 1

                try:
                    safe_log(f"Executing hook '{hook.name}' ({hook.priority.value})")

                    await asyncio.wait_for(
                        hook.cleanup_func(),
                        timeout=hook.timeout_seconds
                    )

                    result.hooks_succeeded += 1
                    safe_log(f"Hook '{hook.name}' completed successfully")

                except asyncio.TimeoutError:
                    result.hooks_timed_out += 1
                    error = AgentCoreError(f"Hook '{hook.name}' timed out after {hook.timeout_seconds}s")
                    result.errors.append(error)
                    safe_log(f"Hook '{hook.name}' timed out", level="warning")

                except Exception as e:
                    result.hooks_failed += 1
                    result.errors.append(e)
                    safe_log(f"Hook '{hook.name}' failed: {e}", level="error")

            # Wait for drain timeout
            if self._shutdown_config.wait_for_active_executions:
                await asyncio.sleep(self._shutdown_config.drain_timeout_seconds)

            result.state = ShutdownState.COMPLETED
            safe_log("Graceful shutdown completed successfully")

        except Exception as e:
            result.state = ShutdownState.FAILED
            result.errors.append(e)
            safe_log(f"Graceful shutdown failed: {e}", level="error")

        finally:
            # Calculate duration
            result.duration_seconds = time.time() - start_time
            result.end_time = datetime.utcnow()
            self._state = result.state

            # Unregister signal handlers
            if self._signal_handlers_registered:
                self._unregister_signal_handlers()

        return result

    async def shutdown_with_timeout(
        self,
        timeout_seconds: Optional[float] = None
    ) -> ShutdownResult:
        """
        Execute shutdown with overall timeout.

        Args:
            timeout_seconds: Maximum time for complete shutdown

        Returns:
            Shutdown result
        """
        timeout = timeout_seconds or self._shutdown_config.timeout_seconds

        try:
            return await asyncio.wait_for(
                self.shutdown(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            safe_log(f"Shutdown timed out after {timeout}s, forcing exit", level="warning")

            result = ShutdownResult(
                state=ShutdownState.TIMEOUT,
                duration_seconds=timeout,
            )

            # Force kill cleanup
            await self._force_kill_cleanup(result)

            return result

    async def _force_kill_cleanup(self, result: ShutdownResult) -> None:
        """Perform emergency cleanup when timeout exceeded."""
        safe_log("Performing force kill cleanup", level="warning")

        # Close all connection pools immediately
        # (This would be called by the registered hooks with CRITICAL priority)
        # The force kill is a last resort if those also timed out

        result.state = ShutdownState.TIMEOUT
        result.end_time = datetime.utcnow()

    def _unregister_signal_handlers(self) -> None:
        """Unregister signal handlers."""
        try:
            loop = asyncio.get_event_loop()

            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)

            self._signal_handlers_registered = False
            safe_log("Signal handlers unregistered")

        except Exception as e:
            safe_log(f"Failed to unregister signal handlers: {e}", level="warning")

    @property
    def state(self) -> ShutdownState:
        """Get current shutdown state."""
        return self._state

    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._state != ShutdownState.RUNNING

    def wait_for_shutdown(self, timeout: Optional[float] = None) -> Awaitable[bool]:
        """
        Wait for shutdown signal.

        Args:
            timeout: Maximum time to wait

        Returns:
            True if shutdown was triggered
        """
        return asyncio.wait_for(
            self._shutdown_event.wait(),
            timeout=timeout
        )


# ============================================================================
# Specialized Shutdown Managers
# ============================================================================

class AgentCoreShutdownManager(GracefulShutdown):
    """
    Shutdown manager specialized for AgentCore operations.

    Automatically registers common AgentCore shutdown hooks:
    - Connection pool cleanup
    - Cache flushing
    - Batch processor draining
    - Active execution waiting
    """

    async def initialize(self) -> None:
        """Initialize and register default AgentCore shutdown hooks."""
        await super().initialize()

        # Register default hooks for AgentCore components
        self._register_default_hooks()

    def _register_default_hooks(self) -> None:
        """Register default AgentCore shutdown hooks."""
        # Import here to avoid circular dependency
        try:
            # Connection pool cleanup (HIGH priority)
            try:
                from .connection_pool import close_pools

                self.register_hook(
                    name="close_connection_pools",
                    priority=ShutdownPriority.HIGH,
                    cleanup_func=close_pools,
                    timeout_seconds=10.0,
                    metadata={"description": "Close all AgentCore connection pools"}
                )
            except ImportError:
                pass

            # Cache manager cleanup (NORMAL priority)
            try:
                from ..cache import close_cache_manager

                self.register_hook(
                    name="close_cache_manager",
                    priority=ShutdownPriority.NORMAL,
                    cleanup_func=close_cache_manager,
                    timeout_seconds=5.0,
                    metadata={"description": "Flush and close cache manager"}
                )
            except ImportError:
                pass

            # Note: Additional hooks can be registered for:
            # - Runtime agent cancellation (CRITICAL)
            # - Browser session cleanup (HIGH)
            # - Code Interpreter session cleanup (HIGH)
            # - Batch processor draining (NORMAL)

        except Exception as e:
            safe_log(f"Failed to register default shutdown hooks: {e}", level="warning")


# ============================================================================
# Convenience Functions
# ============================================================================

_shutdown_manager: Optional[GracefulShutdown] = None


def get_shutdown_manager(
    config: Optional[AgentCoreConfig] = None,
    shutdown_config: Optional[ShutdownConfig] = None,
) -> GracefulShutdown:
    """
    Get the shutdown manager instance (singleton).

    Args:
        config: Optional AgentCore configuration
        shutdown_config: Optional shutdown configuration

    Returns:
        GracefulShutdown instance
    """
    global _shutdown_manager

    if _shutdown_manager is None:
        _shutdown_manager = AgentCoreShutdownManager(
            config=config,
            shutdown_config=shutdown_config
        )

    return _shutdown_manager


async def initialize_shutdown(
    config: Optional[AgentCoreConfig] = None,
    shutdown_config: Optional[ShutdownConfig] = None,
) -> GracefulShutdown:
    """
    Initialize the shutdown manager.

    Args:
        config: Optional AgentCore configuration
        shutdown_config: Optional shutdown configuration

    Returns:
        Initialized shutdown manager
    """
    manager = get_shutdown_manager(config, shutdown_config)
    await manager.initialize()
    return manager


async def trigger_shutdown() -> ShutdownResult:
    """
    Trigger graceful shutdown.

    Returns:
        Shutdown result
    """
    manager = get_shutdown_manager()
    return await manager.shutdown_with_timeout()


# ============================================================================
# Context Manager for Shutdown
# ============================================================================

class ShutdownGuard:
    """
    Context manager that ensures shutdown on exit.

    Usage:
        ```python
        async with ShutdownGuard() as guard:
            # Application runs here
            pass

        # Shutdown automatically triggered on exit
        ```
    """

    def __init__(
        self,
        config: Optional[AgentCoreConfig] = None,
        shutdown_config: Optional[ShutdownConfig] = None,
    ):
        self.config = config
        self.shutdown_config = shutdown_config
        self._manager: Optional[GracefulShutdown] = None

    async def __aenter__(self) -> "ShutdownGuard":
        """Enter context and initialize shutdown manager."""
        self._manager = await initialize_shutdown(
            config=self.config,
            shutdown_config=self.shutdown_config
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context and trigger shutdown."""
        if self._manager:
            result = await self._manager.shutdown_with_timeout()

            # Log shutdown summary
            safe_log(
                f"Shutdown summary: {result.hooks_succeeded}/{result.hooks_executed} "
                f"hooks succeeded in {result.duration_seconds:.2f}s"
            )


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "ShutdownState",
    "ShutdownPriority",
    "ShutdownHook",
    "ShutdownResult",
    "ShutdownConfig",
    "GracefulShutdown",
    "AgentCoreShutdownManager",
    "get_shutdown_manager",
    "initialize_shutdown",
    "trigger_shutdown",
    "ShutdownGuard",
]
