"""
Comprehensive tests for MiniMax-M2 with OpenAI SDK compatibility.

These tests verify that MiniMax-M2 properly implements OpenAI SDK format
for API requests, streaming responses, tool calling, thinking tokens, and error handling.
"""

import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional
import json

# Set environment variables before importing modules
os.environ["ENV_MODE"] = "LOCAL"
os.environ["LOGGING_LEVEL"] = "ERROR"

# Mock langfuse before importing modules that use it
sys.modules['langfuse'] = MagicMock()
sys.modules['langfuse.client'] = MagicMock()

from core.ai_models.registry import registry
from core.services.llm import make_llm_api_call
from core.utils.config import Configuration
from core.utils.logger import logger


class TestMinimaxOpenAICompatibility:
    """Test MiniMax-M2 compatibility with OpenAI SDK format."""
    
    @pytest.mark.asyncio
    async def test_minimax_model_openai_sdk_format(self):
        """Test that MiniMax-M2 model is configured with OpenAI SDK format."""
        model = registry.get("minimax/minimax-m2")
        
        assert model is not None, "MiniMax-M2 should be registered"
        assert model.provider.value == "minimax", "Provider should be MINIMAX"
        assert model.config.api_base == "https://api.minimax.io/v1", "API base should be MiniMax OpenAI-compatible endpoint"
        # OpenAI-compatible API doesn't require extra headers
        assert model.config.extra_headers is None, "Should not have extra headers for OpenAI-compatible API"
    
    @pytest.mark.asyncio
    async def test_minimax_litellm_parameters(self):
        """Test that MiniMax-M2 generates correct LiteLLM parameters."""
        model = registry.get("minimax/minimax-m2")
        params = model.get_litellm_params()
        
        # Verify essential parameters
        assert params["model"] == "openai/MiniMax-M2", "Model ID should be correct"
        assert params["api_base"] == "https://api.minimax.io/v1", "API base should be MiniMax OpenAI-compatible endpoint"
        # OpenAI-compatible API doesn't require extra headers
        assert "extra_headers" not in params or params.get("extra_headers") is None, "Should not have extra headers"
    
    @pytest.mark.asyncio
    async def test_minimax_streaming_thinking_tokens(self):
        """Test that MiniMax-M2 properly handles thinking tokens in streaming with reasoning_split."""
        # Mock streaming response with reasoning_details (OpenAI-compatible format with reasoning_split=True)
        mock_chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_details": [{"text": "Let me think about this step by step..."}]
                    }
                }]
            },
            {
                "choices": [{
                    "delta": {
                        "reasoning_details": [{"text": "I need to analyze the problem carefully."}]
                    }
                }]
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Based on my analysis, here's my response."
                    }
                }]
            },
            {
                "choices": [{
                    "delta": {},
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150
                }
            }
        ]
        
        # Mock the LiteLLM response
        with patch('core.services.llm.provider_router.acompletion') as mock_completion:
            mock_completion.return_value = self._async_generator_from_chunks(mock_chunks)
            
            # Make API call
            response = await make_llm_api_call(
                messages=[{"role": "user", "content": "Test thinking"}],
                model_name="minimax/minimax-m2",
                stream=True
            )
            
            # Process the response
            content_chunks = []
            thinking_chunks = []
            usage_info = None
            
            async for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta if hasattr(chunk.choices[0], 'delta') else None
                    if delta:
                        if hasattr(delta, 'reasoning_details') and delta.reasoning_details:
                            for detail in delta.reasoning_details:
                                if "text" in detail:
                                    thinking_chunks.append(detail["text"])
                        elif hasattr(delta, 'content') and delta.content:
                            content_chunks.append(delta.content)
                
                # Check for usage information
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info = chunk.usage
                    break
            
            # Verify thinking content was captured
            assert len(thinking_chunks) > 0, "Should have captured thinking content"
            assert "Let me think about this" in "".join(thinking_chunks), "Thinking content should be preserved"
            
            # Verify regular content was captured
            assert len(content_chunks) > 0, "Should have captured regular content"
            assert "Based on my analysis" in "".join(content_chunks), "Regular content should be preserved"
    
    @pytest.mark.asyncio
    async def test_minimax_tool_calling_format(self):
        """Test that MiniMax-M2 properly handles OpenAI tool calling format."""
        # Mock streaming response with tool calls
        mock_chunks = [
            {
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"param": "value"}'
                            }
                        }]
                    }
                }]
            },
            {
                "choices": [{
                    "delta": {
                        "content": "I'm calling the test tool now."
                    }
                }]
            }
        ]
        
        with patch('core.services.llm.provider_router.acompletion') as mock_completion:
            mock_completion.return_value = self._async_generator_from_chunks(mock_chunks)
            
            # Make API call with tools
            response = await make_llm_api_call(
                messages=[{"role": "user", "content": "Use test_tool"}],
                model_name="minimax/minimax-m2",
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "test_tool",
                        "description": "A test tool",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "param": {
                                    "type": "string",
                                    "description": "Test parameter"
                                }
                            },
                            "required": ["param"]
                        }
                    }
                }],
                stream=True
            )
            
            # Process response and verify tool call format
            tool_calls_found = False
            async for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta if hasattr(chunk.choices[0], 'delta') else None
                    if delta and hasattr(delta, 'tool_calls') and delta.tool_calls:
                        tool_calls_found = True
                        tool_call = delta.tool_calls[0]
                        assert tool_call["id"] == "call_123", "Tool call ID should be preserved"
                        assert tool_call["function"]["name"] == "test_tool", "Tool name should be preserved"
                        assert tool_call["function"]["arguments"] == '{"param": "value"}', "Arguments should be preserved"
            
            assert tool_calls_found, "Tool calls should be detected in response"
    
    @pytest.mark.asyncio
    async def test_minimax_error_handling(self):
        """Test that MiniMax-M2 errors are properly handled."""
        # Mock error response
        error_response = {
            "error": {
                "message": "Invalid request: missing required parameter",
                "type": "invalid_request_error",
                "code": 400
            }
        }
        
        with patch('core.services.llm.provider_router.acompletion') as mock_completion:
            mock_completion.side_effect = Exception(str(error_response))
            
            # Verify error is raised and processed
            with pytest.raises(Exception) as exc_info:
                await make_llm_api_call(
                    messages=[{"role": "user", "content": "Test"}],
                    model_name="minimax/minimax-m2"
                )
            
            # Verify error contains expected message
            assert "Invalid request" in str(exc_info.value), "Error message should be preserved"
    
    @pytest.mark.asyncio
    async def test_minimax_configuration_loading(self):
        """Test that MiniMax configuration is properly loaded from environment."""
        test_config = {
            "MINIMAX_API_KEY": "test_key_12345",
            "MINIMAX_API_BASE": "https://api.minimax.io/v1",
            "SUPABASE_URL": "http://test",
            "SUPABASE_ANON_KEY": "test",
            "SUPABASE_SERVICE_ROLE_KEY": "test",
            "SUPABASE_JWT_SECRET": "test"
        }
        
        with patch.dict(os.environ, test_config, clear=True):
            config = Configuration()
            
            assert config.MINIMAX_API_KEY == "test_key_12345", "API key should be loaded"
            assert config.MINIMAX_API_BASE == "https://api.minimax.io/v1", "API base should be loaded"
    
    async def _async_generator_from_chunks(self, chunks: List[Dict[str, Any]]):
        """Helper to create an async generator from mock chunks."""
        async def generator():
            for chunk in chunks:
                # Create a mock object that mimics LiteLLM response structure
                mock_chunk = MagicMock()
                for key, value in chunk.items():
                    setattr(mock_chunk, key, value)
                yield mock_chunk
        return generator()
    
    @pytest.mark.asyncio
    async def test_minimax_model_aliases(self):
        """Test that MiniMax-M2 can be accessed via various aliases."""
        aliases = ["minimax-m2", "MiniMax-M2", "Minimax-m2", "minimax/minimax-m2", "openai/minimax-m2"]
        
        for alias in aliases:
            model = registry.get(alias)
            assert model is not None, f"Should be able to get model via alias: {alias}"
            assert model.id == "openai/MiniMax-M2", f"Model ID should be correct for alias: {alias}"


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])
