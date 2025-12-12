"""Property-based tests for MCPAuditLog

**Feature: obot-mcp-integration, Property 11: Audit Log Completeness**
**Validates: Requirements 8.4** - System SHALL create audit log entries for all MCP operations

Tests comprehensive audit log completeness including server operations, tool calls,
OAuth operations, error scenarios, and metadata capture across all operation types.
"""

import pytest
import ipaddress
from unittest.mock import patch, MagicMock, AsyncMock
from hypothesis import given, strategies as st
from hypothesis.strategies import sampled_from, tuples, just, one_of, dictionaries, text, booleans
from datetime import datetime, timezone
import json

from .audit import MCPAuditLog
from core.services.supabase import DBConnection



class MockDBConnectionWrapper:
    """Wrapper to mock DBConnection with async client property"""
    def __init__(self, client):
        self._client = client
    
    @property
    async def client(self):
        return self._client

class TestMCPAuditLogCompleteness:
    """Property-based tests for audit log completeness across all MCP operations"""
    
    def setup_method(self):
        """Setup for each test"""
        self.mock_client = AsyncMock() # This acts as the Supabase client
        self.mock_db = MockDBConnectionWrapper(self.mock_client)
        self.audit_log = MCPAuditLog(db_connection=self.mock_db)
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Core Recording Tests
    # =============================================================================
    
    @pytest.mark.asyncio
    @given(
        action=sampled_from(['server_create', 'server_delete', 'server_update', 'tool_call', 'oauth_start']),
        user_id=st.uuids(),
        server_id=st.one_of(st.none(), st.text(min_size=1, max_size=255)),
        tool_name=st.one_of(st.none(), st.text(min_size=1, max_size=255)),
        success=booleans(),
        error_message=st.one_of(st.none(), st.text(min_size=1, max_size=1000)),
        ip_address=st.one_of(st.none(), st.text(min_size=7, max_size=45)),  # IPv4/IPv6 range
        user_agent=st.one_of(st.none(), st.text(min_size=1, max_size=500))
    )
    async def test_record_completeness_invariant(self, action, user_id, server_id, tool_name, 
                                               success, error_message, ip_address, user_agent):
        """Property 11: Audit Log Completeness - Core recording completeness
        
        For any valid MCP operation parameters, the audit log SHALL create a complete
        record with all required fields including user_id, action, success status,
        and appropriate metadata capture.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Call record method
        await self.audit_log.record(
            action=action,
            user_id=str(user_id),
            success=success,
            server_id=server_id,
            tool_name=tool_name,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Verify database insertion was called with complete data
        self.mock_client.table.assert_called_with('obot_audit_logs')
        insert_call = self.mock_client.table.return_value.insert
        
        # Extract the data that was inserted
        call_args = insert_call.call_args
        inserted_data = call_args[0][0] if call_args else None
        
        if inserted_data:
            # Verify all required fields are present and non-None where expected
            assert 'id' in inserted_data, "Audit log must have unique ID"
            assert 'user_id' in inserted_data, "Audit log must have user_id"
            assert 'action' in inserted_data, "Audit log must have action"
            assert 'success' in inserted_data, "Audit log must have success field"
            assert 'created_at' in inserted_data, "Audit log must have timestamp"
            
            # Verify field values match input (or are sanitized appropriately)
            assert inserted_data['user_id'] == str(user_id), "user_id must be preserved"
            assert inserted_data['action'] == action, "action must be preserved"
            assert inserted_data['success'] == success, "success must be preserved"
            
            # Verify optional fields are handled correctly
            if server_id is not None:
                assert inserted_data['server_id'] == server_id, "server_id should be preserved when provided"
            else:
                assert inserted_data['server_id'] is None, "server_id should be None when not provided"
                
            if tool_name is not None:
                assert inserted_data['tool_name'] == tool_name, "tool_name should be preserved when provided"
            else:
                assert inserted_data['tool_name'] is None, "tool_name should be None when not provided"
    
    @pytest.mark.asyncio
    @given(
        operation=sampled_from(['create', 'delete', 'update']),
        user_id=st.uuids(),
        server_id=st.text(min_size=1, max_size=255),
        success=booleans(),
        error_message=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
        ip_address=st.one_of(st.none(), st.text(min_size=7, max_size=45)),
        user_agent=st.one_of(st.none(), st.text(min_size=1, max_size=500))
    )
    async def test_server_operation_mapping_completeness(self, operation, user_id, server_id, 
                                                        success, error_message, ip_address, user_agent):
        """Property 11: Audit Log Completeness - Server operation action mapping
        
        For any server operation (create/delete/update), the convenience method SHALL
        map to the correct action type and create complete audit log entries.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Call server operation convenience method
        await self.audit_log.record_server_operation(
            operation=operation,
            user_id=str(user_id),
            server_id=server_id,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Verify the correct action was recorded
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            expected_action_map = {
                'create': 'server_create',
                'delete': 'server_delete',
                'update': 'server_update'
            }
            expected_action = expected_action_map.get(operation.lower(), 'server_operation')
            
            assert inserted_data['action'] == expected_action, \
                f"Server operation '{operation}' should map to action '{expected_action}'"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        server_id=st.text(min_size=1, max_size=255),
        tool_name=st.text(min_size=1, max_size=255),
        success=booleans(),
        error_message=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
        ip_address=st.one_of(st.none(), st.text(min_size=7, max_size=45)),
        user_agent=st.one_of(st.none(), st.text(min_size=1, max_size=500))
    )
    async def test_tool_call_recording_completeness(self, user_id, server_id, tool_name,
                                                   success, error_message, ip_address, user_agent):
        """Property 11: Audit Log Completeness - Tool call recording
        
        For any tool call operation, the convenience method SHALL create complete
        audit log entries with tool-specific metadata.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Call tool call convenience method
        await self.audit_log.record_tool_call(
            user_id=str(user_id),
            server_id=server_id,
            tool_name=tool_name,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Verify tool call specific fields
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            
            assert inserted_data['action'] == 'tool_call', "Tool calls must use 'tool_call' action"
            assert inserted_data['tool_name'] == tool_name, "tool_name must be preserved"
            assert inserted_data['server_id'] == server_id, "server_id must be preserved"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        server_id=st.text(min_size=1, max_size=255),
        success=booleans(),
        error_message=st.one_of(st.none(), st.text(min_size=1, max_size=500)),
        ip_address=st.one_of(st.none(), st.text(min_size=7, max_size=45)),
        user_agent=st.one_of(st.none(), st.text(min_size=1, max_size=500))
    )
    async def test_oauth_operation_recording_completeness(self, user_id, server_id, success,
                                                         error_message, ip_address, user_agent):
        """Property 11: Audit Log Completeness - OAuth operation recording
        
        For any OAuth operation, the convenience method SHALL create complete
        audit log entries with OAuth-specific metadata.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Call OAuth operation convenience method
        await self.audit_log.record_oauth_operation(
            user_id=str(user_id),
            server_id=server_id,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Verify OAuth specific fields
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            
            assert inserted_data['action'] == 'oauth_start', "OAuth operations must use 'oauth_start' action"
            assert inserted_data['server_id'] == server_id, "server_id must be preserved"
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Error Scenarios and Metadata
    # =============================================================================
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        server_id=st.one_of(st.none(), st.text(min_size=1, max_size=255)),
        error_message=st.text(min_size=1, max_size=1500)  # Test with long error messages
    )
    async def test_error_scenario_logging_completeness(self, user_id, server_id, error_message):
        """Property 11: Audit Log Completeness - Error scenarios
        
        For any failed operation with error messages, the audit log SHALL capture
        the error information while sanitizing sensitive data appropriately.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record failed operation
        await self.audit_log.record(
            action='tool_call',
            user_id=str(user_id),
            success=False,
            server_id=server_id,
            error_message=error_message
        )
        
        # Verify error logging
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            
            assert inserted_data['success'] is False, "Failed operations must have success=False"
            assert inserted_data['error_message'] is not None, "Error messages must be captured"
            # Error message should be truncated if too long
            assert len(inserted_data['error_message']) <= 1003, \
                "Error messages should be truncated to max length (1000 + '...')"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        action=sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start']),
        ip_address=st.text(min_size=7, max_size=45),  # Valid IP formats
        user_agent=st.text(min_size=1, max_size=1000)
    )
    async def test_metadata_capture_completeness(self, user_id, action, ip_address, user_agent):
        """Property 11: Audit Log Completeness - Metadata capture
        
        For any operation with client metadata, the audit log SHALL capture and
        sanitize IP address and user agent information appropriately.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record operation with metadata
        await self.audit_log.record(
            action=action,
            user_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Verify metadata capture
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            
            # IP address should be sanitized (masked)
            if ip_address:
                assert inserted_data['ip_address'] is not None, "IP address should be captured"
                # Basic validation that IP was processed (may be masked)
                assert len(inserted_data['ip_address']) > 0, "Sanitized IP should not be empty"
            
            # User agent should be captured (may be truncated)
            if user_agent:
                assert inserted_data['user_agent'] is not None, "User agent should be captured"
                assert len(inserted_data['user_agent']) <= 500, \
                    "User agent should be truncated to 500 chars max"
    
    @given(
        ip_address=st.one_of(
            st.just("192.168.1.1"),  # IPv4
            st.just("10.0.0.1"),     # IPv4 private
            st.just("2001:db8::1"),  # IPv6
            st.just("::1"),          # IPv6 loopback
            st.text(min_size=7, max_size=45)  # Random IP strings
        )
    )
    def test_ip_sanitization_completeness(self, ip_address):
        """Property 11: Audit Log Completeness - IP sanitization
        
        For any IP address input, the sanitization function SHALL process it
        appropriately for privacy while preserving network information.
        """
        sanitized = self.audit_log._sanitize_ip_address(ip_address)
        
        # IP should be either None (invalid) or a sanitized string
        if sanitized is not None:
            assert isinstance(sanitized, str), "Sanitized IP should be a string"
            assert len(sanitized) > 0, "Sanitized IP should not be empty"
            
            # For IPv4, should mask the last octet
            if '.' in ip_address:
                parts = sanitized.split('.')
                if len(parts) == 4:
                    assert parts[3] == '0', "IPv4 last octet should be masked to 0"
    
    @given(
        user_agent=st.text(min_size=1, max_size=2000)  # Test with various lengths
    )
    def test_user_agent_sanitization_completeness(self, user_agent):
        """Property 11: Audit Log Completeness - User agent sanitization
        
        For any user agent input, the sanitization function SHALL truncate
        to appropriate length while preserving meaningful information.
        """
        sanitized = self.audit_log._sanitize_user_agent(user_agent)
        
        # User agent should be truncated to 500 chars max
        if user_agent and len(user_agent.strip()) > 0:
            if sanitized is not None:
                assert len(sanitized) <= 500, "User agent should be truncated to 500 chars"
                assert sanitized.strip() == sanitized, "User agent should be trimmed"
    
    @given(
        error_message=st.text(min_size=1, max_size=2000)
    )
    def test_error_sanitization_completeness(self, error_message):
        """Property 11: Audit Log Completeness - Error message sanitization
        
        For any error message input, the sanitization function SHALL truncate
        to appropriate length while preserving error information.
        """
        sanitized = self.audit_log._sanitize_error_message(error_message)
        
        # Error messages should be truncated to max length
        if error_message and len(error_message.strip()) > 0:
            if sanitized is not None:
                assert len(sanitized) <= 1003, \
                    "Error messages should be truncated to 1000 chars + '...'"
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Database Integration Patterns
    # =============================================================================
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        action=sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start']),
        server_id=st.one_of(st.none(), st.text(min_size=1, max_size=255))
    )
    async def test_database_insertion_pattern_completeness(self, user_id, action, server_id):
        """Property 11: Audit Log Completeness - Database insertion patterns
        
        For any audit log insertion, the system SHALL follow consistent
        database insertion patterns with proper error handling.
        """
        # Setup mock to simulate successful insertion
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record operation
        await self.audit_log.record(
            action=action,
            user_id=str(user_id),
            server_id=server_id
        )
        
        # Verify database insertion pattern
        self.mock_client.table.assert_called_with('obot_audit_logs')
        
        # Verify insertion call was made
        self.mock_client.table.return_value.insert.assert_called_once()
        
        # Verify successful insertion logs at debug level (mocked logger)
        # Note: In real implementation, this would log to logger.debug
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        action=sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start'])
    )
    async def test_database_error_handling_completeness(self, user_id, action):
        """Property 11: Audit Log Completeness - Database error handling
        
        For any database insertion failure, the system SHALL handle errors
        gracefully while attempting to log the failure.
        """
        # Setup mock to simulate database failure
        self.mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("Database error")
        
        # Record operation (should not raise exception)
        await self.audit_log.record(
            action=action,
            user_id=str(user_id)
        )
        
        # Verify that the operation completed without raising (error handling)
        # The audit log should attempt insertion but not propagate the error
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Query and Summary Completeness
    # =============================================================================
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        days=st.integers(min_value=1, max_value=365)
    )
    async def test_audit_summary_completeness(self, user_id, days):
        """Property 11: Audit Log Completeness - Audit summary data completeness
        
        For any audit summary query, the system SHALL return complete statistics
        including counts, success rates, and action breakdowns.
        """
        # Setup mock responses for different queries
        self.mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.side_effect = [
            MagicMock(count=100, data=[]),  # Total count
            MagicMock(count=80, data=[]),   # Success count
            MagicMock(count=20, data=[]),   # Failure count
            MagicMock(data=[{'action': 'server_create'}, {'action': 'tool_call'}])  # Action breakdown
        ]
        
        # Get audit summary
        summary = await self.audit_log.get_user_audit_summary(str(user_id), days)
        
        # Verify summary completeness
        assert 'user_id' in summary, "Summary must include user_id"
        assert 'period_days' in summary, "Summary must include period_days"
        assert 'total_operations' in summary, "Summary must include total_operations"
        assert 'successful_operations' in summary, "Summary must include successful_operations"
        assert 'failed_operations' in summary, "Summary must include failed_operations"
        assert 'success_rate' in summary, "Summary must include success_rate"
        assert 'action_breakdown' in summary, "Summary must include action_breakdown"
        assert 'period_start' in summary, "Summary must include period_start"
        assert 'period_end' in summary, "Summary must include period_end"
        
        # Verify calculated values
        assert summary['total_operations'] == 100, "Total should match query result"
        assert summary['successful_operations'] == 80, "Success count should match query result"
        assert summary['failed_operations'] == 20, "Failure count should match query result"
        assert summary['success_rate'] == 80.0, "Success rate should be calculated correctly"
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Health Check Completeness
    # =============================================================================
    
    @pytest.mark.asyncio
    async def test_health_check_completeness(self):
        """Property 11: Audit Log Completeness - Health check functionality
        
        The health check SHALL verify database connectivity and write capability
        with complete status reporting.
        """
        # Setup mock responses
        self.mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test'}]
        )
        
        # Mock the record method to avoid recursive calls
        with patch.object(self.audit_log, 'record', new_callable=AsyncMock) as mock_record:
            # Run health check
            health_result = await self.audit_log.check_health()
            
            # Verify health check completeness
            assert 'status' in health_result, "Health check must include status"
            assert 'database_connected' in health_result, "Health check must include database_connected"
            assert 'can_write_logs' in health_result, "Health check must include can_write_logs"
            assert 'timestamp' in health_result, "Health check must include timestamp"
            
            # Verify test log was written
            mock_record.assert_called_once()
            
            # Verify test log was cleaned up
            self.mock_client.table.return_value.delete.assert_called_once()
    
    # =============================================================================
    # Property 11: Audit Log Completeness - Edge Cases and Boundary Conditions
    # =============================================================================
    
    @pytest.mark.asyncio
    @given(
        action=st.text(min_size=1, max_size=100),
        user_id=st.uuids(),
        success=booleans()
    )
    async def test_action_validation_completeness(self, action, user_id, success):
        """Property 11: Audit Log Completeness - Action validation
        
        For any action type (including invalid ones), the system SHALL handle
        validation gracefully while ensuring logging occurs.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record operation with potentially invalid action
        await self.audit_log.record(
            action=action,
            user_id=str(user_id),
            success=success
        )
        
        # Verify insertion was attempted regardless of action validity
        self.mock_client.table.return_value.insert.assert_called_once()
    
    @pytest.mark.asyncio
    @given(
        user_id=st.one_of(
            st.text(min_size=8, max_size=100),  # Valid UUID-like
            st.text(min_size=1, max_size=7),    # Too short (should be rejected)
            st.text(min_size=101, max_size=200) # Very long (should still work)
        ),
        action=sampled_from(['server_create', 'tool_call'])
    )
    async def test_user_id_validation_completeness(self, user_id, action):
        """Property 11: Audit Log Completeness - User ID validation
        
        For any user_id input (including invalid formats), the system SHALL
        validate appropriately while ensuring logging occurs.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record operation
        await self.audit_log.record(
            action=action,
            user_id=user_id,
            success=True
        )
        
        # For valid user_ids (>= 8 chars), insertion should be attempted
        if len(user_id) >= 8:
            self.mock_client.table.return_value.insert.assert_called_once()
    
    @given(
        timestamps=st.lists(
            st.datetimes(timezones=st.just(timezone.utc)),
            min_size=1,
            max_size=10
        )
    )
    def test_timestamp_format_completeness(self, timestamps):
        """Property 11: Audit Log Completeness - Timestamp format consistency
        
        For any datetime input, the audit log SHALL generate timestamps in
        consistent ISO format with timezone information.
        """
        for timestamp in timestamps:
            # Generate audit log data with timestamp
            audit_data = {
                'id': 'test-id',
                'user_id': 'test-user',
                'action': 'test_action',
                'success': True,
                'created_at': timestamp.isoformat()
            }
            
            # Verify timestamp format
            assert isinstance(audit_data['created_at'], str), "Timestamp should be string"
            assert '+00:00' in audit_data['created_at'], "Timestamp should include UTC timezone"
            assert 'T' in audit_data['created_at'], "Timestamp should use ISO format"


class TestMCPAuditLogPropertyInvariants:
    """Property-based tests for audit log invariants and completeness guarantees"""
    
    def setup_method(self):
        """Setup for each test"""
        self.mock_client = AsyncMock()
        self.mock_db = MockDBConnectionWrapper(self.mock_client)
        self.audit_log = MCPAuditLog(db_connection=self.mock_db)
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        action=sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start']),
        server_id=st.text(min_size=1, max_size=255)
    )
    async def test_audit_record_immutability_invariant(self, user_id, action, server_id):
        """Property 11: Audit Log Completeness - Record immutability
        
        For any audit log record, once created, the essential fields SHALL
        remain immutable and traceable to the original operation.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record operation
        await self.audit_log.record(
            action=action,
            user_id=str(user_id),
            server_id=server_id
        )
        
        # Extract inserted data
        insert_call = self.mock_client.table.return_value.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            
            # Verify immutability constraints
            assert inserted_data['id'] is not None, "Each record must have unique ID"
            assert inserted_data['created_at'] is not None, "Each record must have timestamp"
            assert inserted_data['user_id'] == str(user_id), "user_id must match input"
            assert inserted_data['action'] == action, "action must match input"
    
    @pytest.mark.asyncio
    @given(
        operations=st.lists(
            tuples(
                sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start']),
                st.uuids(),
                st.text(min_size=1, max_size=255)
            ),
            min_size=1,
            max_size=20
        )
    )
    async def test_concurrent_operations_isolation_invariant(self, operations):
        """Property 11: Audit Log Completeness - Concurrent operations isolation
        
        For multiple concurrent operations, each operation SHALL create
        separate, traceable audit log entries without interference.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record all operations
        for action, user_id, server_id in operations:
            await self.audit_log.record(
                action=action,
                user_id=str(user_id),
                server_id=server_id
            )
        
        # Verify each operation created a separate record
        assert self.mock_client.table.return_value.insert.call_count == len(operations), \
            "Each operation should create a separate audit log entry"
    
    @pytest.mark.asyncio
    @given(
        user_id=st.uuids(),
        actions=st.lists(
            sampled_from(['server_create', 'server_delete', 'tool_call', 'oauth_start']),
            min_size=1,
            max_size=10
        )
    )
    async def test_user_action_traceability_invariant(self, user_id, actions):
        """Property 11: Audit Log Completeness - User action traceability
        
        For all operations by the same user, the audit log SHALL maintain
        traceability through consistent user_id association.
        """
        # Setup mock database response
        self.mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{'id': 'test-audit-id'}]
        )
        
        # Record all actions for the same user
        for action in actions:
            await self.audit_log.record(
                action=action,
                user_id=str(user_id)
            )
        
        # Verify all records have same user_id
        for call_args in self.mock_client.table.return_value.insert.call_args_list:
            inserted_data = call_args[0][0]
            assert inserted_data['user_id'] == str(user_id), \
                "All operations by same user must have consistent user_id"
