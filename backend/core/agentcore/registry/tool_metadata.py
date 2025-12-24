"""
Tool Metadata Models

Defines data structures for tool metadata used in the AgentCore tool registry.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class ToolCategory(str, Enum):
    """Categories of tools in the registry"""

    BROWSER = "browser"
    CODE_INTERPRETER = "code_interpreter"
    MCP = "mcp"
    FILE_OPS = "file_ops"
    SEARCH = "search"
    MESSAGING = "messaging"
    DATABASE = "database"
    API = "api"
    UTILITY = "utility"
    OTHER = "other"


@dataclass
class ToolInputParameter:
    """Definition for a tool input parameter"""

    name: str
    type: str  # "string", "integer", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None
    format: Optional[str] = None  # For additional type constraints


@dataclass
class ToolOutputSchema:
    """Definition for tool output schema"""

    type: str = "object"
    description: str = ""
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)


@dataclass
class ToolMetadata:
    """
    Metadata for a registered tool in the AgentCore tool registry.

    Attributes:
        name: Unique tool identifier
        description: Human-readable description
        category: Tool category for grouping
        input_schema: JSON Schema for tool input
        output_schema: JSON Schema for tool output
        is_agentcore_native: Whether this is an AgentCore primitive tool
        deployment_id: AgentCore deployment ID for native tools
        module_path: Python module path for local tools
        class_name: Python class name for local tools
        version: Tool version string
        author: Tool author/creator
        tags: List of searchable tags
        created_at: Timestamp when tool was registered
        updated_at: Timestamp when tool was last updated
        enabled: Whether tool is enabled for execution
        execution_timeout_seconds: Default timeout for tool execution
        requires_runtime: Whether tool requires AgentCore Runtime
        parameters: List of input parameter definitions
    """

    name: str
    description: str
    category: ToolCategory
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    is_agentcore_native: bool = False
    deployment_id: Optional[str] = None
    module_path: Optional[str] = None
    class_name: Optional[str] = None
    version: str = "1.0.0"
    author: str = "kortix"
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    enabled: bool = True
    execution_timeout_seconds: int = 30
    requires_runtime: bool = False
    parameters: List[ToolInputParameter] = field(default_factory=list)

    def __post_init__(self):
        """Validate and normalize tool metadata"""
        # Ensure category is a ToolCategory enum
        if isinstance(self.category, str):
            self.category = ToolCategory(self.category)

        # Auto-extract parameters from input_schema if not provided
        if not self.parameters and self.input_schema:
            self.parameters = self._extract_parameters_from_schema()

        # Normalize tags to lowercase
        self.tags = [tag.lower() for tag in self.tags]

        # Add default tags based on category
        category_tag = self.category.value
        if category_tag not in self.tags:
            self.tags.append(category_tag)

    def _extract_parameters_from_schema(self) -> List["ToolInputParameter"]:
        """Extract parameters from input_schema"""
        from .tool_metadata import ToolInputParameter

        parameters = []
        properties = self.input_schema.get("properties", {})
        required = set(self.input_schema.get("required", []))

        for param_name, param_def in properties.items():
            param = ToolInputParameter(
                name=param_name,
                type=param_def.get("type", "string"),
                description=param_def.get("description", ""),
                required=param_name in required,
                default=param_def.get("default"),
                enum=param_def.get("enum"),
                format=param_def.get("format"),
            )
            parameters.append(param)

        return parameters

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary representation"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "is_agentcore_native": self.is_agentcore_native,
            "deployment_id": self.deployment_id,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "enabled": self.enabled,
            "execution_timeout_seconds": self.execution_timeout_seconds,
            "requires_runtime": self.requires_runtime,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                    "format": p.format,
                }
                for p in self.parameters
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetadata":
        """Create ToolMetadata from dictionary representation"""
        # Handle datetime parsing
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = data.get("updated_at")
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        # Handle parameters
        parameters = [
            ToolInputParameter(**p) for p in data.get("parameters", [])
        ]

        return cls(
            name=data["name"],
            description=data["description"],
            category=ToolCategory(data["category"]),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            is_agentcore_native=data.get("is_agentcore_native", False),
            deployment_id=data.get("deployment_id"),
            module_path=data.get("module_path"),
            class_name=data.get("class_name"),
            version=data.get("version", "1.0.0"),
            author=data.get("author", "kortix"),
            tags=data.get("tags", []),
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at or datetime.utcnow(),
            enabled=data.get("enabled", True),
            execution_timeout_seconds=data.get("execution_timeout_seconds", 30),
            requires_runtime=data.get("requires_runtime", False),
            parameters=parameters,
        )

    def matches_query(self, query: str) -> bool:
        """
        Check if tool matches a search query.

        Args:
            query: Search query string

        Returns:
            True if tool matches the query
        """
        query_lower = query.lower()

        # Search in name, description, tags
        if query_lower in self.name.lower():
            return True
        if query_lower in self.description.lower():
            return True
        if any(query_lower in tag for tag in self.tags):
            return True

        # Search in category
        if query_lower in self.category.value:
            return True

        return False

    def get_parameter(self, name: str) -> Optional[ToolInputParameter]:
        """Get a parameter definition by name"""
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def validate_input(self, input_data: Dict[str, Any]) -> List[str]:
        """
        Validate input data against tool schema.

        Args:
            input_data: Input data to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check required parameters
        required_params = {p.name for p in self.parameters if p.required}
        provided_params = set(input_data.keys())

        missing_params = required_params - provided_params
        for param in missing_params:
            errors.append(f"Missing required parameter: {param}")

        # Check parameter types
        for param in self.parameters:
            if param.name in input_data:
                value = input_data[param.name]
                type_errors = self._validate_parameter_type(param, value)
                errors.extend(type_errors)

        return errors

    def _validate_parameter_type(
        self, param: ToolInputParameter, value: Any
    ) -> List[str]:
        """Validate a single parameter value against its type definition"""
        errors = []

        # Null handling for non-optional parameters
        if value is None:
            if param.required:
                errors.append(f"Parameter '{param.name}' is required but got None")
            return errors

        # Type validation
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected_type = type_map.get(param.type)
        if expected_type and not isinstance(value, expected_type):
            errors.append(
                f"Parameter '{param.name}' expected type {param.type}, "
                f"got {type(value).__name__}"
            )

        # Enum validation
        if param.enum and value not in param.enum:
            errors.append(
                f"Parameter '{param.name}' must be one of {param.enum}, got {value}"
            )

        return errors

    def get_runtime_config(self) -> Dict[str, Any]:
        """
        Get the configuration needed to register this tool with AgentCore Runtime.

        Returns:
            Dictionary with Runtime tool configuration
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "timeoutInSeconds": self.execution_timeout_seconds,
        }
