"""
Tenant Context Middleware for AgentCore Multi-Tenancy

Provides async-safe tenant context propagation using contextvars.
Ensures tenant isolation across all AgentCore adapters.
"""

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional, Set, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# ContextVar for async-safe tenant context propagation
_tenant_context: ContextVar[Optional["TenantContext"]] = ContextVar(
    "tenant_context",
    default=None
)


@dataclass
class TenantContext:
    """
    Tenant context for multi-tenancy isolation.

    This context is propagated through async calls using contextvars,
    ensuring that tenant information is available throughout the
    request lifecycle without explicit parameter passing.

    Attributes:
        account_id: Unique identifier for the tenant account
        deployment_id: Optional Runtime deployment ID for this tenant
        user_id: Optional user ID within the tenant
        tier: Subscription tier (free, pro, enterprise)
        permissions: Set of granted permissions for this context
        created_at: When this context was created
        metadata: Additional tenant-specific metadata

    Example:
        ```python
        from core.agentcore.middleware.tenant import TenantContext, _tenant_context

        # Set tenant context
        ctx = TenantContext(
            account_id="acct-123",
            user_id="user-456",
            tier="pro"
        )
        _tenant_context.set(ctx)

        # Access from any async function
        current = _tenant_context.get()
        if current:
            print(f"Tenant: {current.account_id}")
        ```
    """

    account_id: str
    deployment_id: Optional[str] = None
    user_id: Optional[str] = None
    tier: str = "free"
    permissions: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)

    def can_access_resource(self, resource_account_id: str) -> bool:
        """
        Check if this tenant context can access a resource.

        Args:
            resource_account_id: Account ID that owns the resource

        Returns:
            True if the resource belongs to this tenant
        """
        return self.account_id == resource_account_id

    def has_permission(self, permission: str) -> bool:
        """
        Check if this tenant context has a specific permission.

        Args:
            permission: Permission string to check

        Returns:
            True if the permission is granted
        """
        return permission in self.permissions

    def has_any_permission(self, permissions: Set[str]) -> bool:
        """
        Check if this tenant context has any of the specified permissions.

        Args:
            permissions: Set of permissions to check

        Returns:
            True if at least one permission is granted
        """
        return bool(self.permissions & permissions)

    def with_deployment(self, deployment_id: str) -> "TenantContext":
        """
        Create a copy of this context with a different deployment ID.

        Args:
            deployment_id: New deployment ID

        Returns:
            New TenantContext with updated deployment_id
        """
        return TenantContext(
            account_id=self.account_id,
            deployment_id=deployment_id,
            user_id=self.user_id,
            tier=self.tier,
            permissions=self.permissions.copy(),
            created_at=self.created_at,
            metadata=self.metadata.copy()
        )

    def __repr__(self) -> str:
        """String representation with sensitive data redacted"""
        return (
            f"TenantContext("
            f"account_id={self.account_id[:8]}..., "
            f"user_id={self.user_id[:8] if self.user_id else None}..., "
            f"tier={self.tier}, "
            f"permissions_count={len(self.permissions)})"
        )


class TenantMiddleware:
    """
    Middleware for managing tenant context in async applications.

    Provides a context manager for setting tenant context during request
    processing and utility methods for working with tenant context.

    Example:
        ```python
        middleware = TenantMiddleware()

        # Use as context manager
        async with middleware.with_tenant_context(account_id="acct-123"):
            # All code here has access to tenant context
            current = _tenant_context.get()
            print(f"Processing for tenant: {current.account_id}")
        ```
    """

    async def __aenter__(self) -> "TenantMiddleware":
        """Enter context manager (no-op, use with_tenant_context instead)"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and clear tenant context"""
        _tenant_context.set(None)

    def with_tenant_context(
        self,
        account_id: str,
        user_id: Optional[str] = None,
        tier: str = "free",
        permissions: Optional[Set[str]] = None,
        deployment_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> "TenantContextManager":
        """
        Create a context manager for setting tenant context.

        Args:
            account_id: Tenant account ID
            user_id: Optional user ID
            tier: Subscription tier (default: free)
            permissions: Optional set of permissions
            deployment_id: Optional deployment ID
            metadata: Optional additional metadata

        Returns:
            Context manager that sets tenant context

        Example:
            ```python
            middleware = TenantMiddleware()

            async with middleware.with_tenant_context(
                account_id="acct-123",
                user_id="user-456",
                tier="pro"
            ):
                # Tenant context is available here
                await some_agentcore_operation()
            ```
        """
        context = TenantContext(
            account_id=account_id,
            user_id=user_id,
            tier=tier,
            permissions=permissions or set(),
            deployment_id=deployment_id,
            metadata=metadata or {}
        )
        return TenantContextManager(context)


class TenantContextManager:
    """
    Context manager for setting and clearing tenant context.

    This is returned by TenantMiddleware.with_tenant_context()
    and should not be instantiated directly.
    """

    def __init__(self, context: TenantContext):
        self._context = context
        self._token = None

    async def __aenter__(self) -> TenantContext:
        """Set tenant context on entry"""
        self._token = _tenant_context.set(self._context)
        logger.debug(
            f"Tenant context set: account_id={self._context.account_id[:8]}..., "
            f"user_id={self._context.user_id[:8] if self._context.user_id else None}..."
        )
        return self._context

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clear tenant context on exit"""
        if self._token is not None:
            _tenant_context.reset(self._token)
            logger.debug("Tenant context cleared")


def get_tenant_context() -> Optional[TenantContext]:
    """
    Get the current tenant context.

    Returns:
        Current TenantContext or None if no context is set

    Example:
        ```python
        from core.agentcore.middleware.tenant import get_tenant_context

        ctx = get_tenant_context()
        if ctx:
            print(f"Processing for tenant: {ctx.account_id}")
        else:
            print("No tenant context available")
        ```
    """
    return _tenant_context.get()


def require_tenant_context() -> TenantContext:
    """
    Get the current tenant context or raise an error.

    Returns:
        Current TenantContext

    Raises:
        AgentCoreSessionError: If no tenant context is set

    Example:
        ```python
        from core.agentcore.middleware.tenant import require_tenant_context

        # Will raise if no context is set
        ctx = require_tenant_context()
        print(f"Processing for tenant: {ctx.account_id}")
        ```
    """
    from ..errors import AgentCoreSessionError

    ctx = _tenant_context.get()
    if ctx is None:
        raise AgentCoreSessionError(
            "Tenant context is required but not set. "
            "Use TenantMiddleware.with_tenant_context() to set context."
        )
    return ctx


def verify_tenant_access(resource_account_id: str) -> bool:
    """
    Verify that the current tenant can access a resource.

    Args:
        resource_account_id: Account ID that owns the resource

    Returns:
        True if access is allowed, False otherwise

    Example:
        ```python
        from core.agentcore.middleware.tenant import verify_tenant_access

        if not verify_tenant_access("acct-123"):
            raise PermissionError("Access denied: resource belongs to different tenant")
        ```
    """
    ctx = _tenant_context.get()
    if ctx is None:
        # No context means no access
        return False

    return ctx.can_access_resource(resource_account_id)


__all__ = [
    "TenantContext",
    "TenantMiddleware",
    "TenantContextManager",
    "get_tenant_context",
    "require_tenant_context",
    "verify_tenant_access",
    "_tenant_context",  # Export for testing
]
