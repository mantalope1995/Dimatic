"""
AgentCore Memory Adapter

Provides interface to AWS Bedrock AgentCore Memory for persistent knowledge storage.
Handles memory resource creation, message storage, retrieval, and semantic search.
"""

import logging
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ..config import AgentCoreConfig, get_config
from ..errors import (
    with_retry,
    AgentCoreError,
    AgentCoreSessionError,
    AgentCoreTenantError as TenantError,
)
from ..models import MemoryResource, StoredMessage
from ..middleware import get_tenant_context

logger = logging.getLogger(__name__)


@dataclass
class MemoryResourceConfig:
    """Configuration for AgentCore Memory resource"""
    thread_id: str
    account_id: str
    retention_days: int = 90
    semantic_search_enabled: bool = True
    max_messages: int = 10000


class AgentCoreMemoryAdapter:
    """
    Adapter for AgentCore Memory operations

    This adapter provides methods to:
    - Create memory resources for threads
    - Store messages with metadata
    - Retrieve messages with optional semantic search
    - Delete memory resources
    - Handle fallback to database when unavailable
    """

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize AgentCore Memory adapter

        Args:
            config: AgentCore configuration (uses global config if not provided)
        """
        self.config = config or get_config()
        self._validate_config()
        self._initialize_client()

    def _validate_config(self):
        """Validate that Memory is enabled and configured"""
        if not self.config.memory_enabled:
            logger.warning("AgentCore Memory is not enabled in configuration")

        if not self.config.is_local():
            if not self.config.aws_access_key_id or not self.config.aws_secret_access_key:
                raise ValueError("AWS credentials required for AgentCore Memory")

    def _initialize_client(self):
        """Initialize AWS SDK client for AgentCore Memory"""
        logger.info(
            f"Initializing AgentCore Memory adapter for {self.config.environment} environment"
        )

        # TODO: Initialize boto3 client for AgentCore Memory when SDK is available
        # For now, initialize with placeholder pattern
        #
        # When AWS Bedrock AgentCore Memory SDK is available:
        # import boto3
        # self.client = boto3.client(
        #     'bedrock-agent-memory',  # or actual service name
        #     region_name=self.config.aws_region,  # ap-southeast-2
        #     aws_access_key_id=self.config.aws_access_key_id,
        #     aws_secret_access_key=self.config.aws_secret_access_key
        # )

        self.client = None
        logger.debug(f"Memory adapter initialized (region: {self.config.aws_region})")

    def _build_memory_resource_id(
        self,
        account_id: str,
        thread_id: str
    ) -> str:
        """
        Build tenant-isolated memory resource ID.

        Phase 7: Memory resource IDs now include account_id for tenant isolation.
        OLD format: memory-{thread_id}
        NEW format: memory-{account_id}-{thread_id}

        Args:
            account_id: Tenant account ID
            thread_id: Thread identifier

        Returns:
            Tenant-isolated memory resource ID
        """
        return f"memory-{account_id}-{thread_id}"

    async def _verify_memory_ownership(
        self,
        memory_resource_id: str,
        account_id: str
    ) -> bool:
        """
        Verify memory resource belongs to the tenant's account.

        This is a security check to prevent cross-tenant memory access.

        Args:
            memory_resource_id: Memory resource identifier
            account_id: Account ID to verify ownership

        Returns:
            True if memory resource belongs to the account, False otherwise
        """
        # Phase 7: Parse memory_resource_id format
        # Expected format: memory-{account_id}-{thread_id}
        parts = memory_resource_id.split('-')
        if len(parts) >= 3 and parts[0] == "memory":
            # The second part (index 1) should be account_id
            return parts[1] == account_id
        return False

    async def create_memory_resource(
        self,
        thread_id: str,
        account_id: str,
        retention_days: Optional[int] = None
    ) -> Optional[str]:
        """
        Create AgentCore Memory resource for thread

        Phase 7: Added tenant isolation with account_id in resource ID
        and tenant context verification.

        Args:
            thread_id: Thread identifier
            account_id: Account identifier for tenant isolation
            retention_days: Optional retention period (default: from config)

        Returns:
            memory_resource_id: AgentCore Memory resource identifier, or None if fallback

        Raises:
            TenantError: If tenant context is set and doesn't match account_id
            AgentCoreError: If resource creation fails and fallback is disabled
        """
        logger.info(f"Creating memory resource for thread {thread_id}, account {account_id}")

        # Phase 7: Verify tenant context if set
        tenant_ctx = get_tenant_context()
        if tenant_ctx is not None:
            # Tenant context is set, verify it matches account_id
            if tenant_ctx.account_id != account_id:
                logger.warning(
                    f"SECURITY: Tenant {tenant_ctx.account_id[:8]}... attempted to create "
                    f"memory for account {account_id}"
                )
                raise TenantError(
                    f"Cannot create memory for account {account_id} "
                    f"from tenant {tenant_ctx.account_id}. "
                    f"Cross-tenant memory creation is not permitted."
                )
            # Ownership verified, proceed

        try:
            # Create memory resource configuration
            memory_config = MemoryResourceConfig(
                thread_id=thread_id,
                account_id=account_id,
                retention_days=retention_days or self.config.memory_retention_days,
                semantic_search_enabled=self.config.memory_semantic_search_enabled,
                max_messages=self.config.memory_max_messages,
            )

            # TODO: Call AgentCore Memory API to create resource
            # When AWS Bedrock AgentCore Memory SDK is available:
            # response = await self._call_with_retry(
            #     self._create_memory_api,
            #     thread_id=thread_id,
            #     account_id=account_id,
            #     config=memory_config
            # )
            # memory_resource_id = response['memoryResourceId']

            # Phase 7: Use tenant-isolated resource ID format
            memory_resource_id = self._build_memory_resource_id(account_id, thread_id)

            logger.info(f"Created memory resource: {memory_resource_id}")
            return memory_resource_id

        except Exception as e:
            logger.error(f"Failed to create memory resource for thread {thread_id}: {str(e)}")
            if self.config.fallback_to_database:
                logger.warning("Falling back to database-only mode for this thread")
                return None
            raise AgentCoreError(f"Memory resource creation failed: {str(e)}")

    async def store_message(
        self,
        memory_resource_id: str,
        message: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Store message in AgentCore Memory

        Phase 7: Added tenant ownership verification to prevent cross-tenant
        message storage.

        Args:
            memory_resource_id: Memory resource identifier
            message: Message data (role, content, etc.)
            metadata: Additional metadata for the message

        Returns:
            message_id: Stored message identifier, or None if fallback

        Raises:
            AgentCoreError: If storage fails and fallback is disabled
            TenantError: If tenant tries to store messages in another tenant's memory
        """
        logger.debug(f"Storing message in memory resource {memory_resource_id}")

        # Phase 7: Verify tenant ownership before storing message
        tenant_ctx = get_tenant_context()
        if tenant_ctx is not None:
            # Extract account_id from memory_resource_id
            # Format: memory-{account_id}-{thread_id}
            parts = memory_resource_id.split('-')
            if len(parts) >= 3 and parts[0] == "memory":
                resource_account_id = parts[1]
                if resource_account_id != tenant_ctx.account_id:
                    logger.warning(
                        f"SECURITY: Tenant {tenant_ctx.account_id[:8]}... attempted to store "
                        f"message in memory {memory_resource_id} (belongs to {resource_account_id})"
                    )
                    raise TenantError(
                        f"Cannot store messages in memory resource {memory_resource_id}. "
                        f"This memory resource belongs to account {resource_account_id}, "
                        f"not tenant {tenant_ctx.account_id}. "
                        f"Cross-tenant message storage is not permitted."
                    )

        try:
            # Validate message structure
            if 'role' not in message:
                raise ValueError("Message must contain 'role' field")
            if 'content' not in message:
                raise ValueError("Message must contain 'content' field")

            # TODO: Call AgentCore Memory API to store message
            # When AWS Bedrock AgentCore Memory SDK is available:
            # response = await self._call_with_retry(
            #     self._store_message_api,
            #     memory_resource_id=memory_resource_id,
            #     message=message,
            #     metadata=metadata or {}
            # )
            # message_id = response['memoryId']

            # For now, generate a mock message ID
            message_id = str(uuid.uuid4())

            logger.debug(f"Stored message: {message_id}")
            return message_id

        except Exception as e:
            logger.error(f"Failed to store message in memory {memory_resource_id}: {str(e)}")
            if self.config.fallback_to_database:
                logger.warning("Falling back to database storage")
                return None
            raise AgentCoreError(f"Message storage failed: {str(e)}")

    async def retrieve_messages(
        self,
        memory_resource_id: str,
        limit: int = 100,
        semantic_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages from AgentCore Memory

        Phase 7: Added tenant ownership verification to prevent cross-tenant
        message retrieval.

        Args:
            memory_resource_id: Memory resource identifier
            limit: Maximum number of messages to retrieve
            semantic_query: Optional semantic search query

        Returns:
            List of messages with metadata

        Raises:
            AgentCoreError: If retrieval fails and fallback is disabled
            TenantError: If tenant tries to retrieve messages from another tenant's memory
        """
        logger.debug(
            f"Retrieving messages from memory resource {memory_resource_id} "
            f"(limit={limit}, semantic_query={semantic_query is not None})"
        )

        # Phase 7: Verify tenant ownership before retrieving messages
        tenant_ctx = get_tenant_context()
        if tenant_ctx is not None:
            # Extract account_id from memory_resource_id
            # Format: memory-{account_id}-{thread_id}
            parts = memory_resource_id.split('-')
            if len(parts) >= 3 and parts[0] == "memory":
                resource_account_id = parts[1]
                if resource_account_id != tenant_ctx.account_id:
                    logger.warning(
                        f"SECURITY: Tenant {tenant_ctx.account_id[:8]}... attempted to retrieve "
                        f"messages from memory {memory_resource_id} (belongs to {resource_account_id})"
                    )
                    raise TenantError(
                        f"Cannot retrieve messages from memory resource {memory_resource_id}. "
                        f"This memory resource belongs to account {resource_account_id}, "
                        f"not tenant {tenant_ctx.account_id}. "
                        f"Cross-tenant message retrieval is not permitted."
                    )

        try:
            # TODO: Call AgentCore Memory API to retrieve messages
            # When AWS Bedrock AgentCore Memory SDK is available:
            # if semantic_query and self.config.memory_semantic_search_enabled:
            #     messages = await self._call_with_retry(
            #         self._semantic_search_api,
            #         memory_resource_id=memory_resource_id,
            #         query=semantic_query,
            #         limit=limit
            #     )
            # else:
            #     messages = await self._call_with_retry(
            #         self._retrieve_messages_api,
            #         memory_resource_id=memory_resource_id,
            #         limit=limit
            #     )

            # For now, return empty list
            messages = []

            logger.debug(f"Retrieved {len(messages)} messages")
            return messages

        except Exception as e:
            logger.error(f"Failed to retrieve messages from memory {memory_resource_id}: {str(e)}")
            if self.config.fallback_to_database:
                logger.warning("Falling back to database retrieval")
                return []
            raise AgentCoreError(f"Message retrieval failed: {str(e)}")

    async def delete_memory_resource(self, memory_resource_id: str) -> bool:
        """
        Delete AgentCore Memory resource

        Args:
            memory_resource_id: Memory resource identifier

        Returns:
            True if deletion successful, False otherwise
        """
        logger.info(f"Deleting memory resource {memory_resource_id}")

        try:
            # TODO: Call AgentCore Memory API to delete resource
            # When AWS Bedrock AgentCore Memory SDK is available:
            # result = await self._call_with_retry(
            #     self._delete_memory_api,
            #     memory_resource_id=memory_resource_id
            # )
            # return result.get('success', True)

            # For now, return mock success
            return True

        except Exception as e:
            logger.error(f"Failed to delete memory resource {memory_resource_id}: {str(e)}")
            return False

    async def get_memory_resource_info(
        self,
        memory_resource_id: str
    ) -> Optional[MemoryResource]:
        """
        Get information about a Memory resource

        Args:
            memory_resource_id: Memory resource identifier

        Returns:
            MemoryResource object or None if not found
        """
        logger.debug(f"Getting memory resource info: {memory_resource_id}")

        try:
            # TODO: Call AgentCore Memory API to get resource info
            # When AWS Bedrock AgentCore Memory SDK is available:
            # response = await self._call_with_retry(
            #     self._get_memory_info_api,
            #     memory_resource_id=memory_resource_id
            # )
            # return MemoryResource.from_dict(response)

            return None

        except Exception as e:
            logger.warning(f"Failed to get memory resource info: {str(e)}")
            return None

    async def search_memory(
        self,
        memory_resource_id: str,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search across Memory

        Args:
            memory_resource_id: Memory resource identifier
            query: Semantic search query
            limit: Maximum number of results

        Returns:
            List of relevant messages with similarity scores
        """
        logger.debug(f"Searching memory {memory_resource_id} with query: {query}")

        try:
            # TODO: Call AgentCore Memory semantic search API
            # When AWS Bedrock AgentCore Memory SDK is available:
            # response = await self._call_with_retry(
            #     self._semantic_search_api,
            #     memory_resource_id=memory_resource_id,
            #     query=query,
            #     limit=limit
            # )
            # return response.get('results', [])

            return []

        except Exception as e:
            logger.warning(f"Semantic search failed: {str(e)}")
            return []

    # TODO: Add private API methods when AWS SDK is available
    # These methods will wrap the actual AWS SDK calls

    # async def _create_memory_api(self, thread_id: str, account_id: str, config: MemoryResourceConfig) -> Dict:
    #     """Internal method to call create_memory API"""
    #     pass
    #
    # async def _store_message_api(self, memory_resource_id: str, message: Dict, metadata: Dict) -> Dict:
    #     """Internal method to call put_memory API"""
    #     pass
    #
    # async def _retrieve_messages_api(self, memory_resource_id: str, limit: int) -> List[Dict]:
    #     """Internal method to call get_memory API"""
    #     pass
    #
    # async def _semantic_search_api(self, memory_resource_id: str, query: str, limit: int) -> List[Dict]:
    #     """Internal method to call search_memory API"""
    #     pass
    #
    # async def _delete_memory_api(self, memory_resource_id: str) -> Dict:
    #     """Internal method to call delete_memory API"""
    #     pass
    #
    # async def _get_memory_info_api(self, memory_resource_id: str) -> Dict:
    #     """Internal method to call get_memory_info API"""
    #     pass

    async def _call_with_retry(self, func, *args, **kwargs) -> Any:
        """Call an async function with retry logic"""
        return await with_retry(
            func,
            *args,
            max_attempts=self.config.retry_max_attempts,
            base_delay=self.config.retry_base_delay_seconds,
            max_delay=self.config.retry_max_delay_seconds,
            **kwargs
        )
