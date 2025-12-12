"""Unit tests for Obot client basic functionality"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from core.obot.client import ObotClient, ObotClientError, ObotConnectionError, ObotAuthenticationError
from core.obot.models import MCPCatalogEntry, MCPServer, MCPTool, CreateMCPServerRequest


class TestObotClientBasic:
    """Basic unit tests for Obot client"""
    
    def test_client_initialization(self):
        """Test client initialization with valid configuration"""
        with patch.dict(os.environ, {
            'OBOT_BASE_URL': 'http://test-obot:8080/api',
            'OBOT_BOOTSTRAP_TOKEN': 'test-token'
        }):
            client = ObotClient()
            assert client.base_url == 'http://test-obot:8080/api'
            assert client.bootstrap_token == 'test-token'
            assert client.timeout == 30.0
            assert client.max_retries == 3
            assert client.retry_delay == 1.0
    
    def test_client_initialization_explicit_params(self):
        """Test client initialization with explicit parameters"""
        client = ObotClient(
            base_url='http://explicit:8080',
            bootstrap_token='explicit-token',
            timeout=60.0,
            max_retries=5,
            retry_delay=2.0
        )
        assert client.base_url == 'http://explicit:8080'
        assert client.bootstrap_token == 'explicit-token'
        assert client.timeout == 60.0
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
    
    def test_client_initialization_missing_base_url(self):
        """Test client initialization fails with missing base URL"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Obot base URL must be provided"):
                ObotClient(bootstrap_token="test-token")
    
    def test_client_initialization_missing_bootstrap_token(self):
        """Test client initialization fails with missing bootstrap token"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Obot bootstrap token must be provided"):
                ObotClient(base_url="http://test:8080")
    
    @pytest.mark.asyncio
    async def test_check_health_success(self):
        """Test health check with successful response"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "version": "1.0.0",
                "status": "healthy"
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            health = await client.check_health()
            
            assert health.version == "1.0.0"
            assert health.status == "healthy"
            mock_request.assert_called_once_with("GET", "/version")
    
    @pytest.mark.asyncio
    async def test_check_health_failure(self):
        """Test health check with connection failure"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.side_effect = ObotClientError("Service unavailable")
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            
            with pytest.raises(ObotConnectionError, match="Obot service health check failed"):
                await client.check_health()
    
    @pytest.mark.asyncio
    async def test_list_catalog_entries(self):
        """Test listing catalog entries"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "entries": [
                    {
                        "id": "test-entry-1",
                        "name": "Test Server 1",
                        "description": "A test server",
                        "runtime": "single-user",
                        "editable": True
                    },
                    {
                        "id": "test-entry-2",
                        "name": "Test Server 2",
                        "runtime": "remote",
                        "editable": False
                    }
                ],
                "total": 2,
                "page": 1,
                "per_page": 50
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            result = await client.list_catalog_entries()
            
            assert len(result.entries) == 2
            assert result.total == 2
            assert result.page == 1
            assert result.per_page == 50
            
            # Check first entry
            entry1 = result.entries[0]
            assert entry1.id == "test-entry-1"
            assert entry1.name == "Test Server 1"
            assert entry1.description == "A test server"
            assert entry1.runtime == "single-user"
            assert entry1.editable == True
            
            # Check second entry
            entry2 = result.entries[1]
            assert entry2.id == "test-entry-2"
            assert entry2.name == "Test Server 2"
            assert entry2.runtime == "remote"
            assert entry2.editable == False
    
    @pytest.mark.asyncio
    async def test_get_catalog_entry(self):
        """Test getting specific catalog entry"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "id": "specific-entry",
                "name": "Specific Server",
                "description": "A specific test server",
                "runtime": "single-user",
                "editable": True,
                "catalog_name": "test-catalog"
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            entry = await client.get_catalog_entry("specific-entry")
            
            assert entry.id == "specific-entry"
            assert entry.name == "Specific Server"
            assert entry.description == "A specific test server"
            assert entry.runtime == "single-user"
            assert entry.editable == True
            assert entry.catalog_name == "test-catalog"
            
            mock_request.assert_called_once_with("GET", "/all-mcps/entries/specific-entry")
    
    @pytest.mark.asyncio
    async def test_create_mcp_server(self):
        """Test creating MCP server"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "id": "new-server-123",
                "name": "My Test Server",
                "alias": "my-alias",
                "catalog_entry_id": "test-entry",
                "status": "stopped",
                "configured": False,
                "oauth_required": False
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            request = CreateMCPServerRequest(
                catalog_entry_id="test-entry",
                alias="my-alias",
                env={"API_KEY": "secret"}
            )
            
            server = await client.create_mcp_server(request)
            
            assert server.id == "new-server-123"
            assert server.name == "My Test Server"
            assert server.alias == "my-alias"
            assert server.catalog_entry_id == "test-entry"
            assert server.status == "stopped"
            assert server.configured == False
            assert server.oauth_required == False
            
            # Verify request was made with correct data
            expected_data = {
                "catalog_entry_id": "test-entry",
                "alias": "my-alias",
                "env": {"API_KEY": "secret"}
            }
            mock_request.assert_called_once_with("POST", "/mcp-servers", data=expected_data)
    
    @pytest.mark.asyncio
    async def test_list_mcp_servers(self):
        """Test listing MCP servers"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "servers": [
                    {
                        "id": "server-1",
                        "name": "Server One",
                        "status": "running",
                        "configured": True
                    },
                    {
                        "id": "server-2", 
                        "name": "Server Two",
                        "status": "stopped",
                        "configured": False
                    }
                ],
                "total": 2,
                "page": 1,
                "per_page": 20
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            result = await client.list_mcp_servers(page=1, per_page=20)
            
            assert len(result.servers) == 2
            assert result.total == 2
            assert result.page == 1
            assert result.per_page == 20
            
            server1 = result.servers[0]
            assert server1.id == "server-1"
            assert server1.name == "Server One"
            assert server1.status == "running"
            assert server1.configured == True
            
            server2 = result.servers[1]
            assert server2.id == "server-2"
            assert server2.name == "Server Two"
            assert server2.status == "stopped"
            assert server2.configured == False
    
    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing tools from MCP server"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            mock_request.return_value = {
                "tools": [
                    {
                        "name": "get_data",
                        "description": "Get some data",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"}
                            }
                        },
                        "enabled": True
                    },
                    {
                        "name": "set_data",
                        "description": "Set some data",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"}
                            }
                        },
                        "enabled": False
                    }
                ],
                "total": 2
            }
            
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            result = await client.list_tools("server-123")
            
            assert len(result.tools) == 2
            assert result.total == 2
            
            tool1 = result.tools[0]
            assert tool1.name == "get_data"
            assert tool1.description == "Get some data"
            assert tool1.enabled == True
            assert "query" in tool1.input_schema["properties"]
            
            tool2 = result.tools[1]
            assert tool2.name == "set_data"
            assert tool2.description == "Set some data"
            assert tool2.enabled == False
    
    @pytest.mark.asyncio
    async def test_set_tools(self):
        """Test setting allowed tools for MCP server"""
        with patch('core.obot.client.ObotClient._make_request') as mock_request:
            client = ObotClient(base_url="http://test:8080", bootstrap_token="test")
            await client.set_tools("server-123", ["get_data", "set_data"])
            
            expected_data = {"tool_names": ["get_data", "set_data"]}
            mock_request.assert_called_once_with("PUT", "/mcp-servers/server-123/tools", data=expected_data)


if __name__ == "__main__":
    # Run basic tests
    import sys
    sys.path.insert(0, '.')
    
    # Test client initialization
    print("Testing client initialization...")
    test_client = TestObotClientBasic()
    test_client.test_client_initialization()
    print("✓ Client initialization test passed")
    
    test_client.test_client_initialization_explicit_params()
    print("✓ Explicit parameters test passed")
    
    test_client.test_client_initialization_missing_base_url()
    print("✓ Missing base URL error test passed")
    
    test_client.test_client_initialization_missing_bootstrap_token()
    print("✓ Missing bootstrap token error test passed")
    
    print("\n✓ All unit tests passed!")
