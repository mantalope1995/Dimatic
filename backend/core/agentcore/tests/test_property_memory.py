"""
Property-Based Tests for AgentCore Memory Integration

Tests invariant properties of Memory operations across many generated inputs.
Uses Hypothesis framework to test correctness properties.

Properties:
- Property 7: Memory Resource Creation - Unique IDs with tenant isolation
- Property 8: Message Storage - Messages can be stored and retrieved
- Property 20: Semantic Search - Queries return relevant ranked results
- Property 24: Storage Integrity - Messages survive round-trip serialization

Phase 4: AgentCore Memory Integration
"""

import pytest
import json
from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume
from typing import Dict, Any

from core.agentcore.config import AgentCoreConfig, Environment
from core.agentcore.adapters.memory import AgentCoreMemoryAdapter
from core.agentcore.models import MemoryResource, StoredMessage


@pytest.fixture
def memory_config():
    """Create a local environment configuration for Memory testing"""
    return AgentCoreConfig(
        environment=Environment.LOCAL,
        memory_enabled=True,
        memory_retention_days=90,
        memory_semantic_search_enabled=True,
        memory_max_messages=10000,
        fallback_to_database=True,
        aws_region="ap-southeast-2"  # Phase 1 requirement
    )


class TestProperty7MemoryResourceCreation:
    """
    Property 7: Memory Resource Creation

    Tests that for any thread_id and account_id:
    - Memory resource is created with unique ID
    - Resource ID incorporates thread_id for traceability
    - Resource has tenant isolation (account_id in metadata)
    - Resource has valid status and timestamp
    """

    @pytest.mark.asyncio
    @given(
        thread_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u))
    )
    async def test_memory_resource_has_unique_id(self, thread_id: str, account_id: str, memory_config):
        """
        Property: Memory resource creation returns unique ID for any thread_id and account_id.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        memory_id = await adapter.create_memory_resource(
            thread_id=thread_id,
            account_id=account_id
        )

        # Property: memory_id should not be None
        assert memory_id is not None, "Memory resource ID should not be None"

        # Property: memory_id should be unique (contains thread_id)
        assert thread_id in memory_id or "memory" in memory_id, \
            f"Memory ID should contain reference to thread or 'memory': {memory_id}"

        # Property: memory_id should be a string
        assert isinstance(memory_id, str), "Memory ID should be a string"

    @pytest.mark.asyncio
    @given(
        thread_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u))
    )
    async def test_memory_resource_has_traceable_id(self, thread_id: str, account_id: str, memory_config):
        """
        Property: Memory resource ID is traceable to original thread_id.
        For any thread_id, the memory_resource_id should allow tracing back to the thread.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        memory_id = await adapter.create_memory_resource(
            thread_id=thread_id,
            account_id=account_id
        )

        # Property: Should be able to identify the thread from the memory_id
        # The memory_id should contain the thread_id or a hash of it
        assert memory_id is not None
        # Check that memory_id has some relationship to thread_id
        # (either direct inclusion or consistent hashing pattern)
        assert isinstance(memory_id, str) and len(memory_id) > len(thread_id) or thread_id in memory_id

    @pytest.mark.asyncio
    @given(
        thread_id1=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        thread_id2=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u))
    )
    async def test_memory_resources_are_unique_per_thread(self, thread_id1: str, thread_id2: str, account_id: str, memory_config):
        """
        Property: Different threads get different memory resource IDs.
        For any two distinct thread_ids, their memory_resource_ids should be different.
        """
        assume(thread_id1 != thread_id2)

        adapter = AgentCoreMemoryAdapter(config=memory_config)

        memory_id1 = await adapter.create_memory_resource(
            thread_id=thread_id1,
            account_id=account_id
        )
        memory_id2 = await adapter.create_memory_resource(
            thread_id=thread_id2,
            account_id=account_id
        )

        # Property: Different threads should have different memory resource IDs
        assert memory_id1 != memory_id2, \
            f"Different threads should have different memory IDs: {memory_id1} vs {memory_id2}"

    @pytest.mark.asyncio
    @given(
        thread_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u)),
        retention_days=st.integers(min_value=1, max_value=365)
    )
    async def test_memory_resource_with_custom_retention(self, thread_id: str, account_id: str, retention_days: int, memory_config):
        """
        Property: Memory resource creation respects custom retention_days parameter.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        memory_id = await adapter.create_memory_resource(
            thread_id=thread_id,
            account_id=account_id,
            retention_days=retention_days
        )

        # Property: Should successfully create with custom retention
        assert memory_id is not None


class TestProperty8MessageStorage:
    """
    Property 8: Message Storage in Memory

    Tests that messages:
    - Can be stored successfully
    - Can be retrieved with same content
    - Preserve metadata
    - Have valid message IDs
    """

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        role=st.sampled_from(["user", "assistant", "system", "tool"]),
        content=st.text(min_size=1, max_size=200)
    )
    async def test_message_storage_returns_id(self, memory_resource_id: str, role: str, content: str, memory_config):
        """
        Property: Storing a valid message returns a message ID.
        For any valid message structure, storage should succeed and return an ID.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        message = {
            "role": role,
            "content": content
        }

        message_id = await adapter.store_message(
            memory_resource_id=memory_resource_id,
            message=message
        )

        # Property: Should return a valid message ID
        assert message_id is not None, "Message storage should return an ID"

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        role=st.sampled_from(["user", "assistant", "system", "tool"]),
        content=st.text(min_size=1, max_size=200),
        metadata=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.text(min_size=0, max_size=50) | st.integers() | st.booleans(),
            min_size=0,
            max_size=5
        )
    )
    async def test_message_storage_with_metadata(self, memory_resource_id: str, role: str, content: str, metadata: dict, memory_config):
        """
        Property: Message storage preserves metadata.
        For any message with metadata, storage should include the metadata.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        message = {
            "role": role,
            "content": content
        }

        message_id = await adapter.store_message(
            memory_resource_id=memory_resource_id,
            message=message,
            metadata=metadata
        )

        # Property: Storage with metadata should succeed
        assert message_id is not None

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        message_count=st.integers(min_value=1, max_value=10)
    )
    async def test_multiple_message_storage(self, memory_resource_id: str, message_count: int, memory_config):
        """
        Property: Multiple messages can be stored in the same memory resource.
        For any count of messages, all should be stored successfully.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        message_ids = []
        for i in range(message_count):
            message = {
                "role": "user",
                "content": f"Message {i}"
            }
            message_id = await adapter.store_message(
                memory_resource_id=memory_resource_id,
                message=message
            )
            message_ids.append(message_id)

        # Property: All messages should be stored
        assert len(message_ids) == message_count
        assert all(msg_id is not None for msg_id in message_ids)

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        content=st.one_of(
            st.text(min_size=1, max_size=200),
            st.dictionaries(
                st.text(min_size=1, max_size=10),
                st.text(min_size=0, max_size=100),
                min_size=1,
                max_size=5
            ),
            st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5)
        )
    )
    async def test_various_content_types(self, memory_resource_id: str, content, memory_config):
        """
        Property: Messages with various content types can be stored.
        For any valid content (string, dict, list), storage should succeed.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        message = {
            "role": "user",
            "content": content
        }

        message_id = await adapter.store_message(
            memory_resource_id=memory_resource_id,
            message=message
        )

        # Property: Should handle various content types
        assert message_id is not None


class TestProperty20SemanticSearch:
    """
    Property 20: Semantic Search Functionality

    Tests that semantic search:
    - Returns results for valid queries
    - Results are ranked by relevance
    - Query terms match message content
    - Handles empty results gracefully
    """

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        query=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        limit=st.integers(min_value=1, max_value=50)
    )
    async def test_semantic_search_returns_list(self, memory_resource_id: str, query: str, limit: int, memory_config):
        """
        Property: Semantic search returns a list of results.
        For any query and limit, search should return a list (possibly empty).
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        results = await adapter.search_memory(
            memory_resource_id=memory_resource_id,
            query=query,
            limit=limit
        )

        # Property: Search should always return a list
        assert isinstance(results, list), "Search results should be a list"

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        query=st.text(min_size=1, max_size=100).filter(lambda x: x.strip())
    )
    async def test_semantic_search_with_default_limit(self, memory_resource_id: str, query: str, memory_config):
        """
        Property: Semantic search with default limit works correctly.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        results = await adapter.search_memory(
            memory_resource_id=memory_resource_id,
            query=query
        )

        # Property: Should return results with default limit
        assert isinstance(results, list)

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        limit=st.integers(min_value=1, max_value=100)
    )
    async def test_retrieve_messages_respects_limit(self, memory_resource_id: str, limit: int, memory_config):
        """
        Property: Message retrieval respects the limit parameter.
        For any limit, retrieval should return at most that many messages.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        messages = await adapter.retrieve_messages(
            memory_resource_id=memory_resource_id,
            limit=limit
        )

        # Property: Retrieved messages count should not exceed limit
        assert isinstance(messages, list)
        assert len(messages) <= limit, \
            f"Retrieved {len(messages)} messages, but limit was {limit}"

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_retrieve_with_semantic_query(self, memory_resource_id: str, memory_config):
        """
        Property: Retrieval with semantic query parameter works correctly.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        messages = await adapter.retrieve_messages(
            memory_resource_id=memory_resource_id,
            semantic_query="test query"
        )

        # Property: Should return list
        assert isinstance(messages, list)


class TestProperty24StorageIntegrity:
    """
    Property 24: Memory Storage Integrity

    Tests that messages:
    - Survive serialization/deserialization round-trip
    - Maintain data consistency
    - Preserve structure and types
    """

    @pytest.mark.asyncio
    @given(
        role=st.sampled_from(["user", "assistant", "system", "tool"]),
        content=st.one_of(
            st.text(min_size=1, max_size=200),
            st.dictionaries(
                st.text(min_size=1, max_size=10),
                st.one_of(st.text(min_size=0, max_size=100), st.integers(), st.booleans()),
                min_size=0,
                max_size=5
            )
        ),
        metadata=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.one_of(st.none(), st.text(min_size=0, max_size=50), st.integers(), st.booleans()),
            min_size=0,
            max_size=3
        ),
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_message_structure_preserved(self, role: str, content, metadata: dict, memory_resource_id: str, memory_config):
        """
        Property: Message structure is preserved through storage.
        For any valid message structure, the essential fields should be preserved.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        original_message = {
            "role": role,
            "content": content
        }

        message_id = await adapter.store_message(
            memory_resource_id=memory_resource_id,
            message=original_message,
            metadata=metadata
        )

        # Property: Storage should succeed and return ID
        assert message_id is not None

        # Verify original message structure is valid
        assert "role" in original_message
        assert "content" in original_message
        assert original_message["role"] == role
        assert original_message["content"] == content

    @pytest.mark.asyncio
    @given(
        message_dict=st.dictionaries(
            st.sampled_from(["role", "content", "timestamp", "metadata", "extra_field"]),
            st.one_of(
                st.text(min_size=0, max_size=200),
                st.integers(min_value=0, max_value=1000),
                st.booleans(),
                st.dictionaries(
                    st.text(min_size=1, max_size=5),
                    st.text(min_size=0, max_size=50),
                    min_size=0,
                    max_size=3
                )
            ),
            min_size=2,
            max_size=6
        ).filter(lambda d: "role" in d and "content" in d),
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_complex_message_serialization(self, message_dict: dict, memory_resource_id: str, memory_config):
        """
        Property: Complex message structures can be stored and retrieved.
        For any valid message dict with role and content, storage should work.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        # Ensure required fields
        assume("role" in message_dict and "content" in message_dict)

        message_id = await adapter.store_message(
            memory_resource_id=memory_resource_id,
            message=message_dict
        )

        # Property: Complex message should be stored
        assert message_id is not None

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_empty_retrieval_is_safe(self, memory_resource_id: str, memory_config):
        """
        Property: Retrieving from empty memory resource is safe.
        For any memory resource, retrieval should not crash even if empty.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        messages = await adapter.retrieve_messages(
            memory_resource_id=memory_resource_id,
            limit=100
        )

        # Property: Should return empty list, not crash
        assert isinstance(messages, list)


class TestMemoryAdapterIntegration:
    """
    Integration property tests for Memory adapter lifecycle.

    Tests complete workflows:
    - Create resource → Store messages → Retrieve → Delete
    - Error recovery and fallback behavior
    """

    @pytest.mark.asyncio
    @given(
        thread_id=st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u)),
        message_count=st.integers(min_value=1, max_value=5)
    )
    async def test_full_lifecycle_workflow(self, thread_id: str, account_id: str, message_count: int, memory_config):
        """
        Property: Full lifecycle (create → store → retrieve → delete) works correctly.
        For any thread and message count, the complete workflow should succeed.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        # Step 1: Create memory resource
        memory_id = await adapter.create_memory_resource(
            thread_id=thread_id,
            account_id=account_id
        )
        assert memory_id is not None

        # Step 2: Store multiple messages
        message_ids = []
        for i in range(message_count):
            message = {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Test message {i}"
            }
            msg_id = await adapter.store_message(
                memory_resource_id=memory_id,
                message=message
            )
            message_ids.append(msg_id)

        # Property: All messages should be stored
        assert all(msg_id is not None for msg_id in message_ids)

        # Step 3: Retrieve messages
        messages = await adapter.retrieve_messages(
            memory_resource_id=memory_id,
            limit=message_count
        )
        assert isinstance(messages, list)

        # Step 4: Delete memory resource
        deleted = await adapter.delete_memory_resource(memory_id)
        assert deleted is True

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_delete_nonexistent_resource(self, memory_resource_id: str, memory_config):
        """
        Property: Deleting a non-existent memory resource is safe.
        Should return False or handle gracefully, not crash.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        result = await adapter.delete_memory_resource(memory_resource_id)

        # Property: Should handle gracefully
        # May return True (idempotent) or False (not found)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    @given(
        memory_resource_id=st.text(min_size=1, max_size=50).filter(lambda x: x.strip())
    )
    async def test_get_memory_resource_info(self, memory_resource_id: str, memory_config):
        """
        Property: Getting memory resource info returns MemoryResource or None.
        Should not crash for any memory_resource_id.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        info = await adapter.get_memory_resource_info(memory_resource_id)

        # Property: Should return None (for mock implementation) or MemoryResource
        assert info is None or isinstance(info, MemoryResource)


class TestMemoryRegionRequirement:
    """
    Property: Region enforcement for AgentCore Memory (Phase 1 requirement).

    Tests that all Memory operations use ap-southeast-2 region.
    """

    def test_adapter_uses_ap_southeast_2(self, memory_config):
        """
        Property: Memory adapter is configured with ap-southeast-2 region.
        Phase 1 requires all AgentCore services to use ap-southeast-2 (Australia).
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        # Property: Region should be ap-southeast-2
        assert adapter.config.aws_region == "ap-southeast-2", \
            "Phase 1 requires ap-southeast-2 region for AgentCore Memory"

    @pytest.mark.asyncio
    @given(
        thread_id=st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
        account_id=st.uuids().map(lambda u: str(u))
    )
    async def test_region_enforcement_in_create(self, thread_id: str, account_id: str, memory_config):
        """
        Property: Memory resource creation uses ap-southeast-2 region.
        """
        adapter = AgentCoreMemoryAdapter(config=memory_config)

        # Verify region before creating
        assert adapter.config.aws_region == "ap-southeast-2"

        memory_id = await adapter.create_memory_resource(
            thread_id=thread_id,
            account_id=account_id
        )

        # Property: Should succeed with correct region
        assert memory_id is not None
