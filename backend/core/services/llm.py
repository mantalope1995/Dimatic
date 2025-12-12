"""
LLM API interface for making calls to various language models.

This module provides a unified interface for making API calls to different LLM providers
using LiteLLM with simplified error handling and clean parameter management.
"""

from typing import Union, Dict, Any, Optional, AsyncGenerator, List
import os
import json
import asyncio
import litellm
from litellm.router import Router
from litellm.files.main import ModelResponse
from core.utils.logger import logger
from core.utils.config import config
from core.agentpress.error_processor import ErrorProcessor
from pathlib import Path
from datetime import datetime, timezone

# Configure LiteLLM
# os.environ['LITELLM_LOG'] = 'DEBUG'
# litellm.set_verbose = True  # Enable verbose logging
litellm.modify_params = True
litellm.drop_params = True

# CRITICAL: Disable all LiteLLM internal retries to prevent infinite loops on 400 errors
# We handle retries at our own layer (auto-continue) with proper error checking
litellm.num_retries = 0

# Enable additional debug logging
# import logging
# litellm_logger = logging.getLogger("LiteLLM")
# litellm_logger.setLevel(logging.DEBUG)
provider_router = None


class LLMError(Exception):
    """Exception for LLM-related errors."""
    pass

def setup_api_keys() -> None:
    """Set up API keys from environment variables."""
    if not config:
        logger.warning("Config not loaded - skipping API key setup")
        return
        
    providers = [
        "OPENAI",
        "ANTHROPIC",
        "GROQ",
        "OPENROUTER",
        "XAI",
        "MORPH",
        "GEMINI",
        "OPENAI_COMPATIBLE",
        "SILICONFLOW",
    ]
    
    for provider in providers:
        try:
            key = getattr(config, f"{provider}_API_KEY", None)
            if key:
                # logger.debug(f"API key set for provider: {provider}")
                pass
            else:
                logger.debug(f"No API key found for provider: {provider} (this is normal if not using this provider)")
        except AttributeError as e:
            logger.debug(f"Could not access {provider}_API_KEY: {e}")

    # Set up OpenRouter API base if not already set
    if hasattr(config, 'OPENROUTER_API_KEY') and hasattr(config, 'OPENROUTER_API_BASE'):
        if config.OPENROUTER_API_KEY and config.OPENROUTER_API_BASE:
            os.environ["OPENROUTER_API_BASE"] = config.OPENROUTER_API_BASE
            # logger.debug(f"Set OPENROUTER_API_BASE to {config.OPENROUTER_API_BASE}")

    # Set up Minimax API key
    if hasattr(config, 'MINIMAX_API_KEY'):
        minimax_key = config.MINIMAX_API_KEY
        if minimax_key:
            os.environ["MINIMAX_API_KEY"] = minimax_key
            logger.debug("Minimax API key configured")
        else:
            logger.debug("MINIMAX_API_KEY not configured - Minimax models will not be available")

    # Set up SiliconFlow API key
    if hasattr(config, 'SILICONFLOW_API_KEY'):
        siliconflow_key = config.SILICONFLOW_API_KEY
        if siliconflow_key:
            os.environ["SILICONFLOW_API_KEY"] = siliconflow_key
            logger.debug("SiliconFlow API key configured")
        else:
            logger.debug("SILICONFLOW_API_KEY not configured - Qwen3-VL models will not be available")

def setup_provider_router(openai_compatible_api_key: str = None, openai_compatible_api_base: str = None):
    global provider_router
    
    # Get config values safely - prioritize SiliconFlow for Qwen3-VL models
    siliconflow_api_key = getattr(config, 'SILICONFLOW_API_KEY', None) if config else None
    siliconflow_api_base = getattr(config, 'SILICONFLOW_API_BASE', None) if config else None
    minimax_api_key = getattr(config, 'MINIMAX_API_KEY', None) if config else None
    minimax_api_base = getattr(config, 'MINIMAX_API_BASE', None) if config else None
    config_openai_key = getattr(config, 'OPENAI_COMPATIBLE_API_KEY', None) if config else None
    config_openai_base = getattr(config, 'OPENAI_COMPATIBLE_API_BASE', None) if config else None
    
    # Use SiliconFlow API key if available for Qwen3-VL models
    qwen_api_key = siliconflow_api_key
    qwen_api_base = siliconflow_api_base
    
    # Use Minimax API key if available, otherwise fall back to OpenAI-compatible key
    effective_api_key = openai_compatible_api_key or minimax_api_key or config_openai_key
    effective_api_base = openai_compatible_api_base or minimax_api_base or config_openai_base
    
    model_list = [
        # Qwen3-VL models via SiliconFlow (primary provider for Qwen3-VL optimization)
        {
            "model_name": "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "litellm_params": {
                "model": "openai/Qwen/Qwen3-VL-235B-A22B-Instruct",
                "api_key": qwen_api_key,
                "api_base": qwen_api_base,
                "max_tokens": 262144,  # Maximum output tokens
                "context_window": 262144,  # Context window
            },
            "model_info": {
                "base_model": "openai/Qwen/Qwen3-VL-235B-A22B-Instruct",
                "context_window": 262144,
            },
        },
        {
            "model_name": "Qwen/Qwen3-VL-235B-A22B-Thinking",
            "litellm_params": {
                "model": "openai/Qwen/Qwen3-VL-235B-A22B-Thinking",
                "api_key": qwen_api_key,
                "api_base": qwen_api_base,
                "max_tokens": 262144,
                "context_window": 262144,
            },
            "model_info": {
                "base_model": "openai/Qwen/Qwen3-VL-235B-A22B-Thinking",
                "context_window": 262144,
            },
        },
        {
            "model_name": "Qwen/*",  # Fallback for other Qwen models
            "litellm_params": {
                "model": "openai/Qwen/*",
                "api_key": qwen_api_key,
                "api_base": qwen_api_base,
            },
        },
        # Legacy MiniMax model (kept for compatibility)
        {
            "model_name": "openai-compatible/MiniMax-m2", # Specific MiniMax model
            "litellm_params": {
                "model": "openai/MiniMax-m2",
                "api_key": effective_api_key,
                "api_base": effective_api_base,
                # Note: max_tokens removed - it controls output tokens, not context window
                # Context window validation is handled via model_info.base_model and enable_pre_call_checks
            },
            "model_info": {
                "base_model": "openai/MiniMax-m2",  # Enables LiteLLM context window lookup
            },
        },
        {
            "model_name": "openai-compatible/*", # fallback for other OpenAI-Compatible providers
            "litellm_params": {
                "model": "openai/*",
                "api_key": effective_api_key,
                "api_base": effective_api_base,
            },
        },
        {
            "model_name": "*", # supported LLM provider by LiteLLM
            "litellm_params": {
                "model": "*",
            },
        },
    ]
    
    # Qwen3-VL models are primary - fallback to MiniMax if SiliconFlow unavailable
    fallbacks = []
    
    # No context window fallbacks needed for single-provider setup
    context_window_fallbacks = []
    
    # Configure Router with specific retry settings:
    # - num_retries=0: Disable router-level retries - we handle errors at our layer
    # - fallbacks: ONLY for rate limits and overloaded errors, NOT for 400 errors
    # - context_window_fallbacks: Automatically fallback to models with larger context windows when context is exceeded
    # - enable_pre_call_checks: Validates context window limits before making API calls
    # CRITICAL: 400 Bad Request errors must NOT retry or fallback - they're permanent failures
    # EXCEPTION: ContextWindowExceededError is a special case where fallback to larger context models is appropriate
    provider_router = Router(
        model_list=model_list,
        num_retries=0,  # CRITICAL: Disable all router-level retries to prevent infinite loops
        fallbacks=fallbacks,
        context_window_fallbacks=context_window_fallbacks,  # Handle context window exceeded errors
        enable_pre_call_checks=True,  # Validate context window limits before API calls
        # Only use fallbacks for rate limits (429) and server errors (5xx), NOT client errors (4xx)
        # context_window_fallbacks are separate and only triggered by context length issues
    )
    
    logger.info("Configured LiteLLM Router with Qwen3-VL models as primary provider via SiliconFlow")

def _configure_openai_compatible(params: Dict[str, Any], model_name: str, api_key: Optional[str], api_base: Optional[str]) -> None:
    """Configure OpenAI-compatible provider setup."""
    if not model_name.startswith("openai-compatible/"):
        return
    
    # Get config values safely - prioritize MINIMAX_API_KEY for MiniMax models
    minimax_api_key = getattr(config, 'MINIMAX_API_KEY', None) if config else None
    minimax_api_base = getattr(config, 'MINIMAX_API_BASE', None) if config else None
    config_openai_key = getattr(config, 'OPENAI_COMPATIBLE_API_KEY', None) if config else None
    config_openai_base = getattr(config, 'OPENAI_COMPATIBLE_API_BASE', None) if config else None
    
    # Use Minimax API key if available, otherwise fall back to OpenAI-compatible key
    effective_api_key = api_key or minimax_api_key or config_openai_key
    effective_api_base = api_base or minimax_api_base or config_openai_base
    
    # Check if have required config either from parameters or environment
    if not effective_api_key or not effective_api_base:
        raise LLMError(
            "MINIMAX_API_KEY (or OPENAI_COMPATIBLE_API_KEY) and MINIMAX_API_BASE (or OPENAI_COMPATIBLE_API_BASE) are required for openai-compatible models. If just updated the environment variables, wait a few minutes or restart the service to ensure they are loaded."
        )
    
    setup_provider_router(effective_api_key, effective_api_base)
    logger.debug(f"Configured OpenAI-compatible provider with custom API base")

def _add_tools_config(params: Dict[str, Any], tools: Optional[List[Dict[str, Any]]], tool_choice: str) -> None:
    """Add tools configuration to parameters."""
    if tools is None:
        return
    
    params.update({
        "tools": tools,
        "tool_choice": tool_choice
    })
    # logger.debug(f"Added {len(tools)} tools to API parameters")

async def make_llm_api_call(
    messages: List[Dict[str, Any]],
    model_name: str,
    response_format: Optional[Any] = None,
    temperature: float = 0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: str = "auto",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    stream: bool = True,  # Always stream for better UX
    top_p: Optional[float] = None,
    model_id: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    stop: Optional[List[str]] = None,
) -> Union[Dict[str, Any], AsyncGenerator, ModelResponse]:
    """Make an API call to a language model using LiteLLM.
    
    Args:
        messages: List of message dictionaries
        model_name: Name of the model to use
        response_format: Optional response format specification
        temperature: Temperature for sampling (0-1)
        max_tokens: Maximum tokens to generate
        tools: Optional list of tool definitions
        tool_choice: Tool choice strategy ("auto", "required", "none")
        api_key: Optional API key override
        api_base: Optional API base URL override
        stream: Whether to stream the response
        top_p: Optional top_p for sampling
        model_id: Optional model ID for tracking
        headers: Optional headers to send with request
        extra_headers: Optional extra headers to send with request
        stop: Optional list of stop sequences
    """
    logger.info(f"Making LLM API call to model: {model_name} with {len(messages)} messages")
    
    # Prepare parameters using centralized model configuration
    from core.ai_models import model_manager
    resolved_model_name = model_manager.resolve_model_id(model_name) or model_name
    
    # Only pass headers/extra_headers if they are not None to avoid overriding model config
    override_params = {
        "messages": messages,
        "temperature": temperature,
        "response_format": response_format,
        "top_p": top_p,
        "stream": stream,
        "api_key": api_key,
        "api_base": api_base,
        "stop": stop
    }
    
    # Only add headers if they are provided (not None)
    if headers is not None:
        override_params["headers"] = headers
    if extra_headers is not None:
        override_params["extra_headers"] = extra_headers
    
    params = model_manager.get_litellm_params(resolved_model_name, **override_params)
    
    # Ensure stop sequences are in final params
    if stop is not None:
        params["stop"] = stop
        logger.info(f"🛑 Stop sequences configured: {stop}")
    else:
        params.pop("stop", None)
    
    if model_id:
        params["model_id"] = model_id
    
    if stream:
        params["stream_options"] = {"include_usage": True}
    
    # Apply additional configurations
    _configure_openai_compatible(params, model_name, api_key, api_base)
    _add_tools_config(params, tools, tool_choice)
    
    # Final safeguard: Re-apply stop sequences
    if stop is not None:
        params["stop"] = stop
    
    try:
        # Save debug input if enabled via config
        if config and config.DEBUG_SAVE_LLM_IO:
            try:
                debug_dir = Path("debug_streams")
                debug_dir.mkdir(exist_ok=True)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                debug_file = debug_dir / f"input_{timestamp}.json"
        
                # Save the exact params going to LiteLLM
                debug_data = {
                    "timestamp": timestamp,
                    "model": params.get("model"),
                    "messages": params.get("messages"),
                    "temperature": params.get("temperature"),
                    "max_tokens": params.get("max_tokens"),
                    "stop": params.get("stop"),
                    "stream": params.get("stream"),
                    "tools": params.get("tools"),
                    "tool_choice": params.get("tool_choice"),
                }
                
                with open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                    
                logger.info(f"📁 Saved LLM input to: {debug_file}")
            except Exception as e:
                logger.warning(f"⚠️ Error saving debug input: {e}")
        
        response = await provider_router.acompletion(**params)
        
        # For streaming responses, we need to handle errors that occur during iteration
        if hasattr(response, '__aiter__') and stream:
            return _wrap_streaming_response(response)
        
        return response
        
    except Exception as e:
        # Use ErrorProcessor to handle the error consistently
        processed_error = ErrorProcessor.process_llm_error(e, context={"model": model_name})
        ErrorProcessor.log_error(processed_error)
        raise LLMError(processed_error.message)

async def _wrap_streaming_response(response) -> AsyncGenerator:
    """Wrap streaming response to handle errors during iteration."""
    try:
        async for chunk in response:
            yield chunk
    except Exception as e:
        # Convert streaming errors to processed errors
        processed_error = ErrorProcessor.process_llm_error(e)
        ErrorProcessor.log_error(processed_error)
        raise LLMError(processed_error.message)

setup_api_keys()
setup_provider_router()


if __name__ == "__main__":
    from litellm import completion
    import os

    setup_api_keys()

    response = completion(
        model="minimax/minimax-m2",
        messages=[{"role": "user", "content": "Hello! Testing Minimax-m2."}],
        max_tokens=100,
    )

