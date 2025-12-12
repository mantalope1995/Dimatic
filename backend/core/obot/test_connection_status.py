import pytest
from hypothesis import given, strategies as st
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from .models import MCPServer
from .client import ObotClient

# Property test for connection status accuracy
# We want to ensure that the status returned by the client matches the server state properly
# and that derived fields (like configured, oauth_required) are consistent.

@st.composite
def mcp_server_strategy(draw):
    """Generate random MCPServer states"""
    status = draw(st.sampled_from(["unknown", "pending", "connected", "failed"]))
    configured = draw(st.booleans())
    oauth_required = draw(st.booleans())
    
    # Generate matching oauth_url/missing_vars based on constraints if we wanted to enforce them,
    # but here we test that the client correctly passes through whatever valid JSON it gets.
    # Actually, we are testing the 'get_connection_status' logic in the client we just added?
    # Wait, the client method logic is:
    # return {
    #     "configured": server.configured,
    #     "missingRequiredEnvVars": server.missing_env_vars,
    #     "deploymentStatus": server.status,
    #     "oauthRequired": server.oauth_required,
    #     "oauthUrl": server.oauth_url
    # }
    
    return MCPServer(
        id=str(draw(st.uuids())),
        name=draw(st.text(min_size=1)),
        status=status,
        configured=configured,
        oauth_required=oauth_required,
        oauth_url=draw(st.text(min_size=5)) if oauth_required else None,
        missing_env_vars=draw(st.lists(st.text(min_size=1))),
        catalog_entry_id=draw(st.text(min_size=1)),
        catalog_id=draw(st.text(min_size=1))
    )

@given(server=mcp_server_strategy())
@pytest.mark.asyncio
async def test_connection_status_accuracy(server):
    """
    Property: The connection status dictionary returned by get_connection_status
    must accurately reflect the underlying MCPServer attributes.
    """
    # Mock client/API interaction
    client = ObotClient(base_url="http://test", bootstrap_token="test")
    client.get_mcp_server = AsyncMock(return_value=server)
    
    # Execute
    status = await client.get_connection_status("server-id")
    
    # Verify properties
    assert status["configured"] == server.configured
    assert status["deploymentStatus"] == server.status
    assert status["oauthRequired"] == server.oauth_required
    assert status["missingRequiredEnvVars"] == server.missing_env_vars
    assert status["oauthUrl"] == server.oauth_url

    # Invariants
    if status["deploymentStatus"] == "connected":
        # If connected, typically it should be configured (though this depends on server logic, 
        # let's assume loose coupling for now, but strict mapping check is key)
        pass
        
    if status["oauthRequired"]:
        # If oauth required, we might expect a URL, though not strictly enforced by type system
        if server.oauth_url:
            assert status["oauthUrl"] is not None
