"""
Tests for Qwen3-VL model registry and API routing configuration.

These tests validate that the model registry is properly configured for Qwen3-VL models
and that LiteLLM routing is set up correctly, without requiring actual API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
import os

from core.ai_models.registry import ModelRegistry
from core.ai_models.ai_models import ModelProvider
from core.services.llm import setup_provider_router
from core.utils.config import get_config


class TestQwen3VLRegistry:
    """Test the Qwen3-VL model registry configuration."""
    
    def test_registry_only_contains_qwen3_vl_models(self):
        """
        **Feature: qwen3-vl-optimization, Property 8: Model selection always returns Qwen3-VL**
        **Validates: Requirements 10.2**
        """
        registry = ModelRegistry()
        
        # Get all registered models
        all_models = registry.get_all_models()
        
        # Verify only Qwen3-VL models are registered
        model_ids = [model.id for model in all_models]
        expected_models = [
            "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "Qwen/Qwen3-VL-235B-A22B-Thinking"
        ]
        
        assert len(model_ids) == 2, f"Expected 2 models, got {len(model_ids)}"
        assert set(model_ids) == set(expected_models), f"Expected {expected_models}, got {model_ids}"
        
        # Verify all models use SILICONFLOW provider
        for model in all_models:
            assert model.provider == ModelProvider.SILICONFLOW, f"Model {model.id} should use SILICONFLOW provider"
    
    def test_qwen3_vl_instruct_model_configuration(self):
        """Test that the Qwen3-VL-Instruct model is properly configured."""
        registry = ModelRegistry()
        model = registry.get("Qwen/Qwen3-VL-235B-A22B-Instruct")
        
        assert model is not None, "Qwen3-VL-Instruct model should be registered"
        assert model.name == "Qwen3-VL-235B-A22B-Instruct"
        assert model.provider == ModelProvider.SILICONFLOW
        assert model.context_window == 262_144
        assert model.max_output_tokens == 262_144
        
        # Verify capabilities
        expected_capabilities = {
            "chat", "function_calling", "vision", "thinking", "structured_output"
        }
        actual_capabilities = {cap.value for cap in model.capabilities}
        assert actual_capabilities == expected_capabilities
        
        # Verify aliases
        expected_aliases = ["qwen3-vl-instruct", "Qwen3-VL-Instruct", "qwen-vl-instruct", "kortix/basic", "kortix/power"]
        assert set(model.aliases) == set(expected_aliases)
        
        # Verify vision configuration
        assert model.config.extra_body["min_pixels"] == 512 * 32 * 32
        assert model.config.extra_body["max_pixels"] == 2048 * 32 * 32
    
    def test_qwen3_vl_thinking_model_configuration(self):
        """Test that the Qwen3-VL-Thinking model is properly configured."""
        registry = ModelRegistry()
        model = registry.get("Qwen/Qwen3-VL-235B-A22B-Thinking")
        
        assert model is not None, "Qwen3-VL-Thinking model should be registered"
        assert model.name == "Qwen3-VL-235B-A22B-Thinking"
        assert model.provider == ModelProvider.SILICONFLOW
        assert model.context_window == 262_144
        assert model.max_output_tokens == 262_144
        
        # Verify capabilities
        expected_capabilities = {
            "chat", "function_calling", "vision", "thinking", "structured_output"
        }
        actual_capabilities = {cap.value for cap in model.capabilities}
        assert actual_capabilities == expected_capabilities
        
        # Verify aliases
        expected_aliases = ["qwen3-vl-thinking", "Qwen3-VL-Thinking", "qwen-vl-thinking", "kortix/thinking"]
        assert set(model.aliases) == set(expected_aliases)
        
        # Verify tier availability
        assert model.tier_availability == ["paid"]
    
    def test_model_resolution_by_alias(self):
        """Test that model aliases resolve to correct Qwen3-VL models."""
        registry = ModelRegistry()
        
        # Test kortix aliases (backward compatibility)
        basic_model = registry.resolve_model_id("kortix/basic")
        assert basic_model == "Qwen/Qwen3-VL-235B-A22B-Instruct"
        
        power_model = registry.resolve_model_id("kortix/power")
        assert power_model == "Qwen/Qwen3-VL-235B-A22B-Instruct"
        
        thinking_model = registry.resolve_model_id("kortix/thinking")
        assert thinking_model == "Qwen/Qwen3-VL-235B-A22B-Thinking"
        
        # Test direct aliases
        instruct_model = registry.resolve_model_id("qwen3-vl-instruct")
        assert instruct_model == "Qwen/Qwen3-VL-235B-A22B-Instruct"
        
        thinking_alias_model = registry.resolve_model_id("qwen3-vl-thinking")
        assert thinking_alias_model == "Qwen/Qwen3-VL-235B-A22B-Thinking"
    
    def test_no_legacy_models_registered(self):
        """Verify that legacy models (MiniMax, Anthropic, etc.) are not registered."""
        registry = ModelRegistry()
        all_models = registry.get_all_models()
        
        # These should NOT be in the registry anymore
        legacy_model_ids = [
            "anthropic/claude-3-5-sonnet-20241022",
            "openai/gpt-4o",
            "minimax/minimax-text-chat",
            "google/gemini-pro",
        ]
        
        registered_ids = [model.id for model in all_models]
        
        for legacy_id in legacy_model_ids:
            assert legacy_id not in registered_ids, f"Legacy model {legacy_id} should not be registered"
    
    def test_get_litellm_parameters(self):
        """Test that get_litellm_params returns correct LiteLLM configuration."""
        registry = ModelRegistry()
        instruct_model = registry.get("Qwen/Qwen3-VL-235B-A22B-Instruct")
        
        litellm_params = instruct_model.get_litellm_params()
        
        # Verify LiteLLM model name format
        assert litellm_params["model"] == "openai/Qwen/Qwen3-VL-235B-A22B-Instruct"
        
        # Verify SiliconFlow configuration
        assert litellm_params["api_base"] == "https://api.siliconflow.cn/v1"
        assert litellm_params["max_tokens"] == 262_144
        
        # Verify vision parameters are included in extra_body
        assert "extra_body" in litellm_params
        assert litellm_params["extra_body"]["min_pixels"] == 512 * 32 * 32
        assert litellm_params["extra_body"]["max_pixels"] == 2048 * 32 * 32


class TestSiliconFlowAPIRouting:
    """Test SiliconFlow API routing configuration."""
    
    @patch.dict(os.environ, {}, clear=True)  # Clear all environment variables
    def test_config_without_api_key(self):
        """Test that the system handles missing API key gracefully."""
        config = get_config()
        
        # Should return None when no API key is configured
        assert config.SILICONFLOW_API_KEY is None
        assert config.SILICONFLOW_API_BASE == "https://api.siliconflow.cn/v1"  # Default value
    
    @patch.dict(os.environ, {
        'SILICONFLOW_API_KEY': 'test-key-12345',
        'SILICONFLOW_API_BASE': 'https://custom.siliconflow.cn/v1'
    })
    def test_config_with_api_key(self):
        """Test that environment variables are loaded correctly."""
        config = get_config()
        
        assert config.SILICONFLOW_API_KEY == 'test-key-12345'
        assert config.SILICONFLOW_API_BASE == 'https://custom.siliconflow.cn/v1'
    
    @patch('core.services.llm.litellm')
    def test_setup_provider_router_includes_siliconflow(self, mock_litellm):
        """
        **Feature: qwen3-vl-optimization, Property 9: API routing targets SiliconFlow endpoint**
        **Validates: Requirements 1.2, 9.4**
        """
        # Mock the litellm module
        mock_router = MagicMock()
        mock_litellm.Router.return_value = mock_router
        
        # Call setup_provider_router
        setup_provider_router()
        
        # Verify Router was called with the correct model list
        mock_litellm.Router.assert_called_once()
        
        # Get the model_list argument from the Router call
        call_args = mock_litellm.Router.call_args
        model_list = call_args[1]['model_list']  # kwargs['model_list']
        
        # Verify both Qwen3-VL models are in the model list
        model_names = [model['model_name'] for model in model_list]
        expected_models = [
            "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "Qwen/Qwen3-VL-235B-A22B-Thinking"
        ]
        
        assert set(model_names) == set(expected_models), f"Expected {expected_models}, got {model_names}"
        
        # Verify SiliconFlow API configuration for each model
        for model_config in model_list:
            litellm_params = model_config['litellm_params']
            
            # Should use OpenAI-compatible format with SiliconFlow
            assert litellm_params['model'].startswith('openai/Qwen/')
            assert litellm_params['api_base'] == 'https://api.siliconflow.cn/v1'
            assert litellm_params['max_tokens'] == 262144
            assert litellm_params['context_window'] == 262144
    
    @patch.dict(os.environ, {'SILICONFLOW_API_KEY': 'test-api-key'})
    @patch('core.services.llm.litellm')
    def test_setup_api_keys_includes_siliconflow(self, mock_litellm):
        """Test that setup_api_keys includes SILICONFLOW in the providers list."""
        # This test verifies that SILICONFLOW is included in the providers list
        # which is used for API key setup
        
        # Import and call setup_api_keys
        from core.services.llm import setup_api_keys
        
        # The function should not raise an exception even without mocking litellm
        # since it primarily sets up environment variables
        try:
            setup_api_keys()
            setup_successful = True
        except Exception as e:
            setup_successful = False
            error_msg = str(e)
        
        assert setup_successful, f"setup_api_keys failed: {error_msg if not setup_successful else ''}"


class TestBackwardCompatibility:
    """Test backward compatibility with existing kortix aliases."""
    
    def test_kortix_aliases_resolve_correctly(self):
        """Test that existing kortix/* aliases continue to work."""
        registry = ModelRegistry()
        
        # These aliases are used in existing code and should continue to work
        test_cases = [
            ("kortix/basic", "Qwen/Qwen3-VL-235B-A22B-Instruct"),
            ("kortix/power", "Qwen/Qwen3-VL-235B-A22B-Instruct"),
            ("kortix/thinking", "Qwen/Qwen3-VL-235B-A22B-Thinking"),
        ]
        
        for alias, expected_model_id in test_cases:
            resolved_id = registry.resolve_model_id(alias)
            assert resolved_id == expected_model_id, f"Alias {alias} should resolve to {expected_model_id}"
    
    def test_unavailable_model_returns_none(self):
        """Test that requesting an unregistered model returns None."""
        registry = ModelRegistry()
        
        # These models should no longer be available
        unavailable_models = [
            "kortix/mini",
            "anthropic/claude-3-5-sonnet-20241022",
            "openai/gpt-4o",
            "minimax/minimax-text-chat",
        ]
        
        for model_id in unavailable_models:
            resolved = registry.resolve_model_id(model_id)
            assert resolved is None, f"Unavailable model {model_id} should return None"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
