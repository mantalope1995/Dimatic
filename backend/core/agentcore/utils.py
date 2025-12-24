"""
AgentCore Utility Functions

Provides utility functions for AWS Bedrock AgentCore integration,
including variable substitution for prompts and templates.
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Pattern for %variable_name% placeholders
VARIABLE_PATTERN = re.compile(r'%(\w+)%')


def substitute_variables(
    template: str,
    variables: Dict[str, Any],
    *,
    preserve_placeholders: bool = True,
    strict: bool = False
) -> str:
    """
    Substitute variables in a template string.

    This function replaces %variable_name% patterns in the template with
    corresponding values from the variables dictionary.

    Args:
        template: The template string containing %variable_name% placeholders
        variables: Dictionary mapping variable names to their values
        preserve_placeholders: If True, keeps unmatched placeholders in the result
        strict: If True, raises ValueError for unmatched placeholders

    Returns:
        The template with variables substituted

    Raises:
        ValueError: If strict=True and an unmatched placeholder is found

    Examples:
        >>> substitute_variables("Hello %name%", {"name": "World"})
        'Hello World'

        >>> substitute_variables("%greeting% %name%", {"greeting": "Hello", "name": "World"})
        'Hello World'

        >>> substitute_variables("%greeting% %unknown%", {"greeting": "Hello"})
        '%greeting% %unknown%'  # preserve_placeholders=True

        >>> substitute_variables("%greeting% %name%", {"greeting": "Hello"}, strict=True)
        ValueError: Unmatched placeholder: %name%
    """
    def replacer(match: re.Match) -> str:
        """Callback function for re.sub to replace variables"""
        var_name = match.group(1)
        if var_name in variables:
            value = variables[var_name]
            # Convert value to string
            return str(value)
        # Preserve placeholder if not found
        return match.group(0)

    # First pass: find all placeholders and check for unmatched ones
    placeholders = set(VARIABLE_PATTERN.findall(template))
    unmatched = placeholders - set(variables.keys())

    if strict and unmatched:
        raise ValueError(f"Unmatched placeholder(s): {', '.join(f'%{p}%' for p in unmatched)}")

    # Perform substitution
    result = VARIABLE_PATTERN.sub(replacer, template)

    # Log unmatched placeholders if any (for debugging)
    if unmatched and preserve_placeholders:
        logger.debug(f"Preserved {len(unmatched)} unmatched placeholders: {unmatched}")

    return result


def extract_variables(template: str) -> List[str]:
    """
    Extract all variable names from a template string.

    Args:
        template: The template string containing %variable_name% placeholders

    Returns:
        List of variable names found in the template (unique, in order of appearance)

    Examples:
        >>> extract_variables("Hello %name%, welcome to %app%")
        ['name', 'app']

        >>> extract_variables("No variables here")
        []
    """
    return list(dict.fromkeys(VARIABLE_PATTERN.findall(template)))


def validate_template(template: str, variables: Dict[str, Any]) -> bool:
    """
    Validate that all placeholders in the template have corresponding variables.

    Args:
        template: The template string containing %variable_name% placeholders
        variables: Dictionary mapping variable names to their values

    Returns:
        True if all placeholders have corresponding variables, False otherwise

    Examples:
        >>> validate_template("Hello %name%", {"name": "World"})
        True

        >>> validate_template("Hello %name%", {})
        False
    """
    required = set(extract_variables(template))
    available = set(variables.keys())
    return required.issubset(available)


def substitute_in_dict(
    data: Dict[str, Any],
    variables: Dict[str, Any],
    *,
    keys: Optional[List[str]] = None,
    preserve_placeholders: bool = True
) -> Dict[str, Any]:
    """
    Substitute variables in string values within a dictionary.

    This function scans string values in the dictionary and performs
    variable substitution on any strings that contain placeholders.

    Args:
        data: The dictionary containing values to substitute
        variables: Dictionary mapping variable names to their values
        keys: Optional list of specific keys to process (processes all if None)
        preserve_placeholders: If True, keeps unmatched placeholders in results

    Returns:
        A new dictionary with substituted values

    Examples:
        >>> substitute_in_dict(
        ...     {"greeting": "Hello %name%", "count": 42},
        ...     {"name": "World"}
        ... )
        {'greeting': 'Hello World', 'count': 42}
    """
    result = {}

    for key, value in data.items():
        # Skip if keys are specified and this key isn't in the list
        if keys is not None and key not in keys:
            result[key] = value
            continue

        # Perform substitution on string values
        if isinstance(value, str):
            result[key] = substitute_variables(
                value,
                variables,
                preserve_placeholders=preserve_placeholders
            )
        else:
            result[key] = value

    return result
