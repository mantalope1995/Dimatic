"""
AgentCore Security - Role-Based Access Control (RBAC)

Phase 7: Role assignment and permission checking for multi-tenant access control.

The RBAC system provides:
- Standard roles (admin, developer, viewer)
- Role assignment to users within tenants
- Permission checking based on roles
- Audit logging for role changes
"""

import logging
from datetime import datetime
from typing import List, Set, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from .permissions import Permission, PermissionSet


logger = logging.getLogger(__name__)


class Role(str, Enum):
    """
    Standard roles for tenant users.

    Phase 7: Three-tier role model for AgentCore multi-tenancy:

    ADMIN: Full access to all resources and user management
    DEVELOPER: Can deploy and execute resources, but not manage users
    VIEWER: Read-only access to resources
    """

    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


@dataclass
class RoleAssignment:
    """
    Assigns a role to a user within a tenant.

    Phase 7: Tracks who granted which role to which user, for audit purposes.
    """

    user_id: str
    account_id: str
    role: Role
    granted_by: str  # user_id who granted this role
    granted_at: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.granted_at is None:
            self.granted_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        # Convert datetime to ISO string
        if self.granted_at:
            data["granted_at"] = self.granted_at.isoformat()
        # Convert role enum to string
        data["role"] = self.role.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleAssignment":
        """Reconstruct from dictionary"""
        if isinstance(data.get("role"), str):
            data["role"] = Role(data["role"])
        if isinstance(data.get("granted_at"), str):
            data["granted_at"] = datetime.fromisoformat(data["granted_at"])
        return cls(**data)


class RoleManager:
    """
    Manager for role-based access control.

    Phase 7: Handles role assignment, retrieval, and permission checking.
    Uses DynamoDB for persistent storage with compound key (user_id + account_id).
    """

    # Default role permissions
    ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
        Role.ADMIN: PermissionSet.ADMIN_ALL,
        Role.DEVELOPER: PermissionSet.DEVELOPER,
        Role.VIEWER: PermissionSet.VIEWER,
    }

    def __init__(self, table_name: str = "role_assignments"):
        """
        Initialize role manager.

        Args:
            table_name: DynamoDB table name for role assignments
        """
        self.table_name = table_name
        self._dynamodb_client = None

    def _get_dynamodb_client(self):
        """Get or create DynamoDB client"""
        if self._dynamodb_client is None:
            try:
                import boto3
                from core.agentcore import get_config

                config = get_config()
                self._dynamodb_client = boto3.client(
                    "dynamodb",
                    region_name=config.aws_region,
                    aws_access_key_id=config.aws_access_key_id,
                    aws_secret_access_key=config.aws_secret_access_key,
                )
            except ImportError:
                raise ImportError("boto3 required for role management")
            except Exception as e:
                logger.error(f"Failed to create DynamoDB client: {e}")
                raise
        return self._dynamodb_client

    async def assign_role(
        self,
        user_id: str,
        account_id: str,
        role: Role,
        granted_by: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RoleAssignment:
        """
        Assign a role to a user in a tenant.

        Phase 7: Creates role assignment with audit logging.
        Verifies granter has ADMIN permission before assigning.

        Args:
            user_id: User ID to assign role to
            account_id: Tenant account ID
            role: Role to assign
            granted_by: User ID who is granting this role
            metadata: Optional metadata for audit

        Returns:
            RoleAssignment object

        Raises:
            PermissionError: If granter lacks ADMIN permission
        """
        # Verify granter has ADMIN role
        if not await self._has_permission(granted_by, account_id, Permission.ADMIN):
            from core.agentcore.errors import AgentCoreTenantError
            raise AgentCoreTenantError(
                f"User {granted_by} does not have permission to assign roles in account {account_id}"
            )

        assignment = RoleAssignment(
            user_id=user_id,
            account_id=account_id,
            role=role,
            granted_by=granted_by,
            metadata=metadata or {}
        )

        # Store in DynamoDB
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: dynamodb.put_item(
                TableName=self.table_name,
                Item=self._serialize_item(assignment.to_dict())
            )
        )

        logger.info(
            f"Assigned role {role.value} to user {user_id} "
            f"in account {account_id} by {granted_by}"
        )

        return assignment

    def _serialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python types to DynamoDB types"""
        from boto3.dynamodb.types import TypeSerializer

        serializer = TypeSerializer()
        return serializer.serialize(item)["M"]

    async def get_user_roles(
        self,
        user_id: str,
        account_id: str
    ) -> List[Role]:
        """
        Get all roles for a user in a tenant.

        Args:
            user_id: User ID
            account_id: Tenant account ID

        Returns:
            List of Role enum values
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.query(
                TableName=self.table_name,
                KeyConditionExpression="user_id = :user_id AND account_id = :account_id",
                ExpressionAttributeValues={
                    ":user_id": {"S": user_id},
                    ":account_id": {"S": account_id}
                }
            )
        )

        items = response.get("Items", [])
        roles = []

        for item in items:
            data = self._deserialize_item(item)
            assignment = RoleAssignment.from_dict(data)
            roles.append(assignment.role)

        return roles

    def _deserialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB types to Python types"""
        from boto3.dynamodb.types import TypeDeserializer

        deserializer = TypeDeserializer()
        return deserializer.deserialize({"M": item})

    async def get_role_assignments(
        self,
        user_id: str,
        account_id: str
    ) -> List[RoleAssignment]:
        """
        Get all role assignments for a user in a tenant.

        Args:
            user_id: User ID
            account_id: Tenant account ID

        Returns:
            List of RoleAssignment objects
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.query(
                TableName=self.table_name,
                KeyConditionExpression="user_id = :user_id AND account_id = :account_id",
                ExpressionAttributeValues={
                    ":user_id": {"S": user_id},
                    ":account_id": {"S": account_id}
                }
            )
        )

        items = response.get("Items", [])
        assignments = []

        for item in items:
            data = self._deserialize_item(item)
            assignments.append(RoleAssignment.from_dict(data))

        return assignments

    async def check_permission(
        self,
        user_id: str,
        account_id: str,
        required_permission: Permission
    ) -> bool:
        """
        Check if user has permission in tenant.

        Args:
            user_id: User ID to check
            account_id: Tenant account ID
            required_permission: Permission required

        Returns:
            True if user has permission, False otherwise
        """
        roles = await self.get_user_roles(user_id, account_id)

        # Check all roles
        for role in roles:
            role_perms = self.ROLE_PERMISSIONS.get(role, set())
            if required_permission in role_perms:
                return True

        return False

    async def has_any_permission(
        self,
        user_id: str,
        account_id: str,
        required_permissions: Set[Permission]
    ) -> bool:
        """
        Check if user has any of the specified permissions.

        Args:
            user_id: User ID to check
            account_id: Tenant account ID
            required_permissions: Set of required permissions

        Returns:
            True if user has at least one permission, False otherwise
        """
        roles = await self.get_user_roles(user_id, account_id)

        # Check all roles
        for role in roles:
            role_perms = self.ROLE_PERMISSIONS.get(role, set())
            # Check if any required permission is in role permissions
            if any(perm in role_perms for perm in required_permissions):
                return True

        return False

    async def has_all_permissions(
        self,
        user_id: str,
        account_id: str,
        required_permissions: Set[Permission]
    ) -> bool:
        """
        Check if user has all of the specified permissions.

        Args:
            user_id: User ID to check
            account_id: Tenant account ID
            required_permissions: Set of required permissions

        Returns:
            True if user has all permissions, False otherwise
        """
        roles = await self.get_user_roles(user_id, account_id)

        # Collect all permissions from all roles
        all_permissions: Set[Permission] = set()
        for role in roles:
            role_perms = self.ROLE_PERMISSIONS.get(role, set())
            all_permissions.update(role_perms)

        # Check if all required permissions are present
        return required_permissions.issubset(all_permissions)

    async def revoke_role(
        self,
        user_id: str,
        account_id: str,
        role: Role,
        revoked_by: str
    ) -> bool:
        """
        Revoke a role from a user in a tenant.

        Args:
            user_id: User ID to revoke role from
            account_id: Tenant account ID
            role: Role to revoke
            revoked_by: User ID who is revoking this role

        Returns:
            True if revoked successfully, False otherwise

        Raises:
            PermissionError: If revoker lacks ADMIN permission
        """
        # Verify revoker has ADMIN role
        if not await self._has_permission(revoked_by, account_id, Permission.ADMIN):
            from core.agentcore.errors import AgentCoreTenantError
            raise AgentCoreTenantError(
                f"User {revoked_by} does not have permission to revoke roles in account {account_id}"
            )

        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()

        try:
            # Delete the specific role assignment
            await loop.run_in_executor(
                None,
                lambda: dynamodb.delete_item(
                    TableName=self.table_name,
                    Key={
                        "user_id": {"S": user_id},
                        "account_id": {"S": account_id}
                    },
                    ConditionExpression="role = :role",
                    ExpressionAttributeValues={
                        ":role": {"S": role.value}
                    }
                )
            )
            logger.info(
                f"Revoked role {role.value} from user {user_id} "
                f"in account {account_id} by {revoked_by}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to revoke role: {e}")
            return False

    async def list_users_with_role(
        self,
        account_id: str,
        role: Role
    ) -> List[str]:
        """
        List all users in a tenant with a specific role.

        Args:
            account_id: Tenant account ID
            role: Role to filter by

        Returns:
            List of user IDs with the specified role
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.query(
                TableName=self.table_name,
                IndexName="account_role-index",  # Requires GSI on (account_id, role)
                KeyConditionExpression="account_id = :account_id AND role = :role",
                ExpressionAttributeValues={
                    ":account_id": {"S": account_id},
                    ":role": {"S": role.value}
                }
            )
        )

        items = response.get("Items", [])
        return [
            self._deserialize_item(item).get("user_id")
            for item in items
        ]

    async def _has_permission(
        self,
        user_id: str,
        account_id: str,
        permission: Permission
    ) -> bool:
        """
        Internal permission check helper.

        Args:
            user_id: User ID to check
            account_id: Tenant account ID
            permission: Permission to check

        Returns:
            True if user has permission, False otherwise
        """
        return await self.check_permission(user_id, account_id, permission)

    @classmethod
    def get_permissions_for_role(cls, role: Role) -> Set[Permission]:
        """
        Get permissions for a given role.

        Args:
            role: Role enum value

        Returns:
            Set of Permission values
        """
        return cls.ROLE_PERMISSIONS.get(role, set())

    @classmethod
    def get_default_role(cls) -> Role:
        """
        Get the default role for new users.

        Returns:
            Role enum (VIEWER by default)
        """
        return Role.VIEWER
