#!/usr/bin/env python3
"""
Simple GLM-4.6 Integration Test

This script tests the core GLM-4.6 model registration without requiring full backend setup.
"""

import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Test basic imports and model registration
try:
    from core.ai_models.ai_models import ModelProvider, ModelCapability, ModelPricing, ModelConfig
    from core.ai_models.registry import ModelRegistry
    print("✅ Successfully imported AI model classes")
except ImportError as e:
    print(f"❌ Failed to import AI model classes: {e}")
    sys.exit(1)

def test_model_registration():
    """Test GLM-4.6 model registration."""
    print("\n🔍 Testing GLM-4.6 Model Registration...")
    
    # Create a test registry
    registry = ModelRegistry()
    
    # Test kortix/basic model
    basic_model = registry.get("kortix/basic")
    if not basic_model:
        print("❌ kortix/basic model not found")
        return False
    
    print(f"✅ kortix/basic found:")
    print(f"   - Name: {basic_model.name}")
    print(f"   - Provider: {basic_model.provider.value}")
    print(f"   - Context Window: {basic_model.context_window}")
    print(f"   - Max Output: {basic_model.max_output_tokens}")
    print(f"   - Capabilities: {[cap.value for cap in basic_model.capabilities]}")
    print(f"   - Tier Availability: {basic_model.tier_availability}")
    print(f"   - Priority: {basic_model.priority}")
    print(f"   - Recommended: {basic_model.recommended}")
    
    # Verify provider is Z_AI
    if basic_model.provider != ModelProvider.Z_AI:
        print(f"❌ kortix/basic provider mismatch: expected Z_AI, got {basic_model.provider}")
        return False
    
    # Verify capabilities
    expected_caps = [ModelCapability.CHAT, ModelCapability.FUNCTION_CALLING, ModelCapability.STRUCTURED_OUTPUT]
    for cap in expected_caps:
        if cap not in basic_model.capabilities:
            print(f"❌ kortix/basic missing capability: {cap.value}")
            return False
    
    # Test kortix/power model
    power_model = registry.get("kortix/power")
    if not power_model:
        print("❌ kortix/power model not found")
        return False
    
    print(f"✅ kortix/power found:")
    print(f"   - Name: {power_model.name}")
    print(f"   - Provider: {power_model.provider.value}")
    print(f"   - Capabilities: {[cap.value for cap in power_model.capabilities]}")
    
    # Verify power model has thinking capability
    if ModelCapability.THINKING not in power_model.capabilities:
        print("❌ kortix/power missing thinking capability")
        return False
    
    # Test LiteLLM ID resolution
    basic_litellm_id = registry.get_litellm_model_id("kortix/basic")
    power_litellm_id = registry.get_litellm_model_id("kortix/power")
    expected_id = "openai-compatible/glm-4.6"
    
    if basic_litellm_id != expected_id:
        print(f"❌ kortix/basic LiteLLM ID mismatch: expected {expected_id}, got {basic_litellm_id}")
        return False
    
    if power_litellm_id != expected_id:
        print(f"❌ kortix/power LiteLLM ID mismatch: expected {expected_id}, got {power_litellm_id}")
        return False
    
    print(f"✅ Both models correctly resolve to: {expected_id}")
    
    # Test pricing
    if not basic_model.pricing:
        print("❌ kortix/basic missing pricing")
        return False
    
    expected_input_price = 1.20
    expected_output_price = 4.40
    
    if abs(basic_model.pricing.input_cost_per_million_tokens - expected_input_price) > 0.01:
        print(f"❌ Input price mismatch: expected {expected_input_price}, got {basic_model.pricing.input_cost_per_million_tokens}")
        return False
    
    if abs(basic_model.pricing.output_cost_per_million_tokens - expected_output_price) > 0.01:
        print(f"❌ Output price mismatch: expected {expected_output_price}, got {basic_model.pricing.output_cost_per_million_tokens}")
        return False
    
    print(f"✅ Pricing correct: ${expected_input_price}/M input, ${expected_output_price}/M output")
    
    return True

def test_model_aliases():
    """Test model aliases work correctly."""
    print("\n🔍 Testing Model Aliases...")
    
    registry = ModelRegistry()
    
    # Test various aliases for kortix/basic
    aliases_to_test = ["kortix-basic", "Kortix Basic", "glm-4.6", "GLM-4.6"]
    
    for alias in aliases_to_test:
        model = registry.get(alias)
        if not model:
            print(f"❌ Alias '{alias}' not resolved")
            return False
        if model.id != "kortix/basic":
            print(f"❌ Alias '{alias}' resolved to wrong model: {model.id}")
            return False
        print(f"✅ Alias '{alias}' -> kortix/basic")
    
    return True

def main():
    """Run simple GLM-4.6 integration tests."""
    print("🚀 Starting Simple GLM-4.6 Integration Tests\n")
    
    tests = [
        ("Model Registration", test_model_registration),
        ("Model Aliases", test_model_aliases),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<8} {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All GLM-4.6 integration tests passed!")
        print("\n📝 Next steps:")
        print("   1. Set Z_AI_API_KEY in your .env file")
        print("   2. Test with actual API calls")
        print("   3. Verify frontend integration")
        return 0
    else:
        print("❌ Some tests failed. Please check implementation.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)