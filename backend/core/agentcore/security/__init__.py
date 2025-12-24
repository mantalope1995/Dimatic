"""
AgentCore Security Module

Phase 7: Multi-tenancy and security features for AWS AgentCore integration.

This module provides:
- Permission definitions (Permission, PermissionSet)
- API key management (APIKey, APIKeyManager, APIKeyScope)
- Role-based access control (Role, RoleManager)
"""

from .permissions import Permission, PermissionSet
from .api_keys import APIKey, APIKeyManager, APIKeyScope
from .rbac import Role, RoleAssignment, RoleManager

__all__ = [
    # Permissions
    "Permission",
    "PermissionSet",

    # API Keys
    "APIKey",
    "APIKeyManager",
    "APIKeyScope",

    # RBAC
    "Role",
    "RoleAssignment",
    "RoleManager",
]
