"""
Agent Packager for AWS Bedrock AgentCore Runtime

Handles conversion of Kortix agent configurations to AgentCore Runtime deployment format.
Packages agent instructions, tools, and primitives for serverless deployment.

IMPORTANT: All deployments target ap-southeast-2 region for Phase 1 compliance.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from ..config import AgentCoreConfig, get_config
from ..models import RuntimeDeployment
from ..errors import (
    AgentCoreError,
    ValidationError,
    safe_log,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentCorePackage:
    """
    Represents a packaged agent ready for AgentCore Runtime deployment.

    Attributes:
        agent_id: Unique identifier for the agent
        version_id: Version identifier
        instructions: Agent system prompt/instructions
        tools: List of tools available to the agent
        primitives: Configuration for AgentCore primitives (code_interpreter, browser, etc.)
        model_config: LLM model configuration
        runtime_config: Runtime execution configuration
        metadata: Additional deployment metadata
    """
    agent_id: str
    version_id: str
    instructions: str
    tools: List[Dict[str, Any]] = field(default_factory=list)
    primitives: Dict[str, Any] = field(default_factory=dict)
    model_config: Dict[str, Any] = field(default_factory=dict)
    runtime_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_deployment_config(self) -> Dict[str, Any]:
        """Convert to AgentCore Runtime deployment configuration format"""
        return {
            "agentId": self.agent_id,
            "version": self.version_id,
            "instructions": self.instructions,
            "tools": self.tools,
            "primitives": self.primitives,
            "model": self.model_config,
            "runtime": self.runtime_config,
            "metadata": {
                **self.metadata,
                "packagedAt": datetime.utcnow().isoformat(),
                "region": self.runtime_config.get("region", "ap-southeast-2"),
            }
        }

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_deployment_config(), indent=2)


@dataclass
class ToolDefinition:
    """
    Represents a tool definition for AgentCore Runtime.

    Attributes:
        name: Tool name
        description: Tool description
        input_schema: JSON schema for tool inputs
        type: Tool type (mcp, builtin, custom)
        config: Tool-specific configuration
    """
    name: str
    description: str
    input_schema: Dict[str, Any]
    type: str = "custom"
    config: Dict[str, Any] = field(default_factory=dict)


class AgentPackager:
    """
    Packages Kortix agents for deployment to AWS AgentCore Runtime.

    This class handles:
    - Converting Kortix agent configuration to AgentCore format
    - Extracting and transforming tool definitions
    - Configuring AgentCore primitives (code_interpreter, browser, memory)
    - Validating deployment readiness

    The packager follows these principles:
    - Region enforcement: ap-southeast-2 for Phase 1
    - Tool compatibility: Maps Kortix tools to AgentCore equivalents
    - Primitive configuration: Enables required AgentCore primitives
    """

    # Mapping of Kortix tool types to AgentCore tool types
    TOOL_TYPE_MAPPING = {
        "file_write": "builtin",
        "file_read": "builtin",
        "browser": "browser",
        "code_interpreter": "code_interpreter",
        "mcp": "mcp",
        "web_search": "builtin",
        "mcp_tool": "mcp",
    }

    # Required AgentCore primitives for different tool categories
    PRIMITIVE_REQUIREMENTS = {
        "browser": ["browser"],
        "code_interpreter": ["code_interpreter"],
        "memory": ["memory"],
        "gateway": ["gateway"],
    }

    def __init__(self, config: Optional[AgentCoreConfig] = None):
        """
        Initialize the agent packager.

        Args:
            config: AgentCore configuration. If None, uses global config.

        Raises:
            ConfigurationError: If packager configuration is invalid.
        """
        self.config = config or get_config()

        # Validate that Runtime is enabled
        if not self.config.runtime_enabled:
            raise ValidationError(
                "AgentCore Runtime is not enabled. "
                "Set AGENTCORE_RUNTIME_ENABLED=true to use agent packaging."
            )

        safe_log("Initialized AgentPackager for ap-southeast-2 region")

    def package_agent_version(
        self,
        agent_id: str,
        version_id: str,
        system_prompt: str,
        model: Optional[str] = None,
        configured_mcps: Optional[List[Dict[str, Any]]] = None,
        custom_mcps: Optional[List[Dict[str, Any]]] = None,
        agentpress_tools: Optional[Dict[str, Any]] = None,
        triggers: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentCorePackage:
        """
        Package an agent version for AgentCore Runtime deployment.

        Converts Kortix agent configuration to AgentCore deployment format,
        including tools, primitives, and runtime configuration.

        Args:
            agent_id: Agent identifier
            version_id: Version identifier
            system_prompt: Agent system prompt/instructions
            model: LLM model identifier (optional)
            configured_mcps: Configured MCP integrations
            custom_mcps: Custom MCP integrations
            agentpress_tools: AgentPress tool configuration
            triggers: Agent triggers (if any)
            metadata: Additional metadata

        Returns:
            AgentCorePackage ready for deployment

        Raises:
            ValidationError: If agent configuration is invalid
        """
        safe_log(f"Packaging agent {agent_id} version {version_id} for AgentCore Runtime")

        # Validate required fields
        if not agent_id or not version_id:
            raise ValidationError("agent_id and version_id are required")

        if not system_prompt:
            raise ValidationError("system_prompt is required for agent packaging")

        # Normalize inputs
        configured_mcps = configured_mcps or []
        custom_mcps = custom_mcps or []
        agentpress_tools = agentpress_tools or {}
        triggers = triggers or []
        metadata = metadata or {}

        # Extract tools from agentpress_tools
        tools = self._extract_tools(agentpress_tools, configured_mcps, custom_mcps)

        # Configure primitives based on tool requirements
        primitives = self._configure_primitives(tools)

        # Build model configuration
        model_config = self._build_model_config(model)

        # Build runtime configuration
        runtime_config = self._build_runtime_config()

        # Create package
        package = AgentCorePackage(
            agent_id=agent_id,
            version_id=version_id,
            instructions=system_prompt,
            tools=tools,
            primitives=primitives,
            model_config=model_config,
            runtime_config=runtime_config,
            metadata={
                **metadata,
                "packaged_at": datetime.utcnow().isoformat(),
                "triggers_count": len(triggers),
            }
        )

        safe_log(f"Successfully packaged agent {agent_id} with {len(tools)} tools")
        return package

    def _extract_tools(
        self,
        agentpress_tools: Dict[str, Any],
        configured_mcps: List[Dict[str, Any]],
        custom_mcps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract and transform tool definitions for AgentCore Runtime.

        Converts Kortix tool definitions to AgentCore compatible format,
        including MCP tools, builtin tools, and primitive tools.

        Args:
            agentpress_tools: AgentPress tool configuration
            configured_mcps: Configured MCP integrations
            custom_mcps: Custom MCP integrations

        Returns:
            List of tool definitions in AgentCore format
        """
        tools = []

        # Process AgentPress tools
        for tool_name, tool_config in agentpress_tools.items():
            tool_def = self._convert_agentpress_tool(tool_name, tool_config)
            if tool_def:
                tools.append(tool_def)

        # Process configured MCPs
        for mcp_config in configured_mcps:
            mcp_tools = self._extract_mcp_tools(mcp_config)
            tools.extend(mcp_tools)

        # Process custom MCPs
        for mcp_config in custom_mcps:
            mcp_tools = self._extract_mcp_tools(mcp_config)
            tools.extend(mcp_tools)

        safe_log(f"Extracted {len(tools)} tools for AgentCore Runtime")
        return tools

    def _convert_agentpress_tool(
        self,
        tool_name: str,
        tool_config: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Convert an AgentPress tool to AgentCore format.

        Args:
            tool_name: Tool name
            tool_config: Tool configuration from AgentPress

        Returns:
            Tool definition in AgentCore format, or None if not applicable
        """
        # Determine tool type from tool name or config
        tool_type = self._determine_tool_type(tool_name, tool_config)

        if tool_type == "builtin":
            return {
                "name": tool_name,
                "type": "builtin",
                "description": tool_config.get("description", f"{tool_name} tool"),
                "config": tool_config,
            }
        elif tool_type in ["browser", "code_interpreter"]:
            # These are primitive tools, not standalone
            return None
        elif tool_type == "mcp":
            # MCP tools are handled separately
            return None
        else:
            # Custom tool - convert schema
            return {
                "name": tool_name,
                "type": "custom",
                "description": tool_config.get("description", f"{tool_name} custom tool"),
                "inputSchema": self._extract_input_schema(tool_config),
                "config": tool_config,
            }

    def _determine_tool_type(self, tool_name: str, tool_config: Any) -> str:
        """Determine the AgentCore tool type for a Kortix tool"""
        # Check explicit type in config
        if isinstance(tool_config, dict):
            explicit_type = tool_config.get("agentcore_type")
            if explicit_type:
                return explicit_type

        # Infer from tool name
        if tool_name.startswith("file_"):
            return "builtin"
        elif tool_name in ["browser", "web_search"]:
            return "builtin"
        elif tool_name == "code_interpreter":
            return "code_interpreter"
        else:
            return "custom"

    def _extract_input_schema(self, tool_config: Any) -> Dict[str, Any]:
        """Extract JSON schema from tool configuration"""
        if isinstance(tool_config, dict):
            schema = tool_config.get("input_schema") or tool_config.get("schema")
            if schema:
                return schema

        # Default schema if none provided
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def _extract_mcp_tools(self, mcp_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract tool definitions from MCP configuration.

        Args:
            mcp_config: MCP configuration

        Returns:
            List of MCP tool definitions
        """
        tools = []
        mcp_type = mcp_config.get("type", "sse")

        # Get tools from MCP configuration
        mcp_tools = mcp_config.get("tools", [])
        if isinstance(mcp_tools, list):
            for tool in mcp_tools:
                tools.append({
                    "name": tool.get("name", ""),
                    "type": "mcp",
                    "description": tool.get("description", ""),
                    "mcpType": mcp_type,
                    "mcpConfig": {
                        "name": mcp_config.get("name", ""),
                        "type": mcp_type,
                        **mcp_config.get("config", {})
                    },
                    "inputSchema": tool.get("input_schema") or tool.get("schema") or {},
                })

        return tools

    def _configure_primitives(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Configure AgentCore primitives based on tool requirements.

        Determines which primitives (code_interpreter, browser, memory, gateway)
        are required based on the tool list and returns their configuration.

        Args:
            tools: List of tool definitions

        Returns:
            Dictionary of primitive configurations
        """
        primitives = {}

        # Check which primitives are needed based on tool types
        tool_types = {tool.get("type", "") for tool in tools}

        # Code Interpreter
        if any(t in ["code_interpreter", "builtin"] for t in tool_types):
            primitives["code_interpreter"] = {
                "enabled": True,
                "timeout_seconds": self.config.code_interpreter_timeout_seconds,
                "memory_limit_mb": self.config.code_interpreter_memory_limit_mb,
            }

        # Browser
        if any(t == "browser" for t in tool_types):
            primitives["browser"] = {
                "enabled": True,
                "timeout_seconds": self.config.browser_timeout_seconds,
                "headless": self.config.browser_headless,
                "viewport_width": 1920,
                "viewport_height": 1080,
            }

        # Memory - always enabled for Runtime agents
        if self.config.memory_enabled:
            primitives["memory"] = {
                "enabled": True,
                "retention_days": self.config.memory_retention_days,
                "max_messages": self.config.memory_max_messages,
            }

        # Gateway - enabled if MCP tools present
        if any(t == "mcp" for t in tool_types):
            primitives["gateway"] = {
                "enabled": True,
                "timeout_seconds": self.config.gateway_timeout_seconds,
                "rate_limit_per_minute": self.config.gateway_rate_limit_per_minute,
            }

        safe_log(f"Configured {len(primitives)} primitives: {list(primitives.keys())}")
        return primitives

    def _build_model_config(self, model: Optional[str]) -> Dict[str, Any]:
        """Build LLM model configuration for AgentCore Runtime"""
        # Default model if not specified
        if not model:
            model = "anthropic.claude-sonnet-4-20250514"

        # Parse model identifier
        model_parts = model.split(".")
        provider = model_parts[0] if model_parts else "anthropic"
        model_name = model_parts[-1] if len(model_parts) > 1 else model

        return {
            "provider": provider,
            "model": model,
            "modelName": model_name,
            "region": self.config.aws_region,
        }

    def _build_runtime_config(self) -> Dict[str, Any]:
        """Build runtime execution configuration"""
        return {
            "region": self.config.aws_region,  # ap-southeast-2 for Phase 1
            "timeout_seconds": self.config.runtime_timeout_seconds,
            "memory_limit_mb": self.config.runtime_memory_limit_mb,
            "streaming": True,  # Runtime always uses streaming
            "enableTracing": False,  # Can be enabled per-request
        }

    def validate_package(self, package: AgentCorePackage) -> List[str]:
        """
        Validate a packaged agent for deployment readiness.

        Checks that all required fields are present and valid.

        Args:
            package: The agent package to validate

        Returns:
            List of validation errors (empty if valid)

        Raises:
            ValidationError: If critical validation fails
        """
        errors = []

        # Check required fields
        if not package.agent_id:
            errors.append("agent_id is required")

        if not package.version_id:
            errors.append("version_id is required")

        if not package.instructions:
            errors.append("instructions (system_prompt) is required")

        # Check model config
        if not package.model_config.get("model"):
            errors.append("model_config.model is required")

        # Check runtime config
        if package.runtime_config.get("region") != "ap-southeast-2":
            errors.append(f"runtime_config.region must be ap-southeast-2, got {package.runtime_config.get('region')}")

        # Validate primitives
        for primitive_name, primitive_config in package.primitives.items():
            if not primitive_config.get("enabled"):
                errors.append(f"primitive {primitive_name} must be enabled")

        # Validate tool schemas
        for i, tool in enumerate(package.tools):
            if "name" not in tool:
                errors.append(f"tool[{i}] missing 'name' field")

            if "type" not in tool:
                errors.append(f"tool[{i}] missing 'type' field")

            if tool.get("type") == "mcp":
                if "mcpConfig" not in tool:
                    errors.append(f"tool[{tool.get('name')}] MCP tools require 'mcpConfig'")

        if errors:
            safe_log(f"Package validation failed with {len(errors)} errors")

        return errors

    def package_to_json(self, package: AgentCorePackage) -> str:
        """
        Serialize package to JSON for deployment.

        Args:
            package: The agent package to serialize

        Returns:
            JSON string representation

        Raises:
            ValidationError: if package is invalid
        """
        # Validate before serializing
        errors = self.validate_package(package)
        if errors:
            raise ValidationError(
                f"Package validation failed: {', '.join(errors)}"
            )

        return package.to_json()


def package_agent_for_deployment(
    agent_id: str,
    version_id: str,
    system_prompt: str,
    model: Optional[str] = None,
    configured_mcps: Optional[List[Dict[str, Any]]] = None,
    custom_mcps: Optional[List[Dict[str, Any]]] = None,
    agentpress_tools: Optional[Dict[str, Any]] = None,
    triggers: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[AgentCoreConfig] = None,
) -> AgentCorePackage:
    """
    Convenience function to package an agent for AgentCore deployment.

    This is the main entry point for converting Kortix agents to AgentCore format.

    Args:
        agent_id: Agent identifier
        version_id: Version identifier
        system_prompt: Agent system prompt/instructions
        model: LLM model identifier
        configured_mcps: Configured MCP integrations
        custom_mcps: Custom MCP integrations
        agentpress_tools: AgentPress tool configuration
        triggers: Agent triggers
        metadata: Additional metadata
        config: AgentCore configuration (optional)

    Returns:
        AgentCorePackage ready for deployment

    Raises:
        ValidationError: If agent configuration is invalid
        ConfigurationError: If AgentCore Runtime is not enabled

    Example:
        >>> package = package_agent_for_deployment(
        ...     agent_id="agent-123",
        ...     version_id="version-456",
        ...     system_prompt="You are a helpful assistant.",
        ...     model="anthropic.claude-sonnet-4-20250514",
        ...     agentpress_tools={"browser": {"enabled": True}}
        ... )
        >>> deployment_config = package.to_deployment_config()
    """
    packager = AgentPackager(config=config)
    return packager.package_agent_version(
        agent_id=agent_id,
        version_id=version_id,
        system_prompt=system_prompt,
        model=model,
        configured_mcps=configured_mcps,
        custom_mcps=custom_mcps,
        agentpress_tools=agentpress_tools,
        triggers=triggers,
        metadata=metadata,
    )
