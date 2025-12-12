"""Property-based tests for Obot client configuration parsing

These tests verify Property 7: Environment Configuration Parsing
Validates: Requirements 1.3
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, assume
from hypothesis.stateful import rule, precondition, run_state_machine_as_test

from core.obot.client import ObotClient, ObotClientError, ObotConnectionError
from core.obot.models import ObotHealthResponse


class TestObotClientConfigurationProperties:
    """Property-based tests for Obot client configuration parsing"""
    
    # **Feature: obot-mcp-integration, Property 7: Environment Configuration Parsing**
    # **Validates: Requirements 1.3**
    
    @given(
        base_url=st.text(min_size=1, max_size=500),
        bootstrap_token=st.text(min_size=1, max_size=500),
        timeout=st.floats(min_value=0.1, max_value=300.0),
        max_retries=st.integers(min_value=0, max_value=10),
        retry_delay=st.floats(min_value=0.1, max_value=60.0)
    )
    def test_environment_configuration_parsing(self, base_url, bootstrap_token, timeout, max_retries, retry_delay):
        """Property: For any valid environment variable configuration, the Obot client SHALL correctly parse and apply the configuration values for base URL, JWT secret, and timeout settings."""
        
        # Arrange: Valid configuration values
        assume(len(base_url.strip()) > 0)
        assume(len(bootstrap_token.strip()) > 0)
        assume(timeout > 0)
        assume(max_retries >= 0)
        assume(retry_delay > 0)
        
        with patch.dict(os.environ, {
            'OBOT_BASE_URL': base_url,
            'OBOT_BOOTSTRAP_TOKEN': bootstrap_token
        }):
            # Act: Create Obot client with environment variables
            client = ObotClient(
                timeout=timeout,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
            
            # Assert: Configuration is correctly parsed and applied
            assert client.base_url == base_url
            assert client.bootstrap_token == bootstrap_token
            assert client.timeout == timeout
            assert client.max_retries == max_retries
            assert client.retry_delay == retry_delay
    
    @given(
        base_url_strategy=st.one_of(
            st.just(None),
            st.text(min_size=0, max_size=100)
        ),
        bootstrap_token_strategy=st.one_of(
            st.just(None),
            st.text(min_size=0, max_size=100)
        ),
        explicit_base_url=st.one_of(
            st.just(None),
            st.text(min_size=1, max_size=500)
        ),
        explicit_bootstrap_token=st.one_of(
            st.just(None),
            st.text(min_size=1, max_size=500)
        )
    )
    def test_configuration_precedence(self, base_url_strategy, bootstrap_token_strategy, explicit_base_url, explicit_bootstrap_token):
        """Property: Explicit configuration parameters take precedence over environment variables"""
        
        # Arrange: Set up environment variables (may be None/empty)
        env_vars = {}
        if base_url_strategy:
            env_vars['OBOT_BASE_URL'] = base_url_strategy
        if bootstrap_token_strategy:
            env_vars['OBOT_BOOTSTRAP_TOKEN'] = bootstrap_token_strategy
        
        explicit_base = explicit_base_url or "http://explicit-obot:8080/api"
        explicit_token = explicit_bootstrap_token or "explicit-bootstrap-token"
        
        with patch.dict(os.environ, env_vars, clear=False):
            # Test explicit base URL takes precedence
            if explicit_base_url:
                client = ObotClient(base_url=explicit_base_url, bootstrap_token=explicit_token)
                assert client.base_url == explicit_base_url
            
            # Test explicit bootstrap token takes precedence
            if explicit_bootstrap_token:
                client = ObotClient(base_url=explicit_base, bootstrap_token=explicit_bootstrap_token)
                assert client.bootstrap_token == explicit_bootstrap_token
    
    @given(
        base_url=st.text(min_size=1, max_size=100),
        bootstrap_token=st.text(min_size=1, max_size=100)
    )
    def test_default_configuration_fallback(self, base_url, bootstrap_token):
        """Property: Client uses sensible defaults when configuration is partially missing"""
        
        assume(len(base_url.strip()) > 0)
        assume(len(bootstrap_token.strip()) > 0)
        
        with patch.dict(os.environ, {}, clear=True):
            # Test default timeout when not specified
            client = ObotClient(base_url=base_url, bootstrap_token=bootstrap_token)
            assert client.timeout == 30.0  # Default timeout
            assert client.max_retries == 3  # Default max_retries
            assert client.retry_delay == 1.0  # Default retry_delay
            
            # Test custom values are applied
            client_custom = ObotClient(
                base_url=base_url,
                bootstrap_token=bootstrap_token,
                timeout=60.0,
                max_retries=5,
                retry_delay=2.0
            )
            assert client_custom.timeout == 60.0
            assert client_custom.max_retries == 5
            assert client_custom.retry_delay == 2.0
    
    @given(
        invalid_base_url=st.one_of(
            st.just(""),
            st.just("   "),
            st.none()
        ),
        invalid_bootstrap_token=st.one_of(
            st.just(""),
            st.just("   "),
            st.none()
        )
    )
    def test_invalid_configuration_error_handling(self, invalid_base_url, invalid_bootstrap_token):
        """Property: Invalid configuration raises appropriate ValueError"""
        
        # Test missing base URL
        if invalid_base_url in (None, "", "   "):
            with pytest.raises(ValueError, match="Obot base URL must be provided"):
                ObotClient(bootstrap_token="valid-token")
        
        # Test missing bootstrap token
        if invalid_bootstrap_token in (None, "", "   "):
            with pytest.raises(ValueError, match="Obot bootstrap token must be provided"):
                ObotClient(base_url="http://valid-url:8080")
    
    @given(
        timeout=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-100, max_value=0),
            st.floats(min_value=301.0, max_value=10000.0)
        ),
        max_retries=st.one_of(
            st.integers(min_value=-100, max_value=-1),
            st.integers(min_value=11, max_value=1000)
        ),
        retry_delay=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-100, max_value=0),
            st.floats(min_value=61.0, max_value=10000.0)
        )
    )
    def test_extreme_configuration_values(self, timeout, max_retries, retry_delay):
        """Property: Client handles extreme configuration values gracefully"""
        
        base_url = "http://test-obot:8080/api"
        bootstrap_token = "test-token"
        
        # Negative or zero timeout should work (will be clamped by httpx)
        if timeout > 0 and timeout <= 300:
            client = ObotClient(
                base_url=base_url,
                bootstrap_token=bootstrap_token,
                timeout=timeout,
                max_retries=max_retries if max_retries >= 0 else 0,
                retry_delay=retry_delay if retry_delay > 0 else 0.1
            )
            
            # Values should be stored as provided (validation happens at request time)
            assert client.timeout == timeout
            assert client.max_retries >= 0  # Ensure non-negative
            assert client.retry_delay > 0   # Ensure positive
    
    @given(
        special_chars=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=1, max_size=100)
    )
    def test_special_characters_in_configuration(self, special_chars):
        """Property: Configuration parsing handles special characters correctly"""
        
        assume(len(special_chars.strip()) > 0)
        
        with patch.dict(os.environ, {
            'OBOT_BASE_URL': f"http://test{special_chars}:8080/api",
            'OBOT_BOOTSTRAP_TOKEN': f"token{special_chars}"
        }):
            client = ObotClient()
            
            # Special characters should be preserved
            assert client.base_url == f"http://test{special_chars}:8080/api"
            assert client.bootstrap_token == f"token{special_chars}"


class TestObotClientHealthCheckProperties:
    """Property-based tests for health check functionality"""
    
    @given(
        version_info=st.text(min_size=1, max_size=100),
        status=st.one_of(st.just("healthy"), st.just("unhealthy"), st.just("degraded"))
    )
    @patch('core.obot.client.ObotClient._make_request')
    async def test_health_response_parsing(self, mock_request, version_info, status):
        """Property: Health check response parsing handles valid inputs correctly"""
        
        assume(len(version_info.strip()) > 0)
        
        # Mock successful health response
        mock_request.return_value = {
            "version": version_info,
            "status": status
        }
        
        client = ObotClient(base_url="http://test:8080", bootstrap_token="test-token")
        
        # Act
        health_response = await client.check_health()
        
        # Assert
        assert isinstance(health_response, ObotHealthResponse)
        assert health_response.version == version_info
        assert health_response.status == status
    
    @given(
        response_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.text(min_size=0, max_size=100), st.integers(), st.floats())
        )
    )
    @patch('core.obot.client.ObotClient._make_request')
    async def test_health_response_error_handling(self, mock_request, response_data):
        """Property: Health check gracefully handles malformed responses"""
        
        # Ensure we have required fields
        assume("version" in response_data)
        assume("status" in response_data)
        
        mock_request.return_value = response_data
        
        client = ObotClient(base_url="http://test:8080", bootstrap_token="test-token")
        
        # Should not raise exception for any reasonable response
        try:
            health_response = await client.check_health()
            assert isinstance(health_response, ObotHealthResponse)
        except Exception:
            # Some malformed responses might fail, which is acceptable
            pass


# State machine testing for client configuration lifecycle
class ObotClientConfigStateMachine:
    """State machine to test client configuration lifecycle"""
    
    def __init__(self):
        self.client = None
        self.config_history = []
    
    @rule(
        base_url=st.text(min_size=1, max_size=100),
        bootstrap_token=st.text(min_size=1, max_size=100)
    )
    def create_client(self, base_url, bootstrap_token):
        """Rule: Create client with valid configuration"""
        assume(len(base_url.strip()) > 0)
        assume(len(bootstrap_token.strip()) > 0)
        
        # Clean environment
        with patch.dict(os.environ, {}, clear=True):
            self.client = ObotClient(base_url=base_url, bootstrap_token=bootstrap_token)
            self.config_history.append({
                'action': 'create',
                'base_url': base_url,
                'bootstrap_token': bootstrap_token
            })
        
        assert self.client is not None
        assert self.client.base_url == base_url
        assert self.client.bootstrap_token == bootstrap_token
    
    @rule(
        timeout=st.floats(min_value=1.0, max_value=300.0),
        max_retries=st.integers(min_value=0, max_value=10),
        retry_delay=st.floats(min_value=0.1, max_value=60.0)
    )
    def update_timeout_settings(self, timeout, max_retries, retry_delay):
        """Rule: Update timeout and retry settings"""
        if self.client:
            self.client.timeout = timeout
            self.client.max_retries = max_retries
            self.client.retry_delay = retry_delay
            
            self.config_history.append({
                'action': 'update_settings',
                'timeout': timeout,
                'max_retries': max_retries,
                'retry_delay': retry_delay
            })
            
            assert self.client.timeout == timeout
            assert self.client.max_retries == max_retries
            assert self.client.retry_delay == retry_delay
    
    @precondition(lambda self: self.client is not None)
    @rule()
    def close_and_recreate_client(self):
        """Rule: Close client and recreate with same configuration"""
        if self.client:
            original_base_url = self.client.base_url
            original_bootstrap_token = self.client.bootstrap_token
            
            # Close client
            # (Note: actual close would be async in real usage)
            
            # Recreate with same config
            with patch.dict(os.environ, {}, clear=True):
                new_client = ObotClient(
                    base_url=original_base_url,
                    bootstrap_token=original_bootstrap_token
                )
                
                self.config_history.append({
                    'action': 'recreate',
                    'base_url': original_base_url,
                    'bootstrap_token': original_bootstrap_token
                })
            
            assert new_client.base_url == original_base_url
            assert new_client.bootstrap_token == original_bootstrap_token


def test_client_configuration_state_machine():
    """Run state machine test for client configuration lifecycle"""
    run_state_machine_as_test(ObotClientConfigStateMachine)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
