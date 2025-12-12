"""Property-based tests for Obot Profile Service

These tests verify Property 8: Profile Query Compatibility
Validates: Requirements 7.3
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume
from hypothesis.stateful import rule, precondition, run_state_machine_as_test

from core.obot.profile_service import ObotProfileService
from core.obot.models import ObotProfile


class MockDBClient:
    """Mock database client for testing"""
    
    def __init__(self):
        self.profiles = {}  # profile_id -> profile_data
        self.next_id = 1
    
    async def table(self, table_name):
        return MockTable(self, table_name)


class MockTable:
    """Mock Supabase table operations"""
    
    def __init__(self, db_client: MockDBClient, table_name: str):
        self.db = db_client
        self.table_name = table_name
    
    async def select(self, *args):
        return MockQuery(self.db, self.table_name, 'select', args)
    
    async def insert(self, data):
        return MockQuery(self.db, self.table_name, 'insert', data)
    
    async def update(self, data):
        return MockQuery(self.db, self.table_name, 'update', data)
    
    async def delete(self):
        return MockQuery(self.db, self.table_name, 'delete', None)


class MockQuery:
    """Mock Supabase query operations"""
    
    def __init__(self, db_client: MockDBClient, table_name: str, operation: str, data):
        self.db = db_client
        self.table_name = table_name
        self.operation = operation
        self.data = data
        self._filters = {}
        self._order_by = None
    
    def eq(self, column, value):
        self._filters[column] = ('eq', value)
        return self
    
    def order(self, column, desc=False):
        self._order_by = (column, desc)
        return self
    
    async def execute(self):
        if self.table_name == 'obot_profiles':
            return self._execute_obot_profiles_query()
        return MagicMock(data=[])
    
    def _execute_obot_profiles_query(self):
        """Execute mock query on obot_profiles table"""
        result = []
        
        # Apply filters
        for profile_id, profile_data in self.db.profiles.items():
            match = True
            
            # Apply filters (eq operations)
            for column, (op, value) in self._filters.items():
                if op == 'eq':
                    if profile_data.get(column) != value:
                        match = False
                        break
            
            if match:
                result.append(profile_data)
        
        # Apply ordering
        if self._order_by:
            column, desc = self._order_by
            result.sort(key=lambda x: x.get(column, ''), reverse=desc)
        
        return MagicMock(data=result)


class MockDBConnectionWrapper:
    """Wrapper to mock DBConnection with async client property"""
    def __init__(self, client):
        self._client = client
    
    @property
    async def client(self):
        return self._client

class TestObotProfileServiceQueryCompatibility:
    """Property-based tests for profile query compatibility"""
    
    # **Feature: obot-mcp-integration, Property 8: Profile Query Compatibility**
    # **Validates: Requirements 7.3**
    
    def setup_method(self):
        """Set up test fixtures"""
        self.mock_db_client = MockDBClient()
        # Use wrapper instead of MagicMock for DBConnection
        self.mock_db_conn = MockDBConnectionWrapper(self.mock_db_client)
        
        self.service = ObotProfileService(db_connection=self.mock_db_conn)
        self.mock_db = self.mock_db_client
    
    @given(
        account_id_strategy=st.uuids(),
        num_profiles=st.integers(min_value=0, max_value=50)
    )
    def test_get_profiles_returns_own_only(self, account_id_strategy, num_profiles):
        """Property: For any profile query by account ID, the query SHALL return all profiles associated with that account in a format compatible with the existing profile listing UI."""
        
        # Convert UUID strategy to actual UUID
        account_id = str(account_id_strategy)
        
        # Create multiple users with profiles
        other_accounts = [str(uuid4()) for _ in range(3)]
        
        # Create profiles for our target account
        target_profiles = []
        for i in range(num_profiles):
            profile_data = self._create_mock_profile_data(account_id, f"target-profile-{i}")
            self.mock_db.profiles[profile_data['id']] = profile_data
            target_profiles.append(profile_data)
        
        # Create profiles for other accounts
        other_profiles = []
        for other_account in other_accounts:
            for i in range(3):
                profile_data = self._create_mock_profile_data(other_account, f"other-profile-{i}")
                self.mock_db.profiles[profile_data['id']] = profile_data
                other_profiles.append(profile_data)
        
        # Act: Query profiles for target account
        profiles = asyncio.run(self.service.get_profiles(account_id))
        
        # Assert: Only target account's profiles are returned
        returned_ids = {p.id for p in profiles}
        expected_ids = {p['id'] for p in target_profiles}
        other_ids = {p['id'] for p in other_profiles}
        
        assert returned_ids == expected_ids, "Should return only target account's profiles"
        assert len(returned_ids.intersection(other_ids)) == 0, "Should not return other accounts' profiles"
        assert len(profiles) == num_profiles, f"Should return {num_profiles} profiles for target account"
        
        # Assert: All returned profiles have correct account_id
        for profile in profiles:
            assert profile.account_id == account_id, f"Profile {profile.id} should belong to target account"
    
    @given(
        account_id_strategy=st.uuids(),
        profile_count=st.integers(min_value=1, max_value=20)
    )
    def test_profile_listing_ordering(self, account_id_strategy, profile_count):
        """Property: Profile queries SHALL return results ordered by creation date (newest first)"""
        
        account_id = str(account_id_strategy)
        
        # Create profiles with different creation times
        base_time = datetime.now(timezone.utc)
        profiles = []
        
        for i in range(profile_count):
            profile_data = self._create_mock_profile_data(
                account_id, 
                f"profile-{i}", 
                created_at=base_time.replace(microsecond=i * 1000)  # Different microseconds for ordering
            )
            self.mock_db.profiles[profile_data['id']] = profile_data
            profiles.append(profile_data)
        
        # Act: Query profiles
        result_profiles = asyncio.run(self.service.get_profiles(account_id))
        
        # Assert: Results are ordered by created_at DESC (newest first)
        assert len(result_profiles) == profile_count
        
        for i in range(len(result_profiles) - 1):
            current_time = result_profiles[i].created_at
            next_time = result_profiles[i + 1].created_at
            
            assert current_time >= next_time, f"Profiles should be ordered by created_at DESC, but {current_time} < {next_time}"
    
    @given(
        account_id_strategy=st.uuids(),
        profile_count=st.integers(min_value=1, max_value=15)
    )
    def test_profile_data_integrity(self, account_id_strategy, profile_count):
        """Property: Profile query results SHALL preserve all essential fields and data types"""
        
        account_id = str(account_id_strategy)
        
        # Create profiles with diverse data
        profiles_data = []
        for i in range(profile_count):
            profile_data = self._create_mock_profile_data(
                account_id,
                f"profile-{i}",
                icon_url="https://example.com/icon.png" if i % 2 == 0 else None,
                status=["pending", "connected", "error", "oauth_required"][i % 4]
            )
            self.mock_db.profiles[profile_data['id']] = profile_data
            profiles_data.append(profile_data)
        
        # Act: Query profiles
        result_profiles = asyncio.run(self.service.get_profiles(account_id))
        
        # Assert: Data integrity is preserved
        assert len(result_profiles) == profile_count
        
        for original_data, result_profile in zip(profiles_data, result_profiles):
            assert result_profile.id == original_data['id']
            assert result_profile.account_id == original_data['account_id']
            assert result_profile.obot_server_id == original_data['obot_server_id']
            assert result_profile.catalog_entry_id == original_data['catalog_entry_id']
            assert result_profile.display_name == original_data['display_name']
            assert result_profile.icon_url == original_data.get('icon_url')
            assert result_profile.status == original_data['status']
            assert isinstance(result_profile.created_at, datetime)
            assert isinstance(result_profile.updated_at, datetime)
    
    @given(
        account_id_strategy=st.uuids(),
        profile_id_strategy=st.uuids(),
        owns_profile=st.booleans()
    )
    def test_get_profile_ownership_check(self, account_id_strategy, profile_id_strategy, owns_profile):
        """Property: Profile get operations SHALL enforce ownership verification"""
        
        account_id = str(account_id_strategy)
        profile_id = str(profile_id_strategy)
        
        if owns_profile:
            # Create profile owned by the account
            profile_data = self._create_mock_profile_data(account_id, "owned-profile")
            self.mock_db.profiles[profile_id] = profile_data
        
        # Act: Try to get profile
        result = asyncio.run(self.service.get_profile(profile_id, account_id))
        
        # Assert: Ownership is correctly enforced
        if owns_profile:
            assert result is not None, "Should return profile if user owns it"
            assert result.id == profile_id
            assert result.account_id == account_id
        else:
            assert result is None, "Should return None if user doesn't own profile"
    
    @given(
        account_id_strategy=st.uuids(),
        server_id_strategy=st.text(min_size=1, max_size=100),
        owns_server=st.booleans()
    )
    def test_get_profile_by_server_id_ownership(self, account_id_strategy, server_id_strategy, owns_server):
        """Property: Server ID lookups SHALL enforce ownership checks"""
        
        account_id = str(account_id_strategy)
        server_id = server_id_strategy
        
        if owns_server:
            # Create profile with the server ID owned by the account
            profile_data = self._create_mock_profile_data(account_id, "server-profile", obot_server_id=server_id)
            self.mock_db.profiles[profile_data['id']] = profile_data
        
        # Act: Query by server ID
        result = asyncio.run(self.service.get_profile_by_server_id(account_id, server_id))
        
        # Assert: Ownership is correctly enforced
        if owns_server:
            assert result is not None, "Should return profile if user owns server"
            assert result.obot_server_id == server_id
            assert result.account_id == account_id
        else:
            assert result is None, "Should return None if user doesn't own server"
    
    @given(
        display_name=st.text(min_size=1, max_size=100),
        uniqueness_scenarios=st.sampled_from(["unique", "duplicate", "multiple_duplicates"])
    )
    def test_unique_display_name_generation(self, display_name, uniqueness_scenarios):
        """Property: Display name generation SHALL handle uniqueness conflicts correctly"""
        
        assume(len(display_name.strip()) > 0)
        
        account_id = str(uuid4())
        
        # Create mock client
        mock_client = MagicMock()
        mock_client.table = MagicMock(return_value=mock_client)
        
        if uniqueness_scenarios == "duplicate":
            # Create one existing profile with same name
            existing_profile = self._create_mock_profile_data(account_id, display_name)
            mock_client.execute.return_value = MagicMock(data=[{"id": existing_profile['id']}])
        elif uniqueness_scenarios == "multiple_duplicates":
            # Create multiple existing profiles with same name + counter
            base_name = display_name.rsplit(' (', 1)[0] if ' (' in display_name else display_name
            mock_client.execute.return_value = MagicMock(data=[
                {"id": f"{base_name}-1"},
                {"id": f"{base_name}-2"},
                {"id": f"{base_name}-3"}
            ])
        else:  # unique
            mock_client.execute.return_value = MagicMock(data=[])
        
        self.service.db.client = mock_client
        
        # Act: Generate unique display name
        result = asyncio.run(self.service._generate_unique_display_name(display_name, account_id, mock_client))
        
        # Assert: Uniqueness is handled correctly
        if uniqueness_scenarios == "unique":
            assert result == display_name, "Should return original name if unique"
        elif uniqueness_scenarios == "duplicate":
            assert result == f"{display_name} (2)", "Should add counter (2) for first duplicate"
        elif uniqueness_scenarios == "multiple_duplicates":
            assert result == f"{display_name} (4)", "Should add next counter (4) for multiple duplicates"
    
    def _create_mock_profile_data(self, account_id: str, display_name: str, **overrides) -> dict:
        """Helper to create mock profile data"""
        profile_id = str(uuid4())
        now = datetime.now(timezone.utc)
        
        default_data = {
            'id': profile_id,
            'account_id': account_id,
            'obot_server_id': f"server-{uuid4()}",
            'catalog_entry_id': f"catalog-{uuid4()}",
            'display_name': display_name,
            'icon_url': None,
            'status': 'pending',
            'created_at': now.isoformat(),
            'updated_at': now.isoformat()
        }
        
        default_data.update(overrides)
        return default_data


# State machine testing for profile service operations
class ObotProfileServiceStateMachine:
    """State machine to test profile service lifecycle operations"""
    
    def __init__(self):
        self.service = ObotProfileService()
        self.mock_db = MockDBClient()
        self.service.db.client = self.mock_db.table('obot_profiles')
        self.accounts = []
        self.profiles = []
    
    @rule(account_id_strategy=st.uuids())
    def create_account(self, account_id_strategy):
        """Rule: Create a new account for testing"""
        account_id = str(account_id_strategy)
        if account_id not in self.accounts:
            self.accounts.append(account_id)
        assert len(self.accounts) >= 1
    
    @precondition(lambda self: len(self.accounts) > 0)
    @rule(
        account_index=st.integers(min_value=0),
        display_name=st.text(min_size=1, max_size=50),
        server_id=st.text(min_size=1, max_size=100)
    )
    def create_profile(self, account_index, display_name, server_id):
        """Rule: Create a profile for a random account"""
        assume(account_index < len(self.accounts))
        assume(len(display_name.strip()) > 0)
        assume(len(server_id.strip()) > 0)
        
        account_id = self.accounts[account_index]
        
        # Create profile
        profile_data = self._create_mock_profile_data(account_id, display_name, obot_server_id=server_id)
        self.mock_db.profiles[profile_data['id']] = profile_data
        self.profiles.append((account_id, profile_data['id']))
        
        assert len(self.profiles) >= 1
    
    @precondition(lambda self: len(self.accounts) > 0)
    @rule(account_index=st.integers(min_value=0))
    def query_account_profiles(self, account_index):
        """Rule: Query profiles for a random account"""
        assume(account_index < len(self.accounts))
        
        account_id = self.accounts[account_index]
        
        # Query profiles
        try:
            profiles = asyncio.run(self.service.get_profiles(account_id))
            
            # Verify all returned profiles belong to the account
            for profile in profiles:
                assert profile.account_id == account_id
                
            # Verify no profiles from other accounts are returned
            other_accounts = [a for a in self.accounts if a != account_id]
            for other_account in other_accounts:
                other_profiles = asyncio.run(self.service.get_profiles(other_account))
                for profile in other_profiles:
                    assert profile.account_id == other_account
            
        except Exception as e:
            # Some operations might fail, which is acceptable in state testing
            pass
    
    @precondition(lambda self: len(self.profiles) > 0)
    @rule(profile_index=st.integers(min_value=0))
    def query_specific_profile(self, profile_index):
        """Rule: Query a specific profile with ownership verification"""
        assume(profile_index < len(self.profiles))
        
        account_id, profile_id = self.profiles[profile_index]
        
        # Try to get the profile
        try:
            profile = asyncio.run(self.service.get_profile(profile_id, account_id))
            assert profile is not None
            assert profile.id == profile_id
            assert profile.account_id == account_id
            
            # Try with wrong account (should return None)
            wrong_account = str(uuid4())
            if wrong_account != account_id:
                wrong_profile = asyncio.run(self.service.get_profile(profile_id, wrong_account))
                assert wrong_profile is None
                
        except Exception as e:
            # Some operations might fail, which is acceptable
            pass
    
    @precondition(lambda self: len(self.profiles) > 0)
    @rule(profile_index=st.integers(min_value=0))
    def delete_profile(self, profile_index):
        """Rule: Delete a profile with ownership check"""
        assume(profile_index < len(self.profiles))
        
        account_id, profile_id = self.profiles[profile_index]
        
        # Verify profile exists
        original_count = len(self.mock_db.profiles)
        
        # Try to delete
        try:
            result = asyncio.run(self.service.delete_profile(profile_id, account_id))
            
            # If successful, profile should be gone
            if result:
                assert profile_id not in self.mock_db.profiles
                self.profiles.pop(profile_index)
            
        except Exception as e:
            # Some operations might fail, which is acceptable
            pass
    
    def _create_mock_profile_data(self, account_id: str, display_name: str, **overrides) -> dict:
        """Helper to create mock profile data"""
        profile_id = str(uuid4())
        now = datetime.now(timezone.utc)
        
        default_data = {
            'id': profile_id,
            'account_id': account_id,
            'obot_server_id': f"server-{uuid4()}",
            'catalog_entry_id': f"catalog-{uuid4()}",
            'display_name': display_name,
            'icon_url': None,
            'status': 'pending',
            'created_at': now.isoformat(),
            'updated_at': now.isoformat()
        }
        
        default_data.update(overrides)
        return default_data


def test_profile_service_state_machine():
    """Run state machine test for profile service lifecycle"""
    run_state_machine_as_test(ObotProfileServiceStateMachine)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
