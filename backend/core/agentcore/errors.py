"""
AgentCore Error Handling and Retry Logic (Phase 10 Enhanced)

Provides exception hierarchy, retry utilities, and error recovery for AgentCore operations.
Implements exponential backoff retry logic for transient failures with enhanced context tracking.

Phase 10: Enhanced error handling with:
- Structured error context for debugging
- Error aggregation for batch operations
- Automatic error recovery strategies
- Error serialization for API responses
"""

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Phase 10 region
PHASE_10_REGION = "ap-southeast-2"


# ============================================================================
# Error Severity and Categories
# ============================================================================

class ErrorSeverity(str, Enum):
    """Severity level for errors."""
    LOW = "low"  # Non-critical, can be ignored
    MEDIUM = "medium"  # Affects functionality but system continues
    HIGH = "high"  # Critical, affects core functionality
    CRITICAL = "critical"  # System-impacting, immediate attention required


class ErrorCategory(str, Enum):
    """Categories of errors for better classification."""
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    SERVICE_UNAVAILABLE = "service_unavailable"
    VALIDATION = "validation"
    EXECUTION = "execution"
    RESOURCE_NOT_FOUND = "resource_not_found"
    TENANT = "tenant"
    GATEWAY = "gateway"
    BROWSER = "browser"
    CODE_INTERPRETER = "code_interpreter"
    MEMORY = "memory"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


# ============================================================================
# Error Context
# ============================================================================

@dataclass
class ErrorContext:
    """
    Structured context for error tracking and debugging.

    Attributes:
        error_type: Type of error
        category: Error category
        severity: Error severity
        message: Human-readable error message
        timestamp: When the error occurred
        region: AWS region where error occurred
        operation: Operation being performed
        resource_id: Related resource identifier
        account_id: Tenant/account ID
        retryable: Whether error is retryable
        retry_attempts: Number of retry attempts made
        cause: Original exception
        stack_trace: Exception stack trace
        metadata: Additional error metadata
        suggestion: Suggested fix (optional)
    """
    error_type: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    region: str = PHASE_10_REGION
    operation: Optional[str] = None
    resource_id: Optional[str] = None
    account_id: Optional[str] = None
    retryable: bool = False
    retry_attempts: int = 0
    cause: Optional[Exception] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error_type": self.error_type,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "region": self.region,
            "operation": self.operation,
            "resource_id": self.resource_id,
            "account_id": self.account_id,
            "retryable": self.retryable,
            "retry_attempts": self.retry_attempts,
            "cause": str(self.cause) if self.cause else None,
            "suggestion": self.suggestion,
            "metadata": self.metadata,
        }

    def to_log_string(self) -> str:
        """Generate a log-friendly string representation."""
        parts = [
            f"[{self.category.value.upper()}]",
            f"[{self.severity.value.upper()}]",
            self.message,
        ]
        if self.operation:
            parts.append(f"operation={self.operation}")
        if self.resource_id:
            parts.append(f"resource={self.resource_id}")
        if self.account_id:
            parts.append(f"account={self.account_id[:8]}...")  # Partial for safety
        return " ".join(parts)


# ============================================================================
# Exception Hierarchy
# ============================================================================

class AgentCoreError(Exception):
    """
    Base exception for all AgentCore errors.

    Enhanced with structured context for better debugging and monitoring.
    """

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        **kwargs
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self._context = context or ErrorContext(
            error_type=self.__class__.__name__,
            category=category,
            severity=severity,
            message=message,
            **kwargs
        )
        super().__init__(message)

    @property
    def context(self) -> ErrorContext:
        """Get the error context."""
        return self._context

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return self.context.to_dict()

    def __str__(self) -> str:
        return self.context.to_log_string()


class AgentCoreConfigurationError(AgentCoreError):
    """Raised when AgentCore configuration is invalid."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


class AgentCoreSessionError(AgentCoreError):
    """Raised when AgentCore session operations fail."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.EXECUTION,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class AgentCoreExecutionError(AgentCoreError):
    """Raised when code or command execution fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.EXECUTION,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class AgentCoreBrowserError(AgentCoreError):
    """Raised when browser automation fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.BROWSER,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class AgentCoreRetryableError(AgentCoreError):
    """Base exception for retryable transient errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("retryable", True)
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class AgentCoreNonRetryableError(AgentCoreError):
    """Base exception for non-retryable errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("retryable", False)
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


# Specific retryable errors
class ThrottlingError(AgentCoreRetryableError):
    """Raised when API rate limits are exceeded."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.MEDIUM,
            suggestion="Implement exponential backoff and retry",
            **kwargs
        )


class ServiceUnavailableError(AgentCoreRetryableError):
    """Raised when AgentCore service is temporarily unavailable."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.SERVICE_UNAVAILABLE,
            severity=ErrorSeverity.HIGH,
            suggestion="Retry with exponential backoff",
            **kwargs
        )


class NetworkError(AgentCoreRetryableError):
    """Raised when network connectivity fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            suggestion="Check network connectivity and retry",
            **kwargs
        )


# Specific non-retryable errors
class AuthenticationError(AgentCoreNonRetryableError):
    """Raised when AWS credentials are invalid."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.CRITICAL,
            suggestion="Verify AWS credentials are valid",
            **kwargs
        )


class AuthorizationError(AgentCoreNonRetryableError):
    """Raised when IAM permissions are insufficient."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.CRITICAL,
            suggestion="Check IAM permissions for required resources",
            **kwargs
        )


class ResourceNotFoundError(AgentCoreNonRetryableError):
    """Raised when a requested resource doesn't exist."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.RESOURCE_NOT_FOUND,
            severity=ErrorSeverity.HIGH,
            suggestion="Verify the resource exists and you have access",
            **kwargs
        )


class ValidationError(AgentCoreNonRetryableError):
    """Raised when input validation fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            suggestion="Review input parameters and try again",
            **kwargs
        )


class AgentCoreTenantError(AgentCoreNonRetryableError):
    """Raised when tenant tries to access another tenant's resources."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.TENANT,
            severity=ErrorSeverity.CRITICAL,
            suggestion="Verify you're accessing resources within your tenant",
            **kwargs
        )


# Gateway-specific errors
class GatewayError(AgentCoreError):
    """Base exception for Gateway-related errors."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.GATEWAY,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


class MCPServerNotFoundError(GatewayError):
    """Raised when requested MCP server deployment doesn't exist."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            suggestion="Verify MCP server is deployed",
            **kwargs
        )


class MCPToolInvocationError(GatewayError):
    """Raised when MCP tool invocation fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            suggestion="Verify tool is registered and available",
            **kwargs
        )


class OAuthFlowError(GatewayError):
    """Raised when OAuth flow fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            suggestion="Verify OAuth configuration and retry flow",
            **kwargs
        )


class InvalidOAuthStateError(OAuthFlowError):
    """Raised when OAuth state validation fails."""

    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            suggestion="OAuth state invalid or expired, restart OAuth flow",
            **kwargs
        )


# ============================================================================
# MultiError for Batch Operations
# ============================================================================

@dataclass
class ErrorAccumulation:
    """
    Accumulated errors from batch operations.

    Attributes:
        total_items: Total number of items processed
        successful_count: Number of successful operations
        error_count: Number of errors
        errors: List of (item_id, error) tuples
    """
    total_items: int
    successful_count: int
    error_count: int
    errors: List[tuple] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.successful_count / self.total_items) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_items": self.total_items,
            "successful_count": self.successful_count,
            "error_count": self.error_count,
            "success_rate": round(self.success_rate, 2),
            "errors": [
                {"item_id": item_id, "error": error.to_dict() if hasattr(error, 'to_dict') else str(error)}
                for item_id, error in self.errors
            ],
        }


class MultiError(AgentCoreError):
    """
    Exception for aggregating multiple errors from batch operations.

    Usage:
        ```python
        errors = []
        for item in items:
            try:
                await process(item)
            except Exception as e:
                errors.append((item.id, e))

        if errors:
            raise MultiError(
                "Batch processing had errors",
                accumulation=ErrorAccumulation(
                    total_items=len(items),
                    successful_count=len(items) - len(errors),
                    error_count=len(errors),
                    errors=errors,
                )
            )
        ```
    """

    def __init__(
        self,
        message: str,
        *,
        accumulation: ErrorAccumulation,
        **kwargs
    ):
        self.accumulation = accumulation
        super().__init__(
            message,
            category=ErrorCategory.EXECUTION,
            severity=ErrorSeverity.MEDIUM if accumulation.success_rate > 50 else ErrorSeverity.HIGH,
            **kwargs
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base_dict = super().to_dict()
        base_dict["accumulation"] = self.accumulation.to_dict()
        return base_dict


# ============================================================================
# Error Detection
# ============================================================================

def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.

    Args:
        error: The exception to check

    Returns:
        True if the error should be retried, False otherwise
    """
    # Direct instance checks for our custom exceptions
    if isinstance(error, AgentCoreRetryableError):
        return True
    if isinstance(error, AgentCoreNonRetryableError):
        return False

    # Check boto3/client errors for retryable patterns
    error_message = str(error).lower()

    # Retryable error patterns
    retryable_patterns = [
        'throttling',
        'rate limit',
        'too many requests',
        'service unavailable',
        '503',
        '500',
        'timeout',
        'connection',
        'network',
        'temporary failure',
    ]

    return any(pattern in error_message for pattern in retryable_patterns)


def get_error_category(error: Exception) -> ErrorCategory:
    """
    Determine error category from exception.

    Args:
        error: The exception to categorize

    Returns:
        Error category
    """
    if isinstance(error, AgentCoreError):
        return error.category

    error_message = str(error).lower()

    # Categorize based on error message
    if 'throttl' in error_message or 'rate limit' in error_message:
        return ErrorCategory.RATE_LIMIT
    if 'auth' in error_message and 'permission' in error_message:
        return ErrorCategory.AUTHORIZATION
    if 'auth' in error_message or 'credential' in error_message:
        return ErrorCategory.AUTHENTICATION
    if 'not found' in error_message or 'does not exist' in error_message:
        return ErrorCategory.RESOURCE_NOT_FOUND
    if 'timeout' in error_message or 'connection' in error_message:
        return ErrorCategory.NETWORK
    if 'valid' in error_message or 'invalid' in error_message:
        return ErrorCategory.VALIDATION

    return ErrorCategory.UNKNOWN


# ============================================================================
# Retry Decorators
# ============================================================================

def with_retry(
    func: Optional[Callable[..., T]] = None,
    *,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Union[Callable[[Callable[..., T]], Callable[..., T]], Callable[..., T]]:
    """
    Decorator factory or direct function to execute an async function with retry logic.

    Can be used in two ways:
    1. As a decorator: @with_retry(max_attempts=3)
    2. As a direct function: await with_retry(my_func, arg1, arg2, max_attempts=3)

    Args:
        func: The async function to execute (optional when used as decorator)
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff in seconds
        max_delay: Maximum delay between retries in seconds
        on_retry: Callback function called after each retry (receives exception, attempt number)

    Returns:
        Decorator function or direct result

    Raises:
        AgentCoreError: If all retry attempts fail
    """
    from .config import get_config

    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @wraps(f)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            config = get_config()

            # Use config defaults if not specified
            attempts = max_attempts if max_attempts is not None else config.retry_max_attempts
            delay = base_delay if base_delay is not None else config.retry_base_delay_seconds
            max_d = max_delay if max_delay is not None else config.retry_max_delay_seconds

            last_error = None

            for attempt in range(attempts):
                try:
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt + 1}/{attempts} for {f.__name__}")
                    return await f(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    # Update error context with retry info
                    if isinstance(e, AgentCoreError):
                        e.context.retry_attempts = attempt + 1

                    # Call on_retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1)
                        except Exception:
                            pass  # Ignore callback errors

                    # Check if error is retryable
                    if not is_retryable_error(e):
                        logger.error(f"Non-retryable error in {f.__name__}: {safe_format(str(e))}")
                        raise

                    # If this was the last attempt, raise
                    if attempt >= attempts - 1:
                        logger.error(
                            f"Max retry attempts ({attempts}) exceeded for {f.__name__}: {safe_format(str(e))}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    current_delay = min(delay * (2 ** attempt), max_d)
                    logger.warning(
                        f"Retryable error in {f.__name__} (attempt {attempt + 1}/{attempts}): {safe_format(str(e))}. "
                        f"Retrying in {current_delay:.2f} seconds..."
                    )
                    await asyncio.sleep(current_delay)

            # Should never reach here, but type checkers need it
            if last_error:
                raise last_error
            raise AgentCoreError("Unexpected error in retry logic")

        return wrapper

    if func is not None:
        # Called without arguments: @with_retry or with_retry(func)
        return decorator(func)
    else:
        # Called with arguments: @with_retry(max_attempts=3)
        return decorator


# Synchronous retry decorator for non-async functions
def sync_retry(
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
):
    """
    Decorator for adding retry logic to sync functions

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff
        max_delay: Maximum delay between retries
    """
    from .config import get_config
    config = get_config()

    if max_attempts is None:
        max_attempts = config.retry_max_attempts
    if base_delay is None:
        base_delay = config.retry_base_delay_seconds
    if max_delay is None:
        max_delay = config.retry_max_delay_seconds

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None

            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt + 1}/{max_attempts} for {func.__name__}")
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e

                    if not is_retryable_error(e):
                        logger.error(f"Non-retryable error in {func.__name__}: {safe_format(str(e))}")
                        raise

                    if attempt >= max_attempts - 1:
                        logger.error(
                            f"Max retry attempts ({max_attempts}) exceeded for {func.__name__}: {safe_format(str(e))}"
                        )
                        raise

                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"Retryable error in {func.__name__} (attempt {attempt + 1}/{max_attempts}): {safe_format(str(e))}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    import time
                    time.sleep(delay)

            if last_error:
                raise last_error
            raise AgentCoreError("Unexpected error in retry logic")

        return wrapper
    return decorator


# ============================================================================
# Error Recovery Utilities
# ============================================================================

@asynccontextmanager
async def error_boundary(
    *,
    fallback: Any = None,
    catch: tuple = (Exception,),
    on_error: Optional[Callable[[Exception], Any]] = None,
    reraise: bool = False,
):
    """
    Context manager for catching and handling errors gracefully.

    Usage:
        ```python
        async with error_boundary(fallback={"default": True}, catch=(ValueError,)):
            result = await risky_operation()
        # Returns result or fallback if error occurred
        ```

    Args:
        fallback: Fallback value to return on error
        catch: Exception types to catch
        on_error: Callback function called with exception
        reraise: Whether to re-raise after handling

    Yields:
        None
    """
    try:
        yield
    except catch as e:
        safe_log(f"Error boundary caught {type(e).__name__}: {safe_format(str(e))}")

        # Call on_error callback if provided
        if on_error:
            try:
                result = on_error(e)
                if result is not None:
                    yield result
                    return
            except Exception:
                pass  # Ignore callback errors

        # Return fallback if provided
        if fallback is not None:
            yield fallback

        # Re-raise if requested
        if reraise:
            raise


async def with_fallback(
    primary_func: Callable[..., T],
    fallback_func: Optional[Callable[..., T]] = None,
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Execute primary function with fallback on failure.

    Usage:
        ```python
        result = await with_fallback(
            primary_operation,
            fallback_operation,
            arg1, arg2
        )
        ```

    Args:
        primary_func: Primary function to execute
        fallback_func: Fallback function if primary fails
        *args: Positional arguments for function
        **kwargs: Keyword arguments for function

    Returns:
        Result from primary or fallback function

    Raises:
        Exception: If both primary and fallback fail
    """
    try:
        return await primary_func(*args, **kwargs)
    except Exception as e:
        safe_log(f"Primary function failed: {safe_format(str(e))}")

        if fallback_func:
            try:
                return await fallback_func(*args, **kwargs)
            except Exception as fallback_error:
                safe_log(f"Fallback function also failed: {safe_format(str(fallback_error))}")
                raise AgentCoreExecutionError(
                    f"Both primary and fallback functions failed",
                    cause=fallback_error,
                ) from fallback_error
        raise


# ============================================================================
# Safe Logging and Data Redaction
# ============================================================================

def redact_sensitive_data(data: str, sensitive_patterns: Optional[list] = None) -> str:
    """
    Redact sensitive data from log messages.

    Args:
        data: The data string to redact
        sensitive_patterns: List of regex patterns for sensitive data (optional)

    Returns:
        The data string with sensitive information redacted
    """
    import re

    if sensitive_patterns is None:
        sensitive_patterns = [
            # AWS Access Keys
            r'AKIA[0-9A-Z]{16}',
            # AWS Secret Keys (partial match)
            r'(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{32,}(?![A-Za-z0-9/+=])',
            # API Keys
            r'(?i)api[_-]?key["\']*[:=]["\']*[\w-]+',
            # Passwords
            r'(?i)password["\']*[:=]["\']*[\w-]+',
            # Tokens
            r'(?i)token["\']*[:=]["\']*[\w-]+',
            # Session IDs (partial redaction)
            r'\b[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}\b',
        ]

    redacted = data
    for pattern in sensitive_patterns:
        # Replace with redacted placeholder but keep structure for debugging
        if 'AKIA' in pattern:  # AWS Access Key
            redacted = re.sub(pattern, lambda m: m.group(0)[:4] + 'REDACTED' + m.group(0)[-4:], redacted)
        else:
            redacted = re.sub(pattern, '[REDACTED]', redacted)

    return redacted


def safe_format(message: str) -> str:
    """
    Format a message safely with sensitive data redacted.

    Args:
        message: The message to format

    Returns:
        Redacted message string
    """
    return redact_sensitive_data(str(message))


def safe_log(message: str, level: str = "info", exc_info: bool = False) -> None:
    """
    Log a message with sensitive data redacted.

    Args:
        message: The message to log
        level: Log level (debug, info, warning, error)
        exc_info: Include exception info
    """
    redacted = redact_sensitive_data(message)
    log_func = getattr(logger, level.lower(), logger.info)

    if exc_info:
        log_func(redacted, exc_info=True)
    else:
        log_func(redacted)


# ============================================================================
# Batch Error Handling
# ============================================================================

async def execute_batch_with_tolerance(
    items: List[Any],
    execute_func: Callable[[Any], Any],
    *,
    max_errors: int = 0,
    raise_on_error: bool = False,
    continue_on_error: bool = True,
) -> ErrorAccumulation:
    """
    Execute batch operations with error tolerance.

    Usage:
        ```python
        async def process_item(item):
            return await some_api_call(item)

        result = await execute_batch_with_tolerance(
            items=[1, 2, 3, 4, 5],
            execute_func=process_item,
            max_errors=2
        )
        print(f"Success rate: {result.success_rate}%")
        ```

    Args:
        items: Items to process
        execute_func: Async function to execute on each item
        max_errors: Maximum errors before aborting (0 = no limit)
        raise_on_error: Raise immediately on first error
        continue_on_error: Continue processing after errors

    Returns:
        ErrorAccumulation with results
    """
    accumulation = ErrorAccumulation(
        total_items=len(items),
        successful_count=0,
        error_count=0,
        errors=[],
    )

    for item in items:
        try:
            result = await execute_func(item)
            accumulation.successful_count += 1
        except Exception as e:
            accumulation.error_count += 1
            accumulation.errors.append((str(item), e))

            # Check if we should abort
            if max_errors > 0 and accumulation.error_count >= max_errors:
                safe_log(f"Max errors ({max_errors}) reached, aborting batch")
                break

            if raise_on_error:
                raise

            if not continue_on_error:
                break

    return accumulation


# Export public symbols
__all__ = [
    # Region
    "PHASE_10_REGION",
    # Enums
    "ErrorSeverity",
    "ErrorCategory",
    # Context
    "ErrorContext",
    "ErrorAccumulation",
    # Exceptions
    "AgentCoreError",
    "AgentCoreConfigurationError",
    "AgentCoreSessionError",
    "AgentCoreExecutionError",
    "AgentCoreBrowserError",
    "AgentCoreRetryableError",
    "AgentCoreNonRetryableError",
    "ThrottlingError",
    "ServiceUnavailableError",
    "NetworkError",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "ValidationError",
    "AgentCoreTenantError",
    "GatewayError",
    "MCPServerNotFoundError",
    "MCPToolInvocationError",
    "OAuthFlowError",
    "InvalidOAuthStateError",
    "MultiError",
    # Utilities
    "is_retryable_error",
    "get_error_category",
    "with_retry",
    "sync_retry",
    "error_boundary",
    "with_fallback",
    "execute_batch_with_tolerance",
    "redact_sensitive_data",
    "safe_format",
    "safe_log",
]
