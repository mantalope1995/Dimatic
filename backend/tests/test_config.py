"""
Unit tests for configuration loading.

Tests Requirements 7.1, 7.2, 7.3:
- Test API key loading from environment
- Test API base URL loading
- Test error handling for missing key
"""

import os
import pytest
from unittest.mock import patch
from core.utils.config import Configuration, EnvMode


class TestMinimaxConfiguration:
    """Test Minimax API configuration loading."""
    
    def test_minimax_api_key_loading_from_environment(self):
        """
        Test that MINIMAX_API_KEY is loaded from environment variables.
        Requirements: 7.1
        """
        test_api_key = "test_minimax_key_12345"
        
        with patch.dict(os.environ, {
            'MINIMAX_API_KEY': test_api_key,
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }):
            config = Configuration()
            assert config.MINIMAX_API_KEY == test_api_key
    
    def test_minimax_api_base_loading_from_environment(self):
        """
        Test that MINIMAX_API_BASE is loaded from environment variables.
        Requirements: 7.2
        """
        test_api_base = "https://custom.minimax.api/v1"
        
        with patch.dict(os.environ, {
            'MINIMAX_API_BASE': test_api_base,
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }):
            config = Configuration()
            assert config.MINIMAX_API_BASE == test_api_base
    
    def test_minimax_api_base_default_value(self):
        """
        Test that MINIMAX_API_BASE has correct default value when not set.
        Requirements: 7.2
        """
        with patch.dict(os.environ, {
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }, clear=True):
            config = Configuration()
            assert config.MINIMAX_API_BASE == "https://api.minimax.chat/v1"
    
    def test_minimax_api_key_missing_returns_none(self):
        """
        Test that missing MINIMAX_API_KEY returns None (optional field).
        Requirements: 7.3
        """
        with patch.dict(os.environ, {
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }, clear=True):
            config = Configuration()
            assert config.MINIMAX_API_KEY is None
    
    def test_minimax_configuration_with_all_values(self):
        """
        Test that both MINIMAX_API_KEY and MINIMAX_API_BASE load correctly together.
        Requirements: 7.1, 7.2
        """
        test_api_key = "test_key_abc123"
        test_api_base = "https://test.minimax.com/v2"
        
        with patch.dict(os.environ, {
            'MINIMAX_API_KEY': test_api_key,
            'MINIMAX_API_BASE': test_api_base,
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }):
            config = Configuration()
            assert config.MINIMAX_API_KEY == test_api_key
            assert config.MINIMAX_API_BASE == test_api_base
    
    def test_minimax_api_key_empty_string(self):
        """
        Test that empty string for MINIMAX_API_KEY is handled correctly.
        Requirements: 7.3
        """
        with patch.dict(os.environ, {
            'MINIMAX_API_KEY': '',
            'SUPABASE_URL': 'http://test',
            'SUPABASE_ANON_KEY': 'test',
            'SUPABASE_SERVICE_ROLE_KEY': 'test',
            'SUPABASE_JWT_SECRET': 'test'
        }):
            config = Configuration()
            # Empty string should be treated as empty string, not None
            assert config.MINIMAX_API_KEY == ''
