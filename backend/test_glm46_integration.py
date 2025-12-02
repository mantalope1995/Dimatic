#!/usr/bin/env python3
"""
GLM-4.6 Integration Test Script

This script tests the GLM-4.6 integration by:
1. Testing model registry configuration
2. Testing model resolution
3. Testing actual API calls to GLM-4.6 via Z AI
4. Verifying both kortix/basic and kortix/power use GLM-4.6
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from core.ai_models import model_manager
from core.services.llm import make_llm_api_call, LLMError
from core.utils.logger import logger


async def test_model_registry():
    """Test that GLM-4.6 models are properly registered."""
    print("🔍 Testing Model Registry...")
    
    # Test kortix/basic
    basic_model = model_manager.get_model("kortix/basic")
    if not basic_model:
        print("❌ kortix/basic model not found in registry")
        return False
    
    print(f"✅ kortix/basic found: {basic_model.name} (Provider: {basic_model.provider.value})")
    print(f"   - Context Window: {basic_model.context_window}")
    print(f"   - Max Output: {basic_model.max_output_tokens}")
    print(f"   - Capabilities: {[cap.value for cap in basic_model.capabilities]}")
    print(f"   - Tier Availability: {basic_model.tier_availability}")
    
    # Test kortix/power
    power_model = model_manager.get_model("kortix/power")
    if not power_model:
        print("❌ kortix/power model not found in registry")
        return False
    
    print(f"✅ kortix/power found: {power_model.name} (Provider: {power_model.provider.value})")
    print(f"   - Context Window: {power_model.context_window}")
    print(f"   - Max Output: {power_model.max_output_tokens}")
    print(f"   - Capabilities: {[cap.value for cap in power_model.capabilities]}")
    print(f"   - Tier Availability: {power_model.tier_availability}")
    
    # Test LiteLLM ID resolution
    basic_litellm_id = model_manager.registry.get_litellm_model_id("kortix/basic")
    power_litellm_id = model_manager.registry.get_litellm_model_id("kortix/power")
    
    expected_id = "openai-compatible/glm-4.6"
    
    if basic_litellm_id != expected_id:
        print(f"❌ kortix/basic LiteLLM ID mismatch: expected {expected_id}, got {basic_litellm_id}")
        return False
    
    if power_litellm_id != expected_id:
        print(f"❌ kortix/power LiteLLM ID mismatch: expected {expected_id}, got {power_litellm_id}")
        return False
    
    print(f"✅ Both kortix models correctly resolve to: {expected_id}")
    
    return True


async def test_model_resolution():
    """Test model ID resolution logic."""
    print("\n🔍 Testing Model Resolution...")
    
    test_cases = [
        ("kortix/basic", "kortix/basic"),
        ("kortix/power", "kortix/power"),
        ("glm-4.6", "openai-compatible/glm-4.6"),
        ("GLM-4.6", "openai-compatible/glm-4.6"),
        ("openai-compatible/glm-4.6", "openai-compatible/glm-4.6"),
    ]
    
    for input_id, expected_id in test_cases:
        resolved_id = model_manager.resolve_model_id(input_id)
        if resolved_id != expected_id:
            print(f"❌ Resolution failed: {input_id} -> {resolved_id} (expected {expected_id})")
            return False
        print(f"✅ {input_id} -> {resolved_id}")
    
    return True


async def test_api_calls():
    """Test actual API calls to GLM-4.6."""
    print("\n🔍 Testing API Calls...")
    
    # Check if Z_AI_API_KEY is set
    if not os.getenv("Z_AI_API_KEY"):
        print("⚠️  Z_AI_API_KEY not set in environment. Skipping API tests.")
        print("   Set Z_AI_API_KEY in your .env file to run API tests.")
        return True  # Not a failure, just skipped
    
    test_messages = [
        {"role": "user", "content": "Hello, GLM-4.6! Please respond with a brief greeting and tell me what model you are."}
    ]
    
    # Test kortix/basic (should use GLM-4.6)
    try:
        print("Testing kortix/basic...")
        response = await make_llm_api_call(
            messages=test_messages,
            model_name="kortix/basic",
            temperature=0.7,
            max_tokens=100,
            stream=False
        )
        
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content
            print(f"✅ kortix/basic API call successful!")
            print(f"   Response: {content[:100]}...")
        else:
            print(f"❌ kortix/basic API call failed: unexpected response format")
            return False
            
    except Exception as e:
        print(f"❌ kortix/basic API call failed: {e}")
        return False
    
    # Test kortix/power (should also use GLM-4.6)
    try:
        print("Testing kortix/power...")
        response = await make_llm_api_call(
            messages=test_messages,
            model_name="kortix/power",
            temperature=0.7,
            max_tokens=100,
            stream=False
        )
        
        if hasattr(response, 'choices') and response.choices:
            content = response.choices[0].message.content
            print(f"✅ kortix/power API call successful!")
            print(f"   Response: {content[:100]}...")
        else:
            print(f"❌ kortix/power API call failed: unexpected response format")
            return False
            
    except Exception as e:
        print(f"❌ kortix/power API call failed: {e}")
        return False
    
    return True


async def test_cost_calculation():
    """Test cost calculation for GLM-4.6."""
    print("\n🔍 Testing Cost Calculation...")
    
    # Test kortix/basic cost calculation
    basic_cost = model_manager.calculate_cost(
        model_id="kortix/basic",
        input_tokens=1000,
        output_tokens=500
    )
    
    expected_basic_cost = (1000 * 1.20 / 1_000_000) + (500 * 4.40 / 1_000_000)
    
    if basic_cost is None:
        print("❌ kortix/basic cost calculation returned None")
        return False
    
    if abs(basic_cost - expected_basic_cost) > 0.000001:
        print(f"❌ kortix/basic cost calculation mismatch: expected ${expected_basic_cost:.6f}, got ${basic_cost:.6f}")
        return False
    
    print(f"✅ kortix/basic cost calculation correct: ${basic_cost:.6f} for 1000 input + 500 output tokens")
    
    # Test kortix/power cost calculation (should be same)
    power_cost = model_manager.calculate_cost(
        model_id="kortix/power",
        input_tokens=1000,
        output_tokens=500
    )
    
    if abs(power_cost - expected_basic_cost) > 0.000001:
        print(f"❌ kortix/power cost calculation mismatch: expected ${expected_basic_cost:.6f}, got ${power_cost:.6f}")
        return False
    
    print(f"✅ kortix/power cost calculation correct: ${power_cost:.6f} for 1000 input + 500 output tokens")
    
    return True


async def main():
    """Run all GLM-4.6 integration tests."""
    print("🚀 Starting GLM-4.6 Integration Tests\n")
    
    tests = [
        ("Model Registry", test_model_registry),
        ("Model Resolution", test_model_resolution),
        ("Cost Calculation", test_cost_calculation),
        ("API Calls", test_api_calls),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
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
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)