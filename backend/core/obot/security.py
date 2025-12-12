"""Obot Security Middleware

User context validation middleware for Obot MCP Gateway that validates user context 
server-side and rejects requests with mismatched user identities.

Implements Requirement 8.3: WHEN making Obot API requests THEN the system SHALL 
validate user context server-side and reject requests with mismatched user identities
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set
from uuid import UUID
import logging
import ipaddress

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from core.services.supabase import DBConnection
from core.utils.auth_utils import _decode_jwt_with_verification
from .models import ObotUserMapping, ObotProfile
from .identity_service import ObotIdentityService
from .audit import MCPAuditLog


logger = logging.getLogger(__name__)

# Security exception classes
class SecurityError(Exception):
    """Base security exception"""
    pass


class AuthenticationError(SecurityError):
    """Raised when authentication fails (401)"""
    def __init__(self, message: str = "Authentication required"):
        self.message = message
        super().__init__(message)


class AuthorizationError(SecurityError):
    """Raised when user lacks required permissions (403)"""
    def __init__(self, message: str = "Insufficient permissions"):
        self.message = message
        super().__init__(message)


class ResourceOwnershipError(SecurityError):
    """Raised when user attempts to access resources they don't own (403)"""
    def __init__(self, message: str = "Resource access denied"):
        self.message = message
        super().__init__(message)


# Security configuration
class SecurityConfig:
    """Configuration for Obot security middleware"""
    
    def __init__(self):
        # JWT validation settings
        self.jwt_secret = os.getenv("OBOT_JWT_SECRET", "default-secret-change-in-production")
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = int(os.getenv("OBOT_JWT_EXPIRE_MINUTES", "60"))
        
        # Security thresholds
        self.max_token_age_minutes = int(os.getenv("OBOT_MAX_TOKEN_AGE_MINUTES", "60"))
        self.require_user_mapping = os.getenv("OBOT_REQUIRE_USER_MAPPING", "true").lower() == "true"
        self.allow_admin_override = os.getenv("OBOT_ALLOW_ADMIN_OVERRIDE", "true").lower() == "true"
        
        # Admin role configuration
        self.admin_role_check = os.getenv("OBOT_ADMIN_ROLE_CHECK", "true").lower() == "true"
        self.admin_role_field = os.getenv("OBOT_ADMIN_ROLE_FIELD", "role")
        self.admin_role_values = set(os.getenv("OBOT_ADMIN_ROLE_VALUES", "admin,superuser").split(","))
        
        # Request context logging
        self.log_ip_addresses = os.getenv("OBOT_LOG_IP_ADDRESSES", "true").lower() == "true"
        self.log_user_agents = os.getenv("OBOT_LOG_USER_AGENTS", "true").lower() == "true"
        self.ip_masking_enabled = os.getenv("OBOT_IP_MASKING_ENABLED", "true").lower() == "true"
        
        # Rate limiting for security operations
        self.security_check_rate_limit = int(os.getenv("OBOT_SECURITY_CHECK_RATE_LIMIT", "100"))
        
        logger.debug(f"Loaded security config: JWT expire={self.jwt_expire_minutes}m, "
                    f"Admin check={self.admin_role_check}, IP logging={self.log_ip_addresses}")


# Global security configuration instance
_security_config = None


def get_security_config() -> SecurityConfig:
    """Get global security configuration instance"""
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig()
    return _security_config


# Security context models
class SecurityContext(BaseModel):
    """Security context extracted from request"""
    user_id: str = Field(description="Authenticated user ID")
    email: Optional[str] = Field(description="User email", default=None)
    role: Optional[str] = Field(description="User role", default=None)
    is_admin: bool = Field(description="Whether user has admin privileges", default=False)
    ip_address: Optional[str] = Field(description="Client IP address", default=None)
    user_agent: Optional[str] = Field(description="Client user agent", default=None)
    token_issued_at: Optional[datetime] = Field(description="Token issuance time", default=None)
    request_id: str = Field(description="Unique request identifier", default_factory=lambda: str(UUID()))


class RequestContext(BaseModel):
    """Request context for security logging"""
    ip_address: Optional[str]
    user_agent: Optional[str]
    method: str
    path: str
    timestamp: datetime


# Security middleware class
class ObotSecurityMiddleware:
    """Security middleware for Obot MCP Gateway"""
    
    def __init__(
        self,
        db_connection: Optional[DBConnection] = None,
        identity_service: Optional[ObotIdentityService] = None,
        audit_log: Optional[MCPAuditLog] = None
    ):
        """Initialize security middleware
        
        Args:
            db_connection: Database connection for user verification
            identity_service: Identity service for user mapping verification
            audit_log: Audit log service for security events
        """
        self.db = db_connection or DBConnection()
        self.identity_service = identity_service
        self.audit_log = audit_log or MCPAuditLog(self.db)
        self.config = get_security_config()
        
        # Initialize HTTP bearer scheme for token extraction
        self.bearer_scheme = HTTPBearer()
        
        logger.info("Initialized ObotSecurityMiddleware")
    
    def _sanitize_ip_address(self, ip_address: Optional[str]) -> Optional[str]:
        """Sanitize IP address for privacy compliance"""
        if not ip_address or not self.config.log_ip_addresses:
            return None
            
        try:
            ip = ipaddress.ip_address(ip_address.strip())
            if self.config.ip_masking_enabled:
                if ip.version == 4:
                    parts = str(ip).split('.')
                    if len(parts) == 4:
                        return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
                else:
                    return f"{str(ip)[:19]}::"
            return str(ip)
        except Exception:
            return None
    
    def _sanitize_user_agent(self, user_agent: Optional[str]) -> Optional[str]:
        """Sanitize user agent for privacy compliance"""
        if not user_agent or not self.config.log_user_agents:
            return None
        return user_agent.strip()[:500]  # Limit length
    
    def _extract_request_context(self, request: Request) -> RequestContext:
        """Extract and sanitize request context"""
        # Extract client IP with proxy support
        client_ip = None
        forwarded_for = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip
        else:
            client_ip = request.client.host if request.client else None
        
        return RequestContext(
            ip_address=self._sanitize_ip_address(client_ip),
            user_agent=self._sanitize_user_agent(request.headers.get("User-Agent")),
            method=request.method,
            path=request.url.path,
            timestamp=datetime.utcnow()
        )
    
    async def validate_user_context(
        self,
        request: Request,
        require_mapping: bool = True,
        require_admin: bool = False
    ) -> SecurityContext:
        """
        Validate user context from JWT token and request
        
        Args:
            request: FastAPI request object
            require_mapping: Whether user must have Obot mapping
            require_admin: Whether user must have admin privileges
            
        Returns:
            SecurityContext with validated user information
            
        Raises:
            AuthenticationError: If authentication fails
            AuthorizationError: If authorization fails
        """
        try:
            # Extract request context
            request_context = self._extract_request_context(request)
            
            # Extract and validate JWT token
            try:
                credentials = await self.bearer_scheme(request)
                token = credentials.credentials
            except Exception as e:
                raise AuthenticationError("Bearer token required")
            
            # Decode and verify JWT token
            try:
                payload = _decode_jwt_with_verification(token)
            except HTTPException as e:
                await self._log_security_event(
                    "jwt_validation_failed",
                    None,
                    request_context,
                    success=False,
                    details={"error": str(e.detail)}
                )
                raise AuthenticationError("Invalid or expired token")
            
            # Extract user information from token
            user_id = self._extract_user_id_from_token(payload)
            if not user_id:
                raise AuthenticationError("User ID not found in token")
            
            email = payload.get("email")
            role = payload.get(self.config.admin_role_field)
            is_admin = self._check_admin_role(role)
            
            # Validate token age
            if self.config.max_token_age_minutes > 0:
                self._validate_token_age(payload)
            
            # Create security context
            context = SecurityContext(
                user_id=user_id,
                email=email,
                role=role,
                is_admin=is_admin,
                ip_address=request_context.ip_address,
                user_agent=request_context.user_agent,
                token_issued_at=self._extract_token_issued_at(payload)
            )
            
            # Check if user mapping is required and validate
            if require_mapping and self.config.require_user_mapping:
                await self._validate_user_mapping(context)
            
            # Check admin requirement
            if require_admin and not (is_admin or self.config.allow_admin_override):
                await self._log_security_event(
                    "admin_access_denied",
                    user_id,
                    request_context,
                    success=False
                )
                raise AuthorizationError("Admin privileges required")
            
            # Log successful validation
            await self._log_security_event(
                "user_context_validated",
                user_id,
                request_context,
                success=True
            )
            
            logger.debug(f"User context validated for user {user_id[:8]}... (admin: {is_admin})")
            return context
            
        except (AuthenticationError, AuthorizationError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error in user context validation: {e}", exc_info=True)
            await self._log_security_event(
                "validation_error",
                None,
                self._extract_request_context(request),
                success=False,
                details={"error": str(e)}
            )
            raise AuthenticationError("Authentication system error")
    
    def _extract_user_id_from_token(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract user ID from JWT payload"""
        # Try common JWT claims for user ID
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
        
        # Validate UUID format
        if user_id:
            try:
                UUID(user_id)
                return user_id
            except ValueError:
                logger.warning(f"Invalid user ID format in token: {user_id}")
        
        return None
    
    def _check_admin_role(self, role: Optional[str]) -> bool:
        """Check if user role indicates admin privileges"""
        if not role:
            return False
        
        if not self.config.admin_role_check:
            return False
        
        return role.lower() in self.config.admin_role_values
    
    def _validate_token_age(self, payload: Dict[str, Any]) -> None:
        """Validate that token is not too old"""
        if "iat" in payload:
            issued_at = datetime.fromtimestamp(payload["iat"])
            age_minutes = (datetime.utcnow() - issued_at).total_seconds() / 60
            
            if age_minutes > self.config.max_token_age_minutes:
                raise AuthenticationError("Token too old")
    
    def _extract_token_issued_at(self, payload: Dict[str, Any]) -> Optional[datetime]:
        """Extract token issuance time from payload"""
        if "iat" in payload:
            return datetime.fromtimestamp(payload["iat"])
        return None
    
    async def _validate_user_mapping(self, context: SecurityContext) -> None:
        """Validate that user has a valid Obot user mapping"""
        if not self.identity_service:
            logger.warning("Identity service not available for mapping validation")
            return
        
        try:
            # Check if user mapping exists
            mapping = await self.identity_service.get_obot_user_mapping(context.user_id)
            if not mapping:
                await self._log_security_event(
                    "missing_user_mapping",
                    context.user_id,
                    RequestContext(
                        ip_address=context.ip_address,
                        user_agent=context.user_agent,
                        method="N/A",
                        path="mapping_validation",
                        timestamp=datetime.utcnow()
                    ),
                    success=False
                )
                raise AuthorizationError("User mapping not found")
            
            # Check if mapping is active (not disabled)
            if hasattr(mapping, 'disabled') and mapping.disabled:
                raise AuthorizationError("User mapping disabled")
            
        except Exception as e:
            if isinstance(e, AuthorizationError):
                raise
            logger.error(f"Error validating user mapping for {context.user_id}: {e}")
            raise AuthorizationError("User mapping validation failed")
    
    async def validate_resource_ownership(
        self,
        context: SecurityContext,
        resource_type: str,
        resource_id: str,
        owner_field: str = "account_id"
    ) -> bool:
        """
        Validate resource ownership to prevent cross-tenant access
        
        Args:
            context: Security context of authenticated user
            resource_type: Type of resource (profile, server, etc.)
            resource_id: ID of resource to check
            owner_field: Database field that contains owner ID
            
        Returns:
            bool: True if user owns the resource
            
        Raises:
            ResourceOwnershipError: If user doesn't own the resource
        """
        try:
            if resource_type == "profile":
                return await self._validate_profile_ownership(context, resource_id)
            elif resource_type == "server":
                return await self._validate_server_ownership(context, resource_id)
            else:
                raise ValueError(f"Unknown resource type: {resource_type}")
                
        except ResourceOwnershipError:
            raise
        except Exception as e:
            logger.error(f"Error validating resource ownership: {e}")
            raise ResourceOwnershipError("Resource ownership validation failed")
    
    async def _validate_profile_ownership(self, context: SecurityContext, profile_id: str) -> bool:
        """Validate that user owns the specified profile"""
        try:
            client = await self.db.client
            result = await client.table('obot_profiles').select(owner_field).eq('id', profile_id).execute()
            
            if not result.data:
                raise ResourceOwnershipError("Profile not found")
            
            owner_id = result.data[0][owner_field]
            
            if owner_id != context.user_id:
                await self._log_security_event(
                    "profile_access_denied",
                    context.user_id,
                    RequestContext(
                        ip_address=context.ip_address,
                        user_agent=context.user_agent,
                        method="N/A",
                        path=f"profile/{profile_id}",
                        timestamp=datetime.utcnow()
                    ),
                    success=False,
                    details={"profile_id": profile_id, "owner_id": owner_id}
                )
                raise ResourceOwnershipError("Profile access denied")
            
            return True
            
        except ResourceOwnershipError:
            raise
        except Exception as e:
            logger.error(f"Error validating profile ownership: {e}")
            raise ResourceOwnershipError("Profile ownership validation failed")
    
    async def _validate_server_ownership(self, context: SecurityContext, server_id: str) -> bool:
        """Validate that user owns the specified MCP server"""
        # For server ownership, we check through the profile that references the server
        try:
            client = await self.db.client
            result = await client.table('obot_profiles').select('account_id').eq('obot_server_id', server_id).execute()
            
            if not result.data:
                raise ResourceOwnershipError("Server not found")
            
            # Check if user owns any profile that references this server
            for profile in result.data:
                if profile['account_id'] == context.user_id:
                    return True
            
            # If we get here, user doesn't own this server
            await self._log_security_event(
                "server_access_denied",
                context.user_id,
                RequestContext(
                    ip_address=context.ip_address,
                    user_agent=context.user_agent,
                    method="N/A",
                    path=f"server/{server_id}",
                    timestamp=datetime.utcnow()
                ),
                success=False,
                details={"server_id": server_id, "profiles_found": len(result.data)}
            )
            raise ResourceOwnershipError("Server access denied")
            
        except ResourceOwnershipError:
            raise
        except Exception as e:
            logger.error(f"Error validating server ownership: {e}")
            raise ResourceOwnershipError("Server ownership validation failed")
    
    async def _log_security_event(
        self,
        action: str,
        user_id: Optional[str],
        request_context: RequestContext,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log security events for audit trail"""
        try:
            await self.audit_log.record(
                action=action,
                user_id=user_id or "anonymous",
                success=success,
                server_id=details.get("server_id") if details else None,
                tool_name=details.get("tool_name") if details else None,
                error_message=details.get("error") if details else None,
                ip_address=request_context.ip_address,
                user_agent=request_context.user_agent
            )
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    async def check_security_health(self) -> Dict[str, Any]:
        """Check health of security middleware"""
        health_status = {
            "service": "obot_security_middleware",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "config": {
                "jwt_expire_minutes": self.config.jwt_expire_minutes,
                "max_token_age_minutes": self.config.max_token_age_minutes,
                "require_user_mapping": self.config.require_user_mapping,
                "allow_admin_override": self.config.allow_admin_override,
                "admin_role_check": self.config.admin_role_check,
                "log_ip_addresses": self.config.log_ip_addresses
            }
        }
        
        try:
            # Test database connectivity
            client = await self.db.client
            await client.table('obot_user_mappings').select('id').limit(1).execute()
            
            # Test identity service if available
            if self.identity_service:
                health_status["identity_service_available"] = True
            else:
                health_status["identity_service_available"] = False
            
            # Test audit log
            audit_health = await self.audit_log.check_health()
            health_status["audit_log_healthy"] = audit_health.get("status") == "healthy"
            
            logger.debug(f"Security middleware health check passed: {health_status}")
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
            logger.error(f"Security middleware health check failed: {e}")
        
        return health_status


# Dependency injection functions for FastAPI
async def get_security_context(
    request: Request,
    require_mapping: bool = True,
    require_admin: bool = False,
    middleware: Optional[ObotSecurityMiddleware] = None
) -> SecurityContext:
    """
    FastAPI dependency to get validated security context
    
    Args:
        request: FastAPI request
        require_mapping: Whether user must have Obot mapping
        require_admin: Whether user must have admin privileges
        middleware: Security middleware instance
        
    Returns:
        SecurityContext: Validated security context
        
    Raises:
        HTTPException: 401 for auth errors, 403 for permission errors
    """
    if middleware is None:
        middleware = ObotSecurityMiddleware()
    
    try:
        context = await middleware.validate_user_context(request, require_mapping, require_admin)
        return context
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=e.message)
    except AuthorizationError as e:
        raise HTTPException(status_code=403, detail=e.message)
    except Exception as e:
        logger.error(f"Security context validation failed: {e}")
        raise HTTPException(status_code=500, detail="Security validation failed")


async def require_admin_context(
    request: Request,
    middleware: Optional[ObotSecurityMiddleware] = None
) -> SecurityContext:
    """FastAPI dependency for admin-only endpoints"""
    return await get_security_context(request, require_mapping=True, require_admin=True, middleware=middleware)


async def get_optional_security_context(
    request: Request,
    middleware: Optional[ObotSecurityMiddleware] = None
) -> Optional[SecurityContext]:
    """
    FastAPI dependency for optional security context (user may be anonymous)
    
    Returns:
        SecurityContext if authenticated, None if anonymous
    """
    try:
        return await get_security_context(request, require_mapping=False, require_admin=False, middleware=middleware)
    except HTTPException:
        # Return None for anonymous users
        return None


# Resource ownership validation dependencies
async def require_profile_ownership(
    profile_id: str,
    context: SecurityContext = Depends(get_security_context),
    middleware: Optional[ObotSecurityMiddleware] = None
) -> SecurityContext:
    """
    FastAPI dependency to require ownership of a specific profile
    
    Args:
        profile_id: Profile ID from path parameter
        context: Security context from dependency
        middleware: Security middleware instance
        
    Returns:
        SecurityContext: The same context (for chaining)
        
    Raises:
        HTTPException: 403 if user doesn't own the profile
    """
    if middleware is None:
        middleware = ObotSecurityMiddleware()
    
    try:
        await middleware.validate_resource_ownership(context, "profile", profile_id)
        return context
    except ResourceOwnershipError as e:
        raise HTTPException(status_code=403, detail=e.message)


async def require_server_ownership(
    server_id: str,
    context: SecurityContext = Depends(get_security_context),
    middleware: Optional[ObotSecurityMiddleware] = None
) -> SecurityContext:
    """
    FastAPI dependency to require ownership of a specific server
    
    Args:
        server_id: Server ID from path parameter
        context: Security context from dependency
        middleware: Security middleware instance
        
    Returns:
        SecurityContext: The same context (for chaining)
        
    Raises:
        HTTPException: 403 if user doesn't own the server
    """
    if middleware is None:
        middleware = ObotSecurityMiddleware()
    
    try:
        await middleware.validate_resource_ownership(context, "server", server_id)
        return context
    except ResourceOwnershipError as e:
        raise HTTPException(status_code=403, detail=e.message)


# Utility functions for manual security checks
async def validate_user_context_manual(
    token: str,
    request_context: Optional[RequestContext] = None,
    middleware: Optional[ObotSecurityMiddleware] = None
) -> SecurityContext:
    """
    Manually validate user context without FastAPI request
    
    Args:
        token: JWT token string
        request_context: Optional request context
        middleware: Security middleware instance
        
    Returns:
        SecurityContext: Validated security context
        
    Raises:
        AuthenticationError: If authentication fails
    """
    if middleware is None:
        middleware = ObotSecurityMiddleware()
    
    # Create a mock request object for validation
    class MockRequest:
        def __init__(self, token: str, context: Optional[RequestContext]):
            self.headers = {"Authorization": f"Bearer {token}"}
            self.client = type('obj', (object,), {'host': context.ip_address if context else None})()
            self.url = type('obj', (object,), {'path': context.path if context else '/manual'})()
            self.method = context.method if context else "GET"
    
    mock_request = MockRequest(token, request_context)
    return await middleware.validate_user_context(mock_request)


async def validate_resource_ownership_manual(
    context: SecurityContext,
    resource_type: str,
    resource_id: str,
    middleware: Optional[ObotSecurityMiddleware] = None
) -> bool:
    """
    Manually validate resource ownership
    
    Args:
        context: Security context
        resource_type: Type of resource
        resource_id: Resource ID
        middleware: Security middleware instance
        
    Returns:
        bool: True if user owns the resource
        
    Raises:
        ResourceOwnershipError: If user doesn't own the resource
    """
    if middleware is None:
        middleware = ObotSecurityMiddleware()
    
    return await middleware.validate_resource_ownership(context, resource_type, resource_id)


# Global middleware instance
_middleware: Optional[ObotSecurityMiddleware] = None


async def get_security_middleware() -> ObotSecurityMiddleware:
    """Get global security middleware instance"""
    global _middleware
    if _middleware is None:
        _middleware = ObotSecurityMiddleware()
    return _middleware


# Health check function
async def check_security_health() -> Dict[str, Any]:
    """Check health of the security middleware service"""
    middleware = await get_security_middleware()
    return await middleware.check_security_health()


# Logging configuration
def setup_security_logging():
    """Setup security-specific logging configuration"""
    security_logger = logging.getLogger("obot.security")
    
    # Only add handler if none exists
    if not security_logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        security_logger.addHandler(handler)
        security_logger.setLevel(logging.INFO)


# Initialize logging on module import
setup_security_logging()
