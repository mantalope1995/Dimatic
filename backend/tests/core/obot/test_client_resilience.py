
import pytest
from unittest.mock import Mock, patch, AsyncMock
from core.obot.client import ObotClient, ObotServiceUnavailable, ObotClientError
import httpx
import time

@pytest.fixture
def mock_client():
    client = ObotClient("http://test", "token", max_retries=2)
    # We mock the internal _client to avoid actual network calls
    client._client = AsyncMock(spec=httpx.AsyncClient)
    return client

@pytest.mark.asyncio
async def test_retry_on_500(mock_client):
    """Test that client retries on 500 errors and succeeds eventually"""
    # Mock sequence: 500, 500, 200
    mock_response_500 = Mock(spec=httpx.Response)
    mock_response_500.status_code = 500
    mock_response_500.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=Mock(), response=mock_response_500)
    
    mock_response_200 = Mock(spec=httpx.Response)
    mock_response_200.status_code = 200
    mock_response_200.raise_for_status.return_value = None
    
    # Configure side effects for request
    mock_client._client.request.side_effect = [mock_response_500, mock_response_500, mock_response_200]
    
    # Reduce sleep time for test
    with patch("asyncio.sleep", new_callable=AsyncMock):
        response = await mock_client._get("/test")
    
    assert response.status_code == 200
    assert mock_client._client.request.call_count == 3
    assert mock_client.circuit_breaker.failures == 0  # Should reset on success

@pytest.mark.asyncio
async def test_circuit_breaker_trips(mock_client):
    """Test that circuit breaker trips after threshold failures"""
    # Mock persistent failure
    mock_response_500 = Mock(spec=httpx.Response)
    mock_response_500.status_code = 500
    mock_response_500.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=Mock(), response=mock_response_500)
    
    mock_client._client.request.return_value = mock_response_500
    
    # Configure breaker for easy tripping
    mock_client.max_retries = 0 
    mock_client.circuit_breaker.failure_threshold = 3
    
    with patch("asyncio.sleep", new_callable=AsyncMock):
        # 1st call
        with pytest.raises(ObotServiceUnavailable):
            await mock_client._get("/test")
        assert mock_client.circuit_breaker.failures == 1
        
        # 2nd call
        with pytest.raises(ObotServiceUnavailable):
            await mock_client._get("/test")
        assert mock_client.circuit_breaker.failures == 2
        
        # 3rd call -> Trip
        with pytest.raises(ObotServiceUnavailable):
            await mock_client._get("/test")
        assert mock_client.circuit_breaker.failures == 3
        assert mock_client.circuit_breaker.is_open

        # 4th call -> Circuit Open Exception immediately
        with pytest.raises(ObotServiceUnavailable, match="circuit open"):
            await mock_client._get("/test")
    
    assert mock_client._client.request.call_count == 3 # Should not have called 4th time

@pytest.mark.asyncio
async def test_400_does_not_trip_breaker(mock_client):
    """Test that 400 errors do not count as failures for circuit breaker"""
    mock_response_400 = Mock(spec=httpx.Response)
    mock_response_400.status_code = 400
    mock_response_400.raise_for_status.side_effect = httpx.HTTPStatusError("400", request=Mock(), response=mock_response_400)
    
    mock_client._client.request.return_value = mock_response_400
    mock_client.max_retries = 0
    
    with pytest.raises(ObotClientError, match="Client error"):
        await mock_client._get("/test")
        
    assert mock_client.circuit_breaker.failures == 0
    assert not mock_client.circuit_breaker.is_open

@pytest.mark.asyncio
async def test_circuit_breaker_recovery(mock_client):
    """Test that circuit breaker recovers after timeout"""
    mock_client.circuit_breaker.is_open = True
    mock_client.circuit_breaker.failures = 5
    mock_client.circuit_breaker.last_failure_time = 100.0
    mock_client.circuit_breaker.recovery_timeout = 60.0
    
    # Mock time to be before recovery
    with patch("time.time", return_value=120.0):
        assert not mock_client.circuit_breaker.allow_request()
        
    # Mock time to be after recovery
    with patch("time.time", return_value=170.0):
        assert mock_client.circuit_breaker.allow_request()
        
    # Simulate successful probe
    mock_response_200 = Mock(spec=httpx.Response)
    mock_response_200.status_code = 200
    mock_response_200.raise_for_status.return_value = None
    mock_client._client.request.return_value = mock_response_200
    
    with patch("time.time", return_value=170.0):
        await mock_client._get("/test")
        
    assert not mock_client.circuit_breaker.is_open
    assert mock_client.circuit_breaker.failures == 0
