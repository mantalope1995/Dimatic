"""
Property-based tests for Model Registry.

**Feature: minimax-m2-migration, Property 1: Model Registry Initialization**
"""
import os
import sys

# Set environment variables before importing modules
os.environ["ENV_MODE"] = "LOCAL"
os.environ["LOGGING_LEVEL"] = "ERROR"

import pytest
from hypothesis import given, strategies as st, settings

from core.ai_models.registry import ModelRegistry
from core.ai_models.ai_models import ModelProvider, ModelCapability


class TestModelRegistryInitialization:
    """
    **Feature: minimax-m2-migration, Property 1: Model Registry Initialization**
    **Validates: Requirements 1.1, 4.1, 4.2**
    
    Property: For any system initialization, the Model Registry should register 
    Minimax-m2 as the only enabled model, while keeping other models registered 
    but disabled.
    """
    
    @settings(max_examples=100)
    @given(st.integers(min_value=0, max_value=10))
    def test_minimax_m2_is_only_enabled_model(self, _iteration):
        """
        Property test: Minimax-m2 should be the only enabled model across all 
        registry initializations.
        
        This test verifies that:
        1. Minimax-m2 is registered and enabled
        2. All other models are registered but disabled
        3. Only one model is enabled in total
        """
        # Create a fresh registry instance
        registry = ModelRegistry()
        
        # Get all models (including disabled ones)
        all_models = registry.get_all(enabled_only=False)
        enabled_models = registry.get_all(enabled_only=True)
        
        # Property 1: At least one model should be registered
        assert len(all_models) > 0, "Registry should have at least one model registered"
        
        # Property 2: Exactly one model should be enabled
        assert len(enabled_models) == 1, (
            f"Expected exactly 1 enabled model, but found {len(enabled_models)}: "
            f"{[m.id for m in enabled_models]}"
        )
        
        # Property 3: The enabled model should be Minimax-m2
        enabled_model = enabled_models[0]
        assert enabled_model.id == "minimax/minimax-m2", (
            f"Expected enabled model to be 'minimax/minimax-m2', "
            f"but found '{enabled_model.id}'"
        )
        
        # Property 4: Minimax-m2 should have correct provider
        assert enabled_model.provider == ModelProvider.MINIMAX, (
            f"Expected Minimax-m2 provider to be MINIMAX, "
            f"but found {enabled_model.provider}"
        )
        
        # Property 5: Minimax-m2 should have thinking capability
        assert ModelCapability.THINKING in enabled_model.capabilities, (
            "Minimax-m2 should have THINKING capability"
        )
        
        # Property 6: Minimax-m2 should have correct pricing
        assert enabled_model.pricing is not None, "Minimax-m2 should have pricing defined"
        assert enabled_model.pricing.input_cost_per_million_tokens == 0.60, (
            f"Expected input cost of $0.60, but found "
            f"${enabled_model.pricing.input_cost_per_million_tokens}"
        )
        assert enabled_model.pricing.output_cost_per_million_tokens == 2.20, (
            f"Expected output cost of $2.20, but found "
            f"${enabled_model.pricing.output_cost_per_million_tokens}"
        )
        
        # Property 7: Minimax-m2 should have Anthropic SDK-compatible config
        assert enabled_model.config is not None, "Minimax-m2 should have config defined"
        assert enabled_model.config.api_base == "https://api.minimax.chat/v1", (
            f"Expected api_base 'https://api.minimax.chat/v1', "
            f"but found '{enabled_model.config.api_base}'"
        )
        assert enabled_model.config.extra_headers is not None, (
            "Minimax-m2 should have extra_headers defined"
        )
        assert "anthropic-version" in enabled_model.config.extra_headers, (
            "Minimax-m2 should have anthropic-version header"
        )
        
        # Property 8: All other models should be disabled
        disabled_models = [m for m in all_models if not m.enabled]
        assert len(disabled_models) == len(all_models) - 1, (
            f"Expected {len(all_models) - 1} disabled models, "
            f"but found {len(disabled_models)}"
        )
        
        # Property 9: Disabled models should still be registered (for future use)
        for model in disabled_models:
            assert model.id != "minimax/minimax-m2", (
                f"Minimax-m2 should not be in disabled models list"
            )
            # Verify we can still get disabled models by ID
            retrieved = registry.get(model.id)
            assert retrieved is not None, (
                f"Disabled model {model.id} should still be retrievable"
            )
            assert not retrieved.enabled, (
                f"Retrieved model {model.id} should be disabled"
            )
    
    def test_minimax_m2_model_resolution(self):
        """
        Test that Minimax-m2 can be resolved by various identifiers.
        """
        registry = ModelRegistry()
        
        # Test resolution by ID
        model = registry.get("minimax/minimax-m2")
        assert model is not None, "Should resolve by full ID"
        assert model.enabled, "Resolved model should be enabled"
        
        # Test resolution by aliases
        for alias in ["minimax-m2", "Minimax-m2"]:
            model = registry.get(alias)
            assert model is not None, f"Should resolve by alias '{alias}'"
            assert model.id == "minimax/minimax-m2", (
                f"Alias '{alias}' should resolve to minimax/minimax-m2"
            )
    
    def test_minimax_m2_tier_availability(self):
        """
        Test that Minimax-m2 is available to both free and paid tiers.
        """
        registry = ModelRegistry()
        
        # Get models by tier
        free_models = registry.get_by_tier("free", enabled_only=True)
        paid_models = registry.get_by_tier("paid", enabled_only=True)
        
        # Minimax-m2 should be in both tiers
        assert any(m.id == "minimax/minimax-m2" for m in free_models), (
            "Minimax-m2 should be available to free tier"
        )
        assert any(m.id == "minimax/minimax-m2" for m in paid_models), (
            "Minimax-m2 should be available to paid tier"
        )
    
    def test_minimax_m2_litellm_params(self):
        """
        Test that Minimax-m2 generates correct LiteLLM parameters.
        """
        registry = ModelRegistry()
        model = registry.get("minimax/minimax-m2")
        
        assert model is not None, "Minimax-m2 should be registered"
        
        # Get LiteLLM parameters
        params = model.get_litellm_params()
        
        # Verify essential parameters
        assert params["model"] == "minimax/minimax-m2", (
            "Model ID should be included in params"
        )
        assert params["api_base"] == "https://api.minimax.chat/v1", (
            "API base should be included in params"
        )
        assert "extra_headers" in params, (
            "Extra headers should be included in params"
        )
        assert "anthropic-version" in params["extra_headers"], (
            "Anthropic version header should be included"
        )
