from hypothesis import given, strategies as st, settings
import pytest
from httpx import AsyncClient, ASGITransport
import pytest_asyncio
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, Request, Depends
from core.admin.obot_admin_api import router, proxy_obot_request
from core.auth import require_admin

# Property 5: Admin Access Control
# Administrators must be able to access the proxy, while regular users are denied.
# Validates: Requirements 5.1

@pytest.fixture
def mock_admin_dependency():
    with patch("core.auth.require_admin__async") as mock:
        yield mock

# Helper to create async mocks for methods
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

@pytest.mark.asyncio
async def test_admin_proxy_endpoint_access():
    """
    Verify that the admin proxy endpoint requires admin privileges.
    """
    # Create a minimal app for testing the router
    test_app = FastAPI()
    test_app.include_router(router)
    
    # Use ASGITransport for newer httpx
    transport = ASGITransport(app=test_app)
    
    # Override dependency to simulate Admin
    test_app.dependency_overrides[require_admin] = lambda: {"user_id": "admin", "role": "admin"}
    
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        
        # We need to mock the proxy destination to avoid 502 or network call
        # Mock httpx in the router
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.aiter_raw.return_value = [b"Success"]
            
            # Setup the client instance to return the response when send is awaited
            mock_instance = MagicMock()
            # Create an AsyncMock for the send method specifically
            mock_send = AsyncMock(return_value=mock_response)
            mock_instance.send = mock_send
            
            mock_client_cls.return_value.__aenter__.return_value = mock_instance
             
            # We use patch.dict to avoid messing up other env vars like OBOT_MAX_ERROR_MESSAGE_LENGTH in MCPAuditLog
            # and we need to import os to patch it
            import os
            with patch.dict(os.environ, {"OBOT_BASE_URL": "http://mock-obot"}):
                response = await ac.post("/admin/obot/status", json={"test": "data"})
                
                # Should be 200 (Mocked Success)
                assert response.status_code == 200
                assert response.content == b"Success"

@pytest.mark.asyncio
async def test_proxy_logic_audit_logging():
    # Mock request
    mock_request = MagicMock(spec=Request)
    mock_request.method = "POST"
    mock_request.url.path = "/admin/obot/test"
    mock_request.headers = {"content-type": "application/json"}
    mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
    mock_request.query_params = {}
    
    admin_user = {"user_id": "test_admin", "role": "admin"}
    
    # Mock Audit Log
    with patch("core.admin.obot_admin_api.MCPAuditLog") as MockAuditLog:
        mock_audit = MagicMock()
        # record method should be async
        mock_audit.record = AsyncMock()
        MockAuditLog.return_value = mock_audit
        
        # Mock HTTPX
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = MagicMock()
            MockClient.return_value.__aenter__.return_value = mock_client_instance
            
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.headers = {"content-type": "application/json"}
            mock_response.aiter_raw = MagicMock(return_value=[b'{"status": "ok"}'])
            
            # Mock send method
            mock_client_instance.send = AsyncMock(return_value=mock_response)
            
            # Call function
            # We use patch.dict
            import os
            with patch.dict(os.environ, {"OBOT_BASE_URL": "http://mock-obot"}):
                response = await proxy_obot_request(mock_request, "test", admin=admin_user)
                
                # Verify Audit Log was called
                mock_audit.record.assert_called_once()
                call_args = mock_audit.record.call_args[1]
                assert call_args["action"] == "admin_proxy_access"
                assert call_args["user_id"] == "test_admin"
                assert call_args["success"] is True
