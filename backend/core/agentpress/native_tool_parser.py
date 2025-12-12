"""
Native Tool Call Parser Module

This module provides utilities for parsing OpenAI-style native tool calls from LLM responses.
"""

import json
import uuid
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


def extract_tool_call_chunk_data(tool_call_chunk: Any) -> Dict[str, Any]:
    """
    Extract tool call chunk data from a LiteLLM tool_call_chunk object.
    
    Args:
        tool_call_chunk: LiteLLM tool_call_chunk object (may have model_dump or manual attributes)
        
    Returns:
        Dictionary with 'id', 'index', 'type', 'function' keys
    """
    tool_call_data_chunk = {}
    
    if hasattr(tool_call_chunk, 'model_dump'):
        tool_call_data_chunk = tool_call_chunk.model_dump()
    else:
        # Manual extraction for compatibility
        if hasattr(tool_call_chunk, 'id'):
            tool_call_data_chunk['id'] = tool_call_chunk.id
        if hasattr(tool_call_chunk, 'index'):
            tool_call_data_chunk['index'] = tool_call_chunk.index
        if hasattr(tool_call_chunk, 'type'):
            tool_call_data_chunk['type'] = tool_call_chunk.type
        if hasattr(tool_call_chunk, 'function'):
            tool_call_data_chunk['function'] = {}
            if hasattr(tool_call_chunk.function, 'name'):
                tool_call_data_chunk['function']['name'] = tool_call_chunk.function.name
            if hasattr(tool_call_chunk.function, 'arguments'):
                args = tool_call_chunk.function.arguments
                if isinstance(args, str):
                    tool_call_data_chunk['function']['arguments'] = args
                else:
                    tool_call_data_chunk['function']['arguments'] = json.dumps(args)
    
    return tool_call_data_chunk


def is_tool_call_complete(tool_call_buffer_entry: Dict[str, Any]) -> bool:
    """
    Check if a buffered tool call is complete (has all required fields and valid JSON arguments).
    
    Args:
        tool_call_buffer_entry: Dictionary from tool_calls_buffer with 'id', 'function' keys
        
    Returns:
        True if tool call is complete and ready to execute
    """
    if not tool_call_buffer_entry:
        return False
    
    if not (tool_call_buffer_entry.get('id') and 
            tool_call_buffer_entry.get('function', {}).get('name') and
            tool_call_buffer_entry.get('function', {}).get('arguments')):
        return False
    
    # Verify JSON arguments are complete and parse to a dict
    try:
        from core.utils.json_helpers import robust_json_parse
        parsed = robust_json_parse(tool_call_buffer_entry['function']['arguments'])
        # Must parse to a dict (not a string) to be considered complete
        return isinstance(parsed, dict)
    except (json.JSONDecodeError, TypeError):
        return False


def parse_native_tool_call_arguments(arguments: Any) -> Dict[str, Any]:
    """
    Parse native tool call arguments, handling both string and dict formats.
    
    Enhanced with robust error handling and partial JSON support.
    Based on qwen-agent patterns for reliable argument extraction.
    
    Args:
        arguments: Arguments as string (JSON) or dict
        
    Returns:
        Parsed arguments as dict, or original value if parsing fails
    """
    from core.utils.json_helpers import robust_json_parse
    
    if isinstance(arguments, dict):
        return arguments
    
    if isinstance(arguments, str):
        arguments = arguments.strip()
        if not arguments:
            return {}
        
        # Try robust parsing which handles trailing commas and code blocks
        parsed = robust_json_parse(arguments)
        if isinstance(parsed, dict):
            return parsed
            
        # If robust parse returned a string (failed to parse) or non-dict
        # Fallback to partial extraction
        try:
             # Handle common partial JSON patterns
            if arguments.startswith('{') and not arguments.endswith('}'):
                # Incomplete object, try to find complete chunks
                return extract_partial_json_object(arguments)
            elif arguments and not arguments.startswith('{'):
                # Try to find JSON object in the string
                start_idx = arguments.find('{')
                if start_idx >= 0:
                    json_part = arguments[start_idx:]
                    # Try robust parse on the substring
                    parsed_sub = robust_json_parse(json_part)
                    if isinstance(parsed_sub, dict):
                        return parsed_sub
                    return extract_partial_json_object(json_part)
        except Exception:
            pass
            
        return arguments
    
    return arguments


def extract_partial_json_object(json_str: str) -> Dict[str, Any]:
    """
    Extract a partial JSON object from an incomplete JSON string.
    
    Based on qwen-agent extract_fn patterns for handling incomplete tool calls.
    
    Args:
        json_str: Partial JSON string
        
    Returns:
        Partially parsed JSON object or empty dict
    """
    try:
        # Try to balance braces and create a valid JSON
        # Enhanced to be aware of strings to avoid false brace counting
        # Also handles square brackets []
        stack = []
        in_string = False
        escape = False
        
        for char in json_str:
            if in_string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char == '}' or char == ']':
                    if stack and stack[-1] == char:
                        stack.pop()
        
        if stack:
            # Add missing closing characters in reverse order
            json_str += ''.join(reversed(stack))
        
        # Remove trailing commas and fix common issues
        from core.utils.json_helpers import repair_json_string
        json_str = repair_json_string(json_str)
        
        # Try to parse the fixed JSON
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        # If still fails, return empty dict
        return {}


def extract_function_name_and_args(text: str) -> tuple[str, str]:
    """
    Extract function name and arguments from tool call text.
    
    Based on qwen-agent extract_fn function for robust field extraction.
    
    Args:
        text: Tool call text content
        
    Returns:
        Tuple of (function_name, arguments_string)
    """
    fn_name, fn_args = '', ''
    fn_name_s = '"name": "'
    fn_name_e = '", "'
    fn_args_s = '"arguments": '
    
    i = text.find(fn_name_s)
    k = text.find(fn_args_s)
    
    if i > 0:
        _text = text[i + len(fn_name_s):]
        j = _text.find(fn_name_e)
        if j > -1:
            fn_name = _text[:j]
    
    if k > 0:
        fn_args = text[k + len(fn_args_s):]
        fn_args = fn_args.strip()
        
        # Handle both quoted and unquoted arguments
        if len(fn_args) > 0:
            # Remove surrounding quotes if present
            if fn_args.startswith('"') and fn_args.endswith('"'):
                fn_args = fn_args[1:-1]
            elif fn_args.endswith('"'):
                fn_args = fn_args[:-1]
            elif fn_args.endswith('"}'):  # Handle malformed JSON ending
                fn_args = fn_args[:-2]
                if fn_args.startswith('"'):
                    fn_args = fn_args[1:]
            elif fn_args.endswith('""}}'):  # Handle specific malformed case
                fn_args = fn_args[:-4]
                if fn_args.startswith('"'):
                    fn_args = fn_args[1:]
        else:
            fn_args = ''
    
    return fn_name, fn_args


def convert_to_exec_tool_call(
    tool_call: Any,
    raw_arguments_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert a native tool call object to exec_tool_call format.
    
    Args:
        tool_call: Native tool call object (from LiteLLM response) or dict
        raw_arguments_str: Optional raw arguments string (if already extracted)
        
    Returns:
        Dictionary with 'function_name', 'arguments', 'id', 'raw_arguments', 'source'
    """
    # Extract function name and ID
    if isinstance(tool_call, dict):
        function_name = tool_call.get('function', {}).get('name') or tool_call.get('function_name', 'unknown')
        tool_call_id = tool_call.get('id') or str(uuid.uuid4())
        if raw_arguments_str is None:
            raw_arguments_str = tool_call.get('function', {}).get('arguments') or tool_call.get('raw_arguments', '')
    else:
        # LiteLLM object
        function_name = tool_call.function.name if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'name') else 'unknown'
        tool_call_id = tool_call.id if hasattr(tool_call, 'id') else str(uuid.uuid4())
        if raw_arguments_str is None:
            if hasattr(tool_call, 'function') and hasattr(tool_call.function, 'arguments'):
                args = tool_call.function.arguments
                raw_arguments_str = args if isinstance(args, str) else json.dumps(args)
            else:
                raw_arguments_str = ''
    
    # Parse arguments
    parsed_args = parse_native_tool_call_arguments(raw_arguments_str)
    
    return {
        "function_name": function_name,
        "arguments": parsed_args if isinstance(parsed_args, dict) else raw_arguments_str,
        "id": tool_call_id,
        "raw_arguments": raw_arguments_str if isinstance(raw_arguments_str, str) else json.dumps(raw_arguments_str),
        "source": "native"
    }


def convert_buffer_to_complete_tool_calls(tool_calls_buffer: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert buffered tool calls to complete native tool calls format.
    
    Args:
        tool_calls_buffer: Dictionary mapping index -> buffered tool call data
        
    Returns:
        List of complete tool calls in LiteLLM format
    """
    complete_tool_calls = []
    
    for idx, tc_buf in tool_calls_buffer.items():
        if tc_buf.get('id') and tc_buf.get('function', {}).get('name') and tc_buf.get('function', {}).get('arguments'):
            try:
                # Validate that arguments are valid JSON
                from core.utils.json_helpers import safe_json_parse
                safe_json_parse(tc_buf['function']['arguments'])
                # Keep arguments as JSON string for LiteLLM compatibility
                complete_tool_calls.append({
                    "id": tc_buf['id'],
                    "type": "function",
                    "function": {
                        "name": tc_buf['function']['name'],
                        "arguments": tc_buf['function']['arguments']
                    }
                })
            except (json.JSONDecodeError, TypeError):
                continue
    
    return complete_tool_calls


def convert_to_unified_tool_call_format(
    tool_call: Dict[str, Any],
    parse_arguments: bool = True
) -> Dict[str, Any]:
    """
    Convert a native tool call to unified format for metadata storage.
    
    Args:
        tool_call: Tool call dict with 'id' and 'function' keys (LiteLLM format)
        parse_arguments: Whether to parse arguments JSON string to dict
        
    Returns:
        Dictionary with 'tool_call_id', 'function_name', 'arguments', 'source'
    """
    function_name = tool_call.get('function', {}).get('name', 'unknown')
    tool_call_id = tool_call.get('id', str(uuid.uuid4()))
    raw_arguments = tool_call.get('function', {}).get('arguments', '')
    
    if parse_arguments:
        arguments = parse_native_tool_call_arguments(raw_arguments)
    else:
        arguments = raw_arguments
    
    return {
        "tool_call_id": tool_call_id,
        "function_name": function_name,
        "arguments": arguments if isinstance(arguments, dict) else raw_arguments,
        "source": "native"
    }


def convert_buffer_to_metadata_tool_calls(
    tool_calls_buffer: Dict[int, Dict[str, Any]], 
    include_partial: bool = False
) -> List[Dict[str, Any]]:
    """
    Convert buffered tool calls to unified metadata format for streaming chunks.
    
    Args:
        tool_calls_buffer: Dictionary mapping index -> buffered tool call data
        include_partial: Whether to include partial/incomplete tool calls (for streaming)
        
    Returns:
        List of tool calls in unified metadata format (tool_call_id, function_name, arguments, source)
    """
    unified_tool_calls = []
    for idx in sorted(tool_calls_buffer.keys()):
        tc_buf = tool_calls_buffer[idx]
        # Only include tool calls that have at least a name and some arguments (even if partial)
        if tc_buf.get('function', {}).get('name'):
            # Arguments might be incomplete JSON string from LLM
            arguments_str = tc_buf['function'].get('arguments', '')
            
            # Try to parse arguments as JSON - if successful, use parsed object
            # If it fails (partial/incomplete JSON), keep as string
            arguments: Any = arguments_str
            if arguments_str:
                try:
                    parsed = json.loads(arguments_str)
                    # Successfully parsed - use the object (avoids double-escaping)
                    arguments = parsed
                except json.JSONDecodeError:
                    # Partial/incomplete JSON - keep as string for frontend to handle
                    arguments = arguments_str
            
            unified_tool_calls.append({
                "tool_call_id": tc_buf.get('id', f"streaming_tool_{idx}_{str(uuid.uuid4())}"),
                "function_name": tc_buf['function']['name'],
                "arguments": arguments,  # Object if valid JSON, string if partial
                "source": "native"  # Always native for native tool calls
            })
    return unified_tool_calls


def format_tool_result(tool_call_id: str, result: Any, success: bool = True, error: Optional[str] = None) -> Dict[str, Any]:
    """
    Format a tool result in OpenAI tool role message format.
    
    Args:
        tool_call_id: The ID of the tool call this result corresponds to
        result: The result data from tool execution
        success: Whether the tool execution succeeded
        error: Error message if execution failed
        
    Returns:
        Dictionary in OpenAI tool role message format
    """
    if success:
        content = result if isinstance(result, str) else json.dumps(result)
    else:
        content = error or "Tool execution failed"
    
    return {
        "role": "tool",
        "content": content,
        "tool_call_id": tool_call_id
    }


def parse_tool_calls(response_content: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from response content using robust field extraction.
    
    Enhanced version that can handle various response formats and partial calls.
    
    Args:
        response_content: Response content that may contain tool calls
        
    Returns:
        List of parsed tool call dictionaries
    """
    tool_calls = []
    
    # Look for tool call patterns in the response
    # This handles both structured JSON and text responses
    lines = response_content.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to extract tool calls using the qwen-agent pattern
        if '{"name":' in line or '"function":' in line:
            try:
                # Try to parse as JSON first
                if line.startswith('{') and line.endswith('}'):
                    tool_call_data = json.loads(line)
                    if isinstance(tool_call_data, dict) and 'name' in tool_call_data:
                        tool_calls.append({
                            "id": str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": tool_call_data.get("name", ""),
                                "arguments": json.dumps(tool_call_data.get("arguments", {}))
                            }
                        })
                else:
                    # Use extract function for text-based tool calls
                    fn_name, fn_args = extract_function_name_and_args(line)
                    if fn_name:
                        tool_calls.append({
                            "id": str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": fn_args if fn_args else "{}"
                            }
                        })
            except (json.JSONDecodeError, ValueError):
                # Fallback to text extraction
                fn_name, fn_args = extract_function_name_and_args(line)
                if fn_name:
                    tool_calls.append({
                        "id": str(uuid.uuid4()),
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": fn_args if fn_args else "{}"
                        }
                    })
    
    return tool_calls

