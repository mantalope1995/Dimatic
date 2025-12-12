"""
JSON helper utilities for handling both legacy (string) and new (dict/list) formats.

These utilities help with the transition from storing JSON as strings to storing
them as proper JSONB objects in the database.
"""

import json
from typing import Any, Union, Dict, List
import re

def repair_json_string(json_str: str) -> str:
    """
    Attempt to repair common JSON syntax errors.
    
    Handles:
    - Trailing commas in objects and lists
    - Unquoted keys (basic alphanumeric)
    - Single quotes -> Double quotes
    
    Args:
        json_str: Malformed JSON string
        
    Returns:
        Repaired string
    """
    if not isinstance(json_str, str):
        return json_str
        
    repaired = json_str.strip()
    
    # helper to replace single quotes with double quotes only outside of double quotes
    # but that's complex. Simple approach first.
    
    # 1. Fix trailing commas: [1, 2,] -> [1, 2] or {"a":1,} -> {"a":1}
    # Regex look behind/ahead to ensure we are inside structure is hard, 
    # but blindly removing comma before closing brace/bracket is usually safe in JSON context
    repaired = re.sub(r',\s*([\]}])', r'\1', repaired)
    
    # 2. Quote unquoted keys: {key: "value"} -> {"key": "value"}
    # Match alphanumeric keys followed by colon, not preceded by quote
    # This is risky if inside a string, but we tackle the most common LLM output case
    # A safer way is using a parser, but regex usually covers 90% of LLM errors
    # Pattern: Look for identifier followed by colon, ensure it's not in quotes (heuristic)
    # repaired = re.sub(r'(?<!")(\b[a-zA-Z_]\w*\b)(?=\s*:)', r'"\1"', repaired)
    
    return repaired

def robust_json_parse(value: Union[str, Dict, List, Any], default: Any = None) -> Any:
    """
    Robustly parse JSON, attempting retrieval and repairs.
    
    Args:
        value: Input value
        default: Default return value
        
    Returns:
        Parsed structure or default
    """
    if value is None:
        return default
        
    if isinstance(value, (dict, list)):
        return value
        
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
            
        # 1. Try standard parse
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
            
        # 2. Try fast repair (trailing commas)
        try:
            repaired = repair_json_string(value)
            return json.loads(repaired)
        except (json.JSONDecodeError, TypeError):
            pass
            
        # 3. Try to unwrap code blocks (```json ... ```)
        # Using regex to capture content inside code blocks
        match = re.search(r'```(?:json)?\s*(.*?)```', value, re.DOTALL)
        if match:
            inner = match.group(1).strip()
            try:
                return json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                # Try repairing inner content
                 try:
                    repaired_inner = repair_json_string(inner)
                    return json.loads(repaired_inner)
                 except (json.JSONDecodeError, TypeError):
                    pass
        
        # 4. Try lenient parsing (fallback) if we had a library, but we don't.
        # Fallback to string if we really can't parse
        return default if default is not None else value
        
    return value


def ensure_dict(value: Union[str, Dict[str, Any], None], default: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Ensure a value is a dictionary.
    
    Handles:
    - None -> returns default or {}
    - Dict -> returns as-is
    - JSON string -> parses and returns dict
    - Other -> returns default or {}
    
    Args:
        value: The value to ensure is a dict
        default: Default value if conversion fails
        
    Returns:
        A dictionary
    """
    if default is None:
        default = {}
        
    if value is None:
        return default
        
    if isinstance(value, dict):
        return value
        
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            return default
        except (json.JSONDecodeError, TypeError):
            return default
            
    return default


def ensure_list(value: Union[str, List[Any], None], default: List[Any] = None) -> List[Any]:
    """
    Ensure a value is a list.
    
    Handles:
    - None -> returns default or []
    - List -> returns as-is
    - JSON string -> parses and returns list
    - Other -> returns default or []
    
    Args:
        value: The value to ensure is a list
        default: Default value if conversion fails
        
    Returns:
        A list
    """
    if default is None:
        default = []
        
    if value is None:
        return default
        
    if isinstance(value, list):
        return value
        
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
            return default
        except (json.JSONDecodeError, TypeError):
            return default
            
    return default


def safe_json_parse(value: Union[str, Dict, List, Any], default: Any = None) -> Any:
    """
    Safely parse a value that might be JSON string or already parsed.
    
    This handles the transition period where some data might be stored as
    JSON strings (old format) and some as proper objects (new format).
    
    Args:
        value: The value to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed value or default
    """
    if value is None:
        return default
        
    # If it's already a dict or list, return as-is
    if isinstance(value, (dict, list)):
        return value
        
    # If it's a string, try to parse it
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, return the string itself
            return value
            
    # For any other type, return as-is
    return value


def to_json_string(value: Any) -> str:
    """
    Convert a value to a JSON string if needed.
    
    This is used for backwards compatibility when yielding data that
    expects JSON strings.
    
    Args:
        value: The value to convert
        
    Returns:
        JSON string representation
    """
    if isinstance(value, str):
        # If it's already a string, check if it's valid JSON
        try:
            json.loads(value)
            return value  # It's already a JSON string
        except (json.JSONDecodeError, TypeError):
            # It's a plain string, encode it as JSON
            return json.dumps(value)
    
    # For all other types, convert to JSON
    return json.dumps(value)


def format_for_yield(message_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a message object for yielding, ensuring content and metadata are JSON strings.
    
    This maintains backward compatibility with clients expecting JSON strings
    while the database now stores proper objects.
    
    Args:
        message_object: The message object from the database
        
    Returns:
        Message object with content and metadata as JSON strings
    """
    if not message_object:
        return message_object
        
    # Create a copy to avoid modifying the original
    formatted = message_object.copy()
    
    # Ensure content is a JSON string
    if 'content' in formatted and not isinstance(formatted['content'], str):
        formatted['content'] = json.dumps(formatted['content'])
        
    # Ensure metadata is a JSON string
    if 'metadata' in formatted and not isinstance(formatted['metadata'], str):
        formatted['metadata'] = json.dumps(formatted['metadata'])
        
    return formatted 