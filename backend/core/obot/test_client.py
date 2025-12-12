"""Property-based tests for ObotClient

**Feature: obot-mcp-integration, Property 7: Environment Configuration Parsing**
**Validates: Requirements 1.3**

Tests environment variable parsing and configuration handling.
"""

import os
import pytest
import httpx
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st
from hypothesis.strategies import sampled_from, tuples, just, one_of, dictionaries

from .client import ObotClient, create_obot_client, ObotClientError


class TestObotClientConfiguration:
    """Test ObotClient configuration parsing and environment handling"""
    
    def test_client_initialization(self):
        """Test basic ObotClient initialization"""
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token="test-token",
            timeout=30.0,
            max_retries=3
        )
        
        assert client.base_url == "http://localhost:8080/api"
        assert client.bootstrap_token == "test-token"
        assert client.timeout == 30.0
        assert client.max_retries == 3
    
    def test_base_url_trailing_slash_removal(self):
        """Test that trailing slashes are removed from base_url"""
        client = ObotClient(
            base_url="http://localhost:8080/api/",
            bootstrap_token="test-token"
        )
        
        assert client.base_url == "http://localhost:8080/api"
    
    @given(st.text(min_size=1, max_size=100))
    def test_base_url_validation(self, base_url):
        """Property 7: Environment Configuration Parsing - Base URL validation
        
        For any valid base URL string, the client should store it correctly
        """
        # Ensure no trailing slash for consistent behavior
        expected_base = base_url.rstrip('/')
        
        client = ObotClient(
            base_url=base_url,
            bootstrap_token="test-token"
        )
        
        assert client.base_url == expected_base
    
    @given(st.text(min_size=1, max_size=200))
    def test_bootstrap_token_validation(self, token):
        """Property 7: Environment Configuration Parsing - Bootstrap token validation
        
        For any non-empty bootstrap token, the client should store it correctly
        """
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token=token
        )
        
        assert client.bootstrap_token == token
    
    @given(st.floats(min_value=1.0, max_value=300.0))
    def test_timeout_validation(self, timeout):
        """Property 7: Environment Configuration Parsing - Timeout validation
        
        For any timeout between 1 and 300 seconds, the client should accept it
        """
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token="test-token",
            timeout=timeout
        )
        
        assert client.timeout == timeout
    
    @given(st.integers(min_value=0, max_value=10))
    def test_max_retries_validation(self, max_retries):
        """Property 7: Environment Configuration Parsing - Max retries validation
        
        For any max_retries between 0 and 10, the client should accept it
        """
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token="test-token",
            max_retries=max_retries
        )
        
        assert client.max_retries == max_retries
    
    def test_create_obot_client_from_env_missing_token(self):
        """Test create_obot_client raises error when OBOT_BOOTSTRAP_TOKEN is missing"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OBOT_BOOTSTRAP_TOKEN environment variable is required"):
                create_obot_client()
    
    def test_create_obot_client_from_env_default_base_url(self):
        """Test create_obot_client uses default base URL when not provided"""
        with patch.dict(os.environ, {"OBOT_BOOTSTRAP_TOKEN": "test-token"}):
            with patch('core.obot.client.ObotClient') as mock_client_class:
                create_obot_client()
                
                mock_client_class.assert_called_once_with(
                    base_url="http://localhost:8080/api",
                    bootstrap_token="test-token"
                )
    
    @given(
        st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=('Cc', 'Cs'))),
        st.text(min_size=1, max_size=500, alphabet=st.characters(blacklist_categories=('Cc', 'Cs')))
    )
    def test_create_obot_client_from_env_custom_values(self, base_url, token):
        """Property 7: Environment Configuration Parsing - Custom environment values
        
        For any non-empty base URL and token, create_obot_client should use them
        """
        with patch.dict(os.environ, {
            "OBOT_BASE_URL": base_url,
            "OBOT_BOOTSTRAP_TOKEN": token
        }):
            with patch('core.obot.client.ObotClient') as mock_client_class:
                create_obot_client()
                
                expected_base = base_url.rstrip('/')
                mock_client_class.assert_called_once_with(
                    base_url=base_url,
                    bootstrap_token=token
                )
    
    def test_client_headers_configuration(self):
        """Test that client is configured with correct headers"""
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token="test-token"
        )
        
        # Check that httpx client has correct headers
        assert client._client.headers["Content-Type"] == "application/json"
        assert client._client.headers["User-Agent"] == "Suna-Obot-Client/1.0"
    
    def test_context_manager_functionality(self):
        """Test that client works as async context manager"""
        import asyncio
        
        async def test_async_context():
            async with ObotClient(
                base_url="http://localhost:8080/api",
                bootstrap_token="test-token"
            ) as client:
                assert client.base_url == "http://localhost:8080/api"
                assert client.bootstrap_token == "test-token"
                # Client should be properly initialized
        
        asyncio.run(test_async_context())
    
    @given(st.one_of(st.text(min_size=1, max_size=100), st.none()))
    def test_base_url_with_special_characters(self, base_url):
        """Property 7: Environment Configuration Parsing - Special characters handling
        
        For any base URL with special characters, the client should handle them correctly
        """
        if base_url is None:
            return  # Skip None case for this test
        
        client = ObotClient(
            base_url=base_url,
            bootstrap_token="test-token"
        )
        
        # Client should accept the URL without modification (except trailing slash)
        assert client.base_url == base_url.rstrip('/')
    
    def test_empty_string_base_url(self):
        """Test that empty string base URL is handled"""
        client = ObotClient(
            base_url="",
            bootstrap_token="test-token"
        )
        
        assert client.base_url == ""
    
    def test_invalid_timeout_raises_error(self):
        """Test that invalid timeout values are handled gracefully"""
        # Negative timeout
        with pytest.raises((ValueError, TypeError, httpx.InvalidURL)):
            ObotClient(
                base_url="http://localhost:8080/api",
                bootstrap_token="test-token",
                timeout=-1
            )
        
        # Zero timeout
        with pytest.raises((ValueError, TypeError, httpx.InvalidURL)):
            ObotClient(
                base_url="http://localhost:8080/api",
                bootstrap_token="test-token",
                timeout=0
            )
    
    def test_invalid_max_retries_raises_error(self):
        """Test that invalid max_retries values are handled"""
        # Negative retries
        with pytest.raises((ValueError, TypeError)):
            ObotClient(
                base_url="http://localhost:8080/api",
                bootstrap_token="test-token",
                max_retries=-1
            )


class TestObotClientPropertyInvariant:
    """Property-based tests for configuration invariants"""
    
    @given(st.text(min_size=1), st.floats(min_value=1.0, max_value=300.0))
    def test_configuration_persistence_invariant(self, token, timeout):
        """Property 7: Configuration persistence invariant
        
        For any valid configuration, the client should persist all configuration values
        """
        client = ObotClient(
            base_url="http://localhost:8080/api",
            bootstrap_token=token,
            timeout=timeout
        )
        
        # All configuration should be accessible
        assert client.bootstrap_token == token
        assert client.timeout == timeout
        assert client.base_url == "http://localhost:8080/api"
    
    @given(
        st.text(min_size=1, max_size=100),
        st.text(min_size=1, max_size=200),
        st.floats(min_value=1.0, max_value=300.0),
        st.integers(min_value=0, max_value=10)
    )
    def test_configuration_completeness_invariant(self, base_url, token, timeout, retries):
        """Property 7: Configuration completeness invariant
        
        For any complete configuration, all parameters should be properly set
        """
        client = ObotClient(
            base_url=base_url,
            bootstrap_token=token,
            timeout=timeout,
            max_retries=retries
        )
        
        # Verify all parameters are correctly set
        assert hasattr(client, 'base_url')
        assert hasattr(client, 'bootstrap_token')
        assert hasattr(client, 'timeout')
        assert hasattr(client, 'max_retries')
        assert hasattr(client, '_client')
        
        # Verify httpx client is initialized
        assert client._client is not None
        assert isinstance(client._client, httpx.AsyncClient)


# Integration test for environment configuration
def test_environment_configuration_integration():
    """Integration test for environment-based configuration"""
    
    test_env = {
        "OBOT_BASE_URL": "http://obot.example.com:9090/api/v2",
        "OBOT_BOOTSTRAP_TOKEN": "secure-bootstrap-token-12345"
    }
    
    with patch.dict(os.environ, test_env):
        with patch('core.obot.client.ObotClient') as mock_client_class:
            client = create_obot_client()
            
            mock_client_class.assert_called_once_with(
                base_url="http://obot.example.com:9090/api/v2",
                bootstrap_token="secure-bootstrap-token-12345"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
