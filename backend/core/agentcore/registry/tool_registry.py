"""
AgentCore Tool Registry

Centralized registry for discovering, managing, and integrating tools
with AgentCore Runtime.
"""

import asyncio
import importlib
import inspect
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from ..config import AgentCoreConfig, get_config
from ..adapters.runtime import AgentCoreRuntimeAdapter
from ..errors import (
    AgentCoreError,
    ValidationError,
    with_retry,
    safe_log,
)
from .tool_metadata import ToolMetadata, ToolCategory

logger = logging.getLogger(__name__)

# Global registry instance
_registry: Optional["ToolRegistry"] = None


class ToolRegistry:
    """
    Centralized tool registry for AgentCore integration.

    Provides:
    - Tool discovery from Python packages
    - Tool metadata management
    - Runtime registration and lifecycle
    - Tool search and filtering
    """

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize the tool registry.

        Args:
            config: AgentCore configuration. If None, uses global config.
        """
        self.config = config or get_config()
        self._tools: Dict[str, ToolMetadata] = {}
        self._runtime_adapter: Optional[AgentCoreRuntimeAdapter] = None
        self._deployment_tools: Dict[str, Set[str]] = {}  # deployment_id -> tool names
        self._discovery_packages: List[str] = []
        self._initialized = False

        # Initialize Runtime adapter if enabled
        if self.config.runtime_enabled:
            try:
                self._runtime_adapter = AgentCoreRuntimeAdapter(self.config)
                safe_log("ToolRegistry initialized with Runtime adapter")
            except Exception as e:
                logger.warning(f"Failed to initialize Runtime adapter: {e}")

    async def initialize(self) -> None:
        """Initialize the registry and discover tools"""
        if self._initialized:
            return

        safe_log("Initializing ToolRegistry")

        # Auto-discover tools from configured packages
        if self.config.runtime_enabled:
            discovery_package = getattr(
                self.config, "tool_registry_package", "core.tools"
            )
            if discovery_package:
                await self.discover_tools(discovery_package)

        self._initialized = True
        safe_log(f"ToolRegistry initialized with {len(self._tools)} tools")

    async def discover_tools(
        self,
        tool_package: str = "core.tools",
        recursive: bool = True,
    ) -> List[ToolMetadata]:
        """
        Discover all tools in the given package.

        Scans the package for classes that inherit from Tool base class
        and registers them automatically.

        Args:
            tool_package: Python package path (e.g., "core.tools")
            recursive: Whether to scan subpackages

        Returns:
            List of discovered tool metadata
        """
        safe_log(f"Discovering tools in package: {tool_package}")

        discovered = []
        try:
            # Import the package
            module = importlib.import_module(tool_package)
            package_path = Path(module.__file__).parent

            # Find all Python files
            python_files = []
            if recursive:
                python_files.extend(package_path.rglob("*.py"))
            else:
                python_files.extend(package_path.glob("*.py"))

            for py_file in python_files:
                # Skip __init__ and special files
                if py_file.name.startswith("_"):
                    continue

                # Calculate module path
                rel_path = py_file.relative_to(package_path.parent)
                module_path = ".".join(
                    rel_path.with_suffix("").parts
                )

                try:
                    # Import the module and find Tool classes
                    tool_module = importlib.import_module(module_path)
                    tools = await self._extract_tools_from_module(tool_module)
                    discovered.extend(tools)

                except ImportError as e:
                    logger.debug(f"Could not import {module_path}: {e}")
                except Exception as e:
                    logger.warning(f"Error scanning {module_path}: {e}")

            # Track discovery package
            if tool_package not in self._discovery_packages:
                self._discovery_packages.append(tool_package)

            safe_log(f"Discovered {len(discovered)} tools from {tool_package}")

        except ImportError as e:
            raise ValidationError(f"Could not import tool package {tool_package}: {e}")

        return discovered

    async def _extract_tools_from_module(
        self, module: Any
    ) -> List[ToolMetadata]:
        """
        Extract tool classes from a module.

        Looks for classes that inherit from Tool base class or have
        a tool registration decorator.

        Args:
            module: Python module to scan

        Returns:
            List of tool metadata found in the module
        """
        discovered = []

        # Get all classes from the module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Skip imported classes (not defined in this module)
            if obj.__module__ != module.__name__:
                continue

            # Check if it's a Tool subclass
            from core.sandbox.tool_base import Tool

            if issubclass(obj, Tool) and obj is not Tool:
                # Skip abstract base classes
                if getattr(obj, "__abstract__", False):
                    continue

                # Extract metadata from the Tool class
                metadata = await self._extract_tool_metadata(obj)
                if metadata:
                    discovered.append(metadata)
                    # Auto-register the tool
                    await self.register_tool(metadata)

        return discovered

    async def _extract_tool_metadata(self, tool_class: type) -> Optional[ToolMetadata]:
        """
        Extract metadata from a Tool class.

        Args:
            tool_class: Tool class to extract metadata from

        Returns:
            ToolMetadata or None if extraction failed
        """
        try:
            # Get basic attributes from the class
            name = getattr(tool_class, "name", tool_class.__name__)
            description = getattr(tool_class, "description", "")
            category_str = getattr(tool_class, "_category", "other")

            # Get input/output schemas
            input_schema = getattr(tool_class, "input_schema", {})
            output_schema = getattr(tool_class, "output_schema", {})

            # Get parameters from schema or class
            parameters = self._extract_parameters(tool_class, input_schema)

            # Determine category
            try:
                category = ToolCategory(category_str)
            except ValueError:
                category = ToolCategory.OTHER

            # Create metadata
            metadata = ToolMetadata(
                name=name,
                description=description,
                category=category,
                input_schema=input_schema,
                output_schema=output_schema,
                module_path=f"{tool_class.__module__}.{tool_class.__name__}",
                class_name=tool_class.__name__,
                parameters=parameters,
                enabled=True,
            )

            return metadata

        except Exception as e:
            logger.warning(f"Failed to extract metadata from {tool_class.__name__}: {e}")
            return None

    def _extract_parameters(
        self, tool_class: type, input_schema: Dict[str, Any]
    ) -> List:
        """Extract parameter definitions from tool class and schema"""
        from .tool_metadata import ToolInputParameter

        parameters = []

        # Extract from schema properties
        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))

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

    async def register_tool(
        self,
        metadata: ToolMetadata,
        deployment_id: Optional[str] = None,
    ) -> bool:
        """
        Register a tool with the registry.

        Args:
            metadata: Tool metadata to register
            deployment_id: Optional Runtime deployment to register with

        Returns:
            True if registration was successful

        Raises:
            ValidationError: If tool metadata is invalid
        """
        # Validate metadata
        if not metadata.name:
            raise ValidationError("Tool name is required")

        # Check for existing tool
        if metadata.name in self._tools:
            logger.warning(f"Tool '{metadata.name}' already registered, updating")

        # Store metadata
        self._tools[metadata.name] = metadata

        # Register with Runtime if adapter available
        if self._runtime_adapter and deployment_id:
            await self._register_with_runtime(metadata, deployment_id)

        safe_log(f"Registered tool: {metadata.name} (category: {metadata.category.value})")
        return True

    async def _register_with_runtime(
        self, metadata: ToolMetadata, deployment_id: str
    ) -> None:
        """Register a tool with AgentCore Runtime deployment"""
        try:
            # Track which deployment has this tool
            if deployment_id not in self._deployment_tools:
                self._deployment_tools[deployment_id] = set()
            self._deployment_tools[deployment_id].add(metadata.name)

            # For Phase 1, Runtime integration is simulated
            # When real SDK is available, call Runtime adapter here
            safe_log(
                f"Tool '{metadata.name}' registered with Runtime deployment {deployment_id}"
            )

        except Exception as e:
            logger.warning(f"Failed to register '{metadata.name}' with Runtime: {e}")

    async def unregister_tool(self, name: str) -> bool:
        """
        Unregister a tool from the registry.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was unregistered
        """
        if name not in self._tools:
            logger.warning(f"Tool '{name}' not found in registry")
            return False

        # Remove from all deployments
        for deployment_id, tool_names in self._deployment_tools.items():
            if name in tool_names:
                tool_names.remove(name)

        # Remove from registry
        del self._tools[name]

        safe_log(f"Unregistered tool: {name}")
        return True

    async def get_tool(self, name: str) -> Optional[ToolMetadata]:
        """
        Get tool metadata by name.

        Args:
            name: Tool name

        Returns:
            ToolMetadata or None if not found
        """
        return self._tools.get(name)

    async def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        enabled_only: bool = True,
        deployment_id: Optional[str] = None,
    ) -> List[ToolMetadata]:
        """
        List all tools in the registry.

        Args:
            category: Optional category filter
            enabled_only: Only return enabled tools
            deployment_id: Optional deployment filter

        Returns:
            List of tool metadata
        """
        tools = list(self._tools.values())

        # Filter by category
        if category:
            tools = [t for t in tools if t.category == category]

        # Filter by enabled status
        if enabled_only:
            tools = [t for t in tools if t.enabled]

        # Filter by deployment
        if deployment_id:
            deployment_tool_names = self._deployment_tools.get(deployment_id, set())
            tools = [t for t in tools if t.name in deployment_tool_names]

        return tools

    async def search_tools(self, query: str) -> List[ToolMetadata]:
        """
        Search for tools by name, description, or tags.

        Args:
            query: Search query string

        Returns:
            List of matching tool metadata
        """
        results = []
        for tool in self._tools.values():
            if tool.matches_query(query):
                results.append(tool)

        return results

    async def get_tools_by_deployment(self, deployment_id: str) -> List[ToolMetadata]:
        """
        Get all tools registered with a specific deployment.

        Args:
            deployment_id: Runtime deployment ID

        Returns:
            List of tool metadata for the deployment
        """
        tool_names = self._deployment_tools.get(deployment_id, set())
        return [
            self._tools[name] for name in tool_names if name in self._tools
        ]

    async def register_deployment_tools(
        self, deployment_id: str, tool_names: List[str]
    ) -> bool:
        """
        Register a set of tools with a Runtime deployment.

        Args:
            deployment_id: Runtime deployment ID
            tool_names: List of tool names to register

        Returns:
            True if registration was successful
        """
        self._deployment_tools[deployment_id] = set(tool_names)

        for tool_name in tool_names:
            tool = self._tools.get(tool_name)
            if tool:
                await self._register_with_runtime(tool, deployment_id)

        safe_log(
            f"Registered {len(tool_names)} tools with deployment {deployment_id}"
        )
        return True

    async def validate_tool_input(
        self, tool_name: str, input_data: Dict[str, Any]
    ) -> List[str]:
        """
        Validate input data for a tool.

        Args:
            tool_name: Name of the tool
            input_data: Input data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        tool = await self.get_tool(tool_name)
        if not tool:
            return [f"Tool '{tool_name}' not found"]

        return tool.validate_input(input_data)

    async def get_tool_count(self) -> int:
        """Get the total number of registered tools"""
        return len(self._tools)

    async def get_categories(self) -> List[ToolCategory]:
        """Get list of all categories with registered tools"""
        categories = set()
        for tool in self._tools.values():
            categories.add(tool.category)
        return sorted(list(categories), key=lambda c: c.value)

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry stats
        """
        category_counts: Dict[str, int] = {}
        for tool in self._tools.values():
            cat = tool.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_tools": len(self._tools),
            "total_deployments": len(self._deployment_tools),
            "categories": category_counts,
            "enabled_tools": sum(1 for t in self._tools.values() if t.enabled),
            "native_tools": sum(1 for t in self._tools.values() if t.is_agentcore_native),
            "discovery_packages": self._discovery_packages,
        }


def get_tool_registry(config: Optional[AgentCoreConfig] = None) -> ToolRegistry:
    """
    Get the global tool registry instance.

    Args:
        config: Optional configuration for the registry

    Returns:
        ToolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry(config)
    return _registry


def reset_tool_registry() -> None:
    """Reset the global tool registry instance (useful for testing)"""
    global _registry
    _registry = None
