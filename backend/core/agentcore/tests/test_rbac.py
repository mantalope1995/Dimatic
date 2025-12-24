"""
Tests for AgentCore RBAC System (Phase 7)

Tests cover:
- Role assignment and revocation
- Permission checking
- Role-based access control
"""

import pytest
from datetime import datetime
from core.agentcore.security import (
    Role,
    RoleAssignment,
    RoleManager,
    Permission,
    PermissionSet,
)


class TestRoleAssignment:
    """Test RoleAssignment dataclass"""

    def test_create_role_assignment(self):
        """Test creating a role assignment"""
        assignment = RoleAssignment(
            user_id="user-1",
            account_id="acct-1",
            role=Role.ADMIN,
            granted_by="admin-user"
        )

        assert assignment.user_id == "user-1"
        assert assignment.account_id == "acct-1"
        assert assignment.role == Role.ADMIN
        assert assignment.granted_by == "admin-user"
        assert isinstance(assignment.granted_at, datetime)
        assert assignment.metadata == {}

    def test_create_role_assignment_with_metadata(self):
        """Test creating a role assignment with metadata"""
        metadata = {"reason": "Project lead"}
        assignment = RoleAssignment(
            user_id="user-1",
            account_id="acct-1",
            role=Role.DEVELOPER,
            granted_by="admin-user",
            metadata=metadata
        )

        assert assignment.metadata == metadata

    def test_role_assignment_serialization(self):
        """Test RoleAssignment to_dict and from_dict"""
        assignment = RoleAssignment(
            user_id="user-1",
            account_id="acct-1",
            role=Role.VIEWER,
            granted_by="admin-user"
        )

        # Serialize
        data = assignment.to_dict()
        assert data["user_id"] == "user-1"
        assert data["account_id"] == "acct-1"
        assert data["role"] == "viewer"
        assert isinstance(data["granted_at"], str)

        # Deserialize
        restored = RoleAssignment.from_dict(data)
        assert restored.user_id == assignment.user_id
        assert restored.account_id == assignment.account_id
        assert restored.role == assignment.role
        assert isinstance(restored.granted_at, datetime)


class TestRoleManager:
    """Test RoleManager class"""

    def test_role_permissions_mapping(self):
        """Test role to permissions mapping"""
        # Admin has all permissions
        admin_perms = RoleManager.get_permissions_for_role(Role.ADMIN)
        assert Permission.ADMIN in admin_perms
        assert Permission.USER_MANAGE in admin_perms
        assert Permission.RUNTIME_DEPLOY in admin_perms

        # Developer has deploy/execute but not admin
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)
        assert Permission.RUNTIME_DEPLOY in dev_perms
        assert Permission.RUNTIME_EXECUTE in dev_perms
        assert Permission.ADMIN not in dev_perms
        assert Permission.USER_MANAGE not in dev_perms

        # Viewer has read-only
        viewer_perms = RoleManager.get_permissions_for_role(Role.VIEWER)
        assert Permission.RUNTIME_READ in viewer_perms
        assert Permission.RUNTIME_DEPLOY not in viewer_perms
        assert Permission.RUNTIME_EXECUTE not in viewer_perms

    def test_get_default_role(self):
        """Test getting default role"""
        default = RoleManager.get_default_role()
        assert default == Role.VIEWER

    def test_check_permission_single_role(self):
        """Test permission check with single role"""
        # Create a mock role manager (without DynamoDB)
        manager = RoleManager()

        # Admin has admin permission
        admin_perms = manager.ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.ADMIN in admin_perms
        assert Permission.USER_MANAGE in admin_perms

        # Developer doesn't have admin permission
        dev_perms = manager.ROLE_PERMISSIONS[Role.DEVELOPER]
        assert Permission.ADMIN not in dev_perms

        # Viewer only has read
        viewer_perms = manager.ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.RUNTIME_READ in viewer_perms
        assert Permission.RUNTIME_EXECUTE not in viewer_perms

    def test_check_permission_multiple_roles(self):
        """Test permission check with multiple roles"""
        # User with both developer and viewer roles
        # Should have union of permissions
        dev_perms = RoleManager.ROLE_PERMISSIONS[Role.DEVELOPER]
        viewer_perms = RoleManager.ROLE_PERMISSIONS[Role.VIEWER]

        # Combine permissions (simulating multiple roles)
        combined = dev_perms | viewer_perms

        # Should have both deploy (developer) and read (viewer)
        assert Permission.RUNTIME_DEPLOY in combined
        assert Permission.RUNTIME_READ in combined

    @pytest.mark.asyncio
    async def test_has_all_permissions(self):
        """Test checking if user has all required permissions"""
        # Manager class method for checking permissions
        admin_perms = RoleManager.get_permissions_for_role(Role.ADMIN)

        # Admin has all these permissions
        required = {Permission.ADMIN, Permission.USER_MANAGE, Permission.RUNTIME_DEPLOY}
        assert required.issubset(admin_perms)

        # Developer doesn't have admin
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)
        assert not required.issubset(dev_perms)

    @pytest.mark.asyncio
    async def test_has_any_permission(self):
        """Test checking if user has any of multiple permissions"""
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)

        # Developer has at least one of these
        required = {Permission.RUNTIME_DEPLOY, Permission.ADMIN}
        assert any(perm in dev_perms for perm in required)

        # Viewer doesn't have either
        viewer_perms = RoleManager.get_permissions_for_role(Role.VIEWER)
        assert not any(perm in viewer_perms for perm in required)


class TestRolePermissions:
    """Test role permission sets"""

    def test_admin_has_all_permissions(self):
        """Test ADMIN role has all permissions"""
        admin_perms = PermissionSet.ADMIN_ALL

        # Should have all permission categories
        assert Permission.RUNTIME_DEPLOY in admin_perms
        assert Permission.RUNTIME_EXECUTE in admin_perms
        assert Permission.MEMORY_CREATE in admin_perms
        assert Permission.GATEWAY_DEPLOY in admin_perms
        assert Permission.CODE_INTERPRETER_EXECUTE in admin_perms
        assert Permission.BROWSER_EXECUTE in admin_perms
        assert Permission.ADMIN in admin_perms
        assert Permission.USER_MANAGE in admin_perms

    def test_developer_permissions(self):
        """Test DEVELOPER role permissions"""
        dev_perms = PermissionSet.DEVELOPER

        # Can deploy and execute
        assert Permission.RUNTIME_DEPLOY in dev_perms
        assert Permission.RUNTIME_EXECUTE in dev_perms
        assert Permission.MEMORY_CREATE in dev_perms
        assert Permission.GATEWAY_DEPLOY in dev_perms

        # But not admin functions
        assert Permission.ADMIN not in dev_perms
        assert Permission.USER_MANAGE not in dev_perms

    def test_viewer_permissions(self):
        """Test VIEWER role permissions"""
        viewer_perms = PermissionSet.VIEWER

        # Only read permissions
        assert Permission.RUNTIME_READ in viewer_perms
        assert Permission.MEMORY_READ in viewer_perms
        assert Permission.GATEWAY_READ in viewer_perms

        # No write/deploy permissions
        assert Permission.RUNTIME_DEPLOY not in viewer_perms
        assert Permission.RUNTIME_EXECUTE not in viewer_perms
        assert Permission.MEMORY_WRITE not in viewer_perms

    def test_api_key_scopes(self):
        """Test API key scope permission sets"""
        # Read-only scope
        read_only = PermissionSet.API_KEY_READ_ONLY
        assert Permission.RUNTIME_READ in read_only
        assert Permission.RUNTIME_EXECUTE not in read_only

        # Execute scope
        execute = PermissionSet.API_KEY_EXECUTE
        assert Permission.RUNTIME_EXECUTE in execute
        assert Permission.RUNTIME_DEPLOY not in execute

        # Deploy scope
        deploy = PermissionSet.API_KEY_DEPLOY
        assert Permission.RUNTIME_DEPLOY in deploy
        assert Permission.RUNTIME_EXECUTE not in deploy


class TestRBACIntegration:
    """Integration tests for RBAC system"""

    def test_permission_hierarchy(self):
        """Test that roles form a proper hierarchy"""
        admin_perms = RoleManager.get_permissions_for_role(Role.ADMIN)
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)
        viewer_perms = RoleManager.get_permissions_for_role(Role.VIEWER)

        # Admin ⊃ Developer ⊃ Viewer
        assert dev_perms.issubset(admin_perms)
        assert viewer_perms.issubset(dev_perms)
        assert viewer_perms.issubset(admin_perms)

        # But not vice versa
        assert not admin_perms.issubset(dev_perms)
        assert not dev_perms.issubset(viewer_perms)

    def test_least_privilege_principle(self):
        """Test that roles follow least privilege principle"""
        admin_perms = RoleManager.get_permissions_for_role(Role.ADMIN)
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)
        viewer_perms = RoleManager.get_permissions_for_role(Role.VIEWER)

        # Each role has progressively fewer permissions
        assert len(admin_perms) > len(dev_perms)
        assert len(dev_perms) > len(viewer_perms)

    def test_critical_permissions_protected(self):
        """Test that critical permissions are appropriately restricted"""
        admin_perms = RoleManager.get_permissions_for_role(Role.ADMIN)
        dev_perms = RoleManager.get_permissions_for_role(Role.DEVELOPER)
        viewer_perms = RoleManager.get_permissions_for_role(Role.VIEWER)

        # User management - admin only
        assert Permission.USER_MANAGE in admin_perms
        assert Permission.USER_MANAGE not in dev_perms
        assert Permission.USER_MANAGE not in viewer_perms

        # API key management - admin only
        assert Permission.API_KEY_MANAGE in admin_perms
        assert Permission.API_KEY_MANAGE not in dev_perms
        assert Permission.API_KEY_MANAGE not in viewer_perms
