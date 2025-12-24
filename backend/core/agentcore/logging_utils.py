"""
AgentCore Logging Utilities (Phase 10)

Structured logging utilities for AgentCore operations in ap-southeast-2.

Phase 10: Enhanced logging with structured context, sensitive data redaction,
and tenant-aware logging for production observability.
"""

import json
import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from contextlib import contextmanager
import traceback

from .config import AgentCoreConfig
from .errors import safe_log, safe_format

# Phase 10 default region
PHASE_10_REGION = "ap-southeast-2"

# ============================================================================
# Enums and Data Classes
# ============================================================================

class LogLevel(str, Enum):
    """Logging levels for AgentCore operations."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(str, Enum):
    """Categories of logs for filtering and analysis."""
    RUNTIME = "runtime"
    MEMORY = "memory"
    CODE_INTERPRETER = "code_interpreter"
    BROWSER = "browser"
    GATEWAY = "gateway"
    BILLING = "billing"
    TENANT = "tenant"
    PERFORMANCE = "performance"
    SECURITY = "security"
    VALIDATION = "validation"
    CACHE = "cache"
    NETWORK = "network"
    EXECUTION = "execution"
    SYSTEM = "system"


@dataclass
class LogContext:
    """
    Context information for structured log entries.

    Attributes:
        account_id: Tenant account ID
        tenant_id: Tenant identifier
        execution_id: AgentCore execution identifier
        agent_id: Agent identifier
        deployment_id: Runtime deployment identifier
        region: AWS region (enforced ap-southeast-2)
        category: Log category
        operation: Operation being performed
        component: System component
        timestamp: Log timestamp
        metadata: Additional structured metadata
    """
    account_id: Optional[str] = None
    tenant_id: Optional[str] = None
    execution_id: Optional[str] = None
    agent_id: Optional[str] = None
    deployment_id: Optional[str] = None
    region: str = PHASE_10_REGION
    category: Optional[LogCategory] = None
    operation: Optional[str] = None
    component: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": redact_value(self.account_id) if self.account_id else None,
            "tenant_id": redact_value(self.tenant_id) if self.tenant_id else None,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "deployment_id": self.deployment_id,
            "region": self.region,
            "category": self.category.value if self.category else None,
            "operation": self.operation,
            "component": self.component,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class StructuredLog:
    """
    A structured log entry with context and metadata.

    Attributes:
        level: Log level
        message: Log message (redacted)
        context: Log context
        exception: Exception information (optional)
        extra: Additional fields
    """
    level: LogLevel
    message: str
    context: Optional[LogContext] = None
    exception: Optional[Dict[str, Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "level": self.level.value,
            "message": self.message,
            "region": PHASE_10_REGION,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if self.context:
            result["context"] = self.context.to_dict()

        if self.exception:
            result["exception"] = self.exception

        if self.extra:
            result["extra"] = self.extra

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


# ============================================================================
# Sensitive Data Redaction
# ============================================================================

SENSITIVE_KEYS: Set[str] = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "session_token",
    "authorization",
    "cookie",
    "credit_card",
    "ssn",
    "social_security",
    "private_key",
    "auth",
    "credentials",
}


def redact_value(value: Any) -> str:
    """
    Redact sensitive values from log output.

    Args:
        value: Value to potentially redact

    Returns:
        Redacted string representation
    """
    if value is None:
        return ""

    value_str = str(value)

    # Check if value looks like a sensitive data pattern
    # Credit card numbers (16 digits, possibly with spaces/dashes)
    if any(c.isdigit() for c in value_str) and len(value_str) >= 14:
        digits_only = "".join(c for c in value_str if c.isdigit())
        if len(digits_only) >= 14 and len(digits_only) <= 16:
            return "***REDACTED***"

    # API keys/tokens (long alphanumeric strings)
    if len(value_str) > 20 and any(c.isalnum() for c in value_str):
        # If it has high entropy (mix of letters, numbers, special chars)
        if (any(c.isupper() for c in value_str) and
            any(c.islower() for c in value_str) and
            any(c.isdigit() for c in value_str)):
            return "***REDACTED***"

    return value_str[:100]  # Limit length


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact sensitive values from a dictionary.

    Args:
        data: Dictionary to redact

    Returns:
        Dictionary with sensitive values redacted
    """
    if not data:
        return {}

    redacted = {}

    for key, value in data.items():
        key_lower = key.lower()

        if key_lower in SENSITIVE_KEYS:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value

    return redacted


# ============================================================================
# AgentCore Logger
# ============================================================================

class AgentCoreLogger:
    """
    Structured logger for AgentCore operations.

    Features:
    - Structured JSON logging
    - Sensitive data redaction
    - Tenant-aware context
    - Log level management
    - File and console handlers
    - Performance metrics logging

    Usage:
        ```python
        logger = AgentCoreLogger("agentcore.runtime")

        # Basic logging
        logger.info("Agent execution started")

        # With context
        logger.info(
            "Agent execution started",
            context=LogContext(
                account_id="acct-123",
                execution_id="exec-456",
                category=LogCategory.RUNTIME
            )
        )

        # With exception
        try:
            ...
        except Exception as e:
            logger.error(
                "Agent execution failed",
                exception=e,
                context=ctx
            )
        ```
    """

    _loggers: Dict[str, "AgentCoreLogger"] = {}
    _initialized = False

    def __new__(cls, name: str, config: Optional[AgentCoreConfig] = None):
        """Singleton pattern for logger instances."""
        if name not in cls._loggers:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._loggers[name] = instance
        return cls._loggers[name]

    def __init__(
        self,
        name: str,
        config: Optional[AgentCoreConfig] = None,
        log_level: LogLevel = LogLevel.INFO,
        log_file: Optional[Path] = None,
    ):
        """
        Initialize AgentCore logger.

        Args:
            name: Logger name (e.g., "agentcore.runtime")
            config: AgentCore configuration
            log_level: Minimum log level
            log_file: Optional log file path
        """
        if self._initialized:
            return

        self.name = name
        self.config = config or AgentCoreConfig()
        self._log_level = log_level
        self._log_file = log_file
        self._context: Optional[LogContext] = None

        # Create Python logger
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, log_level.value.upper()))
        self._logger.handlers.clear()

        # Console handler with formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.value.upper()))

        # Use JSON formatter for production
        if self.config.environment.value == "production":
            formatter = JsonFormatter(region=self.config.aws_region)
        else:
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )

        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

        # File handler (optional)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
            )
            file_handler.setLevel(getattr(logging, log_level.value.upper()))
            file_handler.setFormatter(JsonFormatter(region=self.config.aws_region))
            self._logger.addHandler(file_handler)

        self._initialized = True

    def with_context(self, context: LogContext) -> "AgentCoreLogger":
        """
        Set context for subsequent log entries.

        Args:
            context: Log context to use

        Returns:
            Self for chaining
        """
        self._context = context
        return self

    @contextmanager
    def context_bound(
        self,
        account_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        category: Optional[LogCategory] = None,
        **metadata
    ):
        """
        Context manager for temporary log context.

        Usage:
            ```python
            with logger.context_bound(
                account_id="acct-123",
                execution_id="exec-456",
                category=LogCategory.RUNTIME
            ):
                logger.info("This log will have the context attached")
            ```
        """
        old_context = self._context
        self._context = LogContext(
            account_id=account_id,
            execution_id=execution_id,
            agent_id=agent_id,
            category=category,
            metadata=metadata,
        )
        try:
            yield self
        finally:
            self._context = old_context

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message."""
        self._log(logging.ERROR, message, exception=exception, **kwargs)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log critical message."""
        self._log(logging.CRITICAL, message, exception=exception, **kwargs)

    def _log(
        self,
        level: int,
        message: str,
        exception: Optional[Exception] = None,
        **kwargs
    ):
        """Internal logging method."""
        # Create structured log
        structured = StructuredLog(
            level=LogLevel(level).value.lower() if isinstance(level, int) else level,
            message=safe_format(message),
            context=self._context,
            extra=kwargs.get("extra", {}),
        )

        # Add exception info
        if exception:
            structured.exception = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exc(),
            }

        # Log using Python logger
        extra = {}
        if structured.context:
            extra["structured_context"] = structured.context.to_dict()
        if structured.extra:
            extra["structured_extra"] = structured.extra

        self._logger.log(level, message, extra=extra, exc_info=exception is not None)


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, region: str = PHASE_10_REGION):
        super().__init__()
        self.region = region

    def format(self, record: logging.Log) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "region": self.region,
        }

        # Add context if available
        if hasattr(record, "structured_context"):
            log_entry["context"] = record.structured_context

        # Add extra fields
        if hasattr(record, "structured_extra"):
            log_entry["extra"] = record.structured_extra

        # Add exception info
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None,
            }

        return json.dumps(log_entry, default=str)


# ============================================================================
# Convenience Functions
# ============================================================================

def get_logger(
    name: str,
    config: Optional[AgentCoreConfig] = None,
    log_level: LogLevel = LogLevel.INFO,
) -> AgentCoreLogger:
    """
    Get or create an AgentCore logger.

    Args:
        name: Logger name
        config: Optional AgentCore configuration
        log_level: Log level

    Returns:
        AgentCoreLogger instance
    """
    return AgentCoreLogger(name, config=config, log_level=log_level)


def log_execution_time(
    logger: AgentCoreLogger,
    operation: str,
    category: LogCategory = LogCategory.PERFORMANCE,
):
    """
    Context manager to log execution time.

    Usage:
        ```python
        with log_execution_time(logger, "deploy_agent"):
            result = await deploy_agent(...)
        ```
    """
    import time
    from contextlib import contextmanager

    @contextmanager
    def _timer():
        start = time.time()
        yield
        elapsed = time.time() - start

        logger.info(
            f"{operation} completed",
            context=LogContext(
                category=category,
                operation=operation,
            ),
            extra={
                "execution_time_seconds": elapsed,
            }
        )

    return _timer()


def log_tenant_action(
    logger: AgentCoreLogger,
    action: str,
    account_id: str,
    **metadata
):
    """
    Log a tenant-specific action with context.

    Args:
        logger: AgentCore logger
        action: Action description
        account_id: Tenant account ID
        **metadata: Additional metadata
    """
    logger.info(
        f"Tenant action: {action}",
        context=LogContext(
            account_id=account_id,
            category=LogCategory.TENANT,
            operation=action,
            metadata=metadata,
        )
    )


# ============================================================================
# Performance Logging
# ============================================================================

class PerformanceLogger:
    """Logger for performance metrics and timing."""

    def __init__(self, logger: AgentCoreLogger):
        self.logger = logger
        self._timings: Dict[str, List[float]] = {}

    def record_timing(self, operation: str, duration_seconds: float):
        """
        Record a timing measurement.

        Args:
            operation: Operation name
            duration_seconds: Duration in seconds
        """
        if operation not in self._timings:
            self._timings[operation] = []

        self._timings[operation].append(duration_seconds)

    def get_stats(self, operation: str) -> Dict[str, float]:
        """
        Get statistics for an operation.

        Args:
            operation: Operation name

        Returns:
            Statistics dictionary
        """
        if operation not in self._timings or not self._timings[operation]:
            return {}

        timings = self._timings[operation]

        return {
            "count": len(timings),
            "total_seconds": sum(timings),
            "avg_seconds": sum(timings) / len(timings),
            "min_seconds": min(timings),
            "max_seconds": max(timings),
        }

    def log_summary(self):
        """Log summary of all recorded timings."""
        for operation, timings in self._timings.items():
            stats = self.get_stats(operation)

            self.logger.info(
                f"Performance summary: {operation}",
                context=LogContext(category=LogCategory.PERFORMANCE),
                extra={
                    "operation": operation,
                    "stats": stats,
                }
            )


# Export public symbols
__all__ = [
    "PHASE_10_REGION",
    "LogLevel",
    "LogCategory",
    "LogContext",
    "StructuredLog",
    "AgentCoreLogger",
    "JsonFormatter",
    "get_logger",
    "log_execution_time",
    "log_tenant_action",
    "PerformanceLogger",
    "redact_value",
    "redact_dict",
    "SENSITIVE_KEYS",
]
