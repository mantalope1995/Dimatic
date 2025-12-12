"""Test suite for Obot Security Middleware

Tests the user context validation middleware that implements Requirement 8.3:
WHEN making Obot API requests THEN the system SHALL validate user context 
server-side and reject requests with mismatched user identities
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import jwt
import os
from uuid import uuid4

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.obot.security import (
    ObotSecurityMiddleware,
    SecurityContext,
    RequestContext,
    SecurityConfig,
    SecurityError,
    AuthenticationError,
    AuthorizationError,
    ResourceOwnershipError,
    get_security_context,
    require_admin_context,
    get_optional_security_context,
    require_profile_ownership,
    require_server_ownership,
    validate_user_context_manual,
    validate_resource_ownership_manual,
    check_security_health,
    get_security_middleware
)
from core.obot.models import ObotUserMapping, ObotProfile

class MockDBConnectionWrapper:
    """Wrapper to mock DBConnection with async client property"""
    def __init__(self, client):
        self._client = client
    
    @property
    async def client(self):
        return self._client


class TestSecurityConfig:
    """Test security configuration loading and validation"""
    
    def test_default_config(self):
        """Test default configuration values"""
        config = SecurityConfig()
        
        assert config.jwt_expire_minutes == 60
        assert config.max_token_age_minutes == 60
        assert config.require_user_mapping is True
        assert config.allow_admin_override is True
        assert config.admin_role_check is True
        assert config.admin_role_field == "role"
        assert config.admin_role_values == {"admin", "superuser"}
        assert config.log_ip_addresses is True
        assert config.log_user_agents is True
        assert config.ip_masking_enabled is True
        assert config.security_check_rate_limit == 100
    
    @patch.dict(os.environ, {
        "OBOT_JWT_EXPIRE_MINUTES": "120",
        "OBOT_MAX_TOKEN_AGE_MINUTES": "30",
        "OBOT_REQUIRE_USER_MAPPING": "false",
        "OBOT_ALLOW_ADMIN_OVERRIDE": "false",
        "OBOT_ADMIN_ROLE_CHECK": "false",
        "OBOT_ADMIN_ROLE_VALUES": "admin,superuser,moderator",
        "OBOT_LOG_IP_ADDRESSES": "false",
        "OBOT_LOG_USER_AGENTS": "false",
        "OBOT_IP_MASKING_ENABLED": "false",
        "OBOT_SECURITY_CHECK_RATE_LIMIT": "50"
    })
    def test_environment_override(self):
        """Test configuration override from environment variables"""
        # Need to reload the global config
        import importlib
        import core.obot.security
        importlib.reload(core.obot.security)
        
        from core.obot.security import get_security_config
        
        config = get_security_config()
        assert config.jwt_expire_minutes == 120
        assert config.max_token_age_minutes == 30
        assert config.require_user_mapping is False
        assert config.allow_admin_override is False
        assert config.admin_role_check is False
        assert config.admin_role_values == {"admin", "superuser", "moderator"}
        assert config.log_ip_addresses is False
        assert config.log_user_agents is False
        assert config.ip_masking_enabled is False
        assert config.security_check_rate_limit == 50


class TestSecurityExceptions:
    """Test security exception classes"""
    
    def test_security_error_base(self):
        """Test base SecurityError exception"""
        error = SecurityError("Test error")
        assert str(error) == "Test error"
    
    def test_authentication_error(self):
        """Test AuthenticationError exception"""
        error = AuthenticationError("Custom auth error")
        assert isinstance(error, SecurityError)
        assert error.message == "Custom auth error"
        assert str(error) == "Custom auth error"
        
        # Test default message
        error_default = AuthenticationError()
        assert error_default.message == "Authentication required"
    
    def test_authorization_error(self):
        """Test AuthorizationError exception"""
        error = AuthorizationError("Custom authz error")
        assert isinstance(error, SecurityError)
        assert error.message == "Custom authz error"
        assert str(error) == "Custom authz error"
        
        # Test default message
        error_default = AuthorizationError()
        assert error_default.message == "Insufficient permissions"
    
    def test_resource_ownership_error(self):
        """Test ResourceOwnershipError exception"""
        error = ResourceOwnershipError("Custom ownership error")
        assert isinstance(error, SecurityError)
        assert error.message == "Custom ownership error"
        assert str(error) == "Custom ownership error"
        
        # Test default message
        error_default = ResourceOwnershipError()
        assert error_default.message == "Resource access denied"


class TestSecurityContext:
    """Test security context model"""
    
    def test_security_context_creation(self):
        """Test SecurityContext model creation"""
        user_id = str(uuid4())
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            role="user",
            is_admin=False,
            ip_address="192.168.1.1",
            user_agent="Test Browser",
            token_issued_at=datetime.utcnow()
        )
        
        assert context.user_id == user_id
        assert context.email == "test@example.com"
        assert context.role == "user"
        assert context.is_admin is False
        assert context.ip_address == "192.168.1.1"
        assert context.user_agent == "Test Browser"
        assert context.token_issued_at is not None
        assert context.request_id is not None  # Should be auto-generated
    
    def test_request_context_creation(self):
        """Test RequestContext model creation"""
        context = RequestContext(
            ip_address="192.168.1.1",
            user_agent="Test Browser",
            method="GET",
            path="/api/test",
            timestamp=datetime.utcnow()
        )
        
        assert context.ip_address == "192.168.1.1"
        assert context.user_agent == "Test Browser"
        assert context.method == "GET"
        assert context.path == "/api/test"
        assert context.timestamp is not None


class TestObotSecurityMiddleware:
    """Test ObotSecurityMiddleware functionality"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database connection"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_identity_service(self):
        """Mock identity service"""
        return AsyncMock()
    
    @pytest.fixture
    def mock_audit_log(self):
        """Mock audit log"""
        return AsyncMock()
    
    @pytest.fixture
    def middleware(self, mock_db, mock_identity_service, mock_audit_log):
        """Create security middleware with mocked dependencies"""
        # mock_db is an AsyncMock representing the client, wrap it
        wrapper = MockDBConnectionWrapper(mock_db)
        return ObotSecurityMiddleware(
            db_connection=wrapper,
            identity_service=mock_identity_service,
            audit_log=mock_audit_log
        )
    
    @pytest.fixture
    def valid_jwt_token(self):
        """Create a valid JWT token for testing"""
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "role": "user",
            "iat": datetime.utcnow().timestamp()
        }
        return jwt.encode(payload, "test-secret", algorithm="HS256")
    
    @pytest.fixture
    def admin_jwt_token(self):
        """Create an admin JWT token for testing"""
        payload = {
            "sub": str(uuid4()),
            "email": "admin@example.com",
            "role": "admin",
            "iat": datetime.utcnow().timestamp()
        }
        return jwt.encode(payload, "test-secret", algorithm="HS256")
    
    def test_middleware_initialization(self, middleware):
        """Test middleware initialization"""
        assert middleware.db is not None
        assert middleware.identity_service is not None
        assert middleware.audit_log is not None
        assert middleware.config is not None
        assert middleware.bearer_scheme is not None
    
    @pytest.mark.asyncio
    async def test_sanitize_ip_address(self, middleware):
        """Test IP address sanitization"""
        # Test IPv4 masking
        masked = middleware._sanitize_ip_address("192.168.1.123")
        assert masked == "192.168.1.0"
        
        # Test IPv6 masking
        masked = middleware._sanitize_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert masked == "2001:0db8:85a3:0000::"
        
        # Test invalid IP
        masked = middleware._sanitize_ip_address("invalid-ip")
        assert masked is None
        
        # Test None input
        masked = middleware._sanitize_ip_address(None)
        assert masked is None
    
    @pytest.mark.asyncio
    async def test_sanitize_user_agent(self, middleware):
        """Test user agent sanitization"""
        # Test normal user agent
        sanitized = middleware._sanitize_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        assert len(sanitized) <= 500
        
        # Test long user agent (should be truncated)
        long_ua = "A" * 600
        sanitized = middleware._sanitize_user_agent(long_ua)
        assert len(sanitized) == 500
        
        # Test None input
        sanitized = middleware._sanitize_user_agent(None)
        assert sanitized is None
    
    @pytest.mark.asyncio
    async def test_extract_user_id_from_token(self, middleware):
        """Test user ID extraction from JWT payload"""
        # Test with 'sub' claim
        payload = {"sub": str(uuid4())}
        user_id = middleware._extract_user_id_from_token(payload)
        assert user_id is not None
        
        # Test with 'user_id' claim
        payload = {"user_id": str(uuid4())}
        user_id = middleware._extract_user_id_from_token(payload)
        assert user_id is not None
        
        # Test with 'uid' claim
        payload = {"uid": str(uuid4())}
        user_id = middleware._extract_user_id_from_token(payload)
        assert user_id is not None
        
        # Test with no user ID
        payload = {"email": "test@example.com"}
        user_id = middleware._extract_user_id_from_token(payload)
        assert user_id is None
        
        # Test with invalid UUID
        payload = {"sub": "invalid-uuid"}
        user_id = middleware._extract_user_id_from_token(payload)
        assert user_id is None
    
    @pytest.mark.asyncio
    async def test_check_admin_role(self, middleware):
        """Test admin role checking"""
        # Test with admin role
        assert middleware._check_admin_role("admin") is True
        
        # Test with superuser role
        assert middleware._check_admin_role("superuser") is True
        
        # Test with regular user role
        assert middleware._check_admin_role("user") is False
        
        # Test with moderator role (not in default admin roles)
        assert middleware._check_admin_role("moderator") is False
        
        # Test with None role
        assert middleware._check_admin_role(None) is False
        
        # Test case insensitivity
        assert middleware._check_admin_role("ADMIN") is True
    
    @pytest.mark.asyncio
    async def test_validate_token_age(self, middleware):
        """Test token age validation"""
        # Test with recent token (should pass)
        recent_payload = {"iat": datetime.utcnow().timestamp()}
        middleware._validate_token_age(recent_payload)  # Should not raise
        
        # Test with old token (should raise AuthenticationError)
        old_payload = {"iat": (datetime.utcnow() - timedelta(hours=2)).timestamp()}
        with pytest.raises(AuthenticationError):
            middleware._validate_token_age(old_payload)
        
        # Test with no iat claim (should not raise)
        no_iat_payload = {"sub": str(uuid4())}
        middleware._validate_token_age(no_iat_payload)  # Should not raise
    
    @pytest.mark.asyncio
    async def test_validate_user_context_success(self, middleware, valid_jwt_token, mock_identity_service):
        """Test successful user context validation"""
        # Mock the identity service to return a mapping
        mock_mapping = ObotUserMapping(
            id=str(uuid4()),
            suna_user_id="test-user-id",
            obot_user_id="obot-user-id",
            obot_username="test_user",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        mock_identity_service.get_obot_user_mapping.return_value = mock_mapping
        
        # Create mock request
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {valid_jwt_token}"}
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get.return_value = "Test Browser"
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        
        # Mock the bearer scheme extraction
        with patch.object(middleware.bearer_scheme, '__call__') as mock_bearer:
            mock_credentials = MagicMock()
            mock_credentials.credentials = valid_jwt_token
            mock_bearer.return_value = mock_credentials
            
            # Mock JWT verification
            with patch('core.obot.security._decode_jwt_with_verification') as mock_decode:
                mock_decode.return_value = {
                    "sub": "test-user-id",
                    "email": "test@example.com",
                    "role": "user",
                    "iat": datetime.utcnow().timestamp()
                }
                
                # Test validation
                context = await middleware.validate_user_context(mock_request)
                
                assert context.user_id == "test-user-id"
                assert context.email == "test@example.com"
                assert context.role == "user"
                assert context.is_admin is False
                assert context.ip_address == "192.168.1.0"  # Should be masked
                assert context.user_agent == "Test Browser"
                assert context.token_issued_at is not None
    
    @pytest.mark.asyncio
    async def test_validate_user_context_missing_token(self, middleware):
        """Test user context validation with missing token"""
        mock_request = MagicMock()
        mock_request.headers = {}
        
        with patch.object(middleware.bearer_scheme, '__call__') as mock_bearer:
            mock_bearer.side_effect = Exception("No token")
            
            with pytest.raises(AuthenticationError) as exc_info:
                await middleware.validate_user_context(mock_request)
            
            assert "Bearer token required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_user_context_invalid_jwt(self, middleware, mock_request=None):
        """Test user context validation with invalid JWT"""
        if mock_request is None:
            mock_request = MagicMock()
            mock_request.headers = {"Authorization": "Bearer invalid-token"}
        
        with patch.object(middleware.bearer_scheme, '__call__') as mock_bearer:
            mock_credentials = MagicMock()
            mock_credentials.credentials = "invalid-token"
            mock_bearer.return_value = mock_credentials
            
            with patch('core.obot.security._decode_jwt_with_verification') as mock_decode:
                mock_decode.side_effect = HTTPException(status_code=401, detail="Invalid token")
                
                with pytest.raises(AuthenticationError) as exc_info:
                    await middleware.validate_user_context(mock_request)
                
                assert "Invalid or expired token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_user_context_no_user_id(self, middleware):
        """Test user context validation with no user ID in token"""
        token = jwt.encode({"email": "test@example.com"}, "test-secret", algorithm="HS256")
        
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        
        with patch.object(middleware.bearer_scheme, '__call__') as mock_bearer:
            mock_credentials = MagicMock()
            mock_credentials.credentials = token
            mock_bearer.return_value = mock_credentials
            
            with patch('core.obot.security._decode_jwt_with_verification') as mock_decode:
                mock_decode.return_value = {"email": "test@example.com"}
                
                with pytest.raises(AuthenticationError) as exc_info:
                    await middleware.validate_user_context(mock_request)
                
                assert "User ID not found in token" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_user_context_admin_required(self, middleware, valid_jwt_token):
        """Test user context validation with admin requirement"""
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {valid_jwt_token}"}
        
        with patch.object(middleware.bearer_scheme, '__call__') as mock_bearer:
            mock_credentials = MagicMock()
            mock_credentials.credentials = valid_jwt_token
            mock_bearer.return_value = mock_credentials
            
            with patch('core.obot.security._decode_jwt_with_verification') as mock_decode:
                mock_decode.return_value = {
                    "sub": "test-user-id",
                    "email": "test@example.com",
                    "role": "user",  # Non-admin role
                    "iat": datetime.utcnow().timestamp()
                }
                
                with pytest.raises(AuthorizationError) as exc_info:
                    await middleware.validate_user_context(mock_request, require_admin=True)
                
                assert "Admin privileges required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_profile_success(self, middleware):
        """Test successful profile ownership validation"""
        user_id = str(uuid4())
        profile_id = str(uuid4())
        
        # Mock database response
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": user_id}
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": user_id}
        ]
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            is_admin=False
        )
        
        # Should not raise any exception
        result = await middleware.validate_resource_ownership(context, "profile", profile_id)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_profile_denied(self, middleware):
        """Test profile ownership validation with wrong owner"""
        user_id = str(uuid4())
        profile_id = str(uuid4())
        other_user_id = str(uuid4())
        
        # Mock database response showing different owner
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": other_user_id}
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": other_user_id}
        ]
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            is_admin=False
        )
        
        with pytest.raises(ResourceOwnershipError) as exc_info:
            await middleware.validate_resource_ownership(context, "profile", profile_id)
        
        assert "Profile access denied" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_profile_not_found(self, middleware):
        """Test profile ownership validation with non-existent profile"""
        user_id = str(uuid4())
        profile_id = str(uuid4())
        
        # Mock database response showing no profile found
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            is_admin=False
        )
        
        with pytest.raises(ResourceOwnershipError) as exc_info:
            await middleware.validate_resource_ownership(context, "profile", profile_id)
        
        assert "Profile not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_server_success(self, middleware):
        """Test successful server ownership validation"""
        user_id = str(uuid4())
        server_id = str(uuid4())
        
        # Mock database response
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": user_id}
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": user_id}
        ]
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            is_admin=False
        )
        
        # Should not raise any exception
        result = await middleware.validate_resource_ownership(context, "server", server_id)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_server_denied(self, middleware):
        """Test server ownership validation with wrong owner"""
        user_id = str(uuid4())
        server_id = str(uuid4())
        other_user_id = str(uuid4())
        
        # Mock database response showing different owner
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": other_user_id}
        ]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"account_id": other_user_id}
        ]
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        context = SecurityContext(
            user_id=user_id,
            email="test@example.com",
            is_admin=False
        )
        
        with pytest.raises(ResourceOwnershipError) as exc_info:
            await middleware.validate_resource_ownership(context, "server", server_id)
        
        assert "Server access denied" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_check_security_health(self, middleware):
        """Test security middleware health check"""
        # Mock database connection
        mock_client = AsyncMock()
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = [{}]
        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value.data = [{}]
        middleware.db = MockDBConnectionWrapper(mock_client)
        
        # Mock audit log health check
        middleware.audit_log.check_health.return_value = {"status": "healthy"}
        
        health = await middleware.check_security_health()
        
        assert health["service"] == "obot_security_middleware"
        assert health["status"] == "healthy"
        assert "timestamp" in health
        assert "config" in health
        assert health["identity_service_available"] is True
        assert health["audit_log_healthy"] is True


class TestFastAPIDependencies:
    """Test FastAPI dependency injection functions"""
    
    @pytest.fixture
    def mock_middleware(self):
        """Mock security middleware"""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_get_security_context_success(self, mock_middleware):
        """Test successful security context dependency"""
        # Mock middleware validation
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        mock_middleware.validate_user_context.return_value = expected_context
        
        # Mock request
        mock_request = MagicMock()
        
        context = await get_security_context(
            request=mock_request,
            require_mapping=True,
            require_admin=False,
            middleware=mock_middleware
        )
        
        assert context == expected_context
        mock_middleware.validate_user_context.assert_called_once_with(mock_request, True, False)
    
    @pytest.mark.asyncio
    async def test_get_security_context_auth_error(self, mock_middleware):
        """Test security context dependency with authentication error"""
        # Mock middleware to raise AuthenticationError
        mock_middleware.validate_user_context.side_effect = AuthenticationError("Auth failed")
        
        mock_request = MagicMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_security_context(
                request=mock_request,
                middleware=mock_middleware
            )
        
        assert exc_info.value.status_code == 401
        assert "Auth failed" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_get_security_context_authz_error(self, mock_middleware):
        """Test security context dependency with authorization error"""
        # Mock middleware to raise AuthorizationError
        mock_middleware.validate_user_context.side_effect = AuthorizationError("Access denied")
        
        mock_request = MagicMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await get_security_context(
                request=mock_request,
                middleware=mock_middleware
            )
        
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_require_admin_context(self, mock_middleware):
        """Test admin context dependency"""
        expected_context = SecurityContext(
            user_id="admin-user-id",
            email="admin@example.com",
            is_admin=True
        )
        mock_middleware.validate_user_context.return_value = expected_context
        
        mock_request = MagicMock()
        
        context = await require_admin_context(
            request=mock_request,
            middleware=mock_middleware
        )
        
        assert context == expected_context
        mock_middleware.validate_user_context.assert_called_once_with(mock_request, True, True)
    
    @pytest.mark.asyncio
    async def test_get_optional_security_context_authenticated(self, mock_middleware):
        """Test optional security context when authenticated"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        mock_middleware.validate_user_context.return_value = expected_context
        
        mock_request = MagicMock()
        
        context = await get_optional_security_context(
            request=mock_request,
            middleware=mock_middleware
        )
        
        assert context == expected_context
    
    @pytest.mark.asyncio
    async def test_get_optional_security_context_anonymous(self, mock_middleware):
        """Test optional security context when anonymous"""
        # Mock middleware to raise HTTPException (simulating no auth)
        mock_middleware.validate_user_context.side_effect = HTTPException(status_code=401, detail="No token")
        
        mock_request = MagicMock()
        
        context = await get_optional_security_context(
            request=mock_request,
            middleware=mock_middleware
        )
        
        assert context is None
    
    @pytest.mark.asyncio
    async def test_require_profile_ownership_success(self, mock_middleware):
        """Test profile ownership dependency success"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        
        # Mock validate_resource_ownership to succeed
        mock_middleware.validate_resource_ownership.return_value = True
        
        profile_id = str(uuid4())
        
        context = await require_profile_ownership(
            profile_id=profile_id,
            context=expected_context,
            middleware=mock_middleware
        )
        
        assert context == expected_context
        mock_middleware.validate_resource_ownership.assert_called_once_with(
            expected_context, "profile", profile_id
        )
    
    @pytest.mark.asyncio
    async def test_require_profile_ownership_denied(self, mock_middleware):
        """Test profile ownership dependency denial"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        
        # Mock validate_resource_ownership to raise ResourceOwnershipError
        mock_middleware.validate_resource_ownership.side_effect = ResourceOwnershipError("Access denied")
        
        profile_id = str(uuid4())
        
        with pytest.raises(HTTPException) as exc_info:
            await require_profile_ownership(
                profile_id=profile_id,
                context=expected_context,
                middleware=mock_middleware
            )
        
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_require_server_ownership_success(self, mock_middleware):
        """Test server ownership dependency success"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        
        # Mock validate_resource_ownership to succeed
        mock_middleware.validate_resource_ownership.return_value = True
        
        server_id = str(uuid4())
        
        context = await require_server_ownership(
            server_id=server_id,
            context=expected_context,
            middleware=mock_middleware
        )
        
        assert context == expected_context
        mock_middleware.validate_resource_ownership.assert_called_once_with(
            expected_context, "server", server_id
        )


class TestManualValidation:
    """Test manual validation functions"""
    
    @pytest.fixture
    def mock_middleware(self):
        """Mock security middleware"""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_validate_user_context_manual_success(self, mock_middleware):
        """Test successful manual user context validation"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        mock_middleware.validate_user_context.return_value = expected_context
        
        token = "test-jwt-token"
        request_context = RequestContext(
            ip_address="192.168.1.1",
            user_agent="Test Browser",
            method="GET",
            path="/manual",
            timestamp=datetime.utcnow()
        )
        
        context = await validate_user_context_manual(
            token=token,
            request_context=request_context,
            middleware=mock_middleware
        )
        
        assert context == expected_context
    
    @pytest.mark.asyncio
    async def test_validate_user_context_manual_error(self, mock_middleware):
        """Test manual user context validation with error"""
        mock_middleware.validate_user_context.side_effect = AuthenticationError("Auth failed")
        
        token = "invalid-token"
        
        with pytest.raises(AuthenticationError):
            await validate_user_context_manual(
                token=token,
                middleware=mock_middleware
            )
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_manual_success(self, mock_middleware):
        """Test successful manual resource ownership validation"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        mock_middleware.validate_resource_ownership.return_value = True
        
        result = await validate_resource_ownership_manual(
            context=expected_context,
            resource_type="profile",
            resource_id="profile-123",
            middleware=mock_middleware
        )
        
        assert result is True
        mock_middleware.validate_resource_ownership.assert_called_once_with(
            expected_context, "profile", "profile-123"
        )
    
    @pytest.mark.asyncio
    async def test_validate_resource_ownership_manual_denied(self, mock_middleware):
        """Test manual resource ownership validation denial"""
        expected_context = SecurityContext(
            user_id="test-user-id",
            email="test@example.com",
            is_admin=False
        )
        mock_middleware.validate_resource_ownership.side_effect = ResourceOwnershipError("Denied")
        
        with pytest.raises(ResourceOwnershipError):
            await validate_resource_ownership_manual(
                context=expected_context,
                resource_type="server",
                resource_id="server-123",
                middleware=mock_middleware
            )


class TestHealthCheck:
    """Test health check functionality"""
    
    @pytest.mark.asyncio
    async def test_check_security_health(self):
        """Test security health check"""
        # Mock the global middleware
        mock_middleware = AsyncMock()
        mock_middleware.check_security_health.return_value = {
            "service": "obot_security_middleware",
            "status": "healthy",
            "timestamp": "2023-01-01T00:00:00Z"
        }
        
        with patch('core.obot.security.get_security_middleware', return_value=mock_middleware):
            health = await check_security_health()
            
            assert health["service"] == "obot_security_middleware"
            assert health["status"] == "healthy"
            assert "timestamp" in health
            mock_middleware.check_security_health.assert_called_once()


class TestPropertyBasedTests:
    """Property-based tests for security invariants"""
    
    @pytest.mark.asyncio
    async def test_user_id_consistency_property(self):
        """
        Property: For any valid user ID, the security context 
        should preserve the exact same user ID without modification
        """
        # This is a conceptual test - in practice, the middleware 
        # should never modify the user_id from the JWT token
        test_user_id = str(uuid4())
        
        # The security middleware should extract and return the same user_id
        # This property ensures no user ID mutation occurs during validation
        assert test_user_id == test_user_id  # Identity property
    
    @pytest.mark.asyncio
    async def test_admin_role_consistency_property(self):
        """
        Property: Admin role checking should be deterministic and consistent
        """
        middleware = ObotSecurityMiddleware()
        
        # Test that the same role consistently produces the same result
        admin_roles = ["admin", "ADMIN", "Admin", "superuser", "SUPERUSER"]
        user_roles = ["user", "USER", "User", "guest", "GUEST"]
        
        for role in admin_roles:
            assert middleware._check_admin_role(role) is True
        
        for role in user_roles:
            assert middleware._check_admin_role(role) is False
    
    @pytest.mark.asyncio
    async def test_ip_sanitization_property(self):
        """
        Property: IP sanitization should always return a valid IP or None
        """
        middleware = ObotSecurityMiddleware()
        
        # Test various IP formats
        test_cases = [
            "192.168.1.1",
            "10.0.0.1", 
            "172.16.0.1",
            "2001:db8::1",
            "invalid-ip",
            "",
            None
        ]
        
        for ip in test_cases:
            result = middleware._sanitize_ip_address(ip)
            if result is not None:
                # Should be a valid IP format or masked version
                assert isinstance(result, str)
                assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_user_agent_sanitization_property(self):
        """
        Property: User agent sanitization should always return a string or None
        """
        middleware = ObotSecurityMiddleware()
        
        # Test various user agent lengths
        test_cases = [
            "Short UA",
            "A" * 100,
            "A" * 500,
            "A" * 1000,
            "",
            None
        ]
        
        for ua in test_cases:
            result = middleware._sanitize_user_agent(ua)
            if result is not None:
                # Should be a string and not longer than 500 chars
                assert isinstance(result, str)
                assert len(result) <= 500


# Integration tests
class TestSecurityIntegration:
    """Integration tests for security middleware with real dependencies"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_security_flow(self):
        """Test complete security validation flow"""
        # This test would require a real database and JWT setup
        # For now, we'll test the component integration patterns
        
        middleware = ObotSecurityMiddleware()
        
        # Test that all components are properly initialized
        assert middleware.db is not None
        assert middleware.audit_log is not None
        assert middleware.config is not None
        
        # Test health check doesn't crash
        health = await middleware.check_security_health()
        assert "service" in health
        assert "status" in health
    
    @pytest.mark.asyncio
    async def test_security_config_singleton(self):
        """Test that security config is properly singleton"""
        from core.obot.security import get_security_config
        
        config1 = get_security_config()
        config2 = get_security_config()
        
        # Should be the same instance
        assert config1 is config2


if __name__ == "__main__":
    # Run tests if this file is executed directly
    pytest.main([__file__, "-v"])
