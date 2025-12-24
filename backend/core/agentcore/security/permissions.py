"""
AgentCore Security - Permission Definitions

Phase 7: Fine-grained permissions for RBAC and API key scopes.

Permissions define specific actions that can be performed on AgentCore resources.
Each permission corresponds to a specific capability in the system.
"""

from enum import Enum
from typing import Set, Dict, List


class Permission(str, Enum):
    """Fine-grained permissions for RBAC and API key scopes"""

    # Runtime permissions
    RUNTIME_DEPLOY = "runtime:deploy"
    RUNTIME_EXECUTE = "runtime:execute"
    RUNTIME_DELETE = "runtime:delete"
    RUNTIME_READ = "runtime:read"

    # Memory permissions
    MEMORY_CREATE = "memory:create"
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # Gateway permissions
    GATEWAY_DEPLOY = "gateway:deploy"
    GATEWAY_INVOKE = "gateway:invoke"
    GATEWAY_DELETE = "gateway:delete"
    GATEWAY_READ = "gateway:read"

    # Code Interpreter permissions
    CODE_INTERPRETER_EXECUTE = "code_interpreter:execute"
    CODE_INTERPRETER_READ = "code_interpreter:read"

    # Browser permissions
    BROWSER_EXECUTE = "browser:execute"
    BROWSER_READ = "browser:read"

    # Admin permissions
    ADMIN = "admin"
    USER_MANAGE = "user:manage"
    API_KEY_MANAGE = "api_key:manage"
    SETTINGS_MANAGE = "settings:manage"


class PermissionSet:
    """
    Logical grouping of permissions for common roles and scenarios.

    Phase 7: Provides predefined permission sets for standard use cases.
    """

    # Full admin access
    ADMIN_ALL: Set[Permission] = {
        Permission.ADMIN,
        Permission.USER_MANAGE,
        Permission.API_KEY_MANAGE,
        Permission.SETTINGS_MANAGE,
        # All runtime permissions
        Permission.RUNTIME_DEPLOY,
        Permission.RUNTIME_EXECUTE,
        Permission.RUNTIME_DELETE,
        Permission.RUNTIME_READ,
        # All memory permissions
        Permission.MEMORY_CREATE,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        # All gateway permissions
        Permission.GATEWAY_DEPLOY,
        Permission.GATEWAY_INVOKE,
        Permission.GATEWAY_DELETE,
        Permission.GATEWAY_READ,
        # All code interpreter permissions
        Permission.CODE_INTERPRETER_EXECUTE,
        Permission.CODE_INTERPRETER_READ,
        # All browser permissions
        Permission.BROWSER_EXECUTE,
        Permission.BROWSER_READ,
    }

    # Developer role: Can deploy and execute, but not manage users
    DEVELOPER: Set[Permission] = {
        Permission.RUNTIME_DEPLOY,
        Permission.RUNTIME_EXECUTE,
        Permission.RUNTIME_READ,
        Permission.MEMORY_CREATE,
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.GATEWAY_DEPLOY,
        Permission.GATEWAY_INVOKE,
        Permission.GATEWAY_READ,
        Permission.CODE_INTERPRETER_EXECUTE,
        Permission.CODE_INTERPRETER_READ,
        Permission.BROWSER_EXECUTE,
        Permission.BROWSER_READ,
    }

    # Viewer role: Read-only access
    VIEWER: Set[Permission] = {
        Permission.RUNTIME_READ,
        Permission.MEMORY_READ,
        Permission.GATEWAY_READ,
        Permission.CODE_INTERPRETER_READ,
        Permission.BROWSER_READ,
    }

    # API key scopes - fine-grained for different key types
    API_KEY_READ_ONLY: Set[Permission] = {
        Permission.RUNTIME_READ,
        Permission.MEMORY_READ,
        Permission.GATEWAY_READ,
    }

    API_KEY_EXECUTE: Set[Permission] = {
        Permission.RUNTIME_EXECUTE,
        Permission.MEMORY_WRITE,
        Permission.GATEWAY_INVOKE,
        Permission.CODE_INTERPRETER_EXECUTE,
        Permission.BROWSER_EXECUTE,
    }

    API_KEY_DEPLOY: Set[Permission] = {
        Permission.RUNTIME_DEPLOY,
        Permission.MEMORY_CREATE,
        Permission.GATEWAY_DEPLOY,
    }

    @classmethod
    def get_permissions_for_role(cls, role: str) -> Set[Permission]:
        """
        Get permission set for a given role name.

        Args:
            role: Role name (admin, developer, viewer)

        Returns:
            Set of permissions for the role
        """
        role_map = {
            "admin": cls.ADMIN_ALL,
            "developer": cls.DEVELOPER,
            "viewer": cls.VIEWER,
        }
        return role_map.get(role.lower(), cls.VIEWER)

    @classmethod
    def permissions_to_list(cls, permissions: Set[Permission]) -> List[str]:
        """
        Convert permission set to list of strings for storage.

        Args:
            permissions: Set of Permission enum values

        Returns:
            List of permission string values
        """
        return [p.value for p in permissions]

    @classmethod
    def list_to_permissions(cls, permission_list: List[str]) -> Set[Permission]:
        """
        Convert list of strings to permission set.

        Args:
            permission_list: List of permission string values

        Returns:
            Set of Permission enum values
        """
        return {Permission(p) for p in permission_list}

    @classmethod
    def validate_permissions(cls, permissions: List[str]) -> List[str]:
        """
        Validate that all permission strings are valid Permission values.

        Args:
            permissions: List of permission strings to validate

        Returns:
            List of valid permission strings (filters invalid ones)

        Raises:
            ValueError: If no valid permissions found
        """
        valid_permissions = []
        invalid_permissions = []

        for perm_str in permissions:
            try:
                Permission(perm_str)
                valid_permissions.append(perm_str)
            except ValueError:
                invalid_permissions.append(perm_str)

        if invalid_permissions:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid permissions filtered out: {invalid_permissions}"
            )

        if not valid_permissions:
            raise ValueError("No valid permissions provided")

        return valid_permissions
