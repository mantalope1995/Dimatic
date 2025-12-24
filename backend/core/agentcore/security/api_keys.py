"""
AgentCore Security - API Key Management

Phase 7: Secure API key generation, validation, and lifecycle management.

API keys provide authentication and authorization for tenant access to AgentCore
services. Keys are cryptographically secure, rate-limited, and scoped to specific
permissions.
"""

import secrets
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, asdict, field
from enum import Enum

from .permissions import Permission, PermissionSet


logger = logging.getLogger(__name__)


class APIKeyScope(str, Enum):
    """
    API key scopes for fine-grained access control.

    Scopes are coarse-grained categories that map to sets of specific permissions.
    """

    # Read-only access
    READ_ONLY = "read"

    # Execute operations (run code, invoke tools)
    EXECUTE = "execute"

    # Deployment operations (create resources)
    DEPLOY = "deploy"

    # Full administrative access
    ADMIN = "admin"


@dataclass
class APIKey:
    """
    Secure API key for tenant authentication.

    Phase 7: Cryptographically secure API keys with:
    - SHA-256 hashing for storage (raw key never stored)
    - Scope-based permissions
    - Rate limiting
    - Expiration support
    - Revocation tracking

    Security Notes:
    - Raw key is ONLY available during generation
    - key_hash is stored in DynamoDB for validation
    - key_id is public identifier for key management
    """

    key_id: str
    key_hash: str  # SHA-256 hash of account_id:raw_key
    account_id: str
    scopes: List[str]  # List of APIKeyScope values
    permissions: List[str]  # List of Permission values
    rate_limit: int = 100  # requests per minute
    created_at: datetime = None
    expires_at: Optional[datetime] = None
    is_revoked: bool = False
    last_used_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    @classmethod
    def generate(
        cls,
        account_id: str,
        scopes: List[str],
        permissions: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        rate_limit: int = 100,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[str, "APIKey"]:
        """
        Generate a new API key for a tenant.

        Phase 7: Generates cryptographically secure random key and returns
        both the raw key (for display to user) and APIKey object (for storage).

        Args:
            account_id: Tenant account ID
            scopes: List of APIKeyScope values for coarse-grained access
            permissions: Optional list of Permission values for fine-grained access
            expires_in_days: Days until key expires (None = no expiration)
            rate_limit: Requests per minute limit
            metadata: Optional metadata dict for key description

        Returns:
            Tuple of (raw_key, api_key_object)
            - raw_key: Display this to user ONCE (never available again)
            - api_key_object: Store this in DynamoDB (hash only, no raw key)

        Example:
            >>> raw_key, key = APIKey.generate(
            ...     account_id="acct-123",
            ...     scopes=[APIKeyScope.EXECUTE],
            ...     expires_in_days=365
            ... )
            >>> print(f"Your API key: {raw_key}")  # Show to user ONCE
            >>> # Store key in DynamoDB (key object, not raw key)
        """
        # Validate scopes
        valid_scopes = []
        for scope in scopes:
            try:
                APIKeyScope(scope)
                valid_scopes.append(scope)
            except ValueError:
                logger.warning(f"Invalid API key scope filtered: {scope}")

        if not valid_scopes:
            raise ValueError("No valid API key scopes provided")

        # Generate secure random key (32 bytes = 256 bits)
        raw_key_bytes = secrets.token_bytes(32)
        raw_key = raw_key_bytes.hex()

        # Create key hash for storage
        # Use account_id as salt to prevent rainbow table attacks
        key_material = f"{account_id}:{raw_key}"
        key_hash = hashlib.sha256(key_material.encode()).hexdigest()

        # Generate public key ID (first 16 chars of hash)
        key_id = key_hash[:16]

        # Map scopes to permissions if not explicitly provided
        if permissions is None:
            permissions = cls._scopes_to_permissions(valid_scopes)

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        api_key = cls(
            key_id=key_id,
            key_hash=key_hash,
            account_id=account_id,
            scopes=valid_scopes,
            permissions=permissions,
            rate_limit=rate_limit,
            expires_at=expires_at,
            metadata=metadata or {}
        )

        # Return raw key prefixed with key identifier
        # Format: ak_{key_id}_{raw_key}
        formatted_raw_key = f"ak_{key_id}_{raw_key}"

        return formatted_raw_key, api_key

    @staticmethod
    def _scopes_to_permissions(scopes: List[str]) -> List[str]:
        """
        Map API key scopes to permission lists.

        Args:
            scopes: List of APIKeyScope string values

        Returns:
            List of Permission string values
        """
        scope_to_permissions = {
            APIKeyScope.READ_ONLY: PermissionSet.permissions_to_list(
                PermissionSet.API_KEY_READ_ONLY
            ),
            APIKeyScope.EXECUTE: PermissionSet.permissions_to_list(
                PermissionSet.API_KEY_EXECUTE
            ),
            APIKeyScope.DEPLOY: PermissionSet.permissions_to_list(
                PermissionSet.API_KEY_DEPLOY
            ),
            APIKeyScope.ADMIN: PermissionSet.permissions_to_list(
                PermissionSet.ADMIN_ALL
            ),
        }

        # Combine permissions from all scopes
        combined_permissions = set()
        for scope in scopes:
            combined_permissions.update(scope_to_permissions.get(scope, []))

        return list(combined_permissions)

    def validate_raw_key(self, raw_key: str) -> bool:
        """
        Validate a raw API key against this key's hash.

        Args:
            raw_key: Raw API key string to validate

        Returns:
            True if key matches hash, False otherwise
        """
        # Extract raw key from formatted string if present
        if raw_key.startswith("ak_"):
            parts = raw_key.split("_")
            if len(parts) >= 3:
                raw_key = parts[-1]  # Last part is the actual key

        # Recreate hash with account_id as salt
        key_material = f"{self.account_id}:{raw_key}"
        computed_hash = hashlib.sha256(key_material.encode()).hexdigest()

        return computed_hash == self.key_hash

    def has_permission(self, permission: Permission) -> bool:
        """
        Check if this API key has a specific permission.

        Args:
            permission: Permission to check

        Returns:
            True if key has the permission, False otherwise
        """
        return permission.value in self.permissions

    def has_any_permission(self, permissions: Set[Permission]) -> bool:
        """
        Check if this API key has any of the specified permissions.

        Args:
            permissions: Set of permissions to check

        Returns:
            True if key has at least one permission, False otherwise
        """
        return any(
            perm.value in self.permissions
            for perm in permissions
        )

    def has_all_permissions(self, permissions: Set[Permission]) -> bool:
        """
        Check if this API key has all of the specified permissions.

        Args:
            permissions: Set of permissions to check

        Returns:
            True if key has all permissions, False otherwise
        """
        return all(
            perm.value in self.permissions
            for perm in permissions
        )

    def is_expired(self) -> bool:
        """
        Check if the API key has expired.

        Returns:
            True if key is expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """
        Check if the API key is valid (not revoked, not expired).

        Returns:
            True if key is valid, False otherwise
        """
        return not self.is_revoked and not self.is_expired()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for DynamoDB storage.

        Note: Never includes raw_key - only hash for validation.
        """
        data = asdict(self)
        # Convert datetime to ISO string
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        if self.last_used_at:
            data["last_used_at"] = self.last_used_at.isoformat()
        # Serialize metadata as JSON
        if self.metadata:
            data["metadata"] = json.dumps(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APIKey":
        """
        Reconstruct APIKey from DynamoDB record.

        Args:
            data: Dictionary from DynamoDB

        Returns:
            APIKey object
        """
        # Parse datetime fields
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("expires_at"):
            if isinstance(data["expires_at"], str):
                data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        if data.get("last_used_at"):
            if isinstance(data["last_used_at"], str):
                data["last_used_at"] = datetime.fromisoformat(data["last_used_at"])

        # Parse metadata JSON
        if data.get("metadata") and isinstance(data["metadata"], str):
            data["metadata"] = json.loads(data["metadata"])

        return cls(**data)


class APIKeyManager:
    """
    Manager for API key lifecycle and validation.

    Phase 7: Handles API key creation, validation, revocation, and listing.
    Uses DynamoDB for persistent storage with account_id partitioning.
    """

    def __init__(self, table_name: str = "api_keys"):
        """
        Initialize API key manager.

        Args:
            table_name: DynamoDB table name for API keys
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
                raise ImportError("boto3 required for API key management")
            except Exception as e:
                logger.error(f"Failed to create DynamoDB client: {e}")
                raise
        return self._dynamodb_client

    async def create_key(
        self,
        account_id: str,
        scopes: List[str],
        permissions: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        rate_limit: int = 100,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[str, APIKey]:
        """
        Create a new API key.

        Phase 7: Generates key, stores hash in DynamoDB, returns raw key for display.

        Args:
            account_id: Tenant account ID
            scopes: List of APIKeyScope values
            permissions: Optional fine-grained permissions
            expires_in_days: Days until expiration
            rate_limit: Rate limit (requests per minute)
            metadata: Optional metadata

        Returns:
            Tuple of (raw_key, api_key_object)
        """
        # Generate key
        raw_key, api_key = APIKey.generate(
            account_id=account_id,
            scopes=scopes,
            permissions=permissions,
            expires_in_days=expires_in_days,
            rate_limit=rate_limit,
            metadata=metadata
        )

        # Store in DynamoDB
        dynamodb = self._get_dynamodb_client()

        item = api_key.to_dict()
        item["account_id"] = account_id  # Partition key
        item["key_id"] = api_key.key_id  # Sort key

        # Use boto3 put_item
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: dynamodb.put_item(TableName=self.table_name, Item=self._serialize_item(item))
        )

        logger.info(f"Created API key {api_key.key_id} for account {account_id}")

        # Return raw key (only time it's available)
        return raw_key, api_key

    def _serialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python types to DynamoDB types"""
        from boto3.dynamodb.types import TypeSerializer

        serializer = TypeSerializer()
        return serializer.serialize(item)["M"]

    async def validate_key(
        self,
        raw_key: str,
        required_permission: Optional[Permission] = None
    ) -> Optional[APIKey]:
        """
        Validate API key and return key object if valid.

        Phase 7: Validates raw key hash, checks expiration and revocation,
        optionally verifies required permission.

        Args:
            raw_key: Raw API key string to validate
            required_permission: Optional permission to check

        Returns:
            APIKey object if valid, None otherwise
        """
        # Extract key_id from raw_key
        if not raw_key.startswith("ak_"):
            return None

        parts = raw_key.split("_")
        if len(parts) < 2:
            return None

        key_id = parts[1]

        # Look up key from DynamoDB
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.get_item(
                TableName=self.table_name,
                Key={"key_id": {"S": key_id}}
            )
        )

        item = response.get("Item")
        if not item:
            logger.warning(f"API key {key_id} not found")
            return None

        # Deserialize item
        key_dict = self._deserialize_item(item)
        api_key = APIKey.from_dict(key_dict)

        # Check validity
        if not api_key.is_valid():
            logger.warning(f"API key {key_id} is invalid (revoked or expired)")
            return None

        # Validate raw key hash
        if not api_key.validate_raw_key(raw_key):
            logger.warning(f"API key {key_id} hash mismatch")
            return None

        # Check permission
        if required_permission and not api_key.has_permission(required_permission):
            logger.warning(
                f"API key {key_id} lacks permission {required_permission.value}"
            )
            return None

        # Update last_used_at
        await self._update_last_used(key_id)

        return api_key

    def _deserialize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB types to Python types"""
        from boto3.dynamodb.types import TypeDeserializer

        deserializer = TypeDeserializer()
        return deserializer.deserialize({"M": item})

    async def _update_last_used(self, key_id: str):
        """Update last_used_at timestamp"""
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: dynamodb.update_item(
                TableName=self.table_name,
                Key={"key_id": {"S": key_id}},
                UpdateExpression="SET last_used_at = :now",
                ExpressionAttributeValues={
                    ":now": {"S": datetime.utcnow().isoformat()}
                }
            )
        )

    async def revoke_key(self, key_id: str, account_id: str) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: API key ID to revoke
            account_id: Account ID (for ownership verification)

        Returns:
            True if revoked successfully, False otherwise
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()

        try:
            # Update with condition to verify ownership
            await loop.run_in_executor(
                None,
                lambda: dynamodb.update_item(
                    TableName=self.table_name,
                    Key={"key_id": {"S": key_id}},
                    UpdateExpression="SET is_revoked = :revoked",
                    ConditionExpression="account_id = :account_id",
                    ExpressionAttributeValues={
                        ":revoked": {"BOOL": True},
                        ":account_id": {"S": account_id}
                    }
                )
            )
            logger.info(f"Revoked API key {key_id} for account {account_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to revoke API key {key_id}: {e}")
            return False

    async def list_keys(
        self,
        account_id: str,
        include_revoked: bool = False
    ) -> List[APIKey]:
        """
        List all API keys for an account.

        Args:
            account_id: Account ID to list keys for
            include_revoked: Include revoked keys in results

        Returns:
            List of APIKey objects
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()

        # Query by account_id
        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.query(
                TableName=self.table_name,
                KeyConditionExpression="account_id = :account_id",
                ExpressionAttributeValues={
                    ":account_id": {"S": account_id}
                }
            )
        )

        items = response.get("Items", [])
        keys = []

        for item in items:
            key_dict = self._deserialize_item(item)
            api_key = APIKey.from_dict(key_dict)

            # Filter out revoked keys unless requested
            if not include_revoked and api_key.is_revoked:
                continue

            keys.append(api_key)

        return keys

    async def get_key(self, key_id: str, account_id: str) -> Optional[APIKey]:
        """
        Get a specific API key.

        Args:
            key_id: API key ID
            account_id: Account ID (for ownership verification)

        Returns:
            APIKey object if found and owned by account, None otherwise
        """
        dynamodb = self._get_dynamodb_client()

        import asyncio
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            lambda: dynamodb.get_item(
                TableName=self.table_name,
                Key={"key_id": {"S": key_id}}
            )
        )

        item = response.get("Item")
        if not item:
            return None

        key_dict = self._deserialize_item(item)
        api_key = APIKey.from_dict(key_dict)

        # Verify ownership
        if api_key.account_id != account_id:
            return None

        return api_key
