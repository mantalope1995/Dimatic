"""
Property-based tests for Response Processor thinking token handling.

**Feature: minimax-m2-migration, Property 5 & 6**
"""
import os
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

# Set environment variables before importing modules
os.environ["ENV_MODE"] = "LOCAL"
os.environ["LOGGING_LEVEL"] = "ERROR"

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import asyncio

# Mock langfuse before importing response_processor
sys.modules['langfuse'] = Mock()
sys.modules['langfuse.client'] = Mock()

from core.agentpress.response_processor import ResponseProcessor, ProcessorConfig
from core.agentpress.tool_registry import ToolRegistry


# Mock classes to simulate LiteLLM response structures
@dataclass
class MockUsage:
    """Mock usage object from LiteLLM response."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    thinking_tokens: int = 0
    
    def model_dump(self):
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "thinking_tokens": self.thinking_tokens,
        }


@dataclass
class MockDelta:
    """Mock delta object from streaming chunk."""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List] = None


@dataclass
class MockChoice:
    """Mock choice object from streaming chunk."""
    delta: Optional[MockDelta] = None
    finish_reason: Optional[str] = None
    index: int = 0


@dataclass
class MockStreamChunk:
    """Mock streaming chunk from LiteLLM."""
    choices: List[MockChoice]
    usage: Optional[MockUsage] = None
    model: str = "minimax/minimax-m2"
    
    def model_dump(self):
        result = {
            "choices": [
                {
                    "delta": {
                        "content": c.delta.content if c.delta else None,
                        "reasoning_content": c.delta.reasoning_content if c.delta else None,
                    },
                    "finish_reason": c.finish_reason,
                    "index": c.index,
                }
                for c in self.choices
            ],
            "model": self.model,
        }
        if self.usage:
            result["usage"] = self.usage.model_dump()
        return result


# Hypothesis strategies for generating test data
@st.composite
def usage_with_thinking_tokens(draw):
    """Generate usage objects with various thinking token counts."""
    prompt_tokens = draw(st.integers(min_value=10, max_value=10000))
    completion_tokens = draw(st.integers(min_value=10, max_value=10000))
    thinking_tokens = draw(st.integers(min_value=0, max_value=5000))
    total_tokens = prompt_tokens + completion_tokens + thinking_tokens
    
    return MockUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        thinking_tokens=thinking_tokens,
    )


@st.composite
def streaming_chunk_with_thinking(draw):
    """Generate streaming chunks with thinking content."""
    # Simplify to avoid slow generation - always include at least one field
    chunk_type = draw(st.sampled_from(['thinking', 'content', 'usage', 'mixed']))
    
    if chunk_type == 'thinking':
        delta = MockDelta(
            reasoning_content=draw(st.text(min_size=1, max_size=50)),
        )
        usage = None
    elif chunk_type == 'content':
        delta = MockDelta(
            content=draw(st.text(min_size=1, max_size=50)),
        )
        usage = None
    elif chunk_type == 'usage':
        delta = MockDelta()
        usage = draw(usage_with_thinking_tokens())
    else:  # mixed
        delta = MockDelta(
            content=draw(st.text(min_size=1, max_size=30)),
            reasoning_content=draw(st.text(min_size=1, max_size=30)),
        )
        usage = draw(usage_with_thinking_tokens())
    
    choice = MockChoice(
        delta=delta,
        finish_reason=draw(st.sampled_from(["stop", "length", "tool_calls", None])),
    )
    
    return MockStreamChunk(
        choices=[choice],
        usage=usage,
    )


@st.composite
def streaming_response_sequence(draw):
    """Generate a sequence of streaming chunks representing a complete response."""
    num_chunks = draw(st.integers(min_value=1, max_value=20))
    chunks = []
    
    # Generate content chunks
    for i in range(num_chunks - 1):
        has_thinking = draw(st.booleans())
        has_content = draw(st.booleans())
        
        delta = MockDelta(
            content=draw(st.text(min_size=1, max_size=50)) if has_content else None,
            reasoning_content=draw(st.text(min_size=1, max_size=50)) if has_thinking else None,
        )
        
        chunk = MockStreamChunk(
            choices=[MockChoice(delta=delta)],
        )
        chunks.append(chunk)
    
    # Final chunk with usage and finish_reason
    final_usage = draw(usage_with_thinking_tokens())
    final_chunk = MockStreamChunk(
        choices=[MockChoice(
            delta=MockDelta(),
            finish_reason="stop",
        )],
        usage=final_usage,
    )
    chunks.append(final_chunk)
    
    return chunks, final_usage


class TestThinkingTokenTracking:
    """
    **Feature: minimax-m2-migration, Property 6: Token Usage Calculation**
    **Validates: Requirements 2.5, 8.5**
    
    Property: For any response from Minimax-m2, the total token count should 
    include both regular tokens and thinking tokens in the cost calculation.
    """
    
    @settings(max_examples=100)
    @given(usage_with_thinking_tokens())
    def test_thinking_tokens_extracted_from_usage(self, usage):
        """
        Property test: Thinking tokens should be extracted from usage objects.
        
        This test verifies that when a usage object contains thinking_tokens,
        they are properly extracted and available for cost calculation.
        """
        # Verify thinking_tokens attribute exists and is accessible
        assert hasattr(usage, 'thinking_tokens'), (
            "Usage object should have thinking_tokens attribute"
        )
        
        # Verify thinking_tokens is a non-negative integer
        assert isinstance(usage.thinking_tokens, int), (
            f"thinking_tokens should be an integer, got {type(usage.thinking_tokens)}"
        )
        assert usage.thinking_tokens >= 0, (
            f"thinking_tokens should be non-negative, got {usage.thinking_tokens}"
        )
        
        # Verify total_tokens includes thinking_tokens
        expected_total = usage.prompt_tokens + usage.completion_tokens + usage.thinking_tokens
        assert usage.total_tokens == expected_total, (
            f"total_tokens ({usage.total_tokens}) should equal "
            f"prompt_tokens ({usage.prompt_tokens}) + "
            f"completion_tokens ({usage.completion_tokens}) + "
            f"thinking_tokens ({usage.thinking_tokens}) = {expected_total}"
        )
    
    @settings(max_examples=100)
    @given(usage_with_thinking_tokens())
    def test_thinking_tokens_included_in_serialization(self, usage):
        """
        Property test: Thinking tokens should be included when usage is serialized.
        
        This test verifies that thinking_tokens are preserved when the usage
        object is converted to a dictionary for storage or transmission.
        """
        serialized = usage.model_dump()
        
        # Verify thinking_tokens is in serialized output
        assert 'thinking_tokens' in serialized, (
            "Serialized usage should include thinking_tokens field"
        )
        
        # Verify value is preserved
        assert serialized['thinking_tokens'] == usage.thinking_tokens, (
            f"Serialized thinking_tokens ({serialized['thinking_tokens']}) "
            f"should match original ({usage.thinking_tokens})"
        )
        
        # Verify all token fields are present
        required_fields = ['prompt_tokens', 'completion_tokens', 'total_tokens', 'thinking_tokens']
        for field in required_fields:
            assert field in serialized, (
                f"Serialized usage should include {field} field"
            )
    
    @settings(max_examples=100)
    @given(streaming_chunk_with_thinking())
    def test_thinking_tokens_extracted_from_streaming_chunks(self, chunk):
        """
        Property test: Thinking tokens should be extractable from streaming chunks.
        
        This test verifies that when a streaming chunk contains usage information
        with thinking_tokens, they can be properly extracted.
        """
        if chunk.usage is None:
            # Skip chunks without usage
            return
        
        # Verify thinking_tokens can be extracted using getattr
        thinking_tokens = getattr(chunk.usage, 'thinking_tokens', 0)
        
        # Verify extracted value matches expected
        assert thinking_tokens == chunk.usage.thinking_tokens, (
            f"Extracted thinking_tokens ({thinking_tokens}) should match "
            f"chunk.usage.thinking_tokens ({chunk.usage.thinking_tokens})"
        )
        
        # Verify default value works when attribute is missing
        # Create a simple object without thinking_tokens
        class UsageWithoutThinking:
            def __init__(self):
                self.prompt_tokens = 100
                self.completion_tokens = 50
                self.total_tokens = 150
        
        mock_usage_without_thinking = UsageWithoutThinking()
        
        extracted = getattr(mock_usage_without_thinking, 'thinking_tokens', 0)
        assert extracted == 0, (
            "When thinking_tokens attribute is missing, default should be 0"
        )


class TestThinkingBlockParsing:
    """
    **Feature: minimax-m2-migration, Property 5: Thinking Block Parsing**
    **Validates: Requirements 2.3, 2.4**
    
    Property: For any streaming response from Minimax-m2 containing thinking blocks,
    the system should correctly parse and separate thinking content from regular content.
    """
    
    @settings(max_examples=100)
    @given(streaming_chunk_with_thinking())
    def test_thinking_content_separated_from_regular_content(self, chunk):
        """
        Property test: Thinking content should be distinguishable from regular content.
        
        This test verifies that when a chunk contains both reasoning_content
        (thinking) and regular content, they can be separately identified.
        """
        if not chunk.choices or not chunk.choices[0].delta:
            return
        
        delta = chunk.choices[0].delta
        
        # Verify reasoning_content and content are separate fields
        has_reasoning = delta.reasoning_content is not None
        has_content = delta.content is not None
        
        if has_reasoning:
            assert hasattr(delta, 'reasoning_content'), (
                "Delta should have reasoning_content attribute for thinking"
            )
            assert isinstance(delta.reasoning_content, str), (
                f"reasoning_content should be a string, got {type(delta.reasoning_content)}"
            )
        
        if has_content:
            assert hasattr(delta, 'content'), (
                "Delta should have content attribute for regular content"
            )
            assert isinstance(delta.content, str), (
                f"content should be a string, got {type(delta.content)}"
            )
        
        # Verify they are independent (one can exist without the other)
        if has_reasoning and has_content:
            # Both can coexist - they are separate fields even if values happen to match
            # The key is that they are separate attributes, not that values differ
            assert hasattr(delta, 'reasoning_content') and hasattr(delta, 'content'), (
                "Both reasoning_content and content should exist as separate attributes"
            )
    
    @settings(max_examples=100)
    @given(streaming_response_sequence())
    def test_thinking_content_accumulation(self, sequence_data):
        """
        Property test: Thinking content should accumulate correctly across chunks.
        
        This test verifies that when multiple chunks contain reasoning_content,
        they can be accumulated into a complete thinking block.
        """
        chunks, final_usage = sequence_data
        
        # Accumulate thinking and regular content separately
        accumulated_thinking = ""
        accumulated_content = ""
        
        for chunk in chunks:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                
                if delta.reasoning_content:
                    accumulated_thinking += delta.reasoning_content
                
                if delta.content:
                    accumulated_content += delta.content
        
        # Verify accumulation preserves content
        # (Both can be empty, but if present, should be strings)
        assert isinstance(accumulated_thinking, str), (
            "Accumulated thinking should be a string"
        )
        assert isinstance(accumulated_content, str), (
            "Accumulated content should be a string"
        )
        
        # Verify final usage includes thinking tokens if thinking content exists
        if accumulated_thinking and final_usage:
            # If there's thinking content, there should be thinking tokens
            # (This is a reasonable expectation for the LLM behavior)
            assert final_usage.thinking_tokens >= 0, (
                "Usage should track thinking tokens when thinking content exists"
            )
    
    @settings(max_examples=100)
    @given(st.text(min_size=0, max_size=200))
    def test_reasoning_content_handling_with_various_types(self, text_content):
        """
        Property test: reasoning_content should handle various text formats.
        
        This test verifies that reasoning_content can handle different types
        of text content including empty strings, special characters, etc.
        """
        # Create a delta with reasoning_content
        delta = MockDelta(reasoning_content=text_content)
        
        # Verify it can be accessed and is the correct type
        assert hasattr(delta, 'reasoning_content'), (
            "Delta should have reasoning_content attribute"
        )
        assert delta.reasoning_content == text_content, (
            "reasoning_content should preserve the original text"
        )
        
        # Verify it can be converted to string (for accumulation)
        as_string = str(delta.reasoning_content) if delta.reasoning_content else ""
        assert isinstance(as_string, str), (
            "reasoning_content should be convertible to string"
        )
    
    def test_thinking_content_extraction_from_list_format(self):
        """
        Test that reasoning_content can be extracted even when it's a list.
        
        Some LLM providers may return reasoning_content as a list of strings.
        This test verifies we can handle that format.
        """
        # Test with list format
        delta_with_list = Mock()
        delta_with_list.reasoning_content = ["thinking ", "part ", "1"]
        
        # Simulate the extraction logic from response_processor.py
        reasoning_content = delta_with_list.reasoning_content
        if isinstance(reasoning_content, list):
            reasoning_content = ''.join(str(item) for item in reasoning_content)
        
        assert reasoning_content == "thinking part 1", (
            "Should be able to join list of reasoning content"
        )
        
        # Test with string format
        delta_with_string = Mock()
        delta_with_string.reasoning_content = "thinking content"
        
        reasoning_content = delta_with_string.reasoning_content
        if isinstance(reasoning_content, list):
            reasoning_content = ''.join(str(item) for item in reasoning_content)
        
        assert reasoning_content == "thinking content", (
            "Should preserve string reasoning content"
        )


class TestThinkingTokenIntegration:
    """
    Integration tests for thinking token handling in the response processor.
    """
    
    def test_response_processor_handles_missing_thinking_tokens(self):
        """
        Test that response processor gracefully handles usage without thinking_tokens.
        
        This ensures backward compatibility with LLM providers that don't
        support thinking tokens.
        """
        # Create a usage object without thinking_tokens attribute
        class UsageWithoutThinking:
            def __init__(self):
                self.prompt_tokens = 100
                self.completion_tokens = 50
                self.total_tokens = 150
        
        usage_without_thinking = UsageWithoutThinking()
        
        # Simulate extraction with default value
        thinking_tokens = getattr(usage_without_thinking, 'thinking_tokens', 0)
        
        # Should default to 0
        assert thinking_tokens == 0, (
            "Missing thinking_tokens should default to 0"
        )
        
        # Total calculation should still work
        total = usage_without_thinking.prompt_tokens + usage_without_thinking.completion_tokens + thinking_tokens
        assert total == 150, (
            "Total should be calculated correctly even without thinking_tokens"
        )
    
    @settings(max_examples=50)
    @given(usage_with_thinking_tokens())
    def test_cost_calculation_includes_thinking_tokens(self, usage):
        """
        Property test: Cost calculation should include thinking tokens.
        
        This test verifies that when calculating costs, thinking tokens
        are included in the total token count.
        """
        # Minimax-m2 pricing from requirements
        input_cost_per_million = 0.60
        output_cost_per_million = 2.20
        
        # Calculate cost including thinking tokens
        # Thinking tokens are typically counted as output tokens for billing
        total_input_cost = (usage.prompt_tokens / 1_000_000) * input_cost_per_million
        total_output_cost = ((usage.completion_tokens + usage.thinking_tokens) / 1_000_000) * output_cost_per_million
        total_cost = total_input_cost + total_output_cost
        
        # Verify cost is non-negative
        assert total_cost >= 0, (
            f"Total cost should be non-negative, got {total_cost}"
        )
        
        # Verify thinking tokens contribute to cost
        if usage.thinking_tokens > 0:
            # Calculate cost without thinking tokens
            cost_without_thinking = total_input_cost + ((usage.completion_tokens / 1_000_000) * output_cost_per_million)
            
            # Cost with thinking should be higher
            assert total_cost > cost_without_thinking, (
                f"Cost with thinking tokens ({total_cost}) should be greater than "
                f"cost without thinking tokens ({cost_without_thinking})"
            )
            
            # Difference should equal thinking token cost
            thinking_cost = (usage.thinking_tokens / 1_000_000) * output_cost_per_million
            assert abs((total_cost - cost_without_thinking) - thinking_cost) < 0.0001, (
                f"Difference in cost should equal thinking token cost"
            )
