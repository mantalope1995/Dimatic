"""
Tests for AgentCore API Key Management (Phase 7)

Tests cover:
- API key generation and validation
- Permission mapping
- Expiration handling
- Revocation tracking
"""

import pytest
from datetime import datetime, timedelta
from core.agentcore.security import (
    APIKey,
    APIKeyManager,
    APIKeyScope,
    Permission,
    PermissionSet,
)


class TestAPIKeyGeneration:
    """Test API key generation"""

    @pytest.mark.asyncio
    async def test_generate_basic_key(self):
        """Test basic API key generation"""
        account_id = "acct-123"
        scopes = [APIKeyScope.READ_ONLY]

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes
        )

        # Verify raw key format
        assert raw_key.startswith("ak_")
        assert len(raw_key) > 20  # Should be substantial length

        # Verify key object
        assert api_key.account_id == account_id
        assert api_key.scopes == [APIKeyScope.READ_ONLY]
        assert api_key.key_id == raw_key.split("_")[1]
        assert api_key.key_hash is not None
        assert isinstance(api_key.created_at, datetime)
        assert api_key.is_revoked is False

    @pytest.mark.asyncio
    async def test_generate_key_with_expiration(self):
        """Test API key with expiration"""
        account_id = "acct-123"
        scopes = [APIKeyScope.EXECUTE]
        expires_in_days = 365

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes,
            expires_in_days=expires_in_days
        )

        # Verify expiration
        assert api_key.expires_at is not None
        expected_expiry = datetime.utcnow() + timedelta(days=expires_in_days)
        # Allow 1 minute tolerance for test timing
        assert abs((api_key.expires_at - expected_expiry).total_seconds()) < 60

    @pytest.mark.asyncio
    async def test_generate_key_with_permissions(self):
        """Test API key with explicit permissions"""
        account_id = "acct-123"
        scopes = [APIKeyScope.EXECUTE]
        permissions = [Permission.RUNTIME_EXECUTE, Permission.MEMORY_WRITE]

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes,
            permissions=permissions
        )

        # Verify permissions
        assert Permission.RUNTIME_EXECUTE.value in api_key.permissions
        assert Permission.MEMORY_WRITE.value in api_key.permissions

    @pytest.mark.asyncio
    async def test_generate_key_with_metadata(self):
        """Test API key with metadata"""
        account_id = "acct-123"
        scopes = [APIKeyScope.ADMIN]
        metadata = {"description": "Test key", "created_by": "user-1"}

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes,
            metadata=metadata
        )

        # Verify metadata
        assert api_key.metadata == metadata


class TestAPIKeyValidation:
    """Test API key validation"""

    @pytest.mark.asyncio
    async def test_validate_raw_key(self):
        """Test raw key validation against hash"""
        account_id = "acct-123"
        scopes = [APIKeyScope.READ_ONLY]

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes
        )

        # Should validate correctly
        assert api_key.validate_raw_key(raw_key) is True

        # Wrong key should fail
        assert api_key.validate_raw_key("wrong_key") is False
        assert api_key.validate_raw_key("ak_wrong_hash_" + "x" * 64) is False

    @pytest.mark.asyncio
    async def test_key_expiration_check(self):
        """Test key expiration detection"""
        account_id = "acct-123"

        # Key that expires in 1 day
        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=[APIKeyScope.READ_ONLY],
            expires_in_days=1
        )
        assert api_key.is_expired() is False

        # Key that never expires
        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=[APIKeyScope.READ_ONLY],
            expires_in_days=None
        )
        assert api_key.is_expired() is False

    @pytest.mark.asyncio
    async def test_key_validity_check(self):
        """Test overall key validity"""
        account_id = "acct-123"

        # Valid key
        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=[APIKeyScope.READ_ONLY]
        )
        assert api_key.is_valid() is True

        # Revoked key
        api_key.is_revoked = True
        assert api_key.is_valid() is False

    @pytest.mark.asyncio
    async def test_permission_check(self):
        """Test permission checking"""
        account_id = "acct-123"
        scopes = [APIKeyScope.EXECUTE]  # Includes RUNTIME_EXECUTE

        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes
        )

        # Should have execute permissions
        assert api_key.has_permission(Permission.RUNTIME_EXECUTE) is True

        # Should not have admin permissions
        assert api_key.has_permission(Permission.ADMIN) is False


class TestAPIKeyScopes:
    """Test API key scope to permission mapping"""

    @pytest.mark.asyncio
    async def test_read_only_scope_permissions(self):
        """Test READ_ONLY scope maps to correct permissions"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.READ_ONLY]
        )

        # READ_ONLY should include read permissions
        assert api_key.has_permission(Permission.RUNTIME_READ) is True
        assert api_key.has_permission(Permission.MEMORY_READ) is True
        assert api_key.has_permission(Permission.GATEWAY_READ) is True

        # But not write/deploy permissions
        assert api_key.has_permission(Permission.RUNTIME_EXECUTE) is False
        assert api_key.has_permission(Permission.RUNTIME_DEPLOY) is False

    @pytest.mark.asyncio
    async def test_execute_scope_permissions(self):
        """Test EXECUTE scope maps to correct permissions"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.EXECUTE]
        )

        # EXECUTE should include execution permissions
        assert api_key.has_permission(Permission.RUNTIME_EXECUTE) is True
        assert api_key.has_permission(Permission.MEMORY_WRITE) is True
        assert api_key.has_permission(Permission.GATEWAY_INVOKE) is True

    @pytest.mark.asyncio
    async def test_deploy_scope_permissions(self):
        """Test DEPLOY scope maps to correct permissions"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.DEPLOY]
        )

        # DEPLOY should include deployment permissions
        assert api_key.has_permission(Permission.RUNTIME_DEPLOY) is True
        assert api_key.has_permission(Permission.MEMORY_CREATE) is True
        assert api_key.has_permission(Permission.GATEWAY_DEPLOY) is True

    @pytest.mark.asyncio
    async def test_admin_scope_permissions(self):
        """Test ADMIN scope maps to all permissions"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.ADMIN]
        )

        # ADMIN should include everything
        assert api_key.has_permission(Permission.RUNTIME_DEPLOY) is True
        assert api_key.has_permission(Permission.RUNTIME_EXECUTE) is True
        assert api_key.has_permission(Permission.ADMIN) is True
        assert api_key.has_permission(Permission.USER_MANAGE) is True


class TestAPIKeySerialization:
    """Test API key serialization"""

    @pytest.mark.asyncio
    async def test_to_dict(self):
        """Test serialization to dictionary"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.READ_ONLY],
            metadata={"description": "Test"}
        )

        data = api_key.to_dict()

        # Verify fields
        assert data["key_id"] == api_key.key_id
        assert data["key_hash"] == api_key.key_hash
        assert data["account_id"] == api_key.account_id
        assert data["scopes"] == [APIKeyScope.READ_ONLY]
        assert isinstance(data["created_at"], str)  # ISO string
        assert data["metadata"] == '{"description": "Test"}'  # JSON string
        # Raw key should never be in serialized data
        assert "raw_key" not in data

    @pytest.mark.asyncio
    async def test_from_dict(self):
        """Test deserialization from dictionary"""
        raw_key, api_key = APIKey.generate(
            account_id="acct-123",
            scopes=[APIKeyScope.READ_ONLY],
            expires_in_days=365,
            metadata={"description": "Test"}
        )

        # Serialize and deserialize
        data = api_key.to_dict()
        restored = APIKey.from_dict(data)

        # Verify restored object
        assert restored.key_id == api_key.key_id
        assert restored.key_hash == api_key.key_hash
        assert restored.account_id == api_key.account_id
        assert restored.scopes == api_key.scopes
        assert isinstance(restored.created_at, datetime)
        assert isinstance(restored.expires_at, datetime)
        assert restored.metadata == {"description": "Test"}


class TestPermissionSet:
    """Test PermissionSet utility class"""

    def test_get_permissions_for_role(self):
        """Test getting permissions for standard roles"""
        # Admin role
        admin_perms = PermissionSet.get_permissions_for_role("admin")
        assert Permission.ADMIN in admin_perms
        assert Permission.USER_MANAGE in admin_perms

        # Developer role
        dev_perms = PermissionSet.get_permissions_for_role("developer")
        assert Permission.RUNTIME_DEPLOY in dev_perms
        assert Permission.ADMIN not in dev_perms  # No admin

        # Viewer role
        viewer_perms = PermissionSet.get_permissions_for_role("viewer")
        assert Permission.RUNTIME_READ in viewer_perms
        assert Permission.RUNTIME_EXECUTE not in viewer_perms  # No execute

    def test_permissions_to_list(self):
        """Test converting permissions to list"""
        perms = {Permission.RUNTIME_READ, Permission.MEMORY_READ}
        perm_list = PermissionSet.permissions_to_list(perms)

        assert isinstance(perm_list, list)
        assert "runtime:read" in perm_list
        assert "memory:read" in perm_list

    def test_list_to_permissions(self):
        """Test converting list to permissions"""
        perm_list = ["runtime:read", "memory:read"]
        perms = PermissionSet.list_to_permissions(perm_list)

        assert Permission.RUNTIME_READ in perms
        assert Permission.MEMORY_READ in perms

    def test_validate_permissions(self):
        """Test permission validation"""
        # Valid permissions
        valid = PermissionSet.validate_permissions([
            "runtime:read",
            "memory:write"
        ])
        assert "runtime:read" in valid
        assert "memory:write" in valid

        # Invalid permissions filtered
        mixed = PermissionSet.validate_permissions([
            "runtime:read",
            "invalid:permission"
        ])
        assert "runtime:read" in mixed
        assert "invalid:permission" not in mixed

        # All invalid raises error
        with pytest.raises(ValueError):
            PermissionSet.validate_permissions([
                "completely:invalid",
                "also:not:real"
            ])
