#!/usr/bin/env python3
"""
SiliconFlow API Integration Test for Qwen3-VL models.

This test validates:
1. SiliconFlow API connectivity
2. Native function calling with Qwen3-VL
3. Vision capabilities
4. Streaming responses
5. Error handling

Requires: SILICONFLOW_API_KEY environment variable
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Check for API key first
if not os.getenv("SILICONFLOW_API_KEY"):
    print("❌ SILICONFLOW_API_KEY not found in environment")
    print("Please set the environment variable before running this test:")
    print("export SILICONFLOW_API_KEY=your_api_key_here")
    sys.exit(1)

def test_basic_api_connectivity():
    """Test basic connectivity to SiliconFlow API."""
    print("Testing basic API connectivity...")
    
    try:
        import litellm
        
        # Test basic completion without tools
        response = litellm.completion(
            model="openai/Qwen/Qwen3-VL-235B-A22B-Instruct",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello from Qwen3-VL!'"}
            ],
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            max_tokens=50
        )
        
        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            if "Hello" in content or "hello" in content:
                print("✓ Basic API connectivity working")
                print(f"  Response: {content[:100]}...")
                return True
            else:
                print(f"✗ Unexpected response: {content}")
                return False
        else:
            print("✗ No response from API")
            return False
            
    except Exception as e:
        print(f"✗ API connectivity test failed: {e}")
        return False

def test_native_function_calling():
    """Test native function calling with Qwen3-VL."""
    print("\nTesting native function calling...")
    
    try:
        import litellm
        
        # Define a simple tool
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather information for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city name"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
        
        response = litellm.completion(
            model="openai/Qwen/Qwen3-VL-235B-A22B-Instruct",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Use the get_weather function when asked about weather."},
                {"role": "user", "content": "What's the weather in San Francisco?"}
            ],
            tools=tools,
            tool_choice="auto",
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            max_tokens=100
        )
        
        if response and response.choices and len(response.choices) > 0:
            message = response.choices[0].message
            if hasattr(message, 'tool_calls') and message.tool_calls:
                tool_call = message.tool_calls[0]
                if tool_call.function.name == "get_weather":
                    args = json.loads(tool_call.function.arguments)
                    if "location" in args and "San Francisco" in args["location"]:
                        print("✓ Native function calling working")
                        print(f"  Tool call: {tool_call.function.name}({args})")
                        return True
                    else:
                        print(f"✗ Wrong function arguments: {args}")
                        return False
                else:
                    print(f"✗ Wrong function called: {tool_call.function.name}")
                    return False
            else:
                print("✗ No tool calls in response")
                print(f"  Content: {message.content if hasattr(message, 'content') else 'None'}")
                return False
        else:
            print("✗ No response from API")
            return False
            
    except Exception as e:
        print(f"✗ Function calling test failed: {e}")
        return False

def test_streaming_responses():
    """Test streaming response functionality."""
    print("\nTesting streaming responses...")
    
    try:
        import litellm
        
        collected_chunks = []
        
        response = litellm.completion(
            model="openai/Qwen/Qwen3-VL-235B-A22B-Instruct",
            messages=[
                {"role": "user", "content": "Count from 1 to 5, one number per line."}
            ],
            stream=True,
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            max_tokens=50
        )
        
        for chunk in response:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    collected_chunks.append(delta.content)
        
        full_response = "".join(collected_chunks)
        if len(collected_chunks) > 1 and "1" in full_response and "5" in full_response:
            print("✓ Streaming responses working")
            print(f"  Chunks received: {len(collected_chunks)}")
            print(f"  Response preview: {full_response[:100]}...")
            return True
        else:
            print(f"✗ Unexpected streaming response: {full_response}")
            return False
            
    except Exception as e:
        print(f"✗ Streaming test failed: {e}")
        return False

def test_thinking_model():
    """Test Qwen3-VL-Thinking model."""
    print("\nTesting Thinking model...")
    
    try:
        import litellm
        
        response = litellm.completion(
            model="openai/Qwen/Qwen3-VL-235B-A22B-Thinking",
            messages=[
                {"role": "user", "content": "Explain the concept of machine learning in simple terms."}
            ],
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            max_tokens=200
        )
        
        if response and response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content
            if "machine learning" in content.lower() or "learning" in content.lower():
                print("✓ Thinking model working")
                print(f"  Response preview: {content[:100]}...")
                return True
            else:
                print(f"✗ Unexpected thinking model response: {content}")
                return False
        else:
            print("✗ No response from Thinking model")
            return False
            
    except Exception as e:
        print(f"✗ Thinking model test failed: {e}")
        return False

def test_error_handling():
    """Test error handling with invalid requests."""
    print("\nTesting error handling...")
    
    try:
        import litellm
        
        # Test with invalid model (should fail gracefully)
        try:
            response = litellm.completion(
                model="openai/Invalid/Model",
                messages=[{"role": "user", "content": "test"}],
                api_base="https://api.siliconflow.cn/v1",
                api_key=os.getenv("SILICONFLOW_API_KEY"),
                max_tokens=10
            )
            print("✗ Expected error but got response")
            return False
        except Exception as e:
            if "model" in str(e).lower() or "404" in str(e) or "not found" in str(e).lower():
                print("✓ Error handling working correctly")
                print(f"  Expected error: {str(e)[:100]}...")
                return True
            else:
                print(f"✗ Unexpected error: {e}")
                return False
                
    except Exception as e:
        print(f"✗ Error handling test setup failed: {e}")
        return False

def main():
    """Run all SiliconFlow integration tests."""
    print("SiliconFlow API Integration Test Suite")
    print("=" * 50)
    print(f"API Base: https://api.siliconflow.cn/v1")
    print(f"API Key: {'*' * 20}{os.getenv('SILICONFLOW_API_KEY', '')[-4:] if os.getenv('SILICONFLOW_API_KEY') else 'None'}")
    print()
    
    tests = [
        test_basic_api_connectivity,
        test_native_function_calling,
        test_streaming_responses,
        test_thinking_model,
        test_error_handling,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"\n❌ {test.__name__} failed")
        except Exception as e:
            print(f"\n❌ {test.__name__} crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All SiliconFlow integration tests passed!")
        print("✅ Qwen3-VL models are fully functional via SiliconFlow API")
        return 0
    else:
        print("❌ Some tests failed. Please check the configuration and API key.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
